#!/usr/bin/env python3
"""Windowed two-path fit for INDEPENDENT-CLOCK two-source captures (Phase B).

When the two simulators do NOT share a 10 MHz reference, the second path's
relative carrier phase phi(t) drifts across the capture (a few Hz -> a full turn
every tens-to-hundreds of ms). Consequences (see dev_notes/11 SOP):

  * A whole-capture COHERENT average nulls path1: mean_t[exp(j*phi_t)] -> 0, so
    the second path vanishes and check_dense_vs_prompt.py's coherent R(tau) looks
    single-path. Feeding that CSV to fit_two_path.py therefore MISSES path1.
    (The magnitude average mag_mean keeps path1 -- use it as the cheap sanity.)

  * The fix is to fit in short TIME WINDOWS in which phi is ~constant, then
    aggregate. Delay and amplitude ratio are window-invariant physical quantities
    (they must be stable across windows); the relative phase sweeps a full circle
    across windows -- that sweep is itself the confirmation of the drifting clock,
    and its diversity is what makes the two paths separable.

Pipeline:
  1. load dense dump, keep sustained-locked epochs (reuse check_dense_vs_prompt).
  2. per-epoch normalize by tap0 (removes path0's own carrier phase -> path0 is
     phase-static, path1 carries the drift exp(j*phi_t)).
  3. measure the drift rate from the phase increment at a probe tap near path1,
     robustly (circular mean of angle(v_{t+1} conj(v_t)) -- no unwrap), and pick a
     window length so phi rotates < --max-rot-deg within a window.
  4. per window: coherent R(tau) = mean of normalized taps -> fit_two_path.
  5. aggregate delta_m and amp_ratio_db (median + robust MAD std) over windows
     that detect a second path; report recovery vs injected ground truth.

Kernel: pass --kernel <Phase A same-PRN single-source reference CSV>. If omitted,
a synthetic L5-shaped kernel is used with a LOUD warning -- fine for a first
geometry check, but amplitude/asymmetry are only trustworthy with the real
same-PRN baseline (asym is PRN-dominated; do NOT borrow another PRN's kernel).

Examples:
  python3 dev_notes/sim/fit_windowed_twosource.py \
      --dense l5_prn15_delay60m_ratio_m6db_run1..._ch_0.dat.json \
      --kernel cn052_prn15_single_reference_Rtau.png.csv \
      --chip-m 29.3 --delay-m 60 --ratio-db -6 --plot fitwin.png
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_dense_correlator_dump as rd            # noqa: E402
from check_dense_vs_prompt import select_locked      # noqa: E402
import fit_two_path as ftp                            # noqa: E402


def measure_drift(times_s, norm, taps, probe_chip):
    """Robust drift rate [Hz] of path1's relative phase at the probe tap.

    Uses the circular mean of the per-epoch phase increment (angle of
    v_{t+1}*conj(v_t)) weighted by |v|, so it needs no phase unwrapping and is
    stable at low per-epoch SNR. Returns (drift_hz, probe_idx, coherence_frac)
    where coherence_frac in [0,1] is the resultant length (1 = pure rotation)."""
    pidx = int(np.argmin(np.abs(taps - probe_chip)))
    v = norm[:, pidx]
    dt = float(np.median(np.diff(times_s))) if len(times_s) > 1 else 1e-3
    steps = v[1:] * np.conj(v[:-1])
    w = np.abs(v[1:]) * np.abs(v[:-1])
    resultant = np.sum(w * np.exp(1j * np.angle(steps)))
    step_rad = float(np.angle(resultant))
    coh = float(np.abs(resultant) / np.sum(w)) if np.sum(w) > 0 else 0.0
    drift_hz = step_rad / (2.0 * np.pi * dt)
    return drift_hz, pidx, coh, dt


def robust_std(x):
    x = np.asarray(x, dtype=float)
    if x.size < 2:
        return 0.0
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dense", required=True, help="two-source composite dense .dat or .dat.json")
    ap.add_argument("--kernel", help="Phase A same-PRN single-source reference CSV (the kernel K); "
                                     "omit to use a synthetic kernel (geometry-only, LOUD warning)")
    ap.add_argument("--chip-m", type=float, default=29.3, help="chip length in metres (L5=29.3)")
    ap.add_argument("--carrier-hz", type=float, default=1176.45e6,
                    help="carrier frequency for the code<->carrier clock cross-check "
                         "(L5=1176.45e6, L1=1575.42e6, B1I=1561.098e6)")
    ap.add_argument("--delay-m", type=float, help="injected path1 delay [m] ground truth (for scoring)")
    ap.add_argument("--ratio-db", type=float, help="injected path1/path0 amplitude ratio [dB] ground truth")
    ap.add_argument("--cn0-min", type=float, default=35.0)
    ap.add_argument("--lock-min", type=float, default=0.6)
    ap.add_argument("--skip-epochs", type=int, default=0)
    ap.add_argument("--min-lock-run", type=int, default=2000)
    ap.add_argument("--settle-epochs", type=int, default=200)
    ap.add_argument("--max-rot-deg", type=float, default=30.0,
                    help="max relative-phase rotation allowed within one window (sets window length)")
    ap.add_argument("--min-win-epochs", type=int, default=12,
                    help="floor on epochs per window (fit is too noisy below this)")
    ap.add_argument("--probe-chip", type=float, default=None,
                    help="tap [chips] to measure drift at; default = injected delay, else auto (mag_mean 2nd peak)")
    ap.add_argument("--max-delay-chips", type=float, default=None,
                    help="widen the two-path delay search to this many chips (default: cover --delay-m with "
                         "30%% margin, floor 2.5). Prevents silently missing delays > 2.5 chip (~73 m @ L5).")
    ap.add_argument("--plot", help="PNG: whole-capture mag_mean vs coherent + per-window delta/ratio scatter")
    args = ap.parse_args()

    # --- load + lock-select ---
    _, dense_bin, meta = rd.load_metadata(args.dense)
    dense = rd.read_records(dense_bin, meta)
    taps = np.asarray(meta["taps_chips"], dtype=np.float64)
    fs = float(meta.get("sampling_frequency_hz", 20e6))
    zt = int(np.argmin(np.abs(taps)))
    if abs(float(taps[zt])) > 0.05:
        raise SystemExit("no tap within 0.05 chip of 0.0 (nearest=%.3f)" % float(taps[zt]))
    keep, n_seg, n_kept = select_locked(dense, args.cn0_min, args.lock_min, args.skip_epochs,
                                        args.min_lock_run, args.settle_epochs)
    d = dense[keep]
    if len(d) == 0:
        raise SystemExit("no sustained-locked records; lower --min-lock-run or check tracking")
    print("dense records: %d  taps: %d  signal: %s  fs: %.1f MHz"
          % (len(dense), len(taps), meta.get("signal", ""), fs / 1e6))
    print("locked segments: %d total / %d kept; kept records: %d (%.1f%%)"
          % (n_seg, n_kept, len(d), 100.0 * len(d) / len(dense)))

    # --- per-epoch normalize by tap0 (path0 phase-static; path1 carries drift) ---
    iq = d["tap_iq"].astype(np.complex128)             # (Nep, Ntap)
    tap0 = iq[:, zt]
    good = np.abs(tap0) > 0.0
    iq, tap0 = iq[good], tap0[good]
    times = d["sample_counter"][good].astype(np.float64) / fs
    times = times - times[0]
    norm = iq / tap0[:, None]                           # (Nep, Ntap)

    coherent = norm.mean(axis=0)                        # whole-capture coherent (path1 gets nulled)
    mag_mean = (np.abs(iq) / np.abs(tap0)[:, None]).mean(axis=0)  # keeps path1

    # secondary peak of mag_mean must be searched OUTSIDE path0's main lobe, else the
    # lobe shoulder (still ~0.6 at 0.6 chip for an L5 kernel) is mistaken for path1.
    # path0 is phase-static so |coherent| shows its full lobe; take the lobe edge
    # (first tap on the delayed side below 20% of the peak) as the exclusion boundary.
    absc = np.abs(coherent)
    thr = 0.2 * float(absc.max()) if absc.size else 0.0
    edge = 1.5
    for j in range(zt, len(taps)):
        if absc[j] < thr:
            edge = float(taps[j])
            break
    far = taps >= max(0.6, edge)
    if far.any():
        fidx = int(np.argmax(mag_mean[far]))
        sec_chip = float(taps[far][fidx])
        sec_amp = float(mag_mean[far][fidx])
        sec_coh = float(absc[far][fidx])
    else:
        sec_chip = sec_amp = sec_coh = 0.0
    print("\n--- whole-capture diagnostic (independent-clock signature) ---")
    print("path0 main-lobe edge %.2f chip; path1 searched beyond it" % edge)
    print("mag_mean secondary peak: %.2f chip (%.1f m), amp %.3f  <- path1 survives magnitude avg"
          % (sec_chip, sec_chip * args.chip_m, sec_amp))
    print("coherent |R| at that tap: %.3f  <- if << mag_mean, phi is drifting (path1 nulled by coherent avg)"
          % sec_coh)

    # --- drift rate -> window length ---
    probe = args.probe_chip
    if probe is None:
        probe = (args.delay_m / args.chip_m) if args.delay_m else sec_chip
    drift_hz, pidx, coh, dt = measure_drift(times, norm, taps, probe)
    print("\n--- drift estimate (probe tap %.2f chip) ---" % float(taps[pidx]))
    print("phi drift rate: %+.2f Hz  (period %.0f ms)  probe coherence: %.2f"
          % (drift_hz, (1e3 / abs(drift_hz) if abs(drift_hz) > 1e-6 else float("inf")), coh))
    rot_per_epoch = abs(drift_hz) * 2.0 * np.pi * dt          # rad/epoch
    if rot_per_epoch > 1e-9:
        win_ep = int(np.radians(args.max_rot_deg) / rot_per_epoch)
    else:
        win_ep = len(iq)                                      # ~shared clock: one big window
    win_ep = max(args.min_win_epochs, min(win_ep, len(iq)))
    n_win = max(1, len(iq) // win_ep)
    print("window length: %d epochs (~%.0f ms, <= %.0f deg rotation); windows: %d"
          % (win_ep, win_ep * dt * 1e3, args.max_rot_deg, n_win))

    # --- kernel ---
    if args.kernel:
        ktaps, K = ftp.load_reference_csv(args.kernel)
        print("kernel: %s (same-PRN Phase A baseline)" % os.path.basename(args.kernel))
    else:
        ktaps, K = taps.copy(), ftp.synth_kernel(taps)
        print("kernel: SYNTHETIC (no --kernel) -- geometry only; amplitude/asym NOT calibrated. "
              "Capture the same-PRN single-source baseline for quantitative results.")

    # --- per-window coherent fit ---
    # delay search span: cover the injected delay with margin; never silently below
    # fit_two_path's 2.5-chip default (~73 m @ L5), so the grid's 90 m point is not missed.
    if args.max_delay_chips is not None:
        dmax = float(args.max_delay_chips)
    elif args.delay_m is not None:
        dmax = max(2.5, 1.3 * abs(args.delay_m) / args.chip_m)
    else:
        dmax = 2.5
    print("two-path delay search: dmax=%.2f chip (%.0f m)" % (dmax, dmax * args.chip_m))
    rows = []
    for w in range(n_win):
        sl = slice(w * win_ep, (w + 1) * win_ep)
        Yw = norm[sl].mean(axis=0)
        f2 = ftp.fit_two_path(taps, Yw, ktaps, K, dmax=dmax)
        f1 = ftp.fit_one_path(taps, Yw, ktaps, K)
        s = ftp.summarize(f2, f1, Yw, args.chip_m)
        detected = s["resid_drop"] > 0.5 and s["amp_ratio_db"] > -25 and s["delta_chips"] > 0.1
        t_center = (w + 0.5) * win_ep * dt          # window mid-time [s], for the delta(t) drift fit
        rows.append((s["delta_m"], s["amp_ratio_db"], s["phase_deg"], s["resid_drop"], float(detected), t_center))
    rows = np.array(rows, dtype=float)
    det = rows[:, 4] > 0.5
    n_det = int(det.sum())
    print("\n--- per-window two-path fit (%d windows) ---" % n_win)
    print("second path detected in %d / %d windows (%.0f%%)" % (n_det, n_win, 100.0 * n_det / n_win))
    if n_det == 0:
        print("NO window detects a second path -- check probe/kernel, or Delta may be sub-resolution.")
        return

    dm = rows[det, 0]
    ar = rows[det, 1]
    ph = rows[det, 2] % 360.0
    print("delta_m      : median %.1f  robust-std %.1f  (over detecting windows)"
          % (np.median(dm), robust_std(dm)))
    print("amp_ratio_db : median %+.2f  robust-std %.2f" % (np.median(ar), robust_std(ar)))
    print("rel phase    : spans %.0f..%.0f deg (spread %.0f deg) -> %s"
          % (ph.min(), ph.max(), ph.max() - ph.min(),
             "confirms drifting phi (independent clocks)" if (ph.max() - ph.min()) > 90 else "phi ~stable"))

    # --- delta(t) linear model: separate the true delay from inter-Tx clock drift ---
    # Independent Tx clocks drift delta LINEARLY at |carrier_drift|*c/f_carrier; fitting a
    # line separates that slope from the fit noise, and the slope cross-checks the
    # independently-measured carrier drift (code and carrier must see the SAME clock).
    C_M_S = 299792458.0
    tw = rows[det, 5]
    dm_t = rows[det, 0]
    have_line = n_det >= 3 and (tw.max() - tw.min()) > 1e-6
    if have_line:
        A = np.column_stack([np.ones_like(tw), tw])
        intercept, slope = (float(v) for v in np.linalg.lstsq(A, dm_t, rcond=None)[0])
        line_resid = robust_std(dm_t - (intercept + slope * tw))
        t_mid = 0.5 * (tw.min() + tw.max())
        dm_mid = intercept + slope * t_mid
        pred_slope = drift_hz * C_M_S / args.carrier_hz          # m/s from the carrier drift
        ratio = abs(slope) / abs(pred_slope) if abs(pred_slope) > 1e-9 else float("nan")
        print("\n--- delta(t) linear model (independent-clock aware) ---")
        print("delta(t)=a+b*t:  a@t0=%.1f m   b=%+.3f m/s  (%.1f m over the %.1f s span)"
              % (intercept, slope, slope * (tw.max() - tw.min()), tw.max() - tw.min()))
        print("scatter about the line (robust std)=%.1f m  <- true fit noise, clock drift removed" % line_resid)
        print("delta @ capture midpoint=%.1f m" % dm_mid)
        print("--- carrier<->code clock cross-check ---")
        print("carrier drift %+.2f Hz -> predicted |code drift|=%.3f m/s ; measured |b|=%.3f m/s ; ratio=%.2f"
              % (drift_hz, abs(pred_slope), abs(slope), ratio))
        print("  (ratio ~1 => code & carrier see the SAME clock => model self-consistent; "
              "sign is fixed by geometry, verify once empirically)")
    else:
        dm_mid = float(np.median(dm))
        print("\n--- delta(t) linear model: skipped (need >=3 detecting windows spread in time) ---")

    if args.delay_m is not None or args.ratio_db is not None:
        print("\n--- recovery vs ground truth ---")
        if args.delay_m is not None:
            print("delay:  injected %.1f m  recovered(midpoint) %.1f m  error %+.1f m"
                  % (args.delay_m, dm_mid, dm_mid - args.delay_m))
            print("  NOTE: with INDEPENDENT Tx clocks the recovered delay carries an unknown clock DC")
            print("  offset + the drift above; trust the amp ratio and the slope<->carrier cross-check,")
            print("  NOT absolute delay == injected. Shared-clock/real-DAS captures remove this caveat.")
        if args.ratio_db is not None:
            print("ratio:  injected %+.1f dB  recovered %+.2f dB  error %+.2f dB"
                  % (args.ratio_db, np.median(ar), np.median(ar) - args.ratio_db))

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(10, 8))
        ax[0].plot(taps, mag_mean, "o-", ms=3, label="mag_mean (keeps path1)")
        ax[0].plot(taps, np.abs(coherent), "s-", ms=3, label="whole-capture coherent (nulls path1)")
        ax[0].axvline(probe, color="r", ls="--", lw=0.8, label="probe/path1")
        ax[0].set_xlabel("tau [chips]"); ax[0].set_ylabel("|R|")
        ax[0].set_title("independent-clock signature: mag_mean shows path1, coherent does not")
        ax[0].grid(True, alpha=0.3); ax[0].legend()
        ax[1].scatter(rows[det, 5], rows[det, 0], s=12, label="per-window delta")
        if have_line:
            tline = np.array([tw.min(), tw.max()])
            ax[1].plot(tline, intercept + slope * tline, "r-", lw=1.2,
                       label="LS line (b=%.2f m/s)" % slope)
        if args.delay_m is not None:
            ax[1].axhline(args.delay_m, color="g", ls="--", lw=0.8, label="injected delay")
        ax[1].set_xlabel("window center time [s]"); ax[1].set_ylabel("recovered delta [m]")
        ax[1].set_title("delta drifts linearly with the inter-Tx clock (slope <-> carrier drift)")
        ax[1].grid(True, alpha=0.3); ax[1].legend()
        fig.tight_layout(); fig.savefig(args.plot, dpi=150)
        print("\nplot -> %s" % args.plot)


if __name__ == "__main__":
    main()

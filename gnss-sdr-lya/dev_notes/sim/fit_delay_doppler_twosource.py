#!/usr/bin/env python3
"""Delay-Doppler two-source extractor (Phase B) -- separate two same-code paths by a
2-D (delay tau1, Doppler-difference f) matched map instead of a 1-D windowed fit.

WHY this and not the windowed/full-segment fitter:
  The windowed fitter works at ONE drift frequency (a fragile point estimate) and
  averages within short windows. It failed on (a) fast-drift captures (window can't be
  short enough) and (b) merged ~1-chip delays (path1 hides in path0's main-lobe tail),
  while PASSING those cases in synthetic -> the bottleneck is the model-reality gap and
  the lack of a second separation axis, not the fitter's cleverness.

THE IDEA -- use Doppler as the second axis:
  Each path carries a DISTINCT Doppler: on the rig from independent-clock drift, and in
  the real deployment (fixed DAS antennas + MOVING receiver) from the geometry-dependent
  radial velocity to each antenna. Project each epoch's tap vector onto the kernel
  shifted by tau1, then FFT over time:
      g_{tau1}(t) = <iq(.,t), K(.-tau1)> ;  M(tau1,f) = |FFT_t g|
  path0 -> a ridge at its Doppler f0, peaked at tau1=0 (amplitude R(tau1)).
  path1 -> a ridge at its Doppler f1, peaked at tau1=tau1_true (amplitude R(tau1-tau1_true)).
  Static kernel mismatch / path0-tail does NOT drift -> sits at f0 -> excluded by masking
  the f0 band. So path1 is separated from path0 by delay AND Doppler; even when MERGED in
  delay (tau1_true small), f1 != f0 resolves it. The amplitude ratio = peak1/peak0 comes
  out clean (each path is coherently integrated in its own Doppler bin -> no tap0 bias).

Processed per contiguous locked segment (handles gaps + Doppler/clock wander); the delay
must be CONSISTENT across segments to be trusted (the Doppler may move -- that is the
motion/clock trajectory, and is itself confirmation of a real drifting source).

Caveat: this needs f1 != f0. A truly static single antenna (no motion, shared clock)
has f1 = f0 for all paths -> the Doppler axis vanishes -> merged sub-chip is unresolvable
(the bandwidth wall). The real deployment escapes this via receiver motion.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_dense_correlator_dump as rd            # noqa: E402
from check_dense_vs_prompt import select_locked      # noqa: E402
import fit_two_path as ftp                            # noqa: E402


def contiguous_runs(mask):
    runs, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def delay_doppler_map(iq_seg, dt, ktaps, K, taps, tau1_grid):
    """Return (M, freqs) where M[f, tau1] = |FFT_t <iq(.,t), K(.-tau1)>|. A Hann window
    over t curbs the strong path0's spectral leakage so a weaker path1 is not buried."""
    # projection matrix Pk[i,k] = K(taps[k]-tau1_grid[i])
    Pk = np.empty((len(tau1_grid), len(taps)), dtype=np.complex128)
    for i, t1 in enumerate(tau1_grid):
        Pk[i] = ftp.kern_at(ktaps, K, taps - t1)
    g = iq_seg @ np.conj(Pk).T                          # (Nep, n_tau1)
    n = g.shape[0]
    win = np.hanning(n)[:, None] if n >= 8 else np.ones((n, 1))
    G = np.fft.fftshift(np.fft.fft(g * win, axis=0), axes=0)
    freqs = np.fft.fftshift(np.fft.fftfreq(n, d=dt))
    return np.abs(G), freqs


def find_paths(M, freqs, tau1_grid, guard_hz, chip_m, min_delay_chips, allow_negative_delay):
    """path0 = global peak (strongest). path1 = strongest peak with |f - f0| >= guard_hz.
    Returns dict with delays, doppler diff, amp ratio (dB), detection SNR (dB)."""
    p0 = np.unravel_index(int(np.argmax(M)), M.shape)
    f0, peak0 = float(freqs[p0[0]]), float(M[p0[0], p0[1]])
    tau0 = float(tau1_grid[p0[1]])
    off_f0 = np.abs(freqs - f0) >= guard_hz
    if not off_f0.any():
        return None
    if allow_negative_delay:
        delay_cols = np.abs(tau1_grid - tau0) >= min_delay_chips
    else:
        delay_cols = (tau1_grid - tau0) >= min_delay_chips
    if not delay_cols.any():
        return None
    Mo = M[off_f0, :][:, delay_cols]
    fo = freqs[off_f0]
    to = tau1_grid[delay_cols]
    p1 = np.unravel_index(int(np.argmax(Mo)), Mo.shape)
    f1, peak1 = float(fo[p1[0]]), float(Mo[p1[0], p1[1]])
    tau1 = float(to[p1[1]])
    # noise floor = median away from both Doppler ridges
    off_f1 = np.abs(fo - f1) >= guard_hz
    noise = float(np.median(Mo[off_f1, :])) if off_f1.any() else float(np.median(Mo))
    # amplitude ratio from ENERGY in each Doppler band (not peak height): Doppler wander
    # spreads path1's peak over several bins, so peak/peak underestimates it by a few dB;
    # integrating |G|^2 over the band recovers the spread energy. A1/A0 = sqrt(E1/E0).
    band = 3.0 * guard_hz
    def _energy(tau_idx, fc):
        sl = np.abs(freqs - fc) <= band
        return float(np.sum(M[sl, tau_idx] ** 2)) if sl.any() else 0.0
    tau1_idx = int(np.flatnonzero(delay_cols)[p1[1]])
    e0, e1 = _energy(p0[1], f0), _energy(tau1_idx, f1)
    amp_ratio_db = 10.0 * np.log10(e1 / e0) if (e0 > 0 and e1 > 0) else float("nan")
    to_db = lambda a, b: 20.0 * np.log10(a / b) if (b > 0 and a > 0) else float("nan")
    return dict(tau0_chips=tau0, f0_hz=f0, peak0=peak0,
                tau1_chips=tau1, f1_hz=f1, peak1=peak1,
                delta_chips=tau1 - tau0, delta_m=(tau1 - tau0) * chip_m,
                dopp_diff_hz=f1 - f0, amp_ratio_db=amp_ratio_db,
                det_snr_db=to_db(peak1, noise))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dense", required=True, help="two-source composite dense .dat or .dat.json")
    ap.add_argument("--kernel", help="same-PRN single-source reference CSV (kernel K); omit=synthetic")
    ap.add_argument("--chip-m", type=float, default=29.3)
    ap.add_argument("--delay-m", type=float, help="injected path1 delay [m] ground truth (scoring)")
    ap.add_argument("--ratio-db", type=float, help="injected path1/path0 amplitude ratio [dB] (scoring)")
    ap.add_argument("--cn0-min", type=float, default=35.0)
    ap.add_argument("--lock-min", type=float, default=0.6)
    ap.add_argument("--min-lock-run", type=int, default=2000)
    ap.add_argument("--settle-epochs", type=int, default=200)
    ap.add_argument("--segment-s", type=float, default=2.0,
                    help="coherent segment length [s]: within it Doppler must be ~constant "
                         "(<< the wander); across segments results are combined incoherently")
    ap.add_argument("--dmax-chips", type=float, default=None, help="max |delay| searched (default from --delay-m)")
    ap.add_argument("--tau-step", type=float, default=0.05, help="delay grid step [chips]")
    ap.add_argument("--guard-hz", type=float, default=None,
                    help="path0 Doppler-ridge exclusion half-width [Hz] (default = 3/segment_len)")
    ap.add_argument("--det-snr-min", type=float, default=10.0, help="per-segment detection threshold [dB]")
    ap.add_argument("--min-delay-chips", type=float, default=0.15,
                    help="minimum separation from path0 searched for path1 [chips]; default keeps 7 m L5 visible while rejecting path0 residual")
    ap.add_argument("--allow-negative-delay", action="store_true",
                    help="also search second-source delays earlier than path0; default assumes simB delay compensation is positive")
    ap.add_argument("--plot", help="PNG of the delay-Doppler map (first good segment)")
    args = ap.parse_args()

    _, dense_bin, meta = rd.load_metadata(args.dense)
    dense = rd.read_records(dense_bin, meta)
    taps = np.asarray(meta["taps_chips"], dtype=np.float64)
    fs = float(meta.get("sampling_frequency_hz", 20e6))
    keep, n_seg, n_kept = select_locked(dense, args.cn0_min, args.lock_min, 0,
                                        args.min_lock_run, args.settle_epochs)
    if not keep.any():
        raise SystemExit("no sustained-locked records; lower --min-lock-run or check tracking")
    iq_all = dense["tap_iq"].astype(np.complex128)
    t_all = dense["sample_counter"].astype(np.float64) / fs
    dt = float(np.median(np.diff(t_all))) if len(t_all) > 1 else 1e-3
    print("dense records: %d  taps: %d  signal: %s  fs: %.1f MHz  epoch dt: %.3f ms"
          % (len(dense), len(taps), meta.get("signal", ""), fs / 1e6, dt * 1e3))
    print("locked segments: %d total / %d kept" % (n_seg, n_kept))

    if args.kernel:
        ktaps, K = ftp.load_reference_csv(args.kernel)
        print("kernel: %s" % os.path.basename(args.kernel))
    else:
        ktaps, K = taps.copy(), ftp.synth_kernel(taps)
        print("kernel: SYNTHETIC (no --kernel) -- geometry only")

    dmax = args.dmax_chips or (max(3.0, 1.3 * abs(args.delay_m) / args.chip_m) if args.delay_m else 3.5)
    tau1_grid = np.round(np.arange(-1.0, dmax + 1e-9, args.tau_step), 4)
    seg_ep = max(64, int(args.segment_s / dt))
    guard_hz = args.guard_hz if args.guard_hz is not None else 3.0 / (seg_ep * dt)
    print("delay grid: -1.0..%.2f chip step %.2f ; min path1 sep: %.2f chip%s ; segment: %d ep (~%.1f s) ; guard: %.2f Hz"
          % (dmax, args.tau_step, args.min_delay_chips,
             " either side" if args.allow_negative_delay else " positive", seg_ep, seg_ep * dt, guard_hz))

    rows, first_map = [], None
    for (a, b) in contiguous_runs(keep):
        for s in range(a, b, seg_ep):
            e = min(s + seg_ep, b)
            if e - s < max(64, seg_ep // 2):
                continue
            M, freqs = delay_doppler_map(iq_all[s:e], dt, ktaps, K, taps, tau1_grid)
            r = find_paths(M, freqs, tau1_grid, guard_hz, args.chip_m,
                           args.min_delay_chips, args.allow_negative_delay)
            if r is None:
                continue
            rows.append(r)
            if first_map is None and r["det_snr_db"] >= args.det_snr_min:
                first_map = (M, freqs, r)

    if not rows:
        raise SystemExit("no analyzable segments")
    det = [r for r in rows if r["det_snr_db"] >= args.det_snr_min]
    print("\n--- delay-Doppler per-segment (%d segments, %d above %.0f dB) ---"
          % (len(rows), len(det), args.det_snr_min))
    if not det:
        print("VERDICT: NO SECOND SOURCE detected above %.0f dB in any segment "
              "(merged with no Doppler separation, or absent)." % args.det_snr_min)
        return
    dm = np.array([r["delta_m"] for r in det])
    dr = np.array([r["dopp_diff_hz"] for r in det])
    ar = np.array([r["amp_ratio_db"] for r in det])
    sn = np.array([r["det_snr_db"] for r in det])
    delay_med, delay_std = float(np.median(dm)), float(np.std(dm))
    print("delay      : median %.1f m  std %.1f m  (consistency across segments)" % (delay_med, delay_std))
    print("doppler dif: median %+.2f Hz  span %.2f..%.2f Hz  (motion/clock trajectory)"
          % (float(np.median(dr)), float(dr.min()), float(dr.max())))
    print("amp ratio  : median %+.2f dB  (peak1/peak0, tap0-bias-free)" % float(np.median(ar)))
    print("det SNR    : median %.1f dB  (min %.1f, max %.1f)" % (float(np.median(sn)), float(sn.min()), float(sn.max())))

    # verdict: enough detecting segments AND delay consistent (Doppler is allowed to move)
    consistent = delay_std <= max(3.0, 0.1 * args.chip_m)      # <= ~0.1 chip or 3 m
    min_delay_m = args.min_delay_chips * args.chip_m
    boundary_latched = abs(delay_med - min_delay_m) <= max(args.tau_step * args.chip_m * 1.5, 1.0)
    reliable = len(det) >= max(2, len(rows) // 2) and consistent and not boundary_latched
    if reliable:
        print("\nVERDICT: RELIABLE (delay %.1f m, %d/%d segments, delay std %.1f m)"
              % (delay_med, len(det), len(rows), delay_std))
    else:
        why = []
        if len(det) < max(2, len(rows) // 2):
            why.append("only %d/%d segments detect" % (len(det), len(rows)))
        if not consistent:
            why.append("delay inconsistent across segments (std %.1f m) -> likely spurious/multi-solution" % delay_std)
        if boundary_latched:
            why.append("delay latched to the minimum searched separation (%.1f m) -> likely path0-tail/kernel residual, not a resolved source" % min_delay_m)
        print("\nVERDICT: UNRELIABLE / uncertain -- " + "; ".join(why))

    if args.delay_m is not None or args.ratio_db is not None:
        print("\n--- recovery vs ground truth ---")
        if args.delay_m is not None:
            print("delay: injected %.1f m  recovered %.1f m  error %+.1f m" % (args.delay_m, delay_med, delay_med - args.delay_m))
        if args.ratio_db is not None:
            print("ratio: injected %+.1f dB  recovered %+.2f dB  error %+.2f dB"
                  % (args.ratio_db, float(np.median(ar)), float(np.median(ar)) - args.ratio_db))

    if args.plot and first_map is not None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        M, freqs, r = first_map
        fig, ax = plt.subplots(figsize=(10, 6))
        ext = [tau1_grid[0] * args.chip_m, tau1_grid[-1] * args.chip_m, freqs[0], freqs[-1]]
        ax.imshow(20 * np.log10(M / M.max() + 1e-6), aspect="auto", origin="lower",
                  extent=ext, cmap="viridis", vmin=-40, vmax=0)
        ax.plot(r["tau0_chips"] * args.chip_m, r["f0_hz"], "wo", ms=8, label="path0")
        ax.plot(r["tau1_chips"] * args.chip_m, r["f1_hz"], "r^", ms=8, label="path1")
        ax.set_xlabel("delay [m]"); ax.set_ylabel("Doppler [Hz]")
        ax.set_title("delay-Doppler map (dB): path1 separated from path0 on the Doppler axis")
        ax.legend(); fig.tight_layout(); fig.savefig(args.plot, dpi=150)
        print("\nplot -> %s" % args.plot)


if __name__ == "__main__":
    main()

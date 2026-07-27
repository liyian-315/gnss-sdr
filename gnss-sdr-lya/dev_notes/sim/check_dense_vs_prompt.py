#!/usr/bin/env python3
"""Phase A validation: dense tap0 vs main-dump Prompt, and averaged reference R(tau).

Consumes:
  --dense : dense correlator dump (.dat or .dat.json)  [Tracking_XX.dense_correlator_dump]
  --trk   : main tracking dump (.dat)                  [Tracking_XX.dump=true]

Checks (dev_notes/11 Phase A success criteria):
  (3) dense tap@0chip  ~=  main-dump Prompt I/Q, aligned by sample_counter.
      With extend_correlation_symbols=1 both are a single 1 ms prompt, so the
      magnitude ratio should be ~1 and the phase difference ~0 (constant).
  (4) averaged |R(tau)| over the locked segment is a smooth symmetric main peak.
      Also emits a coherent (phase-derotated) reference R(tau) normalized to
      R(0)=1, saved as CSV for later two-source fitting.

Example:
  python3 dev_notes/sim/check_dense_vs_prompt.py \
      --dense ./l1_phaseA_dense_ch_0.dat.json \
      --trk   ./l1_phaseA_trk_ch_0.dat \
      --ref-out l1_phaseA_reference_Rtau.png
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_dense_correlator_dump as rd  # noqa: E402


def integrated_autocorr_time(x, c=5.0):
    """Integrated autocorrelation time tau of a 1-D series (Sokal windowing).

    N_eff = N / tau is the number of effectively-independent samples. Tracking-loop
    epochs are correlated (loop memory ~tens of ms), so tau > 1 and the naive
    SEM = std/sqrt(N) is too optimistic; SEM_eff = std/sqrt(N_eff) corrects it.
    """
    x = np.asarray(x, dtype=float)
    n = x.size
    if n < 8:
        return 1.0
    x = x - x.mean()
    c0 = float(np.dot(x, x) / n)
    if c0 <= 0.0:
        return 1.0
    nfft = 1
    while nfft < 2 * n:
        nfft *= 2
    f = np.fft.rfft(x, nfft)
    acov = np.fft.irfft(f * np.conj(f), nfft)[:n] / n
    rho = acov / c0
    tau, csum = 1.0, 0.0
    for k in range(1, n):
        csum += rho[k]
        tau = 1.0 + 2.0 * csum
        if k >= c * tau:          # Sokal automatic window
            break
        if rho[k] < 0.0:          # stop at end of initial positive sequence
            break
    return max(1.0, float(tau))


def effective_n(mag_matrix, mag_std):
    """Conservative N_eff for a per-epoch x per-tap magnitude matrix: take the
    LARGEST tau_int across the informative taps (smallest N_eff -> honest SEM)."""
    n = mag_matrix.shape[0]
    thr = 0.2 * float(np.max(mag_std)) if mag_std.size else 0.0
    taus = [integrated_autocorr_time(mag_matrix[:, j])
            for j in range(mag_matrix.shape[1]) if mag_std[j] > thr]
    tau = max(taus) if taus else 1.0
    return n / tau, tau


def batch_means_sem(mag_matrix, mag_std, tau):
    """Worst-tap batch-means (blocking) SEM. Block length = ceil(3*tau) so block
    means are ~independent; SEM = std(block_means)/sqrt(B). This does NOT assume
    independent epochs. Returns (worst_sem, n_blocks). Falls back to naive SEM if
    too few blocks."""
    n, ntap = mag_matrix.shape
    L = max(1, int(np.ceil(3.0 * tau)))
    B = n // L
    if B < 2:
        return float(np.max(mag_std) / np.sqrt(max(1, n))), B
    blocks = mag_matrix[:B * L].reshape(B, L, ntap).mean(axis=1)   # (B, ntap)
    sem_tap = blocks.std(axis=0, ddof=1) / np.sqrt(B)
    return float(np.max(sem_tap)), B


# Main GPS/GNSS dll_pll_veml_tracking dump record layout (packed, little-endian).
# Matches dll_pll_veml_tracking.cc::log_data() field-for-field (108 bytes/record).
TRK_DTYPE = np.dtype([
    ("abs_VE", "<f4"), ("abs_E", "<f4"), ("abs_P", "<f4"),
    ("abs_L", "<f4"), ("abs_VL", "<f4"),
    ("prompt_I", "<f4"), ("prompt_Q", "<f4"),
    ("sample_counter", "<u8"),
    ("acc_carrier_phase_rad", "<f4"),
    ("carrier_doppler_hz", "<f4"),
    ("carrier_phase_rate_hz_s", "<f4"),
    ("code_freq_chips", "<f4"),
    ("code_phase_rate_chips_s2", "<f4"),
    ("carr_phase_error_hz", "<f4"),
    ("carr_error_filt_hz", "<f4"),
    ("code_error_chips", "<f4"),
    ("code_error_filt_chips", "<f4"),
    ("cn0_db_hz", "<f4"),
    ("carrier_lock_test", "<f4"),
    ("rem_code_phase_samples", "<f4"),
    ("sample_counter_double", "<f8"),
    ("prn", "<u4"),
    ("tow_ms", "<u8"),
    ("wn", "<u4"),
])


def read_trk_dump(path):
    if TRK_DTYPE.itemsize != 108:
        raise AssertionError("TRK_DTYPE itemsize %d != 108" % TRK_DTYPE.itemsize)
    size = os.path.getsize(path)
    if size % TRK_DTYPE.itemsize != 0:
        raise ValueError("trk file size %d not a multiple of %d (wrong layout?)"
                         % (size, TRK_DTYPE.itemsize))
    return np.fromfile(path, dtype=TRK_DTYPE)


def zero_tap_index(taps):
    idx = int(np.argmin(np.abs(taps)))
    if abs(float(taps[idx])) > 0.05:
        raise SystemExit("no tap within 0.05 chip of 0.0 (nearest=%.3f); "
                         "criterion (3) needs a 0-chip tap" % float(taps[idx]))
    return idx


def select_locked(dense, cn0_min, lock_min, skip, min_run, settle, guard_before_loss=0):
    """Keep only records inside SUSTAINED locked runs, excluding settling/transients.

    Returns (mask, n_segments_total, n_segments_kept). A run that fails the CN0 or
    carrier-lock gate breaks the segment, so a capture that reacquires several
    times (e.g. an unstable L5 run) contributes only its stable stretches, and the
    caller can see how much was dropped instead of silently averaging transients.

    guard_before_loss drops the last N records of a kept segment ONLY when that
    segment ends at a real lock failure (base[j] is False), not at end-of-file
    (j == len). This removes epochs that may be drifting toward an imminent loss
    (and could bias R(tau)) without penalizing a segment that simply ran off the
    end of the capture.
    """
    base = ((dense["cn0_snv_db_hz"] >= cn0_min) & (dense["carrier_lock_test"] >= lock_min)).copy()
    if skip > 0:
        base[:skip] = False
    keep = np.zeros(len(base), dtype=bool)
    n_seg = n_kept = 0
    i, n = 0, len(base)
    while i < n:
        if not base[i]:
            i += 1
            continue
        j = i
        while j < n and base[j]:
            j += 1
        n_seg += 1
        if (j - i) >= min_run:
            n_kept += 1
            start = i + settle
            end = j - guard_before_loss if (guard_before_loss > 0 and j < n) else j
            if start < end:
                keep[start:end] = True
        i = j
    return keep, n_seg, n_kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dense", required=True, help="dense .dat or .dat.json")
    ap.add_argument("--trk", help="main tracking .dat (optional; enables criterion 3 tap0==Prompt). "
                                  "Omit for track_pilot runs, where the main dump Prompt is the DATA "
                                  "component while dense taps sample the PILOT -> they legitimately differ.")
    ap.add_argument("--cn0-min", type=float, default=35.0, help="lock filter: min CN0 dB-Hz")
    ap.add_argument("--lock-min", type=float, default=0.6, help="lock filter: min carrier_lock_test")
    ap.add_argument("--skip-epochs", type=int, default=0, help="drop first N dense records globally")
    ap.add_argument("--min-lock-run", type=int, default=2000,
                    help="keep only contiguous locked runs of >=N dense records (reject reacquisition transients)")
    ap.add_argument("--settle-epochs", type=int, default=200,
                    help="drop first N records of EACH kept locked run (loop settling)")
    ap.add_argument("--guard-before-loss", type=int, default=0,
                    help="drop last N records of each segment that ends at a REAL lock failure "
                         "(not end-of-file); guards against pre-loss degraded epochs biasing R(tau)")
    ap.add_argument("--ref-out", help="PNG path for the averaged reference R(tau)")
    ap.add_argument("--ref-csv", help="CSV path for the coherent reference R(tau) (default: <ref-out>.csv)")
    args = ap.parse_args()

    # --- load dense ---
    _, dense_bin, meta = rd.load_metadata(args.dense)
    dense = rd.read_records(dense_bin, meta)
    taps = np.asarray(meta["taps_chips"], dtype=np.float64)
    zt = zero_tap_index(taps)
    print("dense records: %d  taps: %d  zero-tap idx: %d (%.3f chip)  signal: %s"
          % (len(dense), len(taps), zt, taps[zt], meta.get("signal", "")))

    # --- load main trk dump (optional; only needed for criterion 3) ---
    trk = read_trk_dump(args.trk) if args.trk else None
    if trk is not None:
        print("trk records:   %d" % len(trk))

    # --- sustained-lock selection on dense records ---
    keep, n_seg, n_kept = select_locked(dense, args.cn0_min, args.lock_min, args.skip_epochs,
                                        args.min_lock_run, args.settle_epochs, args.guard_before_loss)
    dense_ok = dense[keep]
    kept_frac = len(dense_ok) / max(1, len(dense))
    gated = int(((dense["cn0_snv_db_hz"] >= args.cn0_min) & (dense["carrier_lock_test"] >= args.lock_min)).sum())
    print("lock gate (CN0>=%.0f, lock>=%.2f): %d/%d records; locked segments: %d total, %d kept (>=%d rec)"
          % (args.cn0_min, args.lock_min, gated, len(dense), n_seg, n_kept, args.min_lock_run))
    print("kept after settle=%d, min-run=%d, guard-before-loss=%d: %d records (%.1f%% of file)"
          % (args.settle_epochs, args.min_lock_run, args.guard_before_loss, len(dense_ok), 100.0 * kept_frac))
    if n_seg > n_kept:
        print("  note: %d short/transient segment(s) rejected — reacquisition churn, not averaged"
              % (n_seg - n_kept))
    if kept_frac < 0.2:
        print("  note: kept_fraction %.1f%% is low (tracking churn) — a diagnostic only; "
              "R(tau) quality is set by N_kept + worst-tap SEM (Criterion 4 below)" % (100.0 * kept_frac))
    if len(dense_ok) == 0:
        raise SystemExit("no sustained-locked records survived; lower --min-lock-run or check tracking stability")

    # ---------- Criterion (3): dense tap0 vs main-dump Prompt ----------
    if trk is None:
        print("\n--- Criterion (3): skipped (no --trk) ---")
    else:
        trk_prompt = {int(s): complex(float(i), float(q))
                      for s, i, q in zip(trk["sample_counter"], trk["prompt_I"], trk["prompt_Q"])}
        ratios, dphases, matched = [], [], 0
        for row in dense_ok:
            p = trk_prompt.get(int(row["sample_counter"]))
            if p is None:
                continue
            matched += 1
            tap0 = complex(row["tap_iq"][zt])
            if abs(p) > 0.0:
                ratios.append(abs(tap0) / abs(p))
                dphases.append(np.angle(tap0 * np.conj(p)))
        print("\n--- Criterion (3): dense tap0  vs  main-dump Prompt ---")
        print("matched-by-sample_counter epochs: %d / %d" % (matched, len(dense_ok)))
        if matched == 0:
            print("!! no sample_counter matches — check decimation=1 and same run")
        else:
            ratios = np.asarray(ratios)
            dphases = np.asarray(dphases)
            print("|tap0|/|Prompt|   median=%.4f  (expect ~1.0)   IQR=[%.4f, %.4f]"
                  % (np.median(ratios), np.percentile(ratios, 25), np.percentile(ratios, 75)))
            print("phase(tap0)-phase(Prompt)  median=%+.4f rad (%.2f deg)   std=%.4f rad"
                  % (np.median(dphases), np.degrees(np.median(dphases)), np.std(dphases)))
            ok3 = abs(np.median(ratios) - 1.0) < 0.10 and abs(np.median(dphases)) < 0.10
            print("verdict (3): %s" % ("PASS" if ok3 else "REVIEW — ratio/phase off, see notes"))

    # ---------- Criterion (4): averaged reference R(tau) ----------
    iq = dense_ok["tap_iq"].astype(np.complex128)           # (Nep, Ntap)
    tap0 = iq[:, zt]
    good = np.abs(tap0) > 0.0
    iq, tap0 = iq[good], tap0[good]
    # normalize each epoch by its own tap0 (amplitude + phase) -> shape only, R(0)=1
    norm = iq / tap0[:, None]
    coherent = norm.mean(axis=0)                            # complex reference R(tau)
    magm = np.abs(iq) / np.abs(tap0)[:, None]               # (Nep, Ntap) per-epoch shape
    mag_mean = magm.mean(axis=0)
    mag_std = magm.std(axis=0)
    peak_idx = int(np.argmax(np.abs(coherent)))
    print("\n--- Criterion (4): averaged reference R(tau) over %d epochs ---" % len(iq))
    print("coherent |R| peak at %.3f chip (expect ~0.0)" % taps[peak_idx])
    print("coherent R(0)=%.3f%+.3fj (expect ~1+0j after normalization)"
          % (coherent[zt].real, coherent[zt].imag))
    # symmetry: compare +/- tau magnitude
    asym = float(np.max(np.abs(np.abs(coherent) - np.abs(coherent)[::-1])))
    print("max |R(+tau)|-|R(-tau)| asymmetry = %.4f (small=symmetric, clean single path)" % asym)
    # precision: correlation-corrected. Epochs are temporally correlated, so the
    # naive SEM=std/sqrt(N) is too optimistic; report N_eff (autocorr) and the
    # blocking (batch-means) SEM, which does not assume independence.
    n_kept_c4 = len(iq)
    sem_naive = float(np.max(mag_std) / np.sqrt(n_kept_c4)) if n_kept_c4 else float("nan")
    n_eff, tau_int = effective_n(magm, mag_std)
    sem_worst, n_blocks = batch_means_sem(magm, mag_std, tau_int)
    print("precision (correlation-corrected):")
    print("  tau_int=%.1f epochs  N_kept=%d  N_eff=%.0f  n_blocks=%d" % (tau_int, n_kept_c4, n_eff, n_blocks))
    print("  worst-tap SEM: naive=%.5f  blocking=%.5f  (blocking is honest; naive under-estimates)"
          % (sem_naive, sem_worst))
    print("  -> sigma(asym) ~ sqrt(2)*SEM_block = %.5f  (error-propagated; calibrate vs cross-run std)"
          % (np.sqrt(2.0) * sem_worst))

    ref_csv = args.ref_csv or (args.ref_out + ".csv" if args.ref_out else None)
    if ref_csv:
        hdr = "tap_chips,coherent_re,coherent_im,mag_mean,mag_std"
        data = np.column_stack([taps, coherent.real, coherent.imag, mag_mean, mag_std])
        with open(ref_csv, "w") as fh:
            # '#' metadata line (aggregator reads it; np.genfromtxt skips it)
            fh.write("# kept_records=%d total_records=%d kept_fraction=%.4f n_segments_kept=%d "
                     "tau_int=%.2f n_eff=%.1f n_blocks=%d sem_block_worst=%.6f asym=%.5f "
                     "cn0_min=%.1f lock_min=%.2f min_lock_run=%d settle=%d guard_before_loss=%d "
                     "signal=%s fs_hz=%s\n"
                     % (len(dense_ok), len(dense), kept_frac, n_kept,
                        tau_int, n_eff, n_blocks, sem_worst, asym,
                        args.cn0_min, args.lock_min, args.min_lock_run, args.settle_epochs,
                        args.guard_before_loss, meta.get("signal", "?"), meta.get("sampling_frequency_hz", "?")))
            fh.write(hdr + "\n")
            np.savetxt(fh, data, delimiter=",")
        print("reference R(tau) CSV -> %s" % ref_csv)

    if args.ref_out:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
        ax[0].plot(taps, np.abs(coherent), marker=".", label="coherent |R|")
        ax[0].fill_between(taps, mag_mean - mag_std, mag_mean + mag_std, alpha=0.2, label="|corr| mean±std")
        ax[0].axvline(0.0, color="r", ls="--", lw=0.8)
        ax[0].set_ylabel("normalized |R(tau)|")
        ax[0].set_title("Phase A reference R(tau)  signal=%s  epochs=%d" % (meta.get("signal", ""), len(iq)))
        ax[0].grid(True, alpha=0.3); ax[0].legend()
        ax[1].plot(taps, np.angle(coherent), marker=".")
        ax[1].axvline(0.0, color="r", ls="--", lw=0.8)
        ax[1].set_xlabel("tap offset [chips]"); ax[1].set_ylabel("phase [rad]")
        ax[1].grid(True, alpha=0.3)
        fig.tight_layout(); fig.savefig(args.ref_out, dpi=150)
        print("reference R(tau) plot -> %s" % args.ref_out)


if __name__ == "__main__":
    main()

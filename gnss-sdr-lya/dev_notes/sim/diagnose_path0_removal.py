#!/usr/bin/env python3
"""Diagnostic path0-removal experiment for Phase B dense correlator dumps.

This is intentionally not a production two-source fitter. It answers one
specific question: after fitting and subtracting the dominant path0 from each
epoch's dense complex tap vector, does a known path1 delay become visible in the
delay-Doppler map?

The path0 model is conservative:

    y_epoch(tau) ~= c0_epoch * K(tau - tau0_epoch)

where K is the same-PRN single-source kernel from Phase A. Fitting c0 per epoch
absorbs carrier phase and amplitude wobble; optionally searching a small tau0
range absorbs tracking-loop code jitter. The residual is then passed through the
same delay-Doppler projection used by fit_delay_doppler_twosource.py.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_delay_doppler_twosource as dd  # noqa: E402
import fit_two_path as ftp                # noqa: E402
import read_dense_correlator_dump as rd   # noqa: E402
from check_dense_vs_prompt import select_locked  # noqa: E402


def fit_and_subtract_path0(iq, taps, ktaps, K, tau0_grid):
    """Fit one shifted kernel per epoch and subtract it.

    Returns residual_iq, tau0_by_epoch, c0_by_epoch, rel_resid_by_epoch.
    """
    templates = np.empty((len(tau0_grid), len(taps)), dtype=np.complex128)
    den = np.empty(len(tau0_grid), dtype=np.float64)
    for i, tau0 in enumerate(tau0_grid):
        templates[i] = ftp.kern_at(ktaps, K, taps - tau0)
        den[i] = float(np.vdot(templates[i], templates[i]).real)
        if den[i] <= 0:
            den[i] = np.nan

    residual = np.empty_like(iq)
    tau0 = np.empty(iq.shape[0], dtype=np.float64)
    coeff = np.empty(iq.shape[0], dtype=np.complex128)
    rel_resid = np.empty(iq.shape[0], dtype=np.float64)

    y_norm = np.linalg.norm(iq, axis=1)
    for n, y in enumerate(iq):
        best_i, best_c, best_r = 0, 0j, np.inf
        for i, tmpl in enumerate(templates):
            if not np.isfinite(den[i]):
                continue
            c = np.vdot(tmpl, y) / den[i]
            r = float(np.linalg.norm(y - c * tmpl))
            if r < best_r:
                best_i, best_c, best_r = i, c, r
        residual[n] = y - best_c * templates[best_i]
        tau0[n] = tau0_grid[best_i]
        coeff[n] = best_c
        rel_resid[n] = best_r / y_norm[n] if y_norm[n] > 0 else np.nan
    return residual, tau0, coeff, rel_resid


def map_target_stats(iq_all, keep, dt, ktaps, K, taps, tau_grid, chip_m,
                     segment_s, target_m, target_band_m, guard_hz):
    seg_ep = max(64, int(segment_s / dt))
    if guard_hz is None:
        guard_hz = 3.0 / (seg_ep * dt)
    target_cols = np.where(np.abs(tau_grid * chip_m - target_m) <= target_band_m)[0]
    if len(target_cols) == 0:
        raise ValueError("target band %.1f +/- %.1f m is outside delay grid" % (target_m, target_band_m))

    rows = []
    first = None
    for a, b in dd.contiguous_runs(keep):
        for s in range(a, b, seg_ep):
            e = min(s + seg_ep, b)
            if e - s < max(64, seg_ep // 2):
                continue
            M, freqs = dd.delay_doppler_map(iq_all[s:e], dt, ktaps, K, taps, tau_grid)
            p0 = np.unravel_index(int(np.argmax(M)), M.shape)
            f0 = float(freqs[p0[0]])
            off_f0 = np.abs(freqs - f0) >= guard_hz
            Mo = M[off_f0, :]
            fo = freqs[off_f0]
            best = np.unravel_index(int(np.argmax(Mo)), Mo.shape)
            best_amp = float(Mo[best])
            best_delay = float(tau_grid[best[1]] * chip_m)
            best_f = float(fo[best[0]])
            Mt = Mo[:, target_cols]
            tgt = np.unravel_index(int(np.argmax(Mt)), Mt.shape)
            tgt_amp = float(Mt[tgt])
            tgt_delay = float(tau_grid[target_cols[tgt[1]]] * chip_m)
            tgt_f = float(fo[tgt[0]])
            noise = float(np.median(Mo))
            tgt_snr = 20.0 * np.log10(tgt_amp / noise) if noise > 0 else float("nan")
            rel_db = 20.0 * np.log10(tgt_amp / best_amp) if best_amp > 0 else float("nan")
            rows.append(dict(best_delay_m=best_delay, best_f_hz=best_f,
                             target_delay_m=tgt_delay, target_f_hz=tgt_f,
                             target_vs_best_db=rel_db, target_snr_db=tgt_snr))
            if first is None:
                first = (M, freqs, p0, best, target_cols, tgt)
    return rows, first, guard_hz


def print_stats(label, rows):
    if not rows:
        print("%s: no analyzable segments" % label)
        return
    arr = {k: np.asarray([r[k] for r in rows], dtype=float) for k in rows[0]}
    print("\n--- %s ---" % label)
    print("segments: %d" % len(rows))
    print("best off-ridge delay: median %.1f m, range %.1f..%.1f m" %
          (np.median(arr["best_delay_m"]), np.min(arr["best_delay_m"]), np.max(arr["best_delay_m"])))
    print("target-band delay:    median %.1f m, range %.1f..%.1f m" %
          (np.median(arr["target_delay_m"]), np.min(arr["target_delay_m"]), np.max(arr["target_delay_m"])))
    print("target vs best:       median %.1f dB, max %.1f dB" %
          (np.median(arr["target_vs_best_db"]), np.max(arr["target_vs_best_db"])))
    print("target-band SNR:      median %.1f dB, range %.1f..%.1f dB" %
          (np.median(arr["target_snr_db"]), np.min(arr["target_snr_db"]), np.max(arr["target_snr_db"])))
    for i, r in enumerate(rows[:6], 1):
        print("seg%02d best=%5.1fm@%+.1fHz target=%5.1fm@%+.1fHz target-best=%+.1fdB targetSNR=%.1fdB" %
              (i, r["best_delay_m"], r["best_f_hz"], r["target_delay_m"],
               r["target_f_hz"], r["target_vs_best_db"], r["target_snr_db"]))


def plot_first(first, tau_grid, chip_m, plot_out, title):
    if first is None or not plot_out:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    M, freqs, p0, best, target_cols, tgt = first
    fig, ax = plt.subplots(figsize=(10, 6))
    extent = [tau_grid[0] * chip_m, tau_grid[-1] * chip_m, freqs[0], freqs[-1]]
    ax.imshow(20 * np.log10(M / M.max() + 1e-6), aspect="auto", origin="lower",
              extent=extent, cmap="viridis", vmin=-40, vmax=0)
    ax.plot(tau_grid[p0[1]] * chip_m, freqs[p0[0]], "wo", ms=7, label="strongest")
    ax.plot(tau_grid[best[1]] * chip_m, freqs[best[0]], "r^", ms=7, label="best off-ridge")
    ax.plot(tau_grid[target_cols[tgt[1]]] * chip_m, freqs[tgt[0]], "cx", ms=8, label="target band best")
    ax.set_xlabel("delay [m]")
    ax.set_ylabel("Doppler [Hz]")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(plot_out, dpi=150)
    print("plot -> %s" % plot_out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dense", required=True)
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--chip-m", type=float, default=29.3)
    ap.add_argument("--target-m", type=float, required=True)
    ap.add_argument("--target-band-m", type=float, default=5.0)
    ap.add_argument("--cn0-min", type=float, default=45.0)
    ap.add_argument("--lock-min", type=float, default=0.6)
    ap.add_argument("--min-lock-run", type=int, default=1000)
    ap.add_argument("--settle-epochs", type=int, default=200)
    ap.add_argument("--segment-s", type=float, default=2.0)
    ap.add_argument("--dmax-chips", type=float, default=3.0)
    ap.add_argument("--tau-step", type=float, default=0.05)
    ap.add_argument("--guard-hz", type=float, default=None)
    ap.add_argument("--path0-search-chips", default="-0.25:0.025:0.25",
                    help="tau0 search grid for per-epoch path0 subtraction")
    ap.add_argument("--plot-prefix", help="write *_before.png and *_after.png")
    args = ap.parse_args()

    _, dense_bin, meta = rd.load_metadata(args.dense)
    dense = rd.read_records(dense_bin, meta)
    taps = np.asarray(meta["taps_chips"], dtype=np.float64)
    fs = float(meta.get("sampling_frequency_hz", 20e6))
    iq = dense["tap_iq"].astype(np.complex128)
    t = dense["sample_counter"].astype(np.float64) / fs
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 1e-3
    keep, n_seg, n_kept = select_locked(dense, args.cn0_min, args.lock_min, 0,
                                        args.min_lock_run, args.settle_epochs)
    if not keep.any():
        raise SystemExit("no sustained-locked records")

    ktaps, K = ftp.load_reference_csv(args.kernel)
    tau_grid = np.round(np.arange(-1.0, args.dmax_chips + 1e-9, args.tau_step), 4)
    parts = [float(x) for x in args.path0_search_chips.split(":")]
    if len(parts) != 3:
        raise SystemExit("--path0-search-chips must be start:step:stop")
    tau0_grid = np.round(np.arange(parts[0], parts[2] + 0.5 * parts[1], parts[1]), 5)

    print("dense records: %d taps: %d fs: %.1f MHz dt: %.3f ms" %
          (len(dense), len(taps), fs / 1e6, dt * 1e3))
    print("locked segments: %d total / %d kept" % (n_seg, n_kept))
    print("kernel: %s" % os.path.basename(args.kernel))
    print("path0 tau search: %.3f..%.3f chips step %.3f (%d candidates)" %
          (tau0_grid[0], tau0_grid[-1], tau0_grid[1] - tau0_grid[0] if len(tau0_grid) > 1 else 0.0, len(tau0_grid)))

    before_rows, before_first, guard_hz = map_target_stats(
        iq, keep, dt, ktaps, K, taps, tau_grid, args.chip_m,
        args.segment_s, args.target_m, args.target_band_m, args.guard_hz)
    print_stats("before path0 removal", before_rows)

    residual, tau0, c0, rel = fit_and_subtract_path0(iq, taps, ktaps, K, tau0_grid)
    kept_tau0 = tau0[keep]
    kept_rel = rel[keep]
    print("\npath0 fit on kept epochs:")
    print("tau0 median %.4f chips, range %.4f..%.4f chips" %
          (np.median(kept_tau0), np.min(kept_tau0), np.max(kept_tau0)))
    print("relative residual median %.4f, p90 %.4f" %
          (np.median(kept_rel), np.percentile(kept_rel, 90)))

    after_rows, after_first, _ = map_target_stats(
        residual, keep, dt, ktaps, K, taps, tau_grid, args.chip_m,
        args.segment_s, args.target_m, args.target_band_m, guard_hz)
    print_stats("after path0 removal", after_rows)

    if args.plot_prefix:
        plot_first(before_first, tau_grid, args.chip_m, args.plot_prefix + "_before.png",
                   "delay-Doppler before path0 removal")
        plot_first(after_first, tau_grid, args.chip_m, args.plot_prefix + "_after.png",
                   "delay-Doppler after per-epoch path0 removal")


if __name__ == "__main__":
    main()

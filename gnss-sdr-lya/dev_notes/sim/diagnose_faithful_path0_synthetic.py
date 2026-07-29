#!/usr/bin/env python3
"""Faithful-path0 synthetic diagnostic for Phase B.

The earlier synthetic tests used an ideal path0 ridge, so they under-represented
the real tracking-loop / kernel-mismatch residue that dominates the real
delay-Doppler maps. This tool injects a known path1 into two synthetic worlds:

1. clean path0: c0(t) * K(tau)
2. faithful path0: the actual A-only dense tap vectors, preserving real path0
   texture, phase wobble, code jitter, and kernel mismatch

If the extractor succeeds on (1) but fails on (2), the failure is not a missing
threshold. It is the strong path0 residual field.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diagnose_path0_removal as p0diag  # noqa: E402
import fit_two_path as ftp               # noqa: E402
import read_dense_correlator_dump as rd  # noqa: E402
from check_dense_vs_prompt import select_locked  # noqa: E402


def load_locked_dense(path, cn0_min, lock_min, min_lock_run, settle_epochs):
    _, dense_bin, meta = rd.load_metadata(path)
    dense = rd.read_records(dense_bin, meta)
    taps = np.asarray(meta["taps_chips"], dtype=np.float64)
    fs = float(meta.get("sampling_frequency_hz", 20e6))
    keep, n_seg, n_kept = select_locked(dense, cn0_min, lock_min, 0,
                                        min_lock_run, settle_epochs)
    if not keep.any():
        raise SystemExit("no sustained locked records in %s" % path)
    iq = dense["tap_iq"].astype(np.complex128)[keep]
    t = dense["sample_counter"].astype(np.float64)[keep] / fs
    t = t - t[0]
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 1e-3
    return iq, t, dt, taps, fs, n_seg, n_kept


def estimate_c0(iq, taps, ktaps, K):
    k0 = ftp.kern_at(ktaps, K, taps)
    den = float(np.vdot(k0, k0).real)
    if den <= 0:
        raise ValueError("zero kernel energy")
    return (iq @ np.conj(k0)) / den


def inject_path1(base_iq, times, taps, ktaps, K, delay_m, chip_m, ratio_db, drift_hz, phase_deg):
    delay_chips = delay_m / chip_m
    k1 = ftp.kern_at(ktaps, K, taps - delay_chips)
    c0 = estimate_c0(base_iq, taps, ktaps, K)
    amp = np.median(np.abs(c0)) * (10.0 ** (ratio_db / 20.0))
    mod = np.exp(1j * (2.0 * np.pi * drift_hz * times + np.radians(phase_deg)))
    return base_iq + (amp * mod)[:, None] * k1[None, :]


def run_case(label, iq, keep, dt, ktaps, K, taps, tau_grid, args):
    print("\n========== %s ==========" % label)
    rows, first, guard_hz = p0diag.map_target_stats(
        iq, keep, dt, ktaps, K, taps, tau_grid, args.chip_m,
        args.segment_s, args.target_m, args.target_band_m, None)
    p0diag.print_stats("delay-Doppler", rows)

    residual, tau0, _c0, rel = p0diag.fit_and_subtract_path0(
        iq, taps, ktaps, K, args.path0_tau_grid)
    print("\npath0 fit:")
    print("tau0 median %.4f chips, range %.4f..%.4f chips" %
          (np.median(tau0), np.min(tau0), np.max(tau0)))
    print("relative residual median %.4f, p90 %.4f" %
          (np.median(rel), np.percentile(rel, 90)))
    rows2, first2, _ = p0diag.map_target_stats(
        residual, keep, dt, ktaps, K, taps, tau_grid, args.chip_m,
        args.segment_s, args.target_m, args.target_band_m, guard_hz)
    p0diag.print_stats("after path0 removal", rows2)

    if args.plot_prefix:
        safe = label.lower().replace(" ", "_")
        p0diag.plot_first(first, tau_grid, args.chip_m,
                          "%s_%s_before.png" % (args.plot_prefix, safe),
                          "%s before path0 removal" % label)
        p0diag.plot_first(first2, tau_grid, args.chip_m,
                          "%s_%s_after.png" % (args.plot_prefix, safe),
                          "%s after path0 removal" % label)


def parse_grid(spec):
    parts = [float(x) for x in spec.split(":")]
    if len(parts) != 3:
        raise SystemExit("grid must be start:step:stop")
    return np.round(np.arange(parts[0], parts[2] + 0.5 * parts[1], parts[1]), 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path0-dense", required=True, help="A-only dense .dat.json used as faithful path0")
    ap.add_argument("--kernel", required=True, help="same-PRN A-only reference CSV")
    ap.add_argument("--chip-m", type=float, default=29.3)
    ap.add_argument("--target-m", type=float, required=True, help="injected path1 delay and diagnostic target")
    ap.add_argument("--target-band-m", type=float, default=5.0)
    ap.add_argument("--ratio-db", type=float, default=-6.0)
    ap.add_argument("--drift-hz", type=float, default=250.0)
    ap.add_argument("--phase-deg", type=float, default=0.0)
    ap.add_argument("--max-epochs", type=int, default=20000)
    ap.add_argument("--cn0-min", type=float, default=45.0)
    ap.add_argument("--lock-min", type=float, default=0.6)
    ap.add_argument("--min-lock-run", type=int, default=1000)
    ap.add_argument("--settle-epochs", type=int, default=200)
    ap.add_argument("--segment-s", type=float, default=2.0)
    ap.add_argument("--dmax-chips", type=float, default=3.0)
    ap.add_argument("--tau-step", type=float, default=0.05)
    ap.add_argument("--path0-search-chips", default="-0.25:0.025:0.25")
    ap.add_argument("--plot-prefix")
    args = ap.parse_args()

    ktaps, K = ftp.load_reference_csv(args.kernel)
    real_iq, times, dt, taps, fs, n_seg, n_kept = load_locked_dense(
        args.path0_dense, args.cn0_min, args.lock_min,
        args.min_lock_run, args.settle_epochs)
    n = min(len(real_iq), args.max_epochs)
    real_iq = real_iq[:n]
    times = times[:n]
    keep = np.ones(n, dtype=bool)
    args.path0_tau_grid = parse_grid(args.path0_search_chips)
    tau_grid = np.round(np.arange(-1.0, args.dmax_chips + 1e-9, args.tau_step), 4)

    c0 = estimate_c0(real_iq, taps, ktaps, K)
    k0 = ftp.kern_at(ktaps, K, taps)
    clean_iq = c0[:, None] * k0[None, :]
    clean_syn = inject_path1(clean_iq, times, taps, ktaps, K,
                             args.target_m, args.chip_m, args.ratio_db,
                             args.drift_hz, args.phase_deg)
    real_syn = inject_path1(real_iq, times, taps, ktaps, K,
                            args.target_m, args.chip_m, args.ratio_db,
                            args.drift_hz, args.phase_deg)

    print("path0 dense: %s" % args.path0_dense)
    print("kernel: %s" % os.path.basename(args.kernel))
    print("locked source segments: %d total / %d kept" % (n_seg, n_kept))
    print("epochs used: %d  fs %.1f MHz  dt %.3f ms" % (n, fs / 1e6, dt * 1e3))
    print("inject path1: delay %.1f m (%.3f chip), ratio %.1f dB, drift %+.2f Hz, phase %.1f deg" %
          (args.target_m, args.target_m / args.chip_m, args.ratio_db, args.drift_hz, args.phase_deg))

    run_case("clean synthetic", clean_syn, keep, dt, ktaps, K, taps, tau_grid, args)
    run_case("faithful path0 synthetic", real_syn, keep, dt, ktaps, K, taps, tau_grid, args)


if __name__ == "__main__":
    main()

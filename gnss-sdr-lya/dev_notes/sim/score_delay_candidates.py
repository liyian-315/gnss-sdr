#!/usr/bin/env python3
"""Score candidate second-source delays from dense correlator residuals.

This is a diagnostic/benchmark helper for Phase B.  It does not claim a final
two-source fit.  It asks a simpler question: after subtracting the best static
path0 kernel, which delayed tap bands carry coherent residual energy?

The output is useful when the full fitter is attracted by path0-tail artifacts:
if the injected 30 m / 60 m delay is not near the top of this evidence curve,
the data or model cannot support a reliable separation yet.
"""

import argparse
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_drift_modulated_twosource as fdm  # noqa: E402
import fit_two_path as ftp  # noqa: E402


def robust_median_abs(x):
    x = np.asarray(x)
    if x.size == 0:
        return float("nan")
    return float(np.median(np.abs(x)))


def score_delta(taps, residual, times, ktaps, K, tau0, delta, drift_hz,
                band_half_chip, band_min_frac, chip_m):
    k1 = ftp.kern_at(ktaps, K, taps - tau0 - delta)
    support = np.abs(k1) >= band_min_frac * max(float(np.max(np.abs(k1))), 1e-12)
    band = np.abs(taps - (tau0 + delta)) <= band_half_chip
    mask = support & band
    if int(mask.sum()) < 3:
        mask = support
    if int(mask.sum()) < 3:
        mask = band
    if int(mask.sum()) < 1:
        mask = np.ones_like(taps, dtype=bool)

    kb = k1[mask]
    denom = float(np.vdot(kb, kb).real)
    if denom <= 0.0:
        alpha = np.zeros(residual.shape[0], dtype=np.complex128)
    else:
        alpha = (residual[:, mask] @ np.conj(kb)) / denom

    amp_med = robust_median_abs(alpha)
    amp_p90 = float(np.percentile(np.abs(alpha), 90.0))
    alpha_dc = alpha - np.mean(alpha)
    dyn_med = robust_median_abs(alpha_dc)
    if len(alpha) > 1:
        mod = np.ones_like(alpha, dtype=np.complex128)
        mag = np.abs(alpha_dc)
        ok = mag > np.percentile(mag, 10.0)
        mod[ok] = alpha_dc[ok] / np.maximum(mag[ok], 1e-12)
        step_score = fdm.modulation_step_score(times, mod, drift_hz)
    else:
        step_score = 0.0
    # A deliberately conservative scalar: strong dynamic residual energy plus
    # phase-step consistency. Static path0 mismatch can have amp_med, but it
    # should not score highly unless it also follows the measured drift.
    evidence = dyn_med * max(step_score, 1e-3)
    return {
        "delta_chip": float(delta),
        "delta_m": float(delta * chip_m),
        "amp_med": amp_med,
        "amp_p90": amp_p90,
        "dyn_med": dyn_med,
        "step_score": step_score,
        "evidence": float(evidence),
        "band_taps": int(mask.sum()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dense", required=True)
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--chip-m", type=float, default=29.3)
    ap.add_argument("--delay-m", type=float, help="optional injected delay for rank reporting")
    ap.add_argument("--cn0-min", type=float, default=0.0)
    ap.add_argument("--lock-min", type=float, default=-1.0)
    ap.add_argument("--min-lock-run", type=int, default=1000)
    ap.add_argument("--settle-epochs", type=int, default=200)
    ap.add_argument("--phase-reference", choices=("phase", "tap0", "none"), default="phase")
    ap.add_argument("--min-delay-chips", type=float, default=0.10)
    ap.add_argument("--max-delay-chips", type=float, default=4.0)
    ap.add_argument("--step-chip", type=float, default=0.05)
    ap.add_argument("--band-half-chip", type=float, default=0.6)
    ap.add_argument("--band-min-frac", type=float, default=0.15)
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--csv-out")
    args = ap.parse_args()

    taps, iq_ref, times, _meta = fdm.load_dense_selected(
        args.dense, args.cn0_min, args.lock_min, 0,
        args.min_lock_run, args.settle_epochs, args.phase_reference
    )
    ktaps, K = ftp.load_reference_csv(args.kernel)
    zt = fdm.zero_tap_index(taps)
    tap0_mag = np.maximum(np.abs(iq_ref[:, zt]), 1e-12)
    norm_for_drift = iq_ref / tap0_mag[:, None]
    drift_hz, probe_chip = fdm.choose_probe(times, iq_ref, taps, zt, args.delay_m, args.chip_m)
    one = fdm.fit_one_static(taps, iq_ref, ktaps, K, [0.0])
    tau0, c0 = one[0], one[1]
    k0 = ftp.kern_at(ktaps, K, taps - tau0)
    residual = iq_ref - c0 * k0[None, :]

    deltas = np.arange(max(args.min_delay_chips, args.step_chip),
                       args.max_delay_chips + 1e-9, args.step_chip)
    rows = [
        score_delta(taps, residual, times, ktaps, K, tau0, float(d), drift_hz,
                    args.band_half_chip, args.band_min_frac, args.chip_m)
        for d in deltas
    ]
    rows.sort(key=lambda r: r["evidence"], reverse=True)

    print("dense: %s" % args.dense)
    print("kernel: %s" % args.kernel)
    print("static tau0=%.3f chip  drift=%.2f Hz  probe=%.2f chip" % (tau0, drift_hz, probe_chip))
    print("rank  delta_chip  delta_m  evidence  dyn_med  amp_med  step_score  band")
    print("-" * 82)
    for i, r in enumerate(rows[:args.top], start=1):
        print("%4d  %10.3f  %7.1f  %.5g  %.5g  %.5g  %.3f  %4d" %
              (i, r["delta_chip"], r["delta_m"], r["evidence"], r["dyn_med"],
               r["amp_med"], r["step_score"], r["band_taps"]))
    if args.delay_m is not None:
        target_chip = args.delay_m / args.chip_m
        nearest = min(rows, key=lambda r: abs(r["delta_chip"] - target_chip))
        rank = next(i for i, r in enumerate(rows, start=1) if r is nearest)
        print("target %.1f m (%.3f chip): nearest %.1f m rank=%d evidence=%.5g step=%.3f"
              % (args.delay_m, target_chip, nearest["delta_m"], rank,
                 nearest["evidence"], nearest["step_score"]))

    if args.csv_out:
        by_delay = sorted(rows, key=lambda r: r["delta_chip"])
        with open(args.csv_out, "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(by_delay[0].keys()))
            wr.writeheader()
            wr.writerows(by_delay)
        print("csv -> %s" % args.csv_out)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Synthetic Phase B benchmark for near-resolution two-source separation.

This benchmark formalizes the 0.5-chip target before collecting more RF data. It
uses the same residual-band alternating fitter as the real Phase B benchmark,
but feeds it deterministic synthetic dense profiles:

    Y(tau, t) = K(tau) + A1 exp(j*(2*pi*f*t + phi)) K(tau - delta)

The hard gate is the 0.5-chip case: equal or near-equal power, destructive phase,
and fast independent-clock drift.  A failing case exits non-zero, so this script
can be used as a regression check while the real-data fitter evolves.
"""

import argparse
import csv
import os
import sys
from contextlib import nullcontext, redirect_stdout

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_drift_modulated_twosource as fdm  # noqa: E402
import fit_two_path as ftp  # noqa: E402


def wrap_stdout(verbose):
    if verbose:
        return nullcontext()
    return redirect_stdout(open(os.devnull, "w"))


def fit_case(taps, K, chip_m, delta_chip, ratio_db, drift_hz, phi_deg, noise,
             seed, dmin, dmax, coarse, fine, iterations, verbose):
    Y = fdm.synthetic_case(
        taps, K, chip_m, delta_chip, ratio_db, drift_hz, phi_deg,
        n_epochs=3000, noise=noise, seed=seed
    )
    with wrap_stdout(verbose):
        best, one = fdm.fit_residual_band_iterative(
            taps, Y, taps, K, dmin=dmin, dmax=dmax, tau0_values=[0.0],
            coarse=coarse, fine=fine, iterations=iterations,
            expected_drift_hz=drift_hz, chip_m=chip_m
        )
        summary = fdm.summarize_fit(best, one, Y["data"], chip_m,
                                    delta_chip * chip_m, ratio_db)
    return summary


def make_cases(chip_m):
    del chip_m
    cases = []
    # Required hard target: 0.5 chip, equal power, destructive phase, fast drift.
    for drift_hz in (250.0, -250.0):
        cases.append(("hard_0p5_equal_destructive_fast", 0.5, 0.0, drift_hz, 180.0, 0.003))
    # Phase and amplitude coverage around the hard point.
    for ratio_db in (0.0, -3.0, -6.0):
        for phi_deg in (0.0, 90.0, 180.0):
            for drift_hz in (26.0, 250.0):
                cases.append(("grid_0p5", 0.5, ratio_db, drift_hz, phi_deg, 0.003))
    # Stress the same target with a higher synthetic noise floor.
    for phi_deg in (90.0, 180.0):
        cases.append(("noisy_0p5_equal_fast", 0.5, 0.0, 250.0, phi_deg, 0.010))
    # A small look-ahead toward below 0.5 chip.  These are diagnostic only unless
    # --require-diagnostic is set.
    for delta_chip in (0.4, 0.3):
        cases.append(("diagnostic_sub_0p5", delta_chip, 0.0, 250.0, 180.0, 0.003))
    return cases


def verdict(row, delay_tol_chip, ratio_tol_db, drop_min):
    if row["diagnostic"] == "1":
        return "DIAGNOSTIC"
    reasons = []
    if row["reliable"] != "1":
        reasons.append("fitter_unreliable")
    if abs(float(row["delay_error_chip"])) > delay_tol_chip:
        reasons.append("delay_error")
    if abs(float(row["ratio_error_db"])) > ratio_tol_db:
        reasons.append("ratio_error")
    if float(row["resid_drop"]) < drop_min:
        reasons.append("weak_drop")
    return "PASS" if not reasons else "FAIL:" + "|".join(reasons)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="CSV output")
    ap.add_argument("--kernel", help="optional Phase A reference CSV; default uses synthetic L5-like kernel")
    ap.add_argument("--chip-m", type=float, default=29.3)
    ap.add_argument("--delay-tol-chip", type=float, default=0.06)
    ap.add_argument("--ratio-tol-db", type=float, default=2.0)
    ap.add_argument("--drop-min", type=float, default=0.15)
    ap.add_argument("--dmin", type=float, default=0.10)
    ap.add_argument("--dmax", type=float, default=2.0)
    ap.add_argument("--coarse-chip", type=float, default=0.02)
    ap.add_argument("--fine-chip", type=float, default=0.005)
    ap.add_argument("--iterations", type=int, default=3)
    ap.add_argument("--require-diagnostic", action="store_true",
                    help="also require the sub-0.5 diagnostic cases to pass")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.kernel:
        taps, K = ftp.load_reference_csv(args.kernel)
        print("kernel: %s" % args.kernel)
    else:
        taps = np.round(np.arange(-4.0, 4.0001, 0.1), 3)
        K = ftp.synth_kernel(taps)
        print("kernel: synthetic L5-like")
    rows = []
    for idx, (name, delta_chip, ratio_db, drift_hz, phi_deg, noise) in enumerate(make_cases(args.chip_m), start=1):
        summary = fit_case(
            taps, K, args.chip_m, delta_chip, ratio_db, drift_hz, phi_deg,
            noise, idx, args.dmin, args.dmax, args.coarse_chip, args.fine_chip,
            args.iterations, args.verbose
        )
        row = {
            "case": name,
            "diagnostic": "1" if name.startswith("diagnostic_") and not args.require_diagnostic else "0",
            "delta_chip": "%.3f" % delta_chip,
            "delta_m": "%.3f" % (delta_chip * args.chip_m),
            "ratio_db": "%.2f" % ratio_db,
            "drift_hz": "%.2f" % drift_hz,
            "phi_deg": "%.1f" % phi_deg,
            "noise": "%.4f" % noise,
            "recovered_delta_chip": "%.3f" % (summary["delta_m"] / args.chip_m),
            "recovered_delta_m": "%.3f" % summary["delta_m"],
            "delay_error_chip": "%.4f" % (summary["delta_m"] / args.chip_m - delta_chip),
            "delay_error_m": "%.3f" % (summary["delta_m"] - delta_chip * args.chip_m),
            "recovered_ratio_db": "%.2f" % summary["amp_ratio_db"],
            "ratio_error_db": "%.2f" % (summary["amp_ratio_db"] - ratio_db),
            "resid_drop": "%.4f" % summary["resid_drop"],
            "reliable": "1" if summary["reliable"] else "0",
        }
        row["verdict"] = verdict(row, args.delay_tol_chip, args.ratio_tol_db, args.drop_min)
        rows.append(row)
        print("%-32s delta=%s rec=%s err_chip=%s ratio=%s verdict=%s" %
              (name, row["delta_chip"], row["recovered_delta_chip"],
               row["delay_error_chip"], row["recovered_ratio_db"], row["verdict"]))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    hard = [r for r in rows if r["diagnostic"] == "0"]
    failed = [r for r in hard if r["verdict"] != "PASS"]
    print("summary -> %s" % args.out)
    print("hard cases: %d pass / %d total" % (len(hard) - len(failed), len(hard)))
    if failed:
        print("FAILED cases:")
        for r in failed:
            print("  %s delta=%s ratio=%s drift=%s phi=%s verdict=%s" %
                  (r["case"], r["delta_chip"], r["ratio_db"], r["drift_hz"],
                   r["phi_deg"], r["verdict"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()

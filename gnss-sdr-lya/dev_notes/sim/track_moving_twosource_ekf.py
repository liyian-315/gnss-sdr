#!/usr/bin/env python3
"""Post-correlation EKF baseline for a moving same-code second source.

State:
    x = [relative_delay_chips, relative_delay_rate_chips_per_second]

At each dense-correlator epoch, the two complex path amplitudes are solved by
linear least squares for the predicted delay.  A local variable-projection
Gauss-Newton delay correction becomes the scalar EKF measurement.  This keeps
the nonlinear state small while preserving complex tap information.

The current input is generate_moving_twosource.py NPZ.  Ground truth is used
only for final scoring, never for initialization or filtering.
"""

import argparse
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_delay_doppler_twosource as dd  # noqa: E402
import fit_two_path as ftp  # noqa: E402
import track_moving_twosource as track  # noqa: E402


C_MPS = 299792458.0


def fit_amplitudes(iq, taps, ktaps, kernel, delay_chips):
    k0 = ftp.kern_at(ktaps, kernel, taps)
    k1 = ftp.kern_at(ktaps, kernel, taps - delay_chips)
    model = np.column_stack((k0, k1))
    coeff, _res, _rank, _sv = np.linalg.lstsq(model, iq, rcond=None)
    fitted = model @ coeff
    residual = iq - fitted

    one_coeff = np.vdot(k0, iq) / max(float(np.vdot(k0, k0).real), 1e-30)
    one_residual = iq - one_coeff * k0
    r1 = float(np.linalg.norm(one_residual))
    r2 = float(np.linalg.norm(residual))
    residual_drop = 1.0 - r2 / r1 if r1 > 0 else 0.0
    ratio_db = (
        20.0 * np.log10(abs(coeff[1]) / abs(coeff[0]))
        if abs(coeff[0]) > 0 and abs(coeff[1]) > 0 else float("-inf")
    )
    return coeff, residual, residual_drop, ratio_db


def delay_jacobian(taps, ktaps, kernel, delay_chips, path1_coeff, step):
    plus = ftp.kern_at(ktaps, kernel, taps - (delay_chips + step))
    minus = ftp.kern_at(ktaps, kernel, taps - (delay_chips - step))
    return path1_coeff * (plus - minus) / (2.0 * step)


def initialize_from_delay_doppler(iq, times, taps, ktaps, kernel, chip_m,
                                  carrier_hz, init_s, tau_min, tau_max,
                                  tau_step, top_k):
    dt = float(np.median(np.diff(times)))
    n = min(len(iq), max(64, int(round(init_s / dt))))
    tau_grid = np.arange(tau_min, tau_max + 0.5 * tau_step, tau_step)
    matrix, freqs = dd.delay_doppler_map(iq[:n], dt, ktaps, kernel, taps, tau_grid)
    guard_hz = 2.0 / (n * dt)
    candidates = track.top_candidates(
        matrix, freqs, tau_grid, top_k, guard_hz, tau_min,
        max(0.04, tau_step), max(0.5, guard_hz), chip_m)
    if not candidates:
        raise SystemExit("delay-Doppler initializer produced no candidates")
    wavelength_m = C_MPS / carrier_hz
    for candidate in candidates:
        candidate["delay_chips"] = candidate["delay_m"] / chip_m
        candidate["rate_chips_s"] = (
            -wavelength_m * candidate["doppler_hz"] / chip_m
        )
    return candidates, guard_hz


def ekf_filter(iq, times, taps, ktaps, kernel, x0, args):
    dt_nominal = float(np.median(np.diff(times)))
    x = np.asarray(x0, dtype=np.float64)
    p = np.diag([args.initial_delay_std ** 2, args.initial_rate_std ** 2])
    rows = []

    for index, (time_s, observation) in enumerate(zip(times, iq)):
        dt = dt_nominal if index == 0 else max(float(time_s - times[index - 1]), 1e-6)
        transition = np.array([[1.0, dt], [0.0, 1.0]])
        q = args.process_accel_std ** 2
        process_noise = q * np.array([
            [0.25 * dt ** 4, 0.5 * dt ** 3],
            [0.5 * dt ** 3, dt ** 2],
        ])
        x_pred = transition @ x
        p_pred = transition @ p @ transition.T + process_noise
        x_pred[0] = float(np.clip(x_pred[0], args.tau_min, args.tau_max))

        coeff, residual, residual_drop, ratio_db = fit_amplitudes(
            observation, taps, ktaps, kernel, x_pred[0])
        jacobian_complex = delay_jacobian(
            taps, ktaps, kernel, x_pred[0], coeff[1], args.derivative_step)
        jacobian = np.concatenate((jacobian_complex.real, jacobian_complex.imag))
        innovation_vector = np.concatenate((residual.real, residual.imag))
        information = float(np.dot(jacobian, jacobian))
        residual_power = float(np.median(np.abs(residual) ** 2))
        measurement_variance = max(
            args.measurement_delay_std_floor ** 2,
            residual_power / max(information, 1e-30),
        )

        if information <= 1e-16:
            correction = 0.0
            nis = float("inf")
            accepted = False
        else:
            correction = float(np.dot(jacobian, innovation_vector) / information)
            correction = float(np.clip(
                correction, -args.max_correction_chips, args.max_correction_chips))
            innovation_variance = float(p_pred[0, 0] + measurement_variance)
            nis = correction ** 2 / max(innovation_variance, 1e-30)
            accepted = bool(nis <= args.nis_gate)

        if accepted:
            gain = p_pred[:, 0] / (p_pred[0, 0] + measurement_variance)
            x = x_pred + gain * correction
            p = p_pred - np.outer(gain, p_pred[0, :])
            p = 0.5 * (p + p.T)
        else:
            x, p = x_pred, p_pred

        x[0] = float(np.clip(x[0], args.tau_min, args.tau_max))
        rows.append({
            "time_s": float(time_s),
            "delay_chips": float(x[0]),
            "delay_rate_chips_s": float(x[1]),
            "delay_std_chips": float(np.sqrt(max(p[0, 0], 0.0))),
            "rate_std_chips_s": float(np.sqrt(max(p[1, 1], 0.0))),
            "amp0": float(abs(coeff[0])),
            "amp1": float(abs(coeff[1])),
            "amp_ratio_db": float(ratio_db),
            "residual_drop": float(residual_drop),
            "residual_rel": float(
                np.linalg.norm(residual)
                / max(float(np.linalg.norm(observation)), 1e-30)
            ),
            "nis": float(nis),
            "accepted": int(accepted),
        })
    return rows


def hypothesis_quality(rows, args):
    burn = min(args.burn_epochs, max(0, len(rows) // 4))
    used = rows[burn:]
    residual = np.asarray([r["residual_rel"] for r in used])
    ratio_db = np.asarray([r["amp_ratio_db"] for r in used])
    residual_drop = np.asarray([r["residual_drop"] for r in used])
    delays = np.asarray([r["delay_chips"] for r in used])
    support = (
        (ratio_db >= args.min_ratio_db)
        & (residual_drop >= args.min_residual_drop)
    )
    boundary = (
        (delays <= args.tau_min + 1.5 * args.tau_step)
        | (delays >= args.tau_max - 1.5 * args.tau_step)
    )
    median_residual = float(np.median(residual))
    support_fraction = float(np.mean(support))
    boundary_fraction = float(np.mean(boundary))
    score = (
        median_residual
        + args.hypothesis_support_penalty * (1.0 - support_fraction)
        + args.hypothesis_boundary_penalty * boundary_fraction
    )
    return score, median_residual, support_fraction, boundary_fraction


def verdict(rows, truth_delay_m, chip_m, init_doppler_hz, guard_hz, args):
    burn = min(args.burn_epochs, max(0, len(rows) // 4))
    used = rows[burn:]
    delay_m = np.asarray([r["delay_chips"] * chip_m for r in used])
    delay_std_m = np.asarray([r["delay_std_chips"] * chip_m for r in used])
    ratio_db = np.asarray([r["amp_ratio_db"] for r in used])
    residual_drop = np.asarray([r["residual_drop"] for r in used])
    accepted = np.asarray([r["accepted"] for r in used], dtype=bool)
    model_support = (
        (ratio_db >= args.min_ratio_db)
        & (residual_drop >= args.min_residual_drop)
    )

    accepted_fraction = float(np.mean(accepted))
    support_fraction = float(np.mean(model_support))
    median_std_m = float(np.median(delay_std_m))
    diversity_threshold_hz = max(args.min_diversity_hz,
                                 args.diversity_guard_factor * guard_hz)
    diversity_ok = abs(init_doppler_hz) >= diversity_threshold_hz
    boundary_fraction = float(np.mean(
        (delay_m <= (args.tau_min + 1.5 * args.tau_step) * chip_m)
        | (delay_m >= (args.tau_max - 1.5 * args.tau_step) * chip_m)
    ))
    boundary_ok = boundary_fraction <= args.max_boundary_fraction
    reliable = (
        accepted_fraction >= args.min_accepted_fraction
        and support_fraction >= args.min_support_fraction
        and median_std_m <= args.max_delay_std_m
        and diversity_ok
        and boundary_ok
    )

    truth = truth_delay_m[burn:burn + len(used)]
    error = np.abs(delay_m - truth)
    within = error <= max(3.0, 0.1 * chip_m)
    coverage_2sigma = float(np.mean(error <= 2.0 * delay_std_m))
    reliable = reliable and coverage_2sigma >= args.min_coverage_2sigma
    return {
        "reliable": reliable,
        "accepted_fraction": accepted_fraction,
        "support_fraction": support_fraction,
        "median_std_m": median_std_m,
        "diversity_ok": diversity_ok,
        "diversity_threshold_hz": diversity_threshold_hz,
        "boundary_fraction": boundary_fraction,
        "boundary_ok": boundary_ok,
        "median_error_m": float(np.median(error)),
        "p90_error_m": float(np.percentile(error, 90)),
        "within_fraction": float(np.mean(within)),
        "coverage_2sigma": coverage_2sigma,
        "delay_m": delay_m,
        "truth_m": truth,
        "used_rows": used,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="moving two-source NPZ")
    ap.add_argument("--kernel", help="same coherent kernel CSV used by generator")
    ap.add_argument("--init-s", type=float, default=3.0)
    ap.add_argument("--tau-min", type=float, default=0.05)
    ap.add_argument("--tau-max", type=float, default=1.5)
    ap.add_argument("--tau-step", type=float, default=0.025)
    ap.add_argument("--top-k", type=int, default=12)
    ap.add_argument("--init-hypotheses", type=int, default=8,
                    help="run this many EKF initial modes and select by model evidence")
    ap.add_argument("--initial-delay-std", type=float, default=0.12)
    ap.add_argument("--initial-rate-std", type=float, default=0.05)
    ap.add_argument("--process-accel-std", type=float, default=0.2)
    ap.add_argument("--measurement-delay-std-floor", type=float, default=0.2,
                    help="minimum per-epoch delay measurement std [chips], prevents overconfident covariance")
    ap.add_argument("--derivative-step", type=float, default=0.01)
    ap.add_argument("--max-correction-chips", type=float, default=0.08)
    ap.add_argument("--nis-gate", type=float, default=16.0)
    ap.add_argument("--burn-epochs", type=int, default=200)
    ap.add_argument("--min-ratio-db", type=float, default=-15.0)
    ap.add_argument("--min-residual-drop", type=float, default=0.05)
    ap.add_argument("--min-accepted-fraction", type=float, default=0.8)
    ap.add_argument("--min-support-fraction", type=float, default=0.6)
    ap.add_argument("--max-delay-std-m", type=float, default=3.0)
    ap.add_argument("--min-coverage-2sigma", type=float, default=0.8,
                    help="synthetic benchmark gate for posterior +/-2 sigma truth coverage")
    ap.add_argument("--min-diversity-hz", type=float, default=0.5)
    ap.add_argument("--diversity-guard-factor", type=float, default=2.0,
                    help="initial Doppler must also exceed this multiple of the path0 leakage guard")
    ap.add_argument("--hypothesis-support-penalty", type=float, default=0.2)
    ap.add_argument("--hypothesis-boundary-penalty", type=float, default=0.2)
    ap.add_argument("--max-boundary-fraction", type=float, default=0.2)
    ap.add_argument("--csv")
    ap.add_argument("--plot")
    args = ap.parse_args()

    data = np.load(args.input, allow_pickle=False)
    iq = data["iq"].astype(np.complex128)
    times = data["times_s"].astype(np.float64)
    taps = data["taps_chips"].astype(np.float64)
    truth_delay_m = data["delta_m"].astype(np.float64)
    meta = json.loads(str(data["meta_json"]))
    chip_m = float(meta["chip_m"])
    carrier_hz = float(meta["carrier_hz"])
    if args.kernel:
        ktaps, kernel = ftp.load_reference_csv(args.kernel)
    else:
        ktaps, kernel = taps.copy(), ftp.synth_kernel(taps)

    candidates, guard_hz = initialize_from_delay_doppler(
        iq, times, taps, ktaps, kernel, chip_m, carrier_hz,
        args.init_s, args.tau_min, args.tau_max, args.tau_step, args.top_k)
    hypotheses = []
    for candidate in candidates[:args.init_hypotheses]:
        rows = ekf_filter(
            iq, times, taps, ktaps, kernel,
            (candidate["delay_chips"], candidate["rate_chips_s"]), args)
        quality = hypothesis_quality(rows, args)
        hypotheses.append((quality, candidate, rows))
    hypotheses.sort(key=lambda item: item[0][0])
    for rank, (quality, candidate_i, _rows) in enumerate(hypotheses, 1):
        print("hyp %d: init delay %.2f m Doppler %+.3f Hz map %.1f dB -> score %.4f residual %.4f support %.1f%% boundary %.1f%%" %
              (rank, candidate_i["delay_m"], candidate_i["doppler_hz"],
               candidate_i["score_db"], quality[0], quality[1],
               100.0 * quality[2], 100.0 * quality[3]))
    _quality, candidate, rows = hypotheses[0]
    print("selected initializer: delay %.2f m, Doppler %+.3f Hz, rate %+.5f chip/s, guard %.2f Hz" %
          (candidate["delay_m"], candidate["doppler_hz"],
           candidate["rate_chips_s"], guard_hz))

    result = verdict(rows, truth_delay_m, chip_m, candidate["doppler_hz"],
                     guard_hz, args)
    print("updates accepted: %.1f%%; 2-path support: %.1f%%; median posterior std %.2f m" %
          (100.0 * result["accepted_fraction"],
           100.0 * result["support_fraction"], result["median_std_m"]))
    print("delay error: median %.2f m, p90 %.2f m, within %.1f%%, 2-sigma coverage %.1f%%" %
          (result["median_error_m"], result["p90_error_m"],
           100.0 * result["within_fraction"],
           100.0 * result["coverage_2sigma"]))
    print("diversity gate: %s (|initial Doppler| %.3f Hz, required %.3f Hz)" %
          ("PASS" if result["diversity_ok"] else "FAIL",
           abs(candidate["doppler_hz"]), result["diversity_threshold_hz"]))
    print("boundary gate: %s (%.1f%% epochs at search boundary, max %.1f%%)" %
          ("PASS" if result["boundary_ok"] else "FAIL",
           100.0 * result["boundary_fraction"],
           100.0 * args.max_boundary_fraction))
    print("VERDICT: %s" % ("RELIABLE" if result["reliable"] else "UNRELIABLE"))

    if args.csv:
        fields = list(rows[0]) + ["truth_delay_m", "error_m"]
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for row, truth in zip(rows, truth_delay_m):
                out = dict(row)
                out["truth_delay_m"] = float(truth)
                out["error_m"] = abs(row["delay_chips"] * chip_m - truth)
                writer.writerow(out)
        print("wrote %s" % args.csv)

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        delay = np.asarray([r["delay_chips"] * chip_m for r in rows])
        std = np.asarray([r["delay_std_chips"] * chip_m for r in rows])
        plt.figure(figsize=(9, 4.8))
        plt.plot(times, truth_delay_m, "k-", linewidth=2, label="truth")
        plt.plot(times, delay, color="tab:blue", linewidth=1, label="EKF")
        plt.fill_between(times, delay - 2 * std, delay + 2 * std,
                         color="tab:blue", alpha=0.2, label="EKF +/-2 sigma")
        plt.xlabel("Time [s]")
        plt.ylabel("Relative delay [m]")
        plt.title("Post-correlation EKF two-source delay")
        plt.grid(alpha=0.25)
        plt.legend()
        plt.tight_layout()
        plt.savefig(args.plot, dpi=150)
        print("wrote %s" % args.plot)


if __name__ == "__main__":
    main()

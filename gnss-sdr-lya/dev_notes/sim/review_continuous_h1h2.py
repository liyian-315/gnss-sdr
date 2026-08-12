#!/usr/bin/env python3
"""Independent diagnostics for the continuous H1/H2 implementation.

This mirrors the reviewed estimator while retaining raw residuals/parameters.
It also provides an observation-only global-tau0 multistart diagnostic; that
diagnostic is not a production estimator.
"""

import argparse
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_space_delay_h1h2 as h12  # noqa: E402
import fit_two_path as ftp  # noqa: E402


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def coherent_synth(manifold, taps, kernel, sources, n_blocks, noise_sigma, rng):
    dense = np.zeros((n_blocks, manifold.n_ant, len(taps)), dtype=np.complex128)
    for b in range(n_blocks):
        common_phase = np.exp(1j * rng.uniform(0.0, 2.0 * np.pi))
        for az, tau, amp, relative_phase in sources:
            dense[b] += (common_phase * amp * np.exp(1j * relative_phase) *
                         np.outer(manifold.a(az), h12.kernel_vec(tau, taps, taps, kernel)))
        dense[b] += noise_sigma * (rng.standard_normal(dense[b].shape) +
                                   1j * rng.standard_normal(dense[b].shape)) / np.sqrt(2.0)
    return dense


def trace_fit(dense, taps, kernel, manifold, az_grid, tau_grid, global_tau0=False,
              refine_sweeps=3):
    Y = dense.reshape(dense.shape[0], -1)
    az_step = float(az_grid[1] - az_grid[0])
    tau_step = float(tau_grid[1] - tau_grid[0])
    qcache = {(float(az), float(tau)): h12.build_q(manifold, az, tau, taps, taps, kernel)
              for az in az_grid for tau in tau_grid}

    best1 = (np.inf, None)
    for key, q in qcache.items():
        residual, _ = h12._residual(Y, q[:, None])
        if residual < best1[0]:
            best1 = residual, key
    azc, tauc = best1[1]
    p1, res1 = h12._refine(Y, manifold, taps, taps, kernel, [azc, tauc],
                           [(azc - az_step, azc + az_step),
                            (tauc - tau_step, tauc + tau_step)], refine_sweeps)
    az_h1, tau_h1 = p1

    tau0_seeds = tau_grid if global_tau0 else np.array([tau_h1])
    best2 = (np.inf, None)
    for tau0_seed in tau0_seeds:
        r0 = h12.kernel_vec(tau0_seed, taps, taps, kernel)
        for az0 in az_grid:
            q0 = np.kron(manifold.a(az0), r0)
            for az1 in az_grid:
                for tau1 in tau_grid:
                    if abs(tau1 - tau0_seed) < 0.03:
                        continue
                    residual, _ = h12._residual(
                        Y, np.column_stack([q0, qcache[(float(az1), float(tau1))]]))
                    if residual < best2[0]:
                        best2 = residual, (float(az0), float(tau0_seed),
                                           float(az1), float(tau1))
    az0c, tau0c, az1c, tau1c = best2[1]
    p2, res2 = h12._refine(
        Y, manifold, taps, taps, kernel, [az0c, tau0c, az1c, tau1c],
        [(az0c - az_step, az0c + az_step), (tau0c - tau_step, tau0c + tau_step),
         (az1c - az_step, az1c + az_step), (tau1c - tau_step, tau1c + tau_step)],
        refine_sweeps)
    az0, tau0, az1, tau1 = p2
    if tau1 < tau0:
        az0, tau0, az1, tau1 = az1, tau1, az0, tau0
    q0 = h12.build_q(manifold, az0, tau0, taps, taps, kernel)
    q1 = h12.build_q(manifold, az1, tau1, taps, taps, kernel)
    _, coeff = h12._residual(Y, np.column_stack([q0, q1]))
    mu = h12.coherence(q0, q1)
    cond = float(np.linalg.cond(np.column_stack([q0, q1])))
    improvement = float(10.0 * np.log10(res1 / max(res2, 1e-30)))
    ratio = float(20.0 * np.log10(
        np.median(np.abs(coeff[:, 1]) / (np.abs(coeff[:, 0]) + 1e-30)) + 1e-30))
    return {"h1_residual": res1, "h2_residual": res2,
            "improvement_db": improvement, "h1_az_deg": az_h1,
            "h1_tau_chips": tau_h1, "h1_coarse_az_deg": azc,
            "h1_coarse_tau_chips": tauc, "h2_az0_deg": az0,
            "h2_tau0_chips": tau0, "h2_az1_deg": az1,
            "h2_tau1_chips": tau1, "delta_tau_chips": tau1 - tau0,
            "delta_az_deg": abs(az1 - az0), "amp_ratio_db": ratio,
            "mu_joint": mu, "condition_number": cond,
            "source0_tau_bound_lo": tau0c - tau_step,
            "source0_tau_bound_hi": tau0c + tau_step,
            "source1_tau_bound_lo": tau1c - tau_step,
            "source1_tau_bound_hi": tau1c + tau_step,
            "global_tau0_multistart": global_tau0}


def state_current(result, detect_db=3.0, reliable_db=6.0):
    if result["improvement_db"] < detect_db:
        return "ONE_SOURCE", "NO_SECOND_SOURCE"
    if (result["mu_joint"] > 0.98 or result["condition_number"] > 1e4 or
            result["delta_tau_chips"] < 0.03):
        return "UNRESOLVED", "collision"
    if result["improvement_db"] >= reliable_db:
        return "TWO_SOURCE", "RELIABLE"
    return "TWO_SOURCE", "MARGINAL"


def anchor_rows(taps, kernel, manifold):
    rows = []
    az_grid = np.arange(-60.0, 60.1, 10.0)
    tau_grid = np.arange(-0.6, 0.601, 0.05)
    for label, tau0, tau1 in (("A", -0.25, 0.25), ("B", -0.5, 0.5),
                              ("C", -0.18, 0.32)):
        for delta_az in (10.0, 20.0, 30.0):
            for relative_phase in (0.0, np.pi / 2.0):
                dense = coherent_synth(
                    manifold, taps, kernel,
                    [(-delta_az / 2.0, tau0, 1.0, 0.0),
                     (delta_az / 2.0, tau1, 1.0, relative_phase)],
                    24, 0.01, np.random.default_rng(7100 + len(rows)))
                anchored = trace_fit(dense, taps, kernel, manifold, az_grid, tau_grid)
                multistart = trace_fit(dense, taps, kernel, manifold, az_grid, tau_grid,
                                       global_tau0=True)
                for mode, result in (("reviewed_anchor", anchored),
                                     ("diagnostic_global_multistart", multistart)):
                    rows.append({"case": label, "truth_tau0": tau0,
                                 "truth_tau1": tau1, "truth_delta_tau": tau1 - tau0,
                                 "truth_delta_az": delta_az,
                                 "relative_phase_rad": relative_phase,
                                 "mode": mode, **result})
    return rows


def zero_delay_rows(taps, kernel, manifold):
    rows = []
    az_grid = np.arange(-180.0, 180.1, 10.0)
    tau_grid = np.arange(-0.3, 0.301, 0.05)
    for delta_az in (60.0, 90.0, 120.0, 180.0):
        for power_db in (0.0, -6.0):
            for seed in range(4):
                dense = h12.synth(
                    manifold, taps, taps, kernel,
                    [(-delta_az / 2.0, 0.0, 1.0),
                     (delta_az / 2.0, 0.0, 10.0 ** (power_db / 20.0))],
                    24, 0.03, np.random.default_rng(8000 + len(rows)))
                result = trace_fit(dense, taps, kernel, manifold, az_grid, tau_grid)
                state, detail = state_current(result)
                rows.append({"truth_delta_az": delta_az, "power_ratio_db": power_db,
                             "seed": seed, "current_state": state,
                             "current_detail": detail, **result})
    return rows


def h0_rows(taps, kernel, manifold_fit, mismatch, n_trials, seed_base):
    rows = []
    rng = np.random.default_rng(seed_base)
    az_grid = np.arange(-60.0, 60.1, 10.0)
    tau_grid = np.arange(-0.25, 1.51, 0.1)
    for trial in range(n_trials):
        if mismatch > 0.0:
            eps = mismatch * (rng.standard_normal(manifold_fit.n_ant) +
                              1j * rng.standard_normal(manifold_fit.n_ant)) / np.sqrt(2.0)

            class Perturbed:
                n_ant = manifold_fit.n_ant

                def a(self, az_deg, _eps=eps):
                    return manifold_fit.a(az_deg) * (1.0 + _eps)
            truth_manifold = Perturbed()
        else:
            truth_manifold = manifold_fit
        az = rng.uniform(-60.0, 60.0)
        tau = rng.uniform(-0.1, 0.3)
        dense = h12.synth(truth_manifold, taps, taps, kernel, [(az, tau, 1.0)],
                          24, 0.05, rng)
        result = trace_fit(dense, taps, kernel, manifold_fit, az_grid, tau_grid)
        state, detail = state_current(result)
        h1_az_boundary = min(
            abs(result["h1_az_deg"] - (result["h1_coarse_az_deg"] - 10.0)),
            abs(result["h1_az_deg"] - (result["h1_coarse_az_deg"] + 10.0))) < 1e-3
        h1_tau_boundary = min(
            abs(result["h1_tau_chips"] - (result["h1_coarse_tau_chips"] - 0.1)),
            abs(result["h1_tau_chips"] - (result["h1_coarse_tau_chips"] + 0.1))) < 1e-3
        rows.append({"trial": trial, "truth_az_deg": az, "truth_tau_chips": tau,
                     "manifold_error": mismatch, "state": state, "detail": detail,
                     "h1_az_boundary_hit": h1_az_boundary,
                     "h1_tau_boundary_hit": h1_tau_boundary, **result})
    return rows


def true_h2_rows(taps, kernel, manifold):
    rows = []
    az_grid = np.arange(-80.0, 80.1, 10.0)
    tau_grid = np.arange(-0.25, 1.51, 0.05)
    for delta_tau in (0.0, 0.25, 0.5, 1.0):
        for delta_az in (60.0, 40.0, 30.0, 20.0, 10.0):
            for power_db in (0.0, -6.0):
                for seed in range(5):
                    dense = h12.synth(
                        manifold, taps, taps, kernel,
                        [(-delta_az / 2.0, 0.0, 1.0),
                         (delta_az / 2.0, delta_tau, 10.0 ** (power_db / 20.0))],
                        24, 0.05, np.random.default_rng(9000 + len(rows)))
                    result = trace_fit(dense, taps, kernel, manifold, az_grid, tau_grid)
                    state, detail = state_current(result)
                    rows.append({"truth_delta_tau": delta_tau,
                                 "truth_delta_az": delta_az,
                                 "truth_power_ratio_db": power_db, "seed": seed,
                                 "current_state": state, "current_detail": detail,
                                 **result})
    return rows


def summarize_h0(rows):
    values = np.array([row["improvement_db"] for row in rows])
    return {"n_trials": len(rows), "manifold_error": rows[0]["manifold_error"],
            **{"q%d" % q: float(np.percentile(values, q)) for q in (50, 90, 95, 99)},
            "max": float(np.max(values)),
            "existence_false_alarm_fraction": float(np.mean(
                [row["state"] == "TWO_SOURCE" for row in rows])),
            "unresolved_fraction": float(np.mean(
                [row["state"] == "UNRESOLVED" for row in rows])),
            "optimizer_failure_count": 0,
            "h1_az_boundary_hits": int(sum(row["h1_az_boundary_hit"] for row in rows)),
            "h1_tau_boundary_hits": int(sum(row["h1_tau_boundary_hit"] for row in rows))}


def self_test():
    taps = np.round(np.arange(-1.5, 1.5001, 0.1), 4)
    kernel = ftp.synth_kernel(taps)
    manifold = h12.IdealManifold(h12.ula_xyz(4, 0.5))
    dense = h12.synth(manifold, taps, taps, kernel,
                      [(3.7, 0.04, 1.0), (24.9, 0.41, 10 ** (-6 / 20.0))],
                      24, 0.05, np.random.default_rng(0))
    traced = trace_fit(dense, taps, kernel, manifold,
                       np.arange(-60.0, 60.1, 5.0), np.arange(-0.25, 1.51, 0.05))
    reviewed = h12.fit_h1h2(dense, taps, taps, kernel, manifold, 29.3)
    assert np.isclose(traced["improvement_db"], reviewed["improvement_db"], atol=1e-9)
    assert np.isclose(traced["delta_tau_chips"], reviewed["delta_tau_chips"], atol=1e-9)
    print("review diagnostic self-test: PASS (trace matches reviewed estimator)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir")
    parser.add_argument("--h0-trials", type=int, default=500)
    parser.add_argument("--sections", default="anchor,zero,h0,h2",
                        help="comma-separated: anchor,zero,h0,h2")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.output_dir:
        parser.error("--output-dir is required")
    os.makedirs(args.output_dir, exist_ok=True)
    sections = set(args.sections.split(","))
    taps = np.round(np.arange(-1.5, 1.5001, 0.1), 4)
    kernel = ftp.synth_kernel(taps)
    ula = h12.IdealManifold(h12.ula_xyz(4, 0.5))
    planar = h12.IdealManifold(np.array([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0],
                                         [0.0, 0.5, 0.0], [0.5, 0.5, 0.0]]))
    arbitrary = h12.IdealManifold(np.array([[0.00, 0.00, 0.0], [0.55, 0.10, 0.0],
                                            [0.20, 0.60, 0.0], [0.70, 0.65, 0.0]]))
    if "anchor" in sections:
        write_csv(os.path.join(args.output_dir, "anchor_bias_pre_fix.csv"),
                  anchor_rows(taps, kernel, ula))
    if "zero" in sections:
        write_csv(os.path.join(args.output_dir, "zero_delay_pre_fix.csv"),
                  zero_delay_rows(taps, kernel, planar))
    if "h0" in sections:
        ideal_h0 = h0_rows(taps, kernel, ula, 0.0, args.h0_trials, 10000)
        mismatch_h0 = h0_rows(taps, kernel, ula, 0.05, args.h0_trials, 20000)
        write_csv(os.path.join(args.output_dir, "h0_continuous_random.csv"),
                  ideal_h0 + mismatch_h0)
        write_csv(os.path.join(args.output_dir, "h0_summary.csv"),
                  [summarize_h0(ideal_h0), summarize_h0(mismatch_h0)])
    if "h2" in sections:
        write_csv(os.path.join(args.output_dir, "true_h2_pre_fix.csv"),
                  true_h2_rows(taps, kernel, arbitrary))
    metadata = {"reviewed_sha": "7146fec14d4142a4a7677f3e9eae1703cb3e74c8",
                "evidence": "ideal_simulation_red_team", "h0_trials_per_condition": args.h0_trials,
                "thresholds": "simulation-derived provisional",
                "sections": sorted(sections),
                "anchor_multistart": "diagnostic only; global coarse tau0, no truth initialization",
                "reproduce": "python dev_notes/sim/review_continuous_h1h2.py "
                             "--output-dir <dir> --h0-trials %d --sections %s" %
                             (args.h0_trials, args.sections)}
    with open(os.path.join(args.output_dir, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)
        fh.write("\n")
    print("wrote continuous H1/H2 red-team evidence to %s" % args.output_dir)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Red-team diagnostics for single-source H1/H2 false positives.

This script does not change the estimator. It reproduces its discrete H1/H2
support search, adds observation-only H1 local refinement, frozen-support
train/validation scoring, and efficient H0 Monte Carlo diagnostics.
"""

import argparse
import csv
import json
import os
import sys

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_uca_identifiability as analysis  # noqa: E402
import fit_space_delay_twosource as sd  # noqa: E402
import fit_two_path as ftp  # noqa: E402


STATES = ("RELIABLE", "MARGINAL", "UNRESOLVED", "NO_SECOND_SOURCE")


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def classify(improvement_db, mu_joint, detect_db=3.0, reliable_db=6.0,
             mu_max=0.98):
    if improvement_db < detect_db:
        return "NO_SECOND_SOURCE"
    if mu_joint > mu_max:
        return "UNRESOLVED"
    if improvement_db >= reliable_db:
        return "RELIABLE"
    return "MARGINAL"


class DiscreteSearch:
    def __init__(self, taps, kernel, array_xyz_m, wavelength_m, angle_grid,
                 tau0_grid, tau1_grid):
        self.taps = np.asarray(taps)
        self.kernel = np.asarray(kernel)
        self.xyz = np.asarray(array_xyz_m)
        self.wavelength_m = wavelength_m
        self.angle_grid = np.asarray(angle_grid)
        self.tau0_grid = np.asarray(tau0_grid)
        self.tau1_grid = np.asarray(tau1_grid)
        self.all_tau = np.unique(np.concatenate([self.tau0_grid, self.tau1_grid]))
        self.keys = [(float(az), float(tau)) for az in self.angle_grid
                     for tau in self.all_tau]
        q = [sd.build_q(az, tau, self.taps, self.taps, self.kernel, len(self.xyz),
                        0.5, self.xyz, self.wavelength_m) for az, tau in self.keys]
        self.q = np.asarray(q)
        self.q_norm2 = np.sum(np.abs(self.q) ** 2, axis=1)
        self.key_index = {key: i for i, key in enumerate(self.keys)}
        pairs = []
        for tau0 in self.tau0_grid:
            for az0 in self.angle_grid:
                for az1 in self.angle_grid:
                    for tau1 in self.tau1_grid:
                        if tau1 > tau0:
                            pairs.append((self.key_index[(float(az0), float(tau0))],
                                          self.key_index[(float(az1), float(tau1))]))
        self.pairs = np.asarray(pairs, dtype=np.int32)

    def _residual_for_indices(self, Y, indices):
        X = self.q[np.asarray(indices)].T
        return sd._residual(Y, X)

    def select(self, dense, pair_chunk=20000):
        Y = dense.reshape(dense.shape[0], -1)
        energy = float(np.sum(np.abs(Y) ** 2))
        projection = Y @ self.q.conj().T
        h1_residuals = energy - np.sum(np.abs(projection) ** 2, axis=0) / self.q_norm2
        h1_index = int(np.argmin(h1_residuals))
        h1_residual = float(max(h1_residuals[h1_index], 0.0))

        best_residual = np.inf
        best_pair = None
        best_coeff = None
        for start in range(0, len(self.pairs), pair_chunk):
            pairs = self.pairs[start:start + pair_chunk]
            q0 = self.q[pairs[:, 0]]
            q1 = self.q[pairs[:, 1]]
            g00 = self.q_norm2[pairs[:, 0]]
            g11 = self.q_norm2[pairs[:, 1]]
            g01 = np.sum(q0.conj() * q1, axis=1)
            determinant = g00 * g11 - np.abs(g01) ** 2
            z0 = projection[:, pairs[:, 0]]
            z1 = projection[:, pairs[:, 1]]
            explained = (g11[None, :] * np.abs(z0) ** 2 +
                         g00[None, :] * np.abs(z1) ** 2 -
                         2.0 * np.real(g01[None, :] * z0 * z1.conj())) / determinant[None, :]
            residuals = energy - np.sum(explained, axis=0)
            local = int(np.argmin(residuals))
            if residuals[local] < best_residual:
                best_residual = float(max(residuals[local], 0.0))
                best_pair = tuple(int(x) for x in pairs[local])
        # Recompute the winning coefficients with the reviewed implementation.
        checked_residual, best_coeff = self._residual_for_indices(Y, best_pair)
        if not np.isclose(best_residual, checked_residual, rtol=1e-8, atol=1e-8):
            raise AssertionError("vectorized H2 residual disagrees with estimator LS")
        best_residual = checked_residual
        key0, key1 = self.keys[best_pair[0]], self.keys[best_pair[1]]
        q0, q1 = self.q[list(best_pair)]
        mu_joint = sd.coherence(q0, q1)
        improvement = sd.residual_improvement_db(h1_residual, best_residual, energy)
        amplitudes = np.median(np.abs(best_coeff), axis=0)
        ratio_db = 20.0 * np.log10(amplitudes[1] / max(amplitudes[0], 1e-30) + 1e-30)
        return {"h1_residual": h1_residual, "h2_residual": best_residual,
                "improvement_db": float(improvement),
                "h1_az_deg": self.keys[h1_index][0],
                "h1_tau_chips": self.keys[h1_index][1],
                "h2_az0_deg": key0[0], "h2_tau0_chips": key0[1],
                "h2_az1_deg": key1[0], "h2_tau1_chips": key1[1],
                "h2_amp0": float(amplitudes[0]), "h2_amp1": float(amplitudes[1]),
                "h2_amp_ratio_db": float(ratio_db), "mu_joint": mu_joint,
                "condition_number": float(np.linalg.cond(np.column_stack([q0, q1]))),
                "state": classify(improvement, mu_joint),
                "h1_index": h1_index, "h2_index0": best_pair[0],
                "h2_index1": best_pair[1]}

    def score_frozen(self, dense, selected):
        Y = dense.reshape(dense.shape[0], -1)
        h1_residual, _ = self._residual_for_indices(Y, [selected["h1_index"]])
        h2_residual, coeff = self._residual_for_indices(
            Y, [selected["h2_index0"], selected["h2_index1"]])
        improvement = sd.residual_improvement_db(
            h1_residual, h2_residual, float(np.sum(np.abs(Y) ** 2)))
        return h1_residual, h2_residual, float(improvement), coeff

    def refine_h1(self, dense, selected):
        Y = dense.reshape(dense.shape[0], -1)
        az_start = selected["h1_az_deg"]
        tau_start = selected["h1_tau_chips"]

        def objective(parameters):
            q = sd.build_q(parameters[0], parameters[1], self.taps, self.taps,
                           self.kernel, len(self.xyz), 0.5, self.xyz,
                           self.wavelength_m)
            return sd._residual(Y, q[:, None])[0]

        result = minimize(objective, np.array([az_start, tau_start]), method="Nelder-Mead",
                          options={"xatol": 1e-5, "fatol": 1e-9, "maxiter": 500})
        return {"refined_h1_az_deg": float(result.x[0]),
                "refined_h1_tau_chips": float(result.x[1]),
                "refined_h1_residual": float(result.fun),
                "refinement_success": bool(result.success),
                "refined_improvement_db": sd.residual_improvement_db(
                    result.fun, selected["h2_residual"],
                    float(np.sum(np.abs(Y) ** 2)))}


def synth_single(taps, kernel, xyz, wavelength_m, truth_az, truth_tau,
                 noise_sigma, seed, phase_rms_deg=0.0):
    gain_rng = np.random.default_rng(100000 + seed)
    gain = analysis.fixed_phase_gain(len(xyz), phase_rms_deg, gain_rng)
    return sd.synth_dense(taps, taps, kernel, len(xyz), 0.5, truth_az, truth_az,
                          truth_tau, truth_tau + 0.5, -6.0, 12, noise_sigma,
                          np.random.default_rng(seed), single_source=True,
                          array_xyz_m=xyz, wavelength_m=wavelength_m,
                          truth_gain=gain)


def public_row(result):
    return {key: value for key, value in result.items() if not key.endswith("index") and
            key not in ("h1_index", "h2_index0", "h2_index1")}


def canonical_cases(search, taps, kernel, xyz, wavelength_m, seeds):
    rows = []
    cases = (("A_on_grid_no_noise", 20.0, 0.1, 0.0),
             ("B_off_grid_no_noise", 17.0, 0.07, 0.0),
             ("C_on_grid_noise", 20.0, 0.1, 0.03),
             ("D_off_grid_noise", 17.0, 0.07, 0.03))
    for label, az, tau, noise in cases:
        for seed in seeds:
            dense = synth_single(taps, kernel, xyz, wavelength_m, az, tau, noise, seed)
            selected = search.select(dense)
            refined = search.refine_h1(dense, selected)
            train = search.select(dense[:6])
            validation = search.score_frozen(dense[6:], train)
            row = {"case": label, "seed": seed, "truth_az_deg": az,
                   "truth_tau_chips": tau, "noise_sigma": noise, **public_row(selected),
                   **refined, "holdout_training_improvement_db": train["improvement_db"],
                   "holdout_validation_improvement_db": validation[2]}
            rows.append(row)
    return rows


def grid_scan(taps, kernel, xyz, wavelength_m, seeds):
    rows = []
    scans = []
    for step in (10.0, 5.0, 2.0, 1.0):
        scans.append(("angle", step, np.arange(0.0, 80.0 + step / 2, step),
                      np.arange(-0.1, 0.201, 0.1), np.arange(0.3, 0.801, 0.1)))
    for step in (0.1, 0.05, 0.02, 0.01):
        scans.append(("delay", step, np.arange(0.0, 80.1, 10.0),
                      np.arange(-0.1, 0.2 + step / 2, step),
                      np.arange(0.3, 0.8 + step / 2, step)))
    for axis, step, angles, tau0, tau1 in scans:
        search = DiscreteSearch(taps, kernel, xyz, wavelength_m, angles, tau0, tau1)
        results = []
        for seed in seeds:
            dense = synth_single(taps, kernel, xyz, wavelength_m, 17.0, 0.07, 0.03, seed)
            results.append(search.select(dense))
        rows.append({"scan_axis": axis, "step": step, "realizations": len(seeds),
                     "h1_residual_median": float(np.median([r["h1_residual"] for r in results])),
                     "improvement_db_median": float(np.median([r["improvement_db"] for r in results])),
                     "improvement_db_p95": float(np.percentile([r["improvement_db"] for r in results], 95)),
                     "existence_false_alarm_fraction": float(np.mean(
                         [r["state"] in ("RELIABLE", "MARGINAL") for r in results])),
                     "ambiguous_fraction": float(np.mean([r["state"] == "UNRESOLVED"
                                                          for r in results])),
                     "clean_rejection_fraction": float(np.mean(
                         [r["state"] == "NO_SECOND_SOURCE" for r in results]))})
    return rows


def monte_carlo(search, taps, kernel, xyz, wavelength_m, realizations):
    rows = []
    summaries = []
    conditions = []
    for grid_label, az, tau in (("on_grid", 20.0, 0.1), ("off_grid", 17.0, 0.07)):
        for noise in (0.01, 0.03, 0.05):
            for phase in (0.0, 5.0, 10.0):
                conditions.append((grid_label, az, tau, noise, phase))
    for condition_index, (grid_label, az, tau, noise, phase) in enumerate(conditions):
        condition_rows = []
        for realization in range(realizations):
            seed = 900000 + condition_index * realizations + realization
            dense = synth_single(taps, kernel, xyz, wavelength_m, az, tau, noise, seed,
                                 phase_rms_deg=phase)
            selected = search.select(dense)
            train = search.select(dense[:6])
            validation = search.score_frozen(dense[6:], train)
            row = {"grid": grid_label, "noise_sigma": noise,
                   "phase_rms_deg": phase, "realization": realization, "seed": seed,
                   **public_row(selected),
                   "holdout_training_improvement_db": train["improvement_db"],
                   "holdout_validation_improvement_db": validation[2]}
            rows.append(row)
            condition_rows.append(row)
        improvements = np.array([r["improvement_db"] for r in condition_rows])
        validation = np.array([r["holdout_validation_improvement_db"]
                               for r in condition_rows])
        state_counts = {state: sum(r["state"] == state for r in condition_rows)
                        for state in STATES}
        summaries.append({"grid": grid_label, "noise_sigma": noise,
                          "phase_rms_deg": phase, "realizations": realizations,
                          **{"improvement_q%d" % q: float(np.percentile(improvements, q))
                             for q in (50, 90, 95, 99)},
                          "holdout_validation_improvement_q50": float(np.percentile(validation, 50)),
                          "holdout_validation_improvement_q95": float(np.percentile(validation, 95)),
                          "existence_false_alarm_fraction": float(
                              (state_counts["RELIABLE"] + state_counts["MARGINAL"]) / realizations),
                          "ambiguous_fraction": float(state_counts["UNRESOLVED"] / realizations),
                          "clean_rejection_fraction": float(
                              state_counts["NO_SECOND_SOURCE"] / realizations),
                          "state_counts": json.dumps(state_counts, sort_keys=True)})
    return rows, summaries


def numerical_guard_rows(search, taps, kernel, xyz, wavelength_m, seeds):
    rows = []
    for seed in seeds:
        dense = synth_single(taps, kernel, xyz, wavelength_m, 20.0, 0.1, 0.0, seed)
        selected = search.select(dense)
        Y = dense.reshape(dense.shape[0], -1)
        direct_h1, _ = search._residual_for_indices(Y, [selected["h1_index"]])
        direct_h2, _ = search._residual_for_indices(
            Y, [selected["h2_index0"], selected["h2_index1"]])
        old_improvement = 10.0 * np.log10(
            direct_h1 / max(direct_h2, 1e-30))
        new_improvement = sd.residual_improvement_db(
            direct_h1, direct_h2, float(np.sum(np.abs(Y) ** 2)))
        rows.append({"seed": seed, "h1_residual": direct_h1,
                     "h2_residual": direct_h2,
                     "before_improvement_db": float(old_improvement),
                     "before_state": classify(old_improvement, selected["mu_joint"]),
                     "after_improvement_db": new_improvement,
                     "after_state": classify(new_improvement, selected["mu_joint"]),
                     "bug": "BUG CONFIRMED: exact-fit residual ratio at floating-point zero"})
    return rows


def self_test():
    taps = np.round(np.arange(-1.5, 1.5001, 0.1), 4)
    kernel = ftp.synth_kernel(taps)
    xyz = analysis.uca_xyz()
    search = DiscreteSearch(taps, kernel, xyz, analysis.L5_WAVELENGTH_M,
                            np.arange(0.0, 80.1, 10.0),
                            np.arange(-0.1, 0.201, 0.1), np.arange(0.3, 0.801, 0.1))
    dense = synth_single(taps, kernel, xyz, analysis.L5_WAVELENGTH_M,
                         17.0, 0.07, 0.03, 7908)
    fast = search.select(dense)
    reviewed = sd.fit(dense, taps, taps, kernel, 8, 0.5, 29.3,
                      angle_grid=np.arange(0.0, 80.1, 10.0),
                      tau0_grid=np.arange(-0.1, 0.201, 0.1),
                      tau1_grid=np.arange(0.3, 0.801, 0.1), array_xyz_m=xyz,
                      wavelength_m=analysis.L5_WAVELENGTH_M)
    for key in ("improvement_db", "mu_joint", "cond"):
        mapped = "condition_number" if key == "cond" else key
        assert np.isclose(fast[mapped], reviewed[key], rtol=1e-9, atol=1e-9)
    assert fast["state"] == reviewed["state"]
    assert search.refine_h1(dense, fast)["refined_h1_residual"] <= fast["h1_residual"]
    assert sd.residual_improvement_db(1e-28, 1e-29, 1000.0) == 0.0
    print("diagnostic self-test: PASS (fast search matches reviewed estimator; refinement non-increasing)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir")
    parser.add_argument("--realizations", type=int, default=200)
    parser.add_argument("--keep-raw", action="store_true",
                        help="retain per-realization Monte Carlo CSV (normally unnecessary)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.output_dir:
        parser.error("--output-dir is required")
    if args.realizations < 100:
        parser.error("--realizations must be at least 100")
    os.makedirs(args.output_dir, exist_ok=True)
    taps = np.round(np.arange(-1.5, 1.5001, 0.1), 4)
    kernel = ftp.synth_kernel(taps)
    xyz = analysis.uca_xyz()
    search = DiscreteSearch(taps, kernel, xyz, analysis.L5_WAVELENGTH_M,
                            np.arange(0.0, 80.1, 10.0),
                            np.arange(-0.1, 0.201, 0.1), np.arange(0.3, 0.801, 0.1))
    write_csv(os.path.join(args.output_dir, "canonical_on_off_grid.csv"),
              canonical_cases(search, taps, kernel, xyz, analysis.L5_WAVELENGTH_M,
                              range(7908, 7916)))
    write_csv(os.path.join(args.output_dir, "numerical_guard_before_after.csv"),
              numerical_guard_rows(search, taps, kernel, xyz,
                                   analysis.L5_WAVELENGTH_M, range(7908, 7916)))
    write_csv(os.path.join(args.output_dir, "grid_resolution_scan.csv"),
              grid_scan(taps, kernel, xyz, analysis.L5_WAVELENGTH_M, range(7908, 7928)))
    raw, summary = monte_carlo(search, taps, kernel, xyz,
                               analysis.L5_WAVELENGTH_M, args.realizations)
    if args.keep_raw:
        write_csv(os.path.join(args.output_dir, "h0_monte_carlo.csv"), raw)
    write_csv(os.path.join(args.output_dir, "h0_monte_carlo_summary.csv"), summary)
    metadata = {"reviewed_sha": "fa6c6c641b56120b765a10ee899098371d81fc7b",
                "evidence": "ideal_simulation_diagnostic", "realizations": args.realizations,
                "thresholds": {"detect_db": 3.0, "reliable_db": 6.0,
                               "mu_max": 0.98, "status": "PROVISIONAL"},
                "monte_carlo_seed_rule": "900000 + condition_index*N + realization",
                "grid_scan": "one-axis-at-a-time: delay step 0.1 during angle scan; angle step 10 during delay scan",
                "local_refinement": "Nelder-Mead initialized only from observation-selected coarse H1",
                "holdout": "first 6 snapshots select support; last 6 freeze support and refit amplitudes",
                "reproduce": "python dev_notes/sim/diagnose_h1_h2_false_positive.py "
                             "--output-dir <dir> --realizations %d" % args.realizations}
    with open(os.path.join(args.output_dir, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)
        fh.write("\n")
    print("wrote red-team diagnostics to %s" % args.output_dir)


if __name__ == "__main__":
    main()

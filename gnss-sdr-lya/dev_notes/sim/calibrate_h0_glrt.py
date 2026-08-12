#!/usr/bin/env python3
"""H0 (single-source) GLRT statistic simulation PRE-calibration -- doc19 s14.2.

Generates many single-source scenes (random continuous az/tau, per-block random
phases, optional per-element manifold error), runs the continuous H1/H2
estimator, and reports the empirical distribution of improvement_db under H0.
From it, a PROVISIONAL detect threshold at a requested false-alarm level.

HARD LIMIT (doc19 s14.2): this is simulation pre-calibration for development
only. It must NOT be used as the final experiment threshold. Before the
parking-garage experiment the pipeline is:
  real single-source captures -> refined H1/H2 -> empirical H0 distribution
  -> fix false-alarm level -> freeze threshold -> then dual-source data.

Example:
  python3 dev_notes/sim/calibrate_h0_glrt.py --n-trials 40 --noise-sigma 0.05
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_two_path as ftp  # noqa: E402
import fit_space_delay_h1h2 as h12  # noqa: E402


def run(args):
    rng = np.random.default_rng(args.seed)
    taps = np.round(np.arange(-1.5, 1.5001, 0.1), 4)
    kernel = ftp.synth_kernel(taps)
    if args.array_config:
        pos_wl, _ = h12.load_array_config(args.array_config)
    else:
        pos_wl = h12.ula_xyz(args.n_antennas, 0.5)
    az_grid = np.arange(args.az_min, args.az_max + 0.1, args.az_step)
    tau_grid = np.round(np.arange(-0.75, 1.5001, 0.1), 4)

    stats, states = [], {"ONE_SOURCE": 0, "TWO_SOURCE": 0, "UNRESOLVED": 0}
    cache = {}
    for t in range(args.n_trials):
        true_manifold = h12.IdealManifold(pos_wl)
        if args.manifold_error > 0:  # generation uses perturbed array, fit uses ideal
            pert = pos_wl + 0j  # placeholder shape
            eps = args.manifold_error * (rng.standard_normal((pos_wl.shape[0],))
                                         + 1j * rng.standard_normal((pos_wl.shape[0],))) / np.sqrt(2)

            class Pert(h12.IdealManifold):
                def a(self, az_deg, _eps=eps):
                    return super().a(az_deg) * (1.0 + _eps)
            true_manifold = Pert(pos_wl)
        az = rng.uniform(args.az_min, args.az_max)
        tau = rng.uniform(-0.1, 0.3)
        sc = h12.synth(true_manifold, taps, taps, kernel,
                       [(az, tau, 1.0)], args.n_blocks, args.noise_sigma, rng)
        r = h12.fit_h1h2(sc, taps, taps, kernel, h12.IdealManifold(pos_wl), 29.3,
                         az_grid=az_grid, tau_grid=tau_grid, refine_sweeps=2,
                         cache=cache)
        stats.append(r["improvement_db"])
        states[r["state"]] += 1
        if (t + 1) % 50 == 0:
            print("  trial %d/%d ..." % (t + 1, args.n_trials))

    stats = np.array(stats)
    q = {p: float(np.percentile(stats, p)) for p in (50, 90, 95, 99)}
    thr = float(np.percentile(stats, 100.0 * (1.0 - args.pfa)))
    out = dict(
        purpose="H0 GLRT simulation PRE-calibration (development only)",
        provisional=True,
        must_not_replace="real single-source negative-control calibration (doc19 s14.2)",
        n_trials=args.n_trials, n_antennas=int(pos_wl.shape[0]),
        n_blocks=args.n_blocks, noise_sigma=args.noise_sigma,
        manifold_error=args.manifold_error, pfa_target=args.pfa,
        improvement_db_percentiles=q,
        improvement_db_max=float(np.max(stats)),
        state_counts=states,
        two_source_false_alarm_fraction=states["TWO_SOURCE"] / max(args.n_trials, 1),
        provisional_detect_db_at_pfa=thr,
        note="evidence level: ideal simulation (+manifold perturbation if set); "
             "simulation-derived provisional")
    print(json.dumps(out, indent=2))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print("wrote %s" % args.output)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-trials", type=int, default=40)
    ap.add_argument("--n-antennas", type=int, default=4)
    ap.add_argument("--array-config", help="array_configs/*.json (fail-fast if unconfirmed)")
    ap.add_argument("--n-blocks", type=int, default=24)
    ap.add_argument("--noise-sigma", type=float, default=0.05)
    ap.add_argument("--manifold-error", type=float, default=0.0,
                    help="per-element complex gain error std (e.g. 0.05)")
    ap.add_argument("--pfa", type=float, default=0.05)
    ap.add_argument("--az-min", type=float, default=-60.0)
    ap.add_argument("--az-max", type=float, default=60.0)
    ap.add_argument("--az-step", type=float, default=10.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--output", help="write result JSON")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()

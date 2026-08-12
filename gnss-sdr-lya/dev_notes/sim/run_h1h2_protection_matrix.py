#!/usr/bin/env python3
"""Protection matrix for the doc23 structural fixes -- ideal simulation only.

Runs the fixed continuous H1/H2 estimator over:
  * main matrix: delta_tau x delta_az x power ratio x seeds
  * zero-delay set: delta_tau=0, large angles (incl. 180 deg ULA-degenerate)
  * Codex anchor-pressure cases: symmetric taus around 0
  * benchmark A: 0.5 chip / 30 deg / -6 dB, off-grid tau0

Outputs one CSV with per-run state/estimates/diagnostics/multi-start info.
Evidence level: ideal simulation (shared kernel and steering law).
"""

import argparse
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_two_path as ftp  # noqa: E402
import fit_space_delay_h1h2 as h12  # noqa: E402

FIELDS = ["section", "truth_tau0", "truth_tau1", "truth_delta_tau",
          "truth_delta_az", "power_ratio_db", "seed", "state", "detail",
          "improvement_db", "delta_tau_chips", "delta_az_deg", "amp_ratio_db",
          "mu_joint", "cond", "h1_residual", "h2_residual",
          "n_starts", "multi_start_winner", "winner_h1_seeded",
          "multi_start_residual_spread_db", "optimizer_status"]


def run_case(section, sources, pr_db, seed, taps, kernel, manifold, cache,
             az_grid, writer, truth):
    rng = np.random.default_rng(seed)
    sc = h12.synth(manifold, taps, taps, kernel, sources, 24, 0.05, rng)
    r = h12.fit_h1h2(sc, taps, taps, kernel, manifold, 29.3,
                     az_grid=az_grid, cache=cache)
    residuals = [st["residual"] for st in r["multi_start"] if st["status"] == "ok"]
    spread = 10.0 * np.log10(max(residuals) / max(min(residuals), 1e-30))
    winner = r["multi_start"][r["multi_start_winner"]]
    writer.writerow(dict(
        section=section, truth_tau0=truth[0], truth_tau1=truth[1],
        truth_delta_tau=truth[1] - truth[0], truth_delta_az=truth[2],
        power_ratio_db=pr_db, seed=seed, state=r["state"], detail=r["detail"],
        improvement_db=round(r["improvement_db"], 3),
        delta_tau_chips=(None if r["delta_tau_chips"] is None
                         else round(r["delta_tau_chips"], 4)),
        delta_az_deg=(None if r["delta_az_deg"] is None
                      else round(r["delta_az_deg"], 2)),
        amp_ratio_db=(None if r["amp_ratio_db"] is None
                      else round(r["amp_ratio_db"], 2)),
        mu_joint=round(r["mu_joint"], 4), cond=round(r["cond"], 2),
        h1_residual=round(r["h1_residual"], 3),
        h2_residual=round(r["h2_residual"], 3),
        n_starts=r["n_starts"], multi_start_winner=r["multi_start_winner"],
        winner_h1_seeded=winner.get("h1_seeded", False),
        multi_start_residual_spread_db=round(spread, 2),
        optimizer_status=";".join(st["status"] for st in r["multi_start"])))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="h1h2_protection_matrix.csv")
    ap.add_argument("--seeds", type=int, default=3)
    args = ap.parse_args()

    taps = np.round(np.arange(-1.5, 1.5001, 0.1), 4)
    kernel = ftp.synth_kernel(taps)
    ula = h12.IdealManifold(h12.ula_xyz(4, 0.5))
    cache = {}
    az_narrow = np.arange(-60.0, 60.1, 5.0)
    az_wide = np.arange(-90.0, 90.1, 5.0)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()

        # main matrix (tau0 off-grid 0.04 to stay honest)
        for dtau in (0.0, 0.25, 0.5, 1.0):
            for daz in (60, 40, 30, 20, 10):
                for pr in (0, -6):
                    amp1 = 10 ** (pr / 20.0)
                    for seed in range(args.seeds):
                        t0 = 0.04
                        srcs = [(-daz / 2.0, t0, 1.0), (daz / 2.0, t0 + dtau, amp1)]
                        run_case("matrix", srcs, pr, seed, taps, kernel, ula,
                                 cache, az_narrow, w, (t0, t0 + dtau, daz))
                        print("matrix dtau=%.2f daz=%d pr=%d seed=%d done"
                              % (dtau, daz, pr, seed))

        # zero-delay, wide angles (180 = ULA +/-90 endfire, spatially
        # degenerate for a lambda/2 ULA -- expected UNRESOLVED/ONE_SOURCE)
        for daz in (60, 90, 120, 180):
            for pr in (0, -6):
                amp1 = 10 ** (pr / 20.0)
                for seed in range(args.seeds):
                    srcs = [(-daz / 2.0, 0.0, 1.0), (daz / 2.0, 0.0, amp1)]
                    run_case("zero_delay", srcs, pr, seed, taps, kernel, ula,
                             cache, az_wide, w, (0.0, 0.0, daz))
            print("zero_delay daz=%d done" % daz)

        # Codex anchor-pressure cases
        for (t0, t1) in ((-0.25, 0.25), (-0.5, 0.5), (-0.18, 0.32)):
            for daz in (10, 20, 30):
                for seed in range(args.seeds):
                    srcs = [(-daz / 2.0, t0, 1.0), (daz / 2.0, t1, 1.0)]
                    run_case("anchor_pressure", srcs, 0, seed, taps, kernel,
                             ula, cache, az_narrow, w, (t0, t1, daz))
            print("anchor_pressure %.2f/%.2f done" % (t0, t1))

        # benchmark A: 0.5 chip / 30 deg / -6 dB, off-grid tau0
        amp1 = 10 ** (-6 / 20.0)
        for seed in range(5):
            srcs = [(-15.0, 0.07, 1.0), (15.0, 0.57, amp1)]
            run_case("benchmark_A", srcs, -6, seed, taps, kernel, ula, cache,
                     az_narrow, w, (0.07, 0.57, 30))
        print("benchmark_A done")
    print("wrote %s" % args.output)


if __name__ == "__main__":
    main()

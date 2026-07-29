#!/usr/bin/env python3
"""Track a second same-code source through delay-Doppler candidate continuity.

Each time segment produces several data-driven delay/Doppler candidates.  A
Viterbi-style dynamic program selects the smoothest high-score trajectory.
Ground truth from the synthetic data set is used only for final scoring.
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


def remove_path0_first_order(iq, taps, ktaps, kernel):
    k = ftp.kern_at(ktaps, kernel, taps)
    step = max(1e-4, float(np.median(np.diff(taps))) * 0.25)
    kp = ftp.kern_at(ktaps, kernel, taps - step)
    km = ftp.kern_at(ktaps, kernel, taps + step)
    dk = (kp - km) / (2.0 * step)
    basis = np.column_stack((k, dk))
    coef = iq @ np.conj(basis) @ np.linalg.pinv(basis.T @ np.conj(basis))
    fitted = coef @ basis.T
    return iq - fitted


def top_candidates(M, freqs, tau_grid, top_k, guard_hz, min_delay_chips,
                   nms_delay_chips, nms_hz, chip_m):
    p0 = np.unravel_index(int(np.argmax(M)), M.shape)
    f0 = float(freqs[p0[0]])
    allowed = (
        (np.abs(freqs[:, None] - f0) >= guard_hz)
        & (tau_grid[None, :] >= min_delay_chips)
    )
    noise = float(np.median(M[allowed])) if allowed.any() else float(np.median(M))
    ranked = np.argsort(np.where(allowed, M, -np.inf).ravel())[::-1]
    out = []
    for flat in ranked:
        fi, ti = np.unravel_index(int(flat), M.shape)
        if not np.isfinite(M[fi, ti]):
            break
        delay_m = float(tau_grid[ti] * chip_m)
        doppler_hz = float(freqs[fi] - f0)
        if any(abs(delay_m - c["delay_m"]) < nms_delay_chips * chip_m
               and abs(doppler_hz - c["doppler_hz"]) < nms_hz for c in out):
            continue
        score_db = 20.0 * np.log10(max(float(M[fi, ti]), 1e-30) / max(noise, 1e-30))
        out.append({
            "delay_m": delay_m,
            "doppler_hz": doppler_hz,
            "score_db": score_db,
        })
        if len(out) >= top_k:
            break
    return out


def select_trajectory(candidate_sets, segment_dt, wavelength_m, delay_scale_m,
                      doppler_scale_hz, score_weight):
    if not candidate_sets or any(not row for row in candidate_sets):
        return None
    costs = [-score_weight * np.asarray([c["score_db"] for c in candidate_sets[0]])]
    parents = []
    for current in candidate_sets[1:]:
        previous = candidate_sets[len(costs) - 1]
        next_cost = np.full(len(current), np.inf)
        next_parent = np.full(len(current), -1, dtype=int)
        for j, candidate in enumerate(current):
            transitions = np.asarray([
                ((candidate["delay_m"] - p["delay_m"]
                  + wavelength_m * 0.5
                  * (candidate["doppler_hz"] + p["doppler_hz"])
                  * segment_dt) / delay_scale_m) ** 2
                + ((candidate["doppler_hz"] - p["doppler_hz"]) / doppler_scale_hz) ** 2
                for p in previous
            ])
            total = costs[-1] + transitions
            parent = int(np.argmin(total))
            next_cost[j] = total[parent] - score_weight * candidate["score_db"]
            next_parent[j] = parent
        costs.append(next_cost)
        parents.append(next_parent)
    index = int(np.argmin(costs[-1]))
    path = [candidate_sets[-1][index]]
    for layer in range(len(parents) - 1, -1, -1):
        index = int(parents[layer][index])
        path.append(candidate_sets[layer][index])
    return list(reversed(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="moving two-source .npz")
    ap.add_argument("--kernel", help="same kernel CSV used by the generator")
    ap.add_argument("--segment-s", type=float, default=1.0)
    ap.add_argument("--path0-model", choices=("none", "k-dk-epoch"), default="none",
                    help="default keeps temporal modulation; per-epoch K+dK is diagnostic only because it can absorb a merged path")
    ap.add_argument("--tau-min", type=float, default=0.05)
    ap.add_argument("--tau-max", type=float, default=1.5)
    ap.add_argument("--tau-step", type=float, default=0.025)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--guard-hz", type=float, default=None)
    ap.add_argument("--nms-delay-chips", type=float, default=0.04)
    ap.add_argument("--nms-hz", type=float, default=0.5)
    ap.add_argument("--delay-scale-m", type=float, default=3.0)
    ap.add_argument("--doppler-scale-hz", type=float, default=1.0)
    ap.add_argument("--score-weight", type=float, default=0.08)
    ap.add_argument("--csv")
    ap.add_argument("--plot")
    args = ap.parse_args()

    data = np.load(args.input, allow_pickle=False)
    iq = data["iq"].astype(np.complex128)
    times = data["times_s"].astype(np.float64)
    taps = data["taps_chips"].astype(np.float64)
    truth_delay = data["delta_m"].astype(np.float64)
    truth_doppler = data["delta_doppler_hz"].astype(np.float64)
    meta = json.loads(str(data["meta_json"]))
    chip_m = float(meta["chip_m"])
    if args.kernel:
        ktaps, kernel = ftp.load_reference_csv(args.kernel)
    else:
        ktaps, kernel = taps.copy(), ftp.synth_kernel(taps)

    dt = float(np.median(np.diff(times)))
    segment_epochs = max(64, int(round(args.segment_s / dt)))
    tau_grid = np.arange(args.tau_min, args.tau_max + 0.5 * args.tau_step,
                         args.tau_step)
    guard_hz = args.guard_hz if args.guard_hz is not None else 2.0 / (
        segment_epochs * dt)
    residual = (
        remove_path0_first_order(iq, taps, ktaps, kernel)
        if args.path0_model == "k-dk-epoch" else iq
    )

    candidate_sets = []
    segment_rows = []
    for start in range(0, len(iq) - segment_epochs + 1, segment_epochs):
        end = start + segment_epochs
        M, freqs = dd.delay_doppler_map(
            residual[start:end], dt, ktaps, kernel, taps, tau_grid)
        candidates = top_candidates(
            M, freqs, tau_grid, args.top_k, guard_hz, args.tau_min,
            args.nms_delay_chips, args.nms_hz, chip_m)
        if not candidates:
            continue
        mid = (start + end - 1) // 2
        candidate_sets.append(candidates)
        segment_rows.append({
            "time_s": float(times[mid]),
            "truth_delay_m": float(truth_delay[mid]),
            "truth_doppler_hz": float(truth_doppler[mid]),
            "snapshot_delay_m": candidates[0]["delay_m"],
            "snapshot_doppler_hz": candidates[0]["doppler_hz"],
        })

    trajectory = select_trajectory(
        candidate_sets, segment_epochs * dt,
        299792458.0 / float(meta["carrier_hz"]),
        args.delay_scale_m, args.doppler_scale_hz, args.score_weight)
    if trajectory is None:
        raise SystemExit("no complete candidate trajectory")
    for row, selected in zip(segment_rows, trajectory):
        row.update({
            "track_delay_m": selected["delay_m"],
            "track_doppler_hz": selected["doppler_hz"],
            "track_score_db": selected["score_db"],
        })

    truth = np.asarray([r["truth_delay_m"] for r in segment_rows])
    snapshot = np.asarray([r["snapshot_delay_m"] for r in segment_rows])
    tracked = np.asarray([r["track_delay_m"] for r in segment_rows])
    track_error = np.abs(tracked - truth)
    snapshot_error = np.abs(snapshot - truth)
    within = track_error <= max(3.0, 0.1 * chip_m)
    reliable = (
        len(tracked) >= 5
        and float(np.mean(within)) >= 0.8
        and float(np.percentile(track_error, 90)) <= 5.0
    )

    print("input: %s" % args.input)
    print("segments=%d segment=%.2fs candidates/segment=%d guard=%.2fHz" %
          (len(tracked), segment_epochs * dt, args.top_k, guard_hz))
    print("truth delay span: %.2f..%.2f m; Doppler span: %+.3f..%+.3f Hz" %
          (truth.min(), truth.max(),
           min(r["truth_doppler_hz"] for r in segment_rows),
           max(r["truth_doppler_hz"] for r in segment_rows)))
    print("snapshot top1: median abs error %.2f m, p90 %.2f m" %
          (np.median(snapshot_error), np.percentile(snapshot_error, 90)))
    print("trajectory   : median abs error %.2f m, p90 %.2f m, within %.1f%%" %
          (np.median(track_error), np.percentile(track_error, 90),
           100.0 * np.mean(within)))
    print("VERDICT: %s" % ("RELIABLE" if reliable else "UNRELIABLE"))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(segment_rows[0]))
            writer.writeheader()
            writer.writerows(segment_rows)
        print("wrote %s" % args.csv)

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        t = np.asarray([r["time_s"] for r in segment_rows])
        plt.figure(figsize=(9, 4.8))
        plt.plot(t, truth, "k-", linewidth=2, label="truth")
        plt.plot(t, snapshot, ".", alpha=0.55, label="snapshot top1")
        plt.plot(t, tracked, "o-", markersize=3, label="trajectory")
        plt.xlabel("Time [s]")
        plt.ylabel("Relative delay [m]")
        plt.title("Moving two-source delay trajectory")
        plt.grid(alpha=0.25)
        plt.legend()
        plt.tight_layout()
        plt.savefig(args.plot, dpi=150)
        print("wrote %s" % args.plot)


if __name__ == "__main__":
    main()

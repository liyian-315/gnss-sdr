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
import build_path0_texture_model as texture  # noqa: E402


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
                   nms_delay_chips, nms_hz, chip_m,
                   map_peak_is_path0=True):
    if map_peak_is_path0:
        p0 = np.unravel_index(int(np.argmax(M)), M.shape)
        f0 = float(freqs[p0[0]])
        doppler_allowed = np.abs(freqs[:, None] - f0) >= guard_hz
    else:
        f0 = 0.0
        doppler_allowed = np.ones((len(freqs), 1), dtype=bool)
    allowed = doppler_allowed & (tau_grid[None, :] >= min_delay_chips)
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


def texture_glrt_map(iq_seg, dt, taps, ktaps, kernel, tau_grid, model):
    basis = texture.path0_basis(taps, ktaps, kernel)
    whitened_iq, _coeff = texture.whiten_residual(iq_seg, basis, model)
    templates = []
    for delay in tau_grid:
        shifted = ftp.kern_at(ktaps, kernel, taps - delay)
        templates.append(texture.whiten_template(shifted, basis, model))
    templates = np.asarray(templates)
    norms = np.maximum(np.linalg.norm(templates, axis=1), 1e-12)
    matched = whitened_iq @ np.conj(templates).T / norms[None, :]
    win = np.hanning(len(matched))[:, None] if len(matched) >= 8 else np.ones((len(matched), 1))
    spectrum = np.fft.fftshift(np.fft.fft(matched * win, axis=0), axes=0)
    freqs = np.fft.fftshift(np.fft.fftfreq(len(matched), d=dt))
    return np.abs(spectrum), freqs


def map_peak_score_db(M, tau_grid, min_delay_chips):
    """Max texture-whitened matched power relative to the map median."""
    allowed = tau_grid[None, :] >= min_delay_chips
    samples = M[np.broadcast_to(allowed, M.shape)]
    noise = float(np.median(samples))
    peak = float(np.max(samples))
    return 20.0 * np.log10(max(peak, 1e-30) / max(noise, 1e-30))


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


def trajectory_total_cost(path, segment_dt, wavelength_m, delay_scale_m,
                          doppler_scale_hz, score_weight):
    """Total DP cost of a chosen path (same model as select_trajectory): score reward
    plus physical delay-Doppler transition penalty. Used for the best-vs-second margin."""
    cost = -score_weight * sum(p["score_db"] for p in path)
    for a, b in zip(path[:-1], path[1:]):
        dstep = (b["delay_m"] - a["delay_m"]
                 + wavelength_m * 0.5 * (b["doppler_hz"] + a["doppler_hz"]) * segment_dt) / delay_scale_m
        fstep = (b["doppler_hz"] - a["doppler_hz"]) / doppler_scale_hz
        cost += dstep * dstep + fstep * fstep
    return float(cost)


def second_best_cost(best_path, candidate_sets, tube_m, segment_dt, wavelength_m,
                     delay_scale_m, doppler_scale_hz, score_weight):
    """Cost of the best trajectory materially different from ``best_path``.

    A distinct alternative only needs to leave the best path's delay tube in
    one segment. Requiring that at every segment made the margin infinite when
    a single segment had no distant candidate, which overstated uniqueness.
    """
    alternative_costs = []
    for forced_segment, chosen in enumerate(best_path):
        masked = [list(cands) for cands in candidate_sets]
        masked[forced_segment] = [
            c for c in candidate_sets[forced_segment]
            if abs(c["delay_m"] - chosen["delay_m"]) > tube_m
        ]
        if not masked[forced_segment]:
            continue
        alt_path = select_trajectory(
            masked, segment_dt, wavelength_m,
            delay_scale_m, doppler_scale_hz, score_weight
        )
        if alt_path is not None:
            alternative_costs.append(
                trajectory_total_cost(
                    alt_path, segment_dt, wavelength_m,
                    delay_scale_m, doppler_scale_hz, score_weight
                )
            )
    return min(alternative_costs) if alternative_costs else float("inf")


def trajectory_confidence(best_path, candidate_sets, segment_dt, wavelength_m,
                          delay_scale_m, doppler_scale_hz, score_weight, chip_m, tube_chips):
    """Truth-free confidence signals (NO ground truth). Real captures have no truth, so
    this is the gate that must run on hardware:
      - motion diversity: a real moving source sweeps delay AND Doppler; a static latch
        is ~flat -> this is the diversity gate that rejects the DP static false positives.
      - physics link: does delay[k]-delay[k-1] match -lambda*mean(Doppler)*dt? tests that
        the track obeys geometry, not just smoothness.
      - best-vs-second margin: how much better the chosen path is than the best
        materially-different alternative (unique vs ambiguous).
    """
    delays = np.asarray([p["delay_m"] for p in best_path])
    dopp = np.asarray([p["doppler_hz"] for p in best_path])
    scores = np.asarray([p["score_db"] for p in best_path])
    if len(delays) > 1:
        pred = -wavelength_m * 0.5 * (dopp[1:] + dopp[:-1]) * segment_dt
        obs = delays[1:] - delays[:-1]
        physics_resid = float(np.sqrt(np.mean((obs - pred) ** 2)))
    else:
        physics_resid = float("nan")
    best_cost = trajectory_total_cost(best_path, segment_dt, wavelength_m,
                                      delay_scale_m, doppler_scale_hz, score_weight)
    alt_cost = second_best_cost(best_path, candidate_sets, tube_chips * chip_m, segment_dt,
                                wavelength_m, delay_scale_m, doppler_scale_hz, score_weight)
    return dict(delay_span_m=float(delays.max() - delays.min()),
                doppler_span_hz=float(dopp.max() - dopp.min()),
                physics_resid_m=physics_resid, min_score_db=float(scores.min()),
                best_cost=best_cost, alt_cost=alt_cost, margin=float(alt_cost - best_cost))


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
    ap.add_argument("--texture-model",
                    help="A-only path0 residual texture model; enables whitened GLRT candidates")
    ap.add_argument("--conf-min-motion-m", type=float, default=3.0,
                    help="truth-free gate: min delay span of the track (a static latch is ~flat)")
    ap.add_argument("--conf-min-doppler-hz", type=float, default=0.5,
                    help="truth-free gate: min Doppler span (the real separation axis)")
    ap.add_argument("--conf-max-physics-m", type=float, default=3.0,
                    help="truth-free gate: max RMS delay-step vs -lambda*Doppler*dt residual")
    ap.add_argument("--conf-min-margin", type=float, default=0.0,
                    help="truth-free gate: min best-vs-2nd trajectory cost margin (default 0 = report only; "
                         "calibrate on the cross-reference benchmark before gating on it)")
    ap.add_argument("--conf-tube-chips", type=float, default=0.2,
                    help="delay tube [chips] a 2nd-best trajectory must clear the best by")
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
    texture_model = None
    if args.texture_model:
        texture_model = texture.load_model(args.texture_model)
        if (
            len(texture_model["taps"]) != len(taps)
            or not np.allclose(texture_model["taps"], taps)
        ):
            raise SystemExit("texture-model tap grid does not match input")

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
    glrt_peak_scores = []
    for start in range(0, len(iq) - segment_epochs + 1, segment_epochs):
        end = start + segment_epochs
        if texture_model is not None:
            M, freqs = texture_glrt_map(
                iq[start:end], dt, taps, ktaps, kernel, tau_grid, texture_model
            )
        else:
            M, freqs = dd.delay_doppler_map(
                residual[start:end], dt, ktaps, kernel, taps, tau_grid)
        if texture_model is not None:
            glrt_peak_scores.append(
                map_peak_score_db(M, tau_grid, args.tau_min)
            )
        candidates = top_candidates(
            M, freqs, tau_grid, args.top_k, guard_hz, args.tau_min,
            args.nms_delay_chips, args.nms_hz, chip_m,
            map_peak_is_path0=texture_model is None)
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

    # truth-free confidence (the gate a REAL capture must use -- no ground truth here)
    wavelength_m = 299792458.0 / float(meta["carrier_hz"])
    conf = trajectory_confidence(
        trajectory, candidate_sets, segment_epochs * dt, wavelength_m,
        args.delay_scale_m, args.doppler_scale_hz, args.score_weight,
        chip_m, args.conf_tube_chips)
    conf_reasons = []
    if conf["delay_span_m"] < args.conf_min_motion_m or conf["doppler_span_hz"] < args.conf_min_doppler_hz:
        conf_reasons.append("no motion diversity (delay span %.1f m, Doppler %.2f Hz -> static latch)"
                            % (conf["delay_span_m"], conf["doppler_span_hz"]))
    if np.isnan(conf["physics_resid_m"]) or conf["physics_resid_m"] > args.conf_max_physics_m:
        conf_reasons.append("delay-Doppler link violated (physics resid %.2f m)" % conf["physics_resid_m"])
    if conf["margin"] < args.conf_min_margin:
        conf_reasons.append("best-vs-2nd margin %.2f < %.2f (ambiguous)" % (conf["margin"], args.conf_min_margin))
    confident = not conf_reasons

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
    print("candidate likelihood: %s" %
          ("path0-texture whitened GLRT" if texture_model is not None else "unwhitened matched map"))
    if glrt_peak_scores:
        print(
            "texture GLRT peak: min %.2f dB, median %.2f dB, mean %.2f dB"
            % (
                np.min(glrt_peak_scores),
                np.median(glrt_peak_scores),
                np.mean(glrt_peak_scores),
            )
        )
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
    print("(truth-based synthetic scoring only; real captures must use CONFIDENCE)")
    print("\n--- truth-free confidence (NO ground truth; this is the REAL-DATA gate) ---")
    print("motion diversity : delay span %.1f m, Doppler span %.2f Hz  (static latch is ~flat -> rejected)"
          % (conf["delay_span_m"], conf["doppler_span_hz"]))
    print("physics link     : resid %.2f m  (delay-step vs -lambda*Doppler*dt; tests geometry, not smoothness)"
          % conf["physics_resid_m"])
    print("best-vs-2nd path : margin %.2f  (best cost %.2f, 2nd-best %.2f; larger = more unique)"
          % (conf["margin"], conf["best_cost"], conf["alt_cost"]))
    print("CONFIDENCE: %s%s" % ("CONFIDENT" if confident else "LOW-CONFIDENCE",
                                "" if confident else " -- " + "; ".join(conf_reasons)))

    if args.csv:
        confidence_fields = {
            "truth_verdict": "RELIABLE" if reliable else "UNRELIABLE",
            "confidence": "CONFIDENT" if confident else "LOW-CONFIDENCE",
            "confidence_delay_span_m": conf["delay_span_m"],
            "confidence_doppler_span_hz": conf["doppler_span_hz"],
            "confidence_physics_resid_m": conf["physics_resid_m"],
            "confidence_best_cost": conf["best_cost"],
            "confidence_alt_cost": conf["alt_cost"],
            "confidence_margin": conf["margin"],
        }
        for row in segment_rows:
            row.update(confidence_fields)
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

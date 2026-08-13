#!/usr/bin/env python3
"""Reproduce a 2x2 SAGE/STAP multicorrelator experiment and compare ULA+FBSS.

The implementation follows the path-wise SAGE idea from Rougerie et al. (2012):
subtract all other paths, maximize the current path's space-delay-Doppler
matched likelihood, update its complex amplitude, and iterate.  It is an
azimuth-only slice with fixed elevation, not yet the paper's full 3-D receiver.

Both array methods receive the same path parameters, kernel, block count, and
noise realization policy.  A measured Phase-A kernel CSV can replace the ideal
kernel with --kernel-csv.
"""

import argparse
import csv
import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

import compare_parking_array_geometries as geometry
import fit_two_path as ftp
import simulate_coherent_music_parking as music


CHIP_M = 29.3


def load_kernel(path=None, tap_step=0.1):
    if path:
        taps, kernel = ftp.load_reference_csv(path)
        kernel = kernel / max(np.max(np.abs(kernel)), 1e-12)
        return taps, kernel
    taps = np.arange(-1.5, 1.5001, tap_step)
    # Paper-compatible rectangular-chip autocorrelation. Both methods use it.
    kernel = np.maximum(0.0, 1.0 - np.abs(taps)).astype(complex)
    return taps, kernel


def square_positions(spacing_wl=0.5):
    return geometry.upa_positions(2, 2, spacing_wl)


def ula_positions(spacing_wl=0.5):
    return music.ula_positions(4, spacing_wl, axis_deg=0.0)


def steering(positions, bearing_deg):
    return music.steering_from_positions(positions, bearing_deg)


def response(kernel_taps, kernel, output_taps, delay_chips):
    return ftp.kern_at(kernel_taps, kernel, output_taps - delay_chips)


def synthesize(paths, positions, output_taps, kernel_taps, kernel, n_blocks,
               noise_sigma, rng, block_s=0.001):
    """Return complex STAP multicorrelator data with shape (block, antenna, tap)."""
    times = np.arange(n_blocks) * block_s
    clean = np.zeros((n_blocks, len(positions), len(output_taps)), complex)
    for path in paths:
        spatial = steering(positions, path["bearing_deg"])
        temporal = response(kernel_taps, kernel, output_taps, path["delay_chips"])
        carrier = np.exp(1j * (np.radians(path.get("phase_deg", 0.0))
                               + 2.0 * np.pi * path.get("doppler_hz", 0.0) * times))
        amplitude = 10.0 ** (path.get("ratio_db", 0.0) / 20.0)
        clean += amplitude * carrier[:, None, None] * spatial[None, :, None] * temporal[None, None, :]
    noise = noise_sigma / np.sqrt(2.0) * (
        rng.standard_normal(clean.shape) + 1j * rng.standard_normal(clean.shape)
    )
    return clean + noise


def atom(positions, output_taps, kernel_taps, kernel, times, bearing, delay, doppler):
    spatial = steering(positions, bearing)
    temporal = response(kernel_taps, kernel, output_taps, delay)
    carrier = np.exp(1j * 2.0 * np.pi * doppler * times)
    return carrier[:, None, None] * spatial[None, :, None] * temporal[None, None, :]


def best_atom(hidden, positions, output_taps, kernel_taps, kernel, times,
              angle_grid, delay_grid, doppler_grid):
    angles = np.asarray(angle_grid, dtype=float)
    delays = np.asarray(delay_grid, dtype=float)
    spatial = np.column_stack([steering(positions, angle) for angle in angles])
    temporal = np.column_stack([
        response(kernel_taps, kernel, output_taps, delay) for delay in delays
    ])
    spatial_norm = np.sum(abs(spatial) ** 2, axis=0)
    temporal_norm = np.sum(abs(temporal) ** 2, axis=0)
    best = None
    for doppler in doppler_grid:
        carrier = np.exp(1j * 2.0 * np.pi * doppler * times)
        demodulated = np.einsum("b,bmt->mt", carrier.conj(), hidden)
        inner = spatial.conj().T @ demodulated @ temporal.conj()
        denominator = len(times) * spatial_norm[:, None] * temporal_norm[None, :]
        score = abs(inner) ** 2 / np.maximum(denominator, 1e-15)
        flat = int(np.argmax(score))
        angle_index, delay_index = np.unravel_index(flat, score.shape)
        if best is None or score[angle_index, delay_index] > best[0]:
            angle = angles[angle_index]
            delay = delays[delay_index]
            base = spatial[:, angle_index][None, :, None] * temporal[:, delay_index][None, None, :]
            candidate = carrier[:, None, None] * base
            coefficient = inner[angle_index, delay_index] / denominator[angle_index, delay_index]
            best = (float(score[angle_index, delay_index]), float(angle), float(delay),
                    float(doppler), complex(coefficient), candidate)
    return best


def sage_stap(data, positions, output_taps, kernel_taps, kernel, path_grids,
              iterations=5, block_s=0.001):
    """Path-wise SAGE updates; path_grids contains angle/delay/doppler grids."""
    times = np.arange(data.shape[0]) * block_s
    estimates = []
    prediction = np.zeros_like(data)
    # Sequential matched-filter initialization is the first SAGE sweep.
    for grids in path_grids:
        best = best_atom(data - prediction, positions, output_taps, kernel_taps,
                         kernel, times, *grids)
        estimates.append(dict(bearing_deg=best[1], delay_chips=best[2],
                              doppler_hz=best[3], coefficient=best[4], atom=best[5]))
        prediction += best[4] * best[5]

    history = [float(np.linalg.norm(data - prediction) ** 2)]
    for _ in range(iterations):
        for index, grids in enumerate(path_grids):
            other = prediction - estimates[index]["coefficient"] * estimates[index]["atom"]
            best = best_atom(data - other, positions, output_taps, kernel_taps,
                             kernel, times, *grids)
            prediction = other + best[4] * best[5]
            estimates[index] = dict(bearing_deg=best[1], delay_chips=best[2],
                                    doppler_hz=best[3], coefficient=best[4], atom=best[5])
        history.append(float(np.linalg.norm(data - prediction) ** 2))
    for estimate in estimates:
        estimate.pop("atom")
        estimate["amplitude"] = abs(estimate.pop("coefficient"))
    return estimates, history


def find_two_peaks(spectrum, grid, minimum_separation_deg=5.0):
    order = np.argsort(spectrum)[::-1]
    peaks = []
    for index in order:
        candidate = float(grid[index])
        if all(abs(candidate - old) >= minimum_separation_deg for old in peaks):
            peaks.append(candidate)
        if len(peaks) == 2:
            break
    return sorted(peaks)


def ula_fbss(data, positions, output_taps, kernel_taps, kernel, angle_grid,
             delay_grid, prompt_index=None, bearing_half_plane=None):
    """FBSS-MUSIC DOA recovery, then spatial LS and matched-delay estimation."""
    if prompt_index is None:
        # Use the same complete multicorrelator observation as SAGE/STAP. A
        # prompt-only covariance would hide paths near one-chip delay.
        snapshots = data.transpose(1, 0, 2).reshape(data.shape[1], -1)
    else:
        snapshots = data[:, :, prompt_index].T
    raw_cov = music.covariance(snapshots)
    smooth = music.forward_backward_spatial_smoothing(raw_cov, 3)
    # ULA lies on x. theta is measured from broadside, while bearing is global.
    theta_grid = np.arange(-85.0, 85.01, 1.0)
    spectrum, eigenvalues = music.music_spectrum(smooth, 2, theta_grid)
    theta_peaks = find_two_peaks(spectrum, theta_grid)
    bearings = sorted([90.0 - theta for theta in theta_peaks])
    if bearing_half_plane == "negative_y":
        # A ULA cannot distinguish +bearing from -bearing. Parking geometry can
        # provide only the half-plane (all ceiling emitters below the receiver
        # in this coordinate system), without revealing either true angle.
        bearings = sorted([-abs(bearing) for bearing in bearings])
    manifold = np.column_stack([steering(positions, bearing) for bearing in bearings])
    pinv = np.linalg.pinv(manifold)
    separated = np.einsum("sm,bmt->bst", pinv, data)
    estimates = []
    for source_index, bearing in enumerate(bearings):
        profile = np.mean(separated[:, source_index, :], axis=0)
        scores = []
        for delay in delay_grid:
            template = response(kernel_taps, kernel, output_taps, delay)
            scores.append(abs(np.vdot(template, profile)) ** 2 /
                          max(float(np.vdot(template, template).real), 1e-15))
        estimates.append(dict(bearing_deg=bearing,
                              delay_chips=float(delay_grid[int(np.argmax(scores))])))
    return estimates, spectrum, theta_grid, eigenvalues


def match_errors(estimates, truth):
    if len(estimates) != len(truth):
        return None
    difference = music.circular_angle_difference
    direct = sum(difference(estimates[i]["bearing_deg"], truth[i]["bearing_deg"])
                 for i in range(len(truth)))
    swapped = sum(difference(estimates[::-1][i]["bearing_deg"], truth[i]["bearing_deg"])
                  for i in range(len(truth)))
    ordered = estimates if direct <= swapped else estimates[::-1]
    angle_rmse = np.sqrt(np.mean([difference(ordered[i]["bearing_deg"], truth[i]["bearing_deg"]) ** 2
                                  for i in range(len(truth))]))
    delay_rmse = np.sqrt(np.mean([(ordered[i]["delay_chips"] - truth[i]["delay_chips"]) ** 2 for i in range(len(truth))]))
    return float(angle_rmse), float(delay_rmse)


def paper_reproduction(kernel_csv=None, seed=20260813):
    ktaps, kernel = load_kernel(kernel_csv)
    taps = np.arange(-0.9, 1.0001, 0.1)  # P=20, Cs=0.1 chip from the paper.
    positions = square_positions()
    paths = [
        dict(bearing_deg=131.0, delay_chips=0.0, doppler_hz=0.0, ratio_db=0.0, phase_deg=0.0),
        dict(bearing_deg=-65.0, delay_chips=0.1, doppler_hz=5.0, ratio_db=-3.0, phase_deg=0.0),
    ]
    data = synthesize(paths, positions, taps, ktaps, kernel, 20, 0.08,
                      np.random.default_rng(seed))
    path_grids = [
        (np.arange(121.0, 141.1, 2.0), np.array([0.0]), np.array([0.0])),
        (np.arange(-85.0, -44.9, 2.0), np.arange(0.0, 0.201, 0.02), np.arange(0.0, 10.1, 1.0)),
    ]
    estimates, history = sage_stap(data, positions, taps, ktaps, kernel, path_grids)
    return dict(truth=paths, estimates=estimates, residual_history=history,
                kernel_source=str(kernel_csv or "ideal_rectangular_chip"))


def paper_monte_carlo(kernel_csv=None, trials=100, seed=20260813):
    """Paper-style Monte Carlo summary for the azimuth-only SAGE/STAP slice."""
    rows = []
    for trial in range(trials):
        result = paper_reproduction(kernel_csv, seed + trial)
        estimates = result["estimates"]
        truth = result["truth"]
        rows.append(dict(
            los_angle_error_deg=estimates[0]["bearing_deg"] - truth[0]["bearing_deg"],
            mp_angle_error_deg=estimates[1]["bearing_deg"] - truth[1]["bearing_deg"],
            mp_delay_error_chips=estimates[1]["delay_chips"] - truth[1]["delay_chips"],
            mp_doppler_error_hz=estimates[1]["doppler_hz"] - truth[1]["doppler_hz"],
            residual_reduction_db=10.0 * np.log10(
                result["residual_history"][0] / max(result["residual_history"][-1], 1e-15))))
    def rmse(name):
        return float(np.sqrt(np.mean([row[name] ** 2 for row in rows])))
    return dict(trials=trials, los_angle_rmse_deg=rmse("los_angle_error_deg"),
                mp_angle_rmse_deg=rmse("mp_angle_error_deg"),
                mp_delay_rmse_chips=rmse("mp_delay_error_chips"),
                mp_delay_rmse_m=rmse("mp_delay_error_chips") * CHIP_M,
                mp_doppler_rmse_hz=rmse("mp_doppler_error_hz"),
                residual_reduction_median_db=float(np.median(
                    [row["residual_reduction_db"] for row in rows])))


def parking_paths(receiver_xy, delay_chips=0.5, ratio_db=-6.0):
    tx = [np.array([-10.0, 0.0]), np.array([10.0, 0.0])]
    bearings = [float(np.degrees(np.arctan2(*(point - receiver_xy)[::-1]))) for point in tx]
    return [dict(bearing_deg=bearings[0], delay_chips=0.0, doppler_hz=0.0,
                 ratio_db=0.0, phase_deg=0.0),
            dict(bearing_deg=bearings[1], delay_chips=delay_chips, doppler_hz=0.0,
                 ratio_db=ratio_db, phase_deg=60.0)]


def parking_benchmark(output_dir, kernel_csv=None, trials=20, seed=20260813,
                      delay_values=(0.1, 0.3, 0.5, 1.0),
                      ratio_values=(0.0, -6.0, -10.0)):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ktaps, kernel = load_kernel(kernel_csv)
    taps = np.arange(-1.5, 1.5001, 0.1)
    positions_by_method = {"SAGE_2x2": square_positions(),
                           "ULA_FBSS_blind": ula_positions(),
                           "ULA_FBSS_halfplane": ula_positions()}
    receivers = [np.array([0.0, 5.0]), np.array([-5.0, 5.0]),
                 np.array([0.0, 15.0]), np.array([15.0, 5.0])]
    rows = []
    rng = np.random.default_rng(seed)
    for delay_chips in delay_values:
        for ratio_db in ratio_values:
            for receiver in receivers:
                truth = parking_paths(receiver, delay_chips, ratio_db)
                for trial in range(trials):
                    noise_seed = int(rng.integers(0, 2**31 - 1))
                    for method, positions in positions_by_method.items():
                        data = synthesize(truth, positions, taps, ktaps, kernel, 40, 0.08,
                                          np.random.default_rng(noise_seed))
                        if method == "SAGE_2x2":
                            grids = []
                            for path in truth:
                                delays = (np.array([0.0]) if path["delay_chips"] == 0 else
                                          np.arange(0.05, 1.201, 0.05))
                                # Full bearing search: neither method may look at truth angles.
                                grids.append((np.arange(-180.0, 180.1, 3.0), delays, np.array([0.0])))
                            estimates, _ = sage_stap(data, positions, taps, ktaps, kernel, grids, iterations=4)
                        else:
                            estimates, _, _, _ = ula_fbss(
                                data, positions, taps, ktaps, kernel, None,
                                np.arange(0.0, 1.201, 0.02),
                                bearing_half_plane=("negative_y" if method.endswith("halfplane") else None))
                        errors = match_errors(estimates, truth)
                        angle_rmse, delay_rmse = errors if errors else (np.inf, np.inf)
                        success = angle_rmse <= 5.0 and delay_rmse * CHIP_M <= 6.0
                        rows.append(dict(method=method, delay_chips=delay_chips,
                                         delay_m=delay_chips * CHIP_M, ratio_db=ratio_db,
                                         receiver_x_m=receiver[0], receiver_y_m=receiver[1],
                                         trial=trial, angle_rmse_deg=angle_rmse,
                                         delay_rmse_m=delay_rmse * CHIP_M, success=int(success)))
    csv_path = output_dir / "SAGE方阵与ULA_FBSS停车场公平比较.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    summary = {}
    for method in positions_by_method:
        selected = [row for row in rows if row["method"] == method]
        summary[method] = dict(success_rate=float(np.mean([row["success"] for row in selected])),
                               angle_rmse_median_deg=float(np.median([row["angle_rmse_deg"] for row in selected])),
                               delay_rmse_median_m=float(np.median([row["delay_rmse_m"] for row in selected])))
    summary["kernel_source"] = str(kernel_csv or "ideal_rectangular_chip")
    summary["conditions"] = []
    for method in positions_by_method:
        for delay_chips in delay_values:
            for ratio_db in ratio_values:
                selected = [row for row in rows if row["method"] == method
                            and row["delay_chips"] == delay_chips and row["ratio_db"] == ratio_db]
                summary["conditions"].append(dict(
                    method=method, delay_chips=delay_chips,
                    delay_m=delay_chips * CHIP_M, ratio_db=ratio_db,
                    success_rate=float(np.mean([row["success"] for row in selected])),
                    angle_rmse_median_deg=float(np.median([row["angle_rmse_deg"] for row in selected])),
                    delay_rmse_median_m=float(np.median([row["delay_rmse_m"] for row in selected]))))
    (output_dir / "SAGE方阵与ULA_FBSS停车场公平比较.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    labels = ["2x2 SAGE/STAP", "ULA+FBSS\nblind", "ULA+FBSS\nhalf-plane"]
    values = [summary[name]["success_rate"] for name in positions_by_method]
    fig, ax = plt.subplots(figsize=(7, 4)); ax.bar(labels, values, color=["#276FBF", "#D1495B"])
    ax.set_ylim(0, 1); ax.set_ylabel("Success rate"); ax.set_title("Same scene, kernel, blocks and noise policy")
    for index, value in enumerate(values): ax.text(index, value + 0.02, f"{value:.1%}", ha="center")
    fig.tight_layout(); fig.savefig(output_dir / "SAGE方阵与ULA_FBSS停车场成功率.png", dpi=180); plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    for axis, method in zip(axes, positions_by_method):
        matrix = np.array([[next(item["success_rate"] for item in summary["conditions"]
                                 if item["method"] == method and item["delay_chips"] == delay
                                 and item["ratio_db"] == ratio)
                            for ratio in ratio_values] for delay in delay_values])
        image = axis.imshow(matrix, vmin=0, vmax=1, cmap="viridis", aspect="auto")
        axis.set_title(method); axis.set_xlabel("Path 1 relative power (dB)")
        axis.set_xticks(range(len(ratio_values)), [str(v) for v in ratio_values])
        axis.set_yticks(range(len(delay_values)), [f"{v:.1f}" for v in delay_values])
        for row in range(len(delay_values)):
            for column in range(len(ratio_values)):
                axis.text(column, row, f"{matrix[row, column]:.0%}", ha="center", va="center",
                          color="white" if matrix[row, column] < 0.55 else "black")
    axes[0].set_ylabel("Relative delay (chip)")
    fig.colorbar(image, ax=axes, label="Success rate", shrink=0.85)
    fig.savefig(output_dir / "SAGE方阵与ULA_FBSS延迟功率阶梯.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["paper", "parking", "all"], default="all")
    parser.add_argument("--kernel-csv")
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--delay-values", default="0.1,0.3,0.5,1.0")
    parser.add_argument("--ratio-values", default="0,-6,-10")
    parser.add_argument("--output-dir", default="dev_notes/sim/results/sage_stap_reproduction")
    args = parser.parse_args()
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    if args.mode in ("paper", "all"):
        result = paper_reproduction(args.kernel_csv)
        serializable = dict(result)
        serializable["monte_carlo"] = paper_monte_carlo(args.kernel_csv, args.trials)
        (output / "SAGE_STAP论文参数复现.json").write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
        print("paper SAGE/STAP:", result["estimates"])
        print("residual history:", [round(v, 4) for v in result["residual_history"]])
        print("paper Monte Carlo:", serializable["monte_carlo"])
    if args.mode in ("parking", "all"):
        delays = tuple(float(value) for value in args.delay_values.split(","))
        ratios = tuple(float(value) for value in args.ratio_values.split(","))
        print("parking benchmark:", parking_benchmark(
            output, args.kernel_csv, args.trials, delay_values=delays, ratio_values=ratios))


if __name__ == "__main__":
    main()

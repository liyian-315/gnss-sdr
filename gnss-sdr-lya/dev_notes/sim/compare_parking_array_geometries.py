#!/usr/bin/env python3
"""Fair ULA/UCA/UPA comparison for the 20 m parking-DAS geometry."""

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import simulate_coherent_music_parking as core


def upa_positions(rows, columns, spacing_wl=0.5):
    """Return row-major coordinates for a rectangular planar array."""
    x = (np.arange(columns) - (columns - 1) / 2.0) * spacing_wl
    y = (np.arange(rows) - (rows - 1) / 2.0) * spacing_wl
    return np.array([[column, row] for row in y for column in x], dtype=float)


def rotate_positions(positions, angle_deg):
    angle = np.radians(angle_deg)
    rotation = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    )
    return np.asarray(positions) @ rotation.T


def rectangular_spatial_smoothing(covariance_matrix, shape, subarray_shape):
    """Average all translated rectangular subarray covariance matrices."""
    rows, columns = shape
    sub_rows, sub_columns = subarray_shape
    if covariance_matrix.shape != (rows * columns, rows * columns):
        raise ValueError("covariance dimension does not match rectangular shape")
    if not (1 <= sub_rows <= rows and 1 <= sub_columns <= columns):
        raise ValueError("invalid rectangular subarray shape")
    dimension = sub_rows * sub_columns
    smoothed = np.zeros((dimension, dimension), dtype=complex)
    count = 0
    for row_start in range(rows - sub_rows + 1):
        for column_start in range(columns - sub_columns + 1):
            indices = []
            for row in range(row_start, row_start + sub_rows):
                indices.extend(
                    row * columns + np.arange(column_start, column_start + sub_columns)
                )
            smoothed += covariance_matrix[np.ix_(indices, indices)]
            count += 1
    smoothed /= count
    reversal = np.fliplr(np.eye(dimension))
    smoothed = 0.5 * (smoothed + reversal @ smoothed.conj() @ reversal)
    return smoothed, count


def geometry_definition(kind, n_elements, orientation_deg=0.0):
    if n_elements != 4:
        raise ValueError("this comparison is intentionally restricted to four elements")
    if kind == "ULA":
        positions = core.ula_positions(n_elements, 0.5, axis_deg=orientation_deg)
        return positions, (1, n_elements), (1, n_elements - 1)
    if kind == "UCA":
        positions = rotate_positions(core.uca_positions(n_elements, 0.5), orientation_deg)
        return positions, None, None
    if kind == "UPA":
        shape = (2, 2)
        positions = rotate_positions(upa_positions(*shape), orientation_deg)
        # A 2x2 array has no translated rectangular subarray with dimension > K.
        subarray_shape = None if shape == (2, 2) else (2, shape[1] - 1)
        return positions, shape, subarray_shape
    raise ValueError("unknown geometry")


def simulate_method_set(
    kind,
    n_elements,
    receiver_xy,
    transmitters_xy,
    rng,
    relative_phase_rad,
    orientation_deg=0.0,
    snr_db=15.0,
    source_ratio_db=-6.0,
):
    positions, shape, subarray_shape = geometry_definition(
        kind, n_elements, orientation_deg
    )
    bearings = np.mod(
        [core.bearing_from_receiver(receiver_xy, tx) for tx in transmitters_xy],
        360.0,
    )
    source_manifold = np.column_stack(
        [core.steering_from_positions(positions, angle) for angle in bearings]
    )
    amplitudes = [
        1.0,
        10.0 ** (source_ratio_db / 20.0) * np.exp(1j * relative_phase_rad),
    ]
    samples = core.coherent_snapshots_from_manifold(
        source_manifold, amplitudes, 2048, snr_db, rng, correlation=1.0
    )
    raw = core.covariance(samples)
    grid = np.arange(0.0, 360.0, 1.0)
    raw_scan = np.column_stack(
        [core.steering_from_positions(positions, angle) for angle in grid]
    )
    bartlett = core.bartlett_spectrum(raw, raw_scan)
    direct_music, raw_eigenvalues = core.music_spectrum(
        raw, 2, grid, manifold=raw_scan
    )
    result = {
        "bearings_deg": bearings.tolist(),
        "spatial_coherence": core.normalized_coherence(
            source_manifold[:, 0], source_manifold[:, 1]
        ),
        "raw_rank": core.estimated_signal_rank(raw_eigenvalues, 2),
        "bartlett_peaks_deg": core.strongest_circular_peaks(grid, bartlett, 2).tolist(),
        "direct_music_peaks_deg": core.strongest_circular_peaks(
            grid, direct_music, 2
        ).tolist(),
        "smoothing_supported": False,
    }

    if kind == "UCA":
        transform, modes = core.phase_mode_transform(n_elements)
        subarray_size = len(modes) - 1
        if subarray_size <= 2:
            return result
        transformed = transform @ raw @ transform.conj().T
        smooth = core.forward_backward_spatial_smoothing(
            transformed, subarray_size
        )
        smooth_scan = core.virtual_ula_manifold(grid, subarray_size)
        translated_subarrays = len(modes) - subarray_size + 1
    else:
        if subarray_shape is None:
            return result
        smooth, translated_subarrays = rectangular_spatial_smoothing(
            raw, shape, subarray_shape
        )
        sub_positions = rotate_positions(
            upa_positions(*subarray_shape), orientation_deg
        )
        smooth_scan = np.column_stack(
            [core.steering_from_positions(sub_positions, angle) for angle in grid]
        )

    fbss_music, smooth_eigenvalues = core.music_spectrum(
        smooth, 2, grid, manifold=smooth_scan
    )
    fbss_mvdr = core.mvdr_spectrum(smooth, smooth_scan)
    result.update(
        {
            "smoothing_supported": True,
            "translated_subarrays": translated_subarrays,
            "smoothed_dimension": smooth.shape[0],
            "smoothed_rank": core.estimated_signal_rank(smooth_eigenvalues, 2),
            "smooth_music_peaks_deg": core.strongest_circular_peaks(
                grid, fbss_music, 2
            ).tolist(),
            "smooth_mvdr_peaks_deg": core.strongest_circular_peaks(
                grid, fbss_mvdr, 2
            ).tolist(),
        }
    )
    return result


def run_comparison(output_dir, seed, trials=40):
    transmitters = np.array([[-10.0, 0.0], [10.0, 0.0]])
    positions = {
        "between_center": np.array([0.0, 0.0]),
        "between_offset": np.array([0.0, 5.0]),
        "outside_left": np.array([-20.0, 0.0]),
        "beside_tx0": np.array([-10.0, 5.0]),
        "far_side": np.array([0.0, 20.0]),
    }
    orientations = np.arange(0.0, 180.0, 15.0)
    rows = []
    for kind_index, kind in enumerate(("ULA", "UCA", "UPA")):
        for orientation_index, orientation_deg in enumerate(orientations):
            for position_index, (name, receiver) in enumerate(positions.items()):
                success = dict(bartlett=0, direct_music=0, smooth_mvdr=0, smooth_music=0)
                example = None
                for trial in range(trials):
                    rng = np.random.default_rng(
                        seed + kind_index * 1000000 + orientation_index * 10000
                        + position_index * 1000 + trial
                    )
                    result = simulate_method_set(
                        kind, 4, receiver, transmitters, rng,
                        relative_phase_rad=rng.uniform(-np.pi, np.pi),
                        orientation_deg=orientation_deg,
                    )
                    truth = result["bearings_deg"]
                    success["bartlett"] += core.match_circular_doa(
                        truth, result["bartlett_peaks_deg"]
                    )
                    success["direct_music"] += core.match_circular_doa(
                        truth, result["direct_music_peaks_deg"]
                    )
                    if result["smoothing_supported"]:
                        success["smooth_mvdr"] += core.match_circular_doa(
                            truth, result["smooth_mvdr_peaks_deg"]
                        )
                        success["smooth_music"] += core.match_circular_doa(
                            truth, result["smooth_music_peaks_deg"]
                        )
                    example = result
                rows.append(
                    {
                        "elements": 4,
                        "geometry": kind,
                        "orientation_deg": orientation_deg,
                        "position": name,
                        "bearing_separation_deg": core.circular_angle_difference(
                            *example["bearings_deg"]
                        ),
                        "spatial_coherence": example["spatial_coherence"],
                        "raw_rank": example["raw_rank"],
                        "smoothing_supported": example["smoothing_supported"],
                        "translated_subarrays": example.get("translated_subarrays"),
                        "smoothed_dimension": example.get("smoothed_dimension"),
                        "bartlett_success": success["bartlett"] / trials,
                        "direct_music_success": success["direct_music"] / trials,
                        "smooth_mvdr_success": (
                            success["smooth_mvdr"] / trials
                            if example["smoothing_supported"] else None
                        ),
                        "smooth_music_success": (
                            success["smooth_music"] / trials
                            if example["smoothing_supported"] else None
                        ),
                    }
                )

    csv_path = output_dir / "停车场四阵元线阵圆阵方阵公平对比.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    methods = ["bartlett_success", "direct_music_success", "smooth_mvdr_success", "smooth_music_success"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
    for column_index, kind in enumerate(("ULA", "UCA", "UPA")):
            subset = [r for r in rows if r["geometry"] == kind]
            values = []
            for name in positions:
                position_rows = [r for r in subset if r["position"] == name]
                values.append([
                    np.nan if all(r[method] is None for r in position_rows)
                    else np.mean([r[method] for r in position_rows if r[method] is not None])
                    for method in methods
                ])
            values = np.array([
                row for row in values
            ])
            axis = axes[column_index]
            image = axis.imshow(values, vmin=0, vmax=1, cmap="viridis", aspect="auto")
            for i in range(values.shape[0]):
                for j in range(values.shape[1]):
                    label = "N/A" if np.isnan(values[i, j]) else "%.0f%%" % (100 * values[i, j])
                    axis.text(j, i, label, ha="center", va="center", fontsize=8,
                              color="white" if np.isnan(values[i, j]) or values[i, j] < 0.55 else "black")
            axis.set_title("%s, M=4 (orientation averaged)" % kind)
            axis.set_xticks(range(4), ["Bartlett", "direct\nMUSIC", "smooth\nMVDR", "smooth\nMUSIC"])
            axis.set_yticks(range(len(positions)), list(positions.keys()))
            fig.colorbar(image, ax=axis, shrink=0.75)
    figure_path = output_dir / "停车场四阵元三种阵列算法成功率.png"
    fig.savefig(figure_path, dpi=180)
    plt.close(fig)

    x_values = np.linspace(-30.0, 30.0, 61)
    y_values = np.linspace(-20.0, 20.0, 41)
    geometry_summary = []
    for kind in ("ULA", "UCA", "UPA"):
        all_mu = []
        orientation_p95 = []
        for orientation_deg in orientations:
            element_positions, _, _ = geometry_definition(kind, 4, orientation_deg)
            coherence, _ = core.parking_grid(
                transmitters, x_values, y_values, element_positions
            )
            finite = coherence[np.isfinite(coherence)]
            all_mu.extend(finite.tolist())
            orientation_p95.append(float(np.percentile(finite, 95)))
        all_mu = np.asarray(all_mu)
        method_rows = [r for r in rows if r["geometry"] == kind]
        geometry_summary.append(
            {
                "geometry": kind,
                "median_spatial_coherence": float(np.median(all_mu)),
                "p95_spatial_coherence": float(np.percentile(all_mu, 95)),
                "fraction_mu_below_0_8": float(np.mean(all_mu < 0.8)),
                "fraction_mu_above_0_95": float(np.mean(all_mu > 0.95)),
                "worst_orientation_p95": float(np.max(orientation_p95)),
                "direct_music_success_all": float(np.mean([r["direct_music_success"] for r in method_rows])),
                "smooth_music_success_all": (
                    float(np.mean([r["smooth_music_success"] for r in method_rows]))
                    if all(r["smooth_music_success"] is not None for r in method_rows)
                    else None
                ),
            }
        )

    summary_path = output_dir / "停车场四阵元三种阵列对比摘要.json"
    summary_path.write_text(
        json.dumps(
            {
                "trials_per_condition": trials,
                "orientations_deg": orientations.tolist(),
                "geometry_summary": geometry_summary,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return rows, geometry_summary, csv_path, figure_path, summary_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="dev_notes/sim/results/coherent_music_parking")
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--trials", type=int, default=40)
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows, geometry_summary, csv_path, figure_path, summary_path = run_comparison(
        output_dir, args.seed, args.trials
    )
    for row in rows:
        print(
            "M=%d %s rot=%3.0f %-15s rawMUSIC=%.2f smoothMVDR=%s smoothMUSIC=%s"
            % (
                row["elements"], row["geometry"], row["orientation_deg"], row["position"],
                row["direct_music_success"], row["smooth_mvdr_success"],
                row["smooth_music_success"],
            )
        )
    print("geometry summary:")
    for item in geometry_summary:
        print(" ", item)
    print("wrote", csv_path)
    print("wrote", figure_path)
    print("wrote", summary_path)


if __name__ == "__main__":
    main()

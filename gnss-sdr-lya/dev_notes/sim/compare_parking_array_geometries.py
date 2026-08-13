#!/usr/bin/env python3
"""四阵元 ULA/UCA/UPA 停车场仿真：单点看谱形，批量看统计结果。"""

import argparse
import csv
import json
import os
from pathlib import Path

import matplotlib

# Windows/PyCharm 下保留交互图窗；无桌面的 Linux 自动切到文件输出后端。
if os.name != "nt" and not os.environ.get("DISPLAY"):
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import simulate_coherent_music_parking as core


# ======================== 用户常改参数 ========================
# 这些值也是命令行参数的默认值。坐标单位为 m，角度为全局方位角 deg。
# 两个发射天线默认沿 X 轴对称放置，间距 20 m；接收机默认站在中点上方 5 m。
DEFAULT_RECEIVER_X_M = 0.0
DEFAULT_RECEIVER_Y_M = 5.0
DEFAULT_TX_CENTER_X_M = 0.0
DEFAULT_TX_CENTER_Y_M = 0.0
DEFAULT_TX_SEPARATION_M = 20.0
# 1.0=完全相干（停车场同源同钟重点场景），0.0=互不相关。
DEFAULT_SOURCE_CORRELATION = 1.0
# 第二路比第一路弱 6 dB；改成 0 表示两路等功率。
DEFAULT_SOURCE_RATIO_DB = -6.0
DEFAULT_RELATIVE_PHASE_DEG = 60.0
DEFAULT_SNR_DB = 15.0
DEFAULT_SNAPSHOTS = 4096
# 阵元间距，以波长为单位；0.5 即半波长。L5 上约为 12.7 cm。
DEFAULT_SPACING_WL = 0.5
DEFAULT_ARRAY_ORIENTATION_DEG = 0.0


ARRAY_NAMES = {
    "ULA": "四阵元线阵 ULA",
    "UCA": "四阵元圆阵 UCA",
    "UPA": "2x2 方阵 UPA",
}


def configure_chinese_font():
    """优先选系统中文字体；没有时仍可运行，只可能收到缺字警告。"""
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def spectrum_db(spectrum, floor_db=-45.0):
    values = np.asarray(spectrum, dtype=float)
    values = values / max(float(np.max(values)), 1e-15)
    return np.maximum(10.0 * np.log10(np.maximum(values, 1e-15)), floor_db)


def classify_spectrum(truth_deg, estimate_deg, tolerance_deg=5.0):
    """给图上的两个峰一个直观但保守的分类。"""
    if core.match_circular_doa(truth_deg, estimate_deg, tolerance_deg):
        return "双峰正确分离"
    matched_truth = sum(
        any(core.circular_angle_difference(t, e) <= tolerance_deg for e in estimate_deg)
        for t in truth_deg
    )
    if matched_truth == 1:
        return "仅一路成峰（融合或漏检）"
    if matched_truth == 2:
        return "真值附近有峰，但更强伪峰干扰"
    return "未分离（峰位置错误）"


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


def geometry_definition(kind, n_elements, orientation_deg=0.0, spacing_wl=0.5):
    if n_elements != 4:
        raise ValueError("this comparison is intentionally restricted to four elements")
    if kind == "ULA":
        positions = core.ula_positions(n_elements, spacing_wl, axis_deg=orientation_deg)
        return positions, (1, n_elements), (1, n_elements - 1)
    if kind == "UCA":
        positions = rotate_positions(
            core.uca_positions(n_elements, spacing_wl), orientation_deg
        )
        return positions, None, None
    if kind == "UPA":
        shape = (2, 2)
        positions = rotate_positions(
            upa_positions(*shape, spacing_wl=spacing_wl), orientation_deg
        )
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
    correlation=1.0,
    snapshots=2048,
    spacing_wl=0.5,
    angle_step_deg=1.0,
):
    positions, shape, subarray_shape = geometry_definition(
        kind, n_elements, orientation_deg, spacing_wl
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
        source_manifold, amplitudes, snapshots, snr_db, rng, correlation=correlation
    )
    raw = core.covariance(samples)
    grid = np.arange(0.0, 360.0, angle_step_deg)
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
        "angle_grid_deg": grid,
        "bartlett_spectrum": bartlett,
        "direct_music_spectrum": direct_music,
        "element_positions_wl": positions,
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
            upa_positions(*subarray_shape, spacing_wl=spacing_wl), orientation_deg
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
            "smooth_music_spectrum": fbss_music,
            "smooth_mvdr_spectrum": fbss_mvdr,
        }
    )
    return result


def transmitter_positions(center_xy, separation_m):
    """两个 DAS 发射天线沿全局 X 轴放置，中心和间距均可修改。"""
    center = np.asarray(center_xy, dtype=float)
    half = np.array([separation_m / 2.0, 0.0])
    return np.vstack((center - half, center + half))


def plot_geometry(receiver_xy, transmitters_xy, results, output_path):
    """左侧画停车场坐标，右侧分别画三种四阵元局部几何。"""
    configure_chinese_font()
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.5), constrained_layout=True)
    world = axes[0]
    world.scatter(transmitters_xy[:, 0], transmitters_xy[:, 1], s=100,
                  marker="^", c=["tab:red", "tab:blue"])
    world.scatter(receiver_xy[0], receiver_xy[1], s=90, marker="x", c="black")
    for index, tx in enumerate(transmitters_xy):
        world.plot([receiver_xy[0], tx[0]], [receiver_xy[1], tx[1]], "--", alpha=0.55)
        world.text(tx[0], tx[1], "  发射源 %s" % ("A" if index == 0 else "B"))
    world.text(receiver_xy[0], receiver_xy[1], "  接收机")
    world.set_title("停车场坐标与两路来向")
    world.set_xlabel("X / m")
    world.set_ylabel("Y / m")
    world.grid(True, alpha=0.25)
    world.set_aspect("equal", adjustable="datalim")

    for axis, kind in zip(axes[1:], ("ULA", "UCA", "UPA")):
        positions = np.asarray(results[kind]["element_positions_wl"])
        axis.scatter(positions[:, 0], positions[:, 1], s=90, c="tab:green")
        for index, position in enumerate(positions):
            axis.text(position[0], position[1], "  %d" % (index + 1), va="center")
        axis.axhline(0, color="0.8", linewidth=0.8)
        axis.axvline(0, color="0.8", linewidth=0.8)
        axis.set_title(ARRAY_NAMES[kind])
        axis.set_xlabel("X / 波长")
        axis.set_ylabel("Y / 波长")
        axis.grid(True, alpha=0.25)
        axis.set_aspect("equal", adjustable="box")
        limit = max(0.9, float(np.max(np.abs(positions))) * 1.45)
        axis.set_xlim(-limit, limit)
        axis.set_ylim(-limit, limit)
    fig.savefig(output_path, dpi=180)
    return fig


def plot_spectrum_comparison(results, output_path):
    """逐行对比线阵、圆阵、方阵，直观看两条路径是否形成两个峰。"""
    configure_chinese_font()
    columns = (
        ("Bartlett 常规波束扫描", "bartlett_spectrum", "bartlett_peaks_deg"),
        ("直接 MUSIC", "direct_music_spectrum", "direct_music_peaks_deg"),
        ("空间平滑后 MUSIC", "smooth_music_spectrum", "smooth_music_peaks_deg"),
    )
    fig, axes = plt.subplots(3, 3, figsize=(17, 11), sharex=True, sharey=True,
                             constrained_layout=True)
    for row, kind in enumerate(("ULA", "UCA", "UPA")):
        result = results[kind]
        truth = result["bearings_deg"]
        for column, (method_name, spectrum_key, peaks_key) in enumerate(columns):
            axis = axes[row, column]
            if spectrum_key not in result:
                axis.text(
                    0.5, 0.5,
                    "四阵元该几何不能直接套用\n有效的平移子阵空间平滑",
                    ha="center", va="center", transform=axis.transAxes, fontsize=11,
                )
                axis.set_title("%s\n不适用" % method_name)
                axis.grid(True, alpha=0.2)
                continue
            grid = result["angle_grid_deg"]
            spectrum = spectrum_db(result[spectrum_key])
            estimates = result[peaks_key]
            status = classify_spectrum(truth, estimates)
            if method_name == "直接 MUSIC" and result["raw_rank"] < 2:
                if status == "双峰正确分离":
                    status = "峰位命中，但秩塌缩，不可作可靠结论"
                else:
                    status += "；且秩塌缩"
            axis.plot(grid, spectrum, color="black", linewidth=1.1)
            for truth_index, angle in enumerate(truth):
                axis.axvline(
                    angle,
                    color=("tab:red" if truth_index == 0 else "tab:blue"),
                    linestyle="--", linewidth=1.5,
                    label=("真实源 A" if truth_index == 0 else "真实源 B"),
                )
            for angle in estimates:
                sample = int(np.argmin(abs(grid - angle)))
                axis.plot(angle, spectrum[sample], "x", color="magenta", markersize=8)
            axis.set_title("%s\n%s；估计峰 %s°" % (
                method_name, status, ", ".join("%.1f" % p for p in estimates)
            ), fontsize=10)
            axis.grid(True, alpha=0.22)
        axes[row, 0].set_ylabel("%s\n归一化空间谱 / dB" % ARRAY_NAMES[kind])
    for axis in axes[-1, :]:
        axis.set_xlabel("全局方位角 / deg")
    axes[0, 0].legend(loc="lower right", fontsize=8)
    fig.suptitle(
        "两路同码信号的空间谱：两个尖峰=可分；单个宽峰或错峰=未可靠分离",
        fontsize=14,
    )
    fig.savefig(output_path, dpi=180)
    return fig


def run_single_point(
    output_dir,
    seed,
    receiver_xy,
    tx_center_xy,
    tx_separation_m,
    correlation,
    source_ratio_db,
    relative_phase_deg,
    snr_db,
    snapshots,
    spacing_wl,
    orientation_deg,
    show=False,
):
    """类似 MATLAB 单脚本工作流：改一组参数，同时得到三种阵列的图。"""
    receiver_xy = np.asarray(receiver_xy, dtype=float)
    transmitters_xy = transmitter_positions(tx_center_xy, tx_separation_m)
    results = {}
    for index, kind in enumerate(("ULA", "UCA", "UPA")):
        results[kind] = simulate_method_set(
            kind,
            4,
            receiver_xy,
            transmitters_xy,
            np.random.default_rng(seed + index),
            relative_phase_rad=np.radians(relative_phase_deg),
            orientation_deg=orientation_deg,
            snr_db=snr_db,
            source_ratio_db=source_ratio_db,
            correlation=correlation,
            snapshots=snapshots,
            spacing_wl=spacing_wl,
            angle_step_deg=0.25,
        )

    geometry_path = output_dir / "停车场四阵元单点几何示意图.png"
    spectrum_path = output_dir / "停车场四阵元单点空间谱对比.png"
    geometry_figure = plot_geometry(receiver_xy, transmitters_xy, results, geometry_path)
    spectrum_figure = plot_spectrum_comparison(results, spectrum_path)

    configuration = {
        "receiver_xy_m": receiver_xy.tolist(),
        "transmitters_xy_m": transmitters_xy.tolist(),
        "tx_separation_m": tx_separation_m,
        "source_correlation": correlation,
        "source_ratio_db": source_ratio_db,
        "relative_phase_deg": relative_phase_deg,
        "snr_db": snr_db,
        "snapshots": snapshots,
        "spacing_wavelengths": spacing_wl,
        "array_orientation_deg": orientation_deg,
    }
    summary = {"configuration": configuration, "arrays": {}}
    for kind, result in results.items():
        methods = {
            "bartlett": (result["bartlett_peaks_deg"], "bartlett_spectrum"),
            "direct_music": (result["direct_music_peaks_deg"], "direct_music_spectrum"),
        }
        if result["smoothing_supported"]:
            methods["smooth_music"] = (
                result["smooth_music_peaks_deg"], "smooth_music_spectrum"
            )
        summary["arrays"][kind] = {
            "name": ARRAY_NAMES[kind],
            "truth_bearings_deg": result["bearings_deg"],
            "spatial_coherence": result["spatial_coherence"],
            "raw_covariance_rank": result["raw_rank"],
            "methods": {
                name: {
                    "estimated_peaks_deg": peaks,
                    "status": (
                        "峰位命中，但秩塌缩，不可作可靠结论"
                        if name == "direct_music"
                        and result["raw_rank"] < 2
                        and classify_spectrum(result["bearings_deg"], peaks)
                        == "双峰正确分离"
                        else classify_spectrum(result["bearings_deg"], peaks)
                    ),
                }
                for name, (peaks, _) in methods.items()
            },
        }
    summary_path = output_dir / "停车场四阵元单点仿真结果.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("参数:", configuration)
    for kind, item in summary["arrays"].items():
        print("%s: 真值=%s°, 空间相干度=%.3f, 原始协方差秩=%d" % (
            item["name"], item["truth_bearings_deg"], item["spatial_coherence"],
            item["raw_covariance_rank"]
        ))
        for method, outcome in item["methods"].items():
            print("  %-14s 峰=%s° -> %s" % (
                method, outcome["estimated_peaks_deg"], outcome["status"]
            ))
    print("图片:", geometry_path.resolve())
    print("图片:", spectrum_path.resolve())
    print("结果:", summary_path.resolve())
    if show:
        plt.show()
    else:
        plt.close(geometry_figure)
        plt.close(spectrum_figure)
    return results, geometry_path, spectrum_path, summary_path


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
    parser = argparse.ArgumentParser(
        description="四阵元线阵/圆阵/方阵停车场仿真；默认生成单点空间谱图片"
    )
    parser.add_argument("--mode", choices=("single", "batch"), default="single")
    parser.add_argument("--output-dir", default="dev_notes/sim/results/coherent_music_parking")
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--trials", type=int, default=40)
    parser.add_argument("--receiver-x", type=float, default=DEFAULT_RECEIVER_X_M)
    parser.add_argument("--receiver-y", type=float, default=DEFAULT_RECEIVER_Y_M)
    parser.add_argument("--tx-center-x", type=float, default=DEFAULT_TX_CENTER_X_M)
    parser.add_argument("--tx-center-y", type=float, default=DEFAULT_TX_CENTER_Y_M)
    parser.add_argument("--tx-separation-m", type=float, default=DEFAULT_TX_SEPARATION_M)
    parser.add_argument("--correlation", type=float, default=DEFAULT_SOURCE_CORRELATION)
    parser.add_argument("--ratio-db", type=float, default=DEFAULT_SOURCE_RATIO_DB)
    parser.add_argument("--relative-phase-deg", type=float, default=DEFAULT_RELATIVE_PHASE_DEG)
    parser.add_argument("--snr-db", type=float, default=DEFAULT_SNR_DB)
    parser.add_argument("--snapshots", type=int, default=DEFAULT_SNAPSHOTS)
    parser.add_argument("--spacing-wl", type=float, default=DEFAULT_SPACING_WL)
    parser.add_argument("--orientation-deg", type=float, default=DEFAULT_ARRAY_ORIENTATION_DEG)
    parser.add_argument("--show", action="store_true", help="保存图片后弹出图窗")
    args = parser.parse_args()
    if not 0.0 <= args.correlation <= 1.0:
        parser.error("--correlation 必须在 0 到 1 之间")
    if args.tx_separation_m <= 0 or args.spacing_wl <= 0 or args.snapshots <= 0:
        parser.error("发射间距、阵元间距和快拍数必须为正数")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.mode == "single":
        run_single_point(
            output_dir=output_dir,
            seed=args.seed,
            receiver_xy=(args.receiver_x, args.receiver_y),
            tx_center_xy=(args.tx_center_x, args.tx_center_y),
            tx_separation_m=args.tx_separation_m,
            correlation=args.correlation,
            source_ratio_db=args.ratio_db,
            relative_phase_deg=args.relative_phase_deg,
            snr_db=args.snr_db,
            snapshots=args.snapshots,
            spacing_wl=args.spacing_wl,
            orientation_deg=args.orientation_deg,
            show=args.show,
        )
        return
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

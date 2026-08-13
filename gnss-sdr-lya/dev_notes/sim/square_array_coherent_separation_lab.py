#!/usr/bin/env python3
"""四阵元 2x2 方阵：相干双源的 MUSIC、空间平滑、空间-时延 GLRT/ML 对照。"""

from pathlib import Path
import json
import os

import matplotlib

if os.name != "nt" and not os.environ.get("DISPLAY"):
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import compare_parking_array_geometries as arrays
import fit_two_path as ftp
import simulate_coherent_music_parking as core


# ======================== 实验参数区（像 MATLAB 脚本一样修改） ========================

# 两路信号相对方位角，单位 deg。角度差越大，空间维度通常越容易分离。
SOURCE_A_ANGLE_DEG = -30.0
SOURCE_B_ANGLE_DEG = 30.0

# B 路相对 A 路的码延迟。L5 一个码片约 29.3 m，0.5 chip 约 14.7 m。
SOURCE_B_DELAY_CHIPS = 0.5
CHIP_LENGTH_M = 29.3

# B 路相对 A 路功率；0=等功率，-6=B 路弱 6 dB。
SOURCE_B_RATIO_DB = -6.0
# B 路相对 A 路初始载波相位；完全相干时会改变复数叠加形状。
SOURCE_B_PHASE_DEG = 60.0
# 两路相关系数：1.0=完全相干，0.0=不相关。本实验默认测试最困难的完全相干。
SOURCE_CORRELATION = 1.0
# 是否真的发射第二路；改成 False 可运行单源虚警负对照。
EMIT_SECOND_SOURCE = True

# 每个历元的复噪声标准差；越大表示信号越差。
NOISE_SIGMA = 0.05
# 历元数；越多则协方差和联合似然越稳定。
N_BLOCKS = 64
# 固定种子便于复现实验；修改可检查结果是否依赖某次随机噪声。
RANDOM_SEED = 20260813

# 正方形相邻阵元间距，以波长为单位。0.5=半波长，L5 上约 12.7 cm。
ELEMENT_SPACING_WAVELENGTHS = 0.5
# 方阵整体相对全局 X 轴逆时针旋转角，单位 deg。
ARRAY_ORIENTATION_DEG = 0.0

# dense 相关器的码延迟 tap 范围与间隔，单位 chip。
DELAY_TAP_START = -1.5
DELAY_TAP_STOP = 1.5
DELAY_TAP_STEP = 0.1

# GLRT/ML 搜索网格。角度步长越小越精细，但运行更慢。
SEARCH_ANGLE_MIN_DEG = -90.0
SEARCH_ANGLE_MAX_DEG = 90.0
SEARCH_ANGLE_STEP_DEG = 5.0
SEARCH_DELAY_MIN_CHIPS = 0.1
SEARCH_DELAY_MAX_CHIPS = 1.2
SEARCH_DELAY_STEP_CHIPS = 0.05

# 是否弹出图窗；无桌面服务器会自动只保存图片。
SHOW_FIGURES = True
# 图片与 JSON 的输出目录。
OUTPUT_DIR = Path("dev_notes/sim/results/coherent_music_parking")


def configure_font():
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"
    ]
    plt.rcParams["axes.unicode_minus"] = False


def square_positions(spacing_wl, orientation_deg):
    """按行编号的 2x2 方阵坐标，单位波长。"""
    positions = arrays.upa_positions(2, 2, spacing_wl)
    return arrays.rotate_positions(positions, orientation_deg)


def steering(positions, angle_deg):
    return core.steering_from_positions(positions, angle_deg)


def kernel_at(delay_chips, taps, kernel):
    return ftp.kern_at(taps, kernel, taps - delay_chips)


def joint_template(positions, angle_deg, delay_chips, taps, kernel):
    """q(theta,tau)=a(theta) kron R(tau)，同时包含空间和码时延信息。"""
    return np.kron(
        steering(positions, angle_deg), kernel_at(delay_chips, taps, kernel)
    )


def synthesize_scene(config):
    """产生 (历元, 阵元, tap) 的复数 dense 相关观测。"""
    rng = np.random.default_rng(config["seed"])
    taps = np.round(
        np.arange(
            config["tap_start"],
            config["tap_stop"] + 0.5 * config["tap_step"],
            config["tap_step"],
        ),
        6,
    )
    kernel = ftp.synth_kernel(taps)
    positions = square_positions(config["spacing_wl"], config["orientation_deg"])
    a0 = steering(positions, config["angle_a_deg"])
    a1 = steering(positions, config["angle_b_deg"])
    r0 = kernel_at(0.0, taps, kernel)
    r1 = kernel_at(config["delay_b_chips"], taps, kernel)

    common = (
        rng.standard_normal(config["n_blocks"])
        + 1j * rng.standard_normal(config["n_blocks"])
    ) / np.sqrt(2.0)
    independent = (
        rng.standard_normal((2, config["n_blocks"]))
        + 1j * rng.standard_normal((2, config["n_blocks"]))
    ) / np.sqrt(2.0)
    rho = config["correlation"]
    sources = np.sqrt(rho) * common[None, :] + np.sqrt(1.0 - rho) * independent
    sources[1] *= 10.0 ** (config["ratio_db"] / 20.0) * np.exp(
        1j * np.radians(config["phase_deg"])
    )

    dense = np.empty((config["n_blocks"], 4, len(taps)), dtype=complex)
    for block in range(config["n_blocks"]):
        dense[block] = sources[0, block] * np.outer(a0, r0)
        if config["emit_second_source"]:
            dense[block] += sources[1, block] * np.outer(a1, r1)
    dense += config["noise_sigma"] * (
        rng.standard_normal(dense.shape) + 1j * rng.standard_normal(dense.shape)
    ) / np.sqrt(2.0)
    return dense, taps, kernel, positions


def covariance_rank(eigenvalues, source_count=2):
    return core.estimated_signal_rank(eigenvalues, source_count)


def raw_music(dense, taps, positions):
    """在 Prompt 附近只用四通道空间协方差直接做普通 MUSIC。"""
    prompt = int(np.argmin(abs(taps)))
    spatial_samples = dense[:, :, prompt].T
    covariance = spatial_samples @ spatial_samples.conj().T / spatial_samples.shape[1]
    angle_grid = np.arange(-90.0, 90.01, 0.25)
    manifold = np.column_stack([steering(positions, angle) for angle in angle_grid])
    spectrum, eigenvalues = core.music_spectrum(
        covariance, 2, angle_grid, manifold=manifold
    )
    peaks = core.strongest_peaks(angle_grid, spectrum, 2)
    return covariance, angle_grid, spectrum, eigenvalues, peaks


def square_smoothing_diagnostic(covariance):
    """说明 2x2 方阵为什么没有可用于两源 MUSIC 的标准平移子阵。"""
    # 两个横向 1x2 子阵是唯一有重复平移关系的选择之一。
    row0 = covariance[np.ix_([0, 1], [0, 1])]
    row1 = covariance[np.ix_([2, 3], [2, 3])]
    smoothed = 0.5 * (row0 + row1)
    reversal = np.fliplr(np.eye(2))
    smoothed = 0.5 * (smoothed + reversal @ smoothed.conj() @ reversal)
    return {
        "subarray_dimension": 2,
        "source_count": 2,
        "noise_subspace_dimension": 0,
        "translated_subarrays": 2,
        "eigenvalues": np.linalg.eigvalsh(smoothed)[::-1].real.tolist(),
        "usable_for_two_source_music": False,
        "reason": "1x2 子阵维数等于源数，噪声子空间维数为 0；2x2 整阵又只有一个子阵，无法平滑。",
    }


def residual_energy_from_templates(Y, templates):
    X = np.column_stack(templates)
    coefficients = Y @ np.linalg.pinv(X).T
    residual = Y - coefficients @ X.T
    return float(np.sum(abs(residual) ** 2)), coefficients


def fit_space_delay_glrt(dense, taps, kernel, positions, config):
    """受约束 H1/H2 GLRT/ML：主径 tau0=0，联合搜索两路角度和第二路时延。"""
    Y = dense.reshape(dense.shape[0], -1)
    angle_grid = np.arange(
        config["search_angle_min"],
        config["search_angle_max"] + 0.5 * config["search_angle_step"],
        config["search_angle_step"],
    )
    delay_grid = np.arange(
        config["search_delay_min"],
        config["search_delay_max"] + 0.5 * config["search_delay_step"],
        config["search_delay_step"],
    )
    q0 = np.column_stack(
        [joint_template(positions, angle, 0.0, taps, kernel) for angle in angle_grid]
    )
    q1 = np.column_stack(
        [
            joint_template(positions, angle, delay, taps, kernel)
            for delay in delay_grid
            for angle in angle_grid
        ]
    )
    q1_angles = np.tile(angle_grid, len(delay_grid))
    q1_delays = np.repeat(delay_grid, len(angle_grid))

    data_energy = float(np.sum(abs(Y) ** 2))
    z0_all = Y @ q0.conj()
    norm0_all = np.sum(abs(q0) ** 2, axis=0)
    h1_captured = np.sum(abs(z0_all) ** 2, axis=0) / norm0_all
    best_h1_index = int(np.argmax(h1_captured))
    residual_h1 = data_energy - float(h1_captured[best_h1_index])

    z1 = Y @ q1.conj()
    norm1 = np.sum(abs(q1) ** 2, axis=0).real
    map_residual = np.full((len(delay_grid), len(angle_grid)), np.inf)
    best = (np.inf, None, None)
    for index0, angle0 in enumerate(angle_grid):
        template0 = q0[:, index0]
        z0 = z0_all[:, index0]
        norm0 = float(norm0_all[index0].real)
        cross = template0.conj() @ q1
        determinant = np.maximum(norm0 * norm1 - abs(cross) ** 2, 1e-12)
        captured = (
            norm1 * np.sum(abs(z0) ** 2)
            + norm0 * np.sum(abs(z1) ** 2, axis=0)
            - 2.0 * np.real(cross * np.sum(z0.conj()[:, None] * z1, axis=0))
        ) / determinant
        residuals = np.maximum(data_energy - captured, 1e-20)
        better = residuals < map_residual.reshape(-1)
        map_residual.reshape(-1)[better] = residuals[better]
        candidate = int(np.argmin(residuals))
        if residuals[candidate] < best[0]:
            best = (float(residuals[candidate]), index0, candidate)

    residual_h2, index0, index1 = best
    angle0 = float(angle_grid[index0])
    angle1 = float(q1_angles[index1])
    delay1 = float(q1_delays[index1])
    template0 = q0[:, index0]
    template1 = q1[:, index1]
    _, coefficients = residual_energy_from_templates(Y, [template0, template1])
    improvement_db = 10.0 * np.log10(residual_h1 / residual_h2)
    ratio_db = 20.0 * np.log10(
        np.median(abs(coefficients[:, 1]) / (abs(coefficients[:, 0]) + 1e-30))
    )
    likelihood_db = 10.0 * np.log10(
        residual_h1 / np.maximum(map_residual, 1e-20)
    )
    state = "RELIABLE" if improvement_db >= 6.0 else "NO_SECOND_SOURCE"
    return {
        "state": state,
        "angle_a_deg": angle0,
        "angle_b_deg": angle1,
        "delay_b_chips": delay1,
        "delay_b_m": delay1 * config["chip_m"],
        "ratio_db": float(ratio_db),
        "improvement_db": float(improvement_db),
        "residual_h1": float(residual_h1),
        "residual_h2": float(residual_h2),
        "angle_grid": angle_grid,
        "delay_grid": delay_grid,
        "likelihood_db": likelihood_db,
        "coefficients": coefficients,
    }


def reconstructed_music(glrt, positions, noise_sigma):
    """用 GLRT 支撑重建去相干协方差，再用 MUSIC 形成易读的双角度峰。"""
    estimated_angles = [glrt["angle_a_deg"], glrt["angle_b_deg"]]
    manifold = np.column_stack([steering(positions, angle) for angle in estimated_angles])
    powers = np.mean(abs(glrt["coefficients"]) ** 2, axis=0)
    covariance = manifold @ np.diag(powers) @ manifold.conj().T
    covariance += noise_sigma ** 2 * np.eye(len(positions))
    angle_grid = np.arange(-90.0, 90.01, 0.25)
    scan = np.column_stack([steering(positions, angle) for angle in angle_grid])
    spectrum, eigenvalues = core.music_spectrum(covariance, 2, angle_grid, manifold=scan)
    peaks = core.strongest_peaks(angle_grid, spectrum, 2)
    return covariance, angle_grid, spectrum, eigenvalues, peaks


def normalize_db(values, floor=-45.0):
    values = np.asarray(values, dtype=float)
    values /= max(float(np.max(values)), 1e-30)
    return np.maximum(10.0 * np.log10(np.maximum(values, 1e-30)), floor)


def plot_comparison(raw, smoothing, glrt, rebuilt, config, output_path):
    configure_font()
    _, raw_angles, raw_spectrum, raw_eigenvalues, raw_peaks = raw
    _, rebuilt_angles, rebuilt_spectrum, rebuilt_eigenvalues, rebuilt_peaks = rebuilt
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)

    axes[0, 0].plot(raw_angles, normalize_db(raw_spectrum), color="black")
    axes[0, 0].set_title(
        "普通 MUSIC：原始空间协方差秩=%d（两源要求秩=2）\n估计峰 %s°，不能可靠解释"
        % (covariance_rank(raw_eigenvalues), np.round(raw_peaks, 1).tolist())
    )

    axes[0, 1].axis("off")
    axes[0, 1].text(
        0.5,
        0.58,
        "四阵元 2x2 方阵的标准平移子阵平滑不可用于两源 MUSIC",
        ha="center", va="center", fontsize=13, weight="bold",
    )
    axes[0, 1].text(
        0.5,
        0.39,
        "可平移的 1x2（或 2x1）子阵：维数 2\n"
        "待分离源数：2\n噪声子空间维数：2 - 2 = 0\n\n"
        "使用整个 2x2 虽有 4 维，但只有一个子阵，无法通过平均解相干。",
        ha="center", va="center", fontsize=12,
    )

    image = axes[1, 0].imshow(
        glrt["likelihood_db"],
        origin="lower",
        aspect="auto",
        extent=[
            glrt["angle_grid"][0], glrt["angle_grid"][-1],
            glrt["delay_grid"][0], glrt["delay_grid"][-1],
        ],
        cmap="viridis",
    )
    axes[1, 0].plot(
        glrt["angle_b_deg"], glrt["delay_b_chips"], "rx", markersize=10,
        label="GLRT/ML 估计",
    )
    axes[1, 0].plot(
        config["angle_b_deg"], config["delay_b_chips"], "wo",
        markerfacecolor="none", markersize=10, label="真实第二路",
    )
    axes[1, 0].set_title(
        "空间-时延联合 GLRT/ML：H2 相对 H1 提升 %.1f dB\n"
        "估计 B=(%.1f°, %.2f chip / %.1f m)"
        % (
            glrt["improvement_db"], glrt["angle_b_deg"],
            glrt["delay_b_chips"], glrt["delay_b_m"],
        )
    )
    axes[1, 0].set_xlabel("第二路方位角 / deg")
    axes[1, 0].set_ylabel("第二路相对码延迟 / chip")
    axes[1, 0].legend()
    fig.colorbar(image, ax=axes[1, 0], label="H1→H2 残差改善 / dB")

    axes[1, 1].plot(rebuilt_angles, normalize_db(rebuilt_spectrum), color="black")
    axes[1, 1].set_title(
        "GLRT 支撑约束的协方差重构 + MUSIC\n重构秩=%d，估计峰 %s°"
        % (covariance_rank(rebuilt_eigenvalues), np.round(rebuilt_peaks, 1).tolist())
    )

    for axis in (axes[0, 0], axes[1, 1]):
        axis.axvline(config["angle_a_deg"], color="tab:red", linestyle="--", label="真实 A")
        axis.axvline(config["angle_b_deg"], color="tab:blue", linestyle="--", label="真实 B")
        axis.set_xlabel("方位角 / deg")
        axis.set_ylabel("归一化空间谱 / dB")
        axis.grid(True, alpha=0.25)
        axis.legend()
    fig.suptitle("四阵元正方形阵列：完全相干双源的四种处理结果", fontsize=15)
    fig.savefig(output_path, dpi=180)
    return fig


def plot_likelihood_3d(glrt, config, output_path):
    configure_font()
    angle_mesh, delay_mesh = np.meshgrid(glrt["angle_grid"], glrt["delay_grid"])
    fig = plt.figure(figsize=(11, 8))
    axis = fig.add_subplot(111, projection="3d")
    axis.plot_surface(
        angle_mesh, delay_mesh, glrt["likelihood_db"], cmap="viridis",
        linewidth=0, antialiased=True,
    )
    axis.scatter(
        [config["angle_b_deg"]], [config["delay_b_chips"]],
        [float(np.max(glrt["likelihood_db"]))], color="red", s=60,
        label="真实第二路附近",
    )
    axis.set_xlabel("第二路方位角 / deg")
    axis.set_ylabel("第二路相对码延迟 / chip")
    axis.set_zlabel("H1→H2 残差改善 / dB")
    axis.set_title("空间-时延联合 GLRT/ML 三维似然面")
    axis.legend()
    fig.savefig(output_path, dpi=180)
    return fig


def current_config():
    return {
        "angle_a_deg": SOURCE_A_ANGLE_DEG,
        "angle_b_deg": SOURCE_B_ANGLE_DEG,
        "delay_b_chips": SOURCE_B_DELAY_CHIPS,
        "chip_m": CHIP_LENGTH_M,
        "ratio_db": SOURCE_B_RATIO_DB,
        "phase_deg": SOURCE_B_PHASE_DEG,
        "correlation": SOURCE_CORRELATION,
        "emit_second_source": EMIT_SECOND_SOURCE,
        "noise_sigma": NOISE_SIGMA,
        "n_blocks": N_BLOCKS,
        "seed": RANDOM_SEED,
        "spacing_wl": ELEMENT_SPACING_WAVELENGTHS,
        "orientation_deg": ARRAY_ORIENTATION_DEG,
        "tap_start": DELAY_TAP_START,
        "tap_stop": DELAY_TAP_STOP,
        "tap_step": DELAY_TAP_STEP,
        "search_angle_min": SEARCH_ANGLE_MIN_DEG,
        "search_angle_max": SEARCH_ANGLE_MAX_DEG,
        "search_angle_step": SEARCH_ANGLE_STEP_DEG,
        "search_delay_min": SEARCH_DELAY_MIN_CHIPS,
        "search_delay_max": SEARCH_DELAY_MAX_CHIPS,
        "search_delay_step": SEARCH_DELAY_STEP_CHIPS,
    }


def run_lab(config=None, output_dir=OUTPUT_DIR, show=SHOW_FIGURES):
    config = current_config() if config is None else config
    output_dir.mkdir(parents=True, exist_ok=True)
    dense, taps, kernel, positions = synthesize_scene(config)
    raw = raw_music(dense, taps, positions)
    smoothing = square_smoothing_diagnostic(raw[0])
    glrt = fit_space_delay_glrt(dense, taps, kernel, positions, config)
    rebuilt = reconstructed_music(glrt, positions, config["noise_sigma"])

    comparison_path = output_dir / "方阵相干双源四种处理方法对比.png"
    surface_path = output_dir / "方阵空间时延联合似然三维图.png"
    figure1 = plot_comparison(raw, smoothing, glrt, rebuilt, config, comparison_path)
    figure2 = plot_likelihood_3d(glrt, config, surface_path)
    summary = {
        "configuration": config,
        "raw_music": {
            "estimated_rank": covariance_rank(raw[3]),
            "peaks_deg": raw[4].tolist(),
            "reliable": False if config["correlation"] > 0.99 else None,
        },
        "standard_square_smoothing": smoothing,
        "space_delay_glrt_ml": {
            key: value for key, value in glrt.items()
            if key not in ("angle_grid", "delay_grid", "likelihood_db", "coefficients")
        },
        "reconstructed_music": {
            "estimated_rank": covariance_rank(rebuilt[3]),
            "peaks_deg": rebuilt[4].tolist(),
            "note": "角度支撑来自空间-时延 GLRT/ML；重构本身不是独立发现器。",
        },
    }
    summary_path = output_dir / "方阵相干双源处理结果.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("普通 MUSIC: rank=%d peaks=%s -> 完全相干时不可靠" % (
        covariance_rank(raw[3]), np.round(raw[4], 1).tolist()
    ))
    print("标准方阵平滑:", smoothing["reason"])
    print(
        "空间-时延 GLRT/ML: A=%.1f deg, B=%.1f deg, delay=%.2f chip (%.1f m), "
        "ratio=%.2f dB, improvement=%.1f dB"
        % (
            glrt["angle_a_deg"], glrt["angle_b_deg"], glrt["delay_b_chips"],
            glrt["delay_b_m"], glrt["ratio_db"], glrt["improvement_db"],
        )
    )
    print("重构 MUSIC: rank=%d peaks=%s" % (
        covariance_rank(rebuilt[3]), np.round(rebuilt[4], 1).tolist()
    ))
    print("图片:", comparison_path.resolve())
    print("图片:", surface_path.resolve())
    print("结果:", summary_path.resolve())
    if show:
        plt.show()
    else:
        plt.close(figure1)
        plt.close(figure2)
    return summary, comparison_path, surface_path


if __name__ == "__main__":
    run_lab()

#!/usr/bin/env python3
"""四阵元 ULA 的真实 GPS L1 C/A 波形、MUSIC、FBSS 与双路时延实验台。

信号先按 GPS L1 C/A Gold 码生成原始复基带 IQ，再按 1 ms 分块执行多抽头
相关。两路发射信号来自同一个源的功分，码、导航数据和时钟完全相同；线缆长度、
空间传播距离和可选差分相位抖动形成两路差异。
"""

from pathlib import Path
import csv
import json
import os

import matplotlib

if os.name != "nt" and not os.environ.get("DISPLAY"):
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import simulate_coherent_music_parking as array_tools


# ======================== 用户可修改实验参数区 ========================

# 实验模式："fixed" 只计算固定接收机；"random" 在圆域随机生成点；"both" 两者都做。
EXPERIMENT_MODE = "both"

# GPS L1 C/A 卫星 PRN。当前实现支持 1~32；C/A 码由 G1/G2 两个 m 序列组成 Gold 码。
GPS_PRN = 28
# L1 载波频率与 C/A 码速率。一般不修改。
CARRIER_HZ = 1575.42e6
CODE_RATE_HZ = 1.023e6
# 采样率。20.46 MHz = 每码片 20 点，可表达 0.05 chip 的相关 tap。
SAMPLE_RATE_HZ = 20.46e6
# 生成多少个 1 ms C/A 周期。C/N0 越低，形成稳定空间协方差所需历元通常越多。
# 例如 30 dB-Hz 时每个 1 ms 相关输出约 0 dB SNR，但 30 只是示例，不是场景边界。
CODE_PERIODS = 300

# 两个 DAS 发射天线坐标，单位 m。
TX_A_X_M = -10.0
TX_A_Y_M = 0.0
TX_B_X_M = 10.0
TX_B_Y_M = 0.0
# 固定接收机（四阵元阵列中心）坐标，单位 m。
RECEIVER_X_M = 0.0
RECEIVER_Y_M = 5.0

# 两路由同一源功分。这里是功分器、功放及天线造成的相对发射功率，单位 dB。
TX_A_POWER_DB = 0.0
TX_B_POWER_DB = 0.0
# 两路线缆长度与速度因子。电缆延迟 = 长度 / (速度因子*c)。线长差同时改变
# 码时延和 L1 载波相位，不能把二者设成互不相关的自由参数。
CABLE_A_LENGTH_M = 10.0
CABLE_B_LENGTH_M = 10.0
CABLE_VELOCITY_FACTOR = 0.66
# 可选硬件固定相位偏置，用于表示功放/连接器未被线长模型解释的相位，单位 deg。
TX_B_EXTRA_PHASE_DEG = 0.0
# 同源同钟的理想值为 0。大于 0 时，每毫秒给 B 路加入差分相位抖动 RMS。
DIFFERENTIAL_PHASE_JITTER_DEG_RMS = 0.0

# 固定点是否额外扫描未知硬件相位。对同源静态双路，相关系数仍为 1，但相对载波
# 相位未知；FBSS 在少数相位会退化，所以不能只展示某一个有利相位。
ENABLE_RELATIVE_PHASE_SWEEP = True
RELATIVE_PHASE_SWEEP_DEG = tuple(range(0, 360, 30))
# 固定相对相位后扫描 C/N0，用于判断 FBSS 的实际工作门限。90 度避开当前
# 对称几何在 0/180 度附近的病态相位；相位扫描仍负责揭示这种退化。
ENABLE_CN0_SWEEP = True
CN0_SWEEP_DB_HZ = (10.0, 20.0, 30.0, 35.0, 40.0, 45.0, 50.0)
CN0_SWEEP_PHASE_DEG = 90.0
# 每个 C/N0 条件的独立噪声重复次数。正式论文统计建议提高到 50 或 100；默认 3
# 便于普通电脑交互运行，不能据此估计精确检测概率。
CN0_SWEEP_RUNS = 3

# 手机 GNSS Logger 通常显示 C/N0，单位 dB-Hz，不是带内 SNR。
# 本值定义：A 路在 REFERENCE_DISTANCE_M 处、无阵列增益时的 C/N0。
CN0_A_AT_REFERENCE_DB_HZ = 30.0
REFERENCE_DISTANCE_M = 10.0
# 室内经验路径损耗指数：2 接近自由空间；更大表示遮挡更重；0 表示不随距离衰减。
PATH_LOSS_EXPONENT = 2.0

# 热噪声始终存在，由上面的 C/N0 自动换算。
# 可选窄带干扰：J/S 是干扰功率相对参考 A 路载波功率。默认关闭，先建立干净基线。
ENABLE_CW_INTERFERENCE = False
CW_JS_DB = -10.0
CW_OFFSET_HZ = 25000.0
CW_BEARING_DEG = 270.0
# 可选额外宽带干扰，模拟停车场设备抬高噪声底。INR 是干扰功率/热噪声功率。
ENABLE_WIDEBAND_INTERFERENCE = False
WIDEBAND_INR_DB = 3.0

# 四通道未校准残差。每次 run 随机生成并在该 run 内固定；估计算法仍使用理想流形，
# 用于检查校准误差造成的失配。0 表示理想校准。
CHANNEL_GAIN_ERROR_DB_RMS = 0.0
CHANNEL_PHASE_ERROR_DEG_RMS = 0.0

# 四阵元均匀线阵参数。0.5 波长在 L1 约 9.51 cm，总孔径约 28.5 cm。
ULA_ELEMENT_COUNT = 4
ULA_SPACING_WAVELENGTHS = 0.5
# 阵列轴的全局方向。0° 表示阵元沿 X 轴排布。
ULA_AXIS_DEG = 0.0
# ULA 有前后镜像。"negative_y" 表示已知两发射天线位于接收机 Y 负半平面；
# None 表示不使用该停车场先验，此时同一空间相位对应两个镜像方向。
KNOWN_HALF_PLANE = "negative_y"
# 随机圆域通常跨越 ULA 两侧，不能沿用固定点半平面先验。False 表示随机模式按
# 0~360° 扫描并诚实计入前后镜像；只有随机区域确实全部位于同一侧时才改 True。
RANDOM_USE_KNOWN_HALF_PLANE = False

# 多抽头相关器范围和间隔，单位 chip。这里就是论文中 delay estimation 的观测面。
CORRELATOR_TAP_START_CHIPS = -0.5
CORRELATOR_TAP_STOP_CHIPS = 0.5
CORRELATOR_TAP_STEP_CHIPS = 0.05
# 角度和时延搜索步长。更小更精细但更慢。
DOA_GRID_STEP_DEG = 0.5
DELAY_GRID_STEP_CHIPS = 0.01

# 随机圆域开关参数。圆心可以选 "midpoint"、"tx_a" 或 "tx_b"。
RANDOM_CENTER_MODE = "midpoint"
RANDOM_RADIUS_M = 15.0
# 随机接收机点数量。点在圆内按面积均匀分布，不会全部堆在圆心附近。
RANDOM_RECEIVER_COUNT = 30
# 接收机距离任一发射天线小于该值时重新抽样，避免近场奇点。
RANDOM_MIN_TX_DISTANCE_M = 1.0
RANDOM_SEED = 20260814

# 成功判据：两路 DOA 均在角度容差内，且相对时延误差不超过该米数。
ANGLE_TOLERANCE_DEG = 5.0
DELAY_TOLERANCE_M = 10.0

# 是否弹出图窗；无桌面服务器自动只保存图片。
SHOW_FIGURES = True
OUTPUT_DIR = Path("dev_notes/sim/results/ula_gnss_waveform_fbss")


C_MPS = 299792458.0
CHIP_M = C_MPS / CODE_RATE_HZ

# GPS L1 C/A PRN 的 G2 延迟抽头（1-based）。
G2_TAPS = {
    1: (2, 6), 2: (3, 7), 3: (4, 8), 4: (5, 9), 5: (1, 9), 6: (2, 10),
    7: (1, 8), 8: (2, 9), 9: (3, 10), 10: (2, 3), 11: (3, 4), 12: (5, 6),
    13: (6, 7), 14: (7, 8), 15: (8, 9), 16: (9, 10), 17: (1, 4), 18: (2, 5),
    19: (3, 6), 20: (4, 7), 21: (5, 8), 22: (6, 9), 23: (1, 3), 24: (4, 6),
    25: (5, 7), 26: (6, 8), 27: (7, 9), 28: (8, 10), 29: (1, 6), 30: (2, 7),
    31: (3, 8), 32: (4, 9),
}


def configure_font():
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"
    ]
    plt.rcParams["axes.unicode_minus"] = False


def gps_l1_ca_code(prn):
    """生成一个 1023-chip GPS L1 C/A Gold 码，输出为复相关方便的 +/-1。"""
    if prn not in G2_TAPS:
        raise ValueError("GPS_PRN must be in 1..32")
    g1 = np.ones(10, dtype=np.uint8)
    g2 = np.ones(10, dtype=np.uint8)
    output = np.empty(1023, dtype=float)
    tap_a, tap_b = G2_TAPS[prn]
    for index in range(1023):
        bit = g1[9] ^ g2[tap_a - 1] ^ g2[tap_b - 1]
        output[index] = 1.0 if bit == 0 else -1.0
        g1_feedback = g1[2] ^ g1[9]
        g2_feedback = g2[1] ^ g2[2] ^ g2[5] ^ g2[7] ^ g2[8] ^ g2[9]
        g1[1:] = g1[:-1]
        g2[1:] = g2[:-1]
        g1[0] = g1_feedback
        g2[0] = g2_feedback
    return output


def sample_code(code, times_s, delay_s=0.0):
    chip_phase = np.floor((times_s - delay_s) * CODE_RATE_HZ).astype(np.int64)
    return code[np.mod(chip_phase, len(code))]


def ula_positions_m():
    wavelength = C_MPS / CARRIER_HZ
    spacing = ULA_SPACING_WAVELENGTHS * wavelength
    offsets = (np.arange(ULA_ELEMENT_COUNT) - (ULA_ELEMENT_COUNT - 1) / 2.0) * spacing
    axis = np.radians(ULA_AXIS_DEG)
    return offsets[:, None] * np.array([np.cos(axis), np.sin(axis)])[None, :]


def bearing_deg(receiver_xy, transmitter_xy):
    delta = np.asarray(transmitter_xy) - np.asarray(receiver_xy)
    return float(np.mod(np.degrees(np.arctan2(delta[1], delta[0])), 360.0))


def steering_manifold(positions_m, bearings_deg):
    positions_wl = positions_m / (C_MPS / CARRIER_HZ)
    return np.column_stack([
        array_tools.steering_from_positions(positions_wl, bearing)
        for bearing in np.atleast_1d(bearings_deg)
    ])


def effective_path_length_m(receiver_xy, transmitter_xy, cable_length_m):
    radio_range = float(np.linalg.norm(np.asarray(transmitter_xy) - np.asarray(receiver_xy)))
    return radio_range + cable_length_m / CABLE_VELOCITY_FACTOR


def path_amplitude(range_m, transmitter_power_db):
    distance_factor = (REFERENCE_DISTANCE_M / max(range_m, 0.1)) ** (PATH_LOSS_EXPONENT / 2.0)
    return 10.0 ** (transmitter_power_db / 20.0) * distance_factor


def correlator_taps():
    return np.arange(CORRELATOR_TAP_START_CHIPS,
                     CORRELATOR_TAP_STOP_CHIPS + 0.5 * CORRELATOR_TAP_STEP_CHIPS,
                     CORRELATOR_TAP_STEP_CHIPS)


def local_replicas(code, times_one_period, taps):
    return np.vstack([
        sample_code(code, times_one_period, tap / CODE_RATE_HZ) for tap in taps
    ])


def simulate_correlators(receiver_xy, rng):
    """生成原始 IQ 并执行 1 ms 多抽头相关，返回 (block, antenna, tap)。"""
    receiver_xy = np.asarray(receiver_xy, dtype=float)
    transmitters = [np.array([TX_A_X_M, TX_A_Y_M]), np.array([TX_B_X_M, TX_B_Y_M])]
    cables = [CABLE_A_LENGTH_M, CABLE_B_LENGTH_M]
    powers_db = [TX_A_POWER_DB, TX_B_POWER_DB]
    positions = ula_positions_m()
    code = gps_l1_ca_code(GPS_PRN)
    samples_per_period = int(round(SAMPLE_RATE_HZ * 0.001))
    if not np.isclose(samples_per_period / SAMPLE_RATE_HZ, 0.001, atol=1e-12):
        raise ValueError("SAMPLE_RATE_HZ must produce an integer number of samples per 1 ms")
    t_period = np.arange(samples_per_period) / SAMPLE_RATE_HZ
    taps = correlator_taps()
    replicas = local_replicas(code, t_period, taps)

    center_lengths = [effective_path_length_m(receiver_xy, tx, cable)
                      for tx, cable in zip(transmitters, cables)]
    reference_length = center_lengths[0]
    relative_delays_s = [(length - reference_length) / C_MPS for length in center_lengths]
    ranges = [float(np.linalg.norm(tx - receiver_xy)) for tx in transmitters]
    amplitudes = [path_amplitude(distance, power) for distance, power in zip(ranges, powers_db)]
    bearings = [bearing_deg(receiver_xy, tx) for tx in transmitters]

    # C/N0 convention: reference A carrier power C=1. N0=C/(C/N0), and sampled
    # complex AWGN has E|n[k]|^2=N0*fs. Therefore after T seconds correlation,
    # SNR = (C/N0)*T, exactly matching the dB-Hz definition.
    cn0_linear = 10.0 ** (CN0_A_AT_REFERENCE_DB_HZ / 10.0)
    noise_variance = SAMPLE_RATE_HZ / cn0_linear
    output = np.empty((CODE_PERIODS, ULA_ELEMENT_COUNT, len(taps)), complex)
    nav_rng = np.random.default_rng(RANDOM_SEED + 17)
    nav_bits = nav_rng.choice([-1.0, 1.0], size=(CODE_PERIODS + 19) // 20)
    channel_gain_db = rng.normal(0.0, CHANNEL_GAIN_ERROR_DB_RMS, ULA_ELEMENT_COUNT)
    channel_phase_deg = rng.normal(0.0, CHANNEL_PHASE_ERROR_DEG_RMS, ULA_ELEMENT_COUNT)
    channel_response = 10.0 ** (channel_gain_db / 20.0) * np.exp(1j * np.radians(channel_phase_deg))

    for block in range(CODE_PERIODS):
        absolute_time = block * 0.001 + t_period
        iq = np.zeros((ULA_ELEMENT_COUNT, samples_per_period), complex)
        nav_bit = nav_bits[block // 20]
        for source_index, transmitter in enumerate(transmitters):
            code_wave = sample_code(code, absolute_time, relative_delays_s[source_index])
            jitter = (rng.normal(0.0, DIFFERENTIAL_PHASE_JITTER_DEG_RMS)
                      if source_index == 1 else 0.0)
            extra_phase = TX_B_EXTRA_PHASE_DEG if source_index == 1 else 0.0
            for antenna_index, offset in enumerate(positions):
                antenna_xy = receiver_xy + offset
                range_element = float(np.linalg.norm(transmitter - antenna_xy))
                effective_element = range_element + cables[source_index] / CABLE_VELOCITY_FACTOR
                carrier_phase = -2.0 * np.pi * CARRIER_HZ * (
                    effective_element - reference_length) / C_MPS
                carrier_phase += np.radians(extra_phase + jitter)
                iq[antenna_index] += (
                    amplitudes[source_index] * nav_bit * code_wave * np.exp(1j * carrier_phase)
                )
        if ENABLE_CW_INTERFERENCE:
            cw_amp = 10.0 ** (CW_JS_DB / 20.0)
            cw = cw_amp * np.exp(1j * (2.0 * np.pi * CW_OFFSET_HZ * absolute_time
                                       + rng.uniform(0.0, 2.0 * np.pi)))
            iq += steering_manifold(positions, [CW_BEARING_DEG])[:, 0, None] * cw[None, :]
        noise = np.sqrt(noise_variance / 2.0) * (
            rng.standard_normal(iq.shape) + 1j * rng.standard_normal(iq.shape)
        )
        if ENABLE_WIDEBAND_INTERFERENCE:
            interference_variance = noise_variance * 10.0 ** (WIDEBAND_INR_DB / 10.0)
            noise += np.sqrt(interference_variance / 2.0) * (
                rng.standard_normal(iq.shape) + 1j * rng.standard_normal(iq.shape)
            )
        iq += noise
        iq *= channel_response[:, None]
        output[block] = iq @ replicas.T / samples_per_period

    truth = {
        "receiver_xy_m": receiver_xy.tolist(),
        "bearings_deg": bearings,
        "relative_delays_s": relative_delays_s,
        "relative_delays_chips": [delay * CODE_RATE_HZ for delay in relative_delays_s],
        "relative_delays_m": [delay * C_MPS for delay in relative_delays_s],
        "ranges_m": ranges,
        "amplitudes": amplitudes,
        "cn0_a_db_hz": CN0_A_AT_REFERENCE_DB_HZ
            - 10.0 * PATH_LOSS_EXPONENT * np.log10(max(ranges[0], 0.1) / REFERENCE_DISTANCE_M),
        "cn0_b_db_hz": CN0_A_AT_REFERENCE_DB_HZ + TX_B_POWER_DB - TX_A_POWER_DB
            - 10.0 * PATH_LOSS_EXPONENT * np.log10(max(ranges[1], 0.1) / REFERENCE_DISTANCE_M),
        "raw_sample_snr_a_db": CN0_A_AT_REFERENCE_DB_HZ - 10.0 * np.log10(SAMPLE_RATE_HZ),
        "one_ms_correlator_snr_a_db": CN0_A_AT_REFERENCE_DB_HZ + 10.0 * np.log10(0.001),
        "emitted_source_coherence": 1.0 if DIFFERENTIAL_PHASE_JITTER_DEG_RMS == 0 else None,
        "channel_gain_error_db": channel_gain_db.tolist(),
        "channel_phase_error_deg": channel_phase_deg.tolist(),
    }
    return output, taps, positions, truth


def strongest_peaks(grid, spectrum, count=2, separation_deg=10.0):
    """只从局部极大值选峰，避免把同一宽峰的相邻网格误报为两路。"""
    candidates = np.where((spectrum[1:-1] > spectrum[:-2])
                          & (spectrum[1:-1] >= spectrum[2:]))[0] + 1
    if len(candidates) == 0:
        candidates = np.array([int(np.argmax(spectrum))])
    order = candidates[np.argsort(spectrum[candidates])[::-1]]
    peaks = []
    for index in order:
        angle = float(grid[index])
        if all(array_tools.circular_angle_difference(angle, old) >= separation_deg for old in peaks):
            peaks.append(angle)
        if len(peaks) == count:
            break
    return sorted(peaks)


def scan_grid():
    if KNOWN_HALF_PLANE == "negative_y":
        return np.arange(180.0, 360.0 + 0.5 * DOA_GRID_STEP_DEG, DOA_GRID_STEP_DEG)
    if KNOWN_HALF_PLANE == "positive_y":
        return np.arange(0.0, 180.0 + 0.5 * DOA_GRID_STEP_DEG, DOA_GRID_STEP_DEG)
    return np.arange(0.0, 360.0, DOA_GRID_STEP_DEG)


def estimate_delays(correlators, positions, bearings, taps, code):
    manifold = steering_manifold(positions, bearings)
    separated = np.einsum("sm,bmt->bst", np.linalg.pinv(manifold), correlators)
    # 两路来自同一源，导航位翻转是共同的。以每个历元最强 prompt 的相位作公共
    # 符号/相位参考，再相干平均；这保留复相关峰并比直接平均功率更适合低 C/N0。
    prompt_index = int(np.argmin(abs(taps)))
    common_prompt = np.sum(separated[:, :, prompt_index], axis=1)
    common_rotation = np.exp(-1j * np.angle(common_prompt + 1e-30))
    coherent_profiles = np.mean(separated * common_rotation[:, None, None], axis=0)
    profiles = abs(coherent_profiles)
    delay_grid = np.arange(CORRELATOR_TAP_START_CHIPS,
                           CORRELATOR_TAP_STOP_CHIPS + 0.5 * DELAY_GRID_STEP_CHIPS,
                           DELAY_GRID_STEP_CHIPS)
    # Reference kernel is generated from the same real Gold code and sampling chain.
    samples_per_period = int(round(SAMPLE_RATE_HZ * 0.001))
    times = np.arange(samples_per_period) / SAMPLE_RATE_HZ
    prompt = sample_code(code, times)
    kernel = np.array([np.mean(prompt * sample_code(code, times, delay / CODE_RATE_HZ))
                       for delay in taps])
    estimates = []
    for profile in profiles:
        best = None
        for delay in delay_grid:
            template = np.interp(taps - delay, taps, kernel, left=0.0, right=0.0)
            design = np.column_stack([template, np.ones_like(template)])
            coefficient, *_ = np.linalg.lstsq(design, profile, rcond=None)
            residual = float(np.linalg.norm(profile - design @ coefficient))
            if best is None or residual < best[0]:
                best = (residual, float(delay))
        estimates.append(best[1])
    return estimates, profiles, kernel


def match_estimates(estimated_bearings, estimated_delays, truth):
    true_bearings = truth["bearings_deg"]
    permutations = [(0, 1), (1, 0)]
    permutation = min(permutations, key=lambda order: sum(
        array_tools.circular_angle_difference(estimated_bearings[order[i]], true_bearings[i])
        for i in range(2)))
    bearings = [estimated_bearings[permutation[i]] for i in range(2)]
    delays = [estimated_delays[permutation[i]] for i in range(2)]
    angle_errors = [array_tools.circular_angle_difference(bearings[i], true_bearings[i])
                    for i in range(2)]
    true_delta_m = truth["relative_delays_m"][1] - truth["relative_delays_m"][0]
    estimated_delta_m = (delays[1] - delays[0]) * CHIP_M
    return {
        "estimated_bearings_deg": bearings,
        "estimated_delays_chips": delays,
        "angle_errors_deg": angle_errors,
        "angle_rmse_deg": float(np.sqrt(np.mean(np.square(angle_errors)))),
        "true_delta_m": true_delta_m,
        "estimated_delta_m": estimated_delta_m,
        "delay_error_m": estimated_delta_m - true_delta_m,
        "success": bool(max(angle_errors) <= ANGLE_TOLERANCE_DEG
                        and abs(estimated_delta_m - true_delta_m) <= DELAY_TOLERANCE_M),
    }


def process_methods(correlators, taps, positions, truth):
    prompt_index = int(np.argmin(abs(taps)))
    snapshots = correlators[:, :, prompt_index].T
    raw_covariance = array_tools.covariance(snapshots)
    grid = scan_grid()
    scan_manifold = steering_manifold(positions, grid)
    direct_spectrum, direct_eigenvalues = array_tools.music_spectrum(
        raw_covariance, 2, grid, manifold=scan_manifold)
    smoothed = array_tools.forward_backward_spatial_smoothing(raw_covariance, 3)
    # Three-element translated subarray is centered at the same origin for MUSIC.
    sub_positions = positions[:3] - np.mean(positions[:3], axis=0)
    smooth_manifold = steering_manifold(sub_positions, grid)
    smooth_spectrum, smooth_eigenvalues = array_tools.music_spectrum(
        smoothed, 2, grid, manifold=smooth_manifold)
    code = gps_l1_ca_code(GPS_PRN)
    results = {}
    for name, spectrum in (("direct_music", direct_spectrum), ("fbss_music", smooth_spectrum)):
        bearings = strongest_peaks(grid, spectrum)
        if len(bearings) < 2:
            delays, profiles, kernel = [], np.empty((0, len(taps))), np.zeros(len(taps))
            results[name] = {
                "estimated_bearings_deg": bearings,
                "estimated_delays_chips": [],
                "angle_errors_deg": [],
                "angle_rmse_deg": float("inf"),
                "true_delta_m": truth["relative_delays_m"][1] - truth["relative_delays_m"][0],
                "estimated_delta_m": None,
                "delay_error_m": None,
                "success": False,
                "state": "UNRESOLVED_ONE_PEAK",
            }
        else:
            delays, profiles, kernel = estimate_delays(correlators, positions, bearings, taps, code)
            results[name] = match_estimates(bearings, delays, truth)
            results[name]["state"] = "RESOLVED" if results[name]["success"] else "WRONG_SOLUTION"
        results[name]["spectrum"] = spectrum
        results[name]["profiles"] = profiles
        results[name]["kernel"] = kernel
    results["grid"] = grid
    results["raw_eigenvalues"] = direct_eigenvalues
    results["smooth_eigenvalues"] = smooth_eigenvalues
    return results


def serializable_result(result):
    output = {}
    for key, value in result.items():
        if key in ("spectrum", "profiles", "kernel"):
            continue
        if isinstance(value, np.ndarray):
            output[key] = value.tolist()
        elif isinstance(value, np.generic):
            output[key] = value.item()
        else:
            output[key] = value
    return output


def run_fixed(output_dir):
    receiver = np.array([RECEIVER_X_M, RECEIVER_Y_M])
    correlators, taps, positions, truth = simulate_correlators(
        receiver, np.random.default_rng(RANDOM_SEED))
    result = process_methods(correlators, taps, positions, truth)
    summary = {"truth": truth,
               "direct_music": serializable_result(result["direct_music"]),
               "fbss_music": serializable_result(result["fbss_music"]),
               "raw_eigenvalues": result["raw_eigenvalues"].tolist(),
               "smooth_eigenvalues": result["smooth_eigenvalues"].tolist()}
    (output_dir / "固定接收机四阵元ULA结果.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    tx = np.array([[TX_A_X_M, TX_A_Y_M], [TX_B_X_M, TX_B_Y_M]])
    axes[0].scatter(tx[:, 0], tx[:, 1], marker="^", s=100, label="发射天线")
    axes[0].scatter(receiver[0], receiver[1], marker="x", s=100, label="接收机")
    axes[0].set_aspect("equal"); axes[0].grid(True); axes[0].legend()
    axes[0].set_title("停车场几何"); axes[0].set_xlabel("X / m"); axes[0].set_ylabel("Y / m")
    for name, color in (("direct_music", "#D1495B"), ("fbss_music", "#276FBF")):
        spectrum = result[name]["spectrum"] / max(np.max(result[name]["spectrum"]), 1e-15)
        axes[1].plot(result["grid"], 10 * np.log10(np.maximum(spectrum, 1e-8)),
                     label=name, color=color)
    for bearing in truth["bearings_deg"]:
        axes[1].axvline(bearing, color="black", linestyle="--", alpha=0.5)
    axes[1].set_ylim(-50, 2); axes[1].grid(True); axes[1].legend()
    axes[1].set_title("直接 MUSIC 与 FBSS-MUSIC 空间谱")
    axes[1].set_xlabel("全局方位角 / deg"); axes[1].set_ylabel("归一化谱 / dB")
    for index, profile in enumerate(result["fbss_music"]["profiles"]):
        axes[2].plot(taps, profile / max(np.max(profile), 1e-15), label=f"分离路 {index}")
    axes[2].set_title("FBSS 估角后两路相关峰")
    axes[2].set_xlabel("相对码延迟 / chip"); axes[2].set_ylabel("归一化相关功率")
    axes[2].grid(True)
    if len(result["fbss_music"]["profiles"]):
        axes[2].legend()
    fig.tight_layout(); fig.savefig(output_dir / "固定接收机MUSIC_FBSS与双路时延.png", dpi=180)
    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close(fig)
    return summary


def run_phase_sweep(output_dir):
    """扫描未校准硬件相位，量化完全相干双路的相位退化区。"""
    global TX_B_EXTRA_PHASE_DEG
    original_phase = TX_B_EXTRA_PHASE_DEG
    rows = []
    try:
        for index, phase in enumerate(RELATIVE_PHASE_SWEEP_DEG):
            TX_B_EXTRA_PHASE_DEG = float(phase)
            correlators, taps, positions, truth = simulate_correlators(
                [RECEIVER_X_M, RECEIVER_Y_M],
                np.random.default_rng(RANDOM_SEED + 5000 + index))
            result = process_methods(correlators, taps, positions, truth)
            rows.append({
                "relative_phase_deg": phase,
                "direct_music_success": int(result["direct_music"]["success"]),
                "direct_music_angle_rmse_deg": result["direct_music"]["angle_rmse_deg"],
                "fbss_music_success": int(result["fbss_music"]["success"]),
                "fbss_music_angle_rmse_deg": result["fbss_music"]["angle_rmse_deg"],
                "fbss_music_state": result["fbss_music"]["state"],
            })
    finally:
        TX_B_EXTRA_PHASE_DEG = original_phase
    path = output_dir / "固定点相对载波相位扫描.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for method, color in (("direct_music", "#D1495B"), ("fbss_music", "#276FBF")):
        values = [row[f"{method}_angle_rmse_deg"] for row in rows]
        values = [value if np.isfinite(value) else 180.0 for value in values]
        ax.plot([row["relative_phase_deg"] for row in rows], values,
                marker="o", label=method, color=color)
    ax.axhline(ANGLE_TOLERANCE_DEG, color="black", linestyle="--", label="角度门限")
    ax.set_xlabel("B 路额外相对载波相位 / deg")
    ax.set_ylabel("两路角度 RMSE / deg")
    ax.set_title("完全相干双路的相位敏感性")
    ax.grid(True); ax.legend()
    fig.tight_layout(); fig.savefig(output_dir / "固定点相对载波相位敏感性.png", dpi=180)
    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close(fig)
    return rows


def run_cn0_sweep(output_dir):
    """固定几何和相对相位，扫描参考距离处的 C/N0。"""
    global CN0_A_AT_REFERENCE_DB_HZ, TX_B_EXTRA_PHASE_DEG
    original_cn0 = CN0_A_AT_REFERENCE_DB_HZ
    original_phase = TX_B_EXTRA_PHASE_DEG
    rows = []
    try:
        TX_B_EXTRA_PHASE_DEG = CN0_SWEEP_PHASE_DEG
        for cn0_index, cn0 in enumerate(CN0_SWEEP_DB_HZ):
            CN0_A_AT_REFERENCE_DB_HZ = float(cn0)
            for run in range(CN0_SWEEP_RUNS):
                correlators, taps, positions, truth = simulate_correlators(
                    [RECEIVER_X_M, RECEIVER_Y_M],
                    np.random.default_rng(RANDOM_SEED + 7000 + 100 * cn0_index + run))
                result = process_methods(correlators, taps, positions, truth)
                rows.append({
                    "reference_cn0_db_hz": cn0,
                    "actual_cn0_a_db_hz": truth["cn0_a_db_hz"],
                    "run": run + 1,
                    "direct_music_success": int(result["direct_music"]["success"]),
                    "direct_music_angle_rmse_deg": result["direct_music"]["angle_rmse_deg"],
                    "fbss_music_success": int(result["fbss_music"]["success"]),
                    "fbss_music_angle_rmse_deg": result["fbss_music"]["angle_rmse_deg"],
                    "fbss_music_state": result["fbss_music"]["state"],
                })
    finally:
        CN0_A_AT_REFERENCE_DB_HZ = original_cn0
        TX_B_EXTRA_PHASE_DEG = original_phase

    path = output_dir / "固定点CN0扫描.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    fig, (ax, rate_axis) = plt.subplots(2, 1, figsize=(8, 7), sharex=True)
    actual_levels = sorted(set(row["actual_cn0_a_db_hz"] for row in rows))
    for method, color in (("direct_music", "#D1495B"), ("fbss_music", "#276FBF")):
        medians = []
        rates = []
        for level in actual_levels:
            selected = [row for row in rows if row["actual_cn0_a_db_hz"] == level]
            values = [row[f"{method}_angle_rmse_deg"] for row in selected]
            values = [value if np.isfinite(value) else 180.0 for value in values]
            medians.append(float(np.median(values)))
            rates.append(float(np.mean([row[f"{method}_success"] for row in selected])))
        ax.plot(actual_levels, medians, marker="o", label=method, color=color)
        rate_axis.plot(actual_levels, rates, marker="o", label=method, color=color)
    ax.axhline(ANGLE_TOLERANCE_DEG, color="black", linestyle="--", label="角度门限")
    ax.set_xlabel("A 路实际 C/N0 / dB-Hz")
    ax.set_ylabel("两路角度 RMSE / deg")
    ax.set_title(f"固定相位 {CN0_SWEEP_PHASE_DEG:.0f} 度下的 C/N0 扫描"
                 f"（每档 {CN0_SWEEP_RUNS} 次）")
    ax.grid(True)
    ax.legend()
    rate_axis.set_xlabel("A 路实际 C/N0 / dB-Hz")
    rate_axis.set_ylabel("严格成功率")
    rate_axis.set_ylim(-0.05, 1.05)
    rate_axis.grid(True)
    rate_axis.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "固定点CN0扫描.png", dpi=180)
    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close(fig)
    return rows


def random_center():
    if RANDOM_CENTER_MODE == "tx_a":
        return np.array([TX_A_X_M, TX_A_Y_M])
    if RANDOM_CENTER_MODE == "tx_b":
        return np.array([TX_B_X_M, TX_B_Y_M])
    if RANDOM_CENTER_MODE == "midpoint":
        return np.array([(TX_A_X_M + TX_B_X_M) / 2.0, (TX_A_Y_M + TX_B_Y_M) / 2.0])
    raise ValueError("RANDOM_CENTER_MODE must be midpoint, tx_a, or tx_b")


def random_receivers(rng):
    center = random_center()
    transmitters = np.array([[TX_A_X_M, TX_A_Y_M], [TX_B_X_M, TX_B_Y_M]])
    points = []
    while len(points) < RANDOM_RECEIVER_COUNT:
        radius = RANDOM_RADIUS_M * np.sqrt(rng.random())
        angle = rng.uniform(0.0, 2.0 * np.pi)
        point = center + radius * np.array([np.cos(angle), np.sin(angle)])
        if np.min(np.linalg.norm(transmitters - point, axis=1)) >= RANDOM_MIN_TX_DISTANCE_M:
            points.append(point)
    return np.asarray(points)


def run_random(output_dir):
    global KNOWN_HALF_PLANE
    rng = np.random.default_rng(RANDOM_SEED)
    points = random_receivers(rng)
    rows = []
    original_half_plane = KNOWN_HALF_PLANE
    if not RANDOM_USE_KNOWN_HALF_PLANE:
        KNOWN_HALF_PLANE = None
    try:
        for index, receiver in enumerate(points):
            correlators, taps, positions, truth = simulate_correlators(
                receiver, np.random.default_rng(RANDOM_SEED + 1000 + index))
            result = process_methods(correlators, taps, positions, truth)
            row = {"receiver_index": index, "receiver_x_m": receiver[0], "receiver_y_m": receiver[1],
                   "true_bearing_a_deg": truth["bearings_deg"][0],
                   "true_bearing_b_deg": truth["bearings_deg"][1],
                   "true_delta_m": truth["relative_delays_m"][1],
                   "cn0_a_db_hz": truth["cn0_a_db_hz"], "cn0_b_db_hz": truth["cn0_b_db_hz"]}
            for method in ("direct_music", "fbss_music"):
                item = result[method]
                row[f"{method}_angle_rmse_deg"] = item["angle_rmse_deg"]
                row[f"{method}_delay_error_m"] = item["delay_error_m"]
                row[f"{method}_success"] = int(item["success"])
            rows.append(row)
    finally:
        KNOWN_HALF_PLANE = original_half_plane
    csv_path = output_dir / "随机圆域MUSIC与FBSS逐点结果.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    summary = {method: float(np.mean([row[f"{method}_success"] for row in rows]))
               for method in ("direct_music", "fbss_music")}
    summary.update({"receiver_count": len(rows), "radius_m": RANDOM_RADIUS_M,
                    "center_mode": RANDOM_CENTER_MODE})
    (output_dir / "随机圆域MUSIC与FBSS摘要.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharex=True, sharey=True)
    for axis, method, title in zip(axes, ("direct_music", "fbss_music"),
                                   ("直接 MUSIC", "前后向空间平滑 + MUSIC")):
        success = np.array([row[f"{method}_success"] for row in rows], dtype=bool)
        axis.scatter(points[~success, 0], points[~success, 1], c="#D1495B", marker="x", label="失败")
        axis.scatter(points[success, 0], points[success, 1], c="#2A9D8F", marker="o", label="成功")
        axis.scatter([TX_A_X_M, TX_B_X_M], [TX_A_Y_M, TX_B_Y_M], marker="^", s=100,
                     c="black", label="发射天线")
        axis.set_aspect("equal"); axis.grid(True); axis.set_title(f"{title}：{summary[method]:.1%}")
        axis.set_xlabel("X / m"); axis.legend()
    axes[0].set_ylabel("Y / m")
    fig.tight_layout(); fig.savefig(output_dir / "随机圆域MUSIC与FBSS成功位置.png", dpi=180)
    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close(fig)
    return summary


def main():
    configure_font()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if EXPERIMENT_MODE in ("fixed", "both"):
        fixed = run_fixed(OUTPUT_DIR)
        print("固定点 direct MUSIC:", fixed["direct_music"])
        print("固定点 FBSS-MUSIC:", fixed["fbss_music"])
        print("物理量:", fixed["truth"])
        if ENABLE_RELATIVE_PHASE_SWEEP:
            phase_rows = run_phase_sweep(OUTPUT_DIR)
            print("相位扫描 FBSS 成功率:",
                  np.mean([row["fbss_music_success"] for row in phase_rows]))
        if ENABLE_CN0_SWEEP:
            cn0_rows = run_cn0_sweep(OUTPUT_DIR)
            for level in sorted(set(row["actual_cn0_a_db_hz"] for row in cn0_rows)):
                selected = [row for row in cn0_rows if row["actual_cn0_a_db_hz"] == level]
                print(f"C/N0={level:.1f} dB-Hz: FBSS success="
                      f"{np.mean([row['fbss_music_success'] for row in selected]):.1%}")
    if EXPERIMENT_MODE in ("random", "both"):
        print("随机圆域:", run_random(OUTPUT_DIR))


if __name__ == "__main__":
    main()

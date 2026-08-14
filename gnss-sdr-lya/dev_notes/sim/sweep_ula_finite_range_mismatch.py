#!/usr/bin/env python3
"""扫描四阵元 ULA 的球面波/有限距离流形失配，不与功率或时延变化混在一起。"""

from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import csv
import os

import matplotlib.pyplot as plt
import numpy as np

import ula_gnss_waveform_fbss_lab as lab


# ======================== 用户可修改实验参数区 ========================

# A 路到阵列中心的距离，单位 m。B 路按基准几何同比例拉远，两个真实方位保持不变。
# 这会同比例改变两发射源间距，因此是流形失配隔离实验，不是固定 20 m 停车场位置扫描。
A_DISTANCE_M = (2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0, 50.0)
# 每个距离的独立热噪声重复次数。30 用于预分析；正式报告建议 100。
MONTE_CARLO_RUNS = 30
# 距离点可独立并行。内存紧张时改成 1；一般桌面机使用 4 个进程较稳妥。
PARALLEL_WORKERS = min(4, os.cpu_count() or 1)
# 两路阵列中心接收功率比 B/A；0 dB 是公平资格测试，不代表真实停车场功率分布。
RECEIVED_POWER_RATIO_DB = 0.0
# A 路实际 C/N0；B 路为本值加上 RECEIVED_POWER_RATIO_DB。
ACTUAL_CN0_A_DB_HZ = 45.0
# 固定两路有效路径差，避免拉远发射源时把码相关峰位置也一并改变。
FIXED_RELATIVE_DELAY_M = 15.615528128088307
# 用馈线差补偿几何路径差。共同长度不影响结果，只需保证所有距离下 B 馈线仍为正值。
REFERENCE_CABLE_A_M = 200.0
OUTPUT_DIR = Path("dev_notes/sim/results/ula_b2a_finite_range_sweep")
# 长批处理默认只保存图片，避免最后一个图窗阻塞自动运行；本地交互查看时改为 True。
SHOW_FIGURE = False


def wilson_interval(success_count, sample_count):
    z = 1.959963984540054
    rate = success_count / sample_count
    denominator = 1.0 + z * z / sample_count
    center = (rate + z * z / (2.0 * sample_count)) / denominator
    half = z * np.sqrt(rate * (1.0 - rate) / sample_count
                       + z * z / (4.0 * sample_count ** 2)) / denominator
    return rate, max(0.0, center - half), min(1.0, center + half)


def scaled_geometry(a_distance_m):
    receiver = np.array([lab.RECEIVER_X_M, lab.RECEIVER_Y_M], dtype=float)
    tx_a = np.array([lab.TX_A_X_M, lab.TX_A_Y_M], dtype=float)
    tx_b = np.array([lab.TX_B_X_M, lab.TX_B_Y_M], dtype=float)
    base_a_distance = np.linalg.norm(tx_a - receiver)
    scale = a_distance_m / base_a_distance
    return receiver, receiver + scale * (tx_a - receiver), receiver + scale * (tx_b - receiver)


def phase_mismatch_deg(receiver, transmitter, positions):
    """精确球面波相位减去最佳同方位平面波相位，返回峰峰值和 RMS。"""
    vector = transmitter - receiver
    center_range = np.linalg.norm(vector)
    direction = vector / center_range
    exact = -2.0 * np.pi * lab.CARRIER_HZ * (
        np.linalg.norm(transmitter - (receiver + positions), axis=1) - center_range
    ) / lab.C_MPS
    plane = 2.0 * np.pi * lab.CARRIER_HZ * (positions @ direction) / lab.C_MPS
    residual = np.unwrap(exact - plane)
    residual -= np.mean(residual)
    degrees = np.degrees(residual)
    return float(np.ptp(degrees)), float(np.sqrt(np.mean(degrees ** 2)))


def configure_geometry(a_distance_m):
    receiver, tx_a, tx_b = scaled_geometry(a_distance_m)
    range_a = float(np.linalg.norm(tx_a - receiver))
    range_b = float(np.linalg.norm(tx_b - receiver))
    cable_b = (REFERENCE_CABLE_A_M + lab.CABLE_VELOCITY_FACTOR
               * (FIXED_RELATIVE_DELAY_M - (range_b - range_a)))
    if cable_b <= 0.0:
        raise ValueError("REFERENCE_CABLE_A_M is too short for this distance sweep")
    lab.TX_A_X_M, lab.TX_A_Y_M = tx_a
    lab.TX_B_X_M, lab.TX_B_Y_M = tx_b
    lab.CABLE_A_LENGTH_M = REFERENCE_CABLE_A_M
    lab.CABLE_B_LENGTH_M = cable_b
    return receiver, range_a, range_b, cable_b


def simulate_one(task):
    distance_index, a_distance, run = task
    lab.SPATIAL_WAVE_MODEL = "spherical"
    receiver, range_a, range_b, cable_b = configure_geometry(a_distance)
    positions = lab.ula_positions_m()
    tx_a = np.array([lab.TX_A_X_M, lab.TX_A_Y_M])
    tx_b = np.array([lab.TX_B_X_M, lab.TX_B_Y_M])
    mismatch_a = phase_mismatch_deg(receiver, tx_a, positions)
    mismatch_b = phase_mismatch_deg(receiver, tx_b, positions)
    correlators, taps, array_positions, truth = lab.simulate_correlators(
        receiver,
        np.random.default_rng(lab.RANDOM_SEED + 30000 + distance_index * 1000 + run),
        received_power_ratio_db=RECEIVED_POWER_RATIO_DB,
        actual_cn0_a_db_hz=ACTUAL_CN0_A_DB_HZ)
    result = lab.process_methods(correlators, taps, array_positions, truth)["fbss_music"]
    doa_success = (len(result["angle_errors_deg"]) == 2
                   and max(result["angle_errors_deg"]) <= lab.ANGLE_TOLERANCE_DEG)
    return {
        "a_distance_m": range_a,
        "b_distance_m": range_b,
        "relative_delay_m": truth["relative_delays_m"][1],
        "cable_b_m": cable_b,
        "phase_mismatch_a_p2p_deg": mismatch_a[0],
        "phase_mismatch_a_rms_deg": mismatch_a[1],
        "phase_mismatch_b_p2p_deg": mismatch_b[0],
        "phase_mismatch_b_rms_deg": mismatch_b[1],
        "run": run + 1,
        "bearing_a_deg": result["estimated_bearings_deg"][0],
        "bearing_b_deg": result["estimated_bearings_deg"][1],
        "angle_rmse_deg": result["angle_rmse_deg"],
        "doa_success": int(doa_success),
    }


def plot_summary(summary):
    distances = np.array([row["a_distance_m"] for row in summary])
    rates = np.array([row["success_rate"] for row in summary])
    lows = np.array([row["wilson95_low"] for row in summary])
    highs = np.array([row["wilson95_high"] for row in summary])
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    error_low = np.maximum(rates - lows, 0.0)
    error_high = np.maximum(highs - rates, 0.0)
    axes[0].errorbar(distances, rates, yerr=[error_low, error_high],
                     marker="o", capsize=3)
    axes[0].set_xscale("log"); axes[0].set_ylim(-0.05, 1.05)
    axes[0].set_title("球面波条件下 FBSS DOA 成功率")
    axes[0].set_xlabel("A 路距离 / m"); axes[0].set_ylabel("成功率（Wilson 95% CI）")
    axes[1].plot(distances, [row["median_angle_rmse_deg"] for row in summary],
                 marker="o", label="中位数")
    axes[1].plot(distances, [row["p95_angle_rmse_deg"] for row in summary],
                 marker="s", label="95 分位")
    axes[1].set_xscale("log"); axes[1].set_yscale("log")
    axes[1].set_title("两路角度 RMSE"); axes[1].set_xlabel("A 路距离 / m")
    axes[1].set_ylabel("角度 RMSE / deg"); axes[1].legend()
    axes[2].plot(distances, [row["phase_mismatch_a_p2p_deg"] for row in summary],
                 marker="o", label="A 路")
    axes[2].plot(distances, [row["phase_mismatch_b_p2p_deg"] for row in summary],
                 marker="s", label="B 路")
    axes[2].set_xscale("log"); axes[2].set_yscale("log")
    axes[2].set_title("球面波相对平面波的相位失配")
    axes[2].set_xlabel("A 路距离 / m"); axes[2].set_ylabel("阵元残差峰峰值 / deg")
    axes[2].legend()
    for axis in axes:
        axis.grid(True, which="both")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "有限距离FBSS失配扫描.png", dpi=180)
    if SHOW_FIGURE:
        plt.show()
    else:
        plt.close(fig)


def run_sweep():
    lab.configure_font()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tasks = [(distance_index, distance, run)
             for distance_index, distance in enumerate(A_DISTANCE_M)
             for run in range(MONTE_CARLO_RUNS)]
    if PARALLEL_WORKERS == 1:
        rows = [simulate_one(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            rows = list(executor.map(simulate_one, tasks))

    raw_path = OUTPUT_DIR / "有限距离逐次结果.csv"
    with raw_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    summary = []
    for distance in A_DISTANCE_M:
        selected = [row for row in rows if np.isclose(row["a_distance_m"], distance)]
        count = sum(row["doa_success"] for row in selected)
        rate, low, high = wilson_interval(count, len(selected))
        errors = np.array([row["angle_rmse_deg"] for row in selected])
        summary.append({
            "a_distance_m": distance,
            "b_distance_m": selected[0]["b_distance_m"],
            "phase_mismatch_a_p2p_deg": selected[0]["phase_mismatch_a_p2p_deg"],
            "phase_mismatch_b_p2p_deg": selected[0]["phase_mismatch_b_p2p_deg"],
            "success_count": count,
            "run_count": len(selected),
            "success_rate": rate,
            "wilson95_low": low,
            "wilson95_high": high,
            "median_angle_rmse_deg": float(np.median(errors)),
            "p95_angle_rmse_deg": float(np.percentile(errors, 95)),
        })
    summary_path = OUTPUT_DIR / "有限距离汇总.csv"
    with summary_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)

    plot_summary(summary)
    return summary


if __name__ == "__main__":
    for item in run_sweep():
        print(item)

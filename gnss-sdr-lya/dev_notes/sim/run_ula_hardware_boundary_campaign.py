#!/usr/bin/env python3
"""四阵元 B2a ULA 硬件到货前边界 campaign：角差、功率差和通道误差。"""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import csv
import os

import matplotlib.pyplot as plt
import numpy as np

import sweep_ula_finite_range_mismatch as finite_range
import ula_gnss_waveform_fbss_lab as lab


# ======================== 用户可修改实验参数区 ========================

ENABLED_GROUPS = ("angle", "power", "phase", "gain")
ANGLE_DIFFERENCE_DEG = (90.0, 60.0, 40.0, 30.0, 20.0, 10.0, 5.0)
POWER_RATIO_DB = (0.0, -3.0, -6.0, -10.0, -15.0)  # B 路相对 A 路接收功率
CHANNEL_PHASE_RMS_DEG = (0.0, 1.0, 3.0, 5.0, 10.0)
CHANNEL_GAIN_RMS_DB = (0.0, 0.2, 0.5, 1.0)
MONTE_CARLO_RUNS = 30  # 预分析 30；正式论文曲线建议 100
PARALLEL_WORKERS = min(4, os.cpu_count() or 1)

# 受控共同条件：两源等距离，角差以 270°（阵列负 Y 侧正侧向）为中心对称展开。
SOURCE_DISTANCE_M = 20.0
BEARING_CENTER_DEG = 270.0
BASELINE_ANGLE_DIFFERENCE_DEG = 60.0
ACTUAL_CN0_A_DB_HZ = 45.0
FIXED_RELATIVE_DELAY_M = 15.615528128088307
REFERENCE_CABLE_A_M = 100.0
OUTPUT_DIR = Path("dev_notes/sim/results/ula_b2a_hardware_boundary_campaign")
SHOW_FIGURE = False


def source_xy(receiver, distance_m, bearing_deg):
    bearing = np.radians(bearing_deg)
    return receiver + distance_m * np.array([np.cos(bearing), np.sin(bearing)])


def configure_scene(angle_difference_deg, phase_error_deg, gain_error_db):
    receiver = np.array([0.0, 0.0])
    bearings = (BEARING_CENTER_DEG - angle_difference_deg / 2.0,
                BEARING_CENTER_DEG + angle_difference_deg / 2.0)
    tx_a = source_xy(receiver, SOURCE_DISTANCE_M, bearings[0])
    tx_b = source_xy(receiver, SOURCE_DISTANCE_M, bearings[1])
    lab.TX_A_X_M, lab.TX_A_Y_M = tx_a
    lab.TX_B_X_M, lab.TX_B_Y_M = tx_b
    lab.CABLE_A_LENGTH_M = REFERENCE_CABLE_A_M
    lab.CABLE_B_LENGTH_M = (REFERENCE_CABLE_A_M
                            + lab.CABLE_VELOCITY_FACTOR * FIXED_RELATIVE_DELAY_M)
    lab.SPATIAL_WAVE_MODEL = "spherical"
    lab.KNOWN_HALF_PLANE = "negative_y"
    lab.CHANNEL_PHASE_ERROR_DEG_RMS = phase_error_deg
    lab.CHANNEL_GAIN_ERROR_DB_RMS = gain_error_db
    return receiver, bearings


def task_condition(group, level):
    angle = BASELINE_ANGLE_DIFFERENCE_DEG
    power = 0.0
    phase = 0.0
    gain = 0.0
    if group == "angle":
        angle = level
    elif group == "power":
        power = level
    elif group == "phase":
        phase = level
    elif group == "gain":
        gain = level
    else:
        raise ValueError(f"unknown campaign group: {group}")
    return angle, power, phase, gain


def centered_error_metrics(values):
    values = np.asarray(values, dtype=float)
    residual = values - np.mean(values)
    return float(np.sqrt(np.mean(residual ** 2))), float(np.max(abs(residual)))


def padded_pair(values):
    values = list(values)
    return tuple((values + [float("nan"), float("nan")])[:2])


def simulate_one(task):
    task_index, group, level, run = task
    angle, power, phase, gain = task_condition(group, level)
    receiver, bearings = configure_scene(angle, phase, gain)
    correlators, taps, positions, truth = lab.simulate_correlators(
        receiver,
        np.random.default_rng(lab.RANDOM_SEED + 50000 + task_index * 1000 + run),
        received_power_ratio_db=power,
        actual_cn0_a_db_hz=ACTUAL_CN0_A_DB_HZ)
    result = lab.process_methods(correlators, taps, positions, truth)["fbss_music"]
    estimated_bearings = padded_pair(result["estimated_bearings_deg"])
    doa_success = (len(result["angle_errors_deg"]) == 2
                   and max(result["angle_errors_deg"]) <= lab.ANGLE_TOLERANCE_DEG)
    phase_realized = centered_error_metrics(truth["channel_phase_error_deg"])
    gain_realized = centered_error_metrics(truth["channel_gain_error_db"])
    delay_error = (float("nan") if result["delay_error_m"] is None
                   else result["delay_error_m"])
    full_success = bool(doa_success and np.isfinite(delay_error)
                        and abs(delay_error) <= lab.DELAY_TOLERANCE_M)
    return {
        "group": group,
        "level": level,
        "run": run + 1,
        "true_angle_difference_deg": angle,
        "true_bearing_a_deg": bearings[0],
        "true_bearing_b_deg": bearings[1],
        "received_power_ratio_db": power,
        "cn0_a_db_hz": truth["cn0_a_db_hz"],
        "cn0_b_db_hz": truth["cn0_b_db_hz"],
        "configured_phase_rms_deg": phase,
        "realized_phase_rms_deg": phase_realized[0],
        "realized_phase_max_deg": phase_realized[1],
        "configured_gain_rms_db": gain,
        "realized_gain_rms_db": gain_realized[0],
        "realized_gain_max_db": gain_realized[1],
        "estimated_peak_count": len(result["estimated_bearings_deg"]),
        "estimator_state": result["state"],
        "estimated_bearing_a_deg": estimated_bearings[0],
        "estimated_bearing_b_deg": estimated_bearings[1],
        "angle_rmse_deg": result["angle_rmse_deg"],
        "estimated_delta_m": (float("nan") if result["estimated_delta_m"] is None
                              else result["estimated_delta_m"]),
        "delay_error_m": delay_error,
        "doa_success": int(doa_success),
        "full_success": int(full_success),
    }


def group_levels():
    definitions = {
        "angle": ANGLE_DIFFERENCE_DEG,
        "power": POWER_RATIO_DB,
        "phase": CHANNEL_PHASE_RMS_DEG,
        "gain": CHANNEL_GAIN_RMS_DB,
    }
    return [(group, level) for group in ENABLED_GROUPS for level in definitions[group]]


def summarize(rows):
    output = []
    for group, level in group_levels():
        selected = [row for row in rows if row["group"] == group
                    and np.isclose(row["level"], level)]
        success_count = sum(row["doa_success"] for row in selected)
        full_success_count = sum(
            row.get("full_success", int(
                row["doa_success"] and np.isfinite(row["delay_error_m"])
                and abs(row["delay_error_m"]) <= lab.DELAY_TOLERANCE_M))
            for row in selected)
        unresolved_count = sum(row["estimator_state"] == "UNRESOLVED_ONE_PEAK"
                               for row in selected)
        rate, low, high = finite_range.wilson_interval(success_count, len(selected))
        full_rate, full_low, full_high = finite_range.wilson_interval(
            full_success_count, len(selected))
        errors = np.array([row["angle_rmse_deg"] for row in selected])
        finite_errors = errors[np.isfinite(errors)]
        output.append({
            "group": group,
            "level": level,
            "success_count": success_count,
            "full_success_count": full_success_count,
            "run_count": len(selected),
            "unresolved_one_peak_count": unresolved_count,
            "finite_angle_estimate_count": len(finite_errors),
            "success_rate": rate,
            "wilson95_low": low,
            "wilson95_high": high,
            "full_success_rate": full_rate,
            "full_wilson95_low": full_low,
            "full_wilson95_high": full_high,
            "median_angle_rmse_deg": (float(np.median(finite_errors))
                                      if len(finite_errors) else float("nan")),
            "p95_angle_rmse_deg": (float(np.percentile(finite_errors, 95))
                                   if len(finite_errors) else float("nan")),
        })
    return output


def plot_summary(summary):
    lab.configure_font()
    definitions = (
        ("angle", "两源角度差", "Δθ / deg"),
        ("power", "弱路功率差", "B/A 接收功率 / dB"),
        ("phase", "通道相位误差", "配置相位误差 RMS / deg"),
        ("gain", "通道增益误差", "配置增益误差 RMS / dB"),
    )
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for axis, (group, title, xlabel) in zip(axes.flat, definitions):
        rows = [row for row in summary if row["group"] == group]
        x = np.array([row["level"] for row in rows])
        rate = np.array([row["success_rate"] for row in rows])
        low = np.array([row["wilson95_low"] for row in rows])
        high = np.array([row["wilson95_high"] for row in rows])
        full_rate = np.array([row["full_success_rate"] for row in rows])
        full_low = np.array([row["full_wilson95_low"] for row in rows])
        full_high = np.array([row["full_wilson95_high"] for row in rows])
        axis.errorbar(
            x, rate,
            yerr=[np.maximum(rate - low, 0.0), np.maximum(high - rate, 0.0)],
            marker="o", capsize=3, label="DOA 双峰")
        axis.errorbar(
            x, full_rate,
            yerr=[np.maximum(full_rate - full_low, 0.0),
                  np.maximum(full_high - full_rate, 0.0)],
            marker="s", capsize=3, label="DOA + 时延")
        axis.set_ylim(-0.05, 1.05); axis.grid(True)
        axis.set_title(title); axis.set_xlabel(xlabel); axis.set_ylabel("成功率")
        axis.legend(loc="lower right")
    fig.suptitle("四阵元 B2a ULA 硬件到货前边界（每点 30 次）")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "硬件边界campaign.png", dpi=180)
    if SHOW_FIGURE:
        plt.show()
    else:
        plt.close(fig)


def run_campaign():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conditions = group_levels()
    tasks = [(index, group, level, run)
             for index, (group, level) in enumerate(conditions)
             for run in range(MONTE_CARLO_RUNS)]
    if PARALLEL_WORKERS == 1:
        rows = [simulate_one(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            rows = list(executor.map(simulate_one, tasks))
    with (OUTPUT_DIR / "硬件边界逐次结果.csv").open(
            "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    summary = summarize(rows)
    with (OUTPUT_DIR / "硬件边界汇总.csv").open(
            "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary[0].keys())
        writer.writeheader(); writer.writerows(summary)
    plot_summary(summary)
    return summary


if __name__ == "__main__":
    for item in run_campaign():
        print(item)

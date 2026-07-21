#!/usr/bin/env python3
"""acq_health.py — 判定"捕获是否干净"，而不只是"positive_acq 是否为 1"。

背景（2026-07-18）：现场 3D 谱面是一片噪声草皮、ratio≈4dB、主峰码相位逐 dump 乱跳，
说明根本没干净捕获。此脚本对一批 dump 做聚合判定，直接给 CLEAN / MARGINAL / NOISE 结论。

判定用三个量（比单看 positive_acq 可靠得多）：
  1) 门限余量  margin_db = 10*log10(test_statistic / threshold)：主峰高出 CFAR 门限多少。
  2) 峰噪比    peak2floor_db = 10*log10(grid_max / grid_median)：主峰高出噪声底多少（有 acq_grid 时）。
  3) 主峰码相位稳定度 code_phase_std_chips：真信号在多份 dump 里码相位稳定；噪声乱跳。

用法：
  python3 acq_health.py "gps_l5_acq_*_sat_18.mat" --code-length 10230
  python3 acq_health.py "bds_b1i_acq_*_sat_9.mat"  --code-length 2046
"""
import argparse
import glob
import sys

import h5py
import numpy as np


def scalar(h, key, default=np.nan):
    if key in h:
        return float(np.array(h[key]).reshape(-1)[0])
    return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern", help='dump glob, e.g. "gps_l5_acq_*_sat_18.mat"')
    ap.add_argument("--code-length", type=float, required=True,
                    help="码长 chips：GPS L5=10230, B1I=2046, GPS L1=1023")
    ap.add_argument("--max-files", type=int, default=0, help="最多分析几份（0=全部）")
    ap.add_argument("--clean-margin-db", type=float, default=10.0,
                    help="判 CLEAN 所需的最小门限余量 dB（默认 10）")
    ap.add_argument("--clean-stable-chips", type=float, default=1.0,
                    help="判 CLEAN 所需的主峰码相位 std 上限 chips（默认 1.0）")
    args = ap.parse_args()

    files = sorted(glob.glob(args.pattern))
    if args.max_files > 0:
        files = files[:args.max_files]
    if not files:
        print("NO_DUMPS matched pattern: %s" % args.pattern)
        sys.exit(2)

    rows = []
    for f in files:
        try:
            with h5py.File(f, "r") as h:
                pos = scalar(h, "positive_acq", 0.0)
                test = scalar(h, "test_statistic")
                thr = scalar(h, "threshold")
                has2 = scalar(h, "has_second_peak", 0.0)
                ratio = scalar(h, "peak_ratio")  # main/second（线性）
                dopp = scalar(h, "acq_doppler_hz")

                # 主峰码相位：优先直接从 acq_grid 找 argmax（最可靠），否则退回 acq_delay_samples。
                code_chip = np.nan
                peak2floor_db = np.nan
                if "acq_grid" in h:
                    grid = np.array(h["acq_grid"], dtype=float)
                    if grid.ndim == 2 and grid.size > 0:
                        # 约定 grid[doppler, code]；若反了也不影响 argmax 的 code 轴取法
                        code_len_samples = grid.shape[1]
                        spc = code_len_samples / args.code_length  # 每 chip 多少样点
                        flat_idx = int(np.argmax(grid))
                        _, code_idx = np.unravel_index(flat_idx, grid.shape)
                        code_chip = code_idx / spc if spc > 0 else np.nan
                        gmax = float(grid.max())
                        gmed = float(np.median(grid))
                        if gmed > 0 and gmax > 0:
                            peak2floor_db = 10.0 * np.log10(gmax / gmed)
                if np.isnan(code_chip) and "acq_delay_samples" in h and "acq_grid" in h:
                    pass  # 已在上面处理

                margin_db = (10.0 * np.log10(test / thr)
                             if (np.isfinite(test) and np.isfinite(thr) and test > 0 and thr > 0)
                             else np.nan)
                ratio_db = (10.0 * np.log10(ratio)
                            if (np.isfinite(ratio) and ratio > 0) else np.nan)

                rows.append(dict(f=f.split("/")[-1], pos=pos, test=test, thr=thr,
                                 margin_db=margin_db, peak2floor_db=peak2floor_db,
                                 code_chip=code_chip, has2=has2, ratio_db=ratio_db,
                                 dopp=dopp))
        except Exception as e:  # noqa: BLE001
            print("SKIP %s: %s" % (f, e))

    if not rows:
        print("NO_READABLE_DUMPS")
        sys.exit(2)

    n = len(rows)
    pos_rate = np.mean([r["pos"] for r in rows])
    margins = np.array([r["margin_db"] for r in rows if np.isfinite(r["margin_db"])])
    p2f = np.array([r["peak2floor_db"] for r in rows if np.isfinite(r["peak2floor_db"])])
    chips = np.array([r["code_chip"] for r in rows if np.isfinite(r["code_chip"])])
    has2_rate = np.mean([r["has2"] for r in rows])

    def med(a):
        return float(np.median(a)) if a.size else float("nan")

    code_std = float(np.std(chips)) if chips.size >= 2 else float("nan")

    print("=" * 72)
    print("acq_health: %d dumps | pattern=%s" % (n, args.pattern))
    print("-" * 72)
    for r in rows[:12]:
        print("%-42s pos=%.0f margin=%5.1fdB p2f=%5.1fdB code=%8.1fchip has2=%.0f"
              % (r["f"], r["pos"], r["margin_db"], r["peak2floor_db"],
                 r["code_chip"], r["has2"]))
    if n > 12:
        print("... (%d more)" % (n - 12))
    print("-" * 72)
    print("positive_rate      = %.2f" % pos_rate)
    print("margin_db          median=%.1f  min=%.1f  max=%.1f"
          % (med(margins), float(margins.min()) if margins.size else float('nan'),
             float(margins.max()) if margins.size else float('nan')))
    print("peak2floor_db      median=%.1f  (>~13 才算主峰明显立在噪底之上)" % med(p2f))
    print("code_phase_std     = %.2f chips  (真信号应 <~1；乱跳=噪声)" % code_std)
    print("has_second_peak_rate = %.2f" % has2_rate)

    # 综合判定
    clean = (pos_rate >= 0.8
             and np.isfinite(med(margins)) and med(margins) >= args.clean_margin_db
             and np.isfinite(code_std) and code_std <= args.clean_stable_chips)
    noise = ((np.isfinite(code_std) and code_std > 5.0)
             or (np.isfinite(med(margins)) and med(margins) < 3.0)
             or pos_rate < 0.2)
    verdict = "CLEAN" if clean else ("NOISE" if noise else "MARGINAL")
    print("-" * 72)
    print("VERDICT = %s" % verdict)
    if verdict == "NOISE":
        print("  → 没干净捕获。先查：频点(L5=1176.45MHz)、PRN(config vs 模拟器)、增益(削顶/欠量化)、")
        print("    天线口(RX2)、模拟器是否真发/共时钟、采样格式(gr_complex/10Msps)。不要先动多径算法。")
    elif verdict == "MARGINAL":
        print("  → 临界。稳链路/提增益/加 max_dwells 后复测，先把 VERDICT 顶到 CLEAN 再谈多径。")
    else:
        print("  → 主捕获干净，可进入单路假警基线(has2 应≈0)与双路多径测试。")
    print("=" * 72)


if __name__ == "__main__":
    main()

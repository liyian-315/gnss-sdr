#!/usr/bin/env python3
"""multipath_consistency.py — 时间一致性判据：真反射的 Δ 在连续 dump 里稳定，噪声乱跳。

背景（2026-07-18）：现场第二峰的 Δ 在整个 ±90chip 搜索窗里随机游走，说明报出的"第二峰"是
噪声最大点，不是反射。真多径的关键特征是**时间上稳定**——在很多 dump 里落在同一 Δ 附近。

本脚本读 run_b210_offline_multipath_test.sh 产出的 /tmp/<tag>_summary.tsv，
只取 positive_acq=1 && has2=1 的行，对 delta_chip 做聚类，找出最大的一致簇：
  - 簇内样本数 / 总有效样本数 = 一致率
  - 簇的 Δ 中位数、std（越小越像真多径）
据此给 CONSISTENT / SCATTERED 结论。SCATTERED = 当前"检出"不可信（噪声游走）。

用法：
  python3 multipath_consistency.py /tmp/gps_l5_prn18_twosim_1000m_summary.tsv \
      --chip-m 29.3 --tol-chips 1.0 --min-cluster 5
"""
import argparse
import sys

import numpy as np


def read_tsv(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        idx = {name: i for i, name in enumerate(header)}
        need = ["positive", "has2", "delta_chip", "delta_m"]
        for k in need:
            if k not in idx:
                raise SystemExit("summary.tsv 缺列 %s；实际列=%s" % (k, header))
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                continue
            try:
                rows.append(dict(
                    positive=int(float(parts[idx["positive"]])),
                    has2=int(float(parts[idx["has2"]])),
                    delta_chip=float(parts[idx["delta_chip"]]),
                    delta_m=float(parts[idx["delta_m"]]),
                    file=parts[idx.get("file", 0)],
                ))
            except (ValueError, IndexError):
                continue
    return rows


def largest_cluster(values, tol):
    """对一维值找最大的 ±tol 一致簇（贪心：以每个点为中心数邻居，取最多的）。"""
    if not len(values):
        return [], np.nan
    values = np.asarray(values, dtype=float)
    best_idx, best_center = [], np.nan
    for c in values:
        members = np.where(np.abs(values - c) <= tol)[0]
        if len(members) > len(best_idx):
            best_idx = members
            best_center = float(np.median(values[members]))
    return best_idx, best_center


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("summary_tsv")
    ap.add_argument("--chip-m", type=float, default=29.3, help="每 chip 多少米（L5≈29.3, B1I≈146.6）")
    ap.add_argument("--tol-chips", type=float, default=1.0, help="一致簇半径 chips")
    ap.add_argument("--min-cluster", type=int, default=5, help="判 CONSISTENT 所需最小簇样本数")
    ap.add_argument("--min-fraction", type=float, default=0.5, help="判 CONSISTENT 所需最小一致率")
    args = ap.parse_args()

    rows = read_tsv(args.summary_tsv)
    valid = [r for r in rows if r["positive"] == 1 and r["has2"] == 1 and np.isfinite(r["delta_chip"])]
    print("=" * 72)
    print("multipath_consistency: %s" % args.summary_tsv)
    print("总 dump=%d | positive&has2 有效=%d" % (len(rows), len(valid)))
    if len(valid) < 2:
        print("有效样本不足（<2）。先把主捕获做干净、第二峰门限标定好，再谈一致性。")
        print("VERDICT = INSUFFICIENT")
        sys.exit(0)

    deltas = np.array([r["delta_chip"] for r in valid], dtype=float)
    print("delta_chip: min=%.1f max=%.1f std(全体)=%.1f  → 全体 std 大=游走"
          % (deltas.min(), deltas.max(), float(np.std(deltas))))

    idx, center = largest_cluster(deltas, args.tol_chips)
    frac = len(idx) / len(valid)
    cluster_vals = deltas[idx]
    cl_std = float(np.std(cluster_vals)) if len(idx) >= 2 else 0.0
    center_m = center * args.chip_m

    print("-" * 72)
    print("最大一致簇：样本=%d/%d (一致率=%.2f)  中心Δ=%.2f chip = %.1f m  簇内std=%.2f chip"
          % (len(idx), len(valid), frac, center, center_m, cl_std))

    consistent = (len(idx) >= args.min_cluster and frac >= args.min_fraction)
    verdict = "CONSISTENT" if consistent else "SCATTERED"
    print("-" * 72)
    print("VERDICT = %s" % verdict)
    if verdict == "CONSISTENT":
        print("  → 存在稳定第二径，估计 |Δ|≈%.1f m。可当作可信多径检出。" % abs(center_m))
    else:
        print("  → 第二峰随机游走，当前非可信多径。先收窄 multipath_max_delay_chips、")
        print("    提高 max_dwells/门限、或改导线注入已知延迟；近距(<~2chip)则须转跟踪域多相关器。")
    print("=" * 72)


if __name__ == "__main__":
    main()

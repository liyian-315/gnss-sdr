#!/usr/bin/env python3
"""3D 谱峰面：Doppler × 码相位 × |corr|^2。干净信号下应见一根尖刺立在噪声平面上。
用法：
  python3 dev_notes/sim/plot_acq_3d.py bds_b1i_acq_C_B1_ch_0_1_sat_9.mat --code-length 2046
生成同名 _3d.png。
"""
import argparse
import glob
import sys
from pathlib import Path

import h5py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (注册 3d 投影)


def scalar(h, key, default=float("nan")):
    return float(np.array(h[key]).ravel()[0]) if key in h else default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("matfile", help=".mat 文件或 glob（取第一个匹配）")
    ap.add_argument("--code-length", type=float, default=2046.0, help="码长(chips)：B1I=2046, GPS L1=1023")
    ap.add_argument("--code-unit", choices=["chip", "sample"], default="chip", help="X 轴单位")
    ap.add_argument("--max-code-points", type=int, default=700, help="码相位方向最多绘制点数，避免 PNG 过慢")
    ap.add_argument("--elev", type=float, default=35.0, help="3D 视角 elevation")
    ap.add_argument("--azim", type=float, default=-60.0, help="3D 视角 azimuth")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    files = sorted(glob.glob(args.matfile))
    if not files:
        print("没找到匹配文件:", args.matfile, file=sys.stderr)
        return 2

    mat_path = Path(files[0])
    with h5py.File(mat_path, "r") as h:
        if "acq_grid" not in h:
            print("文件里没有 acq_grid，可用字段:", sorted(h.keys()), file=sys.stderr)
            return 2

        g = np.array(h["acq_grid"], dtype=np.float64)
        if g.ndim != 2:
            print("acq_grid 不是二维矩阵，shape=%s" % (g.shape,), file=sys.stderr)
            return 2

        # 保证 g 为 (doppler, code)：code 维通常远大于 doppler 维。
        if g.shape[0] > g.shape[1]:
            g = g.T
        ndop, ncode = g.shape

        dmax = scalar(h, "doppler_max", 5000.0)
        dstep = scalar(h, "doppler_step", 250.0)
        has2 = scalar(h, "has_second_peak", 0.0)
        sec_delay_samples = scalar(h, "acq_delay_samples_2")
        peak_ratio = scalar(h, "peak_ratio")

    spc = ncode / args.code_length
    if args.code_unit == "chip":
        code = np.arange(ncode) / spc
        xlab = "Code phase [chip]"
    else:
        code = np.arange(ncode, dtype=float)
        xlab = "Code phase [samples]"
    dop = -dmax + dstep * np.arange(ndop)

    step = max(1, ncode // max(1, args.max_code_points))
    C, D = np.meshgrid(code[::step], dop)
    Z = g[:, ::step]

    drow = int(np.argmax(g.max(axis=1)))
    pcol = int(np.argmax(g[drow]))
    peak_x = pcol / spc if args.code_unit == "chip" else float(pcol)
    peak_dop = dop[drow] if drow < len(dop) else float("nan")

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(C, D, Z, cmap="jet", linewidth=0, antialiased=False, rstride=1, cstride=1)
    ax.scatter([peak_x], [peak_dop], [g[drow, pcol]], color="red", s=45, marker="x", label="main peak")

    if has2 == 1 and not np.isnan(sec_delay_samples):
        sec_col = int(round(sec_delay_samples))
        if 0 <= sec_col < ncode:
            sec_x = sec_col / spc if args.code_unit == "chip" else float(sec_col)
            ax.scatter([sec_x], [peak_dop], [g[drow, sec_col]], color="white", s=36, marker="o",
                       edgecolors="black", label="second path")

    ax.set_xlabel(xlab)
    ax.set_ylabel("Doppler [Hz]")
    ax.set_zlabel("|corr|^2")
    title = "3D acq grid | peak @ %.1f %s, %.0f Hz | grid=%s" % (
        peak_x,
        "chip" if args.code_unit == "chip" else "sample",
        peak_dop,
        g.shape,
    )
    if has2 == 1 and peak_ratio > 0:
        title += " | has2=1 ratio=%.1f dB" % (10.0 * np.log10(peak_ratio))
    ax.set_title(title)
    ax.view_init(elev=args.elev, azim=args.azim)
    ax.legend(loc="upper right")

    out = Path(args.out) if args.out else mat_path.with_name(mat_path.stem + "_3d.png")
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    print("saved:", out)
    print("peak: %.1f %s, %.0f Hz | grid shape=%s | spc=%.3f samples/chip | has2=%.0f" %
          (peak_x, "chip" if args.code_unit == "chip" else "sample", peak_dop, g.shape, spc, has2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

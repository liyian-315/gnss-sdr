#!/usr/bin/env python3
"""
画捕获相关面(谱峰图) —— 从 .mat dump 读 acq_grid，出 PNG。
三张子图：① 2D 热图(多普勒×码相位) ② 峰值多普勒行的完整码相位切片 ③ 峰值附近放大(看主峰+第二峰)。

服务器上用（headless，存 PNG 不弹窗）：
  # 若没装 matplotlib：conda install -y -c conda-forge matplotlib
  python3 dev_notes/sim/plot_acq_grid.py bds_b1i_acq_C_B1_ch_0_1_sat_9.mat --code-length 2046
  # 支持 glob，取第一个匹配：
  python3 dev_notes/sim/plot_acq_grid.py "bds_b1i_acq_C_B1_ch_0_*_sat_9.mat" --code-length 2046
生成同名 .png，用 scp / VS Code / 图片查看器打开。
"""
import h5py, numpy as np, glob, argparse
import matplotlib
matplotlib.use("Agg")  # 无显示环境，存文件
import matplotlib.pyplot as plt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("matfile", help=".mat 文件或 glob（取第一个匹配）")
    ap.add_argument("--code-length", type=float, default=2046.0, help="码长(chips)：B1I=2046, GPS L1=1023")
    ap.add_argument("--zoom-chips", type=float, default=25.0, help="放大图的 ±码片范围")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    fs = sorted(glob.glob(args.matfile))
    if not fs:
        print("没找到匹配文件:", args.matfile); return
    f = fs[0]
    h = h5py.File(f, "r")
    g = np.array(h["acq_grid"], dtype=np.float64)

    def sc(k, d=0.0):
        return float(np.array(h[k]).ravel()[0]) if k in h else d
    dmax = sc("doppler_max", 5000.0)
    dstep = sc("doppler_step", 250.0)

    # 保证 g 为 (doppler, code)：code 维通常远大于 doppler 维
    if g.shape[0] > g.shape[1]:
        g = g.T
    ndop, ncode = g.shape
    spc = ncode / args.code_length            # 样点/码片
    chip_m = 2.99792458e8 / (args.code_length * 1000.0)

    # 找全局峰
    drow = int(np.argmax(g.max(axis=1)))
    pcol = int(np.argmax(g[drow]))
    peak_chip = pcol / spc
    peak_dop = -dmax + dstep * drow

    chips = np.arange(ncode) / spc
    dops = np.linspace(-dmax, dmax, ndop)

    fig, ax = plt.subplots(3, 1, figsize=(13, 12))
    # ① 2D 热图
    im = ax[0].imshow(g, aspect="auto", origin="lower", cmap="viridis",
                      extent=[chips[0], chips[-1], dops[0], dops[-1]])
    ax[0].plot(peak_chip, peak_dop, "rx", ms=12, mew=2)
    ax[0].set_xlabel("code phase [chip]"); ax[0].set_ylabel("doppler [Hz]")
    ax[0].set_title("2D acq grid  |  peak @ %.1f chip, %.0f Hz  |  grid=%s  1chip=%.1fm"
                    % (peak_chip, peak_dop, g.shape, chip_m))
    fig.colorbar(im, ax=ax[0])

    # ② 峰值多普勒行 完整码相位切片
    ax[1].plot(chips, g[drow], lw=0.6)
    ax[1].axvline(peak_chip, color="r", ls="--", lw=1)
    ax[1].set_xlabel("code phase [chip]"); ax[1].set_ylabel("|corr|^2")
    ax[1].set_title("peak doppler row (full)")

    # ③ 峰值附近放大（看主峰 + 第二峰/多径）
    lo = max(0.0, peak_chip - args.zoom_chips)
    hi = min(chips[-1], peak_chip + args.zoom_chips)
    m = (chips >= lo) & (chips <= hi)
    ax[2].plot(chips[m], g[drow][m], "-o", ms=2, lw=0.8)
    ax[2].axvline(peak_chip, color="r", ls="--", lw=1, label="main peak")
    ax[2].set_xlabel("code phase [chip]"); ax[2].set_ylabel("|corr|^2")
    ax[2].set_title("zoom ±%g chip (主峰 + 第二峰/多径)  1chip=%.1fm" % (args.zoom_chips, chip_m))
    ax[2].legend()

    out = args.out or (f.split("/")[-1].replace(".mat", "") + ".png")
    plt.tight_layout(); plt.savefig(out, dpi=110)
    print("saved:", out)
    print("peak: %.1f chip, %.0f Hz | grid shape=%s | spc=%.3f samples/chip" % (peak_chip, peak_dop, g.shape, spc))


if __name__ == "__main__":
    main()

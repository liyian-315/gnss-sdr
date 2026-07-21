#!/usr/bin/env python3
"""读 gnss-sdr 捕获 dump(.mat, acq_grid)，直接看相关函数剖面，判断近多径第二径。

不依赖 gnss-sdr 的 find_second_peak（它会抹掉主峰±1chip、易抓主峰肩）。
本工具把若干份网格非相干平均后，打印主峰附近各码片偏移的相对幅度(dB)，
并扫描 [+lo,+hi] chip 窗口内的局部极大值作为第二径候选，同时报正负side不对称度
（真多径在延迟侧，会让 + 侧高于 - 侧）。

用法:
  python3 l5_corr_profile.py --pattern '/tmp/l5off_acq*sat_18.mat' --code-length 10230 --last 8
"""
import argparse
import glob

import h5py
import numpy as np

C = 2.99792458e8


def load_grid(f):
    with h5py.File(f, "r") as h:
        g = np.array(h["acq_grid"], dtype=np.float64)
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", required=True)
    ap.add_argument("--code-length", type=float, default=10230.0, help="L5=10230, L1=1023")
    ap.add_argument("--last", type=int, default=8, help="非相干平均最后 N 份网格")
    ap.add_argument("--lo", type=float, default=0.4, help="第二径搜索起始 chip")
    ap.add_argument("--hi", type=float, default=6.0, help="第二径搜索结束 chip")
    args = ap.parse_args()

    chip_m = C / (args.code_length * 1000.0)
    files = sorted(glob.glob(args.pattern))
    if not files:
        print("no dumps match:", args.pattern)
        return
    grids = [load_grid(f) for f in files[-args.last:]]
    g = np.mean(grids, axis=0)
    if g.shape[0] > g.shape[1]:
        g = g.T  # -> (doppler, code), code 为较长轴
    nd, nfft = g.shape
    spc = nfft / args.code_length

    drow = int(np.argmax(g.max(axis=1)))
    prof = g[drow].astype(np.float64)
    pcol = int(np.argmax(prof))
    peak = prof[pcol]
    noise = np.median(prof)
    print("files=%d(avg last %d) grid=(%d dopp,%d code) spc=%.3f samp/chip 1chip=%.1fm"
          % (len(files), min(args.last, len(files)), nd, nfft, spc, chip_m))
    print("peak: dopp_row=%d/%d code_col=%d  peak/noise=%.1f dB" % (drow, nd, pcol, 10 * np.log10(peak / noise)))

    prof_c = np.roll(prof, nfft // 2 - pcol)
    center = nfft // 2

    def mag_at(choff):
        idx = int(round(center + choff * spc))
        if 0 <= idx < nfft:
            v = prof_c[idx] / peak
            return 10 * np.log10(v) if v > 0 else -99.0
        return float("nan")

    print("\nchip_off  meters   rel_dB   (correlation profile around main peak)")
    for ch in [-3, -2.5, -2, -1.7, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 1.7, 2, 2.5, 3, 3.5, 4, 5, 6]:
        d = mag_at(ch)
        bar = "#" * max(0, int((d + 30)))  # -30dB..0 -> 0..30 chars
        print("%+6.2f  %+7.1f  %6.1f  %s" % (ch, ch * chip_m, d, bar))

    # 正负 side 不对称（真多径在延迟侧）
    print("\n--- 延迟侧 vs 提前侧 不对称(真多径应为正) ---")
    for ch in [0.5, 1.0, 1.5, 1.7, 2.0, 2.5, 3.0]:
        print("  ±%.1f chip: delay=%+.1f dB  early=%+.1f dB  asym=%+.1f dB"
              % (ch, mag_at(ch), mag_at(-ch), mag_at(ch) - mag_at(-ch)))

    # 第二径候选：延迟侧局部极大
    print("\n--- 第二径候选(延迟侧局部极大, >-20dB) ---")
    lo = int(center + args.lo * spc)
    hi = int(center + args.hi * spc)
    seg = prof_c[lo:hi]
    found = False
    for i in range(1, len(seg) - 1):
        if seg[i] > seg[i - 1] and seg[i] >= seg[i + 1]:
            rel = seg[i] / peak
            if rel > 0.01:
                choff = (lo + i - center) / spc
                print("  +%.2f chip (%+.1f m)  %.1f dB" % (choff, choff * chip_m, 10 * np.log10(rel)))
                found = True
    if not found:
        print("  (延迟侧无显著局部极大)")


if __name__ == "__main__":
    main()

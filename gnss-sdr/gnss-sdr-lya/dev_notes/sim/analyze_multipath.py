#!/usr/bin/env python3
"""
通用多径分析脚本 —— 读捕获 dump(.mat)，报告每颗卫星的直射/第二径。
适用 GPS L1(码长1023) 与 BeiDou B1I(码长2046) 等，自动按码长换算码片/米。

用法:
  python3 analyze_multipath.py --pattern "bds_b1i_acq_*_sat_*.mat" --code-length 2046
  python3 analyze_multipath.py --pattern "gpsl1_2path_acq_*_sat_1.mat" --code-length 1023
"""
import h5py, numpy as np, glob, argparse

C = 2.99792458e8


def gv(h, k):
    return float(np.array(h[k]).ravel()[0]) if k in h else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", required=True, help="dump 文件 glob，如 'bds_b1i_acq_*_sat_*.mat'")
    ap.add_argument("--code-length", type=float, default=2046.0, help="码长(chips)：B1I=2046, GPS L1=1023")
    ap.add_argument("--max", type=int, default=30, help="最多显示多少份 dump")
    args = ap.parse_args()

    chip_m = C / (args.code_length * 1000.0)  # 码周期1ms → chip_rate=code_length*1000
    fs = sorted(glob.glob(args.pattern))
    print("匹配 dump: %d 份 | 码长=%g chips | 1 chip=%.1f m" % (len(fs), args.code_length, chip_m))
    if not fs:
        print("没找到 dump。检查 --pattern 和当前目录。")
        return

    print("\n%-28s %4s %8s %10s %10s %8s %8s" % ("dump", "has2", "主径chip", "第二径chip", "Δ延迟chip", "Δ米", "比值dB"))
    print("-" * 88)
    n_mp = 0
    for f in fs[:args.max]:
        h = h5py.File(f, "r")
        g = np.array(h["acq_grid"])                    # (doppler, code)
        spc = g.shape[1] / args.code_length            # 样点/码片
        has2 = gv(h, "has_second_peak")
        prn = gv(h, "PRN")
        d1 = gv(h, "acq_delay_samples")                # 交给跟踪的(主径, 或第二径若acquire_second_path)
        d2 = gv(h, "acq_delay_samples_2")
        pr = gv(h, "peak_ratio")
        # 从网格独立算主峰(稳健)
        drow = int(np.argmax(g.max(axis=1)))
        p1 = int(np.argmax(g[drow]))
        main_chip = p1 / spc
        sec_chip = (d2 / spc) if not np.isnan(d2) else float("nan")
        dchip = sec_chip - main_chip if not np.isnan(sec_chip) else float("nan")
        db = 10 * np.log10(pr) if (not np.isnan(pr) and pr > 0) else float("nan")
        tag = f.split("/")[-1]
        if len(tag) > 27:
            tag = "..." + tag[-24:]
        print("%-28s %4.0f %8.1f %10.1f %10.1f %8.0f %8.1f"
              % (tag, has2, main_chip, sec_chip, dchip, dchip * chip_m if not np.isnan(dchip) else float("nan"), db))
        if has2 == 1:
            n_mp += 1
    print("-" * 88)
    print("有第二径(has2=1)的 dump: %d / %d" % (n_mp, min(len(fs), args.max)))
    print("提示: Δ延迟为正=反射滞后直射(正常多径)；比值dB=主径比第二径强多少(越小反射越强)。")


if __name__ == "__main__":
    main()

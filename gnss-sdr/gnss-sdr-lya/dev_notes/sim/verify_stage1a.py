#!/usr/bin/env python3
# 验证 Stage 1a：检查捕获 dump 里新增的第二峰变量
import h5py, numpy as np, glob, sys

pat = sys.argv[1] if len(sys.argv) > 1 else "gpsl1_2path_acq_G_1C_ch_0_*_sat_1.mat"
fs = sorted(glob.glob(pat))
spc = 4000 / 1023.0
print("dump 份数:", len(fs))
print("=== 第二峰 dump 变量 ===")


def gv(h, k):
    return float(np.array(h[k]).ravel()[0]) if k in h else float("nan")


for f in fs[:5]:
    h = h5py.File(f, "r")
    tag = f.split("ch_0_")[1].replace("_sat_1.mat", "")
    has = gv(h, "has_second_peak")
    d1 = gv(h, "acq_delay_samples")
    d2 = gv(h, "acq_delay_samples_2")
    pr = gv(h, "peak_ratio")
    dop1 = gv(h, "acq_doppler_hz")
    dop2 = gv(h, "acq_doppler_hz_2")
    ts2 = gv(h, "test_statistic_2")
    print(f"  #{tag:>2}: has2={has:.0f}  "
          f"主峰={d1:6.0f}样({d1/spc:5.1f}chip,{dop1:.0f}Hz)  "
          f"第二峰={d2:6.0f}样({d2/spc:5.1f}chip,{dop2:.0f}Hz)  "
          f"比值={pr:.2f}  ts2={ts2:.1f}")

print("\n预期: 主峰 1388样(355.0chip)/1500Hz  第二峰 ~1412样(361chip)/1500Hz  比值~2.9(-4.6dB)")

#!/usr/bin/env python3
import h5py, numpy as np, glob, sys


def g(h, k):
    return float(np.array(h[k]).ravel()[0]) if k in h else float("nan")


for pat, label in [("gpsl1_acq_G_1C_ch_0_1_sat_1.mat", "单径#1"),
                   ("gpsl1_2path_acq_G_1C_ch_0_1_sat_1.mat", "双径#1")]:
    fs = sorted(glob.glob(pat))
    if not fs:
        print(label, "无 dump")
        continue
    h = h5py.File(fs[0], "r")
    print("%s: threshold=%.1f  主峰ts=%.1f  第二峰ts2=%.1f  peak_ratio=%.2f  input_power=%.2e  has2=%.0f"
          % (label, g(h, "threshold"), g(h, "test_statistic"), g(h, "test_statistic_2"),
             g(h, "peak_ratio"), g(h, "input_power"), g(h, "has_second_peak")))

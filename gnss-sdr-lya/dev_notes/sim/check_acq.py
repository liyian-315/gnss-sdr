#!/usr/bin/env python3
"""查捕获是否真的成功：读 dump 的 positive_acq / test_statistic / threshold。
   test_statistic > threshold 才算捕到；否则那个"峰"只是噪声 argmax。"""
import h5py, numpy as np, glob, sys

pat = sys.argv[1] if len(sys.argv) > 1 else "bds_b1i_acq_*_sat_9.mat"
fs = sorted(glob.glob(pat))
print("dump 数:", len(fs))
for f in fs[:8]:
    h = h5py.File(f, "r")
    def g(k):
        return float(np.array(h[k]).ravel()[0]) if k in h else float("nan")
    print("%-40s positive=%.0f  test_stat=%.1f  threshold=%.1f  (>=阈值才算真捕到)  input_power=%.2e  doppler=%.0f"
          % (f.split("/")[-1], g("positive_acq"), g("test_statistic"), g("threshold"), g("input_power"), g("acq_doppler_hz")))

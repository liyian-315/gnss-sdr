#!/usr/bin/env python3
# 验证 Stage 1b：两通道各自交给跟踪的捕获结果
# ch0(共享role,普通) 应交直射(≈355chip)；ch1(acquire_second_path) 应交反射(≈361chip)
import h5py, numpy as np, glob

spc = 4000 / 1023.0


def g(h, k):
    return float(np.array(h[k]).ravel()[0]) if k in h else float("nan")


for ch, name in [(0, "通道0 (普通→直射)"), (1, "通道1 (acquire_second_path→反射)")]:
    fs = sorted(glob.glob("ch_acq_G_1C_ch_%d_*_sat_1.mat" % ch))
    if not fs:
        print("%s: 无 dump（该通道可能未捕获成功）" % name)
        continue
    print("\n%s  (dump %d 份, 看前3份)" % (name, len(fs)))
    for f in fs[:3]:
        h = h5py.File(f, "r")
        # acq_delay_samples = update_synchro 交给跟踪的码相位（ch1 已是第二峰）
        d = g(h, "acq_delay_samples")
        dop = g(h, "acq_doppler_hz")
        has2 = g(h, "has_second_peak")
        d2 = g(h, "acq_delay_samples_2")
        print("   交给跟踪: 码相位=%.0f样(%.1fchip) 多普勒=%.0fHz | has2=%.0f 第二峰=%.1fchip"
              % (d, d / spc, dop, has2, (d2 / spc if not np.isnan(d2) else float("nan"))))

print("\n预期: 通道0 交 ~355chip(直射)；通道1 交 ~361chip(反射)")

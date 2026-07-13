#!/usr/bin/env python3
# 分析捕获相关面 dump：找 top 峰、看双径结构
import h5py, numpy as np, glob, sys

pat = sys.argv[1] if len(sys.argv) > 1 else "gpsl1_2path_acq_G_1C_ch_0_*_sat_1.mat"
fs = sorted(glob.glob(pat))
print("dump 份数:", len(fs), "| 分析:", fs[0])
h = h5py.File(fs[0], "r")
g = np.array(h["acq_grid"])            # (doppler_bins, code_samples)
spc = 4000 / 1023.0                     # 样点/码片 @4MHz
dmax = int(np.array(h["doppler_max"]).ravel()[0])
dstep = int(np.array(h["doppler_step"]).ravel()[0])
print("grid:", g.shape, " doppler_max", dmax, " step", dstep)

drow = int(np.argmax(g.max(axis=1)))
print(f"峰值多普勒 bin={drow} ({-dmax+dstep*drow} Hz)")

row = g[drow].copy()
print("\n--- 峰值多普勒行的 top-6 峰 (样点 / 码片 / 幅度) ---")
r = row.copy()
for _ in range(6):
    p = int(np.argmax(r))
    print(f"  样点 {p:4d}   {p/spc:6.1f} chip   {r[p]:.3e}")
    r[max(0, p-8):p+8] = 0

print("\n--- 预期位置附近 max 值 ---")
for s, name in [(1388, "直射@355chip"), (1412, "反射@361chip"), (3335, "疑似伪峰")]:
    print(f"  {name}: 样点 {s}  邻域max={row[max(0,s-6):s+7].max():.3e}")

print("\n--- 全二维网格 top-6 (去重: 同doppler且样点相近算一个) ---")
flat = np.argsort(g, axis=None)[::-1]
seen = []
for fi in flat:
    d, s = np.unravel_index(fi, g.shape)
    if all(not (dd == d and abs(s-ss) <= 8) for dd, ss in seen):
        seen.append((d, s))
        print(f"  bin{d} ({-dmax+dstep*d}Hz)  样点{s} ({s/spc:.1f}chip)  {g[d,s]:.3e}")
    if len(seen) >= 6:
        break

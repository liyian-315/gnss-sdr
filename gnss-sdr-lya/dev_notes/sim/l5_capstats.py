#!/usr/bin/env python3
"""快速体检一段 complex64(fc32) 原始采集：幅度/DC/削顶/粗谱，判断front-end是否真收到RF。"""
import sys
import numpy as np

f = sys.argv[1]
n = int(float(sys.argv[2])) if len(sys.argv) > 2 else 20_000_000
x = np.fromfile(f, dtype=np.complex64, count=n)
print("file:", f, " samples:", x.size)
if x.size == 0:
    sys.exit("empty/no read")
a = np.abs(x)
print("mean|x|=%.5g  rms=%.5g  max|x|=%.5g" % (a.mean(), np.sqrt(np.mean(a * a)), a.max()))
print("DC: re=%.5g im=%.5g" % (x.real.mean(), x.imag.mean()))
print("frac |x|<1e-4 (dead): %.3f" % float(np.mean(a < 1e-4)))
p = np.percentile(a, [50, 90, 99, 99.9, 100])
print("pct|x| 50/90/99/99.9/max:", np.array2string(p, precision=4))
# 粗谱：看有没有窄带/结构
seg = x[: 1 << 20].astype(np.complex64)
X = np.abs(np.fft.fftshift(np.fft.fft(seg)))
print("spectrum peak/median: %.1f dB (flat~white noise, 高=有窄带/信号结构)" % (10 * np.log10(X.max() / np.median(X))))

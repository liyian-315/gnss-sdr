#!/usr/bin/env python3
"""Inspect a gnss-sdr acquisition .mat dump: list vars, shapes, and the true acq_grid peak."""
import glob
import sys

import h5py
import numpy as np

f = sorted(glob.glob(sys.argv[1]))[-1]
print("file:", f)
h = h5py.File(f, "r")
print("keys:", list(h.keys()))
for k in h.keys():
    a = np.array(h[k])
    line = "  %-24s shape=%s dtype=%s" % (k, a.shape, a.dtype)
    if a.size <= 8:
        line += " val=" + np.array2string(a.ravel(), precision=4)
    else:
        try:
            line += " min=%.4g max=%.4g mean=%.4g" % (a.min(), a.max(), a.mean())
        except Exception:
            pass
    print(line)

g = np.array(h["acq_grid"], dtype=np.float64)
print("\nacq_grid shape", g.shape)
idx = np.unravel_index(int(np.argmax(g)), g.shape)
print("global max at", idx, "val=%.4g median=%.4g  peak/med=%.1f dB" % (g[idx], np.median(g), 10 * np.log10(g[idx] / np.median(g))))
m0 = g.max(axis=0)  # collapse doppler -> code profile
m1 = g.max(axis=1)  # collapse code -> doppler profile
print("collapse-doppler code-profile len=%d peak/med=%.1f dB" % (m0.size, 10 * np.log10(m0.max() / np.median(m0))))
print("collapse-code doppler-profile len=%d peak/med=%.1f dB" % (m1.size, 10 * np.log10(m1.max() / np.median(m1))))
# top-5 code bins in the best doppler row
best_d = int(np.argmax(m1))
row = g[best_d] if g.shape[1] > g.shape[0] else g[:, best_d]
top = np.argsort(row)[-6:][::-1]
print("best doppler idx", best_d, "top-6 code bins:", top, "vals", np.array2string(row[top], precision=4))

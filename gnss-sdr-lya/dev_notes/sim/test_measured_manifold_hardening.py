#!/usr/bin/env python3
"""MeasuredManifold hardening checks (doc23 fix 5). Run: python test_measured_manifold_hardening.py"""
import os
import tempfile

import numpy as np

import fit_space_delay_h1h2 as h

def main():
    results = []

    def case(name, fn, expect_error):
        try:
            fn()
            results.append((name, not expect_error))
        except Exception:
            results.append((name, expect_error))

    tmp = tempfile.mkdtemp()
    az = np.arange(0, 360, 30.0)  # full circle: gap == median spacing -> periodic
    resp = np.exp(1j * np.outer(np.radians(az), np.arange(4)))
    p1 = os.path.join(tmp, "m1.npz"); np.savez(p1, az_deg=az, response=resp)
    m = h.MeasuredManifold(p1)
    assert m.periodic
    case("full-circle loads periodic", lambda: None, False)
    d = np.linalg.norm(m.a(359.99) - m.a(0.01))
    case("360 seam continuous", lambda: (_ for _ in ()).throw(ValueError) if d > 0.05 else None, False)
    case("az=-15 wraps (periodic)", lambda: m.a(-15.0), False)

    az2 = np.arange(-60, 60.1, 15.0)
    p2 = os.path.join(tmp, "m2.npz")
    np.savez(p2, az_deg=az2, response=np.exp(1j * np.outer(np.radians(az2), np.arange(4))))
    m2 = h.MeasuredManifold(p2)
    assert not m2.periodic
    case("sector: inside ok", lambda: m2.a(10.0), False)
    case("sector: outside raises (no clamp)", lambda: m2.a(80.0), True)

    p3 = os.path.join(tmp, "m3.npz"); np.savez(p3, az_deg=az2[::-1], response=resp[:9])
    case("unsorted az rejected", lambda: h.MeasuredManifold(p3), True)
    azd = az2.copy(); azd[3] = azd[2]
    p4 = os.path.join(tmp, "m4.npz"); np.savez(p4, az_deg=azd, response=np.ones((9, 4), complex))
    case("duplicate az rejected", lambda: h.MeasuredManifold(p4), True)
    rn = resp[:9].copy(); rn[2, 1] = np.nan
    p5 = os.path.join(tmp, "m5.npz"); np.savez(p5, az_deg=az2, response=rn)
    case("NaN rejected", lambda: h.MeasuredManifold(p5), True)
    p6 = os.path.join(tmp, "m6.npz"); np.savez(p6, az_deg=az2, response=np.ones((9, 2, 4), complex))
    case("3-D E=2 rejected", lambda: h.MeasuredManifold(p6), True)
    p7 = os.path.join(tmp, "m7.npz"); np.savez(p7, az_deg=az2, response=np.ones((9, 1, 4), complex))
    case("3-D E=1 w/o flag rejected", lambda: h.MeasuredManifold(p7), True)
    case("3-D E=1 with explicit flag ok",
         lambda: h.MeasuredManifold(p7, allow_single_elevation=True), False)
    case("wrong channel count rejected", lambda: h.MeasuredManifold(p1, n_ant_expected=8), True)
    rz = resp.copy(); rz[:, 2] = 0
    p8 = os.path.join(tmp, "m8.npz"); np.savez(p8, az_deg=az, response=rz)
    case("all-zero channel rejected", lambda: h.MeasuredManifold(p8), True)

    for n, passed in results:
        print("%-42s %s" % (n, "PASS" if passed else "FAIL"))
    assert all(p for _, p in results), "manifold hardening failures"
    print("ALL MANIFOLD HARDENING CHECKS PASS (%d cases)" % len(results))

if __name__ == "__main__":
    main()

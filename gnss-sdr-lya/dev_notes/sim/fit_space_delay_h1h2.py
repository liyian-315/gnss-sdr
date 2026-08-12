#!/usr/bin/env python3
"""Continuous-refinement H1/H2 space-delay estimator -- doc19 s14 principles.

Refines the grid-only skeleton (fit_space_delay_twosource.py) with:

  * GENERIC ARRAY: element positions array_xyz_m (M,3), M arbitrary. No
    ULA/UCA/square assumption. Azimuth-only model (doc19 s2.2/s13); no
    a(theta, r) range dependence yet (record-only requirement, s14.5).
  * MEASURED-MANIFOLD HOOK: a(az) can come from an ideal-position model or a
    measured manifold npz (az_deg / response[az, el=1, channel]).
  * CONTINUOUS REFINEMENT: coarse grid search, then golden-section coordinate
    descent on (az0, tau0[, az1, tau1]) with VarPro per-block LS amplitudes.
    tau0 is refined, not hardcoded to 0.
  * REFERENCE SEMANTICS (s14.1): the common tracking reference (GNSS-SDR DLL
    on the reference channel) only defines the ZERO of the correlation
    coordinate system. It is NOT LOS truth, NOT DAS1/DAS2 truth. All delays
    below are `relative delay w.r.t. the common tracking reference`; the
    physically meaningful quantity is delta_tau = tau2_rel - tau1_rel.
  * DECISION STATES (s14.3): ONE_SOURCE / TWO_SOURCE / UNRESOLVED. UNRESOLVED
    fires on high joint-template coherence, bad conditioning, or parameter
    collision -- never force an H1-vs-H2 binary.
  * THRESHOLDS ARE PROVISIONAL (s14.2): detect/reliable dB values must be
    re-derived from REAL single-source negative-control captures before the
    parking-garage experiment. calibrate_h0_glrt.py gives a simulation
    PRE-calibration only.

Examples:
  python3 dev_notes/sim/fit_space_delay_h1h2.py --self-test
  python3 dev_notes/sim/fit_space_delay_h1h2.py --input scene.npz \
      --array-config dev_notes/sim/array_configs/actual_4elem_dualfeed_placeholder.json
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_two_path as ftp  # noqa: E402

PROVISIONAL_NOTE = ("thresholds are PROVISIONAL (doc19 s14.2): freeze only after "
                    "real single-source negative-control calibration")


# ---------------------------------------------------------------- array model
def steering_xyz(az_deg, pos_wl):
    """Ideal az-only steering: a_m = exp(+j 2pi p_m . u(az)), pos_wl (M,3)."""
    az = np.radians(az_deg)
    u = np.array([np.cos(az), np.sin(az), 0.0])
    return np.exp(1j * 2.0 * np.pi * (pos_wl @ u))


def ula_xyz(n_ant, spacing_wl):
    """ULA as a positions-matrix special case (back-compat with the skeleton)."""
    pos = np.zeros((n_ant, 3))
    pos[:, 1] = np.arange(n_ant) * spacing_wl  # along y: a_m = exp(j2pi m d sin az)
    return pos


class IdealManifold:
    """a(az) from element positions (wavelength units). Azimuth-only."""

    def __init__(self, pos_wl):
        self.pos_wl = np.asarray(pos_wl, dtype=float)
        self.n_ant = self.pos_wl.shape[0]

    def a(self, az_deg):
        return steering_xyz(az_deg, self.pos_wl)


class MeasuredManifold:
    """a(az) interpolated from a G1 manifold npz (doc19 s8 item 4).

    Expects keys az_deg (A,), response (A, 1, M) or (A, M). Complex linear
    interpolation per channel; az assumed sorted, no wrap handling yet.
    """

    def __init__(self, npz_path):
        d = np.load(npz_path, allow_pickle=False)
        self.az_deg = d["az_deg"].astype(float)
        resp = d["response"]
        self.resp = resp[:, 0, :] if resp.ndim == 3 else resp
        self.n_ant = self.resp.shape[1]

    def a(self, az_deg):
        re = np.array([np.interp(az_deg, self.az_deg, self.resp[:, m].real)
                       for m in range(self.n_ant)])
        im = np.array([np.interp(az_deg, self.az_deg, self.resp[:, m].imag)
                       for m in range(self.n_ant)])
        return re + 1j * im


def load_array_config(path):
    """Fail-fast loader for array_configs/*.json (doc19 s13.3/s13 v1.1)."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("user_confirmed", False):
        raise SystemExit(
            "FAIL-FAST: array config %r has user_confirmed=false. Fill the real "
            "measured/vendor array_xyz_m and rx wiring before ANY processing "
            "(doc19 s13.3). Refusing to use guessed geometry." % path)
    xyz = cfg.get("array_xyz_m")
    if xyz is None:
        raise SystemExit("FAIL-FAST: array_xyz_m is null in %r." % path)
    xyz = np.asarray(xyz, dtype=float)
    lam = float(cfg["wavelength_m"])
    return xyz / lam, cfg


# ---------------------------------------------------------------- templates
def kernel_vec(tau, taps, ktaps, kernel):
    return ftp.kern_at(ktaps, kernel, taps - tau)


def build_q(manifold, az_deg, tau, taps, ktaps, kernel):
    return np.kron(manifold.a(az_deg), kernel_vec(tau, taps, ktaps, kernel))


def coherence(u, v):
    return float(abs(np.vdot(u, v)) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-30))


def _residual(Y, X):
    C = Y @ np.linalg.pinv(X).T
    resid = Y - C @ X.T
    return float(np.sum(np.abs(resid) ** 2)), C


# ---------------------------------------------------------------- refinement
_GR = 0.5 * (np.sqrt(5.0) - 1.0)


def _golden(f, lo, hi, iters=18):
    a, b = lo, hi
    c, d = b - _GR * (b - a), a + _GR * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(iters):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - _GR * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + _GR * (b - a)
            fd = f(d)
    return (a + b) / 2.0


def _refine(Y, manifold, taps, ktaps, kernel, params, bounds, sweeps=3):
    """Coordinate-descent golden-section refinement of continuous params.

    params: list [(az0, tau0)] or [(az0, tau0), (az1, tau1)] flattened.
    bounds: matching list of (lo, hi) per scalar parameter.
    Returns refined flat params and final residual.
    """
    p = list(params)

    def cost_at(vec):
        cols = [build_q(manifold, vec[2 * s], vec[2 * s + 1], taps, ktaps, kernel)
                for s in range(len(vec) // 2)]
        return _residual(Y, np.column_stack(cols))[0]

    for _ in range(sweeps):
        for i in range(len(p)):
            lo, hi = bounds[i]

            def f1(x, i=i):
                q = p[:i] + [x] + p[i + 1:]
                return cost_at(q)

            p[i] = _golden(f1, lo, hi)
    return p, cost_at(p)


# ---------------------------------------------------------------- H1/H2 fit
def fit_h1h2(Y_bmk, taps, ktaps, kernel, manifold, chip_m,
             az_grid=None, tau_grid=None,
             detect_db=3.0, reliable_db=6.0, mu_max=0.98, cond_max=1e4,
             min_sep_chips=0.03, refine_sweeps=3):
    """Continuous H1/H2 model comparison on Y (B, M, K).

    All tau values are RELATIVE TO THE COMMON TRACKING REFERENCE (s14.1);
    they are not LOS/DAS truth. detect/reliable thresholds: PROVISIONAL.
    """
    if az_grid is None:
        az_grid = np.arange(-60.0, 60.1, 5.0)
    if tau_grid is None:
        tau_grid = np.arange(-0.25, 1.51, 0.05)
    B = Y_bmk.shape[0]
    Y = Y_bmk.reshape(B, -1)
    az_step = float(az_grid[1] - az_grid[0]) if len(az_grid) > 1 else 5.0
    tau_step = float(tau_grid[1] - tau_grid[0]) if len(tau_grid) > 1 else 0.05

    qcache = {(th, ta): build_q(manifold, th, ta, taps, ktaps, kernel)
              for th in az_grid for ta in tau_grid}

    # ---- H1 coarse + refine
    best1 = (np.inf, None)
    for (th, ta), q in qcache.items():
        r, _ = _residual(Y, q[:, None])
        if r < best1[0]:
            best1 = (r, (th, ta))
    (th_c, ta_c) = best1[1]
    p1, res_h1 = _refine(Y, manifold, taps, ktaps, kernel,
                         [th_c, ta_c],
                         [(th_c - az_step, th_c + az_step),
                          (ta_c - tau_step, ta_c + tau_step)], refine_sweeps)
    az_h1, tau_h1 = p1

    # ---- H2 coarse (tau0 anchored at refined H1 tau) + joint refine
    best2 = (np.inf, None)
    r0 = kernel_vec(tau_h1, taps, ktaps, kernel)
    for th0 in az_grid:
        q0 = np.kron(manifold.a(th0), r0)
        for th1 in az_grid:
            for ta1 in tau_grid:
                if abs(ta1 - tau_h1) < min_sep_chips:
                    continue
                r, _ = _residual(Y, np.column_stack([q0, qcache[(th1, ta1)]]))
                if r < best2[0]:
                    best2 = (r, (th0, th1, ta1))
    th0_c, th1_c, ta1_c = best2[1]
    p2, res_h2 = _refine(Y, manifold, taps, ktaps, kernel,
                         [th0_c, tau_h1, th1_c, ta1_c],
                         [(th0_c - az_step, th0_c + az_step),
                          (tau_h1 - tau_step, tau_h1 + tau_step),
                          (th1_c - az_step, th1_c + az_step),
                          (ta1_c - tau_step, ta1_c + tau_step)], refine_sweeps)
    az0, tau0, az1, tau1 = p2
    if tau1 < tau0:  # order sources by relative delay
        az0, tau0, az1, tau1 = az1, tau1, az0, tau0

    q0 = build_q(manifold, az0, tau0, taps, ktaps, kernel)
    q1 = build_q(manifold, az1, tau1, taps, ktaps, kernel)
    _, C = _residual(Y, np.column_stack([q0, q1]))
    mu_joint = coherence(q0, q1)
    mu_spatial = coherence(manifold.a(az0), manifold.a(az1))
    mu_temporal = coherence(kernel_vec(tau0, taps, ktaps, kernel),
                            kernel_vec(tau1, taps, ktaps, kernel))
    cond = float(np.linalg.cond(np.column_stack([q0, q1])))
    improvement_db = 10.0 * np.log10(res_h1 / max(res_h2, 1e-30))
    ratio_db = 20.0 * np.log10(np.median(np.abs(C[:, 1]) / (np.abs(C[:, 0]) + 1e-30)) + 1e-30)
    delta = tau1 - tau0

    # ---- decision (s14.3): never force H1-vs-H2 binary
    detail = None
    if improvement_db < detect_db:
        state = "ONE_SOURCE"
        detail = "NO_SECOND_SOURCE"
    elif mu_joint > mu_max or cond > cond_max or delta < min_sep_chips:
        state = "UNRESOLVED"
        detail = ("mu_joint>%.2f" % mu_max) if mu_joint > mu_max else \
                 ("cond>%g" % cond_max) if cond > cond_max else "param_collision"
    elif improvement_db >= reliable_db:
        state = "TWO_SOURCE"
        detail = "RELIABLE"
    else:
        state = "TWO_SOURCE"
        detail = "MARGINAL"

    out = dict(state=state, detail=detail, improvement_db=improvement_db,
               az1_deg=az0, az2_deg=az1,
               tau1_rel_chips=tau0, tau2_rel_chips=tau1,
               delta_tau_chips=delta, delta_tau_m=delta * chip_m,
               amp_ratio_db=ratio_db, mu_joint=mu_joint, mu_spatial=mu_spatial,
               mu_temporal=mu_temporal, cond=cond,
               h1_az_deg=az_h1, h1_tau_rel_chips=tau_h1,
               reference_semantics="relative delay w.r.t. common tracking reference (NOT LOS/DAS truth)",
               thresholds="PROVISIONAL")
    if state != "TWO_SOURCE":  # rejected-model params are N/A (05 review rule)
        for k in ("az1_deg", "az2_deg", "tau2_rel_chips", "delta_tau_chips",
                  "delta_tau_m", "amp_ratio_db"):
            out[k] = None
    return out


# ---------------------------------------------------------------- synthesis
def synth(manifold, taps, ktaps, kernel, sources, n_blocks, noise_sigma, rng):
    """sources: list of (az_deg, tau_chips, amp). Per-block random phases."""
    dense = np.zeros((n_blocks, manifold.n_ant, len(taps)), dtype=np.complex128)
    for b in range(n_blocks):
        for az, ta, amp in sources:
            dense[b] += (amp * np.exp(1j * rng.uniform(0, 2 * np.pi))
                         * np.outer(manifold.a(az), kernel_vec(ta, taps, ktaps, kernel)))
        dense[b] += noise_sigma * (rng.standard_normal(dense[b].shape)
                                   + 1j * rng.standard_normal(dense[b].shape)) / np.sqrt(2.0)
    return dense


# ---------------------------------------------------------------- self-test
def self_test():
    rng = np.random.default_rng(0)
    taps = np.round(np.arange(-1.5, 1.5001, 0.1), 4)
    kernel = ftp.synth_kernel(taps)
    chip_m = 29.3
    ula = IdealManifold(ula_xyz(4, 0.5))
    # arbitrary (non-ULA/UCA) fixed 4-element geometry, wavelength units
    arb = IdealManifold(np.array([[0.00, 0.00, 0.0], [0.55, 0.10, 0.0],
                                  [0.20, 0.60, 0.0], [0.70, 0.65, 0.0]]))
    amp1 = 10 ** (-6 / 20.0)
    print("=" * 100)
    print("SELF-TEST  continuous H1/H2 (M generic, az-only). "
          "delays = relative to common tracking reference. %s" % PROVISIONAL_NOTE)
    print("=" * 100)
    print("%-46s %5s %5s %6s %9s %9s  %s"
          % ("case", "mu_s", "mu_j", "dB", "d_est", "d_true", "STATE(detail)"))

    def row(label, manifold, sources, d_true):
        sc = synth(manifold, taps, taps, kernel, sources, 24, 0.05, rng)
        r = fit_h1h2(sc, taps, taps, kernel, manifold, chip_m)
        d = "%9.3f" % r["delta_tau_chips"] if r["delta_tau_chips"] is not None else "      N/A"
        print("%-46s %5.3f %5.3f %6.1f %s %9.3f  %s(%s)"
              % (label, r["mu_spatial"], r["mu_joint"], r["improvement_db"],
                 d, d_true, r["state"], r["detail"]))
        return r

    r = row("ULA4 on-grid az 0/30, dtau 0.5, -6dB", ula,
            [(0.0, 0.0, 1.0), (30.0, 0.5, amp1)], 0.5)
    assert r["state"] == "TWO_SOURCE" and abs(r["delta_tau_chips"] - 0.5) < 0.03

    r = row("ULA4 OFF-grid az 3.7/24.9, dtau 0.37, -6dB", ula,
            [(3.7, 0.04, 1.0), (24.9, 0.41, amp1)], 0.37)
    assert r["state"] == "TWO_SOURCE" and abs(r["delta_tau_chips"] - 0.37) < 0.03, \
        "continuous refinement must beat the 0.05-chip grid"

    r = row("ARBITRARY-XYZ4 OFF-grid, dtau 0.37, -6dB", arb,
            [(3.7, 0.04, 1.0), (24.9, 0.41, amp1)], 0.37)
    assert r["state"] == "TWO_SOURCE" and abs(r["delta_tau_chips"] - 0.37) < 0.03

    r = row("ULA4 same dir, equal pwr, dtau 0.1", ula,
            [(10.0, 0.0, 1.0), (10.0, 0.1, 1.0)], 0.1)
    assert r["state"] != "TWO_SOURCE", "degenerate geometry must not report two paths"

    r = row("ULA4 single source", ula, [(0.0, 0.0, 1.0)], 0.0)
    assert r["state"] == "ONE_SOURCE"
    print("-" * 100)
    print("all assertions passed. NOTE: ideal-simulation evidence level only "
          "(generator and estimator share kernel and steering law).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="scene .npz (dense/taps/meta_json)")
    ap.add_argument("--array-config", help="array_configs/*.json (fail-fast if unconfirmed)")
    ap.add_argument("--manifold", help="measured manifold .npz (overrides ideal model)")
    ap.add_argument("--kernel-csv", help="measured Phase A kernel CSV")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--detect-db", type=float, default=3.0, help="PROVISIONAL")
    ap.add_argument("--reliable-db", type=float, default=6.0, help="PROVISIONAL")
    ap.add_argument("--mu-max", type=float, default=0.98, help="PROVISIONAL")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.input:
        raise SystemExit("need --input <scene.npz> or --self-test")
    data = np.load(args.input, allow_pickle=False)
    dense = (data["Y"] if "Y" in data else data["dense"]).astype(np.complex128)
    taps = data["taps"].astype(np.float64)
    meta = json.loads(str(data["meta_json"]))
    if args.manifold:
        manifold = MeasuredManifold(args.manifold)
    elif args.array_config:
        pos_wl, _ = load_array_config(args.array_config)
        manifold = IdealManifold(pos_wl)
    elif "spacing_wl" in meta:  # legacy ULA scenes
        manifold = IdealManifold(ula_xyz(int(meta["n_antennas"]), float(meta["spacing_wl"])))
    else:
        raise SystemExit("need --manifold or --array-config for non-legacy scenes")
    if args.kernel_csv:
        ktaps, kernel = ftp.load_reference_csv(args.kernel_csv)
    else:
        ktaps, kernel = taps, ftp.synth_kernel(taps)
    r = fit_h1h2(dense, taps, ktaps, kernel, manifold, float(meta.get("chip_m", 29.3)),
                 detect_db=args.detect_db, reliable_db=args.reliable_db, mu_max=args.mu_max)
    print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()

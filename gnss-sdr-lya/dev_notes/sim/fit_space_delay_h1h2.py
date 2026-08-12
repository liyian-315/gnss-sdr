#!/usr/bin/env python3
"""Continuous-refinement H1/H2 space-delay estimator -- doc19 s14 + doc23 fixes.

Structural fixes over 7146fec14 (Codex review CONTINUOUS_REFINEMENT_REVIEW_BLOCK):

  * NO H1 ANCHORING (fix 1): the H2 coarse search is a fully independent
    two-source search over (az0, tau0, az1, tau1). The refined H1 solution is
    used ONLY as diagnostics and as one optional extra multi-start seed; it
    never constrains where either H2 source may lie.
  * AUDITABLE MULTI-START (fix 2): the top-K distinct coarse H2 candidates
    (swap-canonicalized, K fixed and reported) are each refined independently
    by golden-section coordinate descent; the lowest refined residual wins.
    Every start's seed, refined params, residual and status are reported.
  * NO DELAY-ONLY COLLISION RULE (fix 3): delta_tau = 0 with distinct spatial
    signatures is a legitimate TWO_SOURCE. Degeneracy is judged on the JOINT
    templates only: mu_joint, joint design condition number, and second-source
    amplitude significance.
  * THREE-STATE SEMANTICS (fix 4): formal states are ONE_SOURCE / TWO_SOURCE /
    UNRESOLVED. Evidence between the detect and reliable thresholds is
    UNRESOLVED (the old MARGINAL survives only as a detail/debug tag and is
    never reported as TWO_SOURCE). Thresholds remain PROVISIONAL and must be
    re-derived from real single-source negative controls (doc19 s14.2).
  * HARDENED MeasuredManifold (fix 5): validated az grid (sorted, unique,
    finite), explicit response-shape/channel checks, no silent elevation
    slicing, explicit 360-degree wrap for full-circle grids and hard errors
    (never silent clamping) outside a sector grid. Complex interpolation is
    per-channel LINEAR ON RE/IM: it under-estimates |a| when the phase step
    between neighbouring grid nodes is large, so the measured grid must keep
    per-channel phase steps small (<~30 deg); the wrap point makes the 0/360
    seam continuous by construction. Normalization convention: responses are
    relative to the reference channel defined at calibration time
    (meta_json.calibration_id); this loader does not re-normalize.

Reference semantics (doc19 s14.1): all delays are relative to the common
tracking reference (NOT LOS/DAS truth); the key quantity is delta_tau.

Azimuth-only. a(theta, r) intentionally NOT implemented (doc19 s14.5).

Examples:
  python3 dev_notes/sim/fit_space_delay_h1h2.py --self-test
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
    az = np.radians(az_deg)
    u = np.array([np.cos(az), np.sin(az), 0.0])
    return np.exp(1j * 2.0 * np.pi * (pos_wl @ u))


def ula_xyz(n_ant, spacing_wl):
    pos = np.zeros((n_ant, 3))
    pos[:, 1] = np.arange(n_ant) * spacing_wl
    return pos


class IdealManifold:
    def __init__(self, pos_wl):
        self.pos_wl = np.asarray(pos_wl, dtype=float)
        self.n_ant = self.pos_wl.shape[0]

    def a(self, az_deg):
        return steering_xyz(az_deg, self.pos_wl)


class MeasuredManifold:
    """Hardened a_measured(az) from a G1 manifold npz (doc19 s8 item 4).

    Accepts response of shape (A, M). A 3-D (A, E, M) response is REJECTED
    unless E == 1 and the caller passes allow_single_elevation=True -- no
    silent elevation-index-0 slicing. Wrap: if the az grid covers the full
    circle (gap to 360 <= 2x median spacing) interpolation is periodic via an
    explicit wrap node; otherwise queries outside [az_min, az_max] raise
    (no silent clamping).
    """

    def __init__(self, npz_path, allow_single_elevation=False, n_ant_expected=None):
        d = np.load(npz_path, allow_pickle=False)
        if "az_deg" not in d or "response" not in d:
            raise ValueError("manifold npz must contain az_deg and response")
        az = np.asarray(d["az_deg"], dtype=float)
        resp = np.asarray(d["response"])
        if resp.ndim == 3:
            if resp.shape[1] != 1 or not allow_single_elevation:
                raise ValueError(
                    "3-D response (A,E,M) with E=%d: refusing silent elevation "
                    "slicing. Pass allow_single_elevation=True only for E==1."
                    % resp.shape[1])
            resp = resp[:, 0, :]
        if resp.ndim != 2:
            raise ValueError("response must be (A,M) or (A,1,M), got %s" % (resp.shape,))
        if az.ndim != 1 or az.shape[0] != resp.shape[0]:
            raise ValueError("az_deg length %s != response rows %s" % (az.shape, resp.shape))
        if az.shape[0] < 3:
            raise ValueError("need >=3 azimuth nodes")
        if not np.all(np.isfinite(az)) or not np.all(np.isfinite(resp)):
            raise ValueError("non-finite values in manifold")
        if np.any(np.diff(az) <= 0):
            raise ValueError("az_deg must be strictly increasing (sorted, unique)")
        if az[-1] - az[0] >= 360.0:
            raise ValueError("az grid spans >= 360 deg (duplicate seam?)")
        if n_ant_expected is not None and resp.shape[1] != n_ant_expected:
            raise ValueError("channel count %d != expected %d" % (resp.shape[1], n_ant_expected))
        if np.any(np.max(np.abs(resp), axis=0) == 0.0):
            raise ValueError("some channel is identically zero")
        self.n_ant = resp.shape[1]
        gap = 360.0 - (az[-1] - az[0])
        med = float(np.median(np.diff(az)))
        self.periodic = gap <= 2.0 * med
        if self.periodic:  # explicit wrap node -> continuous 0/360 seam
            self._az = np.concatenate([az, [az[0] + 360.0]])
            self._resp = np.vstack([resp, resp[:1, :]])
        else:
            self._az, self._resp = az, resp

    def a(self, az_deg):
        az = float(az_deg)
        if self.periodic:
            az = self._az[0] + ((az - self._az[0]) % 360.0)
        elif az < self._az[0] or az > self._az[-1]:
            raise ValueError(
                "az=%.2f outside measured sector [%.2f, %.2f] and grid is not "
                "full-circle: refusing silent clamping" % (az, self._az[0], self._az[-1]))
        re = np.array([np.interp(az, self._az, self._resp[:, m].real)
                       for m in range(self.n_ant)])
        im = np.array([np.interp(az, self._az, self._resp[:, m].imag)
                       for m in range(self.n_ant)])
        return re + 1j * im


def load_array_config(path):
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
    return np.asarray(xyz, dtype=float) / float(cfg["wavelength_m"]), cfg


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
    p = list(params)

    def cost_at(vec):
        cols = [build_q(manifold, vec[2 * s], vec[2 * s + 1], taps, ktaps, kernel)
                for s in range(len(vec) // 2)]
        return _residual(Y, np.column_stack(cols))[0]

    for _ in range(sweeps):
        for i in range(len(p)):
            lo, hi = bounds[i]

            def f1(x, i=i):
                return cost_at(p[:i] + [x] + p[i + 1:])

            p[i] = _golden(f1, lo, hi)
    return p, cost_at(p)


# ---------------------------------------------------------------- coarse H2
def _template_bank(manifold, taps, ktaps, kernel, az_grid, tau_grid, cache):
    key = ("bank", id(manifold), az_grid.tobytes(), tau_grid.tobytes())
    if cache is not None and key in cache:
        return cache[key]
    params = [(th, ta) for th in az_grid for ta in tau_grid]
    Q = np.column_stack([build_q(manifold, th, ta, taps, ktaps, kernel)
                         for th, ta in params])                       # (MK, N)
    G = Q.conj().T @ Q                                                # (N, N)
    bank = (params, Q, G)
    if cache is not None:
        cache[key] = bank
    return bank


def _coarse(Y, params, Q, G, top_k, az_step, tau_step):
    """Independent H1 + H2 coarse search via closed-form projection energies.

    H2 residual for pair (i,j): ||Y||^2 - sum_b h^H G2^-1 h with h=[qi^H y, qj^H y].
    Returns (h1_best, h2_candidates_topK) with swap-canonical (i<j) dedup.
    """
    U = Y @ Q.conj()                              # (B, N): U[b,i] = qi^H y_b
    s = np.sum(np.abs(U) ** 2, axis=0)            # (N,)
    Smat = U.conj().T @ U                         # (N, N): S[i,j] = sum_b Ui* Uj
    gd = np.real(np.diag(G))
    tot = float(np.sum(np.abs(Y) ** 2))

    e1 = s / np.maximum(gd, 1e-30)
    i1 = int(np.argmax(e1))
    h1 = (params[i1], tot - float(e1[i1]))

    det = np.outer(gd, gd) - np.abs(G) ** 2
    E = (gd[None, :] * s[:, None] + gd[:, None] * s[None, :]
         - 2.0 * np.real(G * Smat)) / np.maximum(det, 1e-9)
    bad = det <= 1e-6 * np.outer(gd, gd)          # near-collinear template pairs
    E[bad] = -np.inf
    E[np.tril_indices_from(E)] = -np.inf          # i<j: swap-equivalent dedup

    order = np.argsort(E, axis=None)[::-1]
    n = len(params)
    cands = []
    for flat in order:
        if len(cands) >= top_k or not np.isfinite(E.flat[flat]):
            break
        i, j = divmod(int(flat), n)
        (a0, t0), (a1, t1) = params[i], params[j]
        if t1 < t0 or (t1 == t0 and a1 < a0):     # canonical order by tau then az
            a0, t0, a1, t1 = a1, t1, a0, t0
        new = (a0, t0, a1, t1)
        distinct = True
        for c in cands:
            if (abs(c[0] - a0) <= 1.5 * az_step and abs(c[1] - t0) <= 1.5 * tau_step
                    and abs(c[2] - a1) <= 1.5 * az_step and abs(c[3] - t1) <= 1.5 * tau_step):
                distinct = False
                break
        if distinct:
            cands.append(new)
    return h1, cands


# ---------------------------------------------------------------- H1/H2 fit
def fit_h1h2(Y_bmk, taps, ktaps, kernel, manifold, chip_m,
             az_grid=None, tau_grid=None,
             detect_db=3.0, reliable_db=6.0, mu_max=0.98, cond_max=1e4,
             amp_floor_db=-30.0, n_starts=5, refine_sweeps=3, cache=None):
    """Continuous H1/H2 comparison on Y (B, M, K). Delays are RELATIVE to the
    common tracking reference (s14.1). Thresholds PROVISIONAL (s14.2)."""
    if az_grid is None:
        az_grid = np.arange(-60.0, 60.1, 5.0)
    if tau_grid is None:
        tau_grid = np.round(np.arange(-0.75, 1.5001, 0.05), 4)
    B = Y_bmk.shape[0]
    Y = Y_bmk.reshape(B, -1)
    az_step = float(az_grid[1] - az_grid[0]) if len(az_grid) > 1 else 5.0
    tau_step = float(tau_grid[1] - tau_grid[0]) if len(tau_grid) > 1 else 0.05

    params, Q, G = _template_bank(manifold, taps, ktaps, kernel,
                                  np.asarray(az_grid, float),
                                  np.asarray(tau_grid, float), cache)
    (h1_seed, _), h2_cands = _coarse(Y, params, Q, G, n_starts, az_step, tau_step)

    # H1 refine
    p1, res_h1 = _refine(Y, manifold, taps, ktaps, kernel, list(h1_seed),
                         [(h1_seed[0] - az_step, h1_seed[0] + az_step),
                          (h1_seed[1] - tau_step, h1_seed[1] + tau_step)],
                         refine_sweeps)
    az_h1, tau_h1 = p1

    # H2 multi-start refine (independent coarse seeds + one optional H1-based
    # seed: H1 solution paired with best coarse pair partner -- a seed only,
    # never a constraint)
    seeds = list(h2_cands)
    if h2_cands:
        h1_extra = (az_h1, tau_h1, h2_cands[0][2], h2_cands[0][3])
        seeds.append(h1_extra)
    starts = []
    best = None
    for si, sd in enumerate(seeds):
        bounds = [(sd[0] - az_step, sd[0] + az_step),
                  (sd[1] - tau_step, sd[1] + tau_step),
                  (sd[2] - az_step, sd[2] + az_step),
                  (sd[3] - tau_step, sd[3] + tau_step)]
        pr, res = _refine(Y, manifold, taps, ktaps, kernel, list(sd), bounds,
                          refine_sweeps)
        status = "ok" if np.isfinite(res) else "failed"
        starts.append(dict(start_index=si,
                           seed=[round(v, 6) for v in sd],
                           refined=[round(v, 6) for v in pr],
                           residual=res, status=status,
                           h1_seeded=(si == len(seeds) - 1 and len(seeds) > len(h2_cands))))
        if status == "ok" and (best is None or res < best[1]):
            best = (pr, res, si)
    (az0, tau0, az1, tau1), res_h2, win = best
    if tau1 < tau0 or (tau1 == tau0 and az1 < az0):
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

    # decision (s14.3 + doc23 fix 4): joint-template degeneracy only; no
    # delay-only collision rule; MARGINAL evidence is UNRESOLVED, not TWO_SOURCE
    if improvement_db < detect_db:
        state, detail = "ONE_SOURCE", "below_detect_threshold"
    elif improvement_db < reliable_db:
        state, detail = "UNRESOLVED", "marginal_evidence"
    elif mu_joint > mu_max:
        state, detail = "UNRESOLVED", "joint_coherence"
    elif cond > cond_max:
        state, detail = "UNRESOLVED", "ill_conditioned"
    elif ratio_db < amp_floor_db:
        state, detail = "UNRESOLVED", "weak_second_amplitude"
    else:
        state, detail = "TWO_SOURCE", "reliable"

    out = dict(state=state, detail=detail, improvement_db=improvement_db,
               az1_deg=az0, az2_deg=az1,
               tau1_rel_chips=tau0, tau2_rel_chips=tau1,
               delta_tau_chips=delta, delta_tau_m=delta * chip_m,
               delta_az_deg=az1 - az0,
               amp_ratio_db=ratio_db, mu_joint=mu_joint, mu_spatial=mu_spatial,
               mu_temporal=mu_temporal, cond=cond,
               h1_az_deg=az_h1, h1_tau_rel_chips=tau_h1,
               h1_residual=res_h1, h2_residual=res_h2,
               n_starts=len(seeds), multi_start_winner=win,
               multi_start=starts,
               reference_semantics="relative delay w.r.t. common tracking reference (NOT LOS/DAS truth)",
               thresholds="PROVISIONAL")
    if state != "TWO_SOURCE":
        for k in ("az1_deg", "az2_deg", "tau2_rel_chips", "delta_tau_chips",
                  "delta_tau_m", "delta_az_deg", "amp_ratio_db"):
            out[k] = None
    return out


# ---------------------------------------------------------------- synthesis
def synth(manifold, taps, ktaps, kernel, sources, n_blocks, noise_sigma, rng):
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
    cache = {}
    amp1 = 10 ** (-6 / 20.0)
    print("=" * 104)
    print("SELF-TEST  doc23 structural fixes (independent H2, multi-start, "
          "joint-only degeneracy, 3-state). %s" % PROVISIONAL_NOTE)
    print("=" * 104)
    print("%-48s %5s %6s %9s %9s  %s"
          % ("case", "mu_j", "dB", "d_est", "d_true", "STATE(detail)"))

    def row(label, sources, d_true, seed=None):
        r_ = np.random.default_rng(seed) if seed is not None else rng
        sc = synth(ula, taps, taps, kernel, sources, 24, 0.05, r_)
        r = fit_h1h2(sc, taps, taps, kernel, ula, chip_m, cache=cache)
        d = "%9.3f" % r["delta_tau_chips"] if r["delta_tau_chips"] is not None else "      N/A"
        print("%-48s %5.3f %6.1f %s %9.3f  %s(%s)"
              % (label, r["mu_joint"], r["improvement_db"], d, d_true,
                 r["state"], r["detail"]))
        return r

    r = row("on-grid az 0/30, dtau 0.5, -6dB",
            [(0.0, 0.0, 1.0), (30.0, 0.5, amp1)], 0.5)
    assert r["state"] == "TWO_SOURCE" and abs(r["delta_tau_chips"] - 0.5) < 0.03

    r = row("OFF-grid az 3.7/24.9, dtau 0.37, -6dB",
            [(3.7, 0.04, 1.0), (24.9, 0.41, amp1)], 0.37)
    assert r["state"] == "TWO_SOURCE" and abs(r["delta_tau_chips"] - 0.37) < 0.03

    # Codex anchor-pressure cases: symmetric taus far from tau_h1
    for (t0, t1) in ((-0.25, 0.25), (-0.5, 0.5), (-0.18, 0.32)):
        r = row("ANCHOR-PRESSURE tau %+.2f/%+.2f, 30deg, 0dB" % (t0, t1),
                [(0.0, t0, 1.0), (30.0, t1, 1.0)], t1 - t0, seed=1)
        assert r["state"] == "TWO_SOURCE", "pressure case must resolve"
        assert abs(r["delta_tau_chips"] - (t1 - t0)) < 0.05, \
            "anchor bias must be gone: %.3f vs %.3f" % (r["delta_tau_chips"], t1 - t0)

    # zero-delay, distinct directions: was wrongly UNRESOLVED(collision)
    r = row("ZERO-DELAY az -30/+30, dtau 0, 0dB",
            [(-30.0, 0.0, 1.0), (30.0, 0.0, 1.0)], 0.0, seed=2)
    assert r["state"] == "TWO_SOURCE", "delta_tau=0 with distinct signatures must pass"

    r = row("same dir, equal pwr, dtau 0.1",
            [(10.0, 0.0, 1.0), (10.0, 0.1, 1.0)], 0.1)
    assert r["state"] != "TWO_SOURCE"

    r = row("single source", [(0.0, 0.0, 1.0)], 0.0)
    assert r["state"] == "ONE_SOURCE"
    print("-" * 104)
    print("all assertions passed. evidence level: ideal simulation only.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input")
    ap.add_argument("--array-config")
    ap.add_argument("--manifold")
    ap.add_argument("--kernel-csv")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--detect-db", type=float, default=3.0, help="PROVISIONAL")
    ap.add_argument("--reliable-db", type=float, default=6.0, help="PROVISIONAL")
    ap.add_argument("--mu-max", type=float, default=0.98, help="PROVISIONAL")
    ap.add_argument("--n-starts", type=int, default=5)
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
    elif "spacing_wl" in meta:
        manifold = IdealManifold(ula_xyz(int(meta["n_antennas"]), float(meta["spacing_wl"])))
    else:
        raise SystemExit("need --manifold or --array-config for non-legacy scenes")
    if args.kernel_csv:
        ktaps, kernel = ftp.load_reference_csv(args.kernel_csv)
    else:
        ktaps, kernel = taps, ftp.synth_kernel(taps)
    r = fit_h1h2(dense, taps, ktaps, kernel, manifold, float(meta.get("chip_m", 29.3)),
                 detect_db=args.detect_db, reliable_db=args.reliable_db,
                 mu_max=args.mu_max, n_starts=args.n_starts)
    print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()

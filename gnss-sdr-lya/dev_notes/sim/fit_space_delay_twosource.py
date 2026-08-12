#!/usr/bin/env python3
"""Space-delay joint two-source estimator -- static array track (doc 16).

Static same-code sub-chip separation is UNDER-DETERMINED from one antenna. An
N-element array adds an ANGLE axis: two paths that merge in delay separate in
DIRECTION. Separability is set by the JOINT template coherence

    mu_joint = |q0^H q1| / (|q0| |q1|) = spatial_mu * temporal_mu

because q(theta,tau) = a(theta) (x) r(tau) is a Kronecker product, so the joint
coherence FACTORS into the spatial coherence |a0^H a1| and the temporal coherence
|r0^H r1|. The array MULTIPLIES the (high, near-1 at sub-chip) temporal coherence
by the (<1, when directions differ) spatial coherence -> it turns an unresolvable
pair resolvable. When mu_joint ~ 1 (same direction) the pair stays UNRESOLVED no
matter the optimizer -- and we report exactly that.

Observation model (m = antenna, k = delay tap, b = short time block):

    y[b,m,k] = c0[b] a_m(theta0) R(tau_k - tau0)
             + c1[b] a_m(theta1) R(tau_k - tau1) + n[b,m,k]

The complex amplitudes c[b] are PER-BLOCK nuisance parameters (independent-simulator
clock drift). Separation must come from the SHARED (theta, tau) support across
blocks, so clock drift cannot masquerade as the separation mechanism -- this is the
multiple-measurement-vector (MMV) model from doc 16.

Two stages:
  A0  identifiability:  spatial/temporal/joint coherence + design condition number,
      computed from the templates -> predicts which geometries are fundamentally weak
      BEFORE any optimizer runs.
  A1  constrained GLRT/ML:  1-source (H1) vs 2-source (H2) model comparison; per-block
      complex amplitudes by linear least squares (variable projection); decision ->
      RELIABLE / MARGINAL / UNRESOLVED / NO_SECOND_SOURCE.

This is a SYNTHETIC skeleton (no hardware). On real captures the synthetic kernel
R(tau) is replaced by the Phase A measured kernel and a_m(theta) by the MEASURED
array manifold; the estimator core is unchanged.

Examples:
  python3 dev_notes/sim/fit_space_delay_twosource.py --self-test
  python3 dev_notes/sim/fit_space_delay_twosource.py --input scene.npz
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_two_path as ftp  # noqa: E402


# ---------------------------------------------------------------- array model
def steering_xyz(array_xyz_m, wavelength_m, az_deg):
    """Horizontal-plane steering for arbitrary element positions in metres."""
    xyz = np.asarray(array_xyz_m, dtype=np.float64)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0:
        raise ValueError("array_xyz_m must have shape (M, 3)")
    if not np.isfinite(xyz).all():
        raise ValueError("array_xyz_m must contain finite values")
    if not np.isfinite(wavelength_m) or wavelength_m <= 0.0:
        raise ValueError("wavelength_m must be positive")
    az = np.radians(az_deg)
    direction = np.array([np.cos(az), np.sin(az), 0.0])
    return np.exp(1j * 2.0 * np.pi / wavelength_m * (xyz @ direction))


def ula_xyz(n_ant, spacing_wl, wavelength_m=1.0):
    """Legacy ULA positions. The y-axis preserves the old sin(theta) convention."""
    xyz = np.zeros((n_ant, 3), dtype=np.float64)
    xyz[:, 1] = np.arange(n_ant) * spacing_wl * wavelength_m
    return xyz


def steering(theta_deg, n_ant, spacing_wl):
    """Backward-compatible ULA wrapper around :func:`steering_xyz`."""
    return steering_xyz(ula_xyz(n_ant, spacing_wl), 1.0, theta_deg)


def _array_steering(az_deg, n_ant, spacing_wl, array_xyz_m, wavelength_m):
    if array_xyz_m is None:
        return steering(az_deg, n_ant, spacing_wl)
    if len(array_xyz_m) != n_ant:
        raise ValueError("n_ant must match array_xyz_m")
    return steering_xyz(array_xyz_m, wavelength_m, az_deg)


def kernel_vec(tau, taps, ktaps, kernel):
    """Temporal template r(tau) = [R(tau_k - tau)] over the tap grid (complex)."""
    return ftp.kern_at(ktaps, kernel, taps - tau)


def build_q(theta_deg, tau, taps, ktaps, kernel, n_ant, spacing_wl,
            array_xyz_m=None, wavelength_m=1.0):
    """Joint space-delay template q(theta,tau) = a(theta) (x) r(tau), length M*K."""
    return np.kron(_array_steering(theta_deg, n_ant, spacing_wl,
                                   array_xyz_m, wavelength_m),
                   kernel_vec(tau, taps, ktaps, kernel))


def coherence(u, v):
    return float(abs(np.vdot(u, v)) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-30))


# ---------------------------------------------------------------- synthesis
def synth_dense(taps, ktaps, kernel, n_ant, spacing_wl, theta0, theta1, tau0, tau1,
                ratio_db, n_blocks, noise_sigma, rng, single_source=False,
                array_xyz_m=None, wavelength_m=1.0, truth_gain=None):
    """(B, M, K) complex dense array data. Per-block random phases emulate the two
    independent simulator clocks; (theta, tau) are shared across blocks."""
    ktap = len(taps)
    a0 = _array_steering(theta0, n_ant, spacing_wl, array_xyz_m, wavelength_m)
    a1 = _array_steering(theta1, n_ant, spacing_wl, array_xyz_m, wavelength_m)
    if truth_gain is not None:
        truth_gain = np.asarray(truth_gain, dtype=np.complex128)
        if truth_gain.shape not in ((n_ant,), (n_blocks, n_ant)):
            raise ValueError("truth_gain must have shape (M,) or (B,M)")
    r0 = kernel_vec(tau0, taps, ktaps, kernel)
    r1 = kernel_vec(tau1, taps, ktaps, kernel)
    amp1 = 10.0 ** (ratio_db / 20.0)
    dense = np.zeros((n_blocks, n_ant, ktap), dtype=np.complex128)
    for b in range(n_blocks):
        gain = truth_gain if truth_gain is None or truth_gain.ndim == 1 else truth_gain[b]
        a0_true = a0 if gain is None else a0 * gain
        a1_true = a1 if gain is None else a1 * gain
        dense[b] = np.exp(1j * rng.uniform(0, 2 * np.pi)) * np.outer(a0_true, r0)
        if not single_source:
            dense[b] += amp1 * np.exp(1j * rng.uniform(0, 2 * np.pi)) * np.outer(a1_true, r1)
        dense[b] += noise_sigma * (rng.standard_normal((n_ant, ktap))
                                   + 1j * rng.standard_normal((n_ant, ktap))) / np.sqrt(2.0)
    return dense


# ---------------------------------------------------------------- estimation
def _residual(Y, X):
    """Per-block LS amplitudes for design X (M*K, ncol); returns (residual_energy, C)."""
    C = Y @ np.linalg.pinv(X).T                 # (B, ncol)
    resid = Y - C @ X.T                         # (B, M*K)
    return float(np.sum(np.abs(resid) ** 2)), C


def residual_improvement_db(res_h1, res_h2, reference_energy):
    """Stable H1/H2 residual ratio, including the exact-fit numerical boundary."""
    numerical_zero = 100.0 * np.finfo(np.float64).eps * max(reference_energy, 1.0)
    if res_h1 <= numerical_zero:
        return 0.0
    return float(10.0 * np.log10(res_h1 / max(res_h2, numerical_zero)))


def fit(dense, taps, ktaps, kernel, n_ant, spacing_wl, chip_m,
        angle_grid=None, tau1_grid=None, tau0=0.0,
        detect_db=3.0, reliable_db=6.0, mu_max=0.98,
        array_xyz_m=None, wavelength_m=1.0, tau0_grid=None):
    """Constrained 1-vs-2-source GLRT/ML. Returns a result dict."""
    if angle_grid is None:
        angle_grid = np.arange(-60.0, 60.1, 5.0)
    if tau1_grid is None:
        tau1_grid = np.arange(0.05, 1.51, 0.05)
    B = dense.shape[0]
    Y = dense.reshape(B, -1)
    if tau0_grid is None:
        tau0_grid = np.array([tau0])
    all_tau = np.unique(np.concatenate([np.asarray(tau0_grid), np.asarray(tau1_grid)]))
    tmpl = {(th, ta): build_q(th, ta, taps, ktaps, kernel, n_ant, spacing_wl,
                              array_xyz_m, wavelength_m)
            for th in angle_grid for ta in all_tau}

    # H1: best single space-delay source
    best1 = (np.inf, None)
    for th in angle_grid:
        for ta in all_tau:
            res, _ = _residual(Y, tmpl[(th, ta)][:, None])
            if res < best1[0]:
                best1 = (res, (th, ta))
    res_h1 = best1[0]

    # H2: search both absolute delays when tau0_grid is supplied. The default
    # one-point grid preserves the legacy skeleton behaviour.
    best2 = (np.inf, None, None)
    for ta0 in tau0_grid:
        for th0 in angle_grid:
            q0 = tmpl[(th0, ta0)]
            for th1 in angle_grid:
                for ta1 in tau1_grid:
                    if ta1 <= ta0:
                        continue
                    q1 = tmpl[(th1, ta1)]
                    X = np.column_stack([q0, q1])
                    res, C = _residual(Y, X)
                    if res < best2[0]:
                        best2 = (res, (th0, ta0, th1, ta1), C)
    if best2[1] is None:
        raise ValueError("tau grids contain no ordered tau1 > tau0 pair")
    res_h2, (th0, ta0, th1, ta1), C = best2

    q0 = tmpl[(th0, ta0)]
    q1 = tmpl[(th1, ta1)]
    mu_joint = coherence(q0, q1)
    mu_spatial = coherence(_array_steering(th0, n_ant, spacing_wl, array_xyz_m, wavelength_m),
                           _array_steering(th1, n_ant, spacing_wl, array_xyz_m, wavelength_m))
    mu_temporal = coherence(kernel_vec(ta0, taps, ktaps, kernel), kernel_vec(ta1, taps, ktaps, kernel))
    cond = float(np.linalg.cond(np.column_stack([q0, q1])))
    improvement_db = residual_improvement_db(res_h1, res_h2,
                                              float(np.sum(np.abs(Y) ** 2)))
    ratio_db = 20.0 * np.log10(np.median(np.abs(C[:, 1]) / (np.abs(C[:, 0]) + 1e-30)) + 1e-30)

    if improvement_db < detect_db:
        state = "NO_SECOND_SOURCE"
    elif mu_joint > mu_max:
        state = "UNRESOLVED"
    elif improvement_db >= reliable_db:
        state = "RELIABLE"
    else:
        state = "MARGINAL"

    return dict(state=state, improvement_db=improvement_db,
                theta0=th0, theta1=th1, tau0_chips=ta0, tau1_chips=ta1,
                delta_chips=ta1 - ta0, delta_m=(ta1 - ta0) * chip_m,
                amp_ratio_db=ratio_db, mu_joint=mu_joint,
                mu_spatial=mu_spatial, mu_temporal=mu_temporal, cond=cond)


def print_result(r, truth=None):
    print("--- A0 identifiability (from the fitted templates) ---")
    print("temporal coherence |r0^H r1| = %.3f   <- what ONE antenna sees (near 1 at sub-chip)"
          % r["mu_temporal"])
    print("spatial  coherence |a0^H a1| = %.3f   <- the array's angular separation"
          % r["mu_spatial"])
    print("JOINT    coherence mu        = %.3f   = temporal x spatial  (1=unresolvable)"
          % r["mu_joint"])
    print("design condition number      = %.1f   (high => ill-conditioned amplitudes)" % r["cond"])
    print("--- A1 constrained GLRT (1-source vs 2-source) ---")
    print("H1->H2 residual improvement  = %.2f dB" % r["improvement_db"])
    if r["state"] in ("RELIABLE", "MARGINAL"):
        print("recovered: delta = %.3f chip (%.1f m), angle sep = %+.0f deg, amp ratio = %+.2f dB"
              % (r["delta_chips"], r["delta_m"], r["theta1"] - r["theta0"], r["amp_ratio_db"]))
    else:
        print("recovered: N/A (H2 rejected; candidate parameters suppressed)")
    print("VERDICT: %s" % r["state"])
    if truth is not None:
        d_true = (truth["tau1"] - truth["tau0"])
        print("truth  : delta = %.3f chip (%.1f m), angle sep = %+.0f deg, amp ratio = %+.1f dB"
              % (d_true, d_true * truth["chip_m"], truth["theta1"] - truth["theta0"], truth["ratio_db"]))
        if r["state"] in ("RELIABLE", "MARGINAL"):
            print("delay error = %+.2f m" % (r["delta_m"] - d_true * truth["chip_m"]))


def self_test():
    rng = np.random.default_rng(0)
    taps = np.round(np.arange(-1.5, 1.5001, 0.1), 4)
    kernel = ftp.synth_kernel(taps)
    chip_m = 29.3
    print("=" * 88)
    print("SELF-TEST  ULA lambda/2, L5 chip=29.3 m, path1 -6 dB, noise 0.05, 24 blocks")
    print("mu_joint = mu_temporal x mu_spatial  (the array MULTIPLIES temporal coherence by spatial)")
    print("=" * 88)
    print("%-40s %5s %5s %5s %6s %7s  %s"
          % ("case", "mu_t", "mu_s", "mu_j", "dB", "delta_m", "VERDICT"))
    print("-" * 88)

    def row(label, dense, n_ant, ang=None):
        r = fit(dense, taps, taps, kernel, n_ant, 0.5, chip_m, angle_grid=ang)
        delta = ("%7.1f" % r["delta_m"] if r["state"] in ("RELIABLE", "MARGINAL")
                 else "    N/A")
        print("%-40s %5.3f %5.3f %5.3f %6.1f %7s  %s"
              % (label, r["mu_temporal"], r["mu_spatial"], r["mu_joint"],
                 r["improvement_db"], delta, r["state"]))
        return r

    sc = synth_dense(taps, taps, kernel, 4, 0.5, 0, 30, 0, 0.5, -6, 24, 0.05, rng)
    row("0.5 chip, 30deg apart (min target)", sc, 4)

    sc = synth_dense(taps, taps, kernel, 4, 0.5, 0, 30, 0, 0.1, -6, 24, 0.05, rng)
    row("0.1 chip, 30deg : SINGLE antenna", sc[:, :1, :], 1, ang=np.array([0.0]))
    row("0.1 chip, 30deg : 4-elem ARRAY", sc, 4)

    sc = synth_dense(taps, taps, kernel, 4, 0.5, 0, 0, 0, 0.1, 0.0, 24, 0.05, rng)
    row("0.1 chip, SAME dir, equal pwr : ARRAY", sc, 4)

    sc = synth_dense(taps, taps, kernel, 4, 0.5, 0, 30, 0, 0.5, -6, 24, 0.05, rng, single_source=True)
    row("single source (no path1)", sc, 4)

    print("-" * 88)
    print("read: 0.1 chip (2.9 m): SINGLE antenna -> NO_SECOND_SOURCE (misses it); 4-elem")
    print("      ARRAY -> RELIABLE (recovers 2.9 m). Spatial diversity breaks a sub-resolution")
    print("      delay. SAME direction (mu~1): array adds no separating power -> honest refusal")
    print("      (NO_SECOND_SOURCE here; UNRESOLVED is the boundary state under real noise/texture).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="scene .npz from generate_space_delay_twosource.py")
    ap.add_argument("--self-test", action="store_true", help="run 3 canonical cases in memory")
    ap.add_argument("--detect-db", type=float, default=3.0)
    ap.add_argument("--reliable-db", type=float, default=6.0)
    ap.add_argument("--mu-max", type=float, default=0.98)
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.input:
        raise SystemExit("need --input <scene.npz> or --self-test")

    data = np.load(args.input, allow_pickle=False)
    dense = data["dense"].astype(np.complex128)
    taps = data["taps"].astype(np.float64)
    meta = json.loads(str(data["meta_json"]))
    if "kernel" in data.files:
        kernel = data["kernel"].astype(np.complex128)
        ktaps = data["kernel_taps"].astype(np.float64)
    else:
        kernel = ftp.synth_kernel(taps)
        ktaps = taps
        print("LIMITATION: legacy scene has no embedded kernel; using synthetic kernel")
    array_xyz_m = meta.get("array_xyz_m")
    wavelength_m = float(meta.get("wavelength_m", 1.0))
    r = fit(dense, taps, ktaps, kernel, int(meta["n_antennas"]), float(meta["spacing_wl"]),
            float(meta["chip_m"]), detect_db=args.detect_db, reliable_db=args.reliable_db,
            mu_max=args.mu_max, array_xyz_m=array_xyz_m, wavelength_m=wavelength_m,
            tau0_grid=np.arange(-0.25, 0.251, 0.05))
    print("scene: %s  (%d blocks x %d ant x %d taps)"
          % (os.path.basename(args.input), dense.shape[0], dense.shape[1], dense.shape[2]))
    truth = meta.get("truth")
    print_result(r, truth)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Drift-modulated full-segment two-source fitter for Phase B dense dumps.

This is the next step after fit_windowed_twosource.py.  The windowed fitter first
averages short windows, then fits each averaged profile.  That fails when two
independent simulators drift so fast that the relative phase rotates inside the
minimum practical window, and it is weak near the sub-chip/merged regime.

Model used here:

    Y(tau, t) = c0 * K(tau - tau0)
              + c1 * exp(j * 2*pi*f_drift*t) * K(tau - tau0 - delta)

For a candidate delta, c0 and c1 are complex linear least squares over ALL kept
epochs and ALL dense taps.  We therefore do not average away a fast drifting
second source; the drift modulation is the feature that separates it from the
static main-lobe tail.

Important:
  * The dense taps are only phase-referenced by tap0.  We do NOT divide by tap0
    magnitude, avoiding the merged-regime amplitude bias seen in the windowed
    fitter.
  * tau0 is fixed to 0 by default because the tracking loop already centers the
    prompt.  Use --tau0-grid for diagnostics if the prompt is visibly offset.

Examples:
  python3 dev_notes/sim/fit_drift_modulated_twosource.py --self-test --chip-m 29.3

  python3 dev_notes/sim/fit_drift_modulated_twosource.py \
    --dense <phaseB>/l5_phaseB_dense_ch_0.dat.json \
    --kernel <same-prn-aonly>/aonly_reference_Rtau.png.csv \
    --chip-m 29.3 --delay-m 60 --ratio-db -6 --carrier-hz 1176.45e6 \
    --min-delay-chips 0.5 --max-delay-chips 4.0 \
    --modulation-source residual-band --plot <phaseB>/drift_mod_fit.png
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_dense_correlator_dump as rd  # noqa: E402
from check_dense_vs_prompt import select_locked  # noqa: E402
import fit_two_path as ftp  # noqa: E402


def robust_std(x):
    x = np.asarray(x, dtype=float)
    if x.size < 2:
        return 0.0
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def zero_tap_index(taps):
    idx = int(np.argmin(np.abs(taps)))
    if abs(float(taps[idx])) > 0.05:
        raise SystemExit("no tap within 0.05 chip of 0.0 (nearest=%.3f)" % float(taps[idx]))
    return idx


def phase_reference_iq(iq, zt, mode):
    """Apply the requested common-mode reference."""
    tap0 = iq[:, zt]
    good = np.abs(tap0) > 0.0
    iq = iq[good]
    tap0 = tap0[good]
    if mode == "phase":
        phasor = np.exp(-1j * np.angle(tap0))
        return iq * phasor[:, None], good
    if mode == "tap0":
        return iq / tap0[:, None], good
    if mode == "none":
        return iq, good
    raise ValueError("unknown phase reference mode: %s" % mode)


def load_dense_selected(path, cn0_min, lock_min, skip_epochs, min_lock_run, settle_epochs,
                        phase_reference):
    _, dense_bin, meta = rd.load_metadata(path)
    dense = rd.read_records(dense_bin, meta)
    taps = np.asarray(meta["taps_chips"], dtype=np.float64)
    keep, n_seg, n_kept = select_locked(
        dense, cn0_min, lock_min, skip_epochs, min_lock_run, settle_epochs
    )
    selected = dense[keep]
    if len(selected) == 0:
        raise SystemExit("no sustained-locked records survived; lower gates or check tracking")
    fs = float(meta.get("sampling_frequency_hz", 20e6))
    zt = zero_tap_index(taps)
    iq = selected["tap_iq"].astype(np.complex128)
    iq_ref, good = phase_reference_iq(iq, zt, phase_reference)
    selected = selected[good]
    times = selected["sample_counter"].astype(np.float64) / fs
    times = times - times[0]
    print("dense records: %d  kept: %d (%.1f%%)  segments kept %d/%d  taps: %d  fs: %.1f MHz  ref=%s"
          % (len(dense), len(selected), 100.0 * len(selected) / max(1, len(dense)),
             n_kept, n_seg, len(taps), fs / 1e6, phase_reference))
    return taps, iq_ref, times, meta


def main_lobe_edge(taps, coherent_abs, zt, frac=0.2):
    thr = frac * float(np.max(coherent_abs)) if coherent_abs.size else 0.0
    edge = 1.5
    for j in range(zt, len(taps)):
        if coherent_abs[j] < thr:
            edge = float(taps[j])
            break
    return edge


def measure_drift(times_s, norm, taps, probe_chip):
    pidx = int(np.argmin(np.abs(taps - probe_chip)))
    v = norm[:, pidx]
    if len(v) < 2:
        return 0.0, pidx, 0.0
    dt = float(np.median(np.diff(times_s)))
    steps = v[1:] * np.conj(v[:-1])
    w = np.abs(v[1:]) * np.abs(v[:-1])
    if float(np.sum(w)) <= 0.0:
        return 0.0, pidx, 0.0
    resultant = np.sum(w * np.exp(1j * np.angle(steps)))
    step_rad = float(np.angle(resultant))
    coh = float(np.abs(resultant) / np.sum(w))
    return step_rad / (2.0 * np.pi * dt), pidx, coh


def choose_probe(times, iq_ref, taps, zt, delay_m, chip_m):
    tap0_mag = np.maximum(np.abs(iq_ref[:, zt]), 1e-12)
    norm = iq_ref / tap0_mag[:, None]
    coherent_abs = np.abs((iq_ref / np.exp(1j * 0.0)).mean(axis=0))
    edge = main_lobe_edge(taps, coherent_abs, zt)
    mag_mean = (np.abs(iq_ref) / tap0_mag[:, None]).mean(axis=0)
    far = taps >= max(0.6, edge)
    if delay_m is not None:
        probe = delay_m / chip_m
    elif far.any():
        probe = float(taps[far][int(np.argmax(mag_mean[far]))])
    else:
        probe = 1.0
    drift_hz, pidx, coh = measure_drift(times, norm, taps, probe)
    sec_chip = float(taps[far][int(np.argmax(mag_mean[far]))]) if far.any() else float("nan")
    sec_amp = float(np.max(mag_mean[far])) if far.any() else float("nan")
    print("path0 main-lobe edge %.2f chip; mag secondary %.2f chip (%.1f m), amp %.3f"
          % (edge, sec_chip, sec_chip * chip_m, sec_amp))
    print("drift probe %.2f chip -> f_drift=%+.2f Hz, coherence %.2f"
          % (float(taps[pidx]), drift_hz, coh))
    return drift_hz, float(taps[pidx])


def normal_eq_for_delta(taps, Y, mod, ktaps, K, tau0, delta):
    k0 = ftp.kern_at(ktaps, K, taps - tau0)
    k1 = ftp.kern_at(ktaps, K, taps - tau0 - delta)
    a00 = float(Y.shape[0]) * np.vdot(k0, k0)
    a11 = float(Y.shape[0]) * np.vdot(k1, k1)
    a01 = np.sum(mod) * np.vdot(k0, k1)
    gram = np.array([[a00, a01], [np.conj(a01), a11]], dtype=np.complex128)
    p0 = Y @ np.conj(k0)
    p1 = Y @ np.conj(k1)
    b = np.array([np.sum(p0), np.vdot(mod, p1)], dtype=np.complex128)
    try:
        c = np.linalg.solve(gram, b)
    except np.linalg.LinAlgError:
        c = np.linalg.lstsq(gram, b, rcond=None)[0]
    y2 = float(np.vdot(Y.ravel(), Y.ravel()).real)
    resid2 = max(0.0, y2 - float(np.vdot(c, b).real))
    return c, np.sqrt(resid2), gram


def fit_one_static(taps, Y, ktaps, K, tau0_values):
    y2 = float(np.vdot(Y.ravel(), Y.ravel()).real)
    best = None
    for tau0 in tau0_values:
        k0 = ftp.kern_at(ktaps, K, taps - tau0)
        a = float(Y.shape[0]) * np.vdot(k0, k0)
        b = np.sum(Y @ np.conj(k0))
        c = b / a if abs(a) > 0 else 0.0
        resid2 = max(0.0, y2 - float(np.vdot(c, b).real))
        item = (float(tau0), complex(c), float(np.sqrt(resid2)))
        if best is None or item[2] < best[2]:
            best = item
    return best


def _fit_grid_one_tau0(taps, data, times, ktaps, K, tau0, deltas, drift_values,
                       modulation_vectors=None):
    """Grid search over (drift, delta) for one tau0 using cached Y*K(delta)."""
    y2 = float(np.vdot(data.ravel(), data.ravel()).real)
    k0 = ftp.kern_at(ktaps, K, taps - tau0)
    a00 = float(data.shape[0]) * np.vdot(k0, k0)
    b0 = np.sum(data @ np.conj(k0))
    k1s = np.vstack([ftp.kern_at(ktaps, K, taps - tau0 - d) for d in deltas])
    a11s = float(data.shape[0]) * np.einsum("ij,ij->i", np.conj(k1s), k1s)
    s01s = k1s @ np.conj(k0)  # sum_k K1 * conj(K0) == conj(vdot(K0,K1))
    ps = data @ np.conj(k1s).T  # (epochs, ndelta)
    best = None
    if modulation_vectors is None:
        modulation_vectors = [(float(fhz), np.exp(1j * 2.0 * np.pi * float(fhz) * times))
                              for fhz in drift_values]
    for label, mod in modulation_vectors:
        b1s = np.conj(mod) @ ps
        a01s = np.sum(mod) * s01s  # sum_t mod * sum_k conj(K0)*K1
        for i, delta in enumerate(deltas):
            gram = np.array([[a00, a01s[i]], [np.conj(a01s[i]), a11s[i]]], dtype=np.complex128)
            b = np.array([b0, b1s[i]], dtype=np.complex128)
            try:
                c = np.linalg.solve(gram, b)
            except np.linalg.LinAlgError:
                c = np.linalg.lstsq(gram, b, rcond=None)[0]
            resid2 = max(0.0, y2 - float(np.vdot(c, b).real))
            item = (float(tau0), float(delta), complex(c[0]), complex(c[1]),
                    float(np.sqrt(resid2)), gram, label, mod)
            if best is None or item[4] < best[4]:
                best = item
    return best


def fit_drift_modulated(taps, Y, ktaps, K, drift_hz, dmin, dmax, tau0_values,
                        coarse=0.02, fine=0.005, drift_search_hz=0.0,
                        drift_step_hz=0.05, modulation_vectors=None):
    times = Y["times"] if isinstance(Y, dict) else None
    data = Y["data"] if isinstance(Y, dict) else Y
    if times is None:
        raise ValueError("fit_drift_modulated needs times")
    one = fit_one_static(taps, data, ktaps, K, tau0_values)
    if modulation_vectors is not None:
        drift_values = np.array([drift_hz], dtype=float)
    elif drift_search_hz > 0.0:
        drift_values = np.arange(drift_hz - drift_search_hz,
                                 drift_hz + drift_search_hz + 0.5 * drift_step_hz,
                                 drift_step_hz)
    else:
        drift_values = np.array([drift_hz], dtype=float)
    best = None
    deltas = np.arange(max(dmin, coarse), dmax + 1e-9, coarse)
    for tau0 in tau0_values:
        item = _fit_grid_one_tau0(taps, data, times, ktaps, K, float(tau0), deltas,
                                  drift_values, modulation_vectors)
        if best is None or item[4] < best[4]:
            best = item
    t0b, db, fb = best[0], best[1], best[6]
    t0_fine = [t0b] if len(tau0_values) == 1 else np.arange(t0b - coarse, t0b + coarse + 1e-9, fine)
    fine_modulation_vectors = modulation_vectors
    if modulation_vectors is not None:
        fine_drift_values = np.array([drift_hz], dtype=float)
    elif drift_search_hz > 0.0:
        fine_drift_values = np.array([fb], dtype=float)
        fine_step = max(drift_step_hz / 10.0, 0.005)
        fine_span = max(drift_step_hz, 0.02)
        fine_drift_values = np.arange(fb - fine_span, fb + fine_span + 0.5 * fine_step, fine_step)
    else:
        fine_drift_values = np.array([fb], dtype=float)
    fine_deltas = np.arange(max(dmin, fine, db - coarse), min(dmax, db + coarse) + 1e-9, fine)
    for tau0 in t0_fine:
        item = _fit_grid_one_tau0(taps, data, times, ktaps, K, float(tau0), fine_deltas,
                                  fine_drift_values, fine_modulation_vectors)
        if item[4] < best[4]:
            best = item
    return best, one


def modulation_step_score(times, mod, expected_drift_hz):
    if times is None or len(mod) < 2:
        return 0.0
    dt = np.diff(times)
    steps = mod[1:] * np.conj(mod[:-1])
    ref = np.exp(1j * 2.0 * np.pi * expected_drift_hz * dt)
    return float(np.abs(np.mean(steps * np.conj(ref))))


def residual_band_modulation(taps, data, times, ktaps, K, tau0, c0, delta,
                             expected_drift_hz=0.0,
                             band_half_chip=0.6, band_min_frac=0.15):
    """Estimate path1's per-epoch unit phasor from residual energy near delta.

    The static path0 contribution is removed first. The residual is projected
    onto a shifted kernel over a small delayed-tap band, so one noisy tap cannot
    dominate the modulation estimate.
    """
    k0 = ftp.kern_at(ktaps, K, taps - tau0)
    k1 = ftp.kern_at(ktaps, K, taps - tau0 - delta)
    resid = data - c0 * k0[None, :]
    support = np.abs(k1) >= band_min_frac * max(float(np.max(np.abs(k1))), 1e-12)
    band = np.abs(taps - (tau0 + delta)) <= band_half_chip
    mask = support & band
    if int(mask.sum()) < 3:
        mask = support
    if int(mask.sum()) < 3:
        mask = band
    if int(mask.sum()) < 1:
        mask = np.ones_like(taps, dtype=bool)
    kb = k1[mask]
    denom = float(np.vdot(kb, kb).real)
    if denom <= 0.0:
        alpha = np.ones(data.shape[0], dtype=np.complex128)
    else:
        alpha = (resid[:, mask] @ np.conj(kb)) / denom
    mag = np.abs(alpha)
    ok = mag > np.percentile(mag, 10.0)
    if int(ok.sum()):
        raw_unit = np.ones_like(alpha, dtype=np.complex128)
        raw_unit[ok] = alpha[ok] / mag[ok]
        raw_coherence = float(np.abs(np.mean(raw_unit[ok])))
    else:
        raw_coherence = 0.0
    # If the residual phasor is already almost static, keep the DC component.
    # Removing the mean would erase a shared-clock or very slow-drift second
    # source. For rotating independent-clock captures, remove static leakage
    # from path0/kernel mismatch before taking the phase sequence.
    if raw_coherence < 0.6:
        alpha = alpha - np.mean(alpha)
        mag = np.abs(alpha)
        ok = mag > np.percentile(mag, 10.0)
    mod = np.ones_like(alpha, dtype=np.complex128)
    mod[ok] = alpha[ok] / mag[ok]
    coherence = float(np.abs(np.mean(mod[ok]))) if int(ok.sum()) else 0.0
    step_score = modulation_step_score(times, mod, expected_drift_hz)
    return mod, int(mask.sum()), int(ok.sum()), coherence, step_score


def fit_residual_band_iterative(taps, Y, ktaps, K, dmin, dmax, tau0_values,
                                coarse=0.02, fine=0.005, iterations=3,
                                expected_drift_hz=0.0, mod_score_min=0.20,
                                band_half_chip=0.6, band_min_frac=0.15,
                                chip_m=29.3):
    """Alternating fit:
    static path0 -> residual-band modulation -> full-segment c0/c1/delta fit.
    """
    data = Y["data"] if isinstance(Y, dict) else Y
    times = Y["times"] if isinstance(Y, dict) else None
    if times is None:
        raise ValueError("fit_residual_band_iterative needs times")
    one = fit_one_static(taps, data, ktaps, K, tau0_values)
    tau0_current, c0_current = one[0], one[1]
    best = None
    best_meta = None

    for it in range(max(1, int(iterations))):
        deltas = np.arange(max(dmin, coarse), dmax + 1e-9, coarse)
        iter_best = None
        iter_meta = None
        fallback_best = None
        fallback_meta = None
        for tau0 in tau0_values:
            for delta in deltas:
                mod, n_band, n_phase, coh, step_score = residual_band_modulation(
                    taps, data, times, ktaps, K, float(tau0), c0_current, float(delta),
                    expected_drift_hz,
                    band_half_chip, band_min_frac
                )
                c, resid, gram = normal_eq_for_delta(taps, data, mod, ktaps, K, float(tau0), float(delta))
                item = (float(tau0), float(delta), complex(c[0]), complex(c[1]),
                        float(resid), gram, "residual-band iter%d" % (it + 1), mod)
                meta = (n_band, n_phase, coh, step_score)
                if fallback_best is None or item[4] < fallback_best[4]:
                    fallback_best, fallback_meta = item, meta
                if step_score < mod_score_min:
                    continue
                if iter_best is None or item[4] < iter_best[4]:
                    iter_best = item
                    iter_meta = meta
        if iter_best is None:
            iter_best, iter_meta = fallback_best, fallback_meta
        # Fine pass around the current iteration best.
        t0b, db = iter_best[0], iter_best[1]
        t0_fine = [t0b] if len(tau0_values) == 1 else np.arange(t0b - coarse, t0b + coarse + 1e-9, fine)
        fine_deltas = np.arange(max(dmin, fine, db - coarse), min(dmax, db + coarse) + 1e-9, fine)
        for tau0 in t0_fine:
            for delta in fine_deltas:
                mod, n_band, n_phase, coh, step_score = residual_band_modulation(
                    taps, data, times, ktaps, K, float(tau0), c0_current, float(delta),
                    expected_drift_hz,
                    band_half_chip, band_min_frac
                )
                c, resid, gram = normal_eq_for_delta(taps, data, mod, ktaps, K, float(tau0), float(delta))
                item = (float(tau0), float(delta), complex(c[0]), complex(c[1]),
                        float(resid), gram, "residual-band iter%d" % (it + 1), mod)
                if step_score >= mod_score_min and item[4] < iter_best[4]:
                    iter_best = item
                    iter_meta = (n_band, n_phase, coh, step_score)
        best, best_meta = iter_best, iter_meta
        tau0_current, c0_current = best[0], best[2]
        print("iteration %d: delta %.3f chip (%.1f m), amp %+.2f dB, resid %.4f, "
              "band_taps=%d phase_samples=%d mod_dc=%.3f mod_score=%.3f"
              % (it + 1, best[1], best[1] * chip_m,
                 20.0 * np.log10(abs(best[3]) / abs(best[2])) if abs(best[2]) > 0 else float("nan"),
                 best[4] / max(float(np.linalg.norm(data)), 1e-12),
                 best_meta[0], best_meta[1], best_meta[2], best_meta[3]))
    return best, one


def summarize_fit(best, one, Y, chip_m, delay_m, ratio_db):
    tau0, delta, c0, c1, resid2, gram, fit_drift_hz, fit_mod = best
    tau1 = tau0 + delta
    ny = float(np.linalg.norm(Y))
    resid2_rel = resid2 / ny if ny else float("nan")
    resid1_rel = one[2] / ny if ny else float("nan")
    resid_drop = 1.0 - resid2 / one[2] if one[2] else float("nan")
    amp_ratio_db = 20.0 * np.log10(abs(c1) / abs(c0)) if abs(c0) > 0 else float("nan")
    phase_deg = float(np.degrees(np.angle(c1 / c0))) if abs(c0) > 0 else float("nan")
    cond = float(np.linalg.cond(gram))
    print("\n--- drift-modulated full-segment fit ---")
    print("path0 tau=%.3f chip  path1 tau=%.3f chip  delta=%.3f chip = %.1f m"
          % (tau0, tau1, delta, delta * chip_m))
    print("amp ratio A1/A0=%+.2f dB  relative phase=%+.0f deg" % (amp_ratio_db, phase_deg))
    print("resid2=%.4f  resid1=%.4f  drop=%.3f  gram_cond=%.1f"
          % (resid2_rel, resid1_rel, resid_drop, cond))
    if isinstance(fit_drift_hz, str):
        print("fit modulation=%s" % fit_drift_hz)
    else:
        print("fit drift=%+.3f Hz" % fit_drift_hz)
    reasons = []
    if resid_drop < 0.15:
        reasons.append("weak residual drop %.3f < 0.15" % resid_drop)
    if amp_ratio_db < -25:
        reasons.append("second source too weak %.1f dB" % amp_ratio_db)
    if delta < 0.05:
        reasons.append("delta below search floor")
    if cond > 1e5:
        reasons.append("ill-conditioned gram %.1g" % cond)
    delay_error_m = None
    ratio_error_db = None
    if delay_m is not None:
        delay_error_m = delta * chip_m - delay_m
        if abs(delay_error_m) > max(8.0, 0.25 * abs(delay_m)):
            reasons.append("validation delay error %.1f m" % delay_error_m)
    if ratio_db is not None:
        ratio_error_db = amp_ratio_db - ratio_db
        if abs(ratio_error_db) > 6.0:
            reasons.append("validation ratio error %.1f dB" % ratio_error_db)
    reliable = not reasons
    print("VERDICT: %s%s" % ("RELIABLE" if reliable else "UNRELIABLE / uncertain",
                             "" if reliable else " -- " + "; ".join(reasons)))
    if delay_m is not None:
        print("delay: injected %.1f m  recovered %.1f m  error %+.1f m"
              % (delay_m, delta * chip_m, delay_error_m))
    if ratio_db is not None:
        print("ratio: injected %+.1f dB  recovered %+.2f dB  error %+.2f dB"
              % (ratio_db, amp_ratio_db, ratio_error_db))
    return {
        "delta_m": delta * chip_m,
        "amp_ratio_db": amp_ratio_db,
        "resid_drop": resid_drop,
        "reliable": reliable,
        "tau0": tau0,
        "tau1": tau1,
        "c0": c0,
        "c1": c1,
        "phase_deg": phase_deg,
        "fit_drift_hz": fit_drift_hz,
        "mod": fit_mod,
    }


def synthetic_case(taps, K, chip_m, delta_chip, ratio_db, drift_hz, phi_deg, n_epochs=3000,
                   noise=0.003, tau0=0.0, seed=1):
    rng = np.random.default_rng(seed)
    times = np.arange(n_epochs, dtype=float) * 1e-3
    c0 = 1.0 + 0j
    c1 = (10.0 ** (ratio_db / 20.0)) * np.exp(1j * np.radians(phi_deg))
    k0 = ftp.kern_at(taps, K, taps - tau0)
    k1 = ftp.kern_at(taps, K, taps - tau0 - delta_chip)
    mod = np.exp(1j * 2.0 * np.pi * drift_hz * times)
    Y = c0 * k0[None, :] + c1 * mod[:, None] * k1[None, :]
    Y += noise * (rng.standard_normal(Y.shape) + 1j * rng.standard_normal(Y.shape))
    return {"data": Y.astype(np.complex128), "times": times}


def self_test(chip_m):
    taps = np.round(np.arange(-4.0, 4.0001, 0.1), 3)
    K = ftp.synth_kernel(taps)
    cases = [
        ("60m slow", 60.0 / chip_m, -6.0, 0.04, 90.0),
        ("60m fast", 60.0 / chip_m, -6.0, 250.0, 180.0),
        ("30m near", 30.0 / chip_m, -6.0, 26.0, 45.0),
        ("0.5chip equal destructive", 0.5, 0.0, 250.0, 180.0),
    ]
    print("self-test: drift-modulated full-segment fit")
    for i, (name, dchip, rdb, fhz, phi) in enumerate(cases, start=1):
        print("\n==== %s ====" % name)
        Y = synthetic_case(taps, K, chip_m, dchip, rdb, fhz, phi, seed=i)
        print("[sinusoid modulation]")
        best, one = fit_drift_modulated(
            taps, Y, taps, K, fhz, dmin=0.05, dmax=max(4.0, dchip + 1.0),
            tau0_values=[0.0], coarse=0.02, fine=0.005
        )
        summarize_fit(best, one, Y["data"], chip_m, dchip * chip_m, rdb)
        print("[residual-band alternating modulation]")
        best, one = fit_residual_band_iterative(
            taps, Y, taps, K, dmin=0.05, dmax=max(4.0, dchip + 1.0),
            tau0_values=[0.0], coarse=0.02, fine=0.005,
            iterations=3, expected_drift_hz=fhz, chip_m=chip_m
        )
        summarize_fit(best, one, Y["data"], chip_m, dchip * chip_m, rdb)


def make_tau0_values(spec):
    if spec is None or spec == "0":
        return [0.0]
    parts = [float(x) for x in spec.split(":")]
    if len(parts) != 3:
        raise SystemExit("--tau0-grid must be 'start:step:stop' or 0")
    start, step, stop = parts
    if step == 0:
        raise SystemExit("--tau0-grid step cannot be zero")
    vals = np.arange(start, stop + 0.5 * step, step)
    return [float(v) for v in vals]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dense", help="two-source dense .dat or .dat.json")
    ap.add_argument("--kernel", help="same-PRN Phase A reference CSV")
    ap.add_argument("--chip-m", type=float, default=29.3)
    ap.add_argument("--carrier-hz", type=float, default=1176.45e6)
    ap.add_argument("--delay-m", type=float, help="injected delay, for scoring and default probe")
    ap.add_argument("--ratio-db", type=float, help="injected amplitude ratio, for scoring")
    ap.add_argument("--cn0-min", type=float, default=35.0)
    ap.add_argument("--lock-min", type=float, default=0.6)
    ap.add_argument("--skip-epochs", type=int, default=0)
    ap.add_argument("--min-lock-run", type=int, default=2000)
    ap.add_argument("--settle-epochs", type=int, default=200)
    ap.add_argument("--probe-chip", type=float, help="tap used to estimate relative drift")
    ap.add_argument("--drift-hz", type=float, help="override measured relative drift")
    ap.add_argument("--drift-search-hz", type=float, default=0.0,
                    help="search +/- this many Hz around the measured/overridden drift")
    ap.add_argument("--drift-step-hz", type=float, default=0.05,
                    help="coarse drift search step in Hz; fine pass uses step/10")
    ap.add_argument("--min-delay-chips", type=float, default=0.10,
                    help="minimum positive path separation searched, in chips")
    ap.add_argument("--max-delay-chips", type=float, default=None)
    ap.add_argument("--tau0-grid", default="0",
                    help="0 to fix tau0 at prompt, or start:step:stop for diagnostics")
    ap.add_argument("--phase-reference", choices=("phase", "tap0", "none"), default="phase",
                    help="common-mode reference before fitting: phase keeps prompt magnitude; "
                         "tap0 matches the windowed fitter but biases merged amplitudes; "
                         "none uses raw dense taps")
    ap.add_argument("--modulation-source", choices=("sinusoid", "probe", "residual-band"),
                    default="sinusoid",
                    help="sinusoid uses exp(j*2*pi*f*t); probe uses the measured unit phasor "
                         "at --probe-chip/default delay tap; residual-band alternates static "
                         "path0 subtraction, delayed-band modulation estimation, and full fit")
    ap.add_argument("--iterations", type=int, default=3,
                    help="iterations for --modulation-source residual-band")
    ap.add_argument("--mod-score-min", type=float, default=0.20,
                    help="minimum residual-band phase-step consistency with measured drift")
    ap.add_argument("--band-half-chip", type=float, default=0.6,
                    help="half-width of residual delayed tap band, in chips")
    ap.add_argument("--band-min-frac", type=float, default=0.15,
                    help="also require shifted-kernel magnitude >= this fraction of its peak inside the band")
    ap.add_argument("--coarse-chip", type=float, default=0.02)
    ap.add_argument("--fine-chip", type=float, default=0.005)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--plot", help="PNG comparing magnitude mean and fitted static/modulated components")
    args = ap.parse_args()

    if args.self_test:
        self_test(args.chip_m)
        return
    if not (args.dense and args.kernel):
        raise SystemExit("need --dense and --kernel, or use --self-test")

    taps, iq_ref, times, meta = load_dense_selected(
        args.dense, args.cn0_min, args.lock_min, args.skip_epochs,
        args.min_lock_run, args.settle_epochs, args.phase_reference
    )
    ktaps, K = ftp.load_reference_csv(args.kernel)
    zt = zero_tap_index(taps)
    tap0_mag = np.maximum(np.abs(iq_ref[:, zt]), 1e-12)
    norm_for_drift = iq_ref / tap0_mag[:, None]
    if args.drift_hz is None:
        drift_hz, probe_chip = choose_probe(times, iq_ref, taps, zt, args.delay_m, args.chip_m)
    else:
        drift_hz, probe_chip = float(args.drift_hz), args.probe_chip or (
            args.delay_m / args.chip_m if args.delay_m else 1.0)
        _d, pidx, coh = measure_drift(times, norm_for_drift, taps, probe_chip)
        print("drift override: using %+.2f Hz; measured at %.2f chip was %+.2f Hz (coh %.2f)"
              % (drift_hz, float(taps[pidx]), _d, coh))
    modulation_vectors = None
    if args.modulation_source == "probe":
        pidx = int(np.argmin(np.abs(taps - probe_chip)))
        v = norm_for_drift[:, pidx]
        # Remove DC/static tail before taking phase. If the delayed tap contains a
        # little path0 leakage, its mean is static and should not define modulation.
        v = v - np.mean(v)
        ok = np.abs(v) > np.percentile(np.abs(v), 10.0)
        mod = np.ones_like(v, dtype=np.complex128)
        mod[ok] = v[ok] / np.abs(v[ok])
        modulation_vectors = [("probe@%.2fchip" % float(taps[pidx]), mod)]
        print("modulation source: measured probe phasor at %.2f chip (kept phase samples %d/%d)"
              % (float(taps[pidx]), int(ok.sum()), len(ok)))

    dmax = args.max_delay_chips
    if dmax is None:
        dmax = max(2.5, 1.3 * abs(args.delay_m) / args.chip_m) if args.delay_m else 2.5
    dmin = max(0.0, float(args.min_delay_chips))
    if dmin >= dmax:
        raise SystemExit("--min-delay-chips must be smaller than --max-delay-chips")
    tau0_values = make_tau0_values(args.tau0_grid)
    print("kernel: %s" % os.path.basename(args.kernel))
    print("search: tau0_values=%d  dmin=%.2f chip (%.1f m)  dmax=%.2f chip (%.1f m)  "
          "coarse=%.3f fine=%.3f"
          % (len(tau0_values), dmin, dmin * args.chip_m,
             dmax, dmax * args.chip_m, args.coarse_chip, args.fine_chip))

    Y = {"data": iq_ref, "times": times}
    if args.modulation_source == "residual-band":
        print("modulation source: residual-band alternating fit "
              "(iterations=%d, band_half=%.2f chip, band_min_frac=%.2f, mod_score_min=%.2f)"
              % (args.iterations, args.band_half_chip, args.band_min_frac, args.mod_score_min))
        best, one = fit_residual_band_iterative(
            taps, Y, ktaps, K, dmin, dmax, tau0_values,
            coarse=args.coarse_chip, fine=args.fine_chip,
            iterations=args.iterations,
            expected_drift_hz=drift_hz,
            mod_score_min=args.mod_score_min,
            band_half_chip=args.band_half_chip,
            band_min_frac=args.band_min_frac,
            chip_m=args.chip_m
        )
    else:
        best, one = fit_drift_modulated(
            taps, Y, ktaps, K, drift_hz, dmin, dmax, tau0_values,
            coarse=args.coarse_chip, fine=args.fine_chip,
            drift_search_hz=args.drift_search_hz,
            drift_step_hz=args.drift_step_hz,
            modulation_vectors=modulation_vectors
        )
    s = summarize_fit(best, one, iq_ref, args.chip_m, args.delay_m, args.ratio_db)

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        mag_mean = (np.abs(iq_ref) / tap0_mag[:, None]).mean(axis=0)
        k0 = ftp.kern_at(ktaps, K, taps - s["tau0"])
        k1 = ftp.kern_at(ktaps, K, taps - s["tau1"])
        # Magnitude average of the fitted model under the measured drift.
        mod = s.get("mod")
        if mod is None:
            mod = np.exp(1j * 2.0 * np.pi * drift_hz * times)
        model = s["c0"] * k0[None, :] + s["c1"] * mod[:, None] * k1[None, :]
        model_mag = (np.abs(model) / np.maximum(np.abs(model[:, zt]), 1e-12)[:, None]).mean(axis=0)
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(taps, mag_mean, "o-", ms=3, label="observed mag_mean")
        ax.plot(taps, model_mag, "-", label="drift-modulated model mag_mean")
        ax.plot(taps, np.abs(k0) / max(np.abs(k0).max(), 1e-12), "--", label="path0 kernel")
        ax.plot(taps, np.abs(k1) / max(np.abs(k1).max(), 1e-12), "--", label="path1 shifted kernel")
        ax.axvline(s["tau0"], color="g", lw=0.8)
        ax.axvline(s["tau1"], color="r", lw=0.8)
        ax.set_xlabel("tap offset [chips]")
        ax.set_ylabel("normalized magnitude")
        ax.set_title("drift-modulated full-segment fit: delta %.1f m, ratio %+.1f dB"
                     % (s["delta_m"], s["amp_ratio_db"]))
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(args.plot, dpi=150)
        print("plot -> %s" % args.plot)


if __name__ == "__main__":
    main()

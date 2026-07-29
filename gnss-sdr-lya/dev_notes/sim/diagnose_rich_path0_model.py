#!/usr/bin/env python3
"""Rich path0 model diagnostic: K + dK/dtau + A-only residual basis.

This is a research diagnostic, not a production detector. It tests whether a
richer path0 model learned from single-source A-only data can make an injected
path1 uniquely visible in faithful-path0 synthetic data.

Path0 model:

1. Fit each epoch with a local first-order kernel model:

       y ~= cK * K(tau) + cD * dK/dtau(tau)

   This captures small code-loop shifts without a per-epoch grid search.

2. On A-only training data, align the leftover residual into the path0 phase
   frame and learn a small complex residual basis by SVD.

3. On test data, fit K+dK, project the aligned residual onto the learned basis,
   subtract it, then inspect the residual delay-Doppler map.

Success criterion for this diagnostic:

The injected target delay should become the strongest residual candidate with a
stable delay across segments. If it is merely one of several comparable peaks,
the model has not solved the path0 residual problem yet.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diagnose_faithful_path0_synthetic as fsyn  # noqa: E402
import diagnose_path0_removal as p0diag           # noqa: E402
import fit_two_path as ftp                        # noqa: E402


def derivative_kernel(ktaps, K, taps, h=0.02):
    return (ftp.kern_at(ktaps, K, taps - h) - ftp.kern_at(ktaps, K, taps + h)) / (2.0 * h)


def fit_basis(iq, basis):
    """Least-squares fit rows in iq with column basis.

    basis shape: (n_basis, n_taps). Returns fit, coeffs, relative residuals.
    """
    B = np.asarray(basis, dtype=np.complex128).T
    coeffs = np.linalg.lstsq(B, iq.T, rcond=None)[0].T
    fit = coeffs @ B.T
    denom = np.maximum(np.linalg.norm(iq, axis=1), 1e-12)
    rel = np.linalg.norm(iq - fit, axis=1) / denom
    return fit, coeffs, rel


def smooth_coeffs(coeffs, n):
    if n <= 1:
        return coeffs
    kernel = np.ones(int(n), dtype=np.float64) / float(n)
    out = np.empty_like(coeffs)
    for col in range(coeffs.shape[1]):
        out[:, col] = (np.convolve(coeffs[:, col].real, kernel, mode="same") +
                       1j * np.convolve(coeffs[:, col].imag, kernel, mode="same"))
    return out


def learn_residual_basis(path0_iq, taps, ktaps, K, n_pcs):
    k0 = ftp.kern_at(ktaps, K, taps)
    dk = derivative_kernel(ktaps, K, taps)
    fit, coeffs, rel = fit_basis(path0_iq, np.vstack([k0, dk]))
    residual = path0_iq - fit
    c0 = coeffs[:, 0]
    scale = np.where(np.abs(c0) > 1e-12, c0, 1.0 + 0j)
    aligned = residual / scale[:, None]
    mean = np.mean(aligned, axis=0)
    centered = aligned - mean[None, :]
    if n_pcs > 0:
        _u, s, vh = np.linalg.svd(centered, full_matrices=False)
        pcs = vh[:n_pcs]
        eig = s[:n_pcs]
    else:
        pcs = np.empty((0, path0_iq.shape[1]), dtype=np.complex128)
        eig = np.empty(0, dtype=np.float64)
    return dict(k0=k0, dk=dk, mean=mean, pcs=pcs, eig=eig, train_rel=rel)


def subtract_rich_path0(iq, model, residual_smooth_epochs=1):
    base = np.vstack([model["k0"], model["dk"]])
    fit0, coeffs0, rel0 = fit_basis(iq, base)
    residual0 = iq - fit0
    c0 = coeffs0[:, 0]
    scale = np.where(np.abs(c0) > 1e-12, c0, 1.0 + 0j)
    aligned = residual0 / scale[:, None]
    residual_basis = np.vstack([model["mean"], model["pcs"]])
    fit_aligned, coeffs_res, _rel_res = fit_basis(aligned, residual_basis)
    coeffs_res = smooth_coeffs(coeffs_res, residual_smooth_epochs)
    fit_aligned = coeffs_res @ residual_basis
    fit_total = fit0 + scale[:, None] * fit_aligned
    residual = iq - fit_total
    denom = np.maximum(np.linalg.norm(iq, axis=1), 1e-12)
    rel = np.linalg.norm(residual, axis=1) / denom
    return residual, rel0, rel, coeffs0, coeffs_res


def residualized_template_map(iq_seg, scale_seg, dt, model, ktaps, K, taps, tau_grid):
    """Delay-Doppler map using templates after the same path0 subspace projection.

    Near-delay path1 is partially absorbed by the K+dK path0 fit. Searching the
    residual with the original K then biases the peak later. This diagnostic map
    correlates against P_perp K_delta, where P_perp removes the local path0 basis
    [K, dK, c0 * residual_basis].
    """
    residual_basis = np.vstack([model["mean"], model["pcs"]])
    k_shifted = np.vstack([ftp.kern_at(ktaps, K, taps - tau) for tau in tau_grid])
    g = np.empty((iq_seg.shape[0], len(tau_grid)), dtype=np.complex128)
    for n, y in enumerate(iq_seg):
        basis = np.vstack([model["k0"], model["dk"], scale_seg[n] * residual_basis])
        B = basis.T
        coeffs = np.linalg.lstsq(B, k_shifted.T, rcond=None)[0]
        projected = (B @ coeffs).T
        eff = k_shifted - projected
        den = np.maximum(np.linalg.norm(eff, axis=1), 1e-12)
        g[n] = (y @ np.conj(eff).T) / den
    win = np.hanning(g.shape[0])[:, None] if g.shape[0] >= 8 else np.ones((g.shape[0], 1))
    G = np.fft.fftshift(np.fft.fft(g * win, axis=0), axes=0)
    freqs = np.fft.fftshift(np.fft.fftfreq(g.shape[0], d=dt))
    return np.abs(G), freqs


def map_target_stats(iq_all, keep, dt, ktaps, K, taps, tau_grid, chip_m,
                     segment_s, target_m, target_band_m, guard_hz,
                     project_model=None, path0_scale=None):
    seg_ep = max(64, int(segment_s / dt))
    if guard_hz is None:
        guard_hz = 3.0 / (seg_ep * dt)
    target_cols = np.where(np.abs(tau_grid * chip_m - target_m) <= target_band_m)[0]
    if len(target_cols) == 0:
        raise ValueError("target band %.1f +/- %.1f m is outside delay grid" % (target_m, target_band_m))

    rows = []
    first = None
    for a, b in p0diag.dd.contiguous_runs(keep):
        for s in range(a, b, seg_ep):
            e = min(s + seg_ep, b)
            if e - s < max(64, seg_ep // 2):
                continue
            if project_model is None:
                M, freqs = p0diag.dd.delay_doppler_map(iq_all[s:e], dt, ktaps, K, taps, tau_grid)
            else:
                M, freqs = residualized_template_map(iq_all[s:e], path0_scale[s:e], dt,
                                                     project_model, ktaps, K, taps, tau_grid)
            p0 = np.unravel_index(int(np.argmax(M)), M.shape)
            f0 = float(freqs[p0[0]])
            off_f0 = np.abs(freqs - f0) >= guard_hz
            Mo = M[off_f0, :]
            fo = freqs[off_f0]
            best = np.unravel_index(int(np.argmax(Mo)), Mo.shape)
            best_amp = float(Mo[best])
            best_delay = float(tau_grid[best[1]] * chip_m)
            best_f = float(fo[best[0]])
            Mt = Mo[:, target_cols]
            tgt = np.unravel_index(int(np.argmax(Mt)), Mt.shape)
            tgt_amp = float(Mt[tgt])
            tgt_delay = float(tau_grid[target_cols[tgt[1]]] * chip_m)
            tgt_f = float(fo[tgt[0]])
            noise = float(np.median(Mo))
            tgt_snr = 20.0 * np.log10(tgt_amp / noise) if noise > 0 else float("nan")
            rel_db = 20.0 * np.log10(tgt_amp / best_amp) if best_amp > 0 else float("nan")
            rows.append(dict(best_delay_m=best_delay, best_f_hz=best_f,
                             target_delay_m=tgt_delay, target_f_hz=tgt_f,
                             target_vs_best_db=rel_db, target_snr_db=tgt_snr))
            if first is None:
                first = (M, freqs, p0, best, target_cols, tgt)
    return rows, first, guard_hz


def verdict_from_rows(rows, target_m, target_band_m):
    if not rows:
        return "UNRELIABLE: no analyzable segments"
    best = np.asarray([r["best_delay_m"] for r in rows], dtype=float)
    target_vs_best = np.asarray([r["target_vs_best_db"] for r in rows], dtype=float)
    target_delay = np.asarray([r["target_delay_m"] for r in rows], dtype=float)
    target_hit = np.abs(best - target_m) <= target_band_m
    strong_margin = target_vs_best >= -3.0
    delay_std = float(np.std(target_delay))
    if np.mean(target_hit) >= 0.8 and np.mean(strong_margin) >= 0.8 and delay_std <= max(3.0, target_band_m):
        return "PASS: target is dominant and stable"
    return ("FAIL: target_hit %.0f%%, margin>=-3dB %.0f%%, target_delay_std %.1f m" %
            (100.0 * np.mean(target_hit), 100.0 * np.mean(strong_margin), delay_std))


def run_map(label, iq, keep, dt, ktaps, K, taps, tau_grid, args, plot_prefix=None,
            project_model=None, path0_scale=None):
    print("\n========== %s ==========" % label)
    rows, first, _guard = map_target_stats(
        iq, keep, dt, ktaps, K, taps, tau_grid, args.chip_m,
        args.segment_s, args.target_m, args.target_band_m, None,
        project_model, path0_scale)
    p0diag.print_stats(label, rows)
    print("VERDICT:", verdict_from_rows(rows, args.target_m, args.target_band_m))
    if plot_prefix:
        safe = label.lower().replace(" ", "_").replace("+", "plus")
        p0diag.plot_first(first, tau_grid, args.chip_m,
                          "%s_%s.png" % (plot_prefix, safe),
                          label)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path0-dense", required=True)
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--chip-m", type=float, default=29.3)
    ap.add_argument("--target-m", type=float, required=True)
    ap.add_argument("--target-band-m", type=float, default=5.0)
    ap.add_argument("--ratio-db", type=float, default=-6.0)
    ap.add_argument("--drift-hz", type=float, default=250.0)
    ap.add_argument("--phase-deg", type=float, default=0.0)
    ap.add_argument("--residual-pcs", type=int, default=4)
    ap.add_argument("--max-epochs", type=int, default=20000)
    ap.add_argument("--train-epochs", type=int, default=12000)
    ap.add_argument("--cn0-min", type=float, default=45.0)
    ap.add_argument("--lock-min", type=float, default=0.6)
    ap.add_argument("--min-lock-run", type=int, default=1000)
    ap.add_argument("--settle-epochs", type=int, default=200)
    ap.add_argument("--segment-s", type=float, default=2.0)
    ap.add_argument("--dmax-chips", type=float, default=3.0)
    ap.add_argument("--tau-step", type=float, default=0.05)
    ap.add_argument("--residual-smooth-ms", type=float, default=0.0,
                    help="moving-average smoothing for residual-basis coefficients; 0 disables")
    ap.add_argument("--plot-prefix")
    args = ap.parse_args()

    ktaps, K = ftp.load_reference_csv(args.kernel)
    real_iq, times, dt, taps, fs, n_seg, n_kept = fsyn.load_locked_dense(
        args.path0_dense, args.cn0_min, args.lock_min,
        args.min_lock_run, args.settle_epochs)
    n = min(len(real_iq), args.max_epochs)
    train_n = min(len(real_iq), args.train_epochs)
    real_iq = real_iq[:n]
    times = times[:n]
    train_iq = real_iq[:train_n]
    keep = np.ones(n, dtype=bool)
    tau_grid = np.round(np.arange(-1.0, args.dmax_chips + 1e-9, args.tau_step), 4)

    c0 = fsyn.estimate_c0(real_iq, taps, ktaps, K)
    k0 = ftp.kern_at(ktaps, K, taps)
    clean_iq = c0[:, None] * k0[None, :]
    clean_syn = fsyn.inject_path1(clean_iq, times, taps, ktaps, K,
                                  args.target_m, args.chip_m, args.ratio_db,
                                  args.drift_hz, args.phase_deg)
    faithful_syn = fsyn.inject_path1(real_iq, times, taps, ktaps, K,
                                     args.target_m, args.chip_m, args.ratio_db,
                                     args.drift_hz, args.phase_deg)

    model = learn_residual_basis(train_iq, taps, ktaps, K, args.residual_pcs)
    print("path0 dense: %s" % args.path0_dense)
    print("kernel: %s" % os.path.basename(args.kernel))
    print("locked source segments: %d total / %d kept" % (n_seg, n_kept))
    print("epochs used: %d, train epochs: %d, fs %.1f MHz, dt %.3f ms" %
          (n, train_n, fs / 1e6, dt * 1e3))
    print("inject path1: delay %.1f m (%.3f chip), ratio %.1f dB, drift %+.2f Hz" %
          (args.target_m, args.target_m / args.chip_m, args.ratio_db, args.drift_hz))
    print("path0 model: K + dK/dtau + mean residual + %d residual PCs" % args.residual_pcs)
    smooth_epochs = max(1, int(round(args.residual_smooth_ms * 1e-3 / dt))) if args.residual_smooth_ms > 0 else 1
    if smooth_epochs > 1:
        print("residual-basis coefficient smoothing: %.1f ms (%d epochs)" %
              (args.residual_smooth_ms, smooth_epochs))
    print("training K+dK residual median %.4f, p90 %.4f" %
          (np.median(model["train_rel"]), np.percentile(model["train_rel"], 90)))
    if len(model["eig"]):
        rel_e = model["eig"] / max(float(model["eig"][0]), 1e-12)
        print("residual PC relative singular values:", " ".join("%.3f" % x for x in rel_e[:8]))

    run_map("clean synthetic before", clean_syn, keep, dt, ktaps, K, taps, tau_grid, args, args.plot_prefix)
    clean_res, clean_rel0, clean_rel, clean_c0, _cr = subtract_rich_path0(clean_syn, model, smooth_epochs)
    print("clean rich residual: K+dK median %.4f -> rich median %.4f" %
          (np.median(clean_rel0), np.median(clean_rel)))
    run_map("clean synthetic after rich path0", clean_res, keep, dt, ktaps, K, taps, tau_grid, args,
            args.plot_prefix, model, clean_c0[:, 0])

    run_map("faithful synthetic before", faithful_syn, keep, dt, ktaps, K, taps, tau_grid, args, args.plot_prefix)
    faithful_res, faithful_rel0, faithful_rel, faithful_c0, _cr = subtract_rich_path0(faithful_syn, model, smooth_epochs)
    print("faithful rich residual: K+dK median %.4f -> rich median %.4f" %
          (np.median(faithful_rel0), np.median(faithful_rel)))
    run_map("faithful synthetic after rich path0", faithful_res, keep, dt, ktaps, K, taps, tau_grid, args,
            args.plot_prefix, model, faithful_c0[:, 0])


if __name__ == "__main__":
    main()

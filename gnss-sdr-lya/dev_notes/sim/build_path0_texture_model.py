#!/usr/bin/env python3
"""Learn a regularized complex path0-residual texture model from A-only data.

The model is deliberately post-correlation: each dense tap vector is first fit
with the local path0 basis [K, dK/dtau].  The remaining complex residual is
normalized by the fitted prompt coefficient, then its mean and tap-domain
covariance are learned.  Track B uses the saved whitening transform in a GLRT
matched map so recurrent path0 texture is down-weighted rather than mistaken
for a second source.
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_two_path as ftp  # noqa: E402
import read_dense_correlator_dump as rd  # noqa: E402
from check_dense_vs_prompt import select_locked  # noqa: E402


def path0_basis(taps, ktaps, kernel):
    k0 = ftp.kern_at(ktaps, kernel, taps)
    step = max(1e-4, float(np.median(np.diff(taps))) * 0.25)
    kp = ftp.kern_at(ktaps, kernel, taps - step)
    km = ftp.kern_at(ktaps, kernel, taps + step)
    dk = (kp - km) / (2.0 * step)
    return np.column_stack((k0, dk))


def residualize_normalized(iq, basis):
    gram_inv = np.linalg.pinv(basis.T @ np.conj(basis))
    coeff = iq @ np.conj(basis) @ gram_inv
    residual = iq - coeff @ basis.T
    c0 = coeff[:, 0]
    scale = np.where(np.abs(c0) > 1e-8, c0, 1.0 + 0j)
    return residual / scale[:, None], coeff


def fit_texture_model(residual, shrinkage, eig_floor_fraction):
    mean = np.mean(residual, axis=0)
    centered = residual - mean[None, :]
    cov = centered.conj().T @ centered / max(1, len(centered) - 1)
    variance = max(float(np.trace(cov).real / cov.shape[0]), 1e-12)
    cov = (1.0 - shrinkage) * cov + shrinkage * variance * np.eye(cov.shape[0])
    eigval, eigvec = np.linalg.eigh(cov)
    floor = max(variance * eig_floor_fraction, 1e-12)
    eigval = np.maximum(eigval.real, floor)
    transform = eigvec @ np.diag(1.0 / np.sqrt(eigval))
    whitened = centered @ transform
    return {
        "mean": mean,
        "transform": transform,
        "eigenvalues": eigval,
        "variance": variance,
        "whitened_power_median": float(np.median(np.sum(np.abs(whitened) ** 2, axis=1))),
        "whitened_power_p99": float(np.percentile(np.sum(np.abs(whitened) ** 2, axis=1), 99)),
    }


def load_model(path):
    data = np.load(path, allow_pickle=False)
    return {
        "taps": data["taps_chips"].astype(np.float64),
        "mean": data["residual_mean"].astype(np.complex128),
        "transform": data["whitening_transform"].astype(np.complex128),
        "eigenvalues": data["covariance_eigenvalues"].astype(np.float64),
        "meta": json.loads(str(data["meta_json"])),
    }


def whiten_residual(iq, basis, model):
    residual, coeff = residualize_normalized(iq, basis)
    centered = residual - model["mean"][None, :]
    return centered @ model["transform"], coeff


def whiten_template(template, basis, model):
    projection = basis @ (np.linalg.pinv(basis) @ template)
    effective = template - projection
    return effective @ model["transform"]


def self_test():
    rng = np.random.default_rng(20260731)
    taps = np.arange(-1.5, 1.5001, 0.1)
    kernel = ftp.synth_kernel(taps).astype(np.complex128)
    basis = path0_basis(taps, taps, kernel)
    n = 5000
    shared = (
        rng.standard_normal(n) + 1j * rng.standard_normal(n)
    )[:, None] * np.exp(-0.5 * ((taps - 0.7) / 0.25) ** 2)[None, :]
    white = 0.2 * (
        rng.standard_normal((n, len(taps))) + 1j * rng.standard_normal((n, len(taps)))
    )
    coeff = np.column_stack((np.ones(n, dtype=np.complex128), np.zeros(n)))
    iq = coeff @ basis.T + 0.35 * shared + white
    residual, _ = residualize_normalized(iq, basis)
    model = fit_texture_model(residual[:3000], 0.05, 1e-3)
    def observable_condition(covariance):
        eig = np.linalg.eigvalsh(covariance).real
        observable = eig[eig > max(eig) * 1e-8]
        return float(max(observable) / min(observable))

    before_cov = (
        residual[3000:].conj().T @ residual[3000:]
    ) / len(residual[3000:])
    before = observable_condition(before_cov)
    after_residual = (residual[3000:] - model["mean"][None, :]) @ model["transform"]
    after_cov = (
        (after_residual.conj().T @ after_residual) / len(after_residual)
    )
    after = observable_condition(after_cov)
    print("self-test covariance condition before %.1f after %.1f" % (before, after))
    if not np.isfinite(after) or after >= before:
        raise SystemExit("self-test failed: whitening did not improve covariance")
    print("SELF-TEST PASS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dense", action="append", help="A-only dense .dat.json; repeat to pool runs")
    ap.add_argument("--kernel", help="same-PRN coherent reference CSV")
    ap.add_argument("--output", help="output texture-model .npz")
    ap.add_argument("--cn0-min", type=float, default=35.0)
    ap.add_argument("--lock-min", type=float, default=0.6)
    ap.add_argument("--min-lock-run", type=int, default=1000)
    ap.add_argument("--settle-epochs", type=int, default=200)
    ap.add_argument("--max-records-per-dense", type=int, default=20000)
    ap.add_argument("--shrinkage", type=float, default=0.10)
    ap.add_argument("--eig-floor-fraction", type=float, default=1e-3)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.dense or not args.kernel or not args.output:
        ap.error("--dense, --kernel, and --output are required unless --self-test is used")
    if not 0.0 <= args.shrinkage <= 1.0:
        ap.error("--shrinkage must be in [0,1]")

    ktaps, kernel = ftp.load_reference_csv(args.kernel)
    all_residual = []
    taps = None
    source_rows = []
    for dense_path in args.dense:
        _, binary, meta = rd.load_metadata(dense_path)
        records = rd.read_records(binary, meta)
        current_taps = np.asarray(meta["taps_chips"], dtype=np.float64)
        if taps is None:
            taps = current_taps
        elif len(taps) != len(current_taps) or not np.allclose(taps, current_taps):
            raise SystemExit("tap grid mismatch: %s" % dense_path)
        keep, n_segments, n_kept = select_locked(
            records, args.cn0_min, args.lock_min, 0,
            args.min_lock_run, args.settle_epochs
        )
        iq = records["tap_iq"].astype(np.complex128)[keep]
        if args.max_records_per_dense > 0 and len(iq) > args.max_records_per_dense:
            indices = np.linspace(0, len(iq) - 1, args.max_records_per_dense).astype(int)
            iq = iq[indices]
        if not len(iq):
            print("SKIP no sustained records: %s" % dense_path)
            continue
        basis = path0_basis(taps, ktaps, kernel)
        residual, _ = residualize_normalized(iq, basis)
        all_residual.append(residual)
        source_rows.append({
            "dense": os.path.abspath(dense_path),
            "segments": int(n_segments),
            "kept": int(n_kept),
            "used": int(len(iq)),
        })
    if not all_residual:
        raise SystemExit("no A-only records survived")

    residual = np.vstack(all_residual)
    fitted = fit_texture_model(residual, args.shrinkage, args.eig_floor_fraction)
    meta = {
        "format": "path0_texture_model_v1",
        "kernel": os.path.abspath(args.kernel),
        "sources": source_rows,
        "records": int(len(residual)),
        "shrinkage": args.shrinkage,
        "eig_floor_fraction": args.eig_floor_fraction,
        "variance": fitted["variance"],
        "whitened_power_median": fitted["whitened_power_median"],
        "whitened_power_p99": fitted["whitened_power_p99"],
    }
    np.savez_compressed(
        args.output,
        taps_chips=taps,
        residual_mean=fitted["mean"].astype(np.complex64),
        whitening_transform=fitted["transform"].astype(np.complex64),
        covariance_eigenvalues=fitted["eigenvalues"],
        meta_json=np.asarray(json.dumps(meta, sort_keys=True)),
    )
    print("wrote %s" % args.output)
    print(
        "records=%d taps=%d sources=%d variance=%.4g whitened power median=%.2f p99=%.2f"
        % (
            len(residual), len(taps), len(source_rows), fitted["variance"],
            fitted["whitened_power_median"], fitted["whitened_power_p99"],
        )
    )


if __name__ == "__main__":
    main()

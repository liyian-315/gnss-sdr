#!/usr/bin/env python3
"""Generate a geometry-driven two-source dense-correlator data set.

The receiver moves between two fixed transmitters.  Geometry determines the
relative code delay and carrier phase at every epoch.  Path0 can be either an
ideal kernel or real A-only dense-correlator records, which preserves measured
tracking-loop texture for faithful synthetic tests.
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diagnose_faithful_path0_synthetic as faithful  # noqa: E402
import fit_two_path as ftp  # noqa: E402


C_MPS = 299792458.0


def parse_pair(value):
    parts = [float(x) for x in value.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("coordinate must be x,y")
    return np.asarray(parts, dtype=np.float64)


def parse_grid(value):
    parts = [float(x) for x in value.split(":")]
    if len(parts) != 3 or parts[1] <= 0 or parts[2] < parts[0]:
        raise argparse.ArgumentTypeError("grid must be start:step:stop")
    return np.arange(parts[0], parts[2] + 0.5 * parts[1], parts[1])


def geometry(times, tx0, tx1, rx_start, rx_end, carrier_hz):
    fraction = times / max(float(times[-1]), np.finfo(float).eps)
    rx = rx_start[None, :] + fraction[:, None] * (rx_end - rx_start)[None, :]
    range0 = np.linalg.norm(rx - tx0[None, :], axis=1)
    range1 = np.linalg.norm(rx - tx1[None, :], axis=1)
    delta_m = range1 - range0
    phase_rad = -2.0 * np.pi * delta_m * carrier_hz / C_MPS
    if len(times) > 1:
        delta_doppler_hz = np.gradient(np.unwrap(phase_rad), times) / (2.0 * np.pi)
    else:
        delta_doppler_hz = np.zeros_like(times)
    return rx, range0, range1, delta_m, phase_rad, delta_doppler_hz


def ideal_path0(times, taps, ktaps, kernel, rng, noise_sigma):
    k0 = ftp.kern_at(ktaps, kernel, taps)
    phase_wobble = 0.025 * np.sin(2.0 * np.pi * 0.37 * times)
    amplitude = 1.0 + 0.015 * np.sin(2.0 * np.pi * 0.21 * times + 0.4)
    path0 = (amplitude * np.exp(1j * phase_wobble))[:, None] * k0[None, :]
    if noise_sigma > 0:
        noise = noise_sigma * (
            rng.standard_normal(path0.shape) + 1j * rng.standard_normal(path0.shape)
        ) / np.sqrt(2.0)
        path0 = path0 + noise
    return path0


def normalized_texture(iq, taps, ktaps, kernel):
    coefficient = faithful.estimate_c0(iq, taps, ktaps, kernel)
    safe = np.maximum(np.abs(coefficient), 1e-12)
    coefficient = np.where(
        np.abs(coefficient) >= 1e-12,
        coefficient,
        safe.astype(np.complex128),
    )
    local_kernel = ftp.kern_at(ktaps, kernel, taps)
    return iq / coefficient[:, None] - local_kernel[None, :]


def shift_texture(texture_row, taps, delay_chips):
    sample_at = taps - delay_chips
    return (
        np.interp(sample_at, taps, texture_row.real, left=0.0, right=0.0)
        + 1j * np.interp(sample_at, taps, texture_row.imag, left=0.0, right=0.0)
    )


def smooth_texture_rows(texture, window):
    if window <= 1:
        return texture
    window = min(int(window), len(texture))
    if window % 2 == 0:
        window -= 1
    if window <= 1:
        return texture
    pad = window // 2
    padded = np.pad(texture, ((pad, pad), (0, 0)), mode="edge")
    cumulative = np.vstack(
        (np.zeros((1, texture.shape[1]), dtype=np.complex128),
         np.cumsum(padded, axis=0))
    )
    return (cumulative[window:] - cumulative[:-window]) / float(window)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, help="output compressed .npz")
    ap.add_argument("--kernel", help="single-source coherent reference CSV")
    ap.add_argument("--faithful-path0-dense", help="A-only dense .dat.json")
    ap.add_argument("--faithful-path1-dense",
                    help="B-only dense .dat.json used as measured path1 texture")
    ap.add_argument("--path1-kernel",
                    help="B-only coherent reference CSV; default: --kernel")
    ap.add_argument(
        "--path1-texture-mode",
        choices=("kernel", "smoothed", "epoch"),
        default="smoothed",
        help="kernel=coherent B-only shape; smoothed=shape plus slow residual; "
             "epoch=diagnostic raw residual including receiver noise",
    )
    ap.add_argument("--path1-texture-smooth-epochs", type=int, default=51,
                    help="post-decimation moving-average length for smoothed mode")
    ap.add_argument("--duration-s", type=float, default=30.0)
    ap.add_argument("--epoch-ms", type=float, default=10.0)
    ap.add_argument("--taps", type=parse_grid, default=parse_grid("-4:0.1:4"))
    ap.add_argument("--tx0", type=parse_pair, default=parse_pair("-15,0"))
    ap.add_argument("--tx1", type=parse_pair, default=parse_pair("15,0"))
    ap.add_argument("--rx-start", type=parse_pair, default=parse_pair("-8,-15"))
    ap.add_argument("--rx-end", type=parse_pair, default=parse_pair("-8,15"))
    ap.add_argument("--static", action="store_true", help="hold receiver at --rx-start")
    ap.add_argument("--carrier-hz", type=float, default=1176.45e6)
    ap.add_argument("--chip-m", type=float, default=29.3)
    ap.add_argument("--ratio-db", type=float, default=-6.0)
    ap.add_argument("--phase-deg", type=float, default=0.0)
    ap.add_argument("--noise-sigma", type=float, default=0.01)
    ap.add_argument("--seed", type=int, default=20260729)
    ap.add_argument("--cn0-min", type=float, default=45.0)
    ap.add_argument("--lock-min", type=float, default=0.6)
    ap.add_argument("--min-lock-run", type=int, default=1000)
    ap.add_argument("--settle-epochs", type=int, default=200)
    args = ap.parse_args()

    if args.kernel:
        ktaps, kernel = ftp.load_reference_csv(args.kernel)
    else:
        ktaps = np.asarray(args.taps, dtype=np.float64)
        kernel = ftp.synth_kernel(ktaps)

    rng = np.random.default_rng(args.seed)
    requested_dt = args.epoch_ms * 1e-3
    source = "ideal"
    if args.faithful_path0_dense:
        if not args.kernel:
            raise SystemExit("--faithful-path0-dense requires --kernel")
        raw_iq, raw_t, raw_dt, taps, _fs, _n_seg, _n_kept = faithful.load_locked_dense(
            args.faithful_path0_dense, args.cn0_min, args.lock_min,
            args.min_lock_run, args.settle_epochs)
        stride = max(1, int(round(requested_dt / raw_dt)))
        path0 = raw_iq[::stride]
        times = raw_t[::stride]
        keep = times <= args.duration_s
        path0, times = path0[keep], times[keep]
        times = times - times[0]
        source = "faithful"
    else:
        taps = np.asarray(args.taps, dtype=np.float64)
        n = max(2, int(np.floor(args.duration_s / requested_dt)) + 1)
        times = np.arange(n, dtype=np.float64) * requested_dt
        path0 = ideal_path0(times, taps, ktaps, kernel, rng, args.noise_sigma)

    if len(times) < 2:
        raise SystemExit("not enough epochs after source selection")

    path1_texture = None
    path1_source = "ideal"
    path1_kernel_path = args.path1_kernel or args.kernel
    path1_ktaps, path1_base_kernel = ktaps, kernel
    if args.faithful_path1_dense:
        if not path1_kernel_path:
            raise SystemExit("--faithful-path1-dense requires --path1-kernel or --kernel")
        b_ktaps, b_kernel = ftp.load_reference_csv(path1_kernel_path)
        path1_ktaps, path1_base_kernel = b_ktaps, b_kernel
        b_iq, _b_t, b_dt, b_taps, _b_fs, _b_n_seg, _b_n_kept = faithful.load_locked_dense(
            args.faithful_path1_dense, args.cn0_min, args.lock_min,
            args.min_lock_run, args.settle_epochs)
        if len(b_taps) != len(taps) or not np.allclose(b_taps, taps):
            raise SystemExit("path1 dense tap grid does not match path0")
        b_stride = max(1, int(round(requested_dt / b_dt)))
        b_iq = b_iq[::b_stride]
        count = min(len(path0), len(b_iq))
        path0, times, b_iq = path0[:count], times[:count], b_iq[:count]
        if count < 2:
            raise SystemExit("not enough common path0/path1 texture epochs")
        if args.path1_texture_mode != "kernel":
            path1_texture = normalized_texture(b_iq, taps, b_ktaps, b_kernel)
            if args.path1_texture_mode == "smoothed":
                path1_texture = smooth_texture_rows(
                    path1_texture, args.path1_texture_smooth_epochs
                )
        path1_source = "faithful"

    rx_end = args.rx_start if args.static else args.rx_end
    rx, range0, range1, delta_m, relative_phase, relative_doppler = geometry(
        times, args.tx0, args.tx1, args.rx_start, rx_end, args.carrier_hz)
    relative_phase = relative_phase - relative_phase[0] + np.radians(args.phase_deg)

    c0 = faithful.estimate_c0(path0, taps, ktaps, kernel)
    amplitude = np.median(np.abs(c0)) * 10.0 ** (args.ratio_db / 20.0)
    path1 = np.empty_like(path0, dtype=np.complex128)
    for i, delay_m in enumerate(delta_m):
        delay_chips = delay_m / args.chip_m
        k1 = ftp.kern_at(path1_ktaps, path1_base_kernel, taps - delay_chips)
        if path1_texture is not None:
            k1 = k1 + shift_texture(path1_texture[i], taps, delay_chips)
        path1[i] = amplitude * np.exp(1j * relative_phase[i]) * k1
    iq = path0 + path1

    meta = {
        "format": "moving_twosource_v1",
        "path0_source": source,
        "kernel": os.path.abspath(args.kernel) if args.kernel else "synthetic",
        "faithful_path0_dense": (
            os.path.abspath(args.faithful_path0_dense)
            if args.faithful_path0_dense else None
        ),
        "path1_source": path1_source,
        "faithful_path1_dense": (
            os.path.abspath(args.faithful_path1_dense)
            if args.faithful_path1_dense else None
        ),
        "path1_kernel": (
            os.path.abspath(path1_kernel_path)
            if args.faithful_path1_dense else None
        ),
        "path1_texture_mode": (
            args.path1_texture_mode if args.faithful_path1_dense else None
        ),
        "carrier_hz": args.carrier_hz,
        "chip_m": args.chip_m,
        "ratio_db": args.ratio_db,
        "tx0_xy_m": args.tx0.tolist(),
        "tx1_xy_m": args.tx1.tolist(),
        "rx_start_xy_m": args.rx_start.tolist(),
        "rx_end_xy_m": rx_end.tolist(),
        "static": args.static,
        "seed": args.seed,
    }
    np.savez_compressed(
        args.output,
        iq=iq.astype(np.complex64),
        path0_iq=path0.astype(np.complex64),
        path1_iq=path1.astype(np.complex64),
        times_s=times,
        taps_chips=taps,
        rx_xy_m=rx,
        range0_m=range0,
        range1_m=range1,
        delta_m=delta_m,
        delta_doppler_hz=relative_doppler,
        meta_json=np.asarray(json.dumps(meta, sort_keys=True)),
    )
    print("wrote %s" % args.output)
    print("epochs=%d taps=%d dt=%.3f ms path0=%s path1=%s" %
          (len(times), len(taps), np.median(np.diff(times)) * 1e3,
           source, path1_source))
    print("relative delay: %.2f..%.2f m (%.3f..%.3f chip)" %
          (delta_m.min(), delta_m.max(),
           delta_m.min() / args.chip_m, delta_m.max() / args.chip_m))
    print("relative Doppler: %+.3f..%+.3f Hz; path1/path0=%+.1f dB" %
          (relative_doppler.min(), relative_doppler.max(), args.ratio_db))


if __name__ == "__main__":
    main()

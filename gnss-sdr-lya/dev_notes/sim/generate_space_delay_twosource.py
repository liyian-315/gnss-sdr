#!/usr/bin/env python3
"""Generate a synthetic N-channel (ULA) two-source space-delay scene (static array track).

Writes an .npz consumed by fit_space_delay_twosource.py. Two same-code sources arrive
from known directions with a known delay difference; per-block random phases emulate the
two independent simulator clocks (the separation must come from the SHARED angle/delay
support, not the per-block phase). Real captures later replace this with measured
4-channel dense correlators + a measured array manifold; the estimator is unchanged.

Examples:
  # separable: two sources 30 deg apart, 0.5 chip, -6 dB
  python3 dev_notes/sim/generate_space_delay_twosource.py --theta0 0 --theta1 30 \
      --delay-chips 0.5 --ratio-db -6 --output /tmp/scene_sep.npz
  # degenerate control: same direction (must come back UNRESOLVED)
  python3 dev_notes/sim/generate_space_delay_twosource.py --theta0 0 --theta1 0 \
      --delay-chips 0.5 --output /tmp/scene_same.npz
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_space_delay_twosource as sd  # noqa: E402
import fit_two_path as ftp  # noqa: E402


def parse_taps(spec):
    start, step, stop = (float(x) for x in spec.split(":"))
    return np.round(np.arange(start, stop + 1e-9, step), 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, help="output .npz")
    ap.add_argument("--n-antennas", type=int, default=4, help="ULA elements (2 = single-B210 coherent proof)")
    ap.add_argument("--spacing-wl", type=float, default=0.5, help="element spacing in wavelengths")
    ap.add_argument("--theta0", type=float, default=0.0, help="path0 direction [deg]")
    ap.add_argument("--theta1", type=float, default=30.0, help="path1 direction [deg]")
    ap.add_argument("--delay-chips", type=float, default=0.5, help="path1 delay (path0 at 0) [chips]")
    ap.add_argument("--ratio-db", type=float, default=-6.0, help="path1/path0 amplitude [dB]")
    ap.add_argument("--chip-m", type=float, default=29.3, help="chip length [m] (L5=29.3)")
    ap.add_argument("--taps", default="-1.5:0.1:1.5", help="dense tap grid start:step:stop [chips]")
    ap.add_argument("--n-blocks", type=int, default=24, help="short time blocks (MMV)")
    ap.add_argument("--noise-sigma", type=float, default=0.05, help="complex noise std (kernel peak = 1)")
    ap.add_argument("--single-source", action="store_true", help="H0 control: emit path0 only")
    ap.add_argument("--kernel-csv", help="measured Phase A reference CSV; omit = synthetic kernel")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    taps = parse_taps(args.taps)
    if args.kernel_csv:
        ktaps, kernel = ftp.load_reference_csv(args.kernel_csv)
        kernel = np.interp(taps, ktaps, kernel.real) + 1j * np.interp(taps, ktaps, kernel.imag)
    kernel = ftp.synth_kernel(taps) if not args.kernel_csv else kernel

    rng = np.random.default_rng(args.seed)
    dense = sd.synth_dense(taps, taps, kernel, args.n_antennas, args.spacing_wl,
                           args.theta0, args.theta1, 0.0, args.delay_chips, args.ratio_db,
                           args.n_blocks, args.noise_sigma, rng, single_source=args.single_source)

    truth = dict(theta0=args.theta0, theta1=args.theta1, tau0=0.0, tau1=args.delay_chips,
                 ratio_db=args.ratio_db, chip_m=args.chip_m, single_source=args.single_source)
    meta = dict(n_antennas=args.n_antennas, spacing_wl=args.spacing_wl, chip_m=args.chip_m,
                noise_sigma=args.noise_sigma, kernel="measured" if args.kernel_csv else "synthetic",
                truth=truth)
    np.savez_compressed(args.output, dense=dense.astype(np.complex64), taps=taps,
                        meta_json=json.dumps(meta))
    print("wrote %s  (%d blocks x %d ant x %d taps, %s kernel)"
          % (args.output, dense.shape[0], dense.shape[1], dense.shape[2], meta["kernel"]))
    print("truth: theta0=%.0f theta1=%.0f delay=%.2f chip ratio=%.1f dB single_source=%s"
          % (args.theta0, args.theta1, args.delay_chips, args.ratio_db, args.single_source))


if __name__ == "__main__":
    main()

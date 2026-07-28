#!/usr/bin/env python3
"""Offline two-path (MEDLL-style) fit of a dense correlation profile.

Models an observed complex R(tau) as a sum of two shifted copies of the measured
single-source kernel K(tau) (a Phase A reference fingerprint):

    Y(tau) = c0 * K(tau - tau0) + c1 * K(tau - tau1)          (c0, c1 complex)

Given the two delays, c0/c1 are LINEAR least squares (variable projection), so the
only nonlinear search is over (tau0, tau1) -- robust even when the two paths merge
inside one main lobe (the sub-chip case classic peak-picking cannot resolve).

Outputs per fit: tau0, tau1, delta (chips + metres), amplitude ratio (dB),
relative phase (deg), fit residual, and a 1-path-vs-2-path residual drop used as a
second-path DETECTION signal.

The kernel comes from a Phase A TRUSTWORTHY reference CSV (coherent R). The
observed profile is another such CSV (the two-source composite, analysed the same
way). --self-test injects known two-path params into a synthetic kernel and
reports recovery accuracy -- run this first, before any real Phase B data.

Examples:
  python3 dev_notes/sim/fit_two_path.py --self-test --chip-m 29.3
  python3 dev_notes/sim/fit_two_path.py --kernel cn052_ref.csv \
      --observed phaseB_composite_ref.csv --chip-m 29.3 --plot fit.png
"""

import argparse
import io
import os

import numpy as np


def load_reference_csv(path):
    """Return (taps_chips, R_complex) from a check_dense_vs_prompt.py reference CSV."""
    with open(path) as fh:
        body = "".join(ln for ln in fh if not ln.lstrip().startswith("#"))
    d = np.genfromtxt(io.StringIO(body), delimiter=",", names=True)
    taps = np.atleast_1d(d["tap_chips"]).astype(float)
    re = np.atleast_1d(d["coherent_re"]).astype(float)
    im = np.atleast_1d(d["coherent_im"]).astype(float)
    order = np.argsort(taps)
    return taps[order], (re + 1j * im)[order]


def synth_kernel(taps, fwhm_chips=1.09):
    """Bandlimited single-source kernel ~ matching the measured L5 shape (FWHM ~1.09
    chips). Real, peak 1 at tau=0. For --self-test only; real runs load the CSV."""
    # a raised-cosine-ish lobe: 1 - (|t|/h)^2 smoothed, zero beyond ~1.5 chips
    h = fwhm_chips / np.sqrt(2.0)          # scale so half-max ~ fwhm/2
    k = np.maximum(0.0, 1.0 - (taps / (1.5)) ** 2)  # smooth lobe to ~1.5 chips
    tri = np.maximum(0.0, 1.0 - np.abs(taps) / (fwhm_chips))
    K = 0.5 * k + 0.5 * tri
    K = K / K.max()
    return K.astype(complex)


def kern_at(kernel_taps, K, x):
    """Interpolate the (complex) kernel at offsets x [chips]; 0 outside support."""
    re = np.interp(x, kernel_taps, K.real, left=0.0, right=0.0)
    im = np.interp(x, kernel_taps, K.imag, left=0.0, right=0.0)
    return re + 1j * im


def _fit_delays(taps, Y, ktaps, K, tau0, tau1):
    M = np.column_stack([kern_at(ktaps, K, taps - tau0),
                         kern_at(ktaps, K, taps - tau1)])
    c, _res, _rank, _sv = np.linalg.lstsq(M, Y, rcond=None)
    resid = float(np.linalg.norm(Y - M @ c))
    return c, resid


def fit_one_path(taps, Y, ktaps, K, tau_lo=-1.0, tau_hi=1.0, coarse=0.05, fine=0.01):
    best = (None, None, np.inf)
    for tau in np.arange(tau_lo, tau_hi + 1e-9, coarse):
        M = kern_at(ktaps, K, taps - tau)[:, None]
        c, *_ = np.linalg.lstsq(M, Y, rcond=None)
        r = float(np.linalg.norm(Y - M @ c))
        if r < best[2]:
            best = (float(tau), complex(c[0]), r)
    t = best[0]
    for tau in np.arange(t - coarse, t + coarse + 1e-9, fine):
        M = kern_at(ktaps, K, taps - tau)[:, None]
        c, *_ = np.linalg.lstsq(M, Y, rcond=None)
        r = float(np.linalg.norm(Y - M @ c))
        if r < best[2]:
            best = (float(tau), complex(c[0]), r)
    return best  # (tau, c, resid)


def fit_two_path(taps, Y, ktaps, K, tau0_lo=-2.0, tau0_hi=0.6, dmax=2.5,
                 coarse=0.05, fine=0.01):
    best = (None, None, None, None, np.inf)  # tau0, tau1, c0, c1, resid
    for tau0 in np.arange(tau0_lo, tau0_hi + 1e-9, coarse):
        for d in np.arange(0.05, dmax + 1e-9, coarse):
            c, r = _fit_delays(taps, Y, ktaps, K, tau0, tau0 + d)
            if r < best[4]:
                best = (float(tau0), float(tau0 + d), complex(c[0]), complex(c[1]), r)
    t0b, t1b = best[0], best[1]
    for tau0 in np.arange(t0b - coarse, t0b + coarse + 1e-9, fine):
        for tau1 in np.arange(t1b - coarse, t1b + coarse + 1e-9, fine):
            if tau1 - tau0 < 0.03:
                continue
            c, r = _fit_delays(taps, Y, ktaps, K, tau0, tau1)
            if r < best[4]:
                best = (float(tau0), float(tau1), complex(c[0]), complex(c[1]), r)
    return best


def summarize(fit2, fit1, Y, chip_m):
    tau0, tau1, c0, c1, r2 = fit2
    _, _, r1 = fit1
    ny = float(np.linalg.norm(Y))
    # order so path0 is the EARLIER (LOS candidate)
    if tau1 < tau0:
        tau0, tau1, c0, c1 = tau1, tau0, c1, c0
    a0, a1 = abs(c0), abs(c1)
    delta = tau1 - tau0
    return dict(
        tau0_chips=tau0, tau1_chips=tau1,
        delta_chips=delta, delta_m=delta * chip_m,
        amp0=a0, amp1=a1,
        amp_ratio_db=(20.0 * np.log10(a1 / a0) if a0 > 0 else float("nan")),
        phase_deg=float(np.degrees(np.angle((c1 / c0)))) if a0 > 0 else float("nan"),
        resid2_rel=r2 / ny if ny else float("nan"),
        resid1_rel=r1 / ny if ny else float("nan"),
        resid_drop=(1.0 - r2 / r1) if r1 else float("nan"),
    )


def self_test(chip_m):
    taps = np.round(np.arange(-2.0, 2.0001, 0.1), 3)   # wider window for larger delays
    K = synth_kernel(taps)
    ktaps = taps
    sigma = 0.002                                       # ~ measured worst-tap SEM
    print("self-test kernel FWHM ~1.09 chips; noise sigma=%.4f; chip=%.1f m" % (sigma, chip_m))
    print("  d_chip d_m   ar_db  phi   | rec_d_m  rec_ar  rec_phi  resid2  drop  det")
    print("  " + "-" * 78)
    rng = [(0.20, 0), (0.30, -3), (0.50, 0), (0.50, -6), (0.70, -3), (1.00, 0), (1.50, -6)]
    # deterministic pseudo-noise (no RNG: hashed sin), varied per case index
    for idx, (d, ar) in enumerate(rng):
        for phi in (0.0, 90.0, 180.0):
            c0 = 1.0 + 0j
            c1 = (10.0 ** (ar / 20.0)) * np.exp(1j * np.radians(phi))
            Y = c0 * kern_at(ktaps, K, taps - 0.0) + c1 * kern_at(ktaps, K, taps - d)
            seed = np.sin((np.arange(len(taps)) + 1) * (12.9898 + idx + phi)) * 43758.5453
            noise = (seed - np.floor(seed) - 0.5)
            seed2 = np.sin((np.arange(len(taps)) + 1) * (78.233 + idx + phi)) * 12345.6789
            noise2 = (seed2 - np.floor(seed2) - 0.5)
            Y = Y + sigma * (noise + 1j * noise2)
            f2 = fit_two_path(taps, Y, ktaps, K)
            f1 = fit_one_path(taps, Y, ktaps, K)
            s = summarize(f2, f1, Y, chip_m)
            det = "Y" if s["resid_drop"] > 0.5 and s["amp_ratio_db"] > -25 else "n"
            print("  %5.2f %5.1f  %+5.0f %4.0f | %7.1f  %+6.1f  %5.0f  %.4f  %.2f   %s"
                  % (d, d * chip_m, ar, phi,
                     s["delta_m"], s["amp_ratio_db"], (s["phase_deg"] % 360),
                     s["resid2_rel"], s["resid_drop"], det))
    print("\n  (rec_d_m should track d_m; rec_ar ~ ar_db; rec_phi ~ phi; small delta is the hard case)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", help="Phase A single-source reference CSV (the kernel K)")
    ap.add_argument("--observed", help="two-source composite reference CSV to fit")
    ap.add_argument("--chip-m", type=float, default=29.3, help="chip length in metres (L5=29.3, B1I=146.6, L1=293)")
    ap.add_argument("--self-test", action="store_true", help="inject known two-path params into a synthetic kernel and report recovery")
    ap.add_argument("--plot", help="PNG of observed vs fitted |R(tau)|")
    args = ap.parse_args()

    if args.self_test:
        self_test(args.chip_m)
        return
    if not (args.kernel and args.observed):
        raise SystemExit("need --kernel and --observed (or --self-test)")

    ktaps, K = load_reference_csv(args.kernel)
    taps, Y = load_reference_csv(args.observed)
    f2 = fit_two_path(taps, Y, ktaps, K)
    f1 = fit_one_path(taps, Y, ktaps, K)
    s = summarize(f2, f1, Y, args.chip_m)
    print("kernel:   %s" % os.path.basename(args.kernel))
    print("observed: %s" % os.path.basename(args.observed))
    print("--- two-path fit ---")
    print("  path0 (LOS/earliest): tau=%.3f chips   |A0|=%.3f" % (s["tau0_chips"], s["amp0"]))
    print("  path1 (later):        tau=%.3f chips   |A1|=%.3f" % (s["tau1_chips"], s["amp1"]))
    print("  delta   = %.3f chips = %.1f m" % (s["delta_chips"], s["delta_m"]))
    print("  amp ratio A1/A0 = %+.2f dB   relative phase = %+.0f deg" % (s["amp_ratio_db"], s["phase_deg"]))
    print("  fit residual (2-path) = %.4f   (1-path) = %.4f   drop = %.2f"
          % (s["resid2_rel"], s["resid1_rel"], s["resid_drop"]))
    detected = s["resid_drop"] > 0.5 and s["amp_ratio_db"] > -25 and s["delta_chips"] > 0.1
    print("  SECOND SOURCE: %s" % ("DETECTED" if detected else "not clearly detected (compare vs single-source baseline)"))

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        model = (s["amp0"] * 0)  # placeholder to keep flake happy
        c0 = s["amp0"]; c1 = s["amp1"]
        fitc = (c0 * kern_at(ktaps, K, taps - s["tau0_chips"])
                + (c1 * np.exp(1j * np.radians(s["phase_deg"]))) * kern_at(ktaps, K, taps - s["tau1_chips"]))
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(taps, np.abs(Y), "o-", ms=3, label="observed |R|")
        ax.plot(taps, np.abs(fitc), "-", label="two-path fit |R|")
        ax.axvline(s["tau0_chips"], color="g", ls="--", lw=0.8, label="path0")
        ax.axvline(s["tau1_chips"], color="r", ls="--", lw=0.8, label="path1")
        ax.set_xlabel("tau [chips]"); ax.set_ylabel("|R|"); ax.grid(True, alpha=0.3); ax.legend()
        ax.set_title("two-path fit  delta=%.1f m  A1/A0=%+.1f dB" % (s["delta_m"], s["amp_ratio_db"]))
        fig.tight_layout(); fig.savefig(args.plot, dpi=150)
        print("plot -> %s" % args.plot)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Aggregate Phase A reference R(tau) fingerprints across repeated runs.

Consumes reference CSVs written by check_dense_vs_prompt.py --ref-csv
(header: tap_chips,coherent_re,coherent_im,mag_mean,mag_std).

The point (per user + Codex 2026-07-26): one clean-peak plot is not a baseline.
For each simulator power / RF condition, describe the clean single-source
fingerprint by STABLE STATISTICS over >=3 repeats, not one lucky run.

Per-run features extracted from the normalized magnitude shape (R(0)=1):
  peak_chip     sub-tap peak position (parabolic), should ~= 0.0
  fwhm_chips    full width at half maximum of |R| = main-lobe width
  asym_max      max ||R(+tau)|-|R(-tau)||  (0 = perfectly symmetric clean path)
  skew_chips    centroid of the main lobe (|tau|<=1 chip); signed asymmetry
  noise_floor   median |R| for |tau|>=1 chip (sidelobe/noise level)
  tap_std_mean  mean per-tap epoch std inside the run (run-internal jitter)

Runs are grouped by label (default: parent directory name) and reported as
mean +/- std per group, so a high-variance outlier (e.g. an unstable L5 run)
shows up as large std instead of being averaged away.

Example (three L5 -50 repeats, chip=29.3 m):
  python3 dev_notes/sim/aggregate_reference_fingerprint.py \
    run1/l5_phaseA_reference_Rtau.png.csv \
    run2/l5_phaseA_reference_Rtau.png.csv \
    run3/l5_phaseA_reference_Rtau.png.csv \
    --labels l5_-50,l5_-50,l5_-50 --chip-m 29.3 --plot l5_-50_fingerprint.png
"""

import argparse
import io
import os

import numpy as np


def load_meta(path):
    """Parse leading '#' metadata line(s) written by check_dense_vs_prompt.py."""
    meta = {}
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if not s.startswith("#"):
                break
            for tok in s[1:].split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    meta[k] = v
    return meta


def load_csv(path):
    # strip '#' metadata lines ourselves so names=True reads the real header
    with open(path) as fh:
        body = "".join(ln for ln in fh if not ln.lstrip().startswith("#"))
    d = np.genfromtxt(io.StringIO(body), delimiter=",", names=True)
    taps = np.atleast_1d(d["tap_chips"]).astype(float)
    mag = np.atleast_1d(d["mag_mean"]).astype(float)
    tap_std = np.atleast_1d(d["mag_std"]).astype(float) if "mag_std" in d.dtype.names else np.full_like(mag, np.nan)
    order = np.argsort(taps)
    return taps[order], mag[order], tap_std[order], load_meta(path)


def _half_cross(taps, mag, i, direction, level):
    j = i
    n = len(mag)
    while 0 <= j + direction < n:
        k = j + direction
        if mag[k] < level:
            t1, t2, m1, m2 = taps[j], taps[k], mag[j], mag[k]
            if m1 == m2:
                return float(t2)
            return float(t1 + (m1 - level) / (m1 - m2) * (t2 - t1))
        j = k
    return None  # never dropped below half within the tap span


def features(taps, mag, tap_std):
    step = float(taps[1] - taps[0]) if len(taps) > 1 else 1.0
    i = int(np.argmax(mag))
    peak_chip, peak_val = float(taps[i]), float(mag[i])
    if 0 < i < len(mag) - 1:                       # parabolic sub-tap peak
        y0, y1, y2 = float(mag[i - 1]), float(mag[i]), float(mag[i + 1])
        denom = y0 - 2 * y1 + y2
        if denom != 0.0:
            delta = 0.5 * (y0 - y2) / denom
            peak_chip = float(taps[i]) + delta * step
            peak_val = y1 - 0.25 * (y0 - y2) * delta

    half = 0.5 * peak_val
    left = _half_cross(taps, mag, i, -1, half)
    right = _half_cross(taps, mag, i, +1, half)
    fwhm = (right - left) if (left is not None and right is not None) else float("nan")

    symmetric = np.allclose(taps, -taps[::-1], atol=1e-6)
    asym_max = float(np.max(np.abs(mag - mag[::-1]))) if symmetric else float("nan")

    lobe = np.abs(taps) <= 1.0
    skew = float(np.sum(taps[lobe] * mag[lobe]) / np.sum(mag[lobe])) if lobe.any() else float("nan")

    far = np.abs(taps) >= 1.0
    noise_floor = float(np.median(mag[far])) if far.any() else float("nan")

    tap_std_mean = float(np.nanmean(tap_std))
    return dict(peak_chip=peak_chip, fwhm_chips=fwhm, asym_max=asym_max,
                skew_chips=skew, noise_floor=noise_floor, tap_std_mean=tap_std_mean)


FEATURE_KEYS = ["peak_chip", "fwhm_chips", "asym_max", "skew_chips", "noise_floor", "tap_std_mean"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+", help="reference_Rtau CSV files (check_dense_vs_prompt.py --ref-csv)")
    ap.add_argument("--labels", help="comma list, one per csv; default = each file's parent dir name")
    ap.add_argument("--chip-m", type=float, help="chip length in meters (L1 C/A=293.0, B1I=146.6, L5=29.3) to also print widths in meters")
    ap.add_argument("--min-kept-fraction", type=float, default=0.2,
                    help="flag runs/conditions whose sustained-locked kept fraction is below this")
    ap.add_argument("--plot", help="overlay |R(tau)| of all runs to this PNG")
    args = ap.parse_args()

    if args.labels:
        labels = args.labels.split(",")
        if len(labels) != len(args.csvs):
            raise SystemExit("--labels count %d != csv count %d" % (len(labels), len(args.csvs)))
    else:
        labels = [os.path.basename(os.path.dirname(os.path.abspath(p))) or "." for p in args.csvs]

    runs = []
    for path, label in zip(args.csvs, labels):
        taps, mag, tap_std, meta = load_csv(path)
        feat = features(taps, mag, tap_std)
        kept_frac = float(meta["kept_fraction"]) if "kept_fraction" in meta else float("nan")
        runs.append((label, path, taps, mag, feat, kept_frac))

    # ---- per-run table ----
    print("=== per-run fingerprint features ===")
    hdr = "label            peak_chip  fwhm_chips  asym_max  skew_chips  noise_floor  tap_std_mean  kept%  file"
    print(hdr); print("-" * len(hdr))
    for label, path, _taps, _mag, f, kf in runs:
        kfs = ("%5.1f" % (100 * kf)) if np.isfinite(kf) else "   NA"
        flag = "  <LOW-KEPT>" if (np.isfinite(kf) and kf < args.min_kept_fraction) else ""
        print("%-15s  %+8.4f  %10.4f  %8.4f  %+9.4f  %11.5f  %12.5f  %s  %s%s"
              % (label, f["peak_chip"], f["fwhm_chips"], f["asym_max"], f["skew_chips"],
                 f["noise_floor"], f["tap_std_mean"], kfs, os.path.basename(path), flag))

    # ---- per-group mean +/- std ----
    print("\n=== per-group baseline (mean +/- std over repeats) ===")
    groups = {}
    for label, _p, _t, _m, f, kf in runs:
        groups.setdefault(label, []).append((f, kf))
    for label, items in groups.items():
        flist = [it[0] for it in items]
        kfs = [it[1] for it in items]
        n = len(flist)
        print("[%s] n=%d" % (label, n))
        for key in FEATURE_KEYS:
            vals = np.array([fl[key] for fl in flist], dtype=float)
            mean, std = np.nanmean(vals), (np.nanstd(vals) if n > 1 else 0.0)
            line = "    %-13s %+10.4f  +/- %8.4f" % (key, mean, std)
            if args.chip_m and key in ("peak_chip", "fwhm_chips", "skew_chips"):
                line += "   (%.2f +/- %.2f m)" % (mean * args.chip_m, std * args.chip_m)
            print(line)
        valid_kf = [k for k in kfs if np.isfinite(k)]
        if valid_kf:
            below = sum(1 for k in valid_kf if k < args.min_kept_fraction)
            print("    kept_fraction  mean %.1f%%  min %.1f%%  (%d/%d below %.0f%%)%s"
                  % (100 * np.mean(valid_kf), 100 * min(valid_kf), below, len(valid_kf),
                     100 * args.min_kept_fraction,
                     "  <-- UNDER-SAMPLED CONDITION, treat fingerprint as low-confidence" if below else ""))
        if n >= 3:
            fwhm = np.array([fl["fwhm_chips"] for fl in flist])
            asym = np.array([fl["asym_max"] for fl in flist])
            cv = np.nanstd(fwhm) / np.nanmean(fwhm) if np.nanmean(fwhm) else float("nan")
            print("    stability: FWHM CV=%.1f%%  asym range=[%.4f, %.4f]%s"
                  % (100 * cv, np.nanmin(asym), np.nanmax(asym),
                     "  <-- OUTLIER RUN, do not average blindly" if np.nanmax(asym) > 3 * np.nanmin(asym) + 0.01 else ""))

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        color_of, seen = {}, set()
        fig, ax = plt.subplots(figsize=(10, 6))
        for label, _p, taps, mag, _f, _kf in runs:
            color_of.setdefault(label, colors[len(color_of) % len(colors)])
            ax.plot(taps, mag, lw=1.0, alpha=0.7, color=color_of[label],
                    label=None if label in seen else label)
            seen.add(label)
        ax.axvline(0.0, color="k", ls="--", lw=0.6)
        ax.axhline(0.5, color="gray", ls=":", lw=0.6)
        ax.set_xlabel("tap offset [chips]"); ax.set_ylabel("normalized |R(tau)|")
        ax.set_title("Phase A reference R(tau) overlay (%d runs)" % len(runs))
        ax.grid(True, alpha=0.3); ax.legend()
        fig.tight_layout(); fig.savefig(args.plot, dpi=150)
        print("\noverlay plot -> %s" % args.plot)


if __name__ == "__main__":
    main()

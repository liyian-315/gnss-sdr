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


def max_tap_sem(tap_std, n_kept):
    """Worst-tap standard error of the averaged |R(tau)|: max_tap(tap_std)/sqrt(N).

    This is the principled precision of the fingerprint -- how well-determined each
    averaged tap is -- and it depends on the ABSOLUTE epoch count, not the kept
    fraction. (Averaging noise falls as 1/sqrt(N); even a low-kept-fraction run has
    thousands of clean epochs in a 30 s decim=1 capture.)
    """
    if not (np.isfinite(n_kept) and n_kept > 0):
        return float("nan")
    finite = tap_std[np.isfinite(tap_std)]
    if not len(finite):
        return float("nan")
    return float(np.max(finite) / np.sqrt(n_kept))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+", help="reference_Rtau CSV files (check_dense_vs_prompt.py --ref-csv)")
    ap.add_argument("--labels", help="comma list, one per csv; default = each file's parent dir name")
    ap.add_argument("--chip-m", type=float, help="chip length in meters (L1 C/A=293.0, B1I=146.6, L5=29.3) to also print widths in meters")
    ap.add_argument("--min-epochs", type=int, default=2000,
                    help="measurability floor on ABSOLUTE kept epochs. Naive SEM=tap_std/sqrt(N) "
                         "assumes independent epochs, but tracking epochs are correlated over the loop "
                         "memory (~tens of ms), so effective N << raw N; ~2000 raw (~2 s at decim=1) "
                         "keeps enough effectively-independent samples. Not a kept-fraction gate.")
    ap.add_argument("--sem-target", type=float, default=0.002,
                    help="precision target: worst-tap SEM of |R(tau)| should be <= this "
                         "(default 0.002 ~= 1/8 of the ~0.016 clean asymmetry)")
    ap.add_argument("--fwhm-cv-max", type=float, default=0.02,
                    help="reproducibility: max cross-run FWHM coefficient of variation to call a condition reproducible")
    ap.add_argument("--asym-std-max", type=float, default=0.003,
                    help="reproducibility: max cross-run std of asym_max to call a condition reproducible")
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
        n_kept = int(meta["kept_records"]) if "kept_records" in meta else (
            int(round(kept_frac * int(meta["total_records"]))) if ("kept_fraction" in meta and "total_records" in meta) else -1)
        sem = max_tap_sem(tap_std, n_kept)
        runs.append((label, path, taps, mag, feat, kept_frac, n_kept, sem))

    # ---- per-run table (precision = SEM; kept% is diagnostic only) ----
    print("=== per-run fingerprint features ===")
    hdr = "label            peak_chip  fwhm_chips  asym_max   N_kept  max_SEM   kept%(diag)  file"
    print(hdr); print("-" * len(hdr))
    for label, path, _taps, _mag, f, kf, nk, sem in runs:
        kfs = ("%4.0f" % (100 * kf)) if np.isfinite(kf) else "  NA"
        nks = ("%7d" % nk) if nk >= 0 else "     NA"
        sems = ("%.5f" % sem) if np.isfinite(sem) else "   NA"
        under = "  <under-sampled>" if (nk >= 0 and nk < args.min_epochs) else ""
        print("%-15s  %+8.4f  %10.4f  %8.4f  %s  %s      %s%%   %s%s"
              % (label, f["peak_chip"], f["fwhm_chips"], f["asym_max"], nks, sems, kfs,
                 os.path.basename(path), under))

    # ---- per-group: means, precision, reproducibility, verdict ----
    print("\n=== per-group baseline (mean +/- std over repeats) ===")
    groups = {}
    for r in runs:
        groups.setdefault(r[0], []).append(r)
    for label, items in groups.items():
        flist = [r[4] for r in items]
        nks = [r[6] for r in items]
        sems = [r[7] for r in items]
        n = len(flist)
        print("[%s] n=%d" % (label, n))
        for key in FEATURE_KEYS:
            vals = np.array([fl[key] for fl in flist], dtype=float)
            mean, std = np.nanmean(vals), (np.nanstd(vals) if n > 1 else 0.0)
            line = "    %-13s %+10.4f  +/- %8.4f" % (key, mean, std)
            if args.chip_m and key in ("peak_chip", "fwhm_chips", "skew_chips"):
                line += "   (%.2f +/- %.2f m)" % (mean * args.chip_m, std * args.chip_m)
            print(line)

        # measurability + precision
        min_nk = min([x for x in nks if x >= 0], default=-1)
        worst_sem = np.nanmax(sems) if any(np.isfinite(s) for s in sems) else float("nan")
        measurable = (min_nk < 0) or (min_nk >= args.min_epochs)   # unknown N -> don't fail on it
        precise = np.isfinite(worst_sem) and worst_sem <= args.sem_target
        print("    precision:     min N_kept=%s   worst max-SEM=%s (target %.4f)"
              % (("unknown" if min_nk < 0 else str(min_nk)),
                 ("%.5f" % worst_sem if np.isfinite(worst_sem) else "NA"), args.sem_target))

        # reproducibility across repeats
        fwhm = np.array([fl["fwhm_chips"] for fl in flist], dtype=float)
        asym = np.array([fl["asym_max"] for fl in flist], dtype=float)
        peak = np.array([fl["peak_chip"] for fl in flist], dtype=float)
        cv = float(np.nanstd(fwhm) / np.nanmean(fwhm)) if np.nanmean(fwhm) else float("nan")
        asym_std = float(np.nanstd(asym))
        reproducible = (n >= 2) and np.isfinite(cv) and (cv <= args.fwhm_cv_max) and (asym_std <= args.asym_std_max)
        if n >= 2:
            print("    reproducibility: FWHM CV=%.2f%%  asym std=%.4f  peak std=%.4f chip  (n=%d)"
                  % (100 * cv, asym_std, float(np.nanstd(peak)), n))
        else:
            print("    reproducibility: n=1 (need repeats to assess)")

        # verdict
        if not measurable:
            verdict = "INSUFFICIENT (min N_kept %d < %d -> R(tau) not well-determined)" % (min_nk, args.min_epochs)
        elif n < 2:
            verdict = "SINGLE-RUN (precision %s; repeat >=3x for a trusted baseline)" % ("OK" if precise else "weak")
        elif precise and reproducible:
            verdict = "TRUSTWORTHY (precise + reproducible)"
        else:
            reasons = []
            if not precise:
                reasons.append("SEM %.5f > target %.4f" % (worst_sem, args.sem_target))
            if not reproducible:
                reasons.append("not reproducible (FWHM CV %.2f%% / asym std %.4f)" % (100 * cv, asym_std))
            verdict = "MARGINAL (" + "; ".join(reasons) + ")"
        print("    VERDICT: %s" % verdict)

        # kept fraction kept only as a tracking-health diagnostic
        valid_kf = [r[5] for r in items if np.isfinite(r[5])]
        if valid_kf:
            print("    diag: kept_fraction mean %.0f%% min %.0f%% (tracking-churn indicator, not a quality gate)"
                  % (100 * np.mean(valid_kf), 100 * min(valid_kf)))

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        color_of, seen = {}, set()
        fig, ax = plt.subplots(figsize=(10, 6))
        for r in runs:
            label, taps, mag = r[0], r[2], r[3]
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

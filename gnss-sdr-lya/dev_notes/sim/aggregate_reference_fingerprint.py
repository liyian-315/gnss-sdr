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
    ap.add_argument("--min-blocks", type=int, default=20,
                    help="measurability floor on EFFECTIVE independent samples (batch-means blocks, "
                         "n_blocks=N/tau from the CSV). Epochs are correlated, so this gates on n_blocks, "
                         "not raw epochs; ~20 blocks is the floor for a stable SEM estimate.")
    ap.add_argument("--sem-target", type=float, default=0.002,
                    help="INTERIM engineering threshold on the blocking (correlation-corrected) worst-tap "
                         "SEM. NOT yet physically calibrated: the trusted uncertainty is the cross-run "
                         "empirical std; sigma(asym)~sqrt(2)*SEM is printed for calibration against it.")
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
        n_kept = int(meta["kept_records"]) if "kept_records" in meta else -1
        n_eff = float(meta["n_eff"]) if "n_eff" in meta else float("nan")
        n_blocks = int(meta["n_blocks"]) if "n_blocks" in meta else -1
        # prefer the correlation-corrected (blocking) SEM from the CSV; fall back to naive
        sem = float(meta["sem_block_worst"]) if "sem_block_worst" in meta else max_tap_sem(tap_std, n_kept)
        runs.append(dict(label=label, path=path, taps=taps, mag=mag, feat=feat,
                         kept_frac=kept_frac, n_kept=n_kept, n_eff=n_eff, n_blocks=n_blocks, sem=sem))

    # ---- per-run table (precision = correlation-corrected SEM; kept% is diagnostic) ----
    print("=== per-run fingerprint features ===")
    hdr = "label            peak_chip  fwhm_chips  asym_max   N_kept   N_eff  blk  SEM_blk   kept%  file"
    print(hdr); print("-" * len(hdr))
    for r in runs:
        f = r["feat"]
        nks = ("%7d" % r["n_kept"]) if r["n_kept"] >= 0 else "     NA"
        nes = ("%6.0f" % r["n_eff"]) if np.isfinite(r["n_eff"]) else "    NA"
        blk = ("%3d" % r["n_blocks"]) if r["n_blocks"] >= 0 else " NA"
        sems = ("%.5f" % r["sem"]) if np.isfinite(r["sem"]) else "   NA"
        kfs = ("%4.0f" % (100 * r["kept_frac"])) if np.isfinite(r["kept_frac"]) else "  NA"
        under = "  <under-sampled>" if (r["n_blocks"] >= 0 and r["n_blocks"] < args.min_blocks) else ""
        print("%-15s  %+8.4f  %10.4f  %8.4f  %s  %s  %s  %s   %s%%  %s%s"
              % (r["label"], f["peak_chip"], f["fwhm_chips"], f["asym_max"], nks, nes, blk, sems, kfs,
                 os.path.basename(r["path"]), under))

    # ---- per-group: means, precision, reproducibility (PRIMARY), calibration, verdict ----
    print("\n=== per-group baseline (mean +/- std over repeats) ===")
    groups = {}
    for r in runs:
        groups.setdefault(r["label"], []).append(r)
    for label, items in groups.items():
        flist = [r["feat"] for r in items]
        n = len(flist)
        print("[%s] n=%d" % (label, n))
        for key in FEATURE_KEYS:
            vals = np.array([fl[key] for fl in flist], dtype=float)
            mean, std = np.nanmean(vals), (np.nanstd(vals) if n > 1 else 0.0)
            line = "    %-13s %+10.4f  +/- %8.4f" % (key, mean, std)
            if args.chip_m and key in ("peak_chip", "fwhm_chips", "skew_chips"):
                line += "   (%.2f +/- %.2f m)" % (mean * args.chip_m, std * args.chip_m)
            print(line)

        # precision (correlation-corrected) + measurability on effective blocks
        blks = [r["n_blocks"] for r in items if r["n_blocks"] >= 0]
        min_blk = min(blks) if blks else -1
        sems = [r["sem"] for r in items if np.isfinite(r["sem"])]
        worst_sem = max(sems) if sems else float("nan")
        measurable = (min_blk < 0) or (min_blk >= args.min_blocks)
        precise = np.isfinite(worst_sem) and worst_sem <= args.sem_target
        print("    precision:     min n_blocks=%s   worst SEM_block=%s (interim target %.4f)"
              % (("unknown" if min_blk < 0 else str(min_blk)),
                 ("%.5f" % worst_sem if np.isfinite(worst_sem) else "NA"), args.sem_target))

        # reproducibility across repeats -- the assumption-free, PRIMARY uncertainty
        fwhm = np.array([fl["fwhm_chips"] for fl in flist], dtype=float)
        asym = np.array([fl["asym_max"] for fl in flist], dtype=float)
        peak = np.array([fl["peak_chip"] for fl in flist], dtype=float)
        cv = float(np.nanstd(fwhm) / np.nanmean(fwhm)) if np.nanmean(fwhm) else float("nan")
        asym_std = float(np.nanstd(asym))
        reproducible = (n >= 2) and np.isfinite(cv) and (cv <= args.fwhm_cv_max) and (asym_std <= args.asym_std_max)
        if n >= 2:
            print("    reproducibility: FWHM CV=%.2f%%  asym std=%.5f  peak std=%.5f chip  (n=%d)"
                  % (100 * cv, asym_std, float(np.nanstd(peak)), n))
            # calibration: cross-run empirical sigma(asym) vs error-propagated within-run prediction
            pred = float(np.sqrt(2.0) * worst_sem) if np.isfinite(worst_sem) else float("nan")
            if np.isfinite(pred) and pred > 0:
                ratio = asym_std / pred
                tag = ("consistent" if 0.33 <= ratio <= 3.0 else
                       ("cross-run >> within-run SEM: between-run systematics dominate -> trust empirical"
                        if ratio > 3.0 else "cross-run << SEM (very few runs / underestimate)"))
                print("    calibration:   sigma(asym) empirical=%.5f  vs  sqrt(2)*SEM=%.5f  ratio=%.1f -> %s"
                      % (asym_std, pred, ratio, tag))
        else:
            print("    reproducibility: n=1 (need repeats; cross-run std is the trusted uncertainty)")

        if not measurable:
            verdict = "INSUFFICIENT (min n_blocks %d < %d; SEM/uncertainty unreliable)" % (min_blk, args.min_blocks)
        elif n < 2:
            verdict = "SINGLE-RUN (repeat >=3x; trust is cross-run reproducibility, not one SEM)"
        elif reproducible:
            verdict = "TRUSTWORTHY (reproducible across runs)"
        else:
            verdict = "MARGINAL (not reproducible: FWHM CV %.2f%% / asym std %.5f)" % (100 * cv, asym_std)
        print("    VERDICT: %s  [precision: %s]" % (verdict, "OK" if precise else "SEM above interim target"))

        valid_kf = [r["kept_frac"] for r in items if np.isfinite(r["kept_frac"])]
        if valid_kf:
            print("    diag: kept_fraction mean %.0f%% min %.0f%% (tracking-churn indicator, not a gate)"
                  % (100 * np.mean(valid_kf), 100 * min(valid_kf)))

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        color_of, seen = {}, set()
        fig, ax = plt.subplots(figsize=(10, 6))
        for r in runs:
            label, taps, mag = r["label"], r["taps"], r["mag"]
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

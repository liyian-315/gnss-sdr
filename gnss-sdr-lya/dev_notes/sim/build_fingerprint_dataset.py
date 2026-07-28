#!/usr/bin/env python3
"""Build one indexed dataset from a tree of Phase A/B fingerprint captures.

Turns a pile of `*_reference_Rtau*.png.csv` files (each written by
check_dense_vs_prompt.py with a '#' metadata line) into a single
`dataset_index.csv` -- one row per capture -- so the CN0-grid / delay-grid
collection is a queryable dataset, not loose files. This is the schema to fix
BEFORE the big collection so Phase A (single-source) and Phase B (two-source)
share one structure.

Per-capture experiment labels come from an optional `condition.json` sidecar in
the SAME directory as the CSV (falls back to blanks if absent):

    {
      "phase": "A",            // "A" single-source | "B" two-source
      "band": "L5",            // L1 | L5 | B1I
      "prn": 28,
      "cn0_target": 50,        // dB-Hz target the sim power was set for
      "sim_power_dbm": -50,
      "delay_m": 0,            // phase B: injected path1 delay; phase A: 0
      "power_ratio_db": null,  // phase B: path1/path0 dB; phase A: null
      "run": 1,                // repeat index for this condition
      "config": "l5 pilot robust",
      "note": ""
    }

Measured fields (cn0_median, n_blocks, sem_block_worst, asym, fwhm, ...) come from
the CSV so the index has both the intended condition and what was actually got.

Usage:
  python3 dev_notes/sim/build_fingerprint_dataset.py <root_dir> [--out dataset_index.csv]
"""

import argparse
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aggregate_reference_fingerprint as agg  # noqa: E402

COND_KEYS = ["phase", "band", "prn", "cn0_target", "sim_power_dbm", "delay_m",
             "power_ratio_db", "run", "config", "note"]
META_KEYS = ["signal", "fs_hz", "cn0_median", "lock_median", "kept_records",
             "kept_fraction", "n_segments_kept", "tau_int", "n_eff", "n_blocks",
             "sem_block_worst", "asym"]
FEAT_KEYS = ["peak_chip", "fwhm_chips", "skew_chips", "noise_floor"]


def load_condition(csv_path):
    cond = {k: "" for k in COND_KEYS}
    j = os.path.join(os.path.dirname(csv_path), "condition.json")
    if os.path.exists(j):
        try:
            with open(j, encoding="utf-8") as fh:
                data = json.load(fh)
            for k in COND_KEYS:
                if k in data and data[k] is not None:
                    cond[k] = data[k]
        except Exception as e:
            print("warn: bad condition.json at %s: %s" % (j, e))
    return cond


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="directory to scan recursively for *reference_Rtau*.png.csv")
    ap.add_argument("--glob", default="**/*reference_Rtau*.png.csv", help="glob under root")
    ap.add_argument("--out", default="dataset_index.csv", help="output index CSV")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.root, args.glob), recursive=True))
    if not paths:
        raise SystemExit("no reference CSVs matched %s under %s" % (args.glob, args.root))

    cols = ["path"] + COND_KEYS + META_KEYS + FEAT_KEYS
    rows = []
    for p in paths:
        meta = agg.load_meta(p)
        cond = load_condition(p)
        try:
            taps, mag, tap_std, _ = agg.load_csv(p)
            feat = agg.features(taps, mag, tap_std)
        except Exception as e:
            print("warn: cannot parse %s: %s" % (p, e))
            feat = {k: "" for k in FEAT_KEYS}
        row = {"path": os.path.relpath(p, args.root)}
        row.update({k: cond.get(k, "") for k in COND_KEYS})
        row.update({k: meta.get(k, "") for k in META_KEYS})
        row.update({k: (feat.get(k, "") if not isinstance(feat.get(k), float) or np.isfinite(feat.get(k)) else "")
                    for k in FEAT_KEYS})
        rows.append(row)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(",".join(cols) + "\n")
        for r in rows:
            fh.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
    print("wrote %s  (%d captures)" % (args.out, len(rows)))

    # coverage summary: unique conditions x repeats
    print("\n=== coverage (phase / band / signal / cn0_target / delay_m / power_ratio_db) ===")
    grid = {}
    for r in rows:
        key = (r["phase"], r["band"], r["signal"], str(r["cn0_target"]), str(r["delay_m"]), str(r["power_ratio_db"]))
        grid.setdefault(key, []).append(r)
    print("  phase band signal cn0T   delay  ratio  runs  cn0_med  min_nblk  mean_asym")
    print("  " + "-" * 82)
    for key in sorted(grid):
        rs = grid[key]
        def fnums(k):
            return [float(x[k]) for x in rs if str(x[k]) not in ("", "nan")]
        cn0 = fnums("cn0_median"); nblk = fnums("n_blocks"); asy = fnums("asym")
        print("  %-5s %-4s %-6s %-5s  %-5s  %-5s  %4d  %7s  %8s  %9s"
              % (key[0] or "-", key[1] or "-", key[2] or "-", key[3] or "-", key[4] or "-", key[5] or "-",
                 len(rs),
                 ("%.1f" % np.mean(cn0)) if cn0 else "-",
                 ("%d" % int(min(nblk))) if nblk else "-",
                 ("%.4f" % np.mean(asy)) if asy else "-"))
    print("\nNext: feed same-condition CSVs to aggregate_reference_fingerprint.py for the TRUSTWORTHY verdict.")


if __name__ == "__main__":
    main()

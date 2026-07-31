#!/usr/bin/env python3
"""Build leave-one-run-out path0 texture models and a benchmark manifest."""

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import defaultdict


def unique_references(summary_path):
    with open(summary_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    references = {}
    for row in rows:
        references.setdefault(row["label"], row)
    return list(references.values())


def tap_grid_key(reference):
    with open(reference["dense"], encoding="utf-8") as fh:
        meta = json.load(fh)
    taps = [float(value) for value in meta["taps_chips"]]
    step = taps[1] - taps[0] if len(taps) > 1 else 0.0
    return (
        reference.get("prn", ""),
        len(taps),
        round(taps[0], 6),
        round(taps[-1], 6),
        round(step, 6),
    )


def is_training_quality(reference):
    return (
        reference.get("reference_quality", "normal") == "normal"
        and float(reference.get("kept_fraction") or 1.0) >= 0.20
        and int(float(reference.get("n_blocks") or 20)) >= 20
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", required=True, help="prior cross-reference summary.csv")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--manifest", help="default: OUTPUT_DIR/manifest.csv")
    ap.add_argument("--cn0-min", type=float, default=35.0)
    ap.add_argument("--max-records-per-dense", type=int, default=20000)
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    builder = os.path.join(script_dir, "build_path0_texture_model.py")
    os.makedirs(args.output_dir, exist_ok=True)
    model_dir = os.path.join(args.output_dir, "models")
    os.makedirs(model_dir, exist_ok=True)

    references = unique_references(args.summary)
    groups = defaultdict(list)
    for reference in references:
        groups[tap_grid_key(reference)].append(reference)

    manifest_rows = []
    for reference in references:
        peers = [
            candidate
            for candidate in groups[tap_grid_key(reference)]
            if candidate["label"] != reference["label"] and is_training_quality(candidate)
        ]
        if not peers:
            print("SKIP %s: no independent training run" % reference["label"])
            continue
        model = os.path.join(model_dir, reference["label"] + ".npz")
        command = [
            sys.executable,
            builder,
            "--kernel",
            reference["kernel"],
            "--output",
            model,
            "--cn0-min",
            str(args.cn0_min),
            "--max-records-per-dense",
            str(args.max_records_per_dense),
        ]
        for peer in peers:
            command.extend(["--dense", peer["dense"]])
        proc = subprocess.run(command, text=True)
        if proc.returncode:
            raise SystemExit("texture model failed for %s" % reference["label"])
        manifest_rows.append(
            {
                "label": reference["label"],
                "prn": reference.get("prn", ""),
                "dense": reference["dense"],
                "kernel": reference["kernel"],
                "cn0_min": args.cn0_min,
                "texture_model": model,
            }
        )
        print(
            "%s: test=1 train=%d group=%s"
            % (reference["label"], len(peers), tap_grid_key(reference))
        )

    if not manifest_rows:
        raise SystemExit("no leave-one-run-out models were built")
    manifest = args.manifest or os.path.join(args.output_dir, "manifest.csv")
    with open(manifest, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=manifest_rows[0].keys())
        writer.writeheader()
        writer.writerows(manifest_rows)
    print("manifest -> %s (%d references)" % (manifest, len(manifest_rows)))


if __name__ == "__main__":
    main()

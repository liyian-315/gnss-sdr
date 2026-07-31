#!/usr/bin/env python3
"""Run the Track B DP and EKF baselines across real A-only textures.

The manifest is a CSV with these required columns:

    label,dense,kernel,cn0_min

Each real A-only texture is reused as path0 in four controlled synthetic cases.
The generated NPZ files are small and remain under the requested output
directory; original captures are never modified.
"""

import argparse
import csv
import os
import re
import subprocess
import sys


SCENARIOS = (
    ("moving_m6", ["--ratio-db", "-6"]),
    ("moving_equal_destructive", ["--ratio-db", "0", "--phase-deg", "180"]),
    ("static_m6", ["--ratio-db", "-6", "--static"]),
    ("moving_absent", ["--ratio-db", "-120"]),
)

DP_METRIC_RE = re.compile(
    r"trajectory\s+: median abs error ([0-9.]+) m, p90 ([0-9.]+) m, within ([0-9.]+)%"
)
EKF_METRIC_RE = re.compile(
    r"delay error: median ([0-9.]+) m, p90 ([0-9.]+) m, within ([0-9.]+)%, "
    r"2-sigma coverage ([0-9.]+)%"
)
EKF_SUPPORT_RE = re.compile(
    r"updates accepted: ([0-9.]+)%; 2-path support: ([0-9.]+)%; "
    r"median posterior std ([0-9.]+) m"
)
VERDICT_RE = re.compile(r"VERDICT: (RELIABLE|UNRELIABLE)")
CONFIDENCE_RE = re.compile(r"CONFIDENCE: (CONFIDENT|LOW-CONFIDENCE)")
DP_CONF_MOTION_RE = re.compile(
    r"motion diversity\s+: delay span ([0-9.]+) m, Doppler span ([0-9.]+) Hz"
)
DP_CONF_PHYSICS_RE = re.compile(r"physics link\s+: resid ([+\-]?(?:inf|nan|[0-9.]+)) m")
DP_CONF_MARGIN_RE = re.compile(
    r"best-vs-2nd path\s+: margin ([+\-]?(?:inf|nan|[0-9.]+))\s+"
    r"\(best cost ([+\-]?(?:inf|nan|[0-9.]+)), 2nd-best ([+\-]?(?:inf|nan|[0-9.]+))"
)


def run(cmd, log_path):
    proc = subprocess.run(
        cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(proc.stdout)
    return proc


def parse_kernel_metadata(path):
    metadata = {}
    with open(path, encoding="utf-8") as fh:
        first = fh.readline().strip()
    if not first.startswith("#"):
        return metadata
    for token in first[1:].split():
        if "=" in token:
            key, value = token.split("=", 1)
            metadata[key] = value
    return metadata


def metric_row(base, method, proc):
    row = dict(base)
    row.update(
        {
            "method": method,
            "returncode": proc.returncode,
            "verdict": "",
            "median_error_m": "",
            "p90_error_m": "",
            "within_pct": "",
            "accepted_pct": "",
            "support_pct": "",
            "median_posterior_std_m": "",
            "coverage_2sigma_pct": "",
            "confidence": "",
            "confidence_delay_span_m": "",
            "confidence_doppler_span_hz": "",
            "confidence_physics_resid_m": "",
            "confidence_margin": "",
            "confidence_best_cost": "",
            "confidence_alt_cost": "",
        }
    )
    verdict = VERDICT_RE.search(proc.stdout)
    if verdict:
        row["verdict"] = verdict.group(1)
    metric = (DP_METRIC_RE if method == "dp" else EKF_METRIC_RE).search(proc.stdout)
    if metric:
        row["median_error_m"], row["p90_error_m"], row["within_pct"] = metric.groups()[:3]
        if method == "ekf":
            row["coverage_2sigma_pct"] = metric.group(4)
    if method == "ekf":
        support = EKF_SUPPORT_RE.search(proc.stdout)
        if support:
            (
                row["accepted_pct"],
                row["support_pct"],
                row["median_posterior_std_m"],
            ) = support.groups()
    else:
        confidence = CONFIDENCE_RE.search(proc.stdout)
        motion = DP_CONF_MOTION_RE.search(proc.stdout)
        physics = DP_CONF_PHYSICS_RE.search(proc.stdout)
        margin = DP_CONF_MARGIN_RE.search(proc.stdout)
        if confidence:
            row["confidence"] = confidence.group(1)
        if motion:
            row["confidence_delay_span_m"], row["confidence_doppler_span_hz"] = motion.groups()
        if physics:
            row["confidence_physics_resid_m"] = physics.group(1)
        if margin:
            (
                row["confidence_margin"],
                row["confidence_best_cost"],
                row["confidence_alt_cost"],
            ) = margin.groups()
    if proc.returncode != 0 and not row["verdict"]:
        row["verdict"] = "ERROR"
    return row


def load_manifest(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    required = {"label", "dense", "kernel", "cn0_min"}
    if not rows or not required.issubset(rows[0]):
        raise SystemExit("manifest requires columns: %s" % ",".join(sorted(required)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--summary", help="default: OUTPUT_DIR/summary.csv")
    ap.add_argument("--duration-s", type=float, default=20.0)
    ap.add_argument("--min-lock-run", type=int, default=1000)
    ap.add_argument("--settle-epochs", type=int, default=200)
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    generator = os.path.join(script_dir, "generate_moving_twosource.py")
    dp = os.path.join(script_dir, "track_moving_twosource.py")
    ekf = os.path.join(script_dir, "track_moving_twosource_ekf.py")
    os.makedirs(args.output_dir, exist_ok=True)

    results = []
    for reference in load_manifest(args.manifest):
        dense = os.path.abspath(os.path.expanduser(reference["dense"]))
        kernel = os.path.abspath(os.path.expanduser(reference["kernel"]))
        if not os.path.exists(dense) or not os.path.exists(kernel):
            print("SKIP %s: missing dense or kernel" % reference["label"])
            continue
        meta = parse_kernel_metadata(kernel)
        quality = "normal"
        if float(meta.get("kept_fraction", "1")) < 0.20 or int(meta.get("n_blocks", "20")) < 20:
            quality = "low_quality_control"

        for scenario, scenario_args in SCENARIOS:
            stem = "%s__%s" % (reference["label"], scenario)
            npz = os.path.join(args.output_dir, stem + ".npz")
            gen_log = os.path.join(args.output_dir, stem + "__generate.log")
            cmd = [
                sys.executable,
                generator,
                "--output",
                npz,
                "--kernel",
                kernel,
                "--faithful-path0-dense",
                dense,
                "--duration-s",
                str(args.duration_s),
                "--cn0-min",
                reference["cn0_min"],
                "--lock-min",
                "0.6",
                "--min-lock-run",
                str(args.min_lock_run),
                "--settle-epochs",
                str(args.settle_epochs),
            ] + scenario_args
            generated = run(cmd, gen_log)
            base = {
                "label": reference["label"],
                "scenario": scenario,
                "reference_quality": quality,
                "prn": reference.get("prn", ""),
                "cn0_median": meta.get("cn0_median", ""),
                "lock_median": meta.get("lock_median", ""),
                "kept_fraction": meta.get("kept_fraction", ""),
                "n_blocks": meta.get("n_blocks", ""),
                "tau_int": meta.get("tau_int", ""),
                "sem_block_worst": meta.get("sem_block_worst", ""),
                "asym": meta.get("asym", ""),
                "dense": dense,
                "kernel": kernel,
            }
            if generated.returncode != 0:
                for method in ("dp", "ekf"):
                    row = dict(base)
                    row.update(
                        {
                            "method": method,
                            "returncode": generated.returncode,
                            "verdict": "GENERATOR_ERROR",
                        }
                    )
                    results.append(row)
                print("%s -> GENERATOR_ERROR" % stem)
                continue

            dp_proc = run(
                [sys.executable, dp, "--input", npz, "--kernel", kernel],
                os.path.join(args.output_dir, stem + "__dp.log"),
            )
            ekf_proc = run(
                [sys.executable, ekf, "--input", npz, "--kernel", kernel],
                os.path.join(args.output_dir, stem + "__ekf.log"),
            )
            dp_row = metric_row(base, "dp", dp_proc)
            ekf_row = metric_row(base, "ekf", ekf_proc)
            results.extend((dp_row, ekf_row))
            print(
                "%-42s DP=%-10s conf=%-14s p90=%-6s EKF=%-10s p90=%-6s"
                % (
                    stem,
                    dp_row["verdict"],
                    dp_row["confidence"],
                    dp_row["p90_error_m"],
                    ekf_row["verdict"],
                    ekf_row["p90_error_m"],
                )
            )

    if not results:
        raise SystemExit("no benchmark results")
    summary = args.summary or os.path.join(args.output_dir, "summary.csv")
    fields = []
    for row in results:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(summary, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    print("summary -> %s" % summary)


if __name__ == "__main__":
    main()

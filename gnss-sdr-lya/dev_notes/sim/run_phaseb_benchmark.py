#!/usr/bin/env python3
"""Run the fixed Phase B benchmark over existing dense dumps.

The benchmark is intentionally data-root based.  It does not collect RF data; it
only reprocesses already captured Phase B directories and writes one CSV row per
run.  This is the guardrail before changing the two-source fitter: PRN23/PRN28
30/60/90 m runs become repeatable regression cases.
"""

import argparse
import csv
import glob
import os
import re
import subprocess
import sys


CASE_RE = re.compile(
    r"prn(?P<prn>\d+)_delay(?P<delay>\d+)m_ratio_m(?P<ratio>\d+)db_run(?P<run>\d+)_30s_0728$"
)


def find_kernel(root, prn):
    pattern = os.path.join(root, "phaseB_l5_baseline", "aonly_prn%d_*_30s_0728",
                           "aonly_reference_Rtau.png.csv") % prn
    hits = sorted(glob.glob(pattern))
    if not hits:
        raise FileNotFoundError("no A-only kernel for PRN%d under %s" % (prn, root))
    return hits[-1]


def parse_target_rank(stdout):
    m = re.search(r"target\s+([0-9.]+)\s+m .* nearest\s+([0-9.]+)\s+m rank=(\d+) evidence=([0-9.eE+-]+) step=([0-9.eE+-]+)", stdout)
    if not m:
        return "", "", "", "", ""
    return m.group(2), m.group(3), m.group(4), m.group(5), "1"


def parse_top(stdout):
    for ln in stdout.splitlines():
        m = re.match(r"\s*1\s+([0-9.+-]+)\s+([0-9.+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)", ln)
        if m:
            return {
                "top_delta_chip": m.group(1),
                "top_delta_m": m.group(2),
                "top_evidence": m.group(3),
                "top_dyn_med": m.group(4),
                "top_amp_med": m.group(5),
                "top_step_score": m.group(6),
            }
    return {
        "top_delta_chip": "",
        "top_delta_m": "",
        "top_evidence": "",
        "top_dyn_med": "",
        "top_amp_med": "",
        "top_step_score": "",
    }


def parse_residual_fit(stdout):
    row = {
        "fit_verdict": "",
        "fit_delta_m": "",
        "fit_ratio_db": "",
        "fit_delay_error_m": "",
        "fit_ratio_error_db": "",
    }
    m = re.search(r"VERDICT:\s+([^\n]+)", stdout)
    if m:
        row["fit_verdict"] = m.group(1).strip()
    m = re.search(r"delta=([0-9.+-]+)\s+chip\s+=\s+([0-9.+-]+)\s+m", stdout)
    if m:
        row["fit_delta_m"] = m.group(2)
    m = re.search(r"amp ratio A1/A0=([0-9.+-]+)\s+dB", stdout)
    if m:
        row["fit_ratio_db"] = m.group(1)
    m = re.search(r"delay:\s+injected\s+[0-9.+-]+\s+m\s+recovered\s+[0-9.+-]+\s+m\s+error\s+([0-9.+-]+)\s+m", stdout)
    if m:
        row["fit_delay_error_m"] = m.group(1)
    m = re.search(r"ratio:\s+injected\s+[0-9.+-]+\s+dB\s+recovered\s+[0-9.+-]+\s+dB\s+error\s+([0-9.+-]+)\s+dB", stdout)
    if m:
        row["fit_ratio_error_db"] = m.group(1)
    return row


def verdict(delay_m, target_nearest_m, target_rank, rank_pass):
    if target_rank == "":
        return "NO_SCORE"
    err = abs(float(target_nearest_m) - float(delay_m))
    rank = int(target_rank)
    if rank <= rank_pass and err <= max(3.0, 0.15 * float(delay_m)):
        return "EVIDENCE_PASS"
    return "EVIDENCE_FAIL"


def run_score(script_dir, dense, kernel, delay_m, chip_m, out_csv, rank_pass):
    score_script = os.path.join(script_dir, "score_delay_candidates.py")
    cmd = [
        sys.executable, score_script,
        "--dense", dense,
        "--kernel", kernel,
        "--chip-m", str(chip_m),
        "--delay-m", str(delay_m),
        "--min-delay-chips", "0.3",
        "--max-delay-chips", "4.0",
        "--step-chip", "0.05",
        "--csv-out", out_csv,
    ]
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    nearest, rank, evidence, step, ok = parse_target_rank(p.stdout)
    row = parse_top(p.stdout)
    row.update({
        "score_rc": str(p.returncode),
        "target_nearest_m": nearest,
        "target_rank": rank,
        "target_evidence": evidence,
        "target_step_score": step,
        "target_line_seen": ok,
        "evidence_verdict": verdict(delay_m, nearest, rank, rank_pass),
    })
    return row, p.stdout


def run_residual_fit(script_dir, dense, kernel, delay_m, ratio_db, chip_m, log_path):
    fit_script = os.path.join(script_dir, "fit_drift_modulated_twosource.py")
    cmd = [
        sys.executable, fit_script,
        "--dense", dense,
        "--kernel", kernel,
        "--chip-m", str(chip_m),
        "--carrier-hz", "1176.45e6",
        "--delay-m", str(delay_m),
        "--ratio-db", str(ratio_db),
        "--cn0-min", "0",
        "--lock-min", "-1",
        "--min-lock-run", "1000",
        "--settle-epochs", "200",
        "--min-delay-chips", "0.3",
        "--max-delay-chips", "4.0",
        "--coarse-chip", "0.05",
        "--fine-chip", "0.01",
        "--phase-reference", "phase",
        "--modulation-source", "residual-band",
        "--iterations", "3",
        "--mod-score-min", "0.20",
    ]
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(p.stdout)
    row = parse_residual_fit(p.stdout)
    row["fit_rc"] = str(p.returncode)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="gnss_data root containing phaseB_l5_* directories")
    ap.add_argument("--out", required=True, help="benchmark summary CSV")
    ap.add_argument("--chip-m", type=float, default=29.3)
    ap.add_argument("--rank-pass", type=int, default=3)
    ap.add_argument("--prns", default="23,28")
    ap.add_argument("--delays", default="30,60,90")
    ap.add_argument("--run-residual-fit", action="store_true",
                    help="also run residual-band fitter for each case and parse its verdict")
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    prns = {int(x) for x in args.prns.split(",") if x}
    delays = {int(x) for x in args.delays.split(",") if x}
    dirs = sorted(glob.glob(os.path.join(args.root, "phaseB_l5_twosource",
                                         "prn*_delay*m_ratio_m*db_run*_30s_0728")))
    rows = []
    for d in dirs:
        m = CASE_RE.search(os.path.basename(d))
        if not m:
            continue
        prn = int(m.group("prn"))
        delay = int(m.group("delay"))
        if prn not in prns or delay not in delays:
            continue
        dense = os.path.join(d, "l5_phaseB_dense_ch_0.dat.json")
        if not os.path.exists(dense):
            continue
        kernel = find_kernel(args.root, prn)
        score_csv = os.path.join(d, "delay_candidate_scores.csv")
        score, stdout = run_score(script_dir, dense, kernel, delay, args.chip_m, score_csv, args.rank_pass)
        log_path = os.path.join(d, "delay_candidate_scores.log")
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write(stdout)
        row = {
            "prn": prn,
            "delay_m": delay,
            "ratio_db": -int(m.group("ratio")),
            "run": int(m.group("run")),
            "dir": d,
            "kernel": kernel,
        }
        row.update(score)
        if args.run_residual_fit:
            fit_log = os.path.join(d, "benchmark_residual_fit.log")
            row.update(run_residual_fit(script_dir, dense, kernel, delay, -int(m.group("ratio")),
                                        args.chip_m, fit_log))
        rows.append(row)
        fit_msg = ""
        if args.run_residual_fit:
            fit_msg = " fit=%s delta=%s" % (row.get("fit_verdict", ""), row.get("fit_delta_m", ""))
        print("PRN%d delay%dm run%s -> %s rank=%s nearest=%s m%s" %
              (prn, delay, m.group("run"), score["evidence_verdict"],
               score["target_rank"], score["target_nearest_m"], fit_msg))

    if not rows:
        raise SystemExit("no benchmark cases found")
    fields = list(rows[0].keys())
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields)
        wr.writeheader()
        wr.writerows(rows)
    print("summary -> %s" % args.out)


if __name__ == "__main__":
    main()

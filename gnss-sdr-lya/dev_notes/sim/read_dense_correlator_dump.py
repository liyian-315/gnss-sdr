#!/usr/bin/env python3
"""Read and plot dense tracking correlator dumps.

Input is the JSON sidecar produced by Tracking_XX.dense_correlator_dump, or the
matching .dat path. The binary record layout is described in the JSON file.

Examples:
  python3 dev_notes/sim/read_dense_correlator_dump.py ./dense_trk_channel_0.dat.json --max 5
  python3 dev_notes/sim/read_dense_correlator_dump.py ./dense_trk_channel_0.dat --epoch -1 --plot-out dense_epoch_last.png
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np


def metadata_path_from_arg(path_arg):
    path = Path(path_arg)
    if path.suffix == ".json":
        return path
    json_path = Path(str(path) + ".json")
    if json_path.exists():
        return json_path
    raise FileNotFoundError("metadata sidecar not found: %s" % json_path)


def load_metadata(path_arg):
    metadata_path = metadata_path_from_arg(path_arg)
    with metadata_path.open("r", encoding="utf-8") as fh:
        meta = json.load(fh)
    binary_path = Path(meta.get("binary_file", ""))
    if not binary_path.is_absolute():
        binary_path = metadata_path.parent / binary_path
    return metadata_path, binary_path, meta


def dense_dtype(tap_count):
    return np.dtype([
        ("sample_counter", "<u8"),
        ("epoch_counter", "<u8"),
        ("channel", "<u4"),
        ("prn", "<u4"),
        ("tow_ms", "<u8"),
        ("wn", "<i4"),
        ("rem_carr_phase_rad", "<f4"),
        ("acc_carrier_phase_rad", "<f4"),
        ("carrier_doppler_hz", "<f4"),
        ("carrier_phase_step_rad", "<f4"),
        ("carrier_phase_rate_step_rad", "<f4"),
        ("rem_code_phase_chips", "<f4"),
        ("code_phase_step_chips", "<f4"),
        ("code_phase_rate_step_chips", "<f4"),
        ("cn0_snv_db_hz", "<f4"),
        ("carrier_lock_test", "<f4"),
        ("tap_iq", "<c8", (tap_count,)),
    ])


def read_records(binary_path, meta):
    tap_count = int(meta["tap_count"])
    dtype = dense_dtype(tap_count)
    expected_size = int(meta["record_size_bytes"])
    if dtype.itemsize != expected_size:
        raise ValueError("dtype size %d != metadata record_size_bytes %d" % (dtype.itemsize, expected_size))
    size = os.path.getsize(binary_path)
    if size % dtype.itemsize != 0:
        raise ValueError("file size %d is not a multiple of record size %d" % (size, dtype.itemsize))
    return np.fromfile(binary_path, dtype=dtype)


def peak_info(row, taps_chips):
    iq = row["tap_iq"]
    mag = np.abs(iq)
    peak_idx = int(np.argmax(mag))
    median = float(np.median(mag))
    ratio_db = 10.0 * np.log10(float(mag[peak_idx]) / median) if median > 0.0 else float("nan")
    return peak_idx, float(taps_chips[peak_idx]), float(mag[peak_idx]), ratio_db


def print_summary(metadata_path, binary_path, meta, records, max_rows):
    taps = np.asarray(meta["taps_chips"], dtype=np.float64)
    print("metadata:", metadata_path)
    print("binary:", binary_path)
    print("records:", len(records), "record_size:", meta["record_size_bytes"], "tap_count:", len(taps))
    print("signal: system=%s signal=%s channel=%s decimation=%s fs=%.3f MHz" % (
        meta.get("system", ""),
        meta.get("signal", ""),
        meta.get("channel", ""),
        meta.get("decimation_epochs", ""),
        float(meta.get("sampling_frequency_hz", 0.0)) / 1e6,
    ))
    if len(taps):
        print("tap span: %.3f .. %.3f chips" % (float(taps[0]), float(taps[-1])))
    print()
    print("idx  epoch   sample_counter  ch  prn  cn0_dbhz  doppler_hz  peak_chip  peak_abs  peak_med_db")
    print("-" * 96)
    for idx, row in enumerate(records[:max_rows]):
        peak_idx, peak_chip, peak_abs, ratio_db = peak_info(row, taps)
        del peak_idx
        print("%3d  %6d  %14d  %2d  %3d  %8.2f  %10.1f  %+9.3f  %8.3g  %10.2f" % (
            idx,
            int(row["epoch_counter"]),
            int(row["sample_counter"]),
            int(row["channel"]),
            int(row["prn"]),
            float(row["cn0_snv_db_hz"]),
            float(row["carrier_doppler_hz"]),
            peak_chip,
            peak_abs,
            ratio_db,
        ))


def plot_epoch(records, meta, epoch_index, plot_out):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    taps = np.asarray(meta["taps_chips"], dtype=np.float64)
    row = records[epoch_index]
    iq = row["tap_iq"]
    mag = np.abs(iq)
    phase = np.angle(iq)
    peak_idx, peak_chip, peak_abs, ratio_db = peak_info(row, taps)

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    axes[0].plot(taps, mag, marker=".", linewidth=1.2)
    axes[0].axvline(peak_chip, color="r", linestyle="--", linewidth=1.0)
    axes[0].set_ylabel("|corr|")
    axes[0].grid(True, alpha=0.3)
    axes[0].set_title(
        "Dense correlator epoch=%d prn=%d peak=%.3f chip peak/median=%.2f dB"
        % (int(row["epoch_counter"]), int(row["prn"]), peak_chip, ratio_db)
    )

    axes[1].plot(taps, phase, marker=".", linewidth=1.2)
    axes[1].set_xlabel("tap offset [chips]")
    axes[1].set_ylabel("phase [rad]")
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(plot_out, dpi=150)
    print("plot:", plot_out)
    print("selected epoch index:", epoch_index)
    print("peak tap index:", peak_idx, "peak chip:", peak_chip, "peak abs:", peak_abs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump_or_json", help="Dense .dat path or .dat.json sidecar")
    ap.add_argument("--max", type=int, default=10, help="Rows to print")
    ap.add_argument("--epoch", type=int, default=0, help="Epoch index to plot/detail; negative indexes are allowed")
    ap.add_argument("--plot-out", help="Write a PNG profile for --epoch")
    args = ap.parse_args()

    metadata_path, binary_path, meta = load_metadata(args.dump_or_json)
    records = read_records(binary_path, meta)
    print_summary(metadata_path, binary_path, meta, records, args.max)

    if args.plot_out:
        if len(records) == 0:
            raise SystemExit("no records to plot")
        epoch_index = args.epoch
        if epoch_index < 0:
            epoch_index += len(records)
        if epoch_index < 0 or epoch_index >= len(records):
            raise SystemExit("epoch index out of range: %s" % args.epoch)
        plot_epoch(records, meta, epoch_index, args.plot_out)


if __name__ == "__main__":
    main()

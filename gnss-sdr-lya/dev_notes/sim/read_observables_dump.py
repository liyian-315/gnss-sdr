#!/usr/bin/env python3
"""Print pseudoranges from GNSS-SDR Hybrid_Observables binary dump.

The legacy Hybrid_Observables dump writes 7 doubles per channel per epoch:
  RX_time, TOW_s, Doppler_Hz, Carrier_phase_cycles, Pseudorange_m, PRN, valid
With Observables.dump_extended=true it writes 9 doubles by appending:
  Signal_Path, CN0_dB_hz

Example:
  python3 dev_notes/sim/read_observables_dump.py gps_l5_dualpath_observables.dat --channels 2 --tail 10
"""
import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np


LEGACY_FIELDS = ("rx_time_s", "tow_s", "doppler_hz", "carrier_cycles", "pseudorange_m", "prn", "valid")
EXTENDED_FIELDS = LEGACY_FIELDS + ("signal_path", "cn0_db_hz")


def choose_fields(raw, channels, requested):
    if requested == "legacy":
        return LEGACY_FIELDS
    if requested == "extended":
        return EXTENDED_FIELDS
    raw_size = raw.size
    extended_epoch = channels * len(EXTENDED_FIELDS)
    legacy_epoch = channels * len(LEGACY_FIELDS)
    if raw_size >= extended_epoch and raw_size % extended_epoch == 0:
        probe = raw.reshape((-1, channels, len(EXTENDED_FIELDS)))[:20, :, :]
        signal_path = probe[:, :, 7].reshape(-1)
        path_is_valid = np.isclose(signal_path, 0.0, atol=0.01) | np.isclose(signal_path, 1.0, atol=0.01)
        if bool(np.all(path_is_valid)):
            return EXTENDED_FIELDS
    if raw_size >= legacy_epoch and raw_size % legacy_epoch == 0:
        return LEGACY_FIELDS
    return EXTENDED_FIELDS if raw_size // extended_epoch else LEGACY_FIELDS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump", nargs="?", default="bds_b1i_observables.dat", help="Hybrid_Observables dump file")
    ap.add_argument("--channels", type=int, default=4, help="Channels_B1.count used when running gnss-sdr")
    ap.add_argument("--tail", type=int, default=10, help="Number of last epochs to print")
    ap.add_argument("--format", choices=("auto", "legacy", "extended"), default="auto",
                    help="Dump row format. auto prefers extended when the file length fits it")
    ap.add_argument("--all", action="store_true", help="Print invalid rows too")
    ap.add_argument("--pairs", action="store_true", help="Print per-epoch primary/secondary pseudorange deltas")
    args = ap.parse_args()

    path = Path(args.dump)
    if not path.exists():
        raise SystemExit("dump not found: %s" % path)
    if args.channels <= 0:
        raise SystemExit("--channels must be positive")

    raw = np.fromfile(path, dtype=np.float64)
    fields = choose_fields(raw, args.channels, args.format)
    row_len = len(fields)
    epoch_len = args.channels * row_len
    if raw.size < epoch_len:
        raise SystemExit("dump too small: %d doubles, need at least %d" % (raw.size, epoch_len))

    usable = (raw.size // epoch_len) * epoch_len
    if usable != raw.size:
        print("warn: ignoring %d trailing doubles (partial epoch)" % (raw.size - usable))
    data = raw[:usable].reshape((-1, args.channels, row_len))

    start = max(0, data.shape[0] - args.tail)
    extended = fields == EXTENDED_FIELDS
    print("file=%s epochs=%d channels=%d format=%s showing=%d..%d" %
          (path, data.shape[0], args.channels, "extended" if extended else "legacy", start, data.shape[0] - 1))
    print("%6s %3s %4s %9s %10s %10s %14s %10s %8s" %
          ("epoch", "ch", "prn", "path", "rx_time", "tow", "pseudorange_m", "doppler", "cn0"))
    print("-" * 88)

    shown = 0
    for e in range(start, data.shape[0]):
        for ch in range(args.channels):
            rx_time, tow, doppler, _carrier, prange, prn, valid = data[e, ch, :len(LEGACY_FIELDS)]
            if not args.all and valid < 0.5:
                continue
            signal_path = int(round(data[e, ch, 7])) if extended else ch % 2
            cn0 = data[e, ch, 8] if extended else float("nan")
            role = "primary" if signal_path == 0 else "second"
            print("%6d %3d %4d %9s %10.3f %10.3f %14.3f %10.1f %8.2f" %
                  (e, ch, int(round(prn)), role, rx_time, tow, prange, doppler, cn0))
            shown += 1
    if shown == 0:
        print("no valid pseudorange rows in selected tail; try --tail 200 or check lock/overflow")
    if args.pairs:
        print("\n%6s %4s %14s %14s %12s" % ("epoch", "prn", "primary_m", "second_m", "delta_m"))
        print("-" * 60)
        paired = 0
        for e in range(start, data.shape[0]):
            by_prn = defaultdict(dict)
            for ch in range(args.channels):
                rx_time, tow, doppler, _carrier, prange, prn, valid = data[e, ch, :len(LEGACY_FIELDS)]
                if valid < 0.5:
                    continue
                signal_path = int(round(data[e, ch, 7])) if extended else ch % 2
                by_prn[int(round(prn))][signal_path] = prange
            for prn, paths in sorted(by_prn.items()):
                if 0 in paths and 1 in paths:
                    print("%6d %4d %14.3f %14.3f %12.3f" %
                          (e, prn, paths[0], paths[1], paths[1] - paths[0]))
                    paired += 1
        if paired == 0:
            print("no primary/second valid pairs in selected tail")


if __name__ == "__main__":
    main()

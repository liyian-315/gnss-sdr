#!/usr/bin/env python3
"""Print pseudoranges from GNSS-SDR Hybrid_Observables binary dump.

The current Hybrid_Observables dump writes 7 doubles per channel per epoch:
  RX_time, TOW_s, Doppler_Hz, Carrier_phase_cycles, Pseudorange_m, PRN, valid

Example:
  python3 dev_notes/sim/read_observables_dump.py bds_b1i_observables.dat --channels 4 --tail 10
"""
import argparse
from pathlib import Path

import numpy as np


FIELDS = ("rx_time_s", "tow_s", "doppler_hz", "carrier_cycles", "pseudorange_m", "prn", "valid")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump", nargs="?", default="bds_b1i_observables.dat", help="Hybrid_Observables dump file")
    ap.add_argument("--channels", type=int, default=4, help="Channels_B1.count used when running gnss-sdr")
    ap.add_argument("--tail", type=int, default=10, help="Number of last epochs to print")
    ap.add_argument("--all", action="store_true", help="Print invalid rows too")
    args = ap.parse_args()

    path = Path(args.dump)
    if not path.exists():
        raise SystemExit("dump not found: %s" % path)
    if args.channels <= 0:
        raise SystemExit("--channels must be positive")

    raw = np.fromfile(path, dtype=np.float64)
    row_len = len(FIELDS)
    epoch_len = args.channels * row_len
    if raw.size < epoch_len:
        raise SystemExit("dump too small: %d doubles, need at least %d" % (raw.size, epoch_len))

    usable = (raw.size // epoch_len) * epoch_len
    if usable != raw.size:
        print("warn: ignoring %d trailing doubles (partial epoch)" % (raw.size - usable))
    data = raw[:usable].reshape((-1, args.channels, row_len))

    start = max(0, data.shape[0] - args.tail)
    print("file=%s epochs=%d channels=%d showing=%d..%d" %
          (path, data.shape[0], args.channels, start, data.shape[0] - 1))
    print("%6s %3s %4s %10s %10s %14s %10s" %
          ("epoch", "ch", "prn", "rx_time", "tow", "pseudorange_m", "doppler"))
    print("-" * 72)

    shown = 0
    for e in range(start, data.shape[0]):
        for ch in range(args.channels):
            rx_time, tow, doppler, _carrier, prange, prn, valid = data[e, ch]
            if not args.all and valid < 0.5:
                continue
            print("%6d %3d %4d %10.3f %10.3f %14.3f %10.1f" %
                  (e, ch, int(round(prn)), rx_time, tow, prange, doppler))
            shown += 1
    if shown == 0:
        print("no valid pseudorange rows in selected tail; try --tail 200 or check lock/overflow")


if __name__ == "__main__":
    main()

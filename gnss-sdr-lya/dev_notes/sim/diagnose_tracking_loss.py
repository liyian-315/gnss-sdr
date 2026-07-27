#!/usr/bin/env python3
"""Diagnose tracking loss-of-lock events from a dense correlator dump.

Uses the per-epoch fields the dense dump already carries (cn0_snv_db_hz,
carrier_lock_test, carrier_doppler_hz, rem_code_phase_chips) to answer Codex's
Phase-B question: around a loss (e.g. the L5Q ~22 s event), WHICH discriminator
degrades first -- carrier lock, C/N0, code phase, or a Doppler jump? This tells
carrier cycle-slip / CN0 fade / code-loop failure apart, and (across run1/run3)
whether the loss time is fixed (scenario) or moves (loop dynamics).

No trk dump needed -- the dense dump is enough.

Examples:
  python3 dev_notes/sim/diagnose_tracking_loss.py --dense l5_pilot_dense_ch_0.dat.json
  python3 dev_notes/sim/diagnose_tracking_loss.py --dense l5_pilot_dense_ch_0.dat.json \
      --around 22 --window 3 --plot loss22_anatomy.png
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_dense_correlator_dump as rd  # noqa: E402


def find_events(t, lock, cn0, sc, lock_th, cn0_th, epoch_step, min_gap_s):
    """Return onset times of degraded regions and of sample-counter gaps (reacquire)."""
    degraded = (lock < lock_th) | (cn0 < cn0_th)
    events = []
    # onsets of degraded stretches
    prev = False
    for k in range(len(degraded)):
        if degraded[k] and not prev:
            events.append(("degrade", float(t[k]), k))
        prev = degraded[k]
    # sample-counter jumps (reacquisition restarts the counter or skips ahead)
    if epoch_step > 0:
        dsc = np.diff(sc.astype(np.int64))
        for k in np.where(np.abs(dsc) > 3 * epoch_step)[0]:
            events.append(("sc_gap", float(t[k + 1]), int(k + 1)))
    # merge events closer than min_gap_s (keep earliest)
    events.sort(key=lambda e: e[1])
    merged = []
    for e in events:
        if merged and (e[1] - merged[-1][1]) < min_gap_s:
            continue
        merged.append(e)
    return merged


def lead_metric(t, lock, cn0, dopp, k_event, pre_n, lock_th, cn0_th):
    lo = max(0, k_event - pre_n)
    seg = slice(lo, k_event + 1)
    tl = t[seg]
    lk, c0, dp = lock[seg], cn0[seg], dopp[seg]
    # earliest crossing time of each threshold inside the pre-window
    def first_cross(sig, th, below=True):
        idx = np.where(sig < th)[0] if below else np.where(sig > th)[0]
        return float(tl[idx[0]]) if len(idx) else None
    t_lock = first_cross(lk, lock_th)
    t_cn0 = first_cross(c0, cn0_th)
    dopp_excursion = float(np.max(np.abs(dp - np.median(dopp)))) if len(dp) else float("nan")
    lead = "none"
    if t_lock is not None and (t_cn0 is None or t_lock <= t_cn0):
        lead = "carrier_lock"
    elif t_cn0 is not None:
        lead = "cn0"
    return dict(min_lock=float(np.min(lk)), min_cn0=float(np.min(c0)),
                dopp_excursion_hz=dopp_excursion, t_lock=t_lock, t_cn0=t_cn0, lead=lead)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dense", required=True, help="dense .dat or .dat.json")
    ap.add_argument("--lock-th", type=float, default=0.6, help="carrier_lock_test threshold")
    ap.add_argument("--cn0-th", type=float, default=30.0, help="CN0 dB-Hz threshold")
    ap.add_argument("--pre-window", type=float, default=1.0, help="seconds before each event to attribute the lead metric")
    ap.add_argument("--min-gap", type=float, default=1.0, help="merge events closer than this many seconds")
    ap.add_argument("--around", type=float, help="zoom the plot around this time [s]")
    ap.add_argument("--window", type=float, default=3.0, help="half-width [s] for --around zoom")
    ap.add_argument("--plot", help="PNG output for the loss-anatomy time series")
    args = ap.parse_args()

    _, dense_bin, meta = rd.load_metadata(args.dense)
    rec = rd.read_records(dense_bin, meta)
    fs = float(meta.get("sampling_frequency_hz", 0.0)) or 1.0
    sc = rec["sample_counter"].astype(np.int64)
    t = (sc - sc[0]) / fs
    lock = rec["carrier_lock_test"].astype(float)
    cn0 = rec["cn0_snv_db_hz"].astype(float)
    dopp = rec["carrier_doppler_hz"].astype(float)
    epoch_step = int(np.median(np.diff(sc))) if len(sc) > 1 else 0
    pre_n = max(1, int(args.pre_window * fs / max(1, epoch_step)))

    print("dense: %s" % dense_bin)
    print("records=%d  fs=%.1f MHz  span=%.1f s  median CN0=%.1f  median lock=%.3f"
          % (len(rec), fs / 1e6, t[-1] if len(t) else 0.0, np.median(cn0), np.median(lock)))

    events = find_events(t, lock, cn0, sc, args.lock_th, args.cn0_th, epoch_step, args.min_gap)
    print("\ndetected %d event(s) (lock<%.2f or CN0<%.0f, or sample-counter gap):"
          % (len(events), args.lock_th, args.cn0_th))
    print("  time_s   type      lead          min_lock  min_cn0  dopp_excursion_hz")
    print("  " + "-" * 68)
    for kind, te, k in events:
        info = lead_metric(t, lock, cn0, dopp, k, pre_n, args.lock_th, args.cn0_th)
        print("  %6.2f   %-8s  %-12s  %8.3f  %7.1f  %10.1f"
              % (te, kind, info["lead"], info["min_lock"], info["min_cn0"], info["dopp_excursion_hz"]))
    if not events:
        print("  (none) — tracking held the whole file at these thresholds")

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
        ax[0].plot(t, cn0, lw=0.8); ax[0].axhline(args.cn0_th, color="r", ls=":", lw=0.8)
        ax[0].set_ylabel("CN0 [dB-Hz]"); ax[0].grid(True, alpha=0.3)
        ax[1].plot(t, lock, lw=0.8); ax[1].axhline(args.lock_th, color="r", ls=":", lw=0.8)
        ax[1].set_ylabel("carrier_lock_test"); ax[1].grid(True, alpha=0.3)
        ax[2].plot(t, dopp, lw=0.8); ax[2].set_ylabel("Doppler [Hz]")
        ax[2].set_xlabel("time [s]"); ax[2].grid(True, alpha=0.3)
        for _kind, te, _k in events:
            for a in ax:
                a.axvline(te, color="k", ls="--", lw=0.6, alpha=0.6)
        if args.around is not None:
            for a in ax:
                a.set_xlim(args.around - args.window, args.around + args.window)
        ax[0].set_title("Tracking loss anatomy: %s" % os.path.basename(str(dense_bin)))
        fig.tight_layout(); fig.savefig(args.plot, dpi=150)
        print("\nplot -> %s" % args.plot)


if __name__ == "__main__":
    main()

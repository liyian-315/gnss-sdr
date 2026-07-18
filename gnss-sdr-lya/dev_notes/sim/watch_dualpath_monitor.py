#!/usr/bin/env python3
"""Watch GNSS-SDR Monitor UDP protobuf and print dual-path observables.

This parser intentionally avoids generated *_pb2.py files. It decodes only the
fields needed from docs/protobuf/gnss_synchro.proto, so it can run on the Ubuntu
test machine with plain Python.

Example:
  python3 dev_notes/sim/watch_dualpath_monitor.py --port 1234 --csv
"""
import argparse
import csv
import json
import socket
import struct
import sys
import time


FIELDS = (
    "host_time_s",
    "system",
    "signal",
    "prn",
    "primary_channel",
    "primary_pseudorange_m",
    "primary_cn0_db_hz",
    "primary_doppler_hz",
    "second_channel",
    "second_pseudorange_m",
    "second_cn0_db_hz",
    "second_doppler_hz",
    "delta_m",
)


def read_varint(buf, pos):
    shift = 0
    result = 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varint")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def skip_field(buf, pos, wire_type):
    if wire_type == 0:
        _, pos = read_varint(buf, pos)
        return pos
    if wire_type == 1:
        return pos + 8
    if wire_type == 2:
        size, pos = read_varint(buf, pos)
        return pos + size
    if wire_type == 5:
        return pos + 4
    raise ValueError("unsupported protobuf wire type: %d" % wire_type)


def parse_gnss_synchro(buf):
    pos = 0
    out = {}
    while pos < len(buf):
        tag, pos = read_varint(buf, pos)
        field = tag >> 3
        wire = tag & 0x07
        if field in (1, 2) and wire == 2:
            size, pos = read_varint(buf, pos)
            value = buf[pos:pos + size].decode("utf-8", errors="replace")
            pos += size
            out["system" if field == 1 else "signal"] = value
        elif field in (3, 4, 9, 10, 17, 18, 20, 21, 24, 26, 27, 28) and wire == 0:
            value, pos = read_varint(buf, pos)
            key = {
                3: "prn",
                4: "channel_id",
                9: "flag_valid_acquisition",
                10: "fs",
                17: "tracking_sample_counter",
                18: "flag_valid_symbol_output",
                20: "flag_valid_word",
                21: "tow_at_current_symbol_ms",
                24: "flag_valid_pseudorange",
                26: "flag_pll_180_deg_phase_locked",
                27: "flag_cycle_slip",
                28: "signal_path",
            }[field]
            out[key] = int(value)
        elif field in (5, 6, 11, 12, 13, 14, 15, 16, 22, 23, 25) and wire == 1:
            value = struct.unpack_from("<d", buf, pos)[0]
            pos += 8
            key = {
                5: "acq_delay_samples",
                6: "acq_doppler_hz",
                11: "prompt_i",
                12: "prompt_q",
                13: "cn0_db_hz",
                14: "carrier_doppler_hz",
                15: "carrier_phase_rads",
                16: "code_phase_samples",
                22: "pseudorange_m",
                23: "rx_time",
                25: "interp_tow_ms",
            }[field]
            out[key] = value
        else:
            pos = skip_field(buf, pos, wire)
    out.setdefault("signal_path", 0)
    return out


def parse_observables(buf):
    pos = 0
    rows = []
    while pos < len(buf):
        tag, pos = read_varint(buf, pos)
        field = tag >> 3
        wire = tag & 0x07
        if field == 1 and wire == 2:
            size, pos = read_varint(buf, pos)
            rows.append(parse_gnss_synchro(buf[pos:pos + size]))
            pos += size
        else:
            pos = skip_field(buf, pos, wire)
    return rows


def update_state(state, rows, require_valid):
    changed_keys = set()
    for row in rows:
        if require_valid and not row.get("flag_valid_pseudorange", 0):
            continue
        key = (row.get("system", ""), row.get("signal", ""), row.get("prn", 0))
        path = row.get("signal_path", 0)
        if path in (0, 1):
            row["_host_time_s"] = time.time()
            state.setdefault(key, {})[path] = row
            changed_keys.add(key)
    return changed_keys


def make_pair(state, key, stale_sec):
    paths = state.get(key, {})
    if 0 not in paths or 1 not in paths:
        return None
    now = time.time()
    if stale_sec > 0:
        if now - paths[0].get("_host_time_s", 0.0) > stale_sec:
            return None
        if now - paths[1].get("_host_time_s", 0.0) > stale_sec:
            return None
    system, signal, prn = key
    primary = paths[0]
    second = paths[1]
    primary_pr = primary.get("pseudorange_m", 0.0)
    second_pr = second.get("pseudorange_m", 0.0)
    return {
        "host_time_s": now,
        "system": system,
        "signal": signal,
        "prn": prn,
        "primary_channel": primary.get("channel_id", -1),
        "primary_pseudorange_m": primary_pr,
        "primary_cn0_db_hz": primary.get("cn0_db_hz", 0.0),
        "primary_doppler_hz": primary.get("carrier_doppler_hz", 0.0),
        "second_channel": second.get("channel_id", -1),
        "second_pseudorange_m": second_pr,
        "second_cn0_db_hz": second.get("cn0_db_hz", 0.0),
        "second_doppler_hz": second.get("carrier_doppler_hz", 0.0),
        "delta_m": second_pr - primary_pr,
    }


def pair_rows(state, changed_keys, stale_sec):
    for key in sorted(changed_keys):
        paired = make_pair(state, key, stale_sec)
        if paired is not None:
            yield paired


def print_table_header():
    print("%10s %3s %3s %3s %14s %8s %14s %8s %12s" %
          ("time", "sys", "sig", "prn", "primary_m", "cn0", "second_m", "cn0", "delta_m"))
    print("-" * 86)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=1234)
    ap.add_argument("--csv", action="store_true", help="Write stable CSV rows to stdout")
    ap.add_argument("--jsonl", action="store_true", help="Write stable JSONL rows to stdout")
    ap.add_argument("--all", action="store_true", help="Include rows without valid pseudorange")
    ap.add_argument("--stale-sec", type=float, default=2.0, help="Drop path pairs older than this. 0 disables")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))

    writer = None
    if args.csv:
        writer = csv.DictWriter(sys.stdout, fieldnames=FIELDS)
        writer.writeheader()
    elif not args.jsonl:
        print_table_header()

    state = {}
    while True:
        packet, _addr = sock.recvfrom(65535)
        try:
            rows = parse_observables(packet)
        except ValueError as exc:
            print("warn: failed to parse monitor packet: %s" % exc, file=sys.stderr)
            continue
        changed_keys = update_state(state, rows, require_valid=not args.all)
        for paired in pair_rows(state, changed_keys, args.stale_sec):
            if args.csv:
                writer.writerow(paired)
                sys.stdout.flush()
            elif args.jsonl:
                print(json.dumps(paired, sort_keys=True), flush=True)
            else:
                print("%10.3f %3s %3s %3d %14.3f %8.2f %14.3f %8.2f %12.3f" %
                      (paired["host_time_s"], paired["system"], paired["signal"], paired["prn"],
                       paired["primary_pseudorange_m"], paired["primary_cn0_db_hz"],
                       paired["second_pseudorange_m"], paired["second_cn0_db_hz"],
                       paired["delta_m"]), flush=True)


if __name__ == "__main__":
    main()

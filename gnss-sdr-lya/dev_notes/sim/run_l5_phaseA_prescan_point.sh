#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${UHD_IMAGES_DIR:-}" && -d /usr/local/share/uhd/images ]]; then
  export UHD_IMAGES_DIR=/usr/local/share/uhd/images
fi

usage() {
  cat <<'EOF'
Run one short GPS L5 Phase A prescan point on B210.

Purpose:
  Build the simulator-power / attenuator / USRP-gain -> measured-CN0 map before
  the full Phase A fingerprint sweep. This is a short, cheap capture, not the
  final fingerprint dataset.

Example:
  bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag pwr45_g40 --sim-power-label -45

Options:
  --tag NAME              Required output tag.
  --sim-power-label TEXT  Optional label for the simulator output setting.
  --prn N                 GPS L5 PRN. Default: 28.
  --secs N                Record seconds. Default: 15.
  --rate N                Sample rate. Default: 20000000.
  --gain N                B210 gain dB. Default: 40.
  --ant NAME              B210 antenna. Default: RX2.
  --device-args ARGS      UHD device args. Default: serial=31502C6.
  --out-root DIR          Output root. Default: /home/bupt/lya/gnss_data/phaseA_prescan.
  --min-lock-run N        Sustained lock min records for check. Default: 2000.
  --settle-epochs N       Drop first N records of each kept segment. Default: 200.
  --guard-before-loss N   Optional tail guard. Default: 0.
EOF
}

TAG=""
SIM_POWER_LABEL=""
PRN="28"
SECS="15"
RATE="20000000"
GAIN="40"
ANT="RX2"
DEVICE_ARGS="serial=31502C6"
OUT_ROOT="/home/bupt/lya/gnss_data/phaseA_prescan"
MIN_LOCK_RUN="2000"
SETTLE_EPOCHS="200"
GUARD_BEFORE_LOSS="0"
FREQ="1176450000"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag) TAG="$2"; shift 2 ;;
    --sim-power-label) SIM_POWER_LABEL="$2"; shift 2 ;;
    --prn) PRN="$2"; shift 2 ;;
    --secs) SECS="$2"; shift 2 ;;
    --rate) RATE="$2"; shift 2 ;;
    --gain) GAIN="$2"; shift 2 ;;
    --ant) ANT="$2"; shift 2 ;;
    --device-args) DEVICE_ARGS="$2"; shift 2 ;;
    --out-root) OUT_ROOT="$2"; shift 2 ;;
    --min-lock-run) MIN_LOCK_RUN="$2"; shift 2 ;;
    --settle-epochs) SETTLE_EPOCHS="$2"; shift 2 ;;
    --guard-before-loss) GUARD_BEFORE_LOSS="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$TAG" ]]; then
  usage >&2
  exit 2
fi

if [[ ! -x ./build/src/main/gnss-sdr ]]; then
  echo "error: ./build/src/main/gnss-sdr not found; run from repo root on the NUC" >&2
  exit 1
fi

OUT="${OUT_ROOT}/${TAG}"
mkdir -p "$OUT"

RAW_BASENAME="l5_prescan_prn${PRN}_${TAG}_${RATE}sps_g${GAIN}_${SECS}s_ishort.dat"
TMP="/dev/shm/${RAW_BASENAME}"
RAW="${OUT}/${RAW_BASENAME}"
CONF="/tmp/l5_prescan_${TAG}.conf"

rm -f "$TMP" "$RAW" \
  "$OUT/record.log" "$OUT/run_gnss_sdr.log" "$OUT/summary.txt" \
  "$OUT/l5_prescan_dense_ch_0.dat" "$OUT/l5_prescan_dense_ch_0.dat.json" \
  "$OUT/l5_prescan_Rtau.png" "$OUT/l5_prescan_Rtau.png.csv" "$OUT/l5_prescan_fp.png"

{
  echo "tag=$TAG"
  echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "sim_power_label=$SIM_POWER_LABEL"
  echo "prn=$PRN"
  echo "secs=$SECS"
  echo "rate=$RATE"
  echo "freq=$FREQ"
  echo "gain=$GAIN"
  echo "ant=$ANT"
  echo "device_args=$DEVICE_ARGS"
  echo "out=$OUT"
} > "$OUT/summary.txt"

echo "[1/5] Recording short L5 prescan sample -> $RAW"
NSAMPS="$(python3 - <<PY
print(int(float("$RATE") * float("$SECS")))
PY
)"
set +e
uhd_rx_cfile -a "$DEVICE_ARGS" -f "$FREQ" -r "$RATE" -g "$GAIN" -A "$ANT" \
  -s --stream-args num_recv_frames=1024 -N "$NSAMPS" "$TMP" 2>&1 | tee "$OUT/record.log"
REC_STATUS=${PIPESTATUS[0]}
set -e
if [[ "$REC_STATUS" -ne 0 ]] && grep -q "No devices found" "$OUT/record.log"; then
  echo "warn: first UHD open failed after firmware/image load; retrying once" | tee -a "$OUT/record.log"
  sleep 1
  uhd_rx_cfile -a "$DEVICE_ARGS" -f "$FREQ" -r "$RATE" -g "$GAIN" -A "$ANT" \
    -s --stream-args num_recv_frames=1024 -N "$NSAMPS" "$TMP" 2>&1 | tee -a "$OUT/record.log"
elif [[ "$REC_STATUS" -ne 0 && -f "$TMP" ]]; then
  actual_size="$(stat -c %s "$TMP")"
  expected_size="$(python3 - <<PY
print(int(float("$RATE") * float("$SECS") * 4))
PY
)"
  if [[ "$actual_size" -ge "$expected_size" ]]; then
    echo "warn: uhd_rx_cfile returned $REC_STATUS but output size is complete ($actual_size bytes); continuing" | tee -a "$OUT/record.log"
  else
    exit "$REC_STATUS"
  fi
else
  exit "$REC_STATUS"
fi
mv "$TMP" "$RAW"
ls -lh "$RAW" | tee -a "$OUT/summary.txt"
if grep -qi overflow "$OUT/record.log"; then
  echo "record_overflow=1" | tee -a "$OUT/summary.txt"
else
  echo "record_overflow=0" | tee -a "$OUT/summary.txt"
fi

echo "[2/5] Generating L5Q pilot robust offline config"
python3 dev_notes/sim/make_l5_dualpath_conf.py \
  --source file --input "$RAW" --sample-type ishort --output "$CONF" \
  --prns "$PRN" --rate "$RATE" --scenario cable --track-pilot \
  --carrier-lock-th 0.55 --max-lock-fail 300 --max-carrier-lock-fail 20000 \
  --observables-dump "$OUT/l5_prescan_observables.dat" \
  --enable-dense-correlator --dense-taps=-1.5:0.1:1.5 --dense-decimation 1 \
  --dense-dump-prefix "$OUT/l5_prescan_dense_ch_"

echo "[3/5] Running GNSS-SDR offline"
./build/src/main/gnss-sdr --config_file="$CONF" 2>&1 | tee "$OUT/run_gnss_sdr.log"
grep -n "Loss of lock" "$OUT/run_gnss_sdr.log" | tee "$OUT/loss_lines.txt" || true
grep -n "DUALPATH_OBS" "$OUT/run_gnss_sdr.log" | tee "$OUT/obs_lines.txt" || true

echo "[4/5] Checking dense R(tau) with sustained-lock selector"
python3 dev_notes/sim/check_dense_vs_prompt.py \
  --dense "$OUT/l5_prescan_dense_ch_0.dat.json" \
  --cn0-min 45 --lock-min 0.6 \
  --min-lock-run "$MIN_LOCK_RUN" --settle-epochs "$SETTLE_EPOCHS" \
  --guard-before-loss "$GUARD_BEFORE_LOSS" \
  --ref-out "$OUT/l5_prescan_Rtau.png" 2>&1 | tee "$OUT/check_dense.log" || true

echo "[5/5] Summarizing measured CN0 and fingerprint quality"
python3 - "$OUT" <<'PY' | tee -a "$OUT/summary.txt"
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.getcwd(), "dev_notes", "sim"))
import read_dense_correlator_dump as rd

out = sys.argv[1]
dense_json = os.path.join(out, "l5_prescan_dense_ch_0.dat.json")
_, dense_bin, meta = rd.load_metadata(dense_json)
rec = rd.read_records(dense_bin, meta)
cn0 = rec["cn0_snv_db_hz"].astype(float)
lock = rec["carrier_lock_test"].astype(float)
valid_cn0 = cn0[cn0 > 0]
print("dense_records=%d" % len(rec))
if len(valid_cn0):
    print("cn0_median=%.2f" % float(np.median(valid_cn0)))
    print("cn0_p10=%.2f" % float(np.percentile(valid_cn0, 10)))
    print("cn0_p90=%.2f" % float(np.percentile(valid_cn0, 90)))
else:
    print("cn0_median=nan")
if len(lock):
    print("lock_median=%.4f" % float(np.median(lock)))
else:
    print("lock_median=nan")

csv = os.path.join(out, "l5_prescan_Rtau.png.csv")
if os.path.exists(csv):
    meta_line = ""
    with open(csv, "r", encoding="utf-8") as fh:
        first = fh.readline().strip()
        if first.startswith("#"):
            meta_line = first[1:].strip()
    if meta_line:
        print("rtau_meta=%s" % meta_line)
PY

if [[ -f "$OUT/l5_prescan_Rtau.png.csv" ]]; then
  python3 dev_notes/sim/aggregate_reference_fingerprint.py \
    "$OUT/l5_prescan_Rtau.png.csv" \
    --labels "$TAG" --chip-m 29.3 --min-kept-fraction 0.2 \
    --plot "$OUT/l5_prescan_fp.png" 2>&1 | tee "$OUT/aggregate.log"
else
  echo "aggregate_skipped=1" | tee -a "$OUT/summary.txt"
fi

echo "done: $OUT"

#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run one B210 record -> offline acquisition dump -> multipath analysis test.

Examples:
  # GPS L5I PRN18, B210 RX2, 30 s, gain 76
  bash dev_notes/sim/run_b210_offline_multipath_test.sh \
    --signal l5 --prn 18 --tag gps_l5_prn18_twosim_1000m

  # BDS B1I PRN9, B210 RX2, 30 s, gain 76
  bash dev_notes/sim/run_b210_offline_multipath_test.sh \
    --signal b1i --prn 9 --tag b1i_prn9_twosim_1000m

Options:
  --signal b1i|l5     Signal to test. Required.
  --prn N             Satellite PRN. Required.
  --tag NAME          Output tag. Required.
  --secs N            Record seconds. Default: 30.
  --chunk-secs N      Max seconds per raw file. Default: 30.
  --gain N            B210 gain dB. Default: 76.
  --ant NAME          B210 antenna port. Default: RX2.
  --pfa VALUE         Override Acquisition pfa in temp config.
  --max-dwells N      Override L5 max_dwells in temp config.
  --expected-delay-m N Prefer best dump whose abs(delta meters) is closest to N.
  --skip-record       Reuse /tmp/<tag>.dat and only rerun offline analysis.
EOF
}

SIGNAL=""
PRN=""
TAG=""
SECS="30"
GAIN="76"
ANT="RX2"
PFA=""
MAX_DWELLS=""
SKIP_RECORD="0"
CHUNK_SECS="30"
EXPECTED_DELAY_M=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --signal) SIGNAL="$2"; shift 2 ;;
    --prn) PRN="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --secs) SECS="$2"; shift 2 ;;
    --chunk-secs) CHUNK_SECS="$2"; shift 2 ;;
    --gain) GAIN="$2"; shift 2 ;;
    --ant) ANT="$2"; shift 2 ;;
    --pfa) PFA="$2"; shift 2 ;;
    --max-dwells) MAX_DWELLS="$2"; shift 2 ;;
    --expected-delay-m) EXPECTED_DELAY_M="$2"; shift 2 ;;
    --skip-record) SKIP_RECORD="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$SIGNAL" || -z "$PRN" || -z "$TAG" ]]; then
  usage >&2
  exit 2
fi

case "$SIGNAL" in
  b1i)
    FREQ="1561098000"
    RATE="4000000"
    CONF="dev_notes/sim/b1i_offline_prn9.conf"
    ACQ_PREFIX="bds_b1i_acq"
    PATTERN="bds_b1i_acq_*_sat_${PRN}.mat"
    CODE_LENGTH="2046"
    PFA_KEY="Acquisition_B1.pfa"
    DWELL_KEY=""
    ;;
  l5)
    FREQ="1176450000"
    RATE="10000000"
    CONF="dev_notes/sim/l5_offline_prn1.conf"
    ACQ_PREFIX="gps_l5_acq"
    PATTERN="gps_l5_acq_*_sat_${PRN}.mat"
    CODE_LENGTH="10230"
    PFA_KEY="Acquisition_L5.pfa"
    DWELL_KEY="Acquisition_L5.max_dwells"
    ;;
  *)
    echo "--signal must be b1i or l5, got: $SIGNAL" >&2
    exit 2
    ;;
esac

if [[ ! -x ./build-conda/src/main/gnss-sdr ]]; then
  echo "Missing ./build-conda/src/main/gnss-sdr. Run this from repo root after activating conda env gnsssdr." >&2
  exit 1
fi

mapfile -t PART_SECS < <(python3 - "$SECS" "$CHUNK_SECS" <<'PY'
import math, sys
total = float(sys.argv[1])
chunk = float(sys.argv[2])
if total <= 0 or chunk <= 0:
    raise SystemExit("--secs and --chunk-secs must be positive")
n = int(math.ceil(total / chunk))
for i in range(n):
    dur = min(chunk, total - i * chunk)
    if dur <= 0:
        continue
    print(("%g" % dur))
PY
)

if [[ ${#PART_SECS[@]} -eq 1 ]]; then
  RAW_FILES=("/tmp/${TAG}.dat")
  PART_TAGS=("${TAG}")
else
  RAW_FILES=()
  PART_TAGS=()
  for idx in "${!PART_SECS[@]}"; do
    part_no="$(printf "%02d" $((idx + 1)))"
    RAW_FILES+=("/tmp/${TAG}_part${part_no}.dat")
    PART_TAGS+=("${TAG}_part${part_no}")
  done
fi

echo "[1/7] Test parameters"
echo "  signal=${SIGNAL} prn=${PRN} tag=${TAG}"
echo "  freq=${FREQ} rate=${RATE} secs=${SECS} chunk_secs=${CHUNK_SECS} gain=${GAIN} ant=${ANT}"
echo "  expected_delay_m=${EXPECTED_DELAY_M:-none}"
echo "  parts=${#PART_SECS[@]}"

select_best_dump() {
  python3 - "$1" "$CODE_LENGTH" "$EXPECTED_DELAY_M" <<'PY'
import glob, h5py, numpy as np, sys
pattern = sys.argv[1]
code_length = float(sys.argv[2])
expected = float(sys.argv[3]) if sys.argv[3] else None
chip_m = 299792458.0 / (code_length * 1000.0)
best = None
for f in glob.glob(pattern):
    try:
        with h5py.File(f, "r") as h:
            test = float(np.array(h["test_statistic"]).reshape(-1)[0]) if "test_statistic" in h else -1.0
            pos = int(np.array(h["positive_acq"]).reshape(-1)[0]) if "positive_acq" in h else 0
            has2 = int(np.array(h["has_second_peak"]).reshape(-1)[0]) if "has_second_peak" in h else 0
            if expected is not None and has2 and "acq_grid" in h and "acq_delay_samples_2" in h:
                grid = np.array(h["acq_grid"])
                spc = grid.shape[1] / code_length
                drow = int(np.argmax(grid.max(axis=1)))
                main_chip = int(np.argmax(grid[drow])) / spc
                sec_chip = float(np.array(h["acq_delay_samples_2"]).reshape(-1)[0]) / spc
                dm = (sec_chip - main_chip) * chip_m
                score = (pos, has2, -abs(abs(dm) - expected), test)
            else:
                score = (pos, has2, test)
            if best is None or score > best[0]:
                best = (score, f)
    except Exception:
        pass
print(best[1] if best else "")
PY
}

print_raw_stats() {
  python3 - "$1" <<'PY'
import numpy as np, os, sys
p = sys.argv[1]
x = np.fromfile(p, dtype=np.complex64)
if x.size == 0:
    raise SystemExit("raw file is empty: " + p)
a = np.abs(x)
print("  file", p)
print("  bytes", os.path.getsize(p), "samples", x.size)
print("  rms", float(np.sqrt(np.mean(a*a))), "mean_abs", float(a.mean()), "max_abs", float(a.max()))
print("  gt0.1", int((a > 0.1).sum()), "gt0.2", int((a > 0.2).sum()), "gt0.5", int((a > 0.5).sum()))
print("  real_minmax", float(x.real.min()), float(x.real.max()))
print("  imag_minmax", float(x.imag.min()), float(x.imag.max()))
PY
}

run_offline_part() {
  local part_tag="$1"
  local raw="$2"
  local tmp_conf="/tmp/${part_tag}.conf"

  echo "[4/7] Preparing temp config: ${tmp_conf}"
  cp "$CONF" "$tmp_conf"
  sed -i "s#^SignalSource.filename=.*#SignalSource.filename=${raw}#" "$tmp_conf"
  sed -i "s#^Channel0.satellite=.*#Channel0.satellite=${PRN}#" "$tmp_conf"
  if [[ -n "$PFA" ]]; then
    sed -i "s#^${PFA_KEY}=.*#${PFA_KEY}=${PFA}#" "$tmp_conf"
  fi
  if [[ -n "$MAX_DWELLS" && -n "$DWELL_KEY" ]]; then
    sed -i "s#^${DWELL_KEY}=.*#${DWELL_KEY}=${MAX_DWELLS}#" "$tmp_conf"
  fi
  grep -E 'SignalSource.filename|Channel0.satellite|Acquisition_.*pfa|Acquisition_L5.max_dwells' "$tmp_conf" || true

  echo "[5/7] Running GNSS-SDR offline acquisition: ${part_tag}"
  rm -f ${ACQ_PREFIX}*.mat ${ACQ_PREFIX}*.png
  ./build-conda/src/main/gnss-sdr --config_file="$tmp_conf" 2>&1 | tee "/tmp/${part_tag}_run.log"

  echo "[6/7] Multipath analysis: ${part_tag}"
  python3 dev_notes/sim/analyze_multipath.py --pattern "$PATTERN" --code-length "$CODE_LENGTH" \
    | tee "/tmp/${part_tag}_analyze.log"

  echo "[7/7] Selecting best dump and plotting: ${part_tag}"
  local best_dump
  best_dump="$(select_best_dump "$PATTERN")"
  if [[ -z "$best_dump" ]]; then
    echo "No dump matched: ${PATTERN}" >&2
    return 1
  fi
  echo "  best_dump=${best_dump}"
  python3 dev_notes/sim/plot_acq_grid.py "$best_dump" --code-length "$CODE_LENGTH" --zoom-chips 80
  python3 dev_notes/sim/plot_acq_3d.py "$best_dump" --code-length "$CODE_LENGTH"
  local base="${best_dump%.mat}"
  cp "$best_dump" "/tmp/${part_tag}_best.mat"
  cp "${base}.png" "/tmp/${part_tag}_best.png"
  cp "${base}_3d.png" "/tmp/${part_tag}_best_3d.png"
}

BEST_PART_DUMPS=()
for idx in "${!RAW_FILES[@]}"; do
  part_tag="${PART_TAGS[$idx]}"
  raw="${RAW_FILES[$idx]}"
  dur="${PART_SECS[$idx]}"
  echo "[2/7] Recording B210 samples: part $((idx + 1))/${#PART_SECS[@]}"
  if [[ "$SKIP_RECORD" != "1" ]]; then
    echo "  ${dur}s -> ${raw}"
    python3 dev_notes/sim/record_b210.py --secs "$dur" --gain "$GAIN" --ant "$ANT" \
      --freq "$FREQ" --rate "$RATE" -o "$raw" 2>&1 | tee "/tmp/${part_tag}_record.log"
    echo "  flushing file to disk before continuing"
    sync "$raw" 2>/dev/null || sync
  else
    echo "  reusing ${raw}"
  fi

  echo "[3/7] Raw sample quick stats: ${part_tag}"
  print_raw_stats "$raw" | tee "/tmp/${part_tag}_stats.log"

  run_offline_part "$part_tag" "$raw"
  BEST_PART_DUMPS+=("/tmp/${part_tag}_best.mat")
done

BEST_DUMP="$(select_best_dump "/tmp/${TAG}_part*_best.mat")"
if [[ -z "$BEST_DUMP" && ${#BEST_PART_DUMPS[@]} -eq 1 ]]; then
  BEST_DUMP="${BEST_PART_DUMPS[0]}"
fi

BASE="${BEST_DUMP%.mat}"
if [[ "$BEST_DUMP" != "/tmp/${TAG}_best.mat" ]]; then
  cp "$BEST_DUMP" "/tmp/${TAG}_best.mat"
fi
if [[ "${BASE}.png" != "/tmp/${TAG}_best.png" ]]; then
  cp "${BASE}.png" "/tmp/${TAG}_best.png"
fi
if [[ "${BASE}_3d.png" != "/tmp/${TAG}_best_3d.png" ]]; then
  cp "${BASE}_3d.png" "/tmp/${TAG}_best_3d.png"
fi
if [[ ${#PART_SECS[@]} -gt 1 ]]; then
  cat /tmp/${TAG}_part*_analyze.log > "/tmp/${TAG}_analyze.log" 2>/dev/null || true
fi
echo "Done."
echo "  segmented recording avoids sustained large-file writes that caused USRP overflow at long durations."
echo "  logs: /tmp/${TAG}*_record.log /tmp/${TAG}*_run.log /tmp/${TAG}_analyze.log"
echo "  best: /tmp/${TAG}_best.mat /tmp/${TAG}_best.png /tmp/${TAG}_best_3d.png"

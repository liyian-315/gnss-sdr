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
  --gain N            B210 gain dB. Default: 76.
  --ant NAME          B210 antenna port. Default: RX2.
  --pfa VALUE         Override Acquisition pfa in temp config.
  --max-dwells N      Override L5 max_dwells in temp config.
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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --signal) SIGNAL="$2"; shift 2 ;;
    --prn) PRN="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --secs) SECS="$2"; shift 2 ;;
    --gain) GAIN="$2"; shift 2 ;;
    --ant) ANT="$2"; shift 2 ;;
    --pfa) PFA="$2"; shift 2 ;;
    --max-dwells) MAX_DWELLS="$2"; shift 2 ;;
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

RAW="/tmp/${TAG}.dat"
TMP_CONF="/tmp/${TAG}.conf"

echo "[1/7] Test parameters"
echo "  signal=${SIGNAL} prn=${PRN} tag=${TAG}"
echo "  freq=${FREQ} rate=${RATE} secs=${SECS} gain=${GAIN} ant=${ANT}"
echo "  raw=${RAW}"

if [[ "$SKIP_RECORD" != "1" ]]; then
  echo "[2/7] Recording B210 samples"
  python3 dev_notes/sim/record_b210.py --secs "$SECS" --gain "$GAIN" --ant "$ANT" \
    --freq "$FREQ" --rate "$RATE" -o "$RAW" 2>&1 | tee "/tmp/${TAG}_record.log"
else
  echo "[2/7] Reusing existing raw file: ${RAW}"
fi

echo "[3/7] Raw sample quick stats"
python3 - "$RAW" <<'PY'
import numpy as np, os, sys
p = sys.argv[1]
x = np.fromfile(p, dtype=np.complex64)
if x.size == 0:
    raise SystemExit("raw file is empty: " + p)
a = np.abs(x)
print("  bytes", os.path.getsize(p), "samples", x.size)
print("  rms", float(np.sqrt(np.mean(a*a))), "mean_abs", float(a.mean()), "max_abs", float(a.max()))
print("  gt0.1", int((a > 0.1).sum()), "gt0.2", int((a > 0.2).sum()), "gt0.5", int((a > 0.5).sum()))
print("  real_minmax", float(x.real.min()), float(x.real.max()))
print("  imag_minmax", float(x.imag.min()), float(x.imag.max()))
PY

echo "[4/7] Preparing temp config: ${TMP_CONF}"
cp "$CONF" "$TMP_CONF"
sed -i "s#^SignalSource.filename=.*#SignalSource.filename=${RAW}#" "$TMP_CONF"
sed -i "s#^Channel0.satellite=.*#Channel0.satellite=${PRN}#" "$TMP_CONF"
if [[ -n "$PFA" ]]; then
  sed -i "s#^${PFA_KEY}=.*#${PFA_KEY}=${PFA}#" "$TMP_CONF"
fi
if [[ -n "$MAX_DWELLS" && -n "$DWELL_KEY" ]]; then
  sed -i "s#^${DWELL_KEY}=.*#${DWELL_KEY}=${MAX_DWELLS}#" "$TMP_CONF"
fi
grep -E 'SignalSource.filename|Channel0.satellite|Acquisition_.*pfa|Acquisition_L5.max_dwells' "$TMP_CONF" || true

echo "[5/7] Running GNSS-SDR offline acquisition"
rm -f ${ACQ_PREFIX}*.mat ${ACQ_PREFIX}*.png
./build-conda/src/main/gnss-sdr --config_file="$TMP_CONF" 2>&1 | tee "/tmp/${TAG}_run.log"

echo "[6/7] Multipath analysis"
python3 dev_notes/sim/analyze_multipath.py --pattern "$PATTERN" --code-length "$CODE_LENGTH" \
  | tee "/tmp/${TAG}_analyze.log"

echo "[7/7] Selecting best dump and plotting"
BEST_DUMP="$(python3 - "$PATTERN" <<'PY'
import glob, h5py, numpy as np, sys
best = None
for f in glob.glob(sys.argv[1]):
    try:
        with h5py.File(f, "r") as h:
            test = float(np.array(h["test_statistic"]).reshape(-1)[0]) if "test_statistic" in h else -1.0
            pos = int(np.array(h["positive_acq"]).reshape(-1)[0]) if "positive_acq" in h else 0
            score = (pos, test)
            if best is None or score > best[0]:
                best = (score, f)
    except Exception:
        pass
print(best[1] if best else "")
PY
)"

if [[ -z "$BEST_DUMP" ]]; then
  echo "No dump matched: ${PATTERN}" >&2
  exit 1
fi

echo "  best_dump=${BEST_DUMP}"
python3 dev_notes/sim/plot_acq_grid.py "$BEST_DUMP" --code-length "$CODE_LENGTH" --zoom-chips 80
python3 dev_notes/sim/plot_acq_3d.py "$BEST_DUMP" --code-length "$CODE_LENGTH"

BASE="${BEST_DUMP%.mat}"
cp "$BEST_DUMP" "/tmp/${TAG}_best.mat"
cp "${BASE}.png" "/tmp/${TAG}_best.png"
cp "${BASE}_3d.png" "/tmp/${TAG}_best_3d.png"
echo "Done."
echo "  logs: /tmp/${TAG}_record.log /tmp/${TAG}_run.log /tmp/${TAG}_analyze.log"
echo "  best: /tmp/${TAG}_best.mat /tmp/${TAG}_best.png /tmp/${TAG}_best_3d.png"

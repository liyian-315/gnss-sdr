#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <gnss-sdr-binary> <config> [--run-seconds N]" >&2
}

[[ $# -ge 2 ]] || { usage; exit 2; }
binary=$1
config=$2
shift 2
run_seconds=0
if [[ $# -gt 0 ]]; then
    [[ $# -eq 2 && $1 == "--run-seconds" ]] || { usage; exit 2; }
    run_seconds=$2
fi

[[ -x $binary ]] || { echo "ERROR: binary is not executable: $binary" >&2; exit 1; }
[[ -f $config ]] || { echo "ERROR: config not found: $config" >&2; exit 1; }

"$binary" --version
required=("Observables.stdout=true" "Acquisition_L5.dump=false" "Tracking_L5.dump=false" "Observables.dump=false" "SignalSource.dump=false")
for setting in "${required[@]}"; do
    grep -Fqx "$setting" "$config" || { echo "ERROR: missing safe product setting: $setting" >&2; exit 1; }
done
if grep -Eq '^Tracking_L5\.dense_correlator_dump=true' "$config"; then
    echo "ERROR: dense correlator dump must be disabled in a product config" >&2
    exit 1
fi

echo "Configuration safety checks: PASS"
if [[ $run_seconds -eq 0 ]]; then
    exit 0
fi

log="runtime-check-$(date +%Y%m%d-%H%M%S).log"
set +e
timeout --signal=INT "${run_seconds}s" "$binary" --config_file="$config" 2>&1 | tee "$log"
run_rc=${PIPESTATUS[0]}
set -e
if [[ $run_rc -ne 0 && $run_rc -ne 124 && $run_rc -ne 130 ]]; then
    echo "ERROR: GNSS-SDR exited with status $run_rc" >&2
    exit "$run_rc"
fi
if grep -qi 'overflow' "$log"; then
    echo "ERROR: UHD overflow found in $log" >&2
    exit 3
fi
grep -q '^DUALPATH_STATUS version=1 ' "$log" || { echo "ERROR: no version-1 dual-path status found in $log" >&2; exit 4; }
echo "Runtime smoke check: PASS ($log)"

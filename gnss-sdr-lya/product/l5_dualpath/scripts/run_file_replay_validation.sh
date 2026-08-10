#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <gnss-sdr-binary> <file-replay-template.conf> <iq.sc16> <prn> <output-dir> [--single-source-negative]" >&2
}

[[ $# -ge 5 && $# -le 6 ]] || { usage; exit 2; }
binary=$(realpath "$1")
template=$(realpath "$2")
iq=$(realpath "$3")
prn=$4
output_dir=$5
mode=${6:-}
[[ -z $mode || $mode == "--single-source-negative" ]] || { usage; exit 2; }
[[ $prn =~ ^[0-9]+$ ]] || { echo "ERROR: PRN must be numeric" >&2; exit 2; }
[[ -x $binary ]] || { echo "ERROR: binary is not executable: $binary" >&2; exit 1; }
[[ -f $template ]] || { echo "ERROR: template not found: $template" >&2; exit 1; }
[[ -f $iq ]] || { echo "ERROR: IQ file not found: $iq" >&2; exit 1; }

mkdir -p "$output_dir"
output_dir=$(realpath "$output_dir")
config="$output_dir/replay.conf"
log="$output_dir/receiver.log"
cp "$template" "$config"
sed -i \
    -e "s#^SignalSource.filename=.*#SignalSource.filename=$iq#" \
    -e "s/^Channel0.satellite=.*/Channel0.satellite=$prn/" \
    -e "s/^Channel1.satellite=.*/Channel1.satellite=$prn/" \
    -e "s#^Observables.dual_path_csv_filename=.*#Observables.dual_path_csv_filename=$output_dir/dual_path_status.csv#" \
    "$config"

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bash "$script_dir/check_runtime.sh" "$binary" "$config"
(cd "$output_dir" && "$binary" --config_file="$config" 2>&1 | tee "$log")
status_args=()
[[ -z $mode ]] || status_args+=("$mode")
bash "$script_dir/check_status_log.sh" "$log" "${status_args[@]}" | tee "$output_dir/summary.txt"

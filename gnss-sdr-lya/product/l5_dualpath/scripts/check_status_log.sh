#!/usr/bin/env bash
set -euo pipefail

[[ $# -ge 1 && $# -le 2 ]] || { echo "Usage: $0 <gnss-sdr-log> [--single-source-negative]" >&2; exit 2; }
log=$1
mode=${2:-}
[[ -z $mode || $mode == "--single-source-negative" ]] || { echo "ERROR: unknown mode: $mode" >&2; exit 2; }
[[ -f $log ]] || { echo "ERROR: log not found: $log" >&2; exit 1; }

grep -q '^DUALPATH_STATUS version=1 ' "$log" || { echo "ERROR: no DUALPATH_STATUS version=1 lines" >&2; exit 1; }
awk '
/^DUALPATH_STATUS version=1 / {
  total++
  for (i=1; i<=NF; i++) {
    if ($i ~ /^state=/) { split($i,a,"="); states[a[2]]++ }
    if ($i ~ /^primary_pseudorange_m=/) { split($i,a,"="); if (a[2] != "N/A") primary_valid++ }
    if ($i ~ /^second_pseudorange_m=/) { split($i,a,"="); if (a[2] != "N/A") second_valid++ }
    if ($i ~ /^reacquisition_count=/) { split($i,a,"="); if (a[2] > reacq) reacq=a[2] }
  }
}
END {
  printf "status_total=%d\n", total
  printf "primary_valid_ratio=%.6f\n", total ? primary_valid / total : 0
  printf "second_valid_ratio=%.6f\n", total ? second_valid / total : 0
  split("SEARCHING CANDIDATE RELIABLE DEGRADED LOST NO_SECOND_SOURCE", names, " ")
  for (i=1; i<=6; i++) printf "state_%s=%d\n", names[i], states[names[i]] + 0
  printf "reacquisition_count=%d\n", reacq + 0
}
' "$log" | sort
runtime=$(sed -n 's/^Total GNSS-SDR run time: \([^ ]*\).*/\1/p' "$log" | tail -1)
printf 'runtime_s=%s\n' "${runtime:-N/A}"
delta_values=$(mktemp)
trap 'rm -f "$delta_values"' EXIT
sed -n 's/^DUALPATH_STATUS version=1 .* delta_m=\([^ ]*\) .*/\1/p' "$log" | grep -v '^N/A$' | sort -n > "$delta_values" || true
if [[ -s $delta_values ]]; then
    delta_median=$(awk '{v[NR]=$1} END {if (NR%2) print v[(NR+1)/2]; else printf "%.6f\n", (v[NR/2]+v[NR/2+1])/2}' "$delta_values")
    delta_mad=$(awk -v m="$delta_median" '{d=$1-m; if(d<0)d=-d; print d}' "$delta_values" | sort -n | awk '{v[NR]=$1} END {if (NR%2) print v[(NR+1)/2]; else printf "%.6f\n", (v[NR/2]+v[NR/2+1])/2}')
    printf 'delta_median=%s\n' "$delta_median"
    printf 'delta_MAD=%s\n' "$delta_mad"
else
    echo 'delta_median=N/A'
    echo 'delta_MAD=N/A'
fi
printf 'overflow_count=%s\n' "$(grep -ci 'overflow' "$log" || true)"
printf 'loss_of_lock_count=%s\n' "$(grep -c 'Loss of lock' "$log" || true)"

if [[ $mode == "--single-source-negative" ]]; then
    candidate_count=$(grep -c '^DUALPATH_STATUS version=1 .* state=CANDIDATE ' "$log" || true)
    reliable_count=$(grep -c '^DUALPATH_STATUS version=1 .* state=RELIABLE ' "$log" || true)
    if ((candidate_count > 0 || reliable_count > 0)); then
        echo "ERROR: single-source negative control produced candidate=$candidate_count reliable=$reliable_count" >&2
        exit 5
    fi
    echo "Single-source negative-control state check: PASS"
fi

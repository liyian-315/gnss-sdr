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
  }
}
END {
  printf "status_total=%d\n", total
  for (s in states) printf "state_%s=%d\n", s, states[s]
}
' "$log" | sort
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

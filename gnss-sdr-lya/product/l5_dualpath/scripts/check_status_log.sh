#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 1 ]] || { echo "Usage: $0 <gnss-sdr-log>" >&2; exit 2; }
log=$1
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

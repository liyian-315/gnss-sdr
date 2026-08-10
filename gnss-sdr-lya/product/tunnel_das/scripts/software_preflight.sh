#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
B210_CONF="$ROOT/product/tunnel_das/conf/gps_l5_tunnel_dual_end_b210.conf"
REPLAY_CONF="$ROOT/product/tunnel_das/conf/gps_l5_tunnel_dual_end_file_replay.conf"
BINARY="${GNSS_SDR_BINARY:-$ROOT/build/src/main/gnss-sdr}"
RUN_TESTS="${GNSS_SDR_RUN_TESTS:-$ROOT/build/tests/run_tests}"

fail() { echo "PREFLIGHT_FAIL $*" >&2; exit 1; }
require_line() { grep -Eq "$2" "$1" || fail "$1 missing: $2"; }

echo "git_sha=$(git -C "$ROOT" rev-parse HEAD)"
[[ -f "$B210_CONF" ]] || fail "missing B210 configuration"
[[ -f "$REPLAY_CONF" ]] || fail "missing replay configuration"

for conf in "$B210_CONF" "$REPLAY_CONF"; do
    first_property_line="$(grep -nEm1 '^[A-Za-z0-9_-]+\.' "$conf" | cut -d: -f1)"
    section_line="$(grep -nEm1 '^\[GNSS-SDR\]$' "$conf" | cut -d: -f1)"
    [[ -n "$section_line" && -n "$first_property_line" && "$section_line" -lt "$first_property_line" ]] ||
        fail "$conf has active properties before [GNSS-SDR]"
    require_line "$conf" '^Tunnel\.enable=true$'
    require_line "$conf" '^Tunnel\.length_m='
    require_line "$conf" '^Tunnel\.measurement_position_m='
    require_line "$conf" '^Tunnel\.end_a_fixed_delay_m='
    require_line "$conf" '^Tunnel\.end_b_fixed_delay_m='
    require_line "$conf" '^Tunnel\.identity_max_error_m='
    require_line "$conf" '^Tunnel\.identity_margin_m='
    require_line "$conf" '^Tunnel\.identity_confirm_epochs='
    require_line "$conf" '^Observables\.dual_path_csv=false$'
    require_line "$conf" '^Observables\.stdout=true$'
    prn0="$(sed -n 's/^Channel0\.satellite=//p' "$conf")"
    prn1="$(sed -n 's/^Channel1\.satellite=//p' "$conf")"
    [[ -n "$prn0" && "$prn0" == "$prn1" ]] || fail "$conf Channel0/Channel1 PRNs differ"
done

require_line "$B210_CONF" '^SignalSource\.implementation=UHD_Signal_Source$'
require_line "$B210_CONF" '^SignalSource\.device_serial='
require_line "$B210_CONF" '^SignalSource\.gain='
require_line "$REPLAY_CONF" '^SignalSource\.implementation=File_Signal_Source$'
require_line "$REPLAY_CONF" '^SignalSource\.filename='

if [[ ! -x "$BINARY" || ! -x "$RUN_TESTS" ]]; then
    echo "FULL_BUILD_NOT_AVAILABLE binary=$BINARY run_tests=$RUN_TESTS" >&2
    exit 2
fi

"$BINARY" --version >/dev/null
FILTER='DualPathPairManager.*:DualPathStatusFormatter.*:TunnelEndAssociation.*:TunnelTemporalIntegration.*'
"$RUN_TESTS" --gtest_filter="$FILTER"
echo "SOFTWARE_PREFLIGHT_PASS"

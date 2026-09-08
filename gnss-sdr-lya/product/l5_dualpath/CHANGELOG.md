# Changelog

## Unreleased

- Added a path-1 watchdog that forces reacquisition when its valid pseudorange repeatedly collapses onto path 0.
- Enabled continuous second-peak acquisition retries in the realtime B210 configurations, allowing recovery after the antenna moves back inside detection range.

## 1.0.0-code-complete - 2026-08-05

- Froze the v1 scope around already-separated GPS L5 dual peaks.
- Prevented path1 from falling back to the primary peak.
- Added configurable second-peak delay, prominence, power-ratio, and boundary gates.
- Added the C++ dual-path quality state machine with rolling median/MAD and successful reacquisition count.
- Added stable `DUALPATH_STATUS version=1` and optional low-rate C++ CSV.
- Added B210 10/20 Msps, file replay, and single-path negative-control configurations.
- Added build, runtime-check, packaging, and validation documentation.

Not yet claimed: formal replay validation, realtime B210 validation, release-candidate status, or sub-chip separation.

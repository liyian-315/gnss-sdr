# Tunnel DAS Software Completion And Hardware Handoff

> Date: 2026-08-10  
> Author: Codex  
> Branch: `product/tunnel-das-balance-v1`  
> Baseline: `0f20184eb58338b0cb52cf3522ea88350b10d067`

## Scope

This round closes software-only product engineering for the tunnel dual-end
coverage and power-balance tool. It does not change acquisition, tracking,
second-peak detection, PVT, or any research estimator. No B210, simulator, or
RF result is claimed.

## Root Cause And Decision

The dual-path report timer in `hybrid_observables_gs::general_work()` was
inside an `n_valid > 0` gate. When a report epoch contained no current PRN
observations, `report_dual_path_observables()` was not called. PairManager's
existing stale-age and empty-update logic therefore received no clock tick,
and TunnelEndAssociation received no updated pair state. A pre-outage
`RELIABLE` result could remain frozen outside the state manager.

Decision: every enabled product report period calls the product state path,
including `update({})`. Observation validity controls measurement contents;
it does not control time.

## Product Semantics

- A missing path first produces `DEGRADED`, then `LOST` under the configured
  confirmation/freshness limits.
- `DEGRADED` and `LOST` publish no formal END_A/END_B values. The frozen
  `TUNNEL_DAS_STATUS version=1` fields render these measurements as `N/A`.
- Reappearance after `LOST` clears the old statistical generation, increments
  `reacquisition_count` once, and starts at `CANDIDATE`.
- Physical END_A/END_B identity remains geometry-based. CN0 crossing does not
  swap identity; a true path0/path1 swap requires fresh identity confirmation.
- Midpoint or otherwise ambiguous geometry remains `identity=UNKNOWN`.

## Deterministic Software Evidence

The temporal integration harness injects the same observation objects consumed
by `DualPathPairManager`, then feeds its statuses to `TunnelEndAssociation`.
It uses report epochs, not IQ generation, and covers:

1. stable dual-end operation;
2. A/B CN0 crossing;
3. path0/path1 swap;
4. second-end loss (`DEGRADED` to `LOST`);
5. total empty epochs;
6. reacquisition through a fresh `CANDIDATE` generation;
7. midpoint ambiguity;
8. asymmetric fixed delays;
9. invalid site configuration;
10. position change after restart.

The pre-fix test result was 8/9 temporal tests: the degraded epoch was rendered
as `UNRESOLVED`. After the output-state and report-clock fixes, the standalone
Tunnel suites passed 22/22. The final CMake-built product filter passed 35/35.

## Configuration Contract

With `Tunnel.enable=true`, startup validates length, position, both fixed
delays, identity limits, and confirmation count. Invalid input prints
`TUNNEL_CONFIG_ERROR ...; Tunnel output disabled`. Valid input prints one
`TUNNEL_DAS_CONFIG` line containing length, position, both distances, both
fixed delays, expected delta, and PRN.

The B210 and file-replay configurations use the same dual-path and Tunnel
parameters. Both keep `Observables.dual_path_csv=false`; normal field operation
requires only the `gnss-sdr` binary and one configuration file.

All active properties must follow `[GNSS-SDR]`. An initial configuration draft
put the editable field block before that section, so the INI parser silently
ignored it and file replay fell back to `./example_capture.dat`. The section
now precedes the editable block, and `software_preflight.sh` rejects this layout
error.

## Build And Test Evidence

Build environment:

- OS / architecture: Ubuntu 24.04 under WSL, x86_64;
- CMake 3.28.3;
- GNU C/C++ 13.3.0, C++20;
- GNU Radio 3.10.9;
- UHD 4.6.0.0;
- build type: Release;
- `ENABLE_UNIT_TESTING=ON`.

Commands and results:

```bash
cmake -S . -B build-wsl-codex \
  -DENABLE_UNIT_TESTING=ON \
  -DENABLE_UNIT_TESTING_EXTRA=OFF \
  -DENABLE_SYSTEM_TESTING=OFF \
  -DENABLE_SYSTEM_TESTING_EXTRA=OFF
cmake --build build-wsl-codex --target run_tests -- -j$(nproc)
build-wsl-codex/tests/run_tests \
  --gtest_filter='DualPathPairManager.*:DualPathStatusFormatter.*:TunnelEndAssociation.*:TunnelTemporalIntegration.*'
cmake --build build-wsl-codex --target gnss-sdr -- -j$(nproc)
```

- full Release `gnss-sdr` build: PASS;
- CMake-built `run_tests`: 35 run, 35 passed, 0 failed, 0 skipped;
- `software_preflight.sh`: `SOFTWARE_PREFLIGHT_PASS`;
- valid file-replay construction smoke: PASS, exact `TUNNEL_DAS_CONFIG`
  printed and flowgraph ended normally;
- invalid `Tunnel.length_m=0` smoke: PASS, `TUNNEL_CONFIG_ERROR` printed,
  Tunnel output disabled, flowgraph ended normally;
- B210 / simulator: `B210_NOT_RUN` (hardware unavailable).

The replay smoke used a short zero-filled local file only to validate parsing
and flowgraph construction. It is not acquisition, tracking, or RF evidence.

## Hardware Handoff

Use `product/tunnel_das/FIELD_TEST_CHECKLIST.md`. The required next evidence is
a B210 run with both ends, END_B shutdown to `DEGRADED -> LOST`, and END_B
restart through `CANDIDATE -> RELIABLE`. Until that run, the highest permitted
status is `SOFTWARE_READY_FOR_HARDWARE_VALIDATION`.

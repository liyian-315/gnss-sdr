# GPS L5 Dual-Path Receiver v1 - Release Blocking Fix Round 1

Date: 2026-08-10  
Author: Codex (GPT-5)

## Scope and baseline

- Product branch: `product/l5-dualpath-receiver-v1`
- Product baseline: `6eedc51aa4f706190e7f589945fa89c7e13c470f`
- Independent review read from: `origin/review/l5-dualpath-receiver-v1`
- Review SHA: `50b1752f1adabb143c68d0a5ecc94655a4d485c2`
- No sub-chip estimator, MEDLL, EKF, array, third path, Python runtime, or path1 PVT work is included.

## B-1: stale path1 could remain RELIABLE

### Original problem

`DualPathPairManager` only advanced records present in the current observation map. A total path1 outage could therefore freeze the previous `RELIABLE` state, rolling window, and track age. The first observation after reacquisition could also reuse the old generation and immediately return to `RELIABLE`.

### Fix

- Added an explicit report clock and per-path last-valid receiver/report times.
- Added configurable `Observables.dual_path_second_path_freshness_limit_s` (5 s in the 1 Hz product configurations).
- A reliable pair now requires both paths to be valid, fresh, time-aligned, and to satisfy the current CN0, Doppler, delay, and stability gates.
- Records absent from an update receive a no-observation tick, so outage state continues to advance.
- Path1 outage progresses `RELIABLE -> DEGRADED -> LOST`; formal path1 values are `N/A` in `LOST`, while path0 remains usable.
- `LOST` clears the rolling delta/stability generation. Reacquisition increments the count once, starts at `CANDIDATE`, and must build a new reliable window.

### Tests and result

The pre-fix review sequence reproduced stale `RELIABLE`, six old window samples, and a 60 s stale track age. After the fix, `DualPathPairManager.TotalOutageMustNotRepublishStaleReliable` and `SecondPathOutageAndReacquisitionUseFreshGeneration` pass together with the existing manager regressions (10/10 manager tests).

Result: **B-1 CLOSED by unit-test evidence.**

## B-2: single-source negative control bypassed product logic

### Original problem

The previous negative-control configuration disabled the second product path, so it could not answer whether the enabled dual-path receiver invents a second source.

### Fix

- `l5_singlepath_negative_control.conf` now starts two L5 channels for one PRN, assigns path0/path1, enables second-peak acquisition, and uses the complete product state machine.
- `check_runtime.sh` statically rejects a negative-control configuration that bypasses either path or disables multipath acquisition.
- `check_status_log.sh --single-source-negative` rejects any emitted `CANDIDATE` or `RELIABLE` state.
- `run_file_replay_validation.sh` accepts the external IQ path, PRN, and output directory without placing raw data in Git or editing the source configuration.

### Actual file replay

NUC A-only PRN28, 20 Msps sc16, 30 s:

- runtime: 7.21 s
- primary valid ratio: 1.000000
- second valid ratio: 0.000000
- states: SEARCHING=2, NO_SECOND_SOURCE=11, CANDIDATE=0, RELIABLE=0
- overflow: 0; loss of lock: 1 (path1 search channel)
- formal second pseudorange/CN0/Doppler/delta: `N/A`

Result: **B-2 CLOSED by static configuration, startup, and real single-source replay evidence.**

## MAJOR-8: registered test target was not built/run

The NUC has no conda installation. The actual target environment used here is:

- host: `NUC11BTMi9`, x86_64 Ubuntu 22.04
- CMake 3.22.1
- GCC/G++ 11.4.0, C++17
- GNU Radio 3.10.1.1 (CMake reports 3.10.1)
- UHD `4.1.0.HEAD-0-g6bd0be9c` (package/CMake reports 4.1.0.5-3)

Commands:

```bash
cmake -S /home/bupt/lya/gnss-sdr/gnss-sdr-lya -B /home/bupt/lya/gnss-sdr/gnss-sdr-lya/build-conda -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=ON
cmake --build /home/bupt/lya/gnss-sdr/gnss-sdr-lya/build-conda --target gnss-sdr -- -j8
cmake --build /home/bupt/lya/gnss-sdr/gnss-sdr-lya/build-conda --target run_tests -- -j8
```

Registered `run_tests` execution:

- DualPathPairManager + formatter + AcquisitionPathSelector: 16/16 passed
- Observables block-factory regression: 4/4 passed
- Acquisition block-factory and PCPS regression: 9/9 passed
- tests built: complete registered `run_tests` executable
- release-relevant tests selected for execution: 29
- tests run: 29
- tests passed: 29
- tests failed: 0
- tests skipped: 0

The registered monolithic executable was built; the release-relevant suites above were executed rather than substituting a manual test-file compile.

## B-3: NUC package was not self-verifying

### Original problem

The prior bundle came from the wrong host class and its external checksum recorded a build-machine path. It lacked an independent clean-directory verifier and a precise dynamic-runtime declaration.

### Fix

- Packaging rejects WSL and non-x86_64 hosts and checks for UHD/GNU Radio metadata.
- The bundle records target, hostname, architecture, OS, kernel, compiler, CMake, GNU Radio, UHD, build time, Git SHA, and `ldd` output.
- The external `.sha256` contains only the archive basename and works with `sha256sum -c`.
- Package-local `SHA256SUMS` contains only relative in-package files.
- `verify_release.sh` copies the archive/checksum to a new temporary directory, verifies both checksum layers, executes `gnss-sdr --version`, statically checks every product configuration, verifies required documents/Git SHA, and rejects missing dynamic libraries.
- The package is assembled from an explicit allow-list; raw IQ, NPZ, build trees, editor settings, keys, and temporary logs are not copied.

### Result

On the target NUC, archive checksum verification and clean-directory `verify_release.sh` both returned `PASS`. Result: **B-3 CLOSED by target-host package evidence.**

## File-replay matrix

All rows used the same NUC product binary and the same product replay template.

| Case | Result | Evidence |
|---|---|---|
| Single-source A-only PRN28 | PASS negative control | path0 100%, path1 0%, RELIABLE=0 |
| PRN23 90 m, -6 dB, 30 s | FAIL / insufficient observables | both paths entered tracking; both lost at 22 s; no product status |
| PRN28 60 m, -6 dB, 30 s | FAIL / insufficient observables | both paths entered tracking; both lost at 21-22 s; no product status |
| PRN23 60 m, -6 dB, 30 s | FAIL / insufficient observables | both paths entered tracking; both lost at 22 s; no product status |
| PRN28 30 m, -6 dB, 30 s | expected unresolved | primary/second valid ratios 1.0, all 16 states SEARCHING, delta 0 m, RELIABLE=0 |
| 200-220 m stable dual source | NOT RUN | no replayable raw IQ exists on this NUC; images are not test input |
| 1000 m long dual source | NOT RUN | no replayable raw IQ exists on this NUC; images are not test input |

The negative control and honest near-distance failure are validated. A positive dual-source `RELIABLE` replay is not yet validated, so this round does not earn `OFFLINE_VALIDATED`.

## Realtime B210

`uhd_find_devices` did not discover a B210 during this round and the simulators were unavailable.

**REALTIME_B210_NOT_RUN**

## Final decision and remaining risk

The three review BLOCKING defects are fixed and their local/NUC test entrances are executable. Release validation remains blocked by:

1. no positive dual-source replay that reaches and sustains `RELIABLE` with this product binary;
2. no replayable 200-220 m or long-distance raw IQ on the NUC;
3. no 30-minute B210 single/dual-source, path1 off/on, overflow, and reacquisition run.

Current product level: **CODE_COMPLETE**.  
Not claimed: `OFFLINE_VALIDATED`, `REALTIME_VALIDATED`, or RC1.

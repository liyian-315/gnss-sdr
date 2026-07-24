# 10 Branch Cleanup Handoff, 2026-07-24

Author: Codex
Date: 2026-07-24

## What Changed

- `research/multipath-correlator-fit` is the active algorithm research branch after the v0.1 gate.
- `gnss-sdr-lya/build/` is a local CMake output directory and must not be tracked by Git.
- Runtime data should stay outside the source tree. On the NUC, use:
  - `~/lya/gnss_data/raw`
  - `~/lya/gnss_data/logs`
  - `~/lya/gnss_data/outputs`
  - `~/lya/gnss_data/analysis`

## Reason

Tracked build artifacts caused host-specific CMake cache pollution and made branch switches fragile. The source branch should contain source, configs, scripts, and documentation only; build trees and acquisition dumps belong to the test host.

## NUC Handoff

After pulling this branch on the NUC, verify:

```bash
cd ~/lya/gnss-sdr/gnss-sdr-lya
git status --short --branch
git branch --show-current
```

Expected branch:

```text
research/multipath-correlator-fit
```

If `build/src/main/gnss-sdr` is missing after the cleanup commit, rebuild with the NUC apt route:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=OFF
cmake --build build --target gnss-sdr -j16
```

-- Codex, 2026-07-24

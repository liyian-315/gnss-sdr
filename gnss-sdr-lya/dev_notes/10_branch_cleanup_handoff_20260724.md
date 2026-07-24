# 10 Branch Cleanup Handoff, 2026-07-24

Author: Codex
Date: 2026-07-24

## What Changed

- `research/multipath-correlator-fit` is the active algorithm research branch after the v0.1 gate.
- `gnss-sdr-lya/build/` is a local CMake output directory and must not be tracked by Git.
- Runtime data should stay outside the source tree. The frozen NUC data root is:

```text
~/lya/gnss_data/
```

## Reason

Tracked build artifacts caused host-specific CMake cache pollution and made branch switches fragile. The source branch should contain source, configs, scripts, and documentation only; build trees and acquisition dumps belong to the test host.

## Frozen Experiment Data Layout

Use this layout on the NUC and on future test hosts:

```text
~/lya/gnss_data/
  raw/       Raw captures from B210 or other receivers.
  logs/      Terminal logs, run logs, recorder logs, monitor CSV logs.
  outputs/   Built binaries copied for preservation, generated configs, PVT/observables outputs.
  analysis/  Plots, summaries, fitted-path results, notebooks, TSV/CSV reports.
  README.txt Host-local short note; optional, not tracked by Git.
```

Rules:

- Do not write new `.dat`, `.mat`, `.png`, `.log`, `.kml`, `.geojson`, or long-run observables into the source tree.
- Store raw captures under `raw/` and analysis products under `analysis/`.
- Keep source-controlled scripts and reusable configs in `gnss-sdr-lya/dev_notes/sim/`.
- If a test needs a temporary config, write it to `/tmp` or `~/lya/gnss_data/outputs/`.
- If a raw capture is worth preserving, use a descriptive tag with date, signal, PRN, sample rate, gain, and scenario.

Suggested naming:

```text
raw/YYYYMMDD_signal_prnXX_rate_gain_scenario.dat
logs/YYYYMMDD_signal_prnXX_scenario_run.log
analysis/YYYYMMDD_signal_prnXX_scenario_summary.tsv
analysis/YYYYMMDD_signal_prnXX_scenario_acq3d.png
```

Example:

```text
raw/20260724_l1ca_prn28_4m_g60_twoantenna_700m.dat
logs/20260724_l1ca_prn28_4m_g60_twoantenna_700m_run.log
analysis/20260724_l1ca_prn28_4m_g60_twoantenna_700m_summary.tsv
```

Decision:

The source repo is for reproducible code, configs, scripts, and docs. The NUC data root is for experiments. This keeps Git branch switches clean and makes large captures easier to preserve or delete intentionally.

-- Codex, 2026-07-24

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

# 11 Dense Tracking Correlator Export

Author: Codex
Date: 2026-07-24

## Goal

Export dense tracking-domain complex correlator taps for offline multipath / multi-source fitting. This is instrumentation only: it must not change tracking lock logic, observables, PVT, or the existing dual-path output unless explicitly enabled.

## Development Checklist

- [x] Step 1: Extend `Dll_Pll_Conf` with dense correlator configuration fields.
- [x] Step 2: Parse `start:step:stop` tap strings and convert chip offsets to sample offsets inside the tracking block.
- [x] Step 3: Add an independent dense multicorrelator, gated by decimation so non-dump epochs do not compute dense taps.
- [x] Step 4: Write dense binary dump using the existing tracking dump style, plus a JSON metadata sidecar.
- [x] Step 5: Add Python tools to inspect and plot dense correlation profiles.
- [x] Step 6: Validate first with offline File Source, then real-time if CPU headroom is acceptable.

## Step 1 Notes

Changed:

```text
src/algorithms/tracking/libs/dll_pll_conf.h
src/algorithms/tracking/libs/dll_pll_conf.cc
```

New config fields:

```ini
Tracking_1C.dense_correlator_dump=false
Tracking_1C.dense_correlator_dump_filename=./dense_correlator_dump.dat
Tracking_1C.dense_correlator_taps_chips=-1.5:0.1:1.5
Tracking_1C.dense_correlator_decimation=20
```

Current behavior:

- Defaults keep dense export disabled.
- `dense_correlator_decimation < 1` is clamped to `1` with a warning.
- Tap string is only stored at this stage; parsing and chip-to-sample conversion are deliberately deferred to Step 2.

Decision:

Use the existing tracking dump style for the main binary stream. JSON is reserved for metadata only.

-- Codex, 2026-07-24

## Config Generator Integration

Date: 2026-07-24
Author: Codex

Changed:

```text
dev_notes/sim/make_l1ca_dualpath_conf.py
dev_notes/sim/make_l5_dualpath_conf.py
```

Added shared command-line options to both generators:

```bash
--enable-dense-correlator
--dense-taps -1.5:0.1:1.5
--dense-decimation 20
--dense-dump-prefix ./gps_l1ca_dense_ch_
--dense-dump-prefix ./gps_l5_dense_ch_
```

Default behavior is unchanged: dense export remains disabled unless `--enable-dense-correlator` is explicitly provided.

Example L1:

```bash
python3 dev_notes/sim/make_l1ca_dualpath_conf.py --source file --input /path/to/l1.dat --rate 4000000 --prns 28 --single-path --enable-dense-correlator --dense-dump-prefix /tmp/dense_l1_ch_ --output /tmp/l1_dense.conf
```

Example L5:

```bash
python3 dev_notes/sim/make_l5_dualpath_conf.py --source file --input /path/to/l5.dat --rate 10000000 --prns 18 --single-path --track-pilot --enable-dense-correlator --dense-dump-prefix /tmp/dense_l5_ch_ --output /tmp/l5_dense.conf
```

If a custom tap spec starts with a negative value, pass it with `=` so `argparse` does not interpret it as an option:

```bash
--dense-taps=-2:0.2:2
```

Judgment:

This turns dense export from a hand-edited config capability into a repeatable experiment setup while preserving existing L1/L5 test configs by default.

-- Codex, 2026-07-24

## Step 6 Notes

Validation host:

```text
NUC11BTMi9
/home/bupt/lya/gnss-sdr
branch: research/multipath-correlator-fit
commit: a69a4910f before validation doc update
```

Input data:

```text
/home/bupt/SignalSim/IFdataGen/GPS_BDS_GAL_L1CA_L1C_B1C_B1I_E1.bin
format: IQ8 / ibyte
sampling_frequency: 18479000 sps
GNSS-SDR internal_fs_sps: 12000000
signal used for validation: GPS L1 C/A
```

Temporary config:

```text
/tmp/gnss_dense_step6/l1_dense_step6.conf
```

The config was derived from:

```text
/home/bupt/SignalSim/IFdataGen/gnsssdr-configs/GPS_BDS_GAL_L1CA_L1C_B1C_B1I_E1.conf
```

Dense settings added:

```ini
Tracking_1C.dense_correlator_dump=true
Tracking_1C.dense_correlator_dump_filename=/tmp/gnss_dense_step6/l1_dense_ch_
Tracking_1C.dense_correlator_taps_chips=-1.5:0.1:1.5
Tracking_1C.dense_correlator_decimation=20
```

Run command:

```bash
cd ~/lya/gnss-sdr/gnss-sdr-lya
timeout 90s ./build/src/main/gnss-sdr --config_file=/tmp/gnss_dense_step6/l1_dense_step6.conf 2>&1 | tee /tmp/gnss_dense_step6/run.log
```

Generated files:

```text
/tmp/gnss_dense_step6/l1_dense_ch_0.dat       175 KB
/tmp/gnss_dense_step6/l1_dense_ch_0.dat.json  1.6 KB
```

Reader validation:

```bash
python3 dev_notes/sim/read_dense_correlator_dump.py /tmp/gnss_dense_step6/l1_dense_ch_0.dat.json --max 12 --epoch -1 --plot-out /tmp/gnss_dense_step6/dense_epoch_last.png
python3 dev_notes/sim/read_dense_correlator_dump.py /tmp/gnss_dense_step6/l1_dense_ch_0.dat --max 3
```

Observed result:

```text
records: 550
record_size: 324 bytes
tap_count: 31
signal: GPS 1C
channel: 0
decimation: 20
fs: 12.000 MHz
tap span: -1.500 .. 1.500 chips
plot generated: /tmp/gnss_dense_step6/dense_epoch_last.png, 104 KB
```

Tracking note:

The SignalSim file acquired and tracked GPS PRN 11, then later reported one loss of lock. This is acceptable for Step 6 because the goal was dump-format closure, not tracking performance evaluation. The dense writer produced records, metadata matched the reader dtype, both `.json` and `.dat` reader entry points worked, and plotting succeeded.

Judgment:

Dense export is now validated end-to-end for offline File Source on NUC: C++ dense writer -> binary + JSON -> Python reader -> PNG plot.

-- Codex, 2026-07-24

## Step 5 Notes

Changed:

```text
dev_notes/sim/read_dense_correlator_dump.py
```

Implemented:

- Reads either `<dense_dump>.dat` or `<dense_dump>.dat.json`.
- Validates `record_size_bytes` against the NumPy dtype.
- Prints a compact table with epoch, sample counter, PRN, CN0, Doppler, strongest tap, and peak/median ratio.
- Plots a selected epoch as two panels:
  - `|corr|` versus tap offset in chips.
  - complex phase versus tap offset in chips.

Example:

```bash
python3 dev_notes/sim/read_dense_correlator_dump.py ./dense_trk_channel_0.dat.json --max 10
python3 dev_notes/sim/read_dense_correlator_dump.py ./dense_trk_channel_0.dat --epoch -1 --plot-out dense_epoch_last.png
```

Judgment:

This is intentionally a reader/inspection tool, not a fitter. The first milestone after dump generation is verifying that the dense complex profiles are readable, phase-bearing, and stable enough to justify MEDLL-style or sparse model fitting.

-- Codex, 2026-07-24

## Step 4 Notes

Changed:

```text
src/algorithms/tracking/gnuradio_blocks/dll_pll_veml_tracking.h
src/algorithms/tracking/gnuradio_blocks/dll_pll_veml_tracking.cc
```

Implemented:

- Opens a per-channel dense dump file when `dense_correlator_dump=true`.
- Writes a JSON sidecar next to the binary file: `<dense_dump>.dat.json`.
- Writes one binary record only for decimation-selected dense epochs.
- Keeps the main binary stream in the existing `ofstream.write()` style.
- Adds a separate `d_dense_correlator_initialized` flag so the dense multicorrelator is freed even if dumping is disabled later because of path/open failures.

Binary record layout:

```text
uint64  sample_counter
uint64  epoch_counter
uint32  channel
uint32  prn
uint64  tow_ms
int32   wn
float32 rem_carr_phase_rad
float32 acc_carrier_phase_rad
float32 carrier_doppler_hz
float32 carrier_phase_step_rad
float32 carrier_phase_rate_step_rad
float32 rem_code_phase_chips
float32 code_phase_step_chips
float32 code_phase_rate_step_chips
float32 cn0_snv_db_hz
float32 carrier_lock_test
complex64[tap_count] tap_iq
```

Metadata fields include:

- `tap_count`
- `taps_chips`
- `decimation_epochs`
- `sampling_frequency_hz`
- `code_samples_per_chip`
- `record_size_bytes`
- field names and primitive types

Judgment:

The dense binary file is not converted to `.mat` in this step. A dynamic number of taps fits better with a small JSON-described binary reader, which will be added in Step 5.

-- Codex, 2026-07-24

## Step 2 Notes

Changed:

```text
src/algorithms/tracking/gnuradio_blocks/dll_pll_veml_tracking.h
src/algorithms/tracking/gnuradio_blocks/dll_pll_veml_tracking.cc
```

Implemented:

- Parses `Tracking_XX.dense_correlator_taps_chips` as `start:step:stop`.
- Rejects malformed specs, zero step, wrong step direction, and more than 257 taps.
- Converts tap offsets from chips to samples using `d_code_samples_per_chip`.
- Stores both forms:
  - `d_dense_code_shift_chips`: chip units for metadata / human inspection.
  - `d_dense_code_shift_samples`: sample units for the multicorrelator.
- If parsing fails while dense dump is enabled, dense dump is disabled with a warning rather than affecting normal tracking.

Judgment:

The existing `d_local_code_shift_chips` name is misleading because it stores sample offsets. Dense export therefore uses an explicit `d_dense_code_shift_samples` name for the internal values. This directly addresses the tap-unit trap noted in the handoff.

-- Codex, 2026-07-24

## Step 3 Notes

Changed:

```text
src/algorithms/tracking/gnuradio_blocks/dll_pll_veml_tracking.h
src/algorithms/tracking/gnuradio_blocks/dll_pll_veml_tracking.cc
```

Implemented:

- Added an independent `d_dense_multicorrelator_cpu`.
- Added `d_dense_correlator_outs` for dense complex correlator outputs.
- Initializes the dense multicorrelator only when `dense_correlator_dump=true` and the tap config parsed successfully.
- Sets dense local code and sample-offset taps in `start_tracking()`, after the PRN-specific tracking code is generated.
- Gates dense correlation computation in `do_correlation_step()` by `dense_correlator_decimation`.

Important judgment:

The decimation gate is placed before `Carrier_wipeoff_multicorrelator_resampler()`. Non-selected epochs therefore do not compute dense taps at all, which keeps the added CPU cost approximately `1 / dense_correlator_decimation` of full dense tracking.

Current limitation:

This step computes dense taps but does not persist them. File output, metadata sidecar, and carrier phase fields are Step 4.

-- Codex, 2026-07-24

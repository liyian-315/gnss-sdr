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
- [x] Step 6: Validate BYTE FORMAT with offline File Source (Step 6 notes below).
- [ ] **Phase A: validate the export PHYSICALLY on one clean cabled path (tap0==Prompt + smooth reference R(tau)). Runbook below. ← current step.**

> ⚠️ Step 6 only proved byte-format closure on a lossy multi-sat file. The
> substantive criteria — tap0 ≈ Prompt, and a smooth single-path R(tau) — are
> Phase A and are still open. Do not treat "dump produces bytes" as "dump is
> physically correct".

## Phase A Runbook — physical validation on one clean cabled path

Author: Claude (Opus 4.8). Date: 2026-07-24.

Scenario reminder (see README §0.1): our target is **indoor DAS multi-source**,
where each path is a meaningful re-radiated source, not a reflection to suppress.
Phase A does not test separation yet — it validates the instrument and calibrates
the reference correlation function `R(tau)` that the later multi-source fit needs.

Hardware (Phase A): ONE simulator (NavSimUI), cabled direct to the B210 through
an attenuator, NO combiner. NavSimUI assigns one 载体 per connected simulator, so
two paths (Phase B) require two simulator boxes combined through the 2-way
splitter used in reverse as a combiner.

Simulator settings to confirm before recording:

```text
调制方式 = 扩频码 (spread code, NOT single carrier)
轨迹 = static (constant position; keeps R(tau) undistorted)
电离层 / 对流层 = off
功率模式 = 等同功率, set high CN0 (~48-52 dB-Hz)
one GPS PRN only
```

Artifacts (all committed):

```text
dev_notes/sim/l1ca_offline_dense.conf     File_Source + dense dump + main dump, extend=1, decim=1
dev_notes/sim/check_dense_vs_prompt.py    criterion (3) tap0==Prompt + (4) averaged reference R(tau)
dev_notes/sim/read_dense_correlator_dump.py   single-epoch profile / smooth-peak sanity
dev_notes/sim/record_b210.py              raw IQ recorder (gr_complex)
```

Pipeline:

```bash
# 1) record raw (conda env gnsssdr); set gain so the capture is NOT clipping
python3 dev_notes/sim/record_b210.py --secs 90 \
  --freq 1575420000 --rate 4000000 --bw 4000000 --gain 40 --ant RX2 \
  -o /tmp/l1_phaseA.dat
python3 dev_notes/sim/l5_capstats.py /tmp/l1_phaseA.dat   # confirm no ADC clipping

# 2) set Channel0.satellite to the transmitted PRN in the conf, then run offline
./build-conda/src/main/gnss-sdr --config_file=dev_notes/sim/l1ca_offline_dense.conf

# 3) analyze
python3 dev_notes/sim/read_dense_correlator_dump.py ./l1_phaseA_dense_ch_0.dat.json \
  --max 12 --epoch -1 --plot-out l1_phaseA_epoch_last.png
python3 dev_notes/sim/check_dense_vs_prompt.py \
  --dense ./l1_phaseA_dense_ch_0.dat.json --trk ./l1_phaseA_trk_ch_0.dat \
  --ref-out l1_phaseA_reference_Rtau.png
```

Success criteria:

```text
(3) |tap0|/|Prompt| median ~= 1.0 and phase(tap0)-phase(Prompt) ~= 0  -> PASS line
(4) coherent |R(tau)| peaks at 0 chip, symmetric (+/- asymmetry small),
    smooth single main lobe -> reference template saved as CSV
```

Design choices baked into the conf (do not "fix" without reason):

- `extend_correlation_symbols=1`: main-dump Prompt is `d_Prompt` (single 1 ms
  period), which matches dense tap0 1:1. With N>1 the Prompt would carry a 1/N
  scaling relative to a single-period dense tap and criterion (3) would look off.
- `dense_correlator_decimation=1`: offline, dump every epoch for maximum
  averaging of the reference `R(tau)`.
- `record --rate` must equal `GNSS-SDR.internal_fs_sps`, and stay the SAME for
  the same-band Phase B, or the reference `R(tau)` is not comparable.

-- Claude (Opus 4.8), 2026-07-24

## Phase A Result - L1/L5 PRN28 Clean Single-Path Baseline

Date: 2026-07-26
Author: Codex

User framing accepted:

Phase A is not only an instrument/software sanity check. It is also the baseline
for understanding what a clean single-path peak looks like. Later two-source
captures can produce a wider, shifted, shouldered, or otherwise distorted peak.
The clean `R(tau)` from Phase A is therefore the reference "single peak
fingerprint" used to decide whether a later peak shape is still a normal clean
signal or a multi-source/multipath deformation.

NUC / B210 test setup:

```text
Host: bupt@192.168.114.204
Repo: /home/bupt/lya/gnss-sdr/gnss-sdr-lya
Branch: research/multipath-correlator-fit
Commit: d4f2e7d feat: Phase A dense-correlator validation kit + indoor DAS scenario framing
B210 serial: 31502C6
Temporary UHD fix: export UHD_IMAGES_DIR=/usr/local/share/uhd/images
Connection: one simulator path cabled directly to RX2
PRN: GPS 28
Simulator output power: L1=-60, L5=-50
```

Important NUC note:

The system `uhd_find_devices` initially reported missing `usrp_b200_fw.hex`.
The image files already existed under `/usr/local/share/uhd/images`; exporting
`UHD_IMAGES_DIR=/usr/local/share/uhd/images` made the B210 visible. This is an
environment issue, not a hardware discovery failure.

Artifacts are intentionally outside the source tree:

```text
/home/bupt/lya/gnss_data/phaseA_l1_prn28_20260726/
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726/
```

L1 Phase A command flow:

```bash
python3 dev_notes/sim/record_b210.py --secs 30 --freq 1575420000 --rate 4000000 --bw 4000000 --gain 40 --ant RX2 --device-args serial=31502C6 -o /home/bupt/lya/gnss_data/phaseA_l1_prn28_20260726/l1_phaseA_prn28_g40_30s.dat
./build/src/main/gnss-sdr --config_file=/tmp/phaseA_l1_prn28_20260726/l1ca_phaseA_prn28_g40_30s.conf
python3 dev_notes/sim/check_dense_vs_prompt.py --dense /home/bupt/lya/gnss_data/phaseA_l1_prn28_20260726/l1_phaseA_dense_ch_0.dat.json --trk /home/bupt/lya/gnss_data/phaseA_l1_prn28_20260726/l1_phaseA_trk_ch_0.dat --ref-out /home/bupt/lya/gnss_data/phaseA_l1_prn28_20260726/l1_phaseA_reference_Rtau.png
```

L1 observations:

```text
Capture: 30 s, 4 Msps, gain 40, no overflow seen in recorder output.
IQ check: rms=0.0005109, p99=0.001079, p999=0.002395, max=0.006803, near_clip_pct=0.0.
Tracking: GPS L1 C/A PRN28 entered tracking at 1 s; no loss-of-lock in the 30 s offline run.
Dense records: 29779, tap_count=31, tap span=-1.5..+1.5 chips, decimation=1.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000-0.000j, asymmetry=0.0116.
Reference files: l1_phaseA_reference_Rtau.png and l1_phaseA_reference_Rtau.png.csv.
```

L5I Phase A command flow:

```bash
python3 dev_notes/sim/record_b210.py --secs 30 --freq 1176450000 --rate 10000000 --bw 10000000 --gain 40 --ant RX2 --device-args serial=31502C6 -o /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726/l5_phaseA_prn28_g40_30s.dat
python3 dev_notes/sim/make_l5_dualpath_conf.py --source file --input /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726/l5_phaseA_prn28_g40_30s.dat --output /tmp/phaseA_l5_prn28_20260726_l5i_g40_30s.conf --prns 28 --rate 10000000 --scenario cable --channels-in-acq 1 --enable-dense-correlator --dense-taps=-1.5:0.1:1.5 --dense-decimation 1 --dense-dump-prefix /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726/l5_phaseA_dense_ch_
./build/src/main/gnss-sdr --config_file=/tmp/phaseA_l5_prn28_20260726_l5i_g40_30s.conf
python3 dev_notes/sim/check_dense_vs_prompt.py --dense /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726/l5_phaseA_dense_ch_0.dat.json --trk /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726/l5_phaseA_trk_ch_0.dat --cn0-min 35 --lock-min 0.6 --skip-epochs 200 --ref-out /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726/l5_phaseA_reference_Rtau.png
```

L5I observations:

```text
Capture: 30 s, 10 Msps, gain 40, no overflow seen in recorder output.
IQ check: rms=0.0007810, p99=0.001641, p999=0.002017, max=0.003439, near_clip_pct=0.0.
Tracking: GPS L5I PRN28 entered tracking at 1 s; secondary code locked at 4 s; one loss-of-lock at 9 s; reacquired and produced valid observables from 20 s onward.
Observable examples: CN0 about 52.5..53.6 dB-Hz, doppler about -760 Hz.
Dense records: 29666, tap_count=31, tap span=-1.5..+1.5 chips, decimation=1.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000-0.000j, asymmetry=0.0428.
Reference files: l5_phaseA_reference_Rtau.png and l5_phaseA_reference_Rtau.png.csv.
```

Judgment:

The dense export implementation is physically aligned with the existing Prompt
tracking dump for both L1 C/A and L5I on this clean cabled PRN28 test. L1 is the
cleaner first reference: it locked without loss and has lower averaged
correlation asymmetry. L5I is also usable as a reference, but the one early
loss-of-lock and larger asymmetry should be kept in mind when comparing later
two-source L5 experiments. Do not interpret Phase A as path separation success;
it only establishes the clean single-path baseline and validates that dense
complex taps preserve the same Prompt phase/amplitude as the original tracker.

-- Codex, 2026-07-26

## Phase A Repeat Capture - Same Power, Run 2

Date: 2026-07-26
Author: Codex

Reason:

One capture is not enough to define a clean peak feature. For each simulator
output power and RF condition, collect repeated captures so the clean
single-path fingerprint can be described by stable statistics, not one lucky
plot. At minimum, compare peak position, `tap0` alignment, coherent `R(tau)`
asymmetry, main-lobe width, and run-to-run variation.

Run 2 artifacts:

```text
/home/bupt/lya/gnss_data/phaseA_l1_prn28_20260726_run2/
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_run2/
```

L1 PRN28 run 2:

```text
Capture: 30 s, 4 Msps, gain 40, RX2, no overflow seen.
IQ check: rms=0.0005164, p99=0.001082, p999=0.002588, max=0.007406, near_clip_pct=0.0.
Tracking: entered tracking at 1 s; no loss-of-lock; NAV subframe seen; CN0 about 51 dB-Hz.
Dense records: 29770, tap_count=31, tap span=-1.5..+1.5 chips, decimation=1.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000+0.000j, asymmetry=0.0125.
Reference files: l1_phaseA_reference_Rtau.png and l1_phaseA_reference_Rtau.png.csv.
```

L5I PRN28 run 2:

```text
Capture: 30 s, 10 Msps, gain 40, RX2, no overflow seen.
IQ check: rms=0.0007804, p99=0.001641, p999=0.002008, max=0.003741, near_clip_pct=0.0.
Tracking: entered tracking at 1 s; loss-of-lock at 9 s and near 30 s; dense locked epochs still sufficient for shape validation.
Dense records: 29499, tap_count=31, tap span=-1.5..+1.5 chips, decimation=1.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000-0.000j, asymmetry=0.0201.
Reference files: l5_phaseA_reference_Rtau.png and l5_phaseA_reference_Rtau.png.csv.
```

Run-to-run judgment:

```text
L1 asymmetry: run1=0.0116, run2=0.0125. This is stable and currently the best clean-peak reference.
L5I asymmetry: run1=0.0428, run2=0.0201. Dense alignment is stable, but tracking stability and shape asymmetry vary more than L1.
```

Next measurement need:

For each power point, repeat at least 3 times before treating any feature as a
baseline. The next script should aggregate multiple `*_reference_Rtau*.csv`
files and report mean/std of the clean peak features.

-- Codex, 2026-07-26

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

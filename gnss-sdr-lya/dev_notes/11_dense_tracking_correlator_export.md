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
captures can produce a wider, shifted, or shouldered peak because two meaningful
DAS sources are superposed.
The clean `R(tau)` from Phase A is therefore the reference "single peak
fingerprint" used to decide whether a later peak shape is still a normal clean
single-source observation or contains an additional source. The goal is not to
"repair a bad signal"; it is to detect and estimate the additional meaningful
source(s).

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

## Phase A Repeat Capture - Run 3, L5 Power Raised

Date: 2026-07-26
Author: Codex

Changed RF condition:

```text
L1 simulator output power: unchanged at -60
L5 simulator output power: raised from -50 to -45
Receiver gain: unchanged at 40 dB
PRN: GPS 28
Connection: one cabled path to B210 RX2
```

Run 3 artifacts:

```text
/home/bupt/lya/gnss_data/phaseA_l1_prn28_20260726_run3/
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_run3_pwr45/
```

L1 PRN28 run 3:

```text
Capture: 30 s, 4 Msps, gain 40, RX2, no overflow seen.
IQ check: rms=0.0004994, p99=0.001075, p999=0.001473, max=0.004230, near_clip_pct=0.0.
Tracking: entered tracking at 1 s; no loss-of-lock; NAV subframe seen; CN0 about 51 dB-Hz.
Dense records: 29774, tap_count=31, tap span=-1.5..+1.5 chips, decimation=1.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000-0.000j, asymmetry=0.0117.
Reference files: l1_phaseA_reference_Rtau.png and l1_phaseA_reference_Rtau.png.csv.
```

L5I PRN28 run 3, L5 output power -45:

```text
Capture: 30 s, 10 Msps, gain 40, RX2, no overflow seen.
IQ check: rms=0.001024, p99=0.002014, p999=0.002403, max=0.004071, near_clip_pct=0.0.
Tracking: entered tracking at 1 s; one loss-of-lock at 22 s; reacquired and secondary code locked at 25 s.
Observables: no valid DUALPATH_OBS was printed in this 30 s offline run.
Dense records: 29669, tap_count=31, tap span=-1.5..+1.5 chips, decimation=1.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000+0.000j, asymmetry=0.0293.
Reference files: l5_phaseA_reference_Rtau.png and l5_phaseA_reference_Rtau.png.csv.
```

Run-to-run judgment:

```text
L1 asymmetry so far: run1=0.0116, run2=0.0125, run3=0.0117.
L1 is very stable as a clean single-peak baseline.

L5I asymmetry so far:
  - power -50: run1=0.0428, run2=0.0201
  - power -45: run3=0.0293
Raising L5 power increased captured IQ RMS from about 0.00078 to 0.00102, with no clipping.
Dense tap alignment stayed correct, but L5I tracking/observable stability did not become fully clean.
```

Judgment:

For Phase A, the dense clean-peak shape is usable for L5I even when observables
are intermittent, because the dense profile is filtered over locked epochs and
`tap0` remains exactly aligned with Prompt. However, do not mix the two success
questions:

```text
Question 1: Is dense export physically correct and is the clean peak measurable? yes.
Question 2: Does L5I produce continuous pseudorange/CN0 output under this config? not yet.
```

-- Codex, 2026-07-26

## Phase A Repeat Capture - Run 4, L5 Power Still -45

Date: 2026-07-26
Author: Codex

Condition:

```text
L1 simulator output power: unchanged at -60
L5 simulator output power: unchanged at -45
Receiver gain: unchanged at 40 dB
PRN: GPS 28
Connection: one cabled path to B210 RX2
```

Run 4 artifacts:

```text
/home/bupt/lya/gnss_data/phaseA_l1_prn28_20260726_run4/
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_run4_pwr45/
```

L1 PRN28 run 4:

```text
Capture: 30 s, 4 Msps, gain 40, RX2, no overflow seen.
IQ check: rms=0.0005186, p99=0.001084, p999=0.002618, max=0.007528, near_clip_pct=0.0.
Tracking: entered tracking at 1 s; no loss-of-lock; NAV subframe seen; CN0 about 51 dB-Hz.
Dense records: 29767, tap_count=31, tap span=-1.5..+1.5 chips, decimation=1.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000-0.000j, asymmetry=0.0130.
Reference files: l1_phaseA_reference_Rtau.png and l1_phaseA_reference_Rtau.png.csv.
```

L5I PRN28 run 4, L5 output power -45:

```text
Capture: 30 s, 10 Msps, gain 40, RX2, no overflow seen.
IQ check: rms=0.001024, p99=0.002008, p999=0.002377, max=0.003305, near_clip_pct=0.0.
Tracking: entered tracking at 1 s; secondary code locked at 4 s; no loss-of-lock in this offline run.
Observables: valid DUALPATH_OBS from 16 s to 30 s, CN0 about 57.9..58.7 dB-Hz.
Telemetry: GPS L5 CNAV ephemeris received at 27 s.
Dense records: 29858, tap_count=31, tap span=-1.5..+1.5 chips, decimation=1.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000+0.000j, asymmetry=0.0428.
Reference files: l5_phaseA_reference_Rtau.png and l5_phaseA_reference_Rtau.png.csv.
```

Run-to-run judgment:

```text
L1 asymmetry so far: run1=0.0116, run2=0.0125, run3=0.0117, run4=0.0130.
L1 remains very stable as a clean single-peak baseline.

L5I asymmetry so far:
  - power -50: run1=0.0428, run2=0.0201
  - power -45: run3=0.0293, run4=0.0428
L5 -45 input RMS is stable around 0.001024 with no clipping.
L5 -45 tracking/observable behavior is not deterministic over one 30 s capture:
  run3 had one loss-of-lock and no valid DUALPATH_OBS;
  run4 had no loss-of-lock, valid DUALPATH_OBS, and CNAV ephemeris.
```

Judgment:

For L5I at this power, a single 30 s capture is not enough to classify tracking
stability. Treat the dense clean-peak reference as valid only after filtering
locked epochs, and treat observables/CNAV continuity as a separate repeatability
metric. For later Phase B, this means we should preserve both:

```text
shape metrics from dense R(tau)
tracking/telemetry metrics from run logs
```

-- Codex, 2026-07-26

## Phase A Design Correction - L5 Must Be Recollected at Wider Bandwidth

Date: 2026-07-26
Author: Codex

Claude's critique is accepted with one wording correction to keep the DAS
multi-source framing consistent:

```text
Additional-source detection rule:
  deviation from clean single-source R(tau) => additional meaningful source(s)

Avoid:
  language that implies the second source should be suppressed or removed.
```

The clean `R(tau)` fingerprint is stronger than a visual comparison template.
It is the kernel of the later two-source model:

```text
y(tau) = A0 * R(tau - tau0) + A1 * R(tau - tau1) * exp(j*phi)
```

Therefore Phase A must preserve the full per-tap complex reference and
statistics, not only scalar summaries such as peak position or asymmetry. The
existing `check_dense_vs_prompt.py` output CSV is the right artifact to keep:

```text
tap_chips,coherent_re,coherent_im,mag_mean,mag_std
```

Important correction to prior L5 Phase A runs:

```text
The existing L5 Phase A captures used 10 Msps / 10 MHz bandwidth.
GPS L5 code rate is 10.23 Mcps, so 10 Msps is <1 sample/chip and does not
capture the L5 main-lobe shape needed for high-resolution separation.
Those runs are useful only as "10 Msps bandwidth-limited L5 references"; they
must not be treated as the final L5 clean fingerprint.
```

Updated Phase A acquisition design:

```text
L5: recollect at >=20 Msps, preferably 20-25 Msps if the B210 host can do it
without overflow. Use sc16/ishort recording to keep disk bandwidth manageable.
L1: 4 Msps is acceptable for C/A; 8 Msps is optional but not the bottleneck.
B1I: later use about 8-10 Msps at 1561.098 MHz.
```

Power/CN0 sweep design:

```text
Target CN0 grid: 50, 45, 40, 35, 30 dB-Hz.
Tune simulator output power by measured Observables.stdout CN0, not by assuming
a fixed dBm-to-CN0 mapping.
Capture length: 20-30 s per run.
Repeats: at least 3 per condition; use 5 for the key same-power condition.
```

Features to extract per condition:

```text
tap0==Prompt verdict
peak position
main-lobe width at half maximum
coherent R(tau) asymmetry
per-tap magnitude std envelope
run-to-run std envelope
tracking/telemetry continuity from logs
```

Judgment:

The current L1 Phase A set is still valid as a clean single-source baseline.
The current L5 set should be kept for traceability but relabeled as
bandwidth-limited. The next real Phase A work is to preflight whether this NUC
can record L5 at 20 Msps sc16 without overflow, then recollect L5 at the CN0
grid above.

-- Codex, 2026-07-26

## Phase A L5 20Msps Preflight and First Wideband Capture

Date: 2026-07-26
Author: Codex

Condition:

```text
Signal: GPS L5I PRN28
Simulator L5 output power: -60
B210: RX2, serial=31502C6
Receiver gain: 40 dB
Target sample rate: 20 Msps
Sample type: ishort/sc16
```

Preflight result:

```text
5 s via dev_notes/sim/record_b210.py:
  output: /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr60_20m_preflight/
  overflow: 0
  file size: 382 MB
  IQ stats: rms=32.14 counts, p99=71.18, p999=102.45, max=172.33, near_clip_pct=0.0
  GNSS-SDR File_Source: L5I tracking started, secondary code locked, dense dump generated
  tap0 vs Prompt: PASS

5 s via uhd_rx_cfile:
  output: /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr60_20m_preflight_uhd/
  command used uhd_rx_cfile -s -N 100000000
  overflow: 0
  file size: 382 MB
  IQ stats: rms=31.49 counts, p99=67.54, p999=82.15, max=147.51, near_clip_pct=0.0
  GNSS-SDR File_Source: L5I tracking started, secondary code locked, dense dump generated
  tap0 vs Prompt: PASS
```

Overflow diagnosis for 30 s 20Msps sc16:

```text
30 s via record_b210.py to NVMe:
  output: /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr60_20m_run1/
  overflow count: 6
  judgment: keep for traceability only; not a clean baseline sample

30 s via uhd_rx_cfile to NVMe:
  output: /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr60_20m_run1_uhd/
  overflow count: 1
  judgment: better than Python recorder but still not strict Phase A quality

30 s via uhd_rx_cfile to /dev/null:
  overflow count: 0
  judgment: USB/B210 streaming path can sustain 20 Msps; the remaining overflow is
            caused by real-time file write jitter.
```

Working capture method:

```bash
uhd_rx_cfile -a serial=31502C6 -f 1176450000 -r 20000000 -g 40 -A RX2 -s --stream-args num_recv_frames=1024 -N 600000000 /dev/shm/l5_phaseA_prn28_pwr60_20m_g40_30s_shm_ishort.dat
mv /dev/shm/l5_phaseA_prn28_pwr60_20m_g40_30s_shm_ishort.dat /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr60_20m_run1_shm/l5_phaseA_prn28_pwr60_20m_g40_30s_shm_ishort.dat
```

The `/dev/shm` method avoids real-time NVMe write jitter. This NUC has a 16 GB
`/dev/shm`, enough for one 30 s 20Msps sc16 capture (~2.3 GB).

First clean 20Msps L5 capture:

```text
Output: /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr60_20m_run1_shm/
Capture: 30 s, 20 Msps, ishort/sc16, /dev/shm first, then moved to gnss_data
Overflow: 0
File size: 2.3 GB
IQ stats: rms=31.37 counts, p99=66.94, p999=81.88, max=129.87, near_clip_pct=0.0
```

GNSS-SDR offline result for the clean 20Msps capture:

```text
Tracking: L5I entered tracking at 1 s; secondary code locked at 4, 14, and 20 s.
Loss-of-lock: at 9 s, 17 s, and 25 s.
Observables/CNAV: no continuous DUALPATH_OBS/CNAV in this -60 power run.
Dense records: 29373, tap_count=31, tap span=-1.5..+1.5 chips, fs=20 MHz.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000-0.000j, asymmetry=0.0393.
Reference files: l5_phaseA_reference_Rtau.png and l5_phaseA_reference_Rtau.png.csv.
```

Judgment:

The wideband L5 capture path is now proven viable on this NUC if the sample file
is first written to `/dev/shm`. At L5 output power -60, the dense clean-peak
fingerprint can be measured, but tracking/observable continuity is poor. This
condition belongs in the low-power/CN0 end of the Phase A sweep; it should not
be used alone as the nominal high-CN0 L5 reference.

-- Codex, 2026-07-26

## Phase A L5 20Msps Capture - Power -55

Date: 2026-07-26
Author: Codex

Condition:

```text
Signal: GPS L5I PRN28
Simulator L5 output power: -55
B210: RX2, serial=31502C6
Receiver gain: 40 dB
Sample rate: 20 Msps
Sample type: ishort/sc16
Capture method: uhd_rx_cfile to /dev/shm, then move to gnss_data
```

Capture artifact:

```text
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr55_20m_run1_shm/
```

Capture command:

```bash
uhd_rx_cfile -a serial=31502C6 -f 1176450000 -r 20000000 -g 40 -A RX2 -s --stream-args num_recv_frames=1024 -N 600000000 /dev/shm/l5_phaseA_prn28_pwr55_20m_g40_30s_shm_ishort.dat
mv /dev/shm/l5_phaseA_prn28_pwr55_20m_g40_30s_shm_ishort.dat /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr55_20m_run1_shm/l5_phaseA_prn28_pwr55_20m_g40_30s_shm_ishort.dat
```

Capture observations:

```text
Capture: 30 s, 20 Msps, ishort/sc16, 0 overflow.
File size: 2.3 GB.
IQ stats: rms=32.29 counts, p99=68.25, p999=86.31, max=150.94, near_clip_pct=0.0.
Compared with L5 -60 wideband run: rms rose only slightly (31.37 -> 32.29 counts).
```

GNSS-SDR offline result:

```text
Tracking: L5I entered tracking at 1 s.
Secondary code locked: at 4 s, 21 s, and 28 s.
Loss-of-lock: at 9 s, 17 s, and 25 s.
Observables/CNAV: no continuous DUALPATH_OBS/CNAV in this -55 power run.
Dense records: 29456, tap_count=31, tap span=-1.5..+1.5 chips, fs=20 MHz.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000-0.000j, asymmetry=0.0908.
Reference files: l5_phaseA_reference_Rtau.png and l5_phaseA_reference_Rtau.png.csv.
```

Judgment:

Dense export remains physically aligned (`tap0==Prompt` PASS), but the -55
wideband sample is not a clean high-quality L5 reference: tracking still cycles
through loss/reacquisition, and the coherent `R(tau)` asymmetry is worse than the
-60 wideband run (0.0908 vs 0.0393). This suggests the current L5I 20Msps
tracking/filtering setup is still not providing a stable enough locked segment
at this condition. Treat this capture as a low-power/unstable-tracking data
point, not as the nominal L5 fingerprint.

-- Codex, 2026-07-26

## Phase A L5 20Msps Capture - Power -50

Date: 2026-07-26
Author: Codex

Condition:

```text
Signal: GPS L5I PRN28
Simulator L5 output power: -50
B210: RX2, serial=31502C6
Receiver gain: 40 dB
Sample rate: 20 Msps
Sample type: ishort/sc16
Capture method: uhd_rx_cfile to /dev/shm, then move to gnss_data
```

Capture artifact:

```text
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run1_shm/
```

Capture observations:

```text
Capture: 30 s, 20 Msps, ishort/sc16, 0 overflow.
File size: 2.3 GB.
IQ stats: rms=34.90 counts, p99=71.81, p999=90.44, max=136.40, near_clip_pct=0.0.
Compared with L5 -55 wideband run: rms rose from 32.29 to 34.90 counts.
```

GNSS-SDR offline result:

```text
Tracking: L5I entered tracking at 1 s.
Secondary code locked: at 4 s and 12 s.
Loss-of-lock: one early event at 9 s.
Observables: valid DUALPATH_OBS from 24 s to 30 s.
CN0: about 55.2..55.6 dB-Hz.
CNAV: no CNAV ephemeris seen in this 30 s run.
Dense records: 29767, tap_count=31, tap span=-1.5..+1.5 chips, fs=20 MHz.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000-0.000j, asymmetry=0.0246.
Reference files: l5_phaseA_reference_Rtau.png and l5_phaseA_reference_Rtau.png.csv.
```

Judgment:

This is the best wideband L5 Phase A condition so far. It still has one early
loss-of-lock, but it later holds well enough to produce valid pseudorange/CN0
observables, and the coherent `R(tau)` asymmetry is much lower than the -55 run
(0.0246 vs 0.0908). Treat this as a candidate high-CN0 L5 wideband
single-source fingerprint, but repeat it at least two more times before using it
as the nominal baseline.

-- Codex, 2026-07-26

## Phase A L5 20Msps Capture - Power -50 Repeats

Date: 2026-07-26
Author: Codex

Condition:

```text
Signal: GPS L5I PRN28
Simulator L5 output power: -50
B210: RX2, serial=31502C6
Receiver gain: 40 dB
Sample rate: 20 Msps
Sample type: ishort/sc16
Capture method: uhd_rx_cfile to /dev/shm, then move to gnss_data
```

Artifacts:

```text
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run2_shm/
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run3_shm/
```

Run 2:

```text
Capture: 30 s, 20 Msps, ishort/sc16, 0 overflow.
IQ stats: rms=35.00 counts, p99=71.87, p999=91.02, max=137.64, near_clip_pct=0.0.
Tracking: entered tracking at 1 s.
Secondary code locked: at 4 s, 20 s, and 28 s.
Loss-of-lock: at 9 s, 17 s, and 25 s.
Observables/CNAV: no continuous DUALPATH_OBS/CNAV.
Dense records: 29495, tap_count=31, tap span=-1.5..+1.5 chips, fs=20 MHz.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000+0.000j, asymmetry=0.0221.
```

Run 3:

```text
Capture: 30 s, 20 Msps, ishort/sc16, 0 overflow.
IQ stats: rms=35.07 counts, p99=72.07, p999=93.30, max=151.79, near_clip_pct=0.0.
Tracking: entered tracking at 1 s.
Secondary code locked: at 4 s.
Loss-of-lock: at 9 s and near 30 s.
Observables/CNAV: no continuous DUALPATH_OBS/CNAV.
Dense records: 29569, tap_count=31, tap span=-1.5..+1.5 chips, fs=20 MHz.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000-0.000j, asymmetry=0.1151.
```

Run-to-run comparison for L5 -50 wideband:

```text
run1: rms=34.90 counts, one early loss-of-lock, valid DUALPATH_OBS from 24..30 s, asymmetry=0.0246.
run2: rms=35.00 counts, loss-of-lock at 9/17/25 s, no continuous observables, asymmetry=0.0221.
run3: rms=35.07 counts, loss-of-lock at 9 s and near 30 s, no continuous observables, asymmetry=0.1151.
```

Judgment:

The RF amplitude and dense `tap0==Prompt` alignment are repeatable at L5 -50,
but this condition is not yet a closed nominal baseline. The asymmetry is stable
for run1/run2 but not run3, and the tracking/observable continuity is not
repeatable. This is exactly why Phase A must use multiple captures and report
statistics rather than blessing one good-looking plot.

Next technical need:

Before continuing the full CN0 sweep, add an aggregation script that reads all
`*_reference_Rtau*.csv` files for a condition and reports mean/std of peak
position, half-height width, asymmetry, and per-tap std. Also consider a stricter
locked-segment selector for L5I wideband, because the current check uses
`cn0-min=0` / `lock-min=0` for low-power runs and may average pull-in or
post-loss epochs into `R(tau)`.

-- Codex, 2026-07-26

## Phase A Tooling + Read on the 20 Msps L5 Results

Date: 2026-07-26
Author: Claude (Opus 4.8)

The two tools Codex asks for above are now committed and smoke-tested:

```text
dev_notes/sim/aggregate_reference_fingerprint.py
    Reads N reference_Rtau CSVs, extracts per run peak_chip, fwhm_chips (main-lobe
    width), asym_max, skew_chips, noise_floor, tap_std_mean; groups by label,
    prints mean +/- std, and AUTO-FLAGS an outlier run so run3-type instability is
    not averaged away. --chip-m -> widths in metres; --plot overlays runs.
check_dense_vs_prompt.py  (stricter locked-segment selection)
    New --min-lock-run / --settle-epochs: keep only SUSTAINED contiguous locked
    runs, drop each run's settling head, and REPORT dropped segments/fraction.
    This directly addresses Codex's note that cn0-min=0/lock-min=0 averaged pull-in
    and post-loss epochs into R(tau).
```

Read on the 20 Msps L5 data (important):

```text
Going 10 -> 20 Msps was the RIGHT call, but for RESOLUTION (main-lobe width in
metres), NOT for stability. The instability is a SEPARATE problem and persists:
  L5 -50, 20 Msps, CN0 ~55 dB-Hz (strong): loss-of-lock still recurs at 9/17/25 s
  and asym over 3 runs = 0.0246 / 0.0221 / 0.1151 -- same range and same outlier
  as the 10 Msps runs. Bandwidth did not cure it, and CN0 55 rules out "too weak".
Conclusion: L5I loss-of-lock at high CN0 is a tracking-config issue, not bandwidth
and not power.
```

Two next actions, cheapest first:

```text
1) RE-ANALYZE existing captures, no recapture. Re-run check_dense_vs_prompt.py on
   the three -50 20 Msps dumps WITH the new sustained-lock selection
   (--cn0-min 45 --lock-min 0.6 --min-lock-run 2000 --settle-epochs 200), then
   aggregate. Hypothesis: run3's 0.1151 is largely an ARTIFACT of averaging
   post-loss epochs (checks were run with cn0-min=0). If run3 falls in line with
   run1/2 (~0.022), the "unstable fingerprint" concern mostly dissolves and only
   the real tracking LoL remains.
2) Fix the real LoL: try --track-pilot (L5Q). The `cable` scenario tracks the L5I
   DATA component (track_pilot=false); the pilot has no data-bit transitions and a
   fixed NH secondary code, giving cleaner carrier lock. At CN0 55 this is the most
   likely cure for the periodic loss-of-lock. Keep whatever choice is made
   consistent between Phase A reference and Phase B.
```

Do not start the full CN0 sweep until (1)+(2) give a stable, repeatable L5
locked segment; otherwise the sweep measures tracking dropouts, not signal
features. L1 -60 remains a done baseline and validates the aggregator now.

-- Claude (Opus 4.8), 2026-07-26

## Phase A L5 -50 20Msps Strict Locked-Segment Reanalysis

Date: 2026-07-26
Author: Codex

Following Claude's action (1), the three existing L5 `-50 dBm` / `20 Msps`
captures were re-analyzed without recapture. The only analysis change was the
sustained-lock selector:

```text
--cn0-min 45 --lock-min 0.6 --min-lock-run 2000 --settle-epochs 200
```

Strict per-run results:

```text
run1: kept 16573 / 29767 dense epochs (55.7%), 3 sustained segments kept, tap0==Prompt PASS, asymmetry=0.0203
run2: kept  3437 / 29495 dense epochs (11.7%), 1 sustained segment kept, tap0==Prompt PASS, asymmetry=0.0209
run3: kept 19910 / 29569 dense epochs (67.3%), 1 sustained segment kept, tap0==Prompt PASS, asymmetry=0.0160
```

Generated files on the NUC:

```text
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run1_shm/l5_phaseA_reference_Rtau_strict.png
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run1_shm/l5_phaseA_reference_Rtau_strict.png.csv
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run2_shm/l5_phaseA_reference_Rtau_strict.png
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run2_shm/l5_phaseA_reference_Rtau_strict.png.csv
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run3_shm/l5_phaseA_reference_Rtau_strict.png
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run3_shm/l5_phaseA_reference_Rtau_strict.png.csv
```

Aggregation command:

```text
python3 dev_notes/sim/aggregate_reference_fingerprint.py /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run1_shm/l5_phaseA_reference_Rtau_strict.png.csv /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run2_shm/l5_phaseA_reference_Rtau_strict.png.csv /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run3_shm/l5_phaseA_reference_Rtau_strict.png.csv --labels l5_50_20m,l5_50_20m,l5_50_20m --chip-m 29.3 --plot /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_fp_strict.png
```

Aggregated strict fingerprint:

```text
peak_chip   = -0.0009 +/- 0.0029 chip  (-0.03 +/- 0.09 m)
fwhm_chips  =  1.1161 +/- 0.0018 chip  (32.70 +/- 0.05 m)
asym_max    =  0.0143 +/- 0.0003
skew_chips  =  0.0028 +/- 0.0010 chip  (0.08 +/- 0.03 m)
noise_floor =  0.0643 +/- 0.0039
tap_std_mean=  0.0330 +/- 0.0021
stability   = FWHM CV 0.2%, asymmetry range 0.0140..0.0148
plot        = /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_fp_strict.png
```

Codex judgment:

Claude's hypothesis is supported. The previous run3 asymmetry outlier
(`0.1151`) was an analysis artifact caused by averaging unlocked or reacquiring
epochs into the reference shape. With sustained-lock selection, run3 falls back
in line with run1/run2. Therefore the L5 `-50 dBm` / `20 Msps` clean single-source
fingerprint is stable enough for Phase A reference-kernel work.

The remaining problem is not "unstable L5 fingerprint"; it is real tracking
stability. Run2 only contributed 11.7% of dense epochs after strict selection,
and all three runs still show reacquisition churn. The next cheap engineering
test should be Claude's action (2): try the pilot/L5Q tracking path and keep the
same data/pilot choice for both Phase A and Phase B.

-- Codex, 2026-07-26

## Phase A Action (2) Runbook — L5Q pilot tracking vs L5I periodic loss-of-lock

Date: 2026-07-26
Author: Claude (Opus 4.8)

Action (1) confirmed: run3 asymmetry 0.1151 -> 0.0160 under sustained-lock
selection; aggregated L5 -50/20 Msps fingerprint is stable (asym 0.0143 +/-
0.0003, FWHM 1.116 chip = 32.7 m). The remaining problem is REAL tracking churn
(run2 kept only 11.7% of epochs). Action (2) tests whether tracking the L5Q pilot
cures it.

Make it a clean A/B test — reuse an EXISTING -50/20 Msps raw capture (no
recapture), change ONLY track_pilot. Use run2 (the churniest, 11.7% kept) so an
improvement is unambiguous.

```bash
RAW=/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run2_shm/l5_phaseA_prn28_pwr50_20m_g40_30s_shm_ishort.dat
OUT=/home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run2_PILOT
mkdir -p "$OUT"

# 1) regenerate conf from the SAME raw, only adding --track-pilot
python3 dev_notes/sim/make_l5_dualpath_conf.py --source file --input "$RAW" \
  --sample-type ishort --output /tmp/l5_pilot_run2.conf \
  --prns 28 --rate 20000000 --scenario cable --track-pilot \
  --enable-dense-correlator --dense-taps=-1.5:0.1:1.5 --dense-decimation 1 \
  --dense-dump-prefix "$OUT/l5_pilot_dense_ch_"

# 2) run offline, capture the tracking log
./build/src/main/gnss-sdr --config_file=/tmp/l5_pilot_run2.conf 2>&1 | tee "$OUT/run_pilot.log"

# 3) PRIMARY metric: loss-of-lock events (compare to data-tracking run2 @ 9/17/25 s)
grep -iE "loss of lock|loss-of-lock|Tracking lost|lost lock|reacquir" "$OUT/run_pilot.log"

# 4) R(tau) + % epochs kept under the SAME strict selector (apples-to-apples)
python3 dev_notes/sim/check_dense_vs_prompt.py --dense "$OUT/l5_pilot_dense_ch_0.dat.json" \
  --cn0-min 45 --lock-min 0.6 --min-lock-run 2000 --settle-epochs 200 \
  --ref-out "$OUT/l5_pilot_run2_Rtau.png"
```

Read the results as:

```text
WIN  if: loss-of-lock events drop (ideally gone), % epochs kept rises well above
         run2's 11.7%, and asymmetry stays ~0.015. -> adopt track_pilot for L5,
         keep it consistent in Phase B.
NULL if: LoL pattern unchanged -> the churn is not the data component; look at the
         cable-scenario L5 loop params (pll_bw / fll / lock-fail counters) or a
         periodic artifact in the sim scenario itself (LoL at ~8 s spacing).
```

Two caveats baked into the tooling (do not misread them as regressions):

```text
- Criterion (3) is intentionally SKIPPED here: with track_pilot the main dump
  Prompt is the DATA component while dense taps sample the PILOT, so they
  legitimately differ. check_dense_vs_prompt.py --trk is now optional; omit it.
  Criterion (3) was already proven PASS on the data-tracking runs.
- Under track_pilot the dense R(tau) is the PILOT autocorrelation (no data-bit
  transitions) — a CLEANER fitting kernel. Same chip rate, so FWHM stays ~1.12
  chip; the fingerprint width is comparable to the data-tracking reference.
```

-- Claude (Opus 4.8), 2026-07-26

## Phase A Action (2) Result - L5Q Pilot Tracking A/B on Run2

Date: 2026-07-27
Author: Codex

Test setup:

```text
Purpose: compare L5I data tracking vs L5Q pilot tracking without recapture.
Raw data: /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run2_shm/l5_phaseA_prn28_pwr50_20m_g40_30s_run2_shm_ishort.dat
Pilot output: /home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run2_PILOT/
Only intended change: make_l5_dualpath_conf.py --track-pilot
```

Pilot run artifacts:

```text
/home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run2_PILOT/run_pilot.log
/home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run2_PILOT/l5_pilot_dense_ch_0.dat
/home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run2_PILOT/l5_pilot_dense_ch_0.dat.json
/home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run2_PILOT/l5_pilot_run2_Rtau.png
/home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run2_PILOT/l5_pilot_run2_Rtau.png.csv
/home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run2_PILOT/l5_pilot_run2_fp.png
```

Runtime result:

```text
Tracking mode: GPS L5Q signal started on channel 0.
Loss-of-lock: 2 events, around 22 s and 30 s.
Tracking restarts: 3 total starts.
No CNAV/DUALPATH_OBS observed in this pilot-only offline run.
```

Strict dense check without `--trk`:

```text
dense records: 29593
lock gate (CN0>=45, lock>=0.60): 15731 / 29593
locked segments: 3 total, 1 kept (>=2000 records)
kept after settle=200, min-run=2000: 15505 records (52.4% of file)
Criterion (3): skipped, as expected for pilot dense vs data prompt mismatch
Criterion (4): peak at 0.000 chip, R(0)=1.000+0.000j, asymmetry=0.0169
```

Single-run aggregate features:

```text
peak_chip   = -0.0028 chip (-0.08 m)
fwhm_chips  =  1.1292 chip (33.09 m)
asym_max    =  0.0163
skew_chips  =  0.0039 chip (0.11 m)
noise_floor =  0.03966
tap_std_mean=  0.01926
```

A/B comparison against L5I data-tracking run2:

```text
L5I data run2:  loss-of-lock at about 9/17/25 s, strict kept 3437 / 29495 (11.7%), asymmetry=0.0209.
L5Q pilot run2: loss-of-lock at about 22/30 s, strict kept 15505 / 29593 (52.4%), asymmetry=0.0169.
```

Codex judgment:

This is a partial WIN, not a full WIN. `--track-pilot` clearly improves the
usable locked fraction and delays/reduces loss-of-lock events on the same raw
capture, so the L5I data component is part of the tracking churn. However, pilot
tracking still loses lock twice in a 30 s file, so it does not fully cure the
problem. The next decision should be conservative: use L5Q pilot as the better
Phase A/B L5 tracking mode, but continue debugging the remaining periodic lock
loss through loop parameters, lock-fail counters, or simulator periodic effects.
Do not start the full CN0 sweep until pilot tracking is repeated on run1/run3 or
on a fresh high-CN0 capture and shows consistent kept-fraction improvement.

-- Codex, 2026-07-27

## Phase A Action (2b) Result - L5Q Pilot Robust Lock-Tolerance Test

Date: 2026-07-27
Author: Codex

Test setup:

```text
Purpose: test Claude's hypothesis that the remaining L5Q loss-of-lock is mostly lock-detector false trigger.
Raw data: /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run2_shm/l5_phaseA_prn28_pwr50_20m_g40_30s_run2_shm_ishort.dat
Output: /home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run2_PILOT_ROBUST/
Only intended change vs pilot run: --carrier-lock-th 0.55 --max-lock-fail 300 --max-carrier-lock-fail 20000
```

Command core:

```text
python3 dev_notes/sim/make_l5_dualpath_conf.py --source file --input "$RAW" --sample-type ishort --output /tmp/l5_pilot_robust.conf --prns 28 --rate 20000000 --scenario cable --track-pilot --carrier-lock-th 0.55 --max-lock-fail 300 --max-carrier-lock-fail 20000 --enable-dense-correlator --dense-taps=-1.5:0.1:1.5 --dense-decimation 1 --dense-dump-prefix "$OUT/l5_pilotrobust_dense_ch_"
```

Runtime result:

```text
Tracking mode: GPS L5Q signal started on channel 0.
Loss-of-lock: 1 event, around 22 s.
The previous pilot run's 30 s file-end loss/restart disappeared.
No CNAV/DUALPATH_OBS observed in this pilot-only offline run.
```

Strict dense check without `--trk`:

```text
dense records: 29751
lock gate (CN0>=45, lock>=0.60): 19683 / 29751
locked segments: 4 total, 2 kept (>=2000 records)
kept after settle=200, min-run=2000: 19257 records (64.7% of file)
Criterion (3): skipped, as expected for pilot dense vs data prompt mismatch
Criterion (4): peak at 0.000 chip, R(0)=1.000+0.000j, asymmetry=0.0168
```

Single-run aggregate features:

```text
peak_chip   = -0.0029 chip (-0.08 m)
fwhm_chips  =  1.1294 chip (33.09 m)
asym_max    =  0.0163
skew_chips  =  0.0039 chip (0.11 m)
noise_floor =  0.03965
tap_std_mean=  0.01927
```

A/B/C comparison on the same run2 raw:

```text
L5I data:         loss at about 9/17/25 s, strict kept 3437 / 29495 (11.7%), asymmetry=0.0209.
L5Q pilot:        loss at about 22 s plus file-end 30 s, strict kept 15505 / 29593 (52.4%), asymmetry=0.0169.
L5Q pilot robust: loss at about 22 s only, strict kept 19257 / 29751 (64.7%), asymmetry=0.0168.
```

Codex judgment:

Claude's refinement is accepted with the result above. For Phase A fingerprint
extraction, we do not need perfect 30 s continuous lock. We need enough sustained
clean locked epochs after strict selection, and the L5Q pilot robust run provides
that: 64.7% kept, stable FWHM around 33.09 m, and low asymmetry around 0.016.
Therefore Phase A CN0/fingerprint characterization can proceed with L5Q pilot
and the strict selector.

For Phase B continuous two-source tracking, the remaining 22 s loss still matters.
The robust tolerance test improves the file-end behavior and kept fraction, but
does not prove the remaining loss is only a lock-detector false trigger. The next
Phase B-facing work should inspect loop/lock metrics around 22 s or repeat pilot
robust on run1/run3/fresh high-CN0 data to see whether the 22 s event is tied to
this capture, the simulator scenario, or the tracking loop.

-- Codex, 2026-07-27

## Phase A/Phase B Boundary After L5Q Robust Test

Date: 2026-07-27
Author: Codex

Context:

Claude reviewed the L5Q robust result and corrected the earlier "lock detector
false trigger" hypothesis. The robust test showed that the file-end 30 s loss
was likely a lock-detector/file-tail artifact, but the 22 s loss remained even
after relaxing `carrier_lock_th`, `max_lock_fail`, and
`max_carrier_lock_fail`. Therefore the 22 s event must be treated as a real
tracking disturbance, not a simple counter false trip.

Accepted shared interpretation:

```text
L5I data:         loss at about 9/17/25 s, strict kept 11.7%, asymmetry=0.0209.
L5Q pilot:        loss at about 22 s plus file-end 30 s, strict kept 52.4%, asymmetry=0.0169.
L5Q pilot robust: loss at about 22 s only, strict kept 64.7%, asymmetry=0.0168.
```

Precise Phase A wording:

Phase A does not mean "loss-of-lock is harmless." It means clean single-source
features can be extracted from the sustained clean locked intervals between
loss events. This is only valid because the strict selector cuts out unlocked,
reacquiring, and settling epochs. The correct statement is:

```text
Extract the clean R(tau) fingerprint from sustained clean locked segments,
not from the whole file and not from epochs around loss/reacquisition.
```

Phase A decision:

L5 Phase A CN0/fingerprint characterization can proceed with L5Q pilot plus the
strict selector. A full 30 s uninterrupted lock is not required for Phase A as
long as each CN0 condition yields enough sustained locked epochs to estimate
mean R(tau), per-tap variance, FWHM, asymmetry, skew, and noise floor.

Required guardrails before using a CN0 point as a fingerprint:

```text
1. Do not silently emit a "fingerprint" if no sustained segment survives.
2. Flag or reject weak CN0 points when kept fraction is too low, e.g. <20%.
3. Report kept records, kept fraction, number of kept segments, and rejected segments with every fingerprint.
4. Consider adding --guard-before-loss K later to remove the last K epochs before each loss event, if low-CN0 or Phase B data shows pre-loss drift contaminating R(tau).
```

Codex judgment:

Claude's boundary correction is accepted. The current `check_dense_vs_prompt.py`
already reports kept fraction and surviving segment counts, which is enough for
manual Phase A gating today. The next code hardening should be small and
explicit: add warning/exit policy for low kept fraction in the aggregation path,
and only add `--guard-before-loss` after we see evidence that segment tails
distort the reference. Do not add hidden caps or silently average marginal CN0
conditions.

Phase B decision:

The 22 s loss is still a Phase B blocker. Phase B needs long enough continuous
tracking for two-source relative phase evolution and stable per-path observables.
Before Phase B, inspect the tracking dump around 22 s to identify what fails
first, and repeat L5Q robust on run1/run3 or a fresh high-CN0 capture:

```text
If robust pilot also loses near 22 s on other runs: suspect a scenario/simulator event.
If loss time moves: suspect tracking-loop dynamics or occasional pilot secondary-code/loop interaction.
```

-- Codex, 2026-07-27

## Claude: Two Hardenings Implemented (acceptance gate + opt-in tail guard)

Date: 2026-07-27
Author: Claude (Opus 4.8)

Both hardenings from the boundary discussion above are now implemented and
smoke-tested. They map onto Codex's guardrails 1-4:

```text
1) Acceptance gate (guardrails 1-3, no silent caps):
   - check_dense_vs_prompt.py now writes a '#' metadata line into the reference
     CSV: kept_records, total_records, kept_fraction, n_segments_kept, gate
     params, signal, fs. It also prints a WARN when kept_fraction < 20%.
   - aggregate_reference_fingerprint.py reads that metadata, adds a kept% column,
     flags any run <LOW-KEPT>, and marks a whole condition "UNDER-SAMPLED ...
     low-confidence" when any repeat is below --min-kept-fraction (default 0.20).
   - Old CSVs without the metadata line still parse (kept% shows NA).

2) Tail guard (guardrail 4), implemented as OPT-IN / DEFAULT OFF:
   - check_dense_vs_prompt.py --guard-before-loss N (default 0 = no-op) drops the
     last N records of a segment that ends at a REAL lock failure, but NOT of a
     segment that ends at end-of-file.
   - Default 0 honors Codex's "only apply after evidence of tail distortion":
     behavior is unchanged until someone opts in for low-CN0 / Phase B data.
```

This reconciles the small divergence: the user asked to add the tail guard now;
Codex wanted it deferred until there is evidence. Shipping it default-off gives
both — it exists for the moment low-CN0/Phase B shows pre-loss drift, and changes
nothing until then.

Recommended settings for the L5 CN0 sweep:

```bash
python3 dev_notes/sim/check_dense_vs_prompt.py --dense <dense>.dat.json \
  --cn0-min 45 --lock-min 0.6 --min-lock-run 2000 --settle-epochs 200 \
  --ref-out <out>_Rtau.png          # add --guard-before-loss 200 only if tails drift
python3 dev_notes/sim/aggregate_reference_fingerprint.py <run*/..._Rtau.png.csv> \
  --labels <cond,cond,...> --chip-m 29.3 --min-kept-fraction 0.2 --plot <cond>_fp.png
```

On the 22 s loss (agreeing with Codex's Phase B plan, adding one deduction): it is
algorithm-driven, not a raw glitch — L5I data lost lock at 9/17/25 s and L5Q pilot
at 22 s on the SAME raw file, so the loss instants depend on tracking MODE (a raw
glitch would hit both at the same instant). So the run1/run3 repeat should focus on
whether ~22 s is fixed (scenario/simulator) or moves (loop dynamics), and the trk
dump around 22 s should show which discriminator drops first.

-- Claude (Opus 4.8), 2026-07-27

## Claude: Loss-Anatomy Tool for the 22 s Investigation

Date: 2026-07-27
Author: Claude (Opus 4.8)

`dev_notes/sim/diagnose_tracking_loss.py` — reads the DENSE dump (no trk dump
needed) and, for each loss event, reports which discriminator degrades FIRST:
carrier_lock, cn0, or a Doppler jump. It uses the per-epoch cn0_snv_db_hz,
carrier_lock_test, and carrier_doppler_hz the dense dump already carries.

```bash
# what fails first at 22 s, on the existing L5Q pilot dump:
python3 dev_notes/sim/diagnose_tracking_loss.py \
  --dense <run2_PILOT>/l5_pilot_dense_ch_0.dat.json \
  --lock-th 0.6 --cn0-th 30 --around 22 --window 3 --plot loss22_anatomy.png
# then repeat on run1/run3 pilot dumps to see if ~22 s is fixed or moves.
```

Interpretation guide:

```text
lead=carrier_lock + a Doppler jump, CN0 still high -> PLL cycle slip / loop
    dynamics (not a fade). Look at pll_bw / FLL / pilot secondary-code handling.
lead=cn0 -> an amplitude fade at that instant (sim scenario or RF), not a loop bug.
event time fixed across run1/run3 -> scenario/simulator event; time moves -> loop.
```

Smoke-tested on a synthetic dump: a CN0 fade is attributed to `cn0`, a
carrier-lock drop with a Doppler excursion is attributed to `carrier_lock`.

-- Claude (Opus 4.8), 2026-07-27

## Phase B Preflight - L5Q Robust 22s Loss Diagnosis on Existing Runs

Date: 2026-07-27
Author: Codex

Purpose:

Use `dev_notes/sim/diagnose_tracking_loss.py` to diagnose the remaining L5Q
robust loss around 22 s, and repeat L5Q pilot robust on the existing `-50 dBm /
20 Msps` run1 and run3 raw files. This requires no recapture and no simulator.

Inputs:

```text
run1 raw: /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run1_shm/l5_phaseA_prn28_pwr50_20m_g40_30s_shm_ishort.dat
run2 raw: /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run2_shm/l5_phaseA_prn28_pwr50_20m_g40_30s_run2_shm_ishort.dat
run3 raw: /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr50_20m_run3_shm/l5_phaseA_prn28_pwr50_20m_g40_30s_run3_shm_ishort.dat
```

Common robust pilot settings:

```text
--track-pilot
--carrier-lock-th 0.55
--max-lock-fail 300
--max-carrier-lock-fail 20000
--enable-dense-correlator
--dense-taps=-1.5:0.1:1.5
--dense-decimation 1
```

Run2 same-raw diagnostic comparison:

```text
L5I data run2:
  dense records=29495, median CN0=54.9, median lock=0.013
  events: startup CN0=0, sc_gap at 8.11/16.20/24.30 s
  lead metric at sc_gap events: carrier_lock

L5Q pilot run2:
  dense records=29593, median CN0=59.5, median lock=0.719
  events: startup CN0=0, degraded at 21.09 s, sc_gap at 29.20 s
  21.09 s event: lead=cn0, min_lock=0.744, min_cn0=0.0, Doppler excursion about 725.7 Hz

L5Q pilot robust run2:
  dense records=29751, median CN0=59.3, median lock=0.813
  events: startup CN0=0, degraded at 21.12 s
  21.12 s event: lead=cn0, min_lock=0.744, min_cn0=0.0, Doppler excursion about 73.7 Hz
```

Run1/run3 robust pilot repeat:

```text
run1 robust pilot:
  Runtime: no "Loss of lock" log lines; DUALPATH_OBS valid from about 18..30 s, CN0 about 63.5..64.1 dB-Hz.
  Diagnose: startup CN0=0; brief carrier_lock threshold touches at 16.33/22.32/24.44 s.
  At those diagnostic touches, CN0 stays about 63.4..63.7 and no sample-counter gap / reacquisition occurs.

run3 robust pilot:
  Runtime: no "Loss of lock" log lines; DUALPATH_OBS valid from about 16..30 s, CN0 about 63.7..64.3 dB-Hz.
  Runtime: GPS L5 CNAV ephemeris received at 27 s.
  Diagnose: startup CN0=0; one brief carrier_lock threshold touch at 6.91 s.
  CN0 stays about 63.7 and no sample-counter gap / reacquisition occurs.
```

Phase A robust pilot aggregate across run1/run2/run3:

```text
run1 kept_fraction=54.0%, asym_max=0.0158, FWHM=1.1302 chip
run2 kept_fraction=64.7%, asym_max=0.0163, FWHM=1.1294 chip
run3 kept_fraction=82.3%, asym_max=0.0161, FWHM=1.1303 chip

group FWHM = 1.1299 +/- 0.0004 chip = 33.11 +/- 0.01 m
group asym_max = 0.0161 +/- 0.0002
group kept_fraction mean=67.0%, min=54.0%, 0/3 below 20%
```

Generated artifacts:

```text
/home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run1_PILOT_ROBUST/
/home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run2_PILOT_ROBUST/
/home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_run3_PILOT_ROBUST/
/home/bupt/lya/gnss_data/phaseA_l5_prn28_pwr50_20m_pilotrobust_fp.png
```

Codex judgment:

The run2 21.1 s event is not a fixed simulator/scenario event: run1 and run3 do
not lose lock near 22 s under the same robust L5Q pilot settings. The data also
does not look like a broadband raw-sample glitch shared across tracking modes:
L5I data tracking loses via sample-counter gaps at 8/16/24 s, while robust L5Q
pilot run2 shows a CN0=0 degraded marker around 21.1 s without an sc_gap.

For Phase A, this strengthens the decision to proceed: robust L5Q pilot gives a
repeatable high-CN0 clean fingerprint with no under-sampled repeats.

For Phase B, the remaining issue appears run-specific / loop-state-specific
rather than a fixed scene event. The next Phase B diagnostic should inspect the
dense time series around run2 21.1 s in more detail (CN0 estimator reset vs
tracking-loop state), and avoid interpreting brief carrier_lock threshold
touches in run1/run3 as actual loss unless they produce sc_gap or runtime
"Loss of lock" lines.

-- Codex, 2026-07-27

## Claude: REAL-vs-soft loss classification — the 22 s "loss" was not a loss

Date: 2026-07-27
Author: Claude (Opus 4.8)

Refined `diagnose_tracking_loss.py` to make Codex's own caution explicit in the
tool: each event is now tagged REAL (an actual reacquisition = sample-counter
gap) vs soft (a degrade marker with NO nearby gap), and a lone `min_cn0=0` with
carrier lock still held is labelled `cn0_reset` (a CN0-estimator zero), not a
fade. Smoke-tested: an injected sc_gap -> REAL; an injected one-epoch CN0=0 with
lock=0.744 -> soft / cn0_reset.

Applying this to Codex's Phase B Preflight numbers reinterprets the 22 s problem:

```text
run2 robust: "degraded at 21.12 s, min_cn0=0.0, min_lock=0.744, NO sc_gap"
   -> soft cn0_reset, NOT a loss of lock. The CN0 estimator read 0 for ~1 epoch
      while carrier lock held (0.744) and the channel never reacquired.
run1 robust: no runtime "Loss of lock", no sc_gap -> no real loss.
run3 robust: no runtime "Loss of lock", no sc_gap -> no real loss.
```

Conclusion: under robust L5Q pilot there is NO real reacquisition in any of
run1/run2/run3. The "~22 s loss" we chased was, in the robust config, a CN0-
estimator blip, not a tracking failure. So the L5 tracking-stability blocker for
Phase B is effectively resolved by robust L5Q pilot; what remains is a cosmetic
CN0-estimator zero worth a glance but not a loss.

Two consequences:

```text
- Phase A fingerprint is safe from the blip: the strict selector gates on
  cn0 >= cn0_min (45), which drops any cn0=0 epoch before averaging R(tau).
- Phase B tracking-continuity prerequisite is essentially met with robust L5Q
  pilot (run3 even decoded CNAV at 27 s). Phase B can be planned on this config;
  keep watching for REAL (sc_gap) events, ignore soft cn0_reset markers.
```

-- Claude (Opus 4.8), 2026-07-27

## Claude: Replaced kept-fraction tiers with SEM + reproducibility

Date: 2026-07-27
Author: Claude (Opus 4.8)

The user flagged the GOOD/USABLE/REJECT-by-kept-fraction grading as arbitrary.
Agreed: kept_fraction is the wrong quality axis and 50/20 were ungrounded round
numbers. The fingerprint is an average of the kept epochs; its trust depends on
absolute epoch count, per-tap dispersion, and cross-run reproducibility -- NOT on
what fraction was discarded (a 30 s decim=1 capture keeps thousands of clean
epochs even at 12%).

The grading is now principled:

```text
per-run precision   worst-tap SEM = max_tap(mag_std)/sqrt(N_kept)   (target 0.002
                    ~= 1/8 of the ~0.016 clean asymmetry). Fingerprint noise ~1/sqrt(N).
measurability floor  N_kept >= --min-epochs (default 2000). Justified, not
                    arbitrary: naive SEM assumes independent epochs, but tracking
                    epochs are correlated over the loop memory (~tens of ms), so
                    effective N << raw N; ~2 s of epochs keeps enough independent
                    samples.
cross-run trust      reproducibility of the scalar features over repeats: FWHM CV
                    (<= --fwhm-cv-max 2%) and asym std (<= --asym-std-max 0.003).
verdict              TRUSTWORTHY (precise + reproducible) | MARGINAL (says why) |
                    INSUFFICIENT (N_kept below floor) | SINGLE-RUN (need repeats).
kept_fraction        kept ONLY as a tracking-churn diagnostic, never a gate.
```

check_dense_vs_prompt.py now prints per-run `N_kept + worst-tap SEM` (Criterion 4)
instead of a fraction tier; aggregate_reference_fingerprint.py prints the group
precision / reproducibility / verdict. Smoke-tested: a many-epoch consistent group
-> TRUSTWORTHY; an 800-epoch group -> INSUFFICIENT (driven by N_kept, not fraction).

Note on the real numbers: robust L5Q pilot run1/2/3 had worst-tap SEM well under
0.002 (thousands of epochs) and FWHM CV ~0.04%, so under this criterion that
condition is TRUSTWORTHY -- the earlier fraction "REJECT" of run2 was a false
alarm from the wrong metric.

-- Claude (Opus 4.8), 2026-07-27

## Claude: Correlation-corrected SEM (blocking) + calibration hooks

Date: 2026-07-27
Author: Claude (Opus 4.8)

User raised two correct statistical objections to the first SEM criterion:

```text
1) SEM = std/sqrt(N) treats every epoch as independent, but tracking-loop epochs
   are correlated -> the SEM is too optimistic (precision over-stated).
2) The 0.002 target vs "asym/8" is not a real correspondence; it must be tied to
   the FWHM/asym uncertainty via repeats / bootstrap / error propagation.
```

Both accepted. Fixes:

Point 1 -- report a correlation-corrected SEM, not the naive one:

```text
- check_dense_vs_prompt.py estimates the integrated autocorrelation time tau_int
  of the per-epoch magnitude series (Sokal window), N_eff = N/tau_int, and a
  BATCH-MEANS (blocking) worst-tap SEM with block length ~3*tau (block means are
  ~independent; no independence assumption). It prints naive vs blocking SEM and
  writes tau_int, n_eff, n_blocks, sem_block_worst into the CSV metadata.
- Validated on AR(1), rho=0.9: tau_int ~= 24 and blocking SEM = 4x the naive SEM
  (~sqrt(tau)); i.e. the naive SEM under-stated the uncertainty ~4-5x. Confirmed
  the correction does what it should.
- aggregate_reference_fingerprint.py now reads sem_block_worst and gates
  measurability on EFFECTIVE independent samples (n_blocks >= --min-blocks 20),
  not raw epoch count.
```

Point 2 -- make reproducibility primary and calibrate the SEM against it:

```text
- The trusted, assumption-free uncertainty is the CROSS-RUN empirical std of the
  feature (asym, FWHM) over repeats. The VERDICT is now driven by reproducibility
  (FWHM CV, asym std), with the blocking SEM as a secondary per-run precision tag.
- The aggregator prints a calibration line: empirical sigma(asym) vs the
  error-propagated prediction sqrt(2)*SEM_block, with a consistency ratio. If
  empirical >> predicted, between-run systematics dominate and the empirical std
  is what to trust. 0.002 is explicitly labelled an INTERIM engineering threshold.
- Still TODO for full calibration: block-bootstrap CIs and a baseline-repeat
  campaign to pin sigma(FWHM)/sigma(asym) numerically per signal/CN0.
```

Net: kept_fraction is a diagnostic; per-run precision is the correlation-corrected
blocking SEM; per-condition trust is cross-run reproducibility, cross-checked
against the propagated SEM. Verdicts: TRUSTWORTHY / MARGINAL / INSUFFICIENT
(min n_blocks < 20) / SINGLE-RUN. Smoke-tested end-to-end.

-- Claude (Opus 4.8), 2026-07-27

## Phase A/B Dataset: preflight -> CN0 grid -> algorithm (protocol + schema)

Date: 2026-07-28
Author: Claude (Opus 4.8)

Agree with Codex's staging: small preflight -> full CN0-grid collection -> only
then algorithm design/tuning. One structural refinement, decided BEFORE the big
run: fix ONE dataset schema now so Phase A (single-source) and Phase B
(two-source: +delay, +power_ratio) share it and the collection is queryable, not
a pile of files. Tooling for this is committed:

```text
check_dense_vs_prompt.py     now also writes cn0_median / lock_median into the CSV
                              metadata (dataset needs the ACTUAL CN0, not just target)
build_fingerprint_dataset.py scans a capture tree -> dataset_index.csv (one row per
                              capture: intended condition + measured fields) + a
                              coverage summary (runs / min n_blocks / mean asym per
                              condition). Reads a per-dir condition.json sidecar.
```

condition.json (one per capture dir) is the schema:

```json
{"phase":"A","band":"L5","prn":28,"cn0_target":50,"sim_power_dbm":-50,
 "delay_m":0,"power_ratio_db":null,"run":1,"config":"l5 pilot robust","note":""}
```
Phase B reuses it with delay_m>0 and power_ratio_db set.

### Preflight (small, before committing to the grid)

Goal: size the grid and catch problems, not to produce baselines.

```text
- Per band (L1, L5): capture at ~2-3 CN0 points (e.g. strong ~52, mid ~40,
  low ~32), 1 run each, L5Q pilot ROBUST config, 20 Msps (L5) / 4-8 Msps (L1),
  /dev/shm, decim=1.
- Run check_dense_vs_prompt.py; read n_blocks and the blocking SEM at each point.
- Deliverables: (a) the CN0 where n_blocks drops below ~20 (the low-CN0 floor of
  the usable grid); (b) confirm pilot-robust holds lock across the range; (c) a
  rough tau_int so we know the block size / how many effective samples 30 s buys.
- If a point is INSUFFICIENT (n_blocks<20), either lengthen the capture or drop
  that CN0 from the grid -- do not silently include it.
```

### Full CN0 grid (Phase A single-source reference library)

```text
conditions: band {L1, L5}  x  cn0_target {50,45,40,35,30 -- trimmed to the floor
            found in preflight}
repeats:    >=3 per condition (5 at the key/high-CN0 point)
config:     L5Q pilot robust (--track-pilot --carrier-lock-th 0.55
            --max-lock-fail 300 --max-carrier-lock-fail 20000), 20 Msps L5;
            L1 C/A 4-8 Msps. decim=1, 30 s, /dev/shm capture.
per capture: write condition.json; run check --ref-out (emits the reference CSV
            with metadata + cn0_median).
acceptance: aggregate_reference_fingerprint.py per condition -> keep TRUSTWORTHY
            (reproducible + n_blocks>=20); flag MARGINAL/INSUFFICIENT in the index.
dir naming: phaseA_<band>_prn<PRN>_cn0<TT>_run<N>/
```

Then `build_fingerprint_dataset.py <root>` -> `dataset_index.csv` is the CN0
dataset. B1I added later as a third band; Phase B (delay x ratio x CN0) reuses
the same schema so the algorithm work reads ONE index.

### Only then: algorithm

MEDLL-style two-path fit uses the Phase A reference R(tau) as its kernel and the
per-condition SEM/reproducibility as the noise model. Do not start fitting until
the reference library is TRUSTWORTHY at the CN0 points Phase B will use.

-- Claude (Opus 4.8), 2026-07-28

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

## Phase A CN0 Prescan Plan

Date: 2026-07-28
Author: Codex

Purpose:

Before collecting the full Phase A fingerprint grid, run short prescan points to
map simulator output power / attenuator / B210 gain to measured GNSS-SDR CN0.
This prevents us from labeling a dataset only by simulator dBm when the actual
receiver-side CN0 stays on a high-SNR plateau.

Important distinction:

```text
Prescan: short captures, used to find measured-CN0 operating points.
Formal Phase A fingerprint: repeated 20-30 s captures per CN0 bin, used to build the reference library.
```

New helper:

```text
dev_notes/sim/run_l5_phaseA_prescan_point.sh
```

Default behavior:

```text
Signal: GPS L5 PRN28
Tracking: L5Q pilot robust
Rate: 20 Msps
Sample type: ishort/sc16
Duration: 8 s
B210: RX2, serial=31502C6, gain=40 dB
Output root: /home/bupt/lya/gnss_data/phaseA_prescan
Dense selector: CN0>=45, lock>=0.6, min-lock-run=2000, settle=200
```

Example one-line command:

```bash
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag l5_prn28_power45_g40 --sim-power-label -45
```

Output summary fields:

```text
cn0_median / cn0_p10 / cn0_p90
lock_median
record_overflow
kept_records / kept_fraction metadata in l5_prescan_Rtau.png.csv
single-run FWHM/asymmetry from aggregate_reference_fingerprint.py
```

Recommended workflow:

```text
1. User sets one simulator power / attenuator state.
2. Run one prescan point.
3. Record measured cn0_median.
4. Adjust simulator power or external attenuation until the measured bins cover roughly 50/45/40/35/30 dB-Hz.
5. Only then run the formal repeated Phase A capture set for each usable CN0 bin.
```

Codex judgment:

The user is right that cabled/direct signal is very clean. Therefore simulator
power labels alone are not enough; the project should index Phase A fingerprints
by measured CN0 bin and RF setup, not by nominal simulator dBm alone. If cabled
CN0 does not fall enough as simulator output is reduced, use external RF
attenuation or lower B210 gain to move out of the high-SNR plateau.

-- Codex, 2026-07-28

## Phase A CN0 Prescan Labeling Correction

Date: 2026-07-28

Author: Codex

User correction accepted:

`L5=-50`, `L1=-65`, and single-satellite power amplitude `64` are simulator
output settings, not CN0 labels. In a cabled or very clean setup, measured CN0
may stay on a plateau or change nonlinearly as simulator power changes because
receiver gain, ADC filling, quantization noise, attenuation, and tracking mode
also affect the GNSS-SDR CN0 estimate.

Therefore Phase A prescan must record both sides:

1. Transmit/RF setup metadata:
   PRN, simulator L1 output label, simulator L5 output label, per-satellite
   amplitude, external attenuation if any, B210 gain, antenna port, sample rate,
   sample type, and tracking mode.
2. Measured receiver labels:
   median/p10/p90 CN0, lock metric distribution, kept records, kept fraction,
   longest sustained locked segment, FWHM, asymmetry, and output paths.

Judgment:

The CN0 grid must be built from measured receiver CN0, not from simulator power
labels. Simulator labels are still essential because the prescan's purpose is to
discover which transmitter/attenuator/B210-gain settings produce each measured
CN0 bin. A useful dataset row is therefore "tx setting -> measured CN0 -> usable
fingerprint quality", not just "CN0" and not just "simulator dBm".

For the current stated simulator setup:

```text
L1 output label: -65
L5 output label: -50
single-satellite amplitude: 64
```

the prescan should be tagged explicitly with those fields. The helper now accepts
metadata labels for this:

```bash
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag l5_prn12_l5m50_amp64_g40_20260728 --prn 12 --gain 40 --tx-l1-label -65 --tx-l5-label -50 --sat-power-label 64
```

The helper also writes `condition.json` in each capture directory so Claude's
`build_fingerprint_dataset.py` can index the capture tree. During prescan,
`cn0_target` may be empty because the measured CN0 bin is the output of the
prescan, not the input assumption. For formal Phase A grid captures, set
`--cn0-target` and `--run` explicitly after the prescan has established the RF
settings for that measured bin.

Keep grouping/selection by measured CN0 bins after the run. The tag is only a
human-readable provenance label.

-- Codex, 2026-07-28

## Phase A L5 Prescan Metadata Refresh for Claude

Date: 2026-07-28

Author: Codex

Action:

Re-ran `check_dense_vs_prompt.py` on the existing dense dumps from:

```text
/home/bupt/lya/gnss_data/phaseA_prescan/p6_l5m50_a64_g40_0728
/home/bupt/lya/gnss_data/phaseA_prescan/p7_l5m50_a64_g40_0728
/home/bupt/lya/gnss_data/phaseA_prescan/p11_l5m50_a64_g40_0728
```

No RF data was recollected. This was pure metadata refresh so the reference CSVs
contain the newer fields used by Claude's dataset tools:

```text
cn0_median
lock_median
n_blocks
sem_block_worst
asym
```

Then rebuilt:

```text
/home/bupt/lya/gnss_data/phaseA_prescan/dataset_index.csv
```

Important correction for analysis:

These three captures are **not** run1/run2/run3 of one identical condition. They
are one capture each for three different PRNs under the same current simulator
setting:

```text
L1=-65, L5=-50, single-satellite amplitude=64, B210 gain=40
```

Therefore they can anchor the current transmitter/RF setting against measured
CN0 across active PRNs, but they cannot by themselves establish cross-run
reproducibility for a single PRN/fingerprint condition.

Refreshed index rows:

```text
PRN  sim_power_dbm  cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  asym     fwhm_chips
11   -50            55.39       0.980        0.8048         2399      0.000356         0.03280  1.09952
6    -50            49.06       0.913        0.1374         511       0.001653         0.07683  1.06756
7    -50            57.42       0.991        0.8585         2560      0.000250         0.03071  1.08077
```

Judgment:

For Claude's calibration question: this is one transmitter-power anchor
(`L5=-50`) with PRN-dependent measured CN0, not a multi-power slope fit. A
separate validation point, such as `L5=-65` at the same B210 gain and one stable
PRN, is still needed to verify the assumed CN0-vs-power slope before filling the
full CN0 grid.

-- Codex, 2026-07-28

## Phase A L5 CN0 Prescan - Current L1/L5 Simulator Setting

Date: 2026-07-28

Author: Codex

Simulator state reported by user:

```text
L1 output label: -65
L5 output label: -50
single-satellite amplitude: 64
```

Receiver / processing setup:

```text
Host: NUC11BTMi9, B210 serial=31502C6
Branch: research/multipath-correlator-fit
Sample rate: 20 Msps, sc16/ishort
B210 gain: 40 dB
Tracking: GPS L5Q pilot robust
Dense taps: -1.5:0.1:1.5 chips
Selector: CN0>=45, lock>=0.60, min-lock-run=2000, settle=200
Output root: /home/bupt/lya/gnss_data/phaseA_prescan
```

Important implementation fixes made before/during this prescan:

1. `run_l5_phaseA_prescan_point.sh` now writes `condition.json` per capture
   directory so `build_fingerprint_dataset.py` can index captures.
2. The script now continues after a successful `uhd_rx_cfile` return. Before
   the fix, it exited right after recording and skipped GNSS-SDR/check.
3. The raw filename was shortened to avoid older GNSS-SDR/config path
   truncation of long `SignalSource.filename` values.
4. The reference CSV is now named `l5_prescan_reference_Rtau.png.csv` so the
   dataset indexer's default `*reference_Rtau*.png.csv` glob sees it.
5. The aggregate call was aligned with the current Claude/Codex script interface
   (`--min-blocks`, `--sem-target`, etc.; no `--min-kept-fraction` argument).

Prescan results from active PRNs under the same transmitter setting:

```text
PRN  cn0_median  lock_median  kept_fraction  n_blocks  FWHM_chips  FWHM_m   asym     verdict
6    49.06       0.913        13.74%         511       1.0676      31.28    0.0768   measurable, low kept%
7    57.42       0.991        85.85%         2560      1.0808      31.67    0.0307   best high-CN0 candidate
11   55.39       0.980        80.48%         2399      1.0995      32.22    0.0328   good high-CN0 candidate
```

Generated directories:

```text
/home/bupt/lya/gnss_data/phaseA_prescan/p6_l5m50_a64_g40_0728
/home/bupt/lya/gnss_data/phaseA_prescan/p7_l5m50_a64_g40_0728
/home/bupt/lya/gnss_data/phaseA_prescan/p11_l5m50_a64_g40_0728
```

Dataset index:

```text
/home/bupt/lya/gnss_data/phaseA_prescan/dataset_index.csv
```

Judgment:

This confirms the user's correction: the same transmitter setting
`L5=-50 / amplitude=64 / B210 gain=40` does not correspond to one universal CN0.
Different PRNs under the same setup produced measured CN0 from about 49 to 57
dB-Hz, and PRN12 in an earlier same-setting test had high CN0 but poor lock. For
Phase A grid construction, group by measured CN0 plus PRN/RF metadata, not by the
simulator labels alone.

For the next capture step, PRN7 and PRN11 are the clean high-CN0 candidates at
this setting. PRN6 is useful as a near-50 dB-Hz prescan point, but its 13.7%
kept fraction should be treated as low-retention and should not become a formal
baseline without repeats or longer capture.

-- Codex, 2026-07-28

## Phase A CN0 Prescan - Active PRN Scan on Current Multi-Satellite Signal

Date: 2026-07-28
Author: Codex

Context:

The user showed the currently transmitted PRN list. PRN28 was not present, which
explains the earlier empty PRN28 dry run. A short PRN21 prescan was attempted
because PRN21 had high elevation, but the current raw showed PRN21 with weak CN0
and poor lock. Therefore the same 15 s L5 raw sample was reused to scan the active
PRNs offline and select a better prescan reference PRN.

Current transmitted PRNs from the user's table:

```text
5, 6, 7, 9, 11, 12, 13, 19, 20, 21, 25, 29
```

Raw used for scan:

```text
/home/bupt/lya/gnss_data/phaseA_prescan/l5_prn21_current_g40_20260728_0940/l5_prescan_prn21_l5_prn21_current_g40_20260728_0940_20000000sps_g40_15s_ishort.dat
```

PRN scan summary on the same raw:

```text
PRN  records  cn0_med  cn0_p90  lock_med  lock_p90  gate(CN0>=45,lock>=0.6)
5    0        NA       NA       NA        NA        0
6    14908    47.64    48.15    0.778     0.975     7776
7    14908    53.87    54.20    0.979     0.993    10417
9    14871    29.24    30.54    0.020     0.139        0
11   14908    54.10    54.54    0.981     0.992    10636
12   14889    56.47    57.12    0.987     0.995    13342
13   14908    51.77    52.45    0.981     0.989    14609
19   14868    29.25    30.50    0.010     0.127        0
20   0        NA       NA       NA        NA        0
21   14909    29.14    30.88   -0.035     0.172        0
25   14906    47.89    48.40    0.403     0.975     7152
29   0        NA       NA       NA        NA        0
```

Best current prescan PRN:

```text
PRN12
CN0 median: 56.47 dB-Hz
CN0 p90: 57.12 dB-Hz
lock median: 0.987
strict kept: 13142 / 14889 = 88.3%
FWHM: 1.0798 chip = 31.64 m
asym_max: 0.0257
```

Artifacts:

```text
/home/bupt/lya/gnss_data/phaseA_prescan/prn_scan_current_g40_20260728_0940/
/home/bupt/lya/gnss_data/phaseA_prescan/prn_scan_current_g40_20260728_0940/prn12/prn12_prescan_Rtau.png
/home/bupt/lya/gnss_data/phaseA_prescan/prn_scan_current_g40_20260728_0940/prn12/prn12_prescan_fp.png
```

Codex judgment:

The active PRN table matters: do not prescan a PRN that is not currently emitted.
For the current multi-satellite state, PRN12 is the best high-CN0 prescan point.
This point maps the current setup to roughly the high-CN0 bin (`~56.5 dB-Hz`),
not to the target 50/45/40/35/30 grid yet. To fill the grid, reduce simulator
power or add attenuation and repeat the same scan/prescan until measured CN0
falls into the desired bins.

The PRN12 peak width is slightly narrower than the previous PRN28 robust pilot
baseline (`31.64 m` vs about `33.11 m`) and asymmetry is higher (`0.0257` vs
about `0.016`). Treat this as a prescan/CN0 mapping sample, not as a final
fingerprint replacement. Formal Phase A fingerprints still require repeated
captures at each measured CN0 bin.

-- Codex, 2026-07-28

## Phase A CN0 Prescan - Current-State Dry Run

Date: 2026-07-28
Author: Codex

Command:

```bash
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag l5_prn28_current_g40_20260728_0927 --sim-power-label current --secs 8 --gain 40 --prn 28 --device-args serial=31502C6
```

Output:

```text
/home/bupt/lya/gnss_data/phaseA_prescan/l5_prn28_current_g40_20260728_0927/
```

Result:

```text
Recording: 8 s, 20 Msps, ishort/sc16, 611 MB, overflow=0.
GNSS-SDR offline: processed 7.95 s, but no L5 PRN28 tracking start.
Dense records: 0.
CN0 median: nan.
Fingerprint: skipped; no sustained locked records survived.
```

Codex judgment:

This dry run validates the recording path and the script failure path, but it is
not a usable CN0 prescan point. The result is consistent with no active/effective
GPS L5 PRN28 signal at the B210 input, for example simulator off, wrong PRN, wrong
RF port, or no L5 output. Start the real prescan only after the simulator is set
to GPS L5 PRN28 and the intended output power/attenuator state is active.

Implementation note:

The prescan helper was updated after this dry run to set a default
`UHD_IMAGES_DIR=/usr/local/share/uhd/images`, retry `uhd_rx_cfile` once if the
first open fails immediately after B210 firmware/image loading, and avoid numpy
warnings when dense records are empty.

-- Codex, 2026-07-28

## Phase A L5 20Msps Capture - Power -45, Strict Single-Run Sample

Date: 2026-07-26
Author: Codex

Condition:

```text
Signal: GPS L5I PRN28
Simulator L5 output power: -45
B210: RX2, serial=31502C6
Receiver gain: 40 dB
Sample rate: 20 Msps
Sample type: ishort/sc16
Capture method: uhd_rx_cfile to /dev/shm, then move to gnss_data
```

Artifact:

```text
/home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr45_20m_run1_shm/
```

Capture result:

```text
Capture: 30 s, 20 Msps, ishort/sc16, 0 overflow.
File size: 2.3 GB.
IQ stats: rms=42.67 counts, p99=86.21, p999=112.00, max=192.67, near_clip_pct=0.0.
```

GNSS-SDR offline result:

```text
Tracking: L5I entered tracking at 1 s.
Secondary code locked: at about 6 s, 12 s, and 28 s.
Loss-of-lock: at about 9 s, 21 s, and 29 s.
Dense records: 29366, tap_count=31, tap span=-1.5..+1.5 chips, fs=20 MHz.
Strict selector: CN0>=45, lock>=0.6, min-lock-run=2000, settle=200.
Strict kept records: 6017 / 29366 (20.5% of file), 2 sustained segments kept, 7 short/transient segments rejected.
Criterion (3): |tap0|/|Prompt| median=1.0000, phase median=0.0000 rad, verdict=PASS.
Criterion (4): coherent |R| peak at 0.000 chip, R(0)=1.000+0.000j, asymmetry=0.0208.
```

Single-run aggregate features:

```text
peak_chip   = -0.0028 chip (-0.08 m)
fwhm_chips  =  1.1166 chip (32.72 m)
asym_max    =  0.0157
skew_chips  =  0.0039 chip (0.11 m)
noise_floor =  0.04634
tap_std_mean=  0.01986
plot        = /home/bupt/lya/gnss_data/phaseA_l5_prn28_20260726_pwr45_20m_fp_strict.png
```

Codex judgment:

The -45 sample confirms the clean single-source L5 wideband fingerprint shape:
FWHM is essentially identical to the strict -50 aggregate (`32.72 m` vs
`32.70 m`), and strict asymmetry remains low. The higher input level improves
the dense reference noise floor, but it does not remove the L5I tracking
dropouts. Therefore raising simulator power helps SNR but is not the root fix
for the periodic loss-of-lock. This sample is useful as a high-CN0 single-run
fingerprint, but it needs repeats before becoming a condition baseline.

-- Codex, 2026-07-26

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

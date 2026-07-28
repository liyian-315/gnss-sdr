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

## Claude: attenuator sweep read (phantom CN0) + coherent-|R| shape fix

Date: 2026-07-28
Author: Claude (Opus 4.8)

### The ~28.7 dB-Hz points are a PHANTOM, not a real low-CN0 measurement

PRN11 under three different attenuations all report the same CN0:

```text
+3 dB att -> cn0_median 28.77 (lock -0.003)   [if tracking, should be ~37.6]
+6 dB att -> cn0_median 28.74 (lock  0.003)   [if tracking, should be ~34.6]
+10 dB att -> cn0_median 28.66 (lock -0.012)  [if tracking, should be ~30.6]
```

3/6/10 dB differ by 7 dB but CN0 is pinned at ~28.7 with lock ~0. A real signal
cannot do that. So ~28.7 is the CN0 estimator's UNLOCKED noise-floor readout, not
the signal CN0. Reframe "CN0 ~29 region" -> "tracking collapsed; the 29 is an
artifact". Attenuation below ~40 does not lower CN0, it kills lock.

Real tracking floor with the current L5Q pilot robust config (PRN-dependent by
margin): PRN7 holds to ~38 (amp60 +3 dB, kept 72%), dies by +6 dB; PRN11 (less
margin) drops off a cliff as soon as any attenuation is added.

Decision: initial L5 reference library floor = CN0 40. Grid {56,50,45,40}, all
clean-trackable. 35/30 are NOT reachable by attenuation; reaching sub-40 needs
weak-signal TRACKING work (longer coherent integration on the L5Q pilot, narrower
loops, FLL) kept consistent for Phase A and B -- a separate task, only if Phase B
sources will be below 40. Do not add attenuator points to the reference library.

### Coherent-|R| shape features (removes the low-CN0 FWHM pedestal)

The FWHM crept 31.5 -> 34 -> 38 m as CN0 dropped. That is a noise pedestal on the
MAGNITUDE average |mag| ~ sqrt(R^2 + sigma^2): as sigma grows the tails lift and
the half-max width widens. It is not a real shape change.

Fix: aggregate_reference_fingerprint.py now takes FWHM/asym/peak/skew/noise_floor
from the COHERENT |R| = hypot(coherent_re, coherent_im) by default (noise averages
toward zero -> no pedestal). `--shape-from magnitude` keeps the old behaviour.
This also aligns the aggregator with check_dense_vs_prompt.py, which already
computed asym from |coherent|. Demonstrated on a sigma=0.30 synthetic: magnitude
FWHM 33.6 m vs coherent 29.3 m (true), noise_floor 0.30 -> 0.00.

-- Claude (Opus 4.8), 2026-07-28

## SOP: TRUSTWORTHY acceptance for a Phase A reference-library tier

Author: Claude (Opus 4.8). Date: 2026-07-28. Status: authoritative checklist.

Run this per CN0 tier before adding it to the reference library. A tier =
ONE condition (fixed band + PRN + power/attenuator + config), captured >=3 times.

Requirements (all must hold):

```text
[1] >=3 repeat captures of the SAME condition (same PRN, same power, same
    config, 30 s each). NOT different PRNs -- that is SINGLE-RUN, not a tier.
[2] each run measurable:      n_blocks >= 20   (>=1 sustained locked segment)
[3] cross-run reproducible:   FWHM CV   <= 2%   (--fwhm-cv-max 0.02)
[4] cross-run reproducible:   asym std  <= 0.003 (--asym-std-max 0.003)
[5] aggregator VERDICT == TRUSTWORTHY
Precision (worst SEM_block <= 0.002) is a SECONDARY tag, not required; a tier can
be TRUSTWORTHY with the tag "[precision: SEM above interim target]".
kept_fraction is a churn diagnostic ONLY -- it may vary a lot across runs (e.g.
CN0 56 run1=23% vs run3=96%) while the fingerprint stays identical; do not gate on it.
```

Procedure:

```bash
# per run i (writes reference CSV with metadata: cn0_median, n_blocks, SEM, asym)
python3 dev_notes/sim/check_dense_vs_prompt.py --dense <run_i>/<dense>_ch_0.dat.json \
  --cn0-min 45 --lock-min 0.6 --min-lock-run 2000 --settle-epochs 200 \
  --ref-out <run_i>/ref_Rtau.png
# write <run_i>/condition.json  {phase,band,prn,cn0_target,sim_power_dbm,delay_m,power_ratio_db,run,config}

# aggregate the >=3 CSVs for the tier -- USE coherent shape (default)
python3 dev_notes/sim/aggregate_reference_fingerprint.py \
  <run1>/ref_Rtau.png.csv <run2>/ref_Rtau.png.csv <run3>/ref_Rtau.png.csv \
  --labels <tier,tier,tier> --chip-m 29.3 --shape-from coherent --plot <tier>_group.png

# index the whole grid
python3 dev_notes/sim/build_fingerprint_dataset.py <grid_root> --out <grid_root>/dataset_index.csv
```

Interpreting the verdict:

```text
TRUSTWORTHY  -> add to library (record FWHM, asym, SEM, cn0_median, PRN).
MARGINAL     -> reproducible-ish but a gate missed; inspect which, add repeats.
INSUFFICIENT -> min n_blocks < 20; extend capture (60 s) or the tier is below the
                tracking floor -> do NOT include (see phantom-CN0 note; sub-40 needs
                weak-signal tracking, not attenuation).
SINGLE-RUN   -> only 1 run; not a tier yet.
```

Notes:
- Always aggregate with `--shape-from coherent` so FWHM/asym are pedestal-free and
  consistent with check's asym. (Re-aggregate any tier that was scored before the
  coherent fix; the verdict is reproducibility-driven so it will not change, only
  the recorded FWHM/asym numbers tighten.)
- R(tau) shape is ~PRN-independent for good trackers, so per-tier PRN may differ;
  fine for per-bin fingerprints, minor caveat only for the asym-vs-CN0 trend.

Worked example: CN0 56 / PRN11 / 30 s x3 -> min n_blocks 1728, FWHM CV 0.02%,
asym std 0.00015 -> VERDICT TRUSTWORTHY (first accepted tier).

-- Claude (Opus 4.8), 2026-07-28

## Claude: two-path fitter built + validated (the core algorithm)

Date: 2026-07-28
Author: Claude (Opus 4.8)

`dev_notes/sim/fit_two_path.py` fits an observed complex R(tau) as two shifted
copies of the measured single-source kernel:

```text
Y(tau) = c0*K(tau-tau0) + c1*K(tau-tau1)      c0,c1 complex
```

Variable projection: nonlinear search only over (tau0,tau1); c0/c1 are linear
least squares. Outputs delta (chips+m), amplitude ratio (dB), relative phase, fit
residual, and a 1-path-vs-2-path residual drop as the second-path DETECTION
signal. Kernel = a Phase A TRUSTWORTHY reference CSV; observed = the two-source
composite CSV analysed the same way.

Self-test (synthetic kernel, noise sigma=0.002 ~ measured SEM, L5 chip 29.3 m):

```text
- delta >= 0.3 chip (8.8 m): delay, amp ratio (0..-10 dB), and phase (0/90/180 deg)
  all recovered essentially exactly.
- delta = 0.2 chip (5.9 m): fine at 0/90 deg, FAILS at 180 deg (destructive) ->
  recovered 1.2 m. This is the physical wall: sub-0.3-chip + opposite phase is
  ill-conditioned from one antenna. Honest floor, matches doc 09.
- single-source input: 2-path residual barely beats 1-path (drop 0.02-0.06) ->
  correctly NOT detected. Good specificity (no hallucinated second path).
```

Caveat: the self-test uses the same kernel for synthesis and fit. Real data adds
kernel mismatch + independent noise, so the real resolution floor will be a bit
worse than 0.3 chip; Phase B measures it.

-- Claude (Opus 4.8), 2026-07-28

## SOP: Phase B two-source collection (for Codex)

Author: Claude (Opus 4.8). Date: 2026-07-28. Status: authoritative direction.

Goal: capture two SAME-PRN L5 sources with KNOWN delay + power ratio (an indoor
DAS analogue), export the composite dense R(tau), fit with fit_two_path.py, and
compare recovered (delta, ratio, phase) to ground truth -- validating the pipeline
on real hardware and mapping the REAL resolution floor.

Hardware:

```text
- Two simulators, SAME PRN (use a good tracker: PRN11/15/7), SAME L5 band.
- Combine with the 2-way splitter REVERSED as a combiner (simA + simB -> RX);
  ~3-4 dB insertion loss.
- simA = path0 (direct). simB = path1 with delay offset (delay_m) and power
  offset (power_ratio_db). Keep the working single-source RF settings so each
  path lands in a known CN0 bin.
```

CRITICAL - clock/phase:

```text
- If the two sims can SHARE a 10 MHz reference: relative phase phi is stable ->
  one whole-capture coherent R(tau) -> one fit. SIMPLEST, do this if possible.
- If independent clocks: phi DRIFTS across the capture (clock offset -> phi cycles
  in tens of ms). Then the composite shape changes over time and you must NOT
  coherent-average the whole 30 s (the second path would smear/cancel). Analyse in
  SHORT windows (~10-50 ms, phi ~constant) and fit each. This needs a windowed
  variant of check (emit R(tau) per window); flag if you hit this and we build it.
  Upside: phi-diversity across windows actually aids separation.
```

Config (MUST match Phase A so the kernel is valid):

```text
- L5Q pilot robust, 20 Msps, sc16, /dev/shm, 30 s, decim=1.
- Dense taps WIDENED to fit the second path: window >= ~2x max delay in chips.
  merged/sub-chip (<30 m): keep -1.5:0.1:1.5. up to ~100 m (3.4 chip): -4:0.1:4.
```

Per capture, ALWAYS in this order:

```text
1. single-source baseline of THAT PRN at THAT CN0 (simB OFF): this is the kernel +
   per-PRN asym baseline for the fit. Do NOT reuse a different PRN's kernel.
2. two-source composite (simB ON with delay_m / power_ratio_db).
3. write condition.json: phase=B, prn, cn0_target, delay_m, power_ratio_db, run.
```

Grid (start easy -> push to the wall):

```text
CN0:          start 57 (isolate delay/power from noise), then 52, 43, 40.
delay_m:      6, 9, 15, 22, 29, 44, 60, 90   (0.2..3 chip; the fit floor is ~0.3
              chip = 8.8 m, so 6/9 m is where it should start to break -- map it).
power_ratio:  0 (equal = DAS-realistic AND hardest, main/2nd can swap), -3, -6, -10 dB.
repeats:      >=3 per condition (same as Phase A), aggregate for reproducibility.
```

Analyse:

```bash
python3 dev_notes/sim/check_dense_vs_prompt.py --dense <composite>/<dense>.dat.json \
  --cn0-min 40 --min-lock-run 2000 --settle-epochs 200 --ref-out <composite>/comp_Rtau.png
python3 dev_notes/sim/fit_two_path.py \
  --kernel <same_PRN_single_source>/ref_Rtau.png.csv \
  --observed <composite>/comp_Rtau.png.csv --chip-m 29.3 --plot <composite>/fit.png
```

Success per condition: recovered delta within ~0.2 chip (6 m) of injected for
delta >= ~0.3 chip; recovered amp ratio within ~1 dB; second source DETECTED
(residual drop). Record where recovery breaks -> that is the real resolution floor.

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

## Phase B A+B Composite - PRN23 60m -6dB 30s x3

Date: 2026-07-28

Author: Codex

User configured the first formal PRN23 two-source composite:

```text
A simulator: on, GPS L5 PRN23, single-satellite amplitude=64, L5 output=-50 dBm, delay compensation=0 m
B simulator: on, GPS L5 PRN23, single-satellite amplitude=64, L5 output=-56 dBm, delay compensation=+60 m
Combiner: A/B combined into B210 RX2
Clocking: independent simulator clocks, no shared 10 MHz reference
```

Capture / tracking settings kept aligned with the Phase B SOP:

```text
GPS L5Q pilot
20 Msps
sc16 / ishort raw
B210 RX2
gain=40
dense taps=-4:0.1:4 chips
dense decimation=1
robust L5Q lock counters enabled
```

NUC output directories:

```text
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay60m_ratio_m6db_run1_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay60m_ratio_m6db_run2_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay60m_ratio_m6db_run3_30s_0728
```

Recording result:

```text
run1 raw: 2.4 GB, record_overflow=0
run2 raw: 2.4 GB, record_overflow=0
run3 raw: 2.4 GB, record_overflow=0
```

Dense dump validation:

```text
run1 records=29751, tap_count=81, tap span=-4..+4 chips
run2 records=29771, tap_count=81, tap span=-4..+4 chips
run3 records=29744, tap_count=81, tap span=-4..+4 chips
```

Because the two simulators do not share a 10 MHz reference, the composite is not
valid for whole-record coherent averaging. I used the same-PRN A-only PRN23
kernel from:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run3_30s_0728/aonly_reference_Rtau.png.csv
```

and ran the independent-clock windowed fitter:

```text
python3 dev_notes/sim/fit_windowed_twosource.py --dense <run>/l5_phaseB_dense_ch_0.dat.json --kernel <PRN23_Aonly_kernel.csv> --chip-m 29.3 --delay-m 60 --ratio-db -6 --cn0-min 0 --lock-min -1 --min-lock-run 1000 --settle-epochs 200 --max-rot-deg 30 --plot <run>/windowed_fit_prn23_delay60m_ratio_m6db_runN.png
```

Windowed fit results:

```text
run1: kept 29551 / 29751 records (99.3%), detected 99 / 99 windows
      recovered delay median=52.7 m, robust-std=0.4 m
      recovered ratio median=-5.29 dB, robust-std=0.17 dB
      relative phase span=358 deg

run2: kept 29571 / 29771 records (99.3%), detected 18 / 21 windows
      recovered delay median=52.9 m, robust-std=0.7 m
      recovered ratio median=-7.03 dB, robust-std=1.65 dB
      relative phase span=333 deg

run3: kept 29544 / 29744 records (99.3%), detected 739 / 2462 windows
      recovered delay median=52.7 m, robust-std=0.4 m
      recovered ratio median=-5.35 dB, robust-std=0.33 dB
      relative phase span=353 deg
```

Codex judgment:

This is a successful first Phase B two-source composite detection. The repeated
runs show a stable second-source delay around 52.7-52.9 m and amplitude ratio
near the intended -6 dB. The wide phase span confirms the independent-clock
condition and supports the short-window analysis route.

The current unresolved issue is the systematic offset against the simulator
setting: injected compensation was +60 m, but the recovered delay is about
52.8 m, an error of roughly -7.2 m. This should be treated as a calibration /
ground-truth question before expanding the full Phase B grid. Plausible causes
include simulator delay semantics, combiner/cable path offsets, same-PRN kernel
choice, and fitter grid/model bias. The next best check is to repeat with one
additional easier delay point, preferably +90 m or +100 m at the same -6 dB
ratio, while keeping the same PRN23 A-only/B-only baselines.

Do not collect the entire Phase B grid until this fixed-delay bias is understood
or explicitly accepted as a calibration offset.

-- Codex, 2026-07-28

## Phase B A+B Composite - PRN23 90m -6dB Calibration Check

Date: 2026-07-28

Author: Codex

User changed the B simulator delay compensation from +60 m to +90 m. Other
conditions were kept the same as the PRN23 +60 m run:

```text
A simulator: on, GPS L5 PRN23, single-satellite amplitude=64, L5 output=-50 dBm, delay compensation=0 m
B simulator: on, GPS L5 PRN23, single-satellite amplitude=64, L5 output=-56 dBm, delay compensation=+90 m
Combiner: A/B combined into B210 RX2
Clocking: independent simulator clocks, no shared 10 MHz reference
Tracking: L5Q pilot robust, 20 Msps, ishort, B210 RX2 gain=40
Dense taps: -4:0.1:4 chips, decimation=1
```

NUC output directories:

```text
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay90m_ratio_m6db_run1_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay90m_ratio_m6db_run2_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay90m_ratio_m6db_run3_30s_0728
```

Capture quality:

```text
run1: record_overflow=0, dense_records=29799, loss_count=1, DUALPATH_OBS=0
run2: record_overflow=0, dense_records=29906, loss_count=0, DUALPATH_OBS=12, CNAV received with CN0=56 dB-Hz
run3: record_overflow=0, dense_records=29909, loss_count=0, DUALPATH_OBS=17, CNAV received with CN0=56 dB-Hz
```

Windowed fitter command pattern:

```text
python3 dev_notes/sim/fit_windowed_twosource.py --dense <run>/l5_phaseB_dense_ch_0.dat.json --kernel <PRN23_Aonly_kernel.csv> --chip-m 29.3 --delay-m 90 --ratio-db -6 --cn0-min 0 --lock-min -1 --min-lock-run 1000 --settle-epochs 200 --max-rot-deg 30 --max-delay-chips 4.0 --plot <run>/windowed_fit_prn23_delay90m_ratio_m6db_runN.png
```

Windowed fit results:

```text
run1: kept 29599 / 29799 records (99.3%), detected 22 / 23 windows
      recovered delay median=83.9 m, robust-std=0.7 m
      recovered ratio median=-5.58 dB, robust-std=0.74 dB
      relative phase span=347 deg

run2: kept 29706 / 29906 records (99.3%), detected 38 / 38 windows
      recovered delay median=84.1 m, robust-std=0.4 m
      recovered ratio median=-6.04 dB, robust-std=1.48 dB
      relative phase span=340 deg

run3: kept 29709 / 29909 records (99.3%), detected 8 / 10 windows
      recovered delay median=83.4 m, robust-std=0.2 m
      recovered ratio median=-10.91 dB, robust-std=4.46 dB
      relative phase span=300 deg
```

Codex judgment:

The +90 m check strongly suggests the previous +60 m discrepancy is mostly a
fixed calibration / path offset, not a proportional scale error. Comparison:

```text
Injected +60 m -> recovered about 52.8 m, error about -7.2 m
Injected +90 m -> recovered about 83.8 m, error about -6.2 m
Delta between recovered medians: about 31.0 m for a 30 m injected change
```

That incremental agreement is the important point. The absolute recovered delay
is shifted by roughly 6-7 m, but changing the simulator delay by +30 m changes
the fitted delay by about +31 m. Before a full Phase B grid, record this as a
calibration offset and avoid interpreting raw recovered delay as absolute truth
without same-cable/same-combiner calibration.

Drift-aware refit note:

After adding the independent-clock `delta(t)` linear model to
`fit_windowed_twosource.py`, I reprocessed the +60 m and +90 m captures. The
midpoint delay values were:

```text
+60 m run1: 52.8 m
+60 m run2: 51.2 m
+60 m run3: 50.8 m

+90 m run1: 84.0 m
+90 m run2: 84.1 m
+90 m run3: 83.6 m
```

The +90 m runs remain tightly grouped around 83.6-84.1 m. The +60 m runs show
more drift sensitivity, but the run-to-run paired change is still close to the
injected +30 m increment:

```text
run1: 84.0 - 52.8 = 31.2 m
run2: 84.1 - 51.2 = 32.9 m
run3: 83.6 - 50.8 = 32.8 m
```

This reinforces the practical interpretation: with independent simulator clocks,
absolute recovered delay includes an unknown clock/path offset, but relative
changes in commanded delay are being recovered at roughly the correct scale.
For the current A/B/combiner setup, do not use the raw recovered delay as an
absolute ground truth without calibration. Use same-session paired deltas or a
calibrated offset.

Next recommended calibration check:

Use one more easy point, e.g. +30 m or +120 m at the same -6 dB ratio. If the
same approximately -6 to -7 m offset remains, subtract it as an experiment
calibration term for this A/B/combiner setup. If the offset changes with delay,
then revisit the fitter model or simulator delay semantics.

-- Codex, 2026-07-28

## Phase B Resolution Targets + Drift-Aware Real-Data Interpretation

Date: 2026-07-28
Author: Claude (Opus 4.8)

AUTHORITATIVE definition of the Phase B goal (what "separate two same-code paths"
must achieve, quantitatively) plus the read on the first real drift-aware PRN23
30/60/90 m results. README's 🎯 block points here.

### Goal: quantitative sub-chip resolution targets (do the minimum first)

Minimum (current focus):

```text
Stably separate Δτ = 0.5 chip ≈ 14.7 m on real hardware.
Conditions: 2nd path ≥ -6 dB ; CN0 ≥ 43 dB-Hz ; multiple relative phases.
Pass bar:   detection success ≥ 90% ; false alarm ≤ 5% ; delay RMSE ≤ 0.1 chip.
Meaning:    the system has real sub-chip separation capability.
```

Stronger:

```text
Push to 0.3 chip ≈ 8.8 m ; cover a -10 dB 2nd path ; detectable at most phases ;
delay RMSE ≤ 0.05-0.1 chip ; clearly better than a fixed ideal-kernel MEDLL ;
emit confidence intervals AND failure warnings.
```

High-challenge / research:

```text
0.1-0.2 chip ≈ 2.9-5.9 m. NOT all conditions must succeed. The valuable output is an
HONEST map: which phases are separable, which power ratios are not, which results are
multi-solution, and how the algorithm flags "I am uncertain". In super-resolution,
reliably reporting "not separable" beats emitting a confident wrong second path.
```

### Real-data read: PRN23 30/60/90 m drift-aware summary

Source: `prn23_delay30_60_90_driftaware_summary.csv` (Codex). Separated delays,
independent simulator clocks, -6 dB injected.

```text
1. DELAY is robust. Midpoint 30->~24 m, 60->~51-53 m, 90->~84 m. recovered-vs-injected
   line slope ~= 1.00, fixed offset ~= -6.5 m. The delay SCALE is unbiased; the offset
   is fixed cable/combiner + a roughly-constant clock DC -> calibrate it out; use paired
   deltas for truth (a same-session +30 m change moves the fit +31-33 m).

2. AMPLITUDE RATIO is trustworthy ONLY with enough phase diversity. Good runs (many
   detecting windows) recover -5..-6 dB; degenerate runs give garbage (30-run2 = +8.23
   dB from 1 window; 90-run3 = -10.91 dB from 10 windows). Window count / phase coverage,
   not delay, decides amplitude trust.

3. The carrier<->code cross-check RATIO is NOT a reliable per-run metric (it ranged
   0.01..14.5). Root cause: at small delay the drift-probe tap sits under path0's main
   lobe, so the carrier-drift estimate is contaminated and the ratio blows up exactly in
   the merged regime we care about. DEMOTED: report it only for well-separated runs with
   measurable drift; print "not meaningful here" otherwise. (Corrects the earlier claim
   that ratio~=1 is a general clock-consistency proof -- it holds only for clean
   separated captures.)
```

Net: phase diversity is the discriminator between a trustworthy fit and a garbage one.

### Tool changes (fit_windowed_twosource.py) motivated by the above

```text
1. Phase-coverage report + delay-dependent GATE + per-capture VERDICT: for merged
   (sub-~1.3-chip) delays, require the detecting windows to sample enough of the phase
   circle (destructive interference must be seen); else flag UNRELIABLE/uncertain
   instead of emitting a number. This IS the false-alarm control the minimum tier needs
   and the "report not-separable" behaviour the research tier needs.
2. Theil-Sen robust delta(t) slope + IQR band (a confidence interval), replacing LS, so
   a few destructive-phase bad-fit windows cannot pull the drift line.
3. --diversity-selftest: on existing well-separated 60/90 m data, shrink the allowed
   phase arc and watch which metrics degrade -> defines "how much coverage is enough"
   offline, before spending hardware on 22/15 m.
```

Physical framing (see `09`): a single static antenna has no angular aperture, so two
same-code sub-chip paths are near-unidentifiable from amplitude alone. The
independent-clock phase sweep is the substitute for aperture -- catching the
destructive-interference phase is what resolves the merged pair. So for the sub-chip
experiment we WANT enough clock drift, and a capture whose phase does not sweep far
enough is genuinely under-determined (no tuning fixes it: capture longer, or prefer a
higher-drift run).

### Smoke-test result (synthetic) + the merged-amplitude caveat

Validated the three changes on physically-consistent synthetic captures (matched
kernel, injected clock drift so both carrier phase and code delay drift together):

```text
separated 60 m, full sweep: coverage 12/12, cross-check ratio 1.00 (meaningful),
    VERDICT RELIABLE, delay + ratio (-6 dB) recovered correctly.
merged 0.5 chip (14.7 m), slow drift: coverage 1/12 -> VERDICT UNRELIABLE
    (insufficient phase diversity) -- the gate correctly refuses to report.
merged 0.5 chip, FULL sweep: DELAY recovered correctly (drift-tracked midpoint 17 m),
    but AMPLITUDE ratio came out -12 dB for an injected -6 dB.
```

Caveat found, now flagged in the tool: in the merged regime the per-epoch tap0
normalization mixes path1 into the reference (`tap0 = path0 + path1*K(delta)`, with
`K(0.5 chip) ~= 0.7`), which BIASES the amplitude ratio even at full phase coverage.
The DELAY stays correct. So for the minimum target (0.5 chip, delay RMSE) the windowed
method works; the merged-regime amplitude is NOT yet trustworthy. The verdict now prints
"RELIABLE delay ... amplitude BIASED in merged regime" instead of a false clean RELIABLE.

Next algorithm step (separate, focused -- do NOT rush into this change): in the merged
regime, replace the per-epoch tap0 division with a per-window estimate that does not use
a contaminated path0 reference -- e.g. coherent-average the carrier-wiped taps per window
(path0's residual phase is ~constant within a ~30 ms window) and let the two-path fit
recover complex c0/c1 directly, after verifying intra-window residual phase is small.
Validate on synthetic + the real 14.7 m capture before trusting any merged amplitude.

-- Claude (Opus 4.8), 2026-07-28

## Phase B A+B Composite - PRN23 30m -6dB Near-Resolution Check

Date: 2026-07-28

Author: Codex

User changed the B simulator delay compensation from +90 m to +30 m. Other
conditions were kept the same:

```text
A simulator: on, GPS L5 PRN23, single-satellite amplitude=64, L5 output=-50 dBm, delay compensation=0 m
B simulator: on, GPS L5 PRN23, single-satellite amplitude=64, L5 output=-56 dBm, delay compensation=+30 m
Combiner: A/B combined into B210 RX2
Clocking: independent simulator clocks, no shared 10 MHz reference
Tracking: L5Q pilot robust, 20 Msps, ishort, B210 RX2 gain=40
Dense taps: -4:0.1:4 chips, decimation=1
```

NUC output directories:

```text
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay30m_ratio_m6db_run1_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay30m_ratio_m6db_run2_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay30m_ratio_m6db_run3_30s_0728
```

Capture quality:

```text
run1: record_overflow=0, dense_records=29906, loss_count=0, DUALPATH_OBS=14
run2: record_overflow=0, dense_records=29878, loss_count=0, DUALPATH_OBS=14
run3: record_overflow=0, dense_records=29896, loss_count=0, DUALPATH_OBS=18
```

This is a near-resolution test. For L5, 30 m is about 1.02 chips and is close to
the measured single-source FWHM (~32 m), so the two sources are expected to fuse
into one broadened/asymmetric main lobe more often than the +60 m and +90 m
cases.

Windowed fit results with the standard probe (`delay_m / chip_m`, about 1 chip):

```text
run1: mag_mean secondary peak=0.80 chip / 23.4 m
      detected 18 / 21 windows
      recovered midpoint delay=23.6 m, median ratio=-6.03 dB

run2: mag_mean secondary peak=0.90 chip / 26.4 m
      auto drift estimate collapsed to one whole-record window
      recovered delay=14.4 m, ratio=+8.23 dB
      judgment: not reliable under the standard auto-window choice

run3: mag_mean secondary peak=0.90 chip / 26.4 m
      detected 19 / 20 windows
      recovered midpoint delay=24.6 m, median ratio=-8.46 dB
```

Extra probe sensitivity check for run2:

```text
probe=0.7 chip: detected 4 / 5 windows, recovered midpoint=22.2 m, ratio=-6.96 dB
probe=0.8 chip: detected 2 / 4 windows, recovered midpoint=24.5 m, ratio=-11.72 dB
probe=1.2 chip: detected 8 / 9 windows, recovered midpoint=25.1 m, ratio=-11.17 dB
```

Codex judgment:

The +30 m case is detectable, but it is no longer as stable as +60 m and +90 m.
Runs 1 and 3 recover a second source around 23-25 m, which matches the previously
observed fixed calibration offset scale:

```text
Injected +30 m -> recovered about 24 m, error about -6 m
Injected +60 m -> recovered about 51-53 m, error about -7 to -9 m
Injected +90 m -> recovered about 84 m, error about -6 m
```

So the current method can separate roughly 1-chip L5 two-source cases under this
high-CN0, -6 dB, PRN23 condition, but +30 m should be marked as a lower-confidence
near-boundary point. At this spacing, model/probe/window choices and phase state
matter more, and amplitude ratio is less stable than at +60/+90 m.

Practical implication:

For Phase B grid expansion, use +60 m and +90 m as stable positive controls, and
use +30 m as the first near-resolution stress point. Do not yet claim sub-chip
separation from this data. The next meaningful stress points are +22 m and +15 m
only after the window selection/fitter robustness is improved and benchmarked
against +30 m.

-- Codex, 2026-07-28

## Phase B Drift-Aware Refit - PRN23 30/60/90m Calibration Line

Date: 2026-07-28

Author: Codex

User requested a no-new-capture refit of the existing PRN23 +30/+60/+90 m
Phase B composite captures using the drift-aware windowed fitter. Goal:

```text
1. Extract each run's recovered midpoint delay and carrier<->code drift ratio.
2. Fit recovered-vs-injected to estimate scale and fixed calibration offset.
```

Input data:

```text
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay30m_ratio_m6db_run{1,2,3}_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay60m_ratio_m6db_run{1,2,3}_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay90m_ratio_m6db_run{1,2,3}_30s_0728
```

Same-PRN kernel:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run3_30s_0728/aonly_reference_Rtau.png.csv
```

Per-run summary CSV:

```text
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn23_delay30_60_90_driftaware_summary.csv
```

Per-run refit table:

```text
inj_m  run  midpoint_m  carrier_code_ratio  detected_windows  amp_ratio_db  quality
30     1    23.6        4.47                18/21             -6.03         OK
30     2    14.4        NA                  1/1               +8.23         reject: too_few_windows,bad_amp_ratio
30     3    24.6        14.52               19/20             -8.46         OK

60     1    52.8        0.62                99/99             -5.29         OK
60     2    51.2        7.73                18/21             -7.03         OK
60     3    50.8        0.01                739/2462          -5.35         weak: low_detect_fraction

90     1    84.0        1.59                22/23             -5.58         OK
90     2    84.1        0.18                38/38             -6.04         OK
90     3    83.6        5.45                8/10              -10.91        OK but amp weak
```

Calibration fit using all condition medians:

```text
condition medians:
30 m -> 23.6 m
60 m -> 51.2 m
90 m -> 84.0 m

recovered = 1.0067 * injected - 7.467 m
residuals = [0.867, -1.733, 0.867] m
```

Calibration fit using primary-quality condition medians
(rejecting the obvious +30 m run2 failure and the weak +60 m run3 from the
primary calibration pool):

```text
condition medians:
30 m -> 24.1 m
60 m -> 52.0 m
90 m -> 84.0 m

recovered = 0.9983 * injected - 6.533 m
residuals = [0.683, -1.367, 0.683] m
```

Codex judgment:

The recovered-vs-injected calibration is strong: slope is approximately 1.0 and
the intercept is approximately -6.5 to -7.5 m. This supports the earlier
interpretation that the dominant absolute-delay discrepancy is a fixed
experiment calibration offset for this A/B/combiner/session, not a scale error
in the fitter.

However, the per-run `carrier<->code ratio` values are mixed and should not be
overstated. Only some runs are near ratio~1. Several runs have poor ratio values
because drift estimation becomes unreliable when the probe tap is weak, the
relative phase is almost static over 30 s, or the near-resolution +30 m case
collapses into too few useful windows. Therefore, the current evidence does not
prove that every run's offset is purely clock-induced. The safer statement is:

```text
Scale is validated by the 30/60/90 m calibration line.
Absolute offset is real for this setup and should be calibrated out.
Carrier<->code ratio is a useful diagnostic, but not yet a hard acceptance gate.
```

Operational calibration for this session:

```text
true_delay_m ~= recovered_midpoint_m + 6.5 m
```

Use that only for this PRN23, A/B/combiner, independent-clock session until a
new baseline calibration is made.

-- Codex, 2026-07-28

## Phase B PRN Switch - PRN28 A-Only Baseline 30s x3

Date: 2026-07-28

Author: Codex

User reported that PRN23 elevation had dropped to about 9 deg, so we switched
the next Phase B target to PRN28 (about 65 deg elevation at the time of the
screenshot). User configured:

```text
A simulator: on, GPS L5 PRN28, L5 output=-50 dBm, delay compensation=0 m
B simulator: off
single-satellite amplitude=64
Combiner / B210 RX2 chain unchanged
```

Capture / processing settings:

```text
GPS L5Q pilot
20 Msps
sc16 / ishort raw
B210 RX2
gain=40
dense taps=-4:0.1:4 chips
dense decimation=1
robust L5Q lock counters enabled
strict reference selection: cn0>=45, lock>=0.6, min-lock-run=2000, settle=200
```

NUC output directories:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn28_l5m50_amp64_run1_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn28_l5m50_amp64_run2_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn28_l5m50_amp64_run3_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn28_l5m50_amp64_run4_30s_0728
```

Capture / check results:

```text
run1: record_overflow=0, loss_count=1, kept=5510 records (18.5%), asym=0.0307, SEM_block=0.00062
run2: record_overflow=0, loss_count=1, kept=0 records, rejected (no sustained lock segment)
run3: record_overflow=0, loss_count=1, kept=6444 records (21.7%), asym=0.0312, SEM_block=0.00056
run4: record_overflow=0, loss_count=1, kept=26984 records (90.8%), asym=0.0317, SEM_block=0.00027
```

Formal PRN28 A-only aggregate used run1/run3/run4:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/prn28_aonly_baseline_30s_x3_coherent.log
/home/bupt/lya/gnss_data/phaseB_l5_baseline/prn28_aonly_baseline_30s_x3_coherent.png
```

Aggregate result:

```text
VERDICT: TRUSTWORTHY (reproducible across runs) [precision: OK]
FWHM = 1.0911 chips = 31.97 m, std=0.01 m
asym_max = 0.0312 +/- 0.0004
peak_chip = -0.0054 chip
min n_blocks = 1102
worst SEM_block = 0.00062
kept_fraction mean=44%, min=19% (tracking churn indicator, not a quality gate)
```

Codex judgment:

PRN28 now has a valid same-PRN A-only kernel for Phase B. The repeated
single-source shape is reproducible and its FWHM matches the Phase A L5 library
(about 32 m). The downside is recurring L5Q tracking churn near 22 s; it did not
prevent kernel extraction, but it should be expected in later PRN28 B-only/A+B
runs and must be handled by the same strict window/lock selection.

PRN28 run2 is rejected and should not be used for kernel fitting.

Recommended next step:

Collect PRN28 B-only for the intended delay point, then PRN28 A+B. Keep all
settings identical to this A-only baseline so the kernel remains comparable.

-- Codex, 2026-07-28

## Phase B PRN28 B-Only Baseline - Delay 30m 30s x3

Date: 2026-07-28

Author: Codex

User configured PRN28 B-only. I assumed the B simulator kept the current Phase B
delay setting of +30 m and L5 output -56 dBm:

```text
A simulator: off
B simulator: on, GPS L5 PRN28, single-satellite amplitude=64, L5 output=-56 dBm, delay compensation=+30 m
Combiner / B210 RX2 chain unchanged
```

Capture / processing settings:

```text
GPS L5Q pilot
20 Msps
sc16 / ishort raw
B210 RX2
gain=40
dense taps=-4:0.1:4 chips
dense decimation=1
robust L5Q lock counters enabled
strict reference selection: cn0>=45, lock>=0.6, min-lock-run=2000, settle=200
```

NUC output directories:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn28_l5m56_delay30m_run1_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn28_l5m56_delay30m_run2_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn28_l5m56_delay30m_run3_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn28_l5m56_delay30m_run4_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn28_l5m56_delay30m_run5_30s_0728
```

Run quality:

```text
run1: record_overflow=0, loss_count=1, kept=3929 records (13.2%), asym=0.0264, SEM_block=0.00105
run2: record_overflow=0, loss_count=1, kept=24206 records (81.5%), asym=0.0277, SEM_block=0.00041
run3: record_overflow=0, loss_count=1, kept=0 records, rejected (no sustained lock segment)
run4: record_overflow=0, loss_count=1, kept=22311 records (75.0%), asym=0.0276, SEM_block=0.00406, rejected from formal baseline because n_blocks=16 / SEM too high
run5: record_overflow=0, loss_count=1, kept=2644 records (8.9%), asym=0.0282, SEM_block=0.00118
```

Formal PRN28 B-only aggregate used run1/run2/run5:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/prn28_bonly_delay30m_baseline_30s_x3_coherent.log
/home/bupt/lya/gnss_data/phaseB_l5_baseline/prn28_bonly_delay30m_baseline_30s_x3_coherent.png
```

Aggregate result:

```text
VERDICT: TRUSTWORTHY (reproducible across runs) [precision: OK]
FWHM = 1.0997 chips = 32.22 m, std=0.02 m
asym_max = 0.0275 +/- 0.0008
peak_chip = -0.0045 chip
min n_blocks = 661
worst SEM_block = 0.00118
kept_fraction mean=35%, min=9% (tracking churn indicator, not a quality gate)
```

Codex judgment:

PRN28 now has a valid B-only same-source baseline for the +30 m delay condition.
The B-only shape is reproducible, with FWHM close to the PRN28 A-only baseline
and a slightly lower asymmetry:

```text
PRN28 A-only: FWHM=31.97 m, asym=0.0312
PRN28 B-only: FWHM=32.22 m, asym=0.0275
```

The recurring single loss/reacquisition near 22 s remains visible, but strict
selection leaves enough clean epochs for a trustworthy baseline. Run3 and run4
should not be used in formal baseline calculations.

Recommended next step:

Collect PRN28 A+B at the same +30 m / -6 dB condition, then use the PRN28 A-only
kernel for windowed two-source fitting. Because +30 m is a near-resolution point,
expect lower confidence than +60/+90 m and check window/probe sensitivity.

-- Codex, 2026-07-28

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

## Phase A L5 Library - Canonical Coherent Re-Aggregation for All 4 Tiers

Date: 2026-07-28

Author: Codex

Claude re-audited the Phase A L5 library and found that older aggregate logs for
CN0 40, 45, and 56 were still based on magnitude-averaged shapes. Accepted. To
remove ambiguity, all four formal tiers were re-aggregated again with explicit
coherent shape selection and canonical output filenames:

```text
shape option: --shape-from coherent
temporary script on NUC: /tmp/aggregate_reference_fingerprint_coherent.py
data root: /home/bupt/lya/gnss_data/phaseA_l5_grid
```

Canonical coherent results:

```text
tier label  PRN   measured CN0 note    verdict        FWHM chips          FWHM meters        asym_max
cn040       5     39.7                 TRUSTWORTHY    1.0884 +/- 0.0008  31.89 +/- 0.02 m  0.0136 +/- 0.0020
cn043       20    42-45, mean ~=43     TRUSTWORTHY    1.0960 +/- 0.0015  32.11 +/- 0.04 m  0.0336 +/- 0.0008
cn052       15    51.7                 TRUSTWORTHY    1.0905 +/- 0.0001  31.95 +/- 0.00 m  0.0171 +/- 0.0003
cn057       11    57.0                 TRUSTWORTHY    1.0916 +/- 0.0002  31.98 +/- 0.01 m  0.0334 +/- 0.0000
```

Canonical files:

```text
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn040_prn5_30s_group_coherent_canonical.log
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn040_prn5_30s_group_coherent_canonical.png
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn043_prn20_30s_group_coherent_canonical.log
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn043_prn20_30s_group_coherent_canonical.png
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn052_prn15_30s_group_coherent_canonical.log
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn052_prn15_30s_group_coherent_canonical.png
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn057_prn11_30s_group_coherent_canonical.log
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn057_prn11_30s_group_coherent_canonical.png
```

Judgment:

These canonical coherent values supersede all older magnitude-shape aggregate
FWHM/asym values in this document. The earlier apparent broadening from roughly
32 m to 35 m at low CN0 was mostly a magnitude-average noise-pedestal artifact,
not a physical widening of the clean L5 correlation kernel. Under coherent
aggregation, the L5 clean-path reference width is stable at about 31.9-32.1 m
across the current measured-CN0 library.

The CN0 45 target tier should be labeled by measured CN0 as `cn043`, not as a
literal CN0 45 tier, because its three runs span roughly 42-45 dB-Hz. The current
library therefore covers measured CN0 approximately:

```text
39.7 / 43 / 51.7 / 57.0 dB-Hz
```

There is still a coverage gap between 43 and 52 dB-Hz. Filling a measured
47-48 dB-Hz tier is optional before Phase B; it would make the CN0 grid more
uniform, but the current four tiers are already TRUSTWORTHY.

-- Codex, 2026-07-28

## Phase B B-Only Baseline - PRN23 Delay 60m 30s x3

Date: 2026-07-28

Author: Codex

User configured B-only:

```text
A simulator off
B simulator on
PRN=23
B L5 output label=-56
B pseudorange compensation=+60 m
single-satellite amplitude=64
B210 RX2
```

Configuration used for processing:

```text
L5Q pilot
robust lock counters enabled:
  carrier_lock_th=0.55
  max_lock_fail=300
  max_carrier_lock_fail=20000
sample rate=20 Msps
sample type=sc16 / ishort
dense taps=-4:0.1:4 chips
dense decimation=1
```

Raw captures:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn23_l5m56_delay60m_run1_raw_30s_0728/raw_bonly_prn23_run1_20m_30s_ishort.dat
/home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn23_l5m56_delay60m_run2_raw_30s_0728/raw_bonly_prn23_run2_20m_30s_ishort.dat
/home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn23_l5m56_delay60m_run3_raw_30s_0728/raw_bonly_prn23_run3_20m_30s_ishort.dat
/home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn23_l5m56_delay60m_run4_raw_30s_0728/raw_bonly_prn23_run4_20m_30s_ishort.dat
```

All raw recordings had:

```text
record_overflow=0
```

Strict extraction summary:

```text
run  kept records  kept fraction  n_blocks  SEM_block_worst  asym(check)  status
1    7394          24.9%          1848      0.00058          0.0227       usable
2    0             0.0%           -         -                -            rejected; no sustained segment >=2000
3    25331         84.8%          6332      0.00031          0.0235       usable
4    3374          11.3%          843       0.00083          0.0233       usable retry
```

Run2 was not used for aggregate statistics because no sustained locked segment
survived the strict selector.

Aggregate command:

```bash
python3 /tmp/aggregate_reference_fingerprint_coherent.py /home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn23_l5m56_delay60m_run1_30s_0728/bonly_reference_Rtau.png.csv /home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn23_l5m56_delay60m_run3_30s_0728/bonly_reference_Rtau.png.csv /home/bupt/lya/gnss_data/phaseB_l5_baseline/bonly_prn23_l5m56_delay60m_run4_30s_0728/bonly_reference_Rtau.png.csv --labels prn23_bonly,prn23_bonly,prn23_bonly --chip-m 29.3 --shape-from coherent --plot /home/bupt/lya/gnss_data/phaseB_l5_baseline/prn23_bonly_delay60m_baseline_30s_x3_coherent.png
```

Aggregate result:

```text
VERDICT: TRUSTWORTHY (reproducible across runs) [precision: OK]
peak_chip=-0.0041 +/- 0.0002 chips (-0.12 +/- 0.01 m)
FWHM=1.1151 +/- 0.0001 chips (32.67 +/- 0.00 m)
asym_max=0.0232 +/- 0.0003
noise_floor=0.0132 +/- 0.0000
tap_std_mean=0.0349 +/- 0.0001
min n_blocks=843
worst SEM_block=0.00083
FWHM CV=0.01%
kept_fraction mean=40%, min=11%
```

Saved aggregate outputs:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/prn23_bonly_delay60m_baseline_30s_x3_coherent.log
/home/bupt/lya/gnss_data/phaseB_l5_baseline/prn23_bonly_delay60m_baseline_30s_x3_coherent.png
```

Judgment:

PRN23 now has both formal same-PRN baselines:

```text
A-only:  PRN23, delay=0,    TRUSTWORTHY, FWHM=32.48 m, asym=0.0263
B-only:  PRN23, delay=60 m, TRUSTWORTHY, FWHM=32.67 m, asym=0.0232
```

B-only run2 was unstable and excluded, but run1/run3/run4 form a reproducible
three-run baseline. The next capture should be the actual A+B PRN23 composite at
`delay_m=60`, `power_ratio_db=-6`, with the same robust-lock and dense settings.

-- Codex, 2026-07-28

## Discussion - Phase B Next Capture After PRN23 Baseline

Date: 2026-07-28

Author: Codex

Claude reviewed the PRN10/23 A-only baseline work and suggested three actions.

Codex correction:

The A-only kernel CSVs were already generated after the initial read-only dense
inspection. They are named:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn10_l5m50_amp64_run1_30s_0728/aonly_reference_Rtau.png.csv
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run1_30s_0728/aonly_reference_Rtau.png.csv
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run2_30s_0728/aonly_reference_Rtau.png.csv
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run3_30s_0728/aonly_reference_Rtau.png.csv
```

PRN23 was also aggregated as `30 s x3`:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/prn23_aonly_baseline_30s_x3_coherent.log
/home/bupt/lya/gnss_data/phaseB_l5_baseline/prn23_aonly_baseline_30s_x3_coherent.png
```

Accepted adjustments:

```text
1. B-only should be mandatory, not optional, for the first serious Phase B point.
   It gives an independent truth check for the delayed simulator and confirms
   that the +60 m setting is actually visible as the delayed source before A+B
   fitting.
2. A-only, B-only, and A+B must use identical tracking/dense settings.
3. Metadata must not claim "robust" unless the config actually uses the robust
   lock-counter options, or the same options must be added consistently.
```

Next capture order:

```text
Selected PRN: 23
Reason: currently high elevation and now has a formal same-PRN A-only baseline.

Step 1 already done:
  A-only, PRN23, L5=-50, delay=0, 30 s x3

Step 2 next:
  B-only, PRN23, A off, B on, L5=-56, delay=+60 m, 30 s x3

Step 3 after B-only passes:
  A+B, PRN23, A L5=-50 delay=0, B L5=-56 delay=+60 m, 30 s x3

Step 4 after the 60 m / -6 dB point is analyzed:
  A+B, PRN23, delay=29 m, power_ratio=-6 dB, 30 s x3
  A+B, PRN23, delay=60 m, power_ratio=0 dB, 30 s x3
```

Analysis rule:

```text
A-only and B-only single-source data may use whole-selected-segment coherent
averaging to build same-PRN kernels.

A+B data must not use a full 30 s coherent average because the two simulators
have independent clocks. Use windowed coherent profiles, then fit_two_path.py.
```

Open implementation detail before the next capture:

Confirm whether `make_l5_dualpath_conf.py` supports the robust lock options used
earlier (`carrier_lock_th`, `max_lock_fail`, `max_carrier_lock_fail`) and either:

```text
Option A: add them consistently to A-only / B-only / A+B configs; or
Option B: remove "robust" from condition.json labels for these Phase B captures.
```

The correlation shape is not changed by lock-counter robustness, but kept
fraction and metadata accuracy matter for reproducible Phase B experiments.

-- Codex, 2026-07-28

## Phase B A-Only Baseline Repeat - PRN23 30s x3

Date: 2026-07-28

Author: Codex

User correctly pointed out that a formal same-PRN baseline should follow the
same repeat discipline as the Phase A library: `>=3` captures, each `>=30 s`,
then aggregate for reproducibility. The earlier PRN23 run1 was only a candidate,
not a formal baseline tier by itself.

Added two more PRN23 A-only captures under the same condition:

```text
B simulator off
A simulator on
PRN=23
single-satellite amplitude=64
L5 output label=-50
B210 gain=40 dB
sample rate=20 Msps
sample type=sc16 / ishort
dense taps=-4:0.1:4 chips
dense decimation=1
```

New raw captures:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run2_raw_30s_0728/raw_aonly_prn23_run2_20m_30s_ishort.dat
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run3_raw_30s_0728/raw_aonly_prn23_run3_20m_30s_ishort.dat
```

Both recorded with:

```text
record_overflow=0
```

Per-run strict extraction:

```text
run  kept records  kept fraction  n_segments_kept  n_blocks  SEM_block_worst  asym(check)  tracking note
1    12374         41.8%          1                100       0.00209          0.0258       earlier candidate run
2    20120         67.6%          2                4024      0.00048          0.0276       loss/reacq near 22 s, then stable
3    23770         79.5%          1                5942      0.00034          0.0254       stable DUALPATH_OBS, CN0 ~=53
```

Aggregate command:

```bash
python3 /tmp/aggregate_reference_fingerprint_coherent.py /home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run1_30s_0728/aonly_reference_Rtau.png.csv /home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run2_30s_0728/aonly_reference_Rtau.png.csv /home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run3_30s_0728/aonly_reference_Rtau.png.csv --labels prn23,prn23,prn23 --chip-m 29.3 --shape-from coherent --plot /home/bupt/lya/gnss_data/phaseB_l5_baseline/prn23_aonly_baseline_30s_x3_coherent.png
```

Aggregate result:

```text
VERDICT: TRUSTWORTHY (reproducible across runs) [precision: SEM above interim target]
peak_chip=-0.0058 +/- 0.0017 chips (-0.17 +/- 0.05 m)
FWHM=1.1084 +/- 0.0020 chips (32.48 +/- 0.06 m)
asym_max=0.0263 +/- 0.0010
noise_floor=0.0129 +/- 0.0006
tap_std_mean=0.0455 +/- 0.0059
min n_blocks=100
worst SEM_block=0.00209
FWHM CV=0.18%
kept_fraction mean=63%, min=42%
```

Saved aggregate outputs:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/prn23_aonly_baseline_30s_x3_coherent.log
/home/bupt/lya/gnss_data/phaseB_l5_baseline/prn23_aonly_baseline_30s_x3_coherent.png
```

Judgment:

PRN23 now satisfies the formal baseline repeat requirement (`30 s x3`) and passes
TRUSTWORTHY by cross-run reproducibility. Precision is weaker than ideal because
run1 has only `n_blocks=100`, so if PRN23 becomes the main Phase B PRN, prefer
the aggregate kernel but keep the precision warning visible. If time/storage
allows, a future run4 could replace run1 and likely improve the precision tag.

Operational correction:

For any PRN selected for Phase B fitting, the formal same-PRN A-only baseline
should be collected as `30 s x3`, not just a single 30 s capture, unless the
capture is explicitly labeled as a quick candidate/sanity baseline.

-- Codex, 2026-07-28

## Phase B A-Only Baseline Capture - PRN10 and PRN23

Date: 2026-07-28

Author: Codex

User configured A-only state:

```text
B simulator off
A simulator on
active candidate PRNs: 10 and 23
single-satellite amplitude=64
L5 output label=-50
B210 RX2
```

One shared raw capture was recorded and then processed separately for PRN10 and
PRN23:

```text
raw directory: /home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn10_23_l5m50_amp64_30s_0728
raw file: raw_aonly_prn10_23_20m_30s_ishort.dat
raw size: 2.3 GB
record_overflow=0
sample rate=20 Msps
sample type=sc16 / ishort
```

Per-PRN processing directories:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn10_l5m50_amp64_run1_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run1_30s_0728
```

Both were processed with:

```text
L5Q pilot robust
dense taps=-4:0.1:4 chips
dense decimation=1
```

Tracking notes:

```text
PRN10: tracking started, loss/reacquisition around 9 s and 17 s, secondary code
       locked around 20 s, DUALPATH_OBS appeared near the end with CN0 ~=54 dB-Hz.
PRN23: tracking started, loss/reacquisition around 9 s and 17 s, no DUALPATH_OBS
       in the 30 s log, but dense dump was produced.
```

Dense dump validation:

```text
PRN10: records=29597, tap_count=81, tap span=-4..+4 chips
PRN23: records=29608, tap_count=81, tap span=-4..+4 chips
```

Strict baseline extraction:

```text
PRN   kept records  kept fraction  n_segments_kept  n_blocks  SEM_block_worst  asym(check)
10    11331         38.3%          1                2832      0.00041          0.0321
23    12374         41.8%          1                100       0.00209          0.0258
```

Generated single-source baseline files:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn10_l5m50_amp64_run1_30s_0728/aonly_reference_Rtau.png.csv
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn10_l5m50_amp64_run1_30s_0728/aonly_reference_Rtau.png
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run1_30s_0728/aonly_reference_Rtau.png.csv
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn23_l5m50_amp64_run1_30s_0728/aonly_reference_Rtau.png
```

Judgment:

PRN10 is the better Phase B candidate from this A-only capture. It has a clean
post-reacquisition baseline segment with many independent blocks and good SEM.
PRN23 can produce a reference profile, but its effective independent sample count
is much lower (`n_blocks=100`) and SEM is above the Phase A interim target; use it
only if PRN10 becomes unavailable or if a repeat PRN23 baseline improves.

Because both PRNs show early loss/reacquisition at roughly 9 s and 17 s, the
baseline profiles are usable only after strict sustained-lock selection. Do not
use full-record averaging for these A-only baselines.

-- Codex, 2026-07-28

## Discussion - Phase B Batch Capture Strategy

Date: 2026-07-28

Author: Codex

User asked whether more Phase B data should be collected now, preferably in one
batch.

Codex position:

Do not immediately collect the full Phase B grid before the independent-clock
analysis path is validated. The current Phase B setup has no shared 10 MHz
reference, so the relative phase between the two simulators can drift inside a
30 s capture. That means a full-record coherent average can suppress the delayed
source; Phase B analysis must use short windows before `fit_two_path.py`.

The safe strategy is:

```text
1. Collect a small but complete Phase B validation package.
2. Run the windowed dense-profile exporter and fit_two_path.py on that package.
3. Once delay/power recovery works on known truth, collect the full grid in one
   batch with the validated settings.
```

Recommended validation package under the current PRN15 / L5Q / 20 Msps setup:

```text
same-PRN single-source baseline:
  A-only, PRN15, L5=-50, delay=0, 30 s x1 or x3

optional source sanity:
  B-only, PRN15, L5=-56, delay=+60 m, 30 s x1

two-source composites:
  delay_m=60, power_ratio_db=-6, 30 s x3
  delay_m=29, power_ratio_db=-6, 30 s x3
  delay_m=60, power_ratio_db=0,  30 s x3
```

Why these three two-source points:

```text
60 m / -6 dB: easiest already-started point; validates non-equal power recovery.
29 m / -6 dB: about one L5 chip; begins testing the practical resolution wall.
60 m / 0 dB: equal-power DAS case; harder but important.
```

Full-grid collection should wait until this validation package proves that the
window length, dense tap span, and fitter configuration are correct. The full
grid from the SOP is large:

```text
delay_m={6,9,15,22,29,44,60,90}
power_ratio_db={0,-3,-6,-10}
repeats=3
=> 96 two-source captures, about 220 GB raw IQ at 30 s / 20 Msps / sc16,
   plus dense dumps and logs.
```

Full-grid capture is worthwhile after the analysis chain is validated, but it
should not be the first thing collected under independent clocks.

-- Codex, 2026-07-28

## Phase B First Two-Source Composite Capture - PRN15, 60 m, -6 dB

Date: 2026-07-28

Author: Codex

User configured two simulators through a reversed splitter into B210 RX2:

```text
Simulator A / primary:
  GPS L5 active, PRN list visible in UI
  single-satellite amplitude=64
  L5 output label=-50
  pseudorange compensation=0 m

Simulator B / second source:
  GPS L5 active, same visible PRN list
  single-satellite amplitude=64
  L5 output label=-56
  pseudorange compensation=+60 m

Clocking:
  no shared 10 MHz reference; simulators are independent-clock sources

RF chain:
  A/B combined by reversed splitter
  combiner output connected to B210 RX2
  B210 gain=40 dB
  sample rate=20 Msps
  sample type=sc16 / ishort
```

Important acquisition note:

I initially attempted PRN11 because it is a strong Phase A reference PRN, but the
user screenshots for the active Phase B simulator state did not include PRN11.
That offline pass produced no tracking and a zero-length dense binary. The raw
recording itself was still valid and contained the currently active PRNs, so I
reprocessed the same raw as PRN15.

Raw composite recording:

```text
/home/bupt/lya/gnss_data/phaseB_l5_twosource/l5_prn11_delay60m_ratio_m6db_run1_30s_0728/raw_prn11_20m_30s_ishort.dat
size=2.3 GB
record_overflow=0
```

Successful PRN15 Phase B processing directory:

```text
/home/bupt/lya/gnss_data/phaseB_l5_twosource/l5_prn15_delay60m_ratio_m6db_run1_30s_0728
```

`raw_prn15_20m_30s_ishort.dat` in that directory is a symlink to the original
raw capture above, avoiding a second 2.3 GB copy.

Condition metadata:

```text
phase=B
band=L5
PRN=15
delay_m=60
power_ratio_db=-6
run=1
clock_mode=independent
dense taps=-4:0.1:4 chips
dense decimation=1
```

Offline GNSS-SDR config was generated with:

```bash
python3 dev_notes/sim/make_l5_dualpath_conf.py --source file --input <raw> --sample-type ishort --output <conf> --rate 20000000 --prns 15 --single-path --track-pilot --scenario cable --blocking true --enable-dense-correlator --dense-taps=-4:0.1:4 --dense-decimation 1 --dense-dump-prefix <out>/l5_phaseB_dense_ch_
```

Tracking result:

```text
Tracking of GPS L5Q signal started on channel 0 for satellite GPS PRN 15
GPS L5Q secondary code locked in channel 0
No loss-of-lock reported during the 30 s offline pass
DUALPATH_OBS CN0 ~=52.5-53.5 dB-Hz
```

Dense dump validation:

```text
dense binary: /home/bupt/lya/gnss_data/phaseB_l5_twosource/l5_prn15_delay60m_ratio_m6db_run1_30s_0728/l5_phaseB_dense_ch_0.dat
dense json:   /home/bupt/lya/gnss_data/phaseB_l5_twosource/l5_prn15_delay60m_ratio_m6db_run1_30s_0728/l5_phaseB_dense_ch_0.dat.json
records=29909
record_size=724 bytes
tap_count=81
tap span=-4.000 .. +4.000 chips
signal=GPS L5
channel=0
decimation=1
fs=20 MHz
last-epoch plot=/home/bupt/lya/gnss_data/phaseB_l5_twosource/l5_prn15_delay60m_ratio_m6db_run1_30s_0728/dense_epoch_last.png
```

Judgment:

This is the first successful Phase B two-source composite dense capture. Because
the two simulators do not share a 10 MHz reference, do not interpret a 30 s
coherent average as a valid two-source profile: the relative phase can drift and
average out the delayed component. The data should be analyzed with short
windows (roughly 10-50 ms) before calling `fit_two_path.py`. The capture itself
is valid and wide enough for the requested 60 m delay because the dense tap span
was widened to `-4:0.1:4` chips.

Next analysis task:

Add or use a windowed dense-profile exporter:

```text
input: l5_phaseB_dense_ch_0.dat.json
window length: start with 20 ms and 50 ms
output: one coherent R(tau) CSV per window, or selected high-SNR windows
then: fit_two_path.py --kernel <PRN15 single-source kernel> --observed <window CSV>
truth: delay_m=60, power_ratio_db=-6
```

-- Codex, 2026-07-28

## Discussion - Phase A L5 Canonical Library Interpretation

Date: 2026-07-28

Author: Codex

Claude reviewed the canonical coherent Phase A L5 library:

```text
tier   PRN   measured CN0  FWHM m  asym
cn040  5     39.7          31.89   0.0136
cn043  20    ~=43          32.11   0.0336
cn052  15    51.7          31.95   0.0171
cn057  11    57.0          31.98   0.0334
```

Codex position:

I agree with the main conclusion: coherent aggregation flattened the L5 main-lobe
width to about `31.9-32.1 m` across the measured-CN0 range. The old low-CN0
`~35 m` width was a magnitude-average noise-pedestal artifact, not a physical
widening of the clean L5 correlation kernel. The measured width is also
physically plausible: ideal L5 chip length is about `29.3 m`, and the observed
extra width is consistent with the finite 20 MHz front-end / sampling chain.

Important boundary:

The stable FWHM supports using a common L5 main-lobe width model for Phase B, but
it does not prove every PRN has identical full correlation shape. The observed
asymmetry is PRN-dependent:

```text
low-asym group:  PRN5, PRN15  ~=0.014-0.017
high-asym group: PRN20, PRN11 ~=0.033-0.034
```

Therefore:

```text
1. For detection by "departure from clean single-source asymmetry", use a
   same-PRN baseline whenever possible. Do not use one global asymmetry threshold.
2. For MEDLL/two-source fitting, prefer the same-PRN single-source coherent
   R(tau) as the kernel when available.
3. A canonical/common L5 kernel is acceptable as a fallback or first
   implementation, but results should carry the PRN/kernel provenance.
```

Next algorithm step:

Start offline two-source fitting before more hardware work blocks progress. The
first implementation should be a reversible analysis tool, not tracking/PVT
logic:

```text
dev_notes/sim/fit_two_path.py
input: dense/reference R(tau) CSV and an observed dense R(tau)
model: A0 * R(tau - tau0) + A1 * R(tau - tau1) * exp(j*phi)
output: tau0, tau1, delta_m, amplitude ratio dB, relative phase, residual
first validation: synthetic two-source profiles injected from the measured
                  coherent single-source kernel, then recover known delay /
                  ratio / phase.
```

Phase B capture reminders:

```text
1. Before two-source capture, collect same-PRN single-source baseline under the
   same RF/CN0 condition.
2. Dense tap span must match the target delay. The current +/-1.5 chip window is
   enough for close-source fusion, but delays around 50-100 m need a wider span,
   for example -4:0.1:4 chips.
3. Continue using condition.json fields delay_m and power_ratio_db so fitting
   results can be compared to known truth.
```

-- Codex, 2026-07-28

## Phase A Formal L5 Fingerprint - Target CN0 50, PRN15, 30s x3

Date: 2026-07-28

Author: Codex

User adjusted the simulator to:

```text
L5 output label=-54
single-satellite amplitude=64
external attenuation=none
B210 gain=40 dB
target bin=CN0 50
```

Initial PRN5 prescan under this setting was stable but low for the target bin:

```text
PRN5 15 s prescan: cn0_median=48.49, kept_fraction=0.3675,
n_blocks=1366, sem_block_worst=0.001110
```

Per user suggestion, changed satellites and ran a 15 s alternate-PRN prescan:

```text
PRN   cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  judgment
15    51.61       0.9599       0.7503         2789      0.000564         best CN0 50 candidate
18    45.38       0.8577       0.5258         1959      0.001258         stable but too low
20    52.19       -0.0425      0              -         -                numeric CN0 but unlocked; unusable
11    nan         nan          0              -         -                no dense records
```

PRN15 was selected for the formal CN0 50 tier.

Formal capture set:

```text
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn050_prn15_run1_30s_0728
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn050_prn15_run2_30s_0728
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn050_prn15_run3_30s_0728
```

Per-run metadata:

```text
run  cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  asym(check)
1    51.74       0.9807       0.8331         6223      0.000370         0.01753
2    51.70       0.9652       0.9325         6964      0.000349         0.01703
3    51.68       0.9899       0.8435         6306      0.000364         0.01677
```

Coherent aggregate command:

```bash
python3 /tmp/aggregate_reference_fingerprint_coherent.py /home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn050_prn15_run1_30s_0728/l5_prescan_reference_Rtau.png.csv /home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn050_prn15_run2_30s_0728/l5_prescan_reference_Rtau.png.csv /home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn050_prn15_run3_30s_0728/l5_prescan_reference_Rtau.png.csv --labels cn050,cn050,cn050 --chip-m 29.3 --shape-from coherent --plot /home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn050_prn15_30s_group_coherent.png
```

Coherent aggregate result:

```text
VERDICT: TRUSTWORTHY (reproducible across runs) [precision: OK]
peak_chip=-0.0033 +/- 0.0002 chips (-0.10 +/- 0.01 m)
FWHM=1.0905 +/- 0.0001 chips (31.95 +/- 0.00 m)
asym_max=0.0171 +/- 0.0003
noise_floor=0.0077 +/- 0.0000
tap_std_mean=0.0433 +/- 0.0001
min n_blocks=6223
worst SEM_block=0.00037
FWHM CV=0.01%
kept_fraction mean=87%, min=83%
overlay plot=/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn050_prn15_30s_group_coherent.png
```

The earlier PRN5 30 s target-50 candidate captures were moved out of the formal
grid to avoid mixing two different measured-CN0/PRN conditions in the same tier:

```text
from: /home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn050_prn5_run{1,2,3}_30s_0728
to:   /home/bupt/lya/gnss_data/phaseA_prescan/formal_rejected_or_alt/
reason: stable but measured CN0 ~=48.6, not the selected formal CN0 50 tier
```

Dataset index was rebuilt:

```text
/home/bupt/lya/gnss_data/phaseA_l5_grid/dataset_index.csv
captures indexed: 12
coverage:
CN0 40: runs=3, cn0_med=39.7, min_nblk=1380
CN0 45: runs=3, cn0_med=43.1, min_nblk=814
CN0 50: runs=3, cn0_med=51.7, min_nblk=6223
CN0 56: runs=3, cn0_med=57.0, min_nblk=1728
```

Judgment:

The formal L5 Phase A reference library now has the intended four-tier grid:
approximately CN0 57, 52, 43, and 40. PRN15 is the accepted CN0 50/52 tier under
`L5=-54, amplitude=64, no attenuation`. PRN20 again demonstrated that a numeric
CN0 close to the target is not sufficient without positive lock and kept epochs.

-- Codex, 2026-07-28

## Phase A L5 CN0 50 Prescan - L5 -57, Amplitude 64, No Attenuation

Date: 2026-07-28

Author: Codex

User adjusted the simulator to:

```text
L5 output label=-57
single-satellite amplitude=64
external attenuation=none
B210 gain=40 dB
target bin=CN0 50
```

Ran a short 15 s prescan on the current high/usable candidates:

```text
PRN20, PRN15, PRN5
```

Results:

```text
PRN   cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  judgment
20    29.03       -0.0308      0              -         -                phantom/unlocked
15    49.06       -0.0865      0              -         -                numeric CN0 near 50 but not locked; unusable
5     46.67       0.9354       0.7250         2695      0.000971         valid but closer to CN0 47 than CN0 50
```

PRN5 generated a clean single-run reference:

```text
coherent peak at 0.000 chip
asymmetry from check=0.0153
aggregate single-run FWHM=1.1043 chips (32.36 m)
single-run verdict=SINGLE-RUN, precision OK
```

Judgment:

Do not use PRN15's `cn0_median=49.06` as a CN0 50 library point: its lock
metric is negative and the strict selector kept zero epochs. It is another
example of why CN0 labels must be paired with lock/kept evidence.

The current `L5=-57, amplitude=64, no attenuation` setting is usable on PRN5 but
lands around measured CN0 47, not 50. For the formal CN0 50 bin, prefer PRN5 and
raise L5 by about 3 dB, e.g. try `L5=-54` first while keeping amplitude 64 and
no attenuation. If PRN5 then lands in the 49-51 dB-Hz band with sustained lock,
capture 30 s x3 for the formal CN0 50 tier.

-- Codex, 2026-07-28

## Phase A L5 Library - Coherent Shape Re-Aggregation for CN0 56/45/40

Date: 2026-07-28

Author: Codex

Claude pointed out that some previously recorded aggregate values used the old
magnitude-average shape. That shape is positively biased by noise and can widen
FWHM, especially near the low-CN0 boundary. Accepted. Re-ran all three formal L5
bins with the current aggregation script and explicit coherent shape selection:

```text
script copied to NUC as /tmp/aggregate_reference_fingerprint_coherent.py
shape option: --shape-from coherent
data root: /home/bupt/lya/gnss_data/phaseA_l5_grid
```

The re-aggregation is analysis-only. It does not change raw captures, dense
dumps, or per-run reference CSVs.

Coherent aggregate results:

```text
bin    PRN/run set       verdict        FWHM chips          FWHM meters        asym_max
56     PRN11 run1/2/3    TRUSTWORTHY    1.0916 +/- 0.0002  31.98 +/- 0.01 m  0.0334 +/- 0.0000
45     PRN20 run1/2/3    TRUSTWORTHY    1.0960 +/- 0.0015  32.11 +/- 0.04 m  0.0336 +/- 0.0008
40     PRN5 run2/3/4     TRUSTWORTHY    1.0884 +/- 0.0008  31.89 +/- 0.02 m  0.0136 +/- 0.0020
```

Precision notes from the coherent aggregate:

```text
CN0 56: min n_blocks=1728, worst SEM_block=0.00038, precision OK
CN0 45: min n_blocks=814,  worst SEM_block=0.00292, SEM above interim target
CN0 40: min n_blocks=1380, worst SEM_block=0.00290, SEM above interim target
```

Saved coherent outputs on NUC:

```text
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn056_prn11_30s_group_coherent.log
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn056_prn11_30s_group_coherent.png
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn045_prn20_30s_group_coherent.log
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn045_prn20_30s_group_coherent.png
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn040_prn5_30s_group_coherent.log
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn040_prn5_30s_group_coherent.png
```

Judgment:

The coherent results supersede the older magnitude-shape FWHM/asym values for
the Phase A L5 reference library. The library remains valid at CN0 56, 45, and
40. The 45 and 40 bins are lower precision than 56 but still reproducible enough
to keep as formal bins. When Claude writes the TRUSTWORTHY SOP, use the coherent
aggregate logs above as the numeric source of truth.

22 s lock-loss observation:

```text
CN0 56 PRN11 run1: loss immediately after Current receiver time: 22 s
CN0 45 PRN20 run1: loss immediately after Current receiver time: 22 s
CN0 40 PRN5  run1: loss immediately after Current receiver time: 22 s
CN0 40 PRN5  run4: loss immediately after Current receiver time: 22 s
```

This does not block Phase A because the strict selector removes disturbed
epochs and enough clean blocks remain. It is still a Phase B risk: two-source
time-domain tracking will need longer continuous clean spans, so this recurring
22 s L5Q lock disturbance must remain on the Phase B preflight checklist.

-- Codex, 2026-07-28

## Phase A Formal L5 Fingerprint - Target CN0 40, High-EL PRN5, 30s x3

Date: 2026-07-28

Author: Codex

Current simulator/RF environment confirmed by user:

```text
L5 output label=-65
single-satellite amplitude=64
external attenuation=none
B210 gain=40 dB
tracking mode=L5Q pilot robust dense
sample rate=20 Msps
sample type=sc16 / ishort
```

The same `L5=-65, amplitude=64, no attenuation` state that produced the target
45 candidate on PRN20 also exposed a usable lower-CN0 high-elevation candidate
on PRN5:

```text
PRN5 prescan: cn0_median=39.79 dB-Hz, lock_median=0.827,
kept_fraction=0.9259, n_blocks=3450, sem_block_worst=0.001897
```

Formal captures were attempted as `l5_cn040_prn5_run1..run4_30s_0728`. Run 1
collapsed under the strict selector (`strict kept=0`, no reference CSV) and was
discarded from the formal aggregate. Runs 2, 3, and 4 were retained:

```text
run  cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  asym     fwhm_chips
2    39.69       0.864        0.9410         7035      0.001313         0.01088  1.1955
3    39.78       0.852        0.9560         7147      0.001287         0.01415  1.1960
4    39.56       0.821        0.1857         1380      0.002897         0.01572  1.1928
```

Aggregate command:

```bash
python3 dev_notes/sim/aggregate_reference_fingerprint.py /home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn040_prn5_run2_30s_0728/l5_prescan_reference_Rtau.png.csv /home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn040_prn5_run3_30s_0728/l5_prescan_reference_Rtau.png.csv /home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn040_prn5_run4_30s_0728/l5_prescan_reference_Rtau.png.csv --labels cn040,cn040,cn040 --chip-m 29.3 --plot /home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn040_prn5_30s_group.png
```

Aggregate result:

```text
VERDICT: TRUSTWORTHY (reproducible across runs) [precision: SEM above interim target]
peak_chip=-0.0058 +/- 0.0025 chips (-0.17 +/- 0.07 m)
FWHM=1.1947 +/- 0.0014 chips (35.01 +/- 0.04 m)
asym_max=0.0070 +/- 0.0023
noise_floor=0.3155 +/- 0.0007
tap_std_mean=0.1860 +/- 0.0022
min n_blocks=1380
worst SEM_block=0.00290
FWHM CV=0.12%
kept_fraction mean=69%, min=19%
overlay plot=/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn040_prn5_30s_group.png
```

Dataset index was rebuilt at:

```text
/home/bupt/lya/gnss_data/phaseA_l5_grid/dataset_index.csv
```

Current L5 Phase A initial library now has three measured-CN0 conditions that
passed aggregate reproducibility:

```text
measured CN0 ~=57 dB-Hz: PRN11, target label 56
measured CN0 ~=42-45 dB-Hz: PRN20, target label 45
measured CN0 ~=39.7 dB-Hz: PRN5, target label 40
```

Judgment:

The current `L5=-65, amplitude=64, no attenuation` environment is valid for the
CN0 ~=40 edge of the initial L5 reference library, with PRN5 preferred over
PRN20/18/15 for this bin. This is not as clean as the high-CN0 bins: one formal
attempt failed completely and the retained run 4 has low kept fraction plus SEM
above the interim precision target. However, the retained group is highly
reproducible in FWHM and peak position, so it is acceptable as the low-CN0
boundary condition for Phase A. Do not use the discarded run 1 in fitting or
aggregate statistics.

-- Codex, 2026-07-28

## Phase A Formal L5 Fingerprint - Target CN0 45, High-EL PRN20, 30s x3

Date: 2026-07-28

Author: Codex

User suggested choosing higher-elevation satellites for cleaner formal captures.
Accepted. Under the current simulator state:

```text
L5 output label=-65
single-satellite amplitude=64
external attenuation=none
B210 gain=40 dB
```

a high-elevation prescan was run for PRN20, PRN18, PRN15, and PRN5. Results:

```text
PRN  EL(deg)  cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  usable note
20   79.3     44.93       0.934        0.6656         2442      0.001233         best target-45 candidate
18   77.7     28.87       -0.0177      0              -         -                phantom/unlocked
15   65.3     42.71       0.940        0.8569         3192      0.001406         usable but lower CN0
5    59.9     39.79       0.827        0.9259         3450      0.001897         usable CN0 ~=40
```

PRN20 was selected for the formal target-CN0 45 condition.

Formal condition:

```text
phase=A
band=L5
PRN=20
cn0_target=45
L5 output label=-65
L1 output label=-65
single-satellite amplitude=64
B210 gain=40 dB
external attenuation=none
sample rate=20 Msps
sample type=sc16/ishort
tracking=L5Q pilot robust dense
capture length=30 s
runs=3
```

Run directories:

```text
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn045_prn20_run1_30s_0728
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn045_prn20_run2_30s_0728
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn045_prn20_run3_30s_0728
```

Per-run index:

```text
run  cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  asym     FWHM_chips
1    42.14       0.914        0.1102         814       0.002922         0.03285  1.1452
2    44.99       0.922        0.8300         6175      0.000775         0.03332  1.1209
3    42.27       0.902        0.7098         2307      0.001101         0.03464  1.1379
```

Aggregate output:

```text
[cn045] n=3
peak_chip  = -0.0058 +/- 0.0013
FWHM       = 1.1347 +/- 0.0102 chips = 33.25 +/- 0.30 m
asym_max   = 0.0156 +/- 0.0018
min n_blocks=814
worst SEM_block=0.00292
FWHM CV=0.90%
asym std=0.00184
VERDICT: TRUSTWORTHY
```

Notes:

This condition was targeted as CN0 45, but the formal run set has measured CN0
spread around `42-45 dB-Hz`. Run 1 suffered low kept fraction and SEM above the
interim target, but the group still passed TRUSTWORTHY due to cross-run
reproducibility. In later analysis, classify this condition by the measured CN0
metadata rather than assuming it is exactly 45.

Artifacts:

```text
/home/bupt/lya/gnss_data/phaseA_l5_grid/dataset_index.csv
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn045_prn20_30s_group.log
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn045_prn20_30s_group.png
```

Judgment:

This is a second formal TRUSTWORTHY L5 Phase A reference-fingerprint condition,
best described as the measured `CN0 ~= 43-45` band. The next useful grid point is
`CN0 ~= 40`, for which the high-elevation prescan suggests PRN5 is a strong
candidate under the same `L5=-65, amplitude=64` setting.

-- Codex, 2026-07-28

## Phase A Formal L5 Fingerprint - CN0 56, PRN11, 30s x3

Date: 2026-07-28

Author: Codex

Formal capture started after the amplitude-64 retry confirmed the correct RF
state for `CN0 ~= 56`.

Condition:

```text
phase=A
band=L5
PRN=11
cn0_target=56
L5 output label=-50
L1 output label=-65
single-satellite amplitude=64
B210 gain=40 dB
external attenuation=none
sample rate=20 Msps
sample type=sc16/ishort
tracking=L5Q pilot robust dense
capture length=30 s
runs=3
```

Output root:

```text
/home/bupt/lya/gnss_data/phaseA_l5_grid
```

Run directories:

```text
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn056_prn11_run1_30s_0728
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn056_prn11_run2_30s_0728
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn056_prn11_run3_30s_0728
```

Per-run index:

```text
run  cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  asym     FWHM_chips
1    56.99       0.972        0.2321         1728      0.000376         0.03349  1.09261
2    57.04       0.979        0.7915         5914      0.000210         0.03339  1.09303
3    56.93       0.990        0.9560         7143      0.000190         0.03340  1.09296
```

Aggregate output:

```text
[cn056] n=3
peak_chip  = -0.0057 +/- 0.0001
FWHM       = 1.0929 +/- 0.0002 chips = 32.02 +/- 0.01 m
asym_max   = 0.0299 +/- 0.0002
noise_floor= 0.0453 +/- 0.0003
min n_blocks=1728
worst SEM_block=0.00038
FWHM CV=0.02%
asym std=0.00015
VERDICT: TRUSTWORTHY
```

Notes:

Run 1 had one runtime loss-of-lock around 22 s and therefore only kept 23.2% of
the dense records, but the strict sustained-lock selector still retained enough
clean epochs (`n_blocks=1728`). Runs 2 and 3 were much cleaner. Cross-run
reproducibility is excellent, so 30 s is sufficient for this `CN0 ~= 56` point;
no 60 s extension is needed.

Artifacts:

```text
/home/bupt/lya/gnss_data/phaseA_l5_grid/dataset_index.csv
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn056_prn11_30s_group.log
/home/bupt/lya/gnss_data/phaseA_l5_grid/l5_cn056_prn11_30s_group.png
```

Judgment:

This is the first formal TRUSTWORTHY L5 Phase A reference-fingerprint condition.
Proceed to the next confirmed grid point using the same 30 s x3 workflow.

-- Codex, 2026-07-28

## Phase A L5 CN0 56 Prescan - Amplitude 64 Retry

Date: 2026-07-28

Author: Codex

User corrected the simulator single-satellite amplitude to `64` and requested
another capture under:

```text
L1 output label: -65
L5 output label: -50
single-satellite amplitude: 64
B210 gain: 40 dB
external attenuation: none
PRN: 11
```

Command pattern used on NUC:

```bash
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p11_l5m50_a64_g40_cn056_prescan_retry_0728 --prn 11 --gain 40 --tx-l1-label -65 --tx-l5-label -50 --sat-power-label 64 --cn0-target 56 --cn0-min 45 --note cn056_prescan_retry_amp64
```

Result:

```text
dense_records=14870
cn0_median=56.87
cn0_p10=56.33
cn0_p90=57.16
lock_median=0.9579
kept_records=14574
kept_fraction=0.9801
n_blocks=9
sem_block_worst=0.010016
FWHM=32.05 m
verdict=INSUFFICIENT
overflow=0
```

Judgment:

The RF/simulator setting is now correct for the intended `CN0 ~= 56` point:
measured CN0 is high and lock is healthy. The previous failed CN0=56 prescan was
therefore caused by the actual simulator state mismatch, not by the receiver.

However, this 15 s prescan should not be treated as a formal reference-library
run because the blocking estimator reports only `n_blocks=9` and
`sem_block_worst=0.010016`. The likely practical remedy is longer/repeated
formal captures (30 s first; extend if the same low n_blocks repeats). The point
is suitable to proceed to formal 30 s CN0=56 repeats, but this prescan itself is
not a TRUSTWORTHY fingerprint.

-- Codex, 2026-07-28

## Phase A L5 CN0 56 Prescan - User Adjusted State Check

Date: 2026-07-28

Author: Codex

User reported:

```text
single-satellite amplitude: 64
L5 output label: -50
L1 output label: -65
```

but the provided simulator screenshot showed `PWR=60.0` for the emitted PRNs.
Because Phase A metadata must not silently mix simulator settings, a short PRN11
prescan was run before starting formal CN0=56 captures.

Command pattern used on NUC:

```bash
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p11_l5m50_a64_or60_g40_cn056_prescan_0728 --prn 11 --gain 40 --tx-l1-label -65 --tx-l5-label -50 --sat-power-label 64 --cn0-target 56 --cn0-min 45 --note cn056_prescan_user_text_amp64_image_pwr60
```

Result:

```text
PRN11 dense_records=14892
cn0_median=29.23
cn0_p10=28.73
cn0_p90=30.25
lock_median=-0.0136
strict kept=0
overflow=0
```

Judgment:

This is not a valid CN0=56 capture state. The reported `CN0 ~= 29` with lock
metric near zero matches the previously identified phantom/unlocked CN0 floor,
not a clean tracked signal. Formal Phase A recording must not start from this
state.

Likely issue to verify on the simulator before retrying:

1. The screenshot `PWR` column shows `60.0`, not `64`.
2. Confirm that L5 output really changed to `-50` on the active RF output path.
3. Confirm the external attenuator is removed.
4. Confirm the active PRN selected for capture is actually emitted on L5 and
   mapped to the same RF output path connected to B210.

-- Codex, 2026-07-28

## Discussion - Reclassify the Apparent CN0 29 Readings

Date: 2026-07-28

Author: Codex

Claude's correction is accepted.

Key observation:

For PRN11, three different attenuation settings produced almost the same
reported CN0 while the lock metric showed no usable lock:

```text
attenuation  expected if truly tracking  measured cn0_median  lock_median
3 dB         about 37-38 dB-Hz           28.77                -0.0034
6 dB         about 34-35 dB-Hz           28.74                 0.0027
10 dB        about 30-31 dB-Hz           28.66                -0.0119
```

Judgment:

Those `CN0 ~= 28.7` values should not be treated as real weak-signal CN0
measurements. They are more likely the CN0 estimator's noise-floor / unlocked
channel artifact after tracking has collapsed. Calling them "CN0 around 30 but
not usable" is too imprecise and can mislead later decisions. The better wording
is:

```text
Below the current tracking margin, the channel collapses and reports a phantom
CN0 floor around 28.7 dB-Hz. This is not a trustworthy tracked signal point.
```

Updated Phase A boundary:

```text
Confirmed L5 usable region for current workflow: about 40 dB-Hz and above.
Borderline exploratory point: PRN7 around 38.4 dB-Hz with 3 dB attenuation.
Rejected for initial library: apparent CN0 around 28.7 after 3/6/10 dB
attenuation on weak PRNs or collapsed channels.
```

Decision:

Stop using attenuation as the next knob for the initial L5 Phase A reference
library. It is not creating clean lower-CN0 reference points; it is pushing the
tracking loop below its current working margin. The first reference library
should use only trustworthy tracked points, roughly:

```text
CN0 ~= 56
CN0 ~= 50
CN0 ~= 45
CN0 ~= 40
```

If Phase B later needs paths in the 30-40 dB-Hz region, that should become a
separate weak-signal tracking work package: L5Q pilot-specific longer coherent
integration, loop bandwidth / FLL-assisted pull-in tuning, and consistent Phase
A/Phase B configs. It should not be solved by adding attenuation to the current
tracking config and accepting phantom CN0 values.

Codex's recommendation:

Proceed to formal L5 Phase A recording on the confirmed grid first. Prefer PRN7
for the low end because it held the best margin. Use repeated 30 s captures and
let `aggregate_reference_fingerprint.py` decide TRUSTWORTHY/MARGINAL from
cross-run reproducibility. Do not include the collapsed CN0 28.7 rows in the
formal clean reference library.

-- Codex, 2026-07-28

## Phase A L5 Prescan - Amplitude 60 with 6 dB Attenuator

Date: 2026-07-28

Author: Codex

User kept:

```text
L1 output label: -70
L5 output label: -70
single-satellite amplitude: 60
B210 gain: 40 dB
```

and changed the external attenuation to 6 dB.

Purpose:

Check whether 6 dB attenuation can produce a usable lower-CN0 point between the
previous 3 dB case and the failed 10 dB case.

Command pattern used on NUC:

```bash
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p7_l5m70_a60_g40_att6_0728 --prn 7 --gain 40 --tx-l1-label -70 --tx-l5-label -70 --sat-power-label 60 --cn0-target 35 --cn0-min 20 --note slope_check_l1_-70_l5_-70_amp60_att6db
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p11_l5m70_a60_g40_att6_0728 --prn 11 --gain 40 --tx-l1-label -70 --tx-l5-label -70 --sat-power-label 60 --cn0-target 35 --cn0-min 20 --note slope_check_l1_-70_l5_-70_amp60_att6db
```

Results:

```text
PRN  result
7    no tracking / no dense records; overflow=0
11   dense records=14862, cn0_median=28.74, cn0_p10=24.47, cn0_p90=33.39,
     lock_median=0.0027, strict kept=0, overflow=0
```

Judgment:

The 6 dB attenuator again pushes the current L5 setup into the `CN0 ~= 29`
region, where the present 15 s L5Q pilot robust dense-fingerprint workflow does
not produce a strict usable clean reference. PRN7 failed to produce dense records
and PRN11 had no sustained segment passing the lock criterion.

This reinforces the current Phase A boundary:

```text
usable low point so far: PRN7, amplitude 60, no attenuator, CN0 ~= 40
borderline exploratory point: PRN7, amplitude 60, 3 dB attenuator, CN0 ~= 38
not currently usable: 6 dB or 10 dB attenuation, CN0 ~= 29
```

Do not include the 6 dB attenuator result in the clean reference library. It is
a low-CN0 tracking/floor diagnostic.

-- Codex, 2026-07-28

## Phase A L5 Prescan - Amplitude 60 with 3 dB Attenuator

Date: 2026-07-28

Author: Codex

User kept:

```text
L1 output label: -70
L5 output label: -70
single-satellite amplitude: 60
B210 gain: 40 dB
```

and added a 3 dB external attenuator.

Purpose:

Check whether a mild external attenuation after the amplitude-60/no-attenuator
case can produce a usable `CN0 ~= 35-38 dB-Hz` L5 Phase A point.

Command pattern used on NUC:

```bash
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p7_l5m70_a60_g40_att3_0728 --prn 7 --gain 40 --tx-l1-label -70 --tx-l5-label -70 --sat-power-label 60 --cn0-target 35 --cn0-min 25 --note slope_check_l1_-70_l5_-70_amp60_att3db
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p11_l5m70_a60_g40_att3_0728 --prn 11 --gain 40 --tx-l1-label -70 --tx-l5-label -70 --sat-power-label 60 --cn0-target 35 --cn0-min 25 --note slope_check_l1_-70_l5_-70_amp60_att3db
```

Results:

```text
PRN  cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  asym     FWHM_m   overflow
7    38.43       0.794        0.7170         2309      0.002844         0.02841  38.09    0
11   28.77       -0.0034      0              -         -                -        -        0
```

Judgment:

The 3 dB attenuator produces a usable-ish low-CN0 point for PRN7
(`CN0 ~= 38.4`, kept 71.7%, n_blocks 2309), but its SEM is above the current
interim target (`0.002844 > 0.0020`) and the FWHM is wider than the higher-CN0
runs. It should be treated as a prescan point, not a trusted reference without
longer/repeated captures.

PRN11 under the same attenuator did not form a strict usable segment and landed
around `CN0 ~= 28.8`, similar to the 10 dB attenuator failure mode. This confirms
that low-CN0 behavior is PRN/link-condition dependent in the current setup. Do
not assume a single external attenuation value maps every PRN to the same usable
CN0 bin.

Practical implication:

For a formal L5 Phase A grid, PRN7 with amplitude 60 + 3 dB attenuation is a
candidate for exploring the `CN0 ~= 38` region. If the target is a robust
`CN0 ~= 35` reference, the next test should likely be longer (30-60 s) and/or
use PRN7 first; PRN11 is not a good low-CN0 candidate under this attenuator.

-- Codex, 2026-07-28

## Phase A L5 Prescan - Amplitude 60, No External Attenuator

Date: 2026-07-28

Author: Codex

User removed the 10 dB attenuator and changed the simulator single-satellite
amplitude from `64` to `60`. L1/L5 output labels remained at `-70`; B210 gain
remained at `40 dB`.

Purpose:

Check whether reducing single-satellite amplitude, without the 10 dB external
attenuator, gives a usable lower-CN0 Phase A point.

Command pattern used on NUC:

```bash
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p7_l5m70_a60_g40_0728 --prn 7 --gain 40 --tx-l1-label -70 --tx-l5-label -70 --sat-power-label 60 --cn0-target 35 --cn0-min 25 --note slope_check_l1_-70_l5_-70_amp60_no_att
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p11_l5m70_a60_g40_0728 --prn 11 --gain 40 --tx-l1-label -70 --tx-l5-label -70 --sat-power-label 60 --cn0-target 35 --cn0-min 25 --note slope_check_l1_-70_l5_-70_amp60_no_att
```

Results:

```text
PRN  cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  asym     FWHM_m   DUALPATH_OBS  overflow
7    40.12       0.806        0.7884         2900      0.001993         0.02716  34.43    yes           0
11   40.63       0.819        0.5478         1946      0.002307         0.03272  34.52    yes           0
```

Judgment:

This setting still lands around `CN0 ~= 40 dB-Hz`, not around 35. It is usable
for a `CN0 ~= 40` Phase A point, and PRN7 is cleaner than PRN11 in this run
(`sem_block_worst=0.001993` vs `0.002307`, kept 78.8% vs 54.8%).

This result also explains the earlier 10 dB attenuator case: the attenuator did
not just "make a normal 30 dB-Hz signal"; it pushed the current SDR tracking /
15 s dense-fingerprint workflow into a regime with unstable carrier-lock metric
and no strict sustained segment.

Question: why can a phone use CN0 around 30 while B210/GNSS-SDR could not form a
clean fingerprint at CN0 around 30 in the attenuated test?

Answer / judgment:

CN0 around 30 dB-Hz is not inherently unusable for GNSS positioning. Phones can
often use such satellites because they use mature receiver firmware, aided
acquisition/tracking, many satellites at once, long smoothing, navigation-state
memory, proprietary lock detectors, and positioning filters that tolerate some
weak/ intermittent channels.

Our current Phase A test is different and stricter:

1. It is single-PRN/single-band dense-correlator export, not multi-satellite PVT.
2. It requires a sustained clean tracking segment to estimate a reference
   `R(tau)` fingerprint, not merely an occasionally usable pseudorange.
3. The selector currently requires carrier-lock quality plus minimum continuous
   run length; at the attenuated `CN0 ~= 29` point, strict kept epochs were zero.
4. The relaxed diagnostic showed wrong peak / no FWHM / huge SEM, so including it
   would poison the clean reference library.
5. B210 + GNSS-SDR tracking loops and lock detectors are not equivalent to a
   phone chipset's highly optimized weak-signal tracking stack.

Therefore the correct statement is not "CN0=30 cannot be used by SDR." The
correct statement is: under this current L5Q pilot robust config, 20 Msps,
15-second file, and strict Phase A fingerprint acceptance rules, the attenuated
`CN0 ~= 29` capture did not provide a trustworthy clean `R(tau)` reference.

Next action implied:

Before deciding whether to include `CN0 ~= 30` in the L5 Phase A library, run a
purpose-built weak-signal test: longer capture (e.g. 30-60 s), possible tracking
parameter tuning, and a repeatability check. For the immediate reference library,
the reliable low point is still `CN0 ~= 40`.

-- Codex, 2026-07-28

## Phase A L5 Prescan - 10 dB External Attenuator

Date: 2026-07-28

Author: Codex

User added a 10 dB external attenuator after the `L5=-70` / amplitude `64`
minimum-output setup. B210 gain stayed at `40 dB`.

Purpose:

Check whether an external attenuator can push the L5 single-source prescan from
the previous `CN0 ~= 40 dB-Hz` point down toward the `CN0 ~= 30 dB-Hz` grid
point.

Command pattern used on NUC:

```bash
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p7_l5m70_a64_g40_att10_0728 --prn 7 --gain 40 --tx-l1-label -70 --tx-l5-label -70 --sat-power-label 64 --cn0-target 30 --cn0-min 25 --note slope_check_l1_-70_l5_-70_amp64_att10db
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p11_l5m70_a64_g40_att10_0728 --prn 11 --gain 40 --tx-l1-label -70 --tx-l5-label -70 --sat-power-label 64 --cn0-target 30 --cn0-min 25 --note slope_check_l1_-70_l5_-70_amp64_att10db
```

Results:

```text
PRN  result
7    no tracking / no dense records; overflow=0
11   dense records=14903, cn0_median=28.66, cn0_p10=24.68, cn0_p90=33.59,
     lock_median=-0.0119, strict kept=0, overflow=0
```

Diagnostic relaxed selector on PRN11:

```text
selector: CN0>=20, lock>=-1, min-lock-run=500, settle=100
kept_records=1921, kept_fraction=12.9%, n_blocks=480
sem_block_worst=0.04539
peak_chip=+1.0498
FWHM=nan
noise_floor=1.4890
```

Judgment:

The 10 dB attenuator does push the observed L5 signal to roughly the `CN0 ~= 30`
region (`PRN11 cn0_median=28.66`), but at 15 s capture length and current robust
tracking settings it does **not** yield a usable Phase A clean fingerprint.
Strict selection keeps no epochs; relaxed diagnostic selection produces an
unstable/noisy profile with wrong peak position and no valid FWHM. Treat this as
a low-CN0 floor diagnostic, not as a reference-library capture.

For formal Phase A, the confirmed usable L5 points so far are:

```text
CN0 ~= 55-57: L5=-50, amplitude=64, gain=40, PRN7/11
CN0 ~= 45-46: L5=-65, amplitude=64, gain=40, PRN7/11
CN0 ~= 40-41: L5=-70, amplitude=64, gain=40, PRN7/11, prefer PRN11
```

For `CN0 ~= 30`, do not proceed with full grid repeats until deciding one of:

1. extend capture duration substantially and/or relax tracking configuration in
   a principled way, or
2. exclude CN0=30 from the initial L5 reference library, or
3. use a less aggressive attenuation / per-satellite amplitude adjustment to
   target CN0 35 first.

-- Codex, 2026-07-28

## Phase A L5 Prescan Slope Check - L5 Output -70

Date: 2026-07-28

Author: Codex

User lowered both simulator signal output labels to `-70`, which is the minimum
available output setting. Single-satellite amplitude remained `64`; B210 gain
remained `40 dB`.

Purpose:

Check whether the current cabled/RF setup can reach the `CN0 ~= 40 dB-Hz` grid
point by simulator output alone before changing per-satellite amplitude or
adding an external attenuator.

Command pattern used on NUC:

```bash
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p7_l5m70_a64_g40_0728 --prn 7 --gain 40 --tx-l1-label -70 --tx-l5-label -70 --sat-power-label 64 --cn0-target 40 --cn0-min 30 --note slope_check_l1_-70_l5_-70_amp64
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p11_l5m70_a64_g40_0728 --prn 11 --gain 40 --tx-l1-label -70 --tx-l5-label -70 --sat-power-label 64 --cn0-target 40 --cn0-min 30 --note slope_check_l1_-70_l5_-70_amp64
```

Results:

```text
PRN  L5 label  cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  asym     FWHM_m   overflow
7    -70       40.55       0.828        0.5276         1922      0.002254         0.03465  34.06    0
11   -70       40.97       0.835        0.6521         2346      0.001940         0.03290  34.13    0
```

Comparison across the measured L5 anchors:

```text
PRN  CN0 at -50  CN0 at -65  CN0 at -70
7    57.42       45.57       40.55
11   55.39       45.85       40.97
```

Judgment:

The `L5=-70, amplitude=64, B210 gain=40` setting reaches the desired
`CN0 ~= 40 dB-Hz` point for PRN7/PRN11. Therefore, for the CN0=40 L5 grid point,
an external attenuator is not immediately required.

However, PRN7's single-run `sem_block_worst=0.002254` is slightly above the
current interim engineering target (`0.0020`), while PRN11 is just inside it.
For formal Phase A reference-library captures at this CN0, prefer PRN11 first,
use repeated runs, and consider 30 s capture length if repeatability or SEM is
not good enough.

If later CN0=35 or CN0=30 is required, the simulator output is already at its
minimum. At that point the next control knob should be per-satellite amplitude
or an external RF attenuator, not lower simulator output.

Dataset index after this step:

```text
/home/bupt/lya/gnss_data/phaseA_prescan/dataset_index.csv
```

It now contains seven L5 prescan rows: PRN6/7/11 at `L5=-50`, PRN7/11 at
`L5=-65`, and PRN7/11 at `L5=-70`.

-- Codex, 2026-07-28

## Phase A L5 Prescan Slope Check - L5 Output -65

Date: 2026-07-28

Author: Codex

User changed the simulator L5 output label from `-50` to `-65`, with
single-satellite amplitude still `64`. B210 gain was kept at `40 dB`; this is
important because the purpose was to test whether measured CN0 follows
transmitter power at the current receiver/RF setting.

Command pattern used on NUC:

```bash
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p7_l5m65_a64_g40_0728 --prn 7 --gain 40 --tx-l1-label -65 --tx-l5-label -65 --sat-power-label 64 --cn0-target 40 --cn0-min 35 --note slope_check_l1_-65_l5_-65_amp64
bash dev_notes/sim/run_l5_phaseA_prescan_point.sh --tag p11_l5m65_a64_g40_0728 --prn 11 --gain 40 --tx-l1-label -65 --tx-l5-label -65 --sat-power-label 64 --cn0-target 40 --cn0-min 35 --note slope_check_l1_-65_l5_-65_amp64
```

Why `--cn0-min 35`:

This was a slope/low-CN0 validation point. Keeping the older `CN0>=45` selector
would reject most epochs if the target actually landed near 40 dB-Hz, so the
selector floor was lowered for this prescan point.

Results:

```text
PRN  L5 label  cn0_median  lock_median  kept_fraction  n_blocks  sem_block_worst  asym     FWHM_m   overflow
7    -65       45.57       0.913        0.4697         1749      0.001356         0.02992  32.21    0
11   -65       45.85       0.959        0.7057         2628      0.001090         0.03364  32.55    0
```

Comparison against the earlier same-PRN `L5=-50` prescan:

```text
PRN  CN0 at -50  CN0 at -65  measured drop for -15 dB tx change
7    57.42       45.57       11.85 dB
11   55.39       45.85       9.54 dB
```

Judgment:

The simple `delta CN0 ~= delta simulator power` assumption is not confirmed in
this current setup. Lowering the L5 output label by 15 dB produced measured CN0
near 45.6 dB-Hz, not near 40 dB-Hz. This still gives a good mid/high-CN0
prescan point, but Claude should use the two measured anchors per PRN to
estimate the next transmitter setting instead of assuming a strict 1:1 slope.

The rebuilt index is:

```text
/home/bupt/lya/gnss_data/phaseA_prescan/dataset_index.csv
```

It now contains five L5 prescan rows: PRN6/7/11 at `L5=-50`, and PRN7/11 at
`L5=-65`.

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

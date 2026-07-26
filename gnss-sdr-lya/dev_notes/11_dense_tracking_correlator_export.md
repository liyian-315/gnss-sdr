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

# Track B Cross-Reference Texture Benchmark

**Date:** 2026-07-29  
**Author:** Codex

## Purpose

The first Track B result used one favorable PRN28 A-only recording as the
faithful path0 texture. This benchmark checks whether the same moving-receiver
DP and post-correlation EKF results survive other real A-only recordings.

This is a cross-texture synthetic benchmark, not a real moving A+B experiment:

- path0 is the actual per-epoch complex dense-correlator texture from A-only;
- path1 is injected from the same-PRN coherent kernel with known geometry;
- receiver motion creates a 0.37--0.55 chip delay trajectory;
- the original A-only captures and kernels are not modified;
- measured B-only texture and static A+B captures are not inputs to this test.

## Dataset

The run used 23 dense/kernel pairs from:

- `phaseA_l5_grid`: PRN5, PRN11, PRN15, and PRN20;
- `phaseB_l5_baseline`: PRN10, PRN11, PRN23, and PRN28.

The measured CN0 range was about 39.6--59.9 dB-Hz. Nineteen references passed
the existing reference-quality gate. Four were retained only as low-quality
controls because `kept_fraction < 0.20` or `n_blocks < 20`.

Each reference produced four 20 s cases:

1. moving path1 at -6 dB;
2. moving equal-power path1 with 180 degree initial phase;
3. static receiver at -6 dB;
4. moving receiver with path1 effectively absent (-120 dB).

Both `track_moving_twosource.py` (DP) and
`track_moving_twosource_ekf.py` (EKF) processed every case.

## Results

### Normal-quality references

| Method | Case | RELIABLE | Median P90 error |
|---|---|---:|---:|
| DP | moving, -6 dB | 14 / 19 | 2.96 m |
| DP | moving, equal power / 180 deg | 4 / 19 | 4.48 m |
| DP | static, -6 dB | 4 / 19 | 9.44 m |
| DP | path absent | 0 / 19 | 14.14 m |
| EKF | moving, -6 dB | 8 / 19 | 1.85 m |
| EKF | moving, equal power / 180 deg | 8 / 19 | 2.65 m |
| EKF | static, -6 dB | 0 / 19 | 2.13 m |
| EKF | path absent | 0 / 19 | 13.12 m |

The strict EKF verdict understates point-estimate performance in some runs:

- moving -6 dB: 11/19 references had P90 error <= 3 m;
- moving equal-power: 10/19 references had P90 error <= 3 m;
- several of those were rejected because 2-sigma truth coverage was below
  80%, not because the delay estimate was grossly wrong.

Low-quality controls produced no EKF `RELIABLE` result. This is desirable, but
DP still accepted two moving cases from those controls.

## Findings

### 1. The PRN28 result was real but not representative

PRN28 run4 remains a strong case:

- EKF moving -6 dB: P90 1.10 m;
- EKF equal-power / 180 deg: P90 1.55 m.

The same algorithms do not generalize at that level to every A-only texture.
The previous result therefore supports feasibility, not cross-PRN robustness.

### 2. Real path0 texture is still the main algorithmic obstacle

Some normal-quality references drive the EKF initializer to the delay boundary
or to a large spurious Doppler. Examples include PRN10 and individual PRN23 or
PRN28 runs. A reference passing the Phase A fingerprint gate is sufficient for
estimating a stable mean kernel, but is not sufficient to guarantee that its
per-epoch residual texture is benign for two-source tracking.

Reference acceptance needs a Track B-specific texture metric. Candidate
metrics include residual Doppler-ridge energy after path0 projection, boundary
initializer rate, and initializer agreement across short blocks.

### 3. EKF gating is safer than DP, but its uncertainty is not calibrated

EKF rejected all static and path-absent controls. DP falsely declared four
normal static controls reliable, so DP must not be used as the final detector
without a motion/diversity gate.

Conversely, EKF rejected several accurate tracks because posterior 2-sigma
coverage was 58--75%. The near-constant posterior standard deviation around
0.69 m does not reflect the reference-dependent path0 texture. Measurement
covariance must include a texture/mismatch term rather than only the local
correlator curvature.

### 4. CN0 is not the only explanatory variable

No normal reference below about 42 dB-Hz produced a successful EKF moving
result, but higher CN0 did not guarantee success. Run-to-run texture changes at
the same PRN and nominal power also changed the verdict. CN0 remains a useful
quality feature, not a sufficient gate.

## Decision

Do not claim that Track B is cross-PRN complete. The current evidence is:

- motion diversity can separate a 0.37--0.55 chip trajectory on several real
  path0 textures;
- the EKF has strong negative-control behavior;
- success is currently reference/run dependent;
- the next algorithm task is texture-aware initialization and covariance, not
  another global threshold change.

Before a real moving capture, add:

1. a Track B texture-quality score derived from A-only residual maps;
2. multi-block or multi-hypothesis initialization with consensus;
3. mismatch-aware EKF measurement covariance;
4. the existing diversity gate to the DP baseline for fair comparison;
5. a cross-reference regression gate using this 23-reference benchmark.

Measured B-only texture and existing static A+B recordings remain useful, but
they answer different questions. B-only can make path1 injection more faithful;
static A+B continues to measure the snapshot separation wall. Neither should be
silently treated as a real moving-receiver validation.

## Existing Static A+B Coverage Audit

The NUC contains 27 static A+B dense datasets:

- PRN11: 7, 15, 30, and 60 m;
- PRN23: 30, 60, and 90 m;
- PRN28: 30 and 60 m;
- PRN15: one early 60 m run.

Twenty-five already had one or more static 1-D/2-D analysis products. The two
previously unanalysed early 60 m runs were checked on 2026-07-29:

- PRN11: no records survived the sustained-lock gate, so no separation claim
  is possible;
- PRN15 delay-Doppler: latched to the 4.4 m minimum-delay boundary and correctly
  returned `UNRELIABLE`;
- PRN15 residual-band fit: recovered 60.4 m, but estimated -22.49 dB instead of
  -6 dB and improved residual energy by only 4.7%, so it also correctly returned
  `UNRELIABLE`.

This is a useful warning: a delay estimate close to the injected answer is not
enough. Amplitude, residual improvement, model conditioning, and capture
quality must pass together.

## Reproduction

The reusable runner is:

```text
python3 dev_notes/sim/run_trackb_cross_reference_benchmark.py --manifest <manifest.csv> --output-dir <output-dir>
```

Manifest columns are `label,prn,dense,kernel,cn0_min`. Results on the NUC are
stored under:

```text
/home/bupt/lya/gnss_data/trackb_cross_reference_0729/
```

The directory contains generated NPZ controls, per-case DP/EKF logs, and
`summary.csv`. It contains no copied raw IQ captures.

## Truth-Free DP Confidence Calibration

**Date:** 2026-07-31
**Author:** Codex

Claude added three truth-free DP confidence features in commit `88cd68eb4`:
motion diversity, delay-Doppler physics consistency, and a best-vs-second
trajectory cost margin. The full 23-reference benchmark was rerun before
accepting the default thresholds.

The first implementation of the alternative-path margin required the
alternative to leave the best path's delay tube in every segment. One segment
without a distant candidate therefore produced an infinite margin and falsely
implied uniqueness. Commit `ea92cacb8` corrected this to the cheapest path that
differs materially in at least one segment.

Results on the 19 normal-quality references:

- all 19 static and all 19 path-absent controls were `LOW-CONFIDENCE`;
- moving -6 dB: only 1 of 14 truth-reliable tracks was confident (7.1% recall);
- moving equal-power: 0 of 4 truth-reliable tracks was confident;
- two of the three confident moving tracks were actually truth-unreliable;
- the corrected margin was not discriminative: truth-reliable moving tracks
  had median margin about 0.27, while negative cases had median about 1.81.

A grid search over delay span, Doppler span, physics residual, and corrected
margin found no useful operating point. With false-positive rate constrained
to 5%, the best recall was 16.7% (3/18).

Decision: retain these fields as diagnostics, but do not label them a calibrated
real-data gate and do not tune the three global thresholds further. False
tracks can be smooth, move substantially, and satisfy the local
delay-Doppler relation. The next gate must include evidence tied to the actual
path0 texture and observation likelihood, not trajectory geometry alone.

The rerun artifacts are on the NUC at:

```text
/home/bupt/lya/gnss_data/trackb_cross_reference_conf_0731/
```

`summary.csv` contains the first gate run; `summary_dp_margin.csv` contains the
corrected alternative-path margin.

## Path0-Texture GLRT: First Leave-One-Run-Out Result

**Date:** 2026-07-31
**Author:** Codex

The next candidate likelihood now models what the geometry-only gate omitted:
the complex residual left by a real path0. For each A-only epoch it fits local
`K + dK/dtau`, normalizes the residual by the fitted path0 amplitude, and learns
a regularized complex residual mean and covariance. The delay-Doppler matched
map is then formed after whitening both the observation and shifted path1
templates.

Evaluation used strict leave-one-run-out grouping by PRN and dense tap grid.
Each test run's texture model was trained only from other normal-quality runs;
the test run never trained itself. PRN10 was excluded because it has only one
run. Twenty-two references received independent models, of which 18 were
normal-quality references shared with the previous baseline.

The first trajectory result is mixed but useful:

- moving H1 median P90 improved from 4.06 m to 2.32 m;
- equal-power destructive-phase reliability improved from 4/18 to 11/18;
- weak path1 at -6 dB regressed from 13/18 to 9/18, mainly at low CN0;
- 24/36 moving cases had lower P90 than the unwhitened baseline.

This means whitening exposes merged equal-power structure but does not yet
generalize weak-path texture across sessions. It is not a finished tracker.

Existence detection is much stronger. The pre-Doppler-guard texture GLRT peak
was evaluated separately from trajectory recovery. Labels are:

- H0: path1 absent (`moving_absent`);
- H1: path1 present, including moving and static cases.

Across 18 normal H0 controls, median GLRT scores were 9.26--11.67 dB. Across 54
H1 cases, 53 scored at least 12.16 dB. The empirical AUC was 0.999. A provisional
threshold between 11.67 and 12.16 dB gives 0/18 false alarms and 53/54
detections on this leave-one-run-out set. The sole miss was the lowest-CN0 PRN5
static weak-path case.

Do not hard-code that threshold yet. The set is small and derived from A-only
texture injection. The next required step is B-only-texture strengthening:
inject or compose the second source using measured B-only residual/kernel
texture, rerun the same H0/H1 protocol, and calibrate the threshold with
confidence intervals. Geometry confidence remains diagnostic only.

The `11.67..12.16 dB` provisional split above used the original unbounded
Doppler map. It is retained as historical evidence only. The current score
uses the physically bounded Doppler map described below; the old numerical
threshold must not be reused.

Reproduction:

```text
python3 dev_notes/sim/prepare_path0_texture_loo.py --summary <old-summary.csv> --output-dir <loo-dir>
python3 dev_notes/sim/run_trackb_cross_reference_benchmark.py --manifest <loo-dir>/manifest.csv --output-dir <loo-dir>/results --duration-s 20
```

NUC artifacts:

```text
/home/bupt/lya/gnss_data/trackb_glrt_loo_0731/
```

## B-Only Texture Strengthening

**Date:** 2026-07-31
**Author:** Codex

The synthetic path1 can now use a measured B-only coherent kernel and optional
slow residual texture. Its historical absolute code phase is removed. The
measured local profile is shifted and phase-modulated by the new known
geometry, so the injected delay remains ground truth.

Three implementation faults were found and corrected during the real-texture
smoke test:

1. injecting every B-only residual epoch duplicated receiver thermal noise;
   the default is now the coherent B-only kernel, while smoothed and raw-epoch
   residual modes remain explicit experiments;
2. the whitened map had already removed path0, but candidate extraction still
   treated the map maximum as path0 and masked it. That maximum was commonly
   path1, so the old code suppressed the desired signal;
3. a short locked texture segment compressed the full receiver trajectory into
   the available time. Geometry now keeps the requested trajectory duration
   and uses only the physically elapsed prefix.

The texture-aware candidate search is limited to `+/-20 Hz` relative Doppler.
For an L5 walking receiver this is a conservative physical bound and rejects
known `48--50 Hz` tracking-texture lines. It is not selected from injected
delay truth.

### Same-PRN A/B result

Eight normal-quality A/B references from PRN11, PRN23, and PRN28 passed the
minimum-duration gate. With the measured B-only coherent kernel:

- moving -6 dB: 8/8 `RELIABLE`, median P90 1.74 m;
- moving equal-power destructive: 8/8 `RELIABLE`, median P90 1.15 m;
- path-absent: 0/8 false `RELIABLE`;
- existence GLRT: AUC 1.0, H0 max 10.87 dB, H1 min 16.44 dB.

The smoothed residual mode also passed 8/8 and had no consistent advantage.
It is therefore not the default. Against the current ideal-path1 control, the
B-only kernel slightly worsened median -6 dB P90 (1.46 to 1.74 m) and improved
equal-power P90 (1.52 to 1.15 m). Its value is a more faithful stress test, not
an artificial claim of universal accuracy gain.

### Low-CN0 boundary

The wide B-only kernel was resampled onto the Phase A narrow tap grid for a
cross-PRN stress test. This is not a same-PRN deployment claim.

- measured CN0 about 45 dB-Hz and above: moving -6 dB 8/8 and equal-power 8/8
  `RELIABLE`;
- measured CN0 about 40 dB-Hz: moving -6 dB 0/2 and equal-power 1/2;
- at the lowest CN0, H1 GLRT scores overlap the path-absent H0 distribution.

The current full 18-reference rerun gives moving -6 dB 16/18 and equal-power
17/18. At measured CN0 >=45 dB-Hz, existence AUC is 1.0 with H0 max 11.16 dB
and H1 min 16.22 dB. Including the lowest-CN0 runs removes that clean margin.

Decision:

- use the coherent B-only kernel as the default strengthened benchmark;
- do not hard-code one global GLRT threshold;
- calibrate likelihood by CN0/noise condition;
- below the validated work envelope, return `INSUFFICIENT/UNDECIDED` rather
  than force a path decision;
- proceed to known-truth moving-simulator trajectory capture before OTA.

NUC artifacts:

```text
/home/bupt/lya/gnss_data/trackb_btexture_0731/
/home/bupt/lya/gnss_data/trackb_glrt_loo_0731/results_current/
```

## Moving-Simulator Capture Means Virtual Motion

**Date:** 2026-07-31
**Author:** Codex

The simulator, combiner, B210, and capture server do not move. The next
known-truth experiment moves a virtual receiver by programming a time-varying
relative range into the two RF outputs.

There are two evidence tiers:

1. known-delay trajectory: only the relative delay is commanded. This is the
   next, simplest algorithm validation and is sufficient because the estimator
   observes relative path delay;
2. geometry-faithful trajectory: define fixed source coordinates and a virtual
   receiver route, then compute both source-to-receiver ranges at every epoch.
   This follows after the known-delay ramp passes.

The first recommended trajectory is:

```text
A compensation: 0 m
B compensation: 7 m -> 22 m in 30 s -> 7 m in 30 s
relative range rate: +/-0.5 m/s
L5 relative Doppler: approximately -/+1.96 Hz
```

This remains inside `0.24..0.75 chip`, crosses the sub-chip region, and has
known delay, rate, reversal time, and Doppler sign. "Known position" does not
mean physically surveying the instruments. For the geometry-faithful tier it
means an arbitrary local ENU frame, for example fixed sources at
`(-15,0)` and `(15,0)` m and a commanded receiver route. The simulator's route
speed or the delay-ramp slope controls velocity; no operator walking speed is
used.

Before capture, verify that the hardware can provide one of:

- per-output time-varying pseudorange compensation or a trajectory file;
- two independently delayed RF outputs from one shared-clock simulator;
- synchronized scheduled playback with exported per-epoch range logs.

Applying the same ordinary GNSS receiver trajectory to both simulators is not
enough if it leaves their relative delay constant.

The current two simulators do not share 10 MHz. Their relative clock contributes
an unknown offset and drift to the commanded geometric delay and Doppler.
Therefore:

- record A-only and B-only static baselines immediately before and after the
  A+B run;
- save both simulators' start time and per-epoch compensation logs;
- compare trajectory shape/rate after clock-offset calibration;
- do not claim absolute meter-level ground truth unless a common clock,
  same-clock dual output, or independently measured clock correction is
  available.

If the simulators cannot accept a dynamic per-channel delay/trajectory, the
current fixed hardware cannot perform this known-truth virtual-motion tier.
The fallback is not to move the simulators: use a same-clock multi-output
source, add programmable RF delay, or postpone to a physically moving B210 with
external trajectory truth.

## Simulator Motion UI and Spatially Assisted Static Mode

**Date:** 2026-07-31
**Author:** Codex

### Simulator UI finding

Static inspection of the `RpsNetCtrl_4000-yazhi2025-8-19.exe` controller in
the `NSF4000 tool` directory found controls for:

- constant-velocity spoofing with east/north/up velocity and duration;
- start/stop real-time trajectory;
- distance compensation and trajectory mode;
- start/stop trajectory spoofing;
- an on-screen log list.

This makes constant-velocity spoofing a plausible source of virtual motion,
but it is not yet a verified ground-truth delay generator. It changes a
navigation trajectory, while the estimator needs the per-PRN relative delay
between simulator A and simulator B. Before a formal capture:

1. hold A static and run constant-velocity spoofing on B only;
2. verify that the target PRN's displayed `PR1` changes linearly and calculate
   its measured slope;
3. verify whether the on-screen log contains the command time, velocity,
   duration, and per-epoch position/range;
4. save the controller traffic to TCP port 90 as a `pcapng` file so that the
   motion-command timestamp is preserved;
5. synchronize the Windows controller and NUC clocks before the run.

The local controller directory does not currently contain a non-empty exported
trajectory log. Until an export or packet-level timestamp is available, the
motion start must not be treated as exact truth.

The controller can operate only one simulator at a time. That does not prevent
the pilot: configure and start static A, disconnect the controller, start raw
capture, connect to B, and then start B motion. A continuous raw capture must
cover a static pre-roll, the complete motion interval, and a static post-roll.

### Decision on two-channel B210

The two-channel direction is accepted as a separate **spatially assisted static
mode**. It complements Track B motion; it does not replace it.

The useful model is not "two independent MEDLL results." Stack the complex
dense correlators from both RF channels:

```text
y = c0 q0(theta0, tau0) + c1 q1(theta1, tau1) + n
```

For this controlled DAS experiment, do not initially estimate both unknown
angles with a two-element array. Two sensors and two coherent sources leave no
noise-subspace margin and make unconstrained DOA estimation fragile. Instead:

- collect A-only and B-only at the final antenna geometry;
- measure the complete complex spatial-delay templates `qA(tau)` and
  `qB(tau)`;
- use those measured templates in a one-source versus two-source GLRT;
- refine accepted two-source candidates with constrained joint ML;
- report `RELIABLE`, `MARGINAL`, `UNRESOLVED`, or `NO_SECOND_SOURCE`.

This is more defensible than ideal steering-vector-only MUSIC, and it directly
reuses the current measured-kernel and texture-aware GLRT work.

Adding dense taps alone is not super-resolution. HRC is a useful tracking-error
baseline, but the path-separation candidates are joint space-delay ML, SAGE, or
MSBL/SBL initialization followed by ML. The first implementation should be the
smallest constrained joint GLRT/ML model, not MUSIC or a large sparse Bayesian
solver.

### Existing software support and missing work

The current code already supports a multi-output UHD source:

```text
SignalSource.RF_channels=2
SignalSource.subdevice=A:A A:B
SignalSource.freq0=1176450000
SignalSource.freq1=1176450000
Channel0.RF_channel_ID=0
Channel1.RF_channel_ID=1
```

`UhdSignalSource` creates one UHD streamer with both channel indices, and
`GNSSFlowgraph` maps each output to a signal conditioner using
`ChannelN.RF_channel_ID`. The current L5 generator, recorder, and dense
correlator workflow remain single-RF-channel oriented and need explicit
two-channel integration and tests.

The B210 channels are simultaneously streamable, but that does not mean their
complex phases are pre-calibrated. UHD documents a random frontend phase offset
after tuning and phase drift over time. Every measurement session therefore
needs a complex channel calibration, and calibration must be rechecked after a
retune, restart, cable change, or material temperature change.

There is also a receiver-side phase-reference trap. If each RF stream is
processed by an independent tracking PLL, the two carrier NCOs can absorb the
spatial phase difference. Two complex dense dumps cannot simply be stacked
unless their accumulated carrier phases are used to restore a common phase
reference. The preferred first prototype is offline:

- record both raw RF streams with one synchronized UHD streamer;
- acquire and track on RF channel 0;
- apply channel 0's common code/carrier hypothesis to both RF streams;
- generate both dense complex profiles under that shared reference;
- apply the measured inter-channel calibration before joint estimation.

This preserves the spatial phase by construction and avoids changing the
real-time tracking loop before the observation model is validated.

### Required experiment order

1. **Cabled two-channel feasibility, no spatial claim.** Split one composite RF
   input into both B210 RX2 ports. Record both channels in one streamer and
   measure sample alignment, overflow rate, complex gain, group delay, and
   phase stability. Repeat after restart and retune.
2. **Wideband complex calibration.** Estimate frequency-dependent
   `G21(f)=Y2(f)/Y1(f)`, not only one scalar phase. Require stable calibrated
   cross-channel residuals over a 30 s run.
3. **Single-source spatial templates.** In a controlled RF environment, use two
   receive antennas separated initially by about `lambda/2` (`12.7 cm` at L5).
   Capture A-only and B-only for every tested geometry. A cable combiner followed
   by a splitter cannot create spatial diversity.
4. **Zero-delay spatial control.** Set the two sources to the same code delay
   but different arrival directions. The two-source GLRT must beat the
   one-source model without using delay separation.
5. **Delay ladder.** Test `1.5, 1.0, 0.75, 0.5 chip`, then only after passing,
   attempt `0.3 chip`. Sweep angle separation, power ratio, phase, and CN0.

Do not start the joint estimator before steps 1 and 2 pass. At 20 Msps,
two-channel `sc16` is approximately 160 MB/s before file-system overhead, so a
5 s `/dev/shm` smoke test precedes every 30 s capture.

### What counts as success

Two channels can improve static `0.5 chip` identifiability only when the
measured spatial signatures are sufficiently different. The result must be a
condition map, not a universal claim:

- detection probability at fixed false-alarm rate;
- delay-difference RMSE and power-ratio error;
- model-selection false alarms on A-only and B-only;
- fraction correctly returned as `UNRESOLVED`;
- sensitivity to angle separation, array orientation, CN0, power ratio, phase,
  restart, and calibration age.

The current research hypothesis is:

> Measured two-channel spatial-delay templates plus constrained joint GLRT/ML
> can materially improve static same-code `0.5 chip` separation over the
> single-channel texture-aware baseline when the two source signatures are
> linearly distinguishable.

This is plausible and testable. It is not yet a demonstrated capability, and it
does not imply that two channels can resolve equal-direction or poorly
calibrated sources.

Primary references:

- Ettus UHD device synchronization:
  https://files.ettus.com/manual/page_sync.html
- Ettus UHD multi-channel streamer configuration:
  https://files.ettus.com/manual/structuhd_1_1stream__args__t.html
- Chang et al., joint angle-delay MSBL and SAGE refinement:
  https://doi.org/10.1007/s10291-020-01072-0
- Rougerie et al., array SAGE/STAP for GNSS multipath:
  https://doi.org/10.1155/2012/804732
- Chang et al., sparse spatial-temporal GNSS estimation:
  https://doi.org/10.1109/PLANS46316.2020.9109852

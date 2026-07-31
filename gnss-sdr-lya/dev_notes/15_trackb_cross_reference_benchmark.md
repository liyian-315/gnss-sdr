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

Reproduction:

```text
python3 dev_notes/sim/prepare_path0_texture_loo.py --summary <old-summary.csv> --output-dir <loo-dir>
python3 dev_notes/sim/run_trackb_cross_reference_benchmark.py --manifest <loo-dir>/manifest.csv --output-dir <loo-dir>/results --duration-s 20
```

NUC artifacts:

```text
/home/bupt/lya/gnss_data/trackb_glrt_loo_0731/
```

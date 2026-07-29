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

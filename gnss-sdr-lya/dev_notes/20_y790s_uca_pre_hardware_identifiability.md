# Y790s pre-hardware array identifiability budget

**Date:** 2026-08-12

**Branch:** `research/y790s-8ch-space-delay`

**Starting SHA:** `767fa64f8265b174ccfc291cb668ad8ffa93295e`

**Evidence ceiling:** **[理想仿真]**, or **[纹理合成]** only when a measured
Phase A/B input is explicitly named. This report is a design budget, not an
experiment result. It does not validate Y790s, eight-channel coherence, real
0.5-chip separation, a 30-degree boundary, or a final five-degree requirement.

## Scope and reproducibility

This round implements arbitrary `array_xyz_m` horizontal-azimuth steering,
preserves the legacy four-element ULA convention, adds the theoretical 8-UCA
A0 scan, and separates the synthesis truth gain from the estimator manifold.
It runs H1/H2 only. It does not implement a driver, real-time C++, MUSIC/MVDR,
H3/H4, elevation fitting, or a large optimizer.

The theoretical reference is eight uniformly spaced elements at radius
`0.162 m`, L5 wavelength `0.2548 m`. This is not the actual four-physical-element
dual-feed hardware geometry described by doc19 v1.1. Actual processing must use
the measured/vendor `array_xyz_m`; the existing unconfirmed placeholder fails
fast.

Reproduce from `gnss-sdr-lya`:

```bash
python dev_notes/sim/analyze_uca_identifiability.py --self-test
python dev_notes/sim/fit_space_delay_twosource.py --self-test
python dev_notes/sim/analyze_uca_identifiability.py \
  --output-dir dev_notes/sim/y790s_uca_pre_hardware \
  --run-sensitivity --realizations 8 --seed 7908
```

To complete the measured-kernel layer, repeat `--kernel` for at least two
TRUSTWORTHY Phase A CSVs. No such CSV, A-only/B-only dense file, or manifest
exists in this checkout or the local project data roots. The NUC absolute paths
recorded in docs 11/15 are not mounted here. Consequently the measured temporal,
joint, and faithful-texture rows are deliberately `NOT_RUN_MISSING_INPUT`; an
ideal triangular/L5-like kernel is not substituted as the main result.

## Q1 — ideal 8-UCA at 0.5 chip

The spatial part is available now. The median equals the min/max to numerical
precision for 5--40 degrees; at larger separation the finite eight-element
sampling shows a small absolute-bearing ripple.

| delta az | mu spatial min / median / max | spatial-only cond median |
|---:|---:|---:|
| 60 deg | 0.390 / 0.396 / 0.405 | 1.520 |
| 40 deg | 0.156 / 0.157 / 0.157 | 1.171 |
| 30 deg | 0.185 / 0.185 / 0.185 | 1.206 |
| 20 deg | 0.574 / 0.574 / 0.574 | 1.921 |
| 10 deg | 0.882 / 0.882 / 0.882 | 4.001 |

`mu_temporal(0.5 chip)`, `mu_joint`, and the joint design condition number are
`N/A — NOT_RUN_MISSING_INPUT`. They depend on the measured Phase A L5 kernel.
The analysis code computes them as
`mu_joint = mu_spatial * mu_temporal` and emits the requested angle-delay maps
when measured kernels are supplied, but inventing numbers here would violate
the evidence boundary.

At `delta az=0`, `mu_spatial=1`, the two spatial columns are identical, the
condition number is infinite, and the smallest singular value is numerically
zero. This is a degeneracy diagnostic, not a universal statement about the
temporal axis.

## Q2 — four-element ULA versus theoretical 8-UCA

**[理想仿真]** The UCA removes the ULA's strong orientation dependence over
small/moderate separation: at 10 degrees the UCA spatial coherence is about
`0.882` for every absolute bearing, whereas the ULA range is `0.822..1.000`.
At 30 degrees the UCA is about `0.185`; the ULA range is `0..1` with median
`0.343`. Thus the UCA offers much more uniform 360-degree coverage, not a
monotonic guarantee that every larger angular difference is always better.
For example, this finite-radius UCA has median coherence `0.157` at 40 degrees
but `0.396` at 60 degrees; sidelobe structure matters.

The old four-ULA `absolute az=0 deg, delta az=30 deg` result has
`mu_spatial=2.9e-16`, condition number `1.0`: it is an exactly orthogonal,
especially favorable geometry. It must not be used as an 8-UCA expectation.
Also, doc19 v1.1 says the target hardware has four physical spatial positions,
not eight; neither ideal curve is a hardware capability prediction until the
actual four-element XYZ is supplied.

## Q3 — phase-error sensitivity of 0.5-chip H1/H2

**[理想仿真]** The synthesis truth uses perturbed per-channel gains while the
estimator retains the ideal manifold. There are eight fixed-seed realizations
per level, `-6 dB` path1, ideal built-in kernel, and a coarse truth-independent
search over both absolute delays. The legacy `3/6 dB` and `mu_max=0.98` gates
are **PROVISIONAL**.

| fixed phase RMS | H1→H2 improvement median | delay-error P90 | nominal RELIABLE |
|---:|---:|---:|---:|
| 0 deg | 11.50 dB | 0.10 chip | 8/8 |
| 2 deg | 11.52 dB | 0.10 chip | 8/8 |
| 5 deg | 10.79 dB | 0.13 chip | 8/8 |
| 10 deg | 8.63 dB | 0.13 chip | 8/8 |
| 20 deg | 5.04 dB | 0.13 chip | 0/8 |
| 30 deg | 3.15 dB | 0.16 chip | 0/8 |

Delay proximity alone is not success. The single-source control exposes a
fatal calibration limitation: with the same broad H2 search, the provisional
threshold false-positive fraction is `8/8` at 0, 2, and 5 degrees and `3/8` at
10 degrees. It falls at high mismatch only because mismatch degrades H2 itself;
that is not useful specificity. Therefore the nominal decision column cannot
be used as a probability-of-detection claim or hardware threshold. Thresholds
must be calibrated from truth-free single-source controls before A1 supports a
budget. The full CSV also records amplitude error, `mu_joint`, condition number,
decision counts, mismatch level, and false positives.

Slow random-walk drift is implemented as a per-channel smooth cumulative walk,
normalized to the requested RMS over the 12-block run (channel 0 fixed). Its
median improvement declines from `11.41 dB` at zero to `8.27 dB` at 10 degrees
and `4.97 dB` at 20 degrees. This differs from independent snapshot white noise
and is recorded in metadata/code.

## Q4 — provisional hardware phase focus

The only defensible wording is:

> **simulation-derived provisional budget:** prioritize vendor/G0 tests of
> calibratable fixed phase and within-run drift in the roughly `0..10 deg RMS`
> region. The ideal mismatch trend begins a material H1→H2 degradation near
> 5--10 degrees and is near/below the provisional 6 dB line by 15--20 degrees.
> This is a test-focus range, not a final hardware standard. No acceptance limit
> can be set until actual four-element XYZ, measured Phase A kernels, faithful
> A/B texture, and truth-free single-source threshold calibration close the loop.

This does not preselect five degrees as the final requirement. The present A1
false-positive failure prevents a tighter numerical standard.

## Q5 — most dangerous error class

Within this limited **[理想仿真]** experiment, fixed phase bias and slow drift
are the clearest hazards: both directly reduce the H1→H2 residual margin, with
fixed 30-degree RMS reaching `3.15 dB` and 20-degree run drift reaching
`4.97 dB`. Combined amplitude/phase complex-manifold mismatch is milder over
the scanned 1--15% axis (`11.60` to `7.80 dB` median), but this comparison is
not a universal ranking because its percentage axis is a model definition, not
an engineering tolerance. Real mutual coupling, position error, feed response,
and texture are untested; “manifold mismatch” may become dominant on hardware.

## Faithful texture sensitivity

| requested case | status | reason |
|---|---|---|
| single source | NOT RUN | no A-only dense texture locally |
| 0.5 chip; 60/40/30/20/10 deg; 0/-6 dB | NOT RUN | no A-only/B-only dense texture or manifest locally |
| phase RMS 0/2/5/10/20 deg across PRNs/references | NOT RUN | no measured references locally |

These rows cannot be labeled **[纹理合成]** until the inputs are actually used.

## Decision and remaining limitations

Result: **`A0_BASELINE_COMPLETE_WITH_LIMITATIONS`**.

- A0 spatial geometry, ULA regression, UCA rotational sanity, degeneracy,
  conditioning trend, fixed-seed reproduction, and truth/model independence are
  complete.
- Measured temporal/joint A0 and faithful texture are blocked only by missing
  external data inputs. The tool is ready to consume multiple references.
- A1 no longer requires truth initialization and searches both absolute delays,
  but the coarse grid remains a benchmark skeleton. It has no measured kernel,
  no measured texture, and its provisional thresholds fail the single-source
  control. A1 cannot set a hardware threshold.
- Matched ideal temporal kernel remains in the sensitivity-only A1 run. Truth
  and estimator spatial manifolds are independent under error, but real joint
  template mismatch is not represented.

The next task may start only after the missing TRUSTWORTHY kernel CSVs and
A/B-only dense/manifest inputs are made available, or if the next task is
explicitly scoped to truth-free H1/H2 threshold calibration. This result is not
permission to enter real Y790s Gate 0.

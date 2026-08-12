# H1/H2 single-source false-positive red-team review

**Date:** 2026-08-12

**Reviewed SHA:** `fa6c6c641b56120b765a10ee899098371d81fc7b`

**Scope:** diagnosis only. No H3/H4, MUSIC, MVDR, SAGE, driver, or new
estimation feature was developed. One confirmed floating-point boundary bug was
fixed minimally after preserving before/after evidence.

## Verdict

Root-cause verdict: **`OFF_GRID_SOURCE_SPLITTING_DOMINANT`**

Review verdict: **`RED_TEAM_PASS_WITH_FIX_REQUIRED`**

The current 8/8 single-source false detections are principally caused by the
coarse H1 dictionary failing to represent the off-grid truth `(az=17 deg,
tau=0.07 chip)`. H2 then uses two discrete atoms to approximate that one
continuous source. The provisional 6 dB threshold exposes the mismatch but is
not its cause. H2's larger search and parameter count are secondary risks, not
the dominant explanation in this case: matched on-grid H0 remains clean, and
the off-grid improvement survives frozen-support hold-out.

Do not continue to real 0.5-chip validation until H1 has observation-only
continuous/local refinement and the refined H1 is compared fairly with H2,
followed by empirical H0 threshold/model-order calibration on held-out
single-source data.

## Reproduction

At the reviewed SHA, before any edit:

```bash
python dev_notes/sim/analyze_uca_identifiability.py --self-test
python dev_notes/sim/fit_space_delay_twosource.py --self-test
python dev_notes/sim/analyze_uca_identifiability.py \
  --output-dir <tmp> --run-sensitivity --realizations 8 --seed 7908
```

The 0.5-chip/30-degree two-source baseline remained `15.6 dB, RELIABLE`.
All six committed sensitivity CSV/JSON files reproduced byte-for-byte. The
reported low-error single-source `8/8` false detections also reproduced.

Red-team diagnostics:

```bash
python dev_notes/sim/diagnose_h1_h2_false_positive.py --self-test
python dev_notes/sim/diagnose_h1_h2_false_positive.py \
  --output-dir dev_notes/sim/y790s_h1_h2_redteam --realizations 200
```

The diagnostic's fast support search is checked against the reviewed estimator
for improvement, coherence, condition number, and state before use.

## On-grid versus off-grid experiment

Eight seeds per case, 12 snapshots, theoretical 8-UCA, same ideal kernel:

| case | H1 residual median | H2 residual median | coarse improvement | refined-H1 improvement | state |
|---|---:|---:|---:|---:|---|
| A: on-grid, no noise | numerical zero | numerical zero | 0 dB after guard | 0 dB | NO_SECOND_SOURCE 8/8 |
| B: off-grid, no noise | 23.597 | 2.214 | 10.277 dB | -103.221 dB | RELIABLE 8/8 before refinement |
| C: on-grid, noise 0.03 | 2.650 | 2.635 | 0.027 dB | 0.026 dB | NO_SECOND_SOURCE 8/8 |
| D: off-grid, noise 0.03 | 26.126 | 4.848 | 7.297 dB | -2.617 dB | RELIABLE 8/8 before refinement |

Case B proves source splitting without noise: H2 is not detecting a random
noise feature. It is approximating one off-grid source with two dictionary
atoms. The observation-selected H1 point is `(20 deg, 0.1 chip)`; truth-free
Nelder-Mead refinement converges to approximately `(17 deg, 0.07 chip)` and
removes more than 9.9 dB of apparent H2 advantage in the noisy case. No truth
value initializes the refinement.

## H2 atom inspection

For all eight canonical off-grid seeds, H2 selects:

```text
atom 0: az=20 deg, tau=0.0 chip
atom 1: az=10 deg, tau=0.3 chip
median amplitude1/amplitude0 ~= -8.1 dB
mu_joint ~= 0.836
```

Thus the pattern is a main atom near the source plus a weaker cross-angle,
delayed residual atom. It does not bracket truth only along one coordinate, but
it clearly uses two atoms to fit one source's joint angle-delay interpolation
error. The second amplitude is not numerically negligible.

## Grid-resolution scan

Truth remains `(17 deg, 0.07 chip)`, noise is 0.03, 20 seeds. The two axes are
scanned separately to keep the H2 candidate count bounded.

| scan | step | H1 residual median | improvement median | existence FA |
|---|---:|---:|---:|---:|
| angle | 10 deg | 26.309 | 7.297 dB | 100% |
| angle | 5 deg | 13.864 | 5.422 dB | 100% (MARGINAL) |
| angle | 2 deg | 6.271 | 3.195 dB | 100% (MARGINAL) |
| angle | 1 deg | 3.849 | 1.346 dB | 0% |
| delay | 0.10 chip | 26.309 | 7.297 dB | 100% |
| delay | 0.05 chip | 25.678 | 7.201 dB | 100% |
| delay | 0.02 chip | 25.270 | 7.124 dB | 100% |
| delay | 0.01 chip | 25.149 | 7.104 dB | 100% |

Finding: **`OFF_GRID_SOURCE_SPLITTING`**. Angle refinement is decisive in this
specific geometry; delay-only refinement is insufficient. A finer fixed grid
is diagnostic evidence, not the recommended implementation: continuous/local
H1 refinement is simpler and avoids an explosive H2 grid.

## H0 Monte Carlo and false-positive semantics

There are 200 realizations per condition for on/off-grid truth, noise
`0.01/0.03/0.05`, and fixed phase mismatch `0/5/10 deg RMS`: 3600 H0 scenes.
Quantiles below show the current noise `0.03` subset.

| grid | phase RMS | improvement q50/q90/q95/q99 dB | existence FA | ambiguous | clean rejection |
|---|---:|---:|---:|---:|---:|
| on | 0 deg | 0.025 / 0.031 / 0.033 / 0.036 | 0% | 0% | 100% |
| on | 5 deg | 0.794 / 1.594 / 1.804 / 2.143 | 0.5% | 0% | 99.5% |
| on | 10 deg | 0.981 / 2.101 / 2.546 / 4.489 | 3.0% | 0% | 97.0% |
| off | 0 deg | 7.328 / 7.403 / 7.420 / 7.459 | 100% | 0% | 0% |
| off | 5 deg | 4.965 / 6.167 / 6.482 / 7.394 | 100% | 0% | 0% |
| off | 10 deg | 2.598 / 4.914 / 5.311 / 5.698 | 39.0% | 0% | 61.0% |

`existence FA` is `RELIABLE + MARGINAL`; `ambiguous` is `UNRESOLVED`;
`clean rejection` is `NO_SECOND_SOURCE`. No Monte Carlo condition produced an
`UNRESOLVED` result. The original aggregate false-positive definition therefore
did not inflate the cited 8/8 through ambiguous states.

The 6 dB threshold is not a calibrated false-alarm threshold. It is also not
the core cause: moving it above 7.5 dB would hide this particular noise=0.03
case, but off-grid H0 reaches about 9.9 dB at lower noise, and the distribution
changes with mismatch and grid. Threshold calibration must follow fair H1/H2
modeling; it cannot repair H1 misspecification.

## Hold-out diagnosis

Support is selected on snapshots 0--5. That support is frozen on snapshots
6--11; only complex amplitudes are re-estimated.

| case | training improvement median | validation improvement median |
|---|---:|---:|
| on-grid, noise 0.03 | 0.030 dB | 0.015 dB |
| off-grid, no noise | 10.277 dB | 10.277 dB |
| off-grid, noise 0.03 | 7.279 dB | 7.332 dB |

The off-grid H2 advantage does not disappear on validation. This rejects
“H2 merely memorized training noise” as the dominant explanation. Search
overfit remains a secondary model-selection concern, especially under real
texture, but the observed failure is systematic dictionary mismatch.

## Implementation and fairness audit

No root-cause implementation bug was found in the main linear algebra:

- H1 and H2 consume exactly the same `dense` data and flattened observations.
- Both use the same angle grid. H1 delay support is the union of the H2
  `tau0_grid` and `tau1_grid`, so H1 is not given a narrower delay dictionary.
- H2 is constrained asymmetrically: source 0 comes from `tau0_grid`, source 1
  from `tau1_grid`, with `tau1 > tau0`. This is intentional but means H2 is not
  a fully symmetric two-source model.
- Neither H1 nor H2 explicitly normalizes templates before LS. This is fair
  because complex LS is invariant to nonzero column scaling. The condition
  number is therefore the condition number of the actual unnormalized design;
  for equal-energy Kronecker templates it matches the normalized closed form.
- `_residual` agrees with per-snapshot `np.linalg.lstsq`: maximum coefficient
  discrepancy `3.4e-16`, residual discrepancy zero.
- `dense.reshape(B,-1)` ordering matches `kron(a,r)` because synthesis uses
  `outer(a,r)` with `[antenna,tap]` C-order flattening.
- Complex pseudoinverse and residual-energy calculations are correct.
- `amp_ratio_db` can be numerically misleading when the second coefficient is
  tiny; it must not be interpreted for rejected H2. In the off-grid false
  detections it is approximately -8.1 dB, so that caveat does not explain them.

### Confirmed numerical bug and minimal fix

**BUG CONFIRMED:** when both H1 and H2 residuals are at floating-point zero,
the old `10*log10(res_h1/max(res_h2,1e-30))` could amplify rounding order. In
one of eight on-grid/no-noise seeds it reported `154.9 dB, RELIABLE`; other
seeds reported large negative values. This is a numerical exact-fit boundary,
not the cause of the noisy off-grid 8/8 failure.

The minimal fix adds an energy-relative numerical-zero guard. Direct-estimator
before/after values are preserved in `numerical_guard_before_after.csv`:
unfixed improvement spans `-2.13..6.16 dB`, with one of eight exact-fit controls
incorrectly `RELIABLE`; afterward all eight report `0 dB, NO_SECOND_SOURCE`.
The existing noisy self-test output is unchanged.

## Required answers

1. **Why 8/8?** H1 is off-grid and leaves a deterministic joint manifold
   residual; H2 splits one source across two atoms and removes most of it.
2. **Is 6 dB the core problem?** No. It is provisional and uncalibrated, but
   threshold-only adjustment masks rather than fixes the misspecified H1.
3. **How much does local H1 refinement remove?** In the canonical noisy case,
   improvement changes from `+7.297` to `-2.617 dB`, over `9.9 dB` removed. In
   noiseless off-grid data it changes from `+10.277` to `-103.221 dB`.
4. **Does H2 use two atoms for one source?** Yes: consistently `(20,0.0)` plus
   `(10,0.3)`, with the second about -8.1 dB.
5. **Does improvement survive hold-out?** Yes: `7.279 dB` training versus
   `7.332 dB` validation for the current noisy off-grid case.
6. **Next action:** first **B**, add observation-only continuous/local H1
   refinement; then **C**, compare H1/H2 with a fair penalized or empirically
   calibrated model-order statistic and held-out H0 controls. Do not do A alone.
7. **Continue real 0.5-chip validation now?** No. A single real source will
   almost always be off any finite ideal grid, so the current benchmark can
   manufacture a second source before real texture/manifold mismatch is added.

Final verdict: **`RED_TEAM_PASS_WITH_FIX_REQUIRED`**.

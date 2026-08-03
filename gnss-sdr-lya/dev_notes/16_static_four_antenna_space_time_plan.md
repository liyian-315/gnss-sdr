# Static Four-Antenna Space-Time Separation Plan

**Date:** 2026-08-03
**Author:** Codex

## Decision

The project will pause moving-receiver capture and open a static spatial track:

> Four synchronized complex RF channels provide the new identifiability
> dimension; repeated time epochs improve statistical confidence but are not
> themselves a new separation dimension in a perfectly static same-clock scene.

This track targets static same-code two-source separation at `0.5 chip`. It
does not claim universal separation when the two sources have indistinguishable
spatial signatures.

The existing work is retained:

- dense complex correlator export remains the observation layer;
- Phase A measured kernels remain the temporal templates;
- faithful A-only/B-only textures remain the negative and positive controls;
- the texture-aware GLRT remains the model-existence gate;
- the confidence states remain `RELIABLE`, `MARGINAL`, `UNRESOLVED`, and
  `NO_SECOND_SOURCE`.

New work is limited to synchronized multi-RF ingestion, array calibration,
common-reference correlation, spatial templates, and joint space-delay
estimation.

## What Four Antennas Change

For two sources, two antennas provide only two spatial observations and almost
no redundancy. Four antennas provide two additional spatial degrees of freedom
for one-source versus two-source model comparison and calibration checks.

For a temporal template `r(tau)` and measured array response `a(theta)`, use:

```text
q(theta, tau) = a(theta) kron r(tau)
y_b = q(theta0, tau0)c0,b + q(theta1, tau1)c1,b + n_b
```

`b` is a short time block. Delay and direction support are shared across
blocks. Complex amplitudes may be block-dependent nuisance parameters. This
prevents independent-simulator clock drift from becoming the claimed
separation mechanism.

The normalized template coherence is an early identifiability metric:

```text
mu = abs(q0^H q1) / (norm(q0) norm(q1))
```

When `mu` is close to one, the result must be `UNRESOLVED` regardless of the
optimizer output. Four antennas are valuable only when their measured spatial
responses reduce this coherence relative to the single-channel temporal model.

## Hardware Architecture

### Preferred receiver

Use one native four-channel receiver with shared sampling clock and a
phase-calibratable RF architecture. An Ettus N310 is one example with four RX
channels, but the exact purchase choice must be made from a separate hardware
evaluation. Native four-channel capture reduces inter-device timing and phase
risk.

### Conditional two-B210 prototype

Two B210 units can be used only as an experimental prototype:

- distribute the same external `10 MHz` and `PPS` to both units;
- start all four channels with one timed UHD command;
- place the two units on independent USB 3 host controllers;
- calibrate complex gain, delay, and phase after every startup and retune;
- measure inter-device phase drift during every run;
- reject runs whose residual phase drift exceeds the sensitivity envelope
  established by simulation.

Common `10 MHz/PPS` aligns frequency and time but does not guarantee a
deterministic RF carrier phase. A continuous low-level calibration pilot may be
needed if pre/post calibration cannot track inter-device drift.

At L5 `20 Msps`, four-channel `sc16` produces about `320 MB/s` and `9.6 GB` per
30 s before metadata and analysis products. Every session starts with a 5 s
RAM-disk throughput test and explicit overflow check.

### Array geometry

Use identical antennas, equal-length cables, fixed gain, and a rigid measured
fixture.

1. First controlled proof: four-element ULA, `lambda/2 = 12.7 cm` spacing at
   L5. Its `1.5 lambda` aperture gives the strongest one-dimensional angular
   discrimination and the simplest calibration.
2. Deployment-oriented follow-up: `2 x 2` square array with `lambda/2`
   horizontal and vertical spacing. It supports two-dimensional spatial
   signatures but has a smaller aperture per axis.

The ULA has front/back and projection ambiguity. It is a research fixture, not
the final general-purpose array.

## Common-Reference Observation Pipeline

Do not run four independent PLLs and directly stack their complex correlators.
Independent carrier NCOs absorb the inter-antenna spatial phase.

The first offline pipeline is:

1. record four raw RF streams in one synchronized capture;
2. acquire and track the selected PRN on reference RF channel 0;
3. apply channel 0's code and carrier hypothesis to all four streams;
4. generate a `4 x K` complex dense profile for each epoch;
5. apply the measured frequency-dependent calibration `G_m(f)`;
6. form short blocks without taking magnitude first;
7. run one-source/two-source model comparison.

Long-time processing uses a multiple-measurement-vector model. It accumulates
likelihood or evidence across blocks with common angle-delay support. It must
not merely average magnitudes. If calibrated phase is proven constant, coherent
integration is an optional stronger mode, not the default assumption.

## Algorithm Roadmap

### A0: Measured-model identifiability

Before implementing a large optimizer, compute template coherence, design
matrix condition number, and a Fisher-information/CRLB approximation from
measured A-only and B-only templates. This predicts which geometries are
fundamentally weak.

### A1: Constrained joint GLRT and variable-projection ML

Start with known or tightly constrained source directions:

- `H1`: one measured space-delay template;
- `H2`: two measured space-delay templates;
- outer search: delay and a small direction neighborhood;
- inner solve: complex amplitudes by linear least squares for every block;
- decision: CN0-conditioned GLRT calibrated on single-source captures;
- uncertainty: profile likelihood, bootstrap, and cross-block consistency.

This is the primary baseline and the first route to a defensible `0.5 chip`
claim.

### A2: Sparse initialization and local refinement

Only after A1 passes real controls:

- use space-delay MSBL/SBL as a coarse multi-source initializer;
- apply off-grid delay refinement;
- optionally apply SAGE or local ML refinement.

Conventional MUSIC is a comparator, not the primary algorithm. The sources are
coherent and ordinary covariance MUSIC can lose rank. A four-element ULA can
support spatial smoothing, but smoothing reduces effective aperture and data
dimension.

## Experimental Gates

### Gate 0: Four-channel electronics

Split one strong source into all four RF inputs. Verify:

- equal sample count and deterministic epoch alignment;
- zero overflow in a 5 s and then 30 s run;
- frequency-dependent complex transfer calibration;
- phase/delay stability within a run;
- repeatability after restart and retune.

This gate makes no spatial-separation claim.

### Gate 1: Single-source spatial manifold

In a shielded or otherwise controlled RF environment, capture A-only over a
known angle grid. Repeat for B-only at the final geometry. Store the full
complex space-delay template, covariance, calibration ID, and array geometry.

The first ULA grid is `-60, -30, 0, 30, 60 deg`, with at least three runs per
angle. Densify the grid only if interpolation error is too high.

### Gate 2: Zero-delay spatial positive control

Set two same-code sources to `0 chip` delay difference and different arrival
directions. A joint spatial model must detect two sources at controlled false
alarm rate. Failure here means that `0.5 chip` testing is premature.

### Gate 3: Minimal 0.5-chip screen

Avoid a full factorial campaign. First fix measured CN0 near `52 dB-Hz` and
power ratio `-6 dB`, then test:

```text
delay_chip:       0, 0.5, 1.0
angle_difference: 0, 10, 30, 60 deg
runs:             3 per condition
```

This is 36 two-source runs plus single-source controls. It answers whether
spatial information materially improves the current static floor.

### Gate 4: Boundary map

Only after Gate 3 succeeds, expand around the transition:

```text
delay_chip:       0.3, 0.5, 0.75, 1.0
angle_difference: 5, 10, 20, 30, 60 deg
power_ratio_db:   0, -3, -6, -10
cn0_db_hz:        45, 52, 57
```

Use adaptive sampling rather than every Cartesian combination. Spend repeats
near the RELIABLE/UNRESOLVED boundary and include multiple PRNs and days.

## Acceptance Criteria

Compare the current single-channel texture-aware baseline with two-channel and
four-channel joint models at the same captures:

- probability of detecting a real second source;
- single-source false-alarm rate;
- delay-difference RMSE and power-ratio error;
- correct `UNRESOLVED` rate in degenerate geometries;
- robustness across PRN, day, restart, calibration, and array orientation;
- likelihood margin, template coherence, and condition number.

The initial research target is:

```text
delay:             0.5 chip
second source:     >= -6 dB
measured CN0:      >= 45 dB-Hz
angle difference: >= 30 deg in the first proof
P_D:               >= 90 percent
P_FA:              <= 5 percent
delay RMSE:        <= 0.1 chip
```

These are experiment gates, not a promised result. Same-direction sources and
poorly calibrated sessions are expected to remain `UNRESOLVED`.

## Work Packages and Stop Rules

1. four-channel hardware feasibility and throughput;
2. raw recorder plus complex calibration report;
3. common-reference four-channel dense correlator;
4. measured-manifold dataset and identifiability report;
5. constrained GLRT/ML baseline;
6. minimal screen and boundary map;
7. optional MSBL/SAGE comparison.

Stop or redesign before package 5 if four-channel phase cannot be calibrated
stably. Stop adding optimizer complexity if measured template coherence and
profile likelihood show that a condition is intrinsically multi-solution.

The largest risks are RF-channel calibration, coherent-source model mismatch,
and obtaining controlled spatial geometry. The previous dense-correlator,
kernel, faithful-texture, GLRT, and confidence work is directly reused and is
not discarded.

## References

- Ettus N310 four-channel architecture:
  https://files.ettus.com/manual/page_usrp_n3xx.html
- UHD device and frontend synchronization:
  https://files.ettus.com/manual/page_sync.html
- Rougerie et al., 2 x 2 array SAGE/STAP for GNSS multipath:
  https://doi.org/10.1155/2012/804732
- Konovaltsev et al., ML and hybrid beamforming for GNSS multipath:
  https://doi.org/10.1109/TSP.2004.842193
- Chang et al., joint angle-delay MSBL and SAGE refinement:
  https://doi.org/10.1007/s10291-020-01072-0
- Razgunas et al., experimental 2 x 2 GNSS SDR array:
  https://doi.org/10.1016/j.asr.2022.12.035
- Marathe et al., GNSS space-time processing distortion risks:
  https://doi.org/10.1155/2016/2154763

# Phase B Path0 Diagnostic Report

Date: 2026-07-29

Authors: Codex, for user + Claude handoff

## Purpose

This report closes the four priority tasks agreed after the PRN28/PRN11 real-data
failures:

1. Plot the real PRN28 +60 m fast-drift delay-Doppler maps and inspect whether a
   path1 peak exists near the expected calibrated delay (`~53 m`).
2. Build a faithful synthetic test so synthetic data no longer hides the real
   path0 failure mode.
3. Run a path0-removal diagnostic and decide whether path1 becomes uniquely
   visible.
4. Reframe the next research direction for the actual moving-receiver DAS goal.

The short answer:

```text
The expected path1 band is present as weak residual energy, but the current
snapshot dense-map methods do not make it uniquely identifiable. The blocker is
structured path0 residual / kernel mismatch, not a simple threshold problem.
```

## Priority 1: Real Delay-Doppler Map Diagnostic

Target data:

```text
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn28_delay60m_ratio_m6db_run3_30s_0728
/home/bupt/lya/gnss_data/phaseB_l5_twosource/prn28_delay60m_ratio_m6db_run4_30s_0728
```

Kernel:

```text
/home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn28_l5m50_amp64_run4_30s_0728/aonly_reference_Rtau.png.csv
```

Generated plots:

```text
.../prn28_delay60m_ratio_m6db_run3_30s_0728/delay_doppler_diagnostic_run3.png
.../prn28_delay60m_ratio_m6db_run4_30s_0728/delay_doppler_diagnostic_run4.png
```

Quantitative target-band check:

```text
PRN28 +60m run3:
  target band: 53 m +/- 5 m
  target-band delay median: 48.3 m, range 48.3..57.1 m
  target vs strongest off-ridge peak: median -31.3 dB, max -23.8 dB
  target-band SNR: median 13.9 dB

PRN28 +60m run4:
  target band: 53 m +/- 5 m
  target-band delay median: 54.9 m, range 48.3..57.1 m
  target vs strongest off-ridge peak: median -34.1 dB, max -33.0 dB
  target-band SNR: median 14.3 dB
```

Judgment:

The expected `~53 m` band is not empty, but it is deeply buried below path0
smear. The map is dominated by horizontal Doppler stripes that extend across
delay. There is no isolated path1 blob near `~53 m`.

This confirms that the original delay-Doppler extractor did not fail because of
a missing threshold. It failed because path0 is not cleanly confined to a single
Doppler ridge.

## Priority 2: Faithful Path0 Synthetic

New tool:

```text
dev_notes/sim/diagnose_faithful_path0_synthetic.py
```

Why it exists:

The earlier synthetic tests used an ideal path0:

```text
path0(tau,t) = c0(t) * K(tau)
```

That made path0 a clean static ridge. Real path0 contains tracking-loop wobble,
code jitter, carrier phase texture, and kernel mismatch. The faithful synthetic
therefore uses the real A-only dense tap vectors as path0 and injects a known
path1:

```text
faithful_synthetic(tau,t) = real_A_only_dense(tau,t)
                          + A1 * exp(j*2*pi*f*t) * K(tau - delay)
```

Command used on NUC:

```bash
python3 dev_notes/sim/diagnose_faithful_path0_synthetic.py \
  --path0-dense /home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn28_l5m50_amp64_run4_30s_0728/l5_aonly_dense_ch_0.dat.json \
  --kernel /home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn28_l5m50_amp64_run4_30s_0728/aonly_reference_Rtau.png.csv \
  --chip-m 29.3 --target-m 53 --target-band-m 5 \
  --ratio-db -6 --drift-hz 250 \
  --cn0-min 45 --lock-min 0.6 --min-lock-run 1000 --settle-epochs 200 \
  --max-epochs 20000 \
  --plot-prefix /home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn28_l5m50_amp64_run4_30s_0728/faithful_synth_53m_m6db_250hz
```

Results:

```text
Clean synthetic, after path0 removal:
  best delay: 52.7 m in all 10 segments
  target vs best: 0.0 dB
  target-band SNR: median 59.2 dB

Faithful path0 synthetic, before path0 removal:
  target vs best: median -33.0 dB
  target-band SNR: median 13.4 dB

Faithful path0 synthetic, after path0 removal:
  target-band delay median: 52.7 m, range 48.3..57.1 m
  target vs best: median -0.4 dB
  target-band SNR: median 17.2 dB
  but best off-ridge delay median: 63.0 m, range 32.2..85.0 m
```

Judgment:

This is the key evidence. The clean synthetic succeeds, but the faithful path0
synthetic reproduces the real-data failure mode:

- the target band becomes stronger after path0 removal;
- however, multiple non-target candidate delays remain competitive;
- delay consistency is not enough unless non-target residual peaks are also
  controlled.

Therefore, the old synthetic benchmark was misleading. Future synthetic tests
must include real path0 texture or they are not useful for validating near-delay
separation.

## Priority 3: Path0 Removal Diagnostic

New tool:

```text
dev_notes/sim/diagnose_path0_removal.py
```

Path0 model used:

```text
y_epoch(tau) ~= c0_epoch * K(tau - tau0_epoch)
```

with `tau0_epoch` searched over:

```text
-0.25:0.025:0.25 chips
```

Results on real PRN28 +60 m fast-drift:

```text
PRN28 +60m run3 before removal:
  target vs best: median -31.3 dB, max -23.8 dB
  target-band SNR: median 13.9 dB

PRN28 +60m run3 after removal:
  target vs best: median -0.4 dB, max 0.0 dB
  target-band SNR: median 17.2 dB
  best off-ridge delay range: -29.3..87.9 m

PRN28 +60m run4 before removal:
  target vs best: median -34.1 dB, max -33.0 dB
  target-band SNR: median 14.3 dB

PRN28 +60m run4 after removal:
  target vs best: median -2.0 dB, max -0.5 dB
  target-band SNR: median 16.4 dB
  best off-ridge delay range: -29.3..87.9 m
```

Judgment:

Path0 removal is directionally useful, because it raises the target band by about
30 dB relative to the dominant path0 smear. But it is not sufficient:

```text
Path1 is present as one strong residual candidate, but not as a unique residual
peak. Current path0 removal does not prove successful separation.
```

What failed:

- Per-epoch one-kernel subtraction leaves structured residual.
- The residual map still contains broad horizontal striping.
- Several delays compete with the expected target band.

What this teaches:

The next algorithm lever is not detector thresholding. It is better path0
modeling and stronger false-positive control.

## Priority 4: Moving-Receiver / Trajectory Reframe

The current two-simulator static snapshot is useful for controlled delay and
power-ratio injection, but it is not the same information geometry as the real
deployment.

Actual target scenario:

```text
fixed indoor DAS antennas + moving receiver + multiple same-code sources
```

If the receiver moves, each source should trace a time trajectory:

```text
delay_i(t), doppler_i(t), amplitude_i(t), phase_i(t)
```

This is better conditioned than asking one static correlation snapshot to
super-resolve two merged peaks. The useful information is not only the shape of
one peak at one time, but the fact that each source evolves consistently over
time according to geometry.

Recommended reframe:

```text
snapshot problem:
  y(tau) = sum_i A_i K(tau - tau_i)

trajectory problem:
  y(tau,t) = sum_i A_i(t) K(tau - tau_i(t)) exp(j phi_i(t))
  with tau_i(t), doppler_i(t), and amplitude_i(t) constrained to be smooth and
  geometry-consistent over receiver motion.
```

This suggests a Channel-SLAM-like research direction:

1. Track candidate paths over time, not only per epoch or per 2 s segment.
2. Use continuity of delay, Doppler, and amplitude as the main discriminator.
3. Treat static snapshot outputs as measurements with uncertainty, not as final
   truth.
4. Use known or estimated receiver motion to make source trajectories separable.
5. Report `UNRELIABLE / multi-solution` when the trajectory constraints do not
   separate sources.

Important caveat:

If the receiver is static, the sources are same-code, same-clock, same-frequency,
and the delay separation is below the effective bandwidth resolution, then 0.5
chip separation may be fundamentally underdetermined. A model can detect
deformation or estimate under strong priors, but it cannot guarantee unique
per-source pseudorange without extra diversity.

Extra diversity can come from:

- receiver motion;
- multiple receiving antennas;
- multiple frequencies;
- known transmitter/antenna positions;
- distinct source clocks or modulation tags;
- time-varying geometry.

## Current Overall Verdict

What we can say now:

```text
L5 dense export works.
Single-source L5 reference kernels are stable.
The test pipeline can capture, replay, and score two-source data.
Farther separations can be observed.
Near-delay extraction is currently blocked by path0 residual and model-reality
gap.
```

What we cannot claim:

```text
We cannot yet claim reliable PRN28 fast-drift +60 m recovery.
We cannot yet claim reliable PRN11 30/15/7 m separation.
We cannot yet claim 0.5 chip separation in a static same-code same-clock DAS
snapshot.
```

## Recommended Next Work

Do next:

1. Build richer path0 subtraction:
   - basis: `K`, `dK/dtau`, maybe local curvature / residual principal
     components from A-only captures;
   - estimate smoothly over segments instead of per epoch;
   - validate first on faithful path0 synthetic.
2. Add residual-map false-positive controls:
   - target delay consistency;
   - margin over non-target peaks;
   - rejection when residual map has many competitive candidates.
3. Start a movement-aware simulation plan:
   - create synthetic moving-receiver trajectories;
   - generate delay/Doppler tracks for multiple fixed transmit antennas;
   - test whether track continuity separates sub-chip sources better than
     snapshot fitting.

Do not do next:

```text
Do not keep tuning current delay-Doppler thresholds to force RELIABLE.
Do not trust clean synthetic benchmark results unless the same method also works
on faithful path0 synthetic.
Do not use the current residual map directly as a production detector.
```

## Handoff Summary for Claude

Codex agrees with Claude's failure diagnosis.

Evidence added by Codex:

- Real PRN28 +60 m maps show the target band exists but is deeply below path0
  smear.
- One-kernel path0 removal raises the target band but leaves multiple strong
  residual candidates.
- Faithful path0 synthetic reproduces the real failure while clean synthetic
  succeeds, proving the earlier synthetic was too optimistic.

Decision:

```text
The next productive algorithm step is richer path0 modeling plus faithful
synthetic validation, not a new detector threshold.
```

Strategic recommendation:

```text
For the final indoor DAS goal, shift from static snapshot super-resolution to
moving-receiver trajectory separation. Snapshot dense maps remain useful as
measurements, but the final estimator should exploit path continuity over time.
```

# Track B Post-Correlation EKF Baseline

Date: 2026-07-29

Author: Codex

## 1. Purpose

This milestone implements option B from the adaptive channel-estimation review:
a post-correlation EKF over the existing complex dense correlator vector.

The implementation is an offline research baseline. It does not modify the
GNSS-SDR real-time C++ tracking loop.

New tool:

```text
dev_notes/sim/track_moving_twosource_ekf.py
```

Current input:

```text
generate_moving_twosource.py NPZ
```

Ground truth in the NPZ is used only for final benchmark scoring and covariance
coverage. It is not used for initialization, hypothesis selection, or updates.

## 2. State And Measurement Model

The nonlinear EKF state is deliberately small:

```text
x = [relative_delay_chips, relative_delay_rate_chips_per_second]
```

The process model is constant velocity with white acceleration noise:

```text
delay[k+1] = delay[k] + delay_rate[k] * dt
delay_rate[k+1] = delay_rate[k]
```

For a predicted delay, both complex amplitudes are conditionally linear:

```text
y(tap) = c0*K(tap) + c1*K(tap-delay) + noise
```

`c0` and `c1` are solved by complex least squares every epoch. The derivative
of `c1*K(tap-delay)` supplies a local Gauss-Newton delay correction. That scalar
correction and its variance form the EKF measurement.

This is a lightweight Rao-Blackwellized design:

```text
EKF: nonlinear delay and delay rate
linear least squares: complex path amplitudes
```

## 3. Multi-Hypothesis Initialization

A single EKF mode failed on the faithful equal-power, 180-degree case:

```text
path1 became the strongest ridge
-> initializer treated path1 as path0
-> delay initialized at the 0.05-chip search boundary
-> local EKF stayed in the wrong mode with false confidence
```

The fix is not a threshold change. The script now keeps several
delay-Doppler initialization candidates, runs one lightweight EKF for each, and
selects the mode using only:

```text
median normalized two-path residual
two-path support fraction
fraction of epochs latched to a search boundary
```

This is a bounded Gaussian-mixture initialization, not a full particle filter.

## 4. Reliability Gates

The `RELIABLE` verdict requires all of:

```text
accepted EKF update fraction
two-path residual/amplitude support fraction
posterior delay standard deviation
delay-Doppler diversity beyond the path0 leakage guard
no sustained search-boundary latch
synthetic truth coverage inside posterior +/-2 sigma
```

The diversity gate is intentionally conservative. A static same-clock capture
can produce a plausible point estimate, but this Track B baseline does not claim
it reliable without an independently observable delay/Doppler trajectory.

Noise defaults were calibrated on faithful synthetic truth:

```text
measurement delay std floor = 0.2 chip per epoch
process acceleration std = 0.2 chip/s^2
```

The larger values are deliberate. Earlier defaults produced a posterior
standard deviation of only `0.08 m` while real errors exceeded `1 m`.

## 5. Benchmark Results

All faithful cases reuse measured PRN28 A-only dense-correlator texture.

| Case | EKF verdict | Median error | P90 error | 2-sigma coverage |
|---|---|---:|---:|---:|
| ideal moving, -6 dB | `RELIABLE` | 0.33 m | 1.01 m | 100.0% |
| ideal static, -6 dB | `UNRELIABLE` | 0.11 m | 0.31 m | 100.0% |
| faithful moving, -6 dB | `RELIABLE` | 0.56 m | 1.10 m | 100.0% |
| faithful moving, equal power, 180 deg | `RELIABLE` | 0.59 m | 1.55 m | 88.5% |
| faithful static, -6 dB | `UNRELIABLE` | 0.69 m | 1.48 m | 86.1% |
| faithful moving, effective path1 absent | `UNRELIABLE` | 9.75 m | 14.86 m | 5.2% |

The no-path1 case had only `14.4%` two-path support, so it failed independently
of the diversity gate.

Comparison with the first dynamic-programming Track B prototype:

```text
faithful moving -6 dB:
  DP  P90 = 1.20 m
  EKF P90 = 1.10 m, plus calibrated covariance

faithful moving equal-power destructive:
  DP  P90 = 2.87 m
  EKF P90 = 1.55 m, plus calibrated covariance
```

## 6. Reproduction

One-line NUC command:

```bash
python3 dev_notes/sim/track_moving_twosource_ekf.py --input /tmp/trackb_faithful_prn28.npz --kernel /home/bupt/lya/gnss_data/phaseB_l5_baseline/aonly_prn28_l5m50_amp64_run4_30s_0728/aonly_reference_Rtau.png.csv --csv /tmp/trackb_faithful_prn28_ekf.csv --plot /tmp/trackb_faithful_prn28_ekf.png
```

## 7. Limits And Next Work

What is proved:

- the post-correlation state model works on ideal and faithful synthetic moving
  observations down to the current `0.37..0.55 chip` trajectory;
- equal-power path swapping requires multiple initialization modes;
- posterior covariance can be made conservative enough to pass a truth-coverage
  gate;
- static and no-path controls do not produce a reliable Track B claim.

What is not proved:

- no real moving B210 capture has been processed;
- path1 still uses a shifted ideal/measured kernel rather than independently
  measured path1 residual texture;
- model order is fixed at one-vs-two source evidence; no path birth/death logic;
- static separation remains outside this Track B reliability claim;
- noise parameters were calibrated on one PRN28 faithful source and need
  cross-PRN/CN0 validation.

Next recommended sequence:

```text
1. Add curved, stop-start, slow-motion and geometry-degenerate synthetic tracks.
2. Repeat faithful tests across PRNs and CN0 reference kernels.
3. Add path birth/death and innovation-based dropout handling.
4. Adapt the reader to real dense dump + external receiver trajectory.
5. Run a surveyed real moving B210 experiment.
6. Only after offline validation, evaluate a low-rate real-time C++ integration.
```


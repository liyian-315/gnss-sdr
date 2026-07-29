# Track B Moving-Receiver Trajectory Prototype

Date: 2026-07-29

Author: Codex

## 1. Goal And Scope

Track B tests the project hypothesis that receiver motion supplies the diversity
missing from a static, single-antenna, same-code snapshot.

This first milestone is deliberately simulation-first:

1. Generate two-source dense-correlator observations from fixed transmitter
   coordinates and a moving receiver trajectory.
2. Extract several delay-Doppler candidates in each time segment.
3. Select a physically consistent trajectory across segments.
4. Verify the positive result on real A-only correlator texture.
5. Require the corresponding static control to remain `UNRELIABLE`.

It does **not** claim that real moving hardware data has already passed. The
faithful synthetic reuses measured PRN28 A-only path0 texture, but path1 and the
receiver trajectory are injected.

## 2. New Tools

### `generate_moving_twosource.py`

The generator models two fixed transmitters and a receiver moving on a straight
line. At every epoch it computes:

```text
range_i(t) = ||receiver(t) - transmitter_i||
delta_m(t) = range_1(t) - range_0(t)
relative_phase(t) = -2*pi*delta_m(t)/lambda
relative_doppler(t) = d(relative_phase)/dt/(2*pi)
```

It outputs a compressed `.npz` containing complex dense taps, geometry, true
relative delay/Doppler, and metadata.

Two path0 modes are supported:

- ideal kernel plus small noise/wobble;
- `--faithful-path0-dense`: measured A-only dense records, preserving real
  tracking-loop texture and kernel mismatch.

### `track_moving_twosource.py`

For each segment the tracker:

1. builds a delay-Doppler matched map;
2. masks the strongest path0 Doppler ridge;
3. keeps multiple non-maximum-suppressed candidates;
4. runs dynamic programming over candidates.

The transition model is physical rather than generic smoothing:

```text
delay[k] - delay[k-1] ~= -lambda * mean(doppler[k-1:k]) * segment_dt
```

Ground truth is used only after extraction to calculate errors and the verdict.
It is not used to select candidates.

The per-epoch `K + dK/dtau` subtraction remains available only as a diagnostic.
It is not the default because unconstrained per-epoch coefficients absorb the
projection of a merged moving path and erase the very temporal diversity Track
B needs.

## 3. Acceptance Gate

The current synthetic gate is:

```text
at least 5 complete segments
>=80% of segments within max(3 m, 0.1 chip)
delay-error P90 <= 5 m
```

Passing faithful synthetic is necessary but not sufficient. The next hardware
gate must use a measured receiver trajectory and must retain a static false
positive control.

## 4. Results

Default geometry:

```text
tx0 = (-15, 0) m
tx1 = (+15, 0) m
receiver = (-8, -15) -> (-8, +15) m
L5 chip = 29.3 m
```

This produces a sub-chip delay trajectory of approximately
`10.9..16.0 m = 0.37..0.55 chip` and relative Doppler of about `-2.5..+2.5 Hz`.

| Case | Path1 | Result | Median delay error | P90 |
|---|---:|---|---:|---:|
| ideal moving | -6 dB | `RELIABLE` | 0.12 m | 0.33 m |
| ideal static | -6 dB | `UNRELIABLE` | 9.44 m | 9.44 m |
| faithful PRN28 moving | -6 dB | `RELIABLE` | 0.54 m | 1.20 m |
| faithful PRN28 moving, 180 deg initial phase | 0 dB | `RELIABLE` | 2.39 m | 2.87 m |
| faithful PRN28 static | -6 dB | `UNRELIABLE` | 5.78 m | 8.71 m |
| faithful PRN28 moving, effective path1 absent | -120 dB | `UNRELIABLE` | 10.44 m | 11.66 m |

The faithful source was:

```text
phaseB_l5_baseline/aonly_prn28_l5m50_amp64_run4_30s_0728
```

The result supports the Track B hypothesis: trajectory continuity and
geometry-related Doppler can recover a sub-chip path that the same static
observation cannot identify reliably.

## 5. Reproduction

Clean moving case:

```bash
python3 dev_notes/sim/generate_moving_twosource.py --output /tmp/trackb_moving_clean.npz --duration-s 20 --epoch-ms 10 --ratio-db -6
python3 dev_notes/sim/track_moving_twosource.py --input /tmp/trackb_moving_clean.npz --segment-s 4 --top-k 12 --csv /tmp/trackb_moving_clean.csv --plot /tmp/trackb_moving_clean.png
```

Faithful PRN28 case:

```bash
python3 dev_notes/sim/generate_moving_twosource.py --output /tmp/trackb_faithful_prn28.npz --kernel <PRN28_AONLY_KERNEL.csv> --faithful-path0-dense <PRN28_AONLY_DENSE.dat.json> --duration-s 20 --epoch-ms 10 --ratio-db -6
python3 dev_notes/sim/track_moving_twosource.py --input /tmp/trackb_faithful_prn28.npz --kernel <PRN28_AONLY_KERNEL.csv> --segment-s 3 --top-k 12 --csv /tmp/trackb_faithful_prn28.csv --plot /tmp/trackb_faithful_prn28.png
```

Static negative control adds `--static` to the generator and otherwise uses the
same command.

## 6. What Remains

Before claiming Track B success:

1. add curved and stop-start trajectories, different transmitter geometries,
   power ratios, CN0 levels, and trajectory-speed sweeps;
2. add confidence based on best-vs-second trajectory margin without truth;
3. test false alarms on A-only data with no injected path1;
4. generate a physically faithful front-end benchmark where path1 also carries
   measured residual texture instead of an ideal shifted kernel;
5. perform a real moving B210 capture with surveyed receiver positions or a
   synchronized external trajectory reference;
6. compare static and moving captures under the same RF condition.

Static and moving modes remain separate deliverables:

- static mode must report an honest separability floor and uncertainty;
- moving mode targets sub-chip separation through trajectory diversity.

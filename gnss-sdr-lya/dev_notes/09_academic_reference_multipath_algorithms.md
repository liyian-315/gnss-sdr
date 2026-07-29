# 09 · Academic Reference: GNSS Multipath Algorithms

> Purpose: shared research notes for Codex/Claude/user. This file records what
> we learn from classic and related papers, and maps those ideas to the current
> GNSS-SDR multipath retrofit. It is not a final design document. Do not invent
> an algorithm here just to look decisive; use this file to keep evidence,
> tradeoffs, and open questions visible.

Last updated: 2026-07-23

Local paper folder:

```text
D:\work\beidou\papers
```

## Current Project Context

The current implementation has proved useful for experiments, but its core
method is still simple:

```text
acquisition 2D grid -> find strongest peak + second local peak -> hand path0/path1
to two tracking channels -> print DUALPATH_OBS / DUALPATH_PAIR
```

This works best when two paths are separated enough to form two clear peaks.
It becomes unreliable when:

- the delay gap is small and the correlation peaks merge;
- two same-PRN paths have similar power and the "main" path can swap;
- the second local peak is a sidelobe/noise peak, not a real path;
- two independent tracking channels lock onto the same peak;
- a parameter change only reduces loss-of-lock, but does not prove that the
  second path is physically real.

The research direction suggested by the papers below is:

```text
tracking-domain multi-correlator observations
-> reconstruct / fit the distorted correlation shape
-> jointly estimate LOS and multipath delay/amplitude/phase
-> classify reliability and feed corrected measurements to PVT
```

## Reading List Index

| Paper | Local file | Main idea | Project relevance |
|---|---|---|---|
| The Multipath Estimating Delay Lock Loop: Approaching Theoretical Accuracy Limits | `The_multipath_estimating_delay_lock_loop_approaching_theoretical_accuracy_limits.pdf` | MEDLL: jointly estimate LOS and multipath parameters by fitting the received correlation shape | Highest value. Points us away from acquisition Top-2 and toward tracking-domain model fitting |
| An Innovative Multipath Mitigation Method Using Coupled Amplitude Delay Lock Loops in GNSS Receivers | `An_innovative_multipath_mitigation_method_using_coupled_amplitude_delay_lock_loops_in_GNSS_receivers.pdf` | CADLL: multiple coupled delay/amplitude loops track several paths and wipe off estimated components | High value. Shows why two independent channels are weaker than a coupled two-path tracker |
| 一种基于 Rake 结构的 GNSS 多径信号捕获方法 | `一种基于Rake结构的GNSS多径信号捕获方法_孙晓文.pdf` | RAKE-style multiple path fingers in acquisition | Useful for Stage-A thinking, but not sufficient for close multipath |
| A Gradient Boosting Decision Tree Based GPS Signal Reception Classification Algorithm | `A gradient boosting decision tree based GPS signal reception.pdf` | Classify LOS / multipath / NLOS using features such as C/N0, residuals, elevation, etc. | Useful later for reliability classification, not for raw path separation |
| GNSS Multipath Detection Using Three-Frequency Signal-to-Noise Measurements | `GNSS multipath detection using three-frequency signal-to-noise measurements.pdf` | Detect multipath from multi-frequency SNR behavior | Useful later if we combine B1I/B1C/L1/L5 features; mostly detection, not separation |
| Multipath-Assisted Positioning with SLAM (Channel-SLAM, Gentner/DLR 2016) | `Multipath_Assisted_Positioning_with_Simultaneous_Localization_and_Mapping.pdf` | Treat each multipath component as a time-synchronized "virtual transmitter"; jointly estimate receiver + all VT positions via a Rao-Blackwellized particle filter | Reference architecture for the reframed "multipath = useful multi-source" goal. Exposes what we lack: aperture (array/motion) + wide bandwidth |
| RIS-Aided Passive Detection for LSS Targets: A GNSS Multipath-Assisted Scheme (Xu/Xiamen 2024) | `RIS-Aided_Passive_Detection_for_LSS_Targets_A_GNSS_Multipath-Assisted_Scheme.pdf` | Virtual-anchor (mirror of static Rx) model + M-tap PMF multi-correlator + offline-learn/online-detect; cites MEDLL as its baseband core | Transferable stack (VA modeling + multi-correlator); confirms sub-metre param estimation at C/N0>30 dB-Hz. RIS is hardware we do not have |
| A Hybrid Optical–Wireless Network for Decimetre-Level Terrestrial Positioning (SuperGPS, Koelemeij/Nature 2022) | `A hybrid optical–wireless network for decimetre-level terrestrial positioning.pdf` | Constellation of sub-ns-synchronized terrestrial USRP transmitters; multiband-OFDM 160 MHz virtual BW → decimetre TD / centimetre carrier-phase | System-level answer for controllable multi-transmitter positioning. Quantifies bandwidth-vs-multipath (20 MHz→4 m, 160 MHz→0.5 m) |

## Paper Notes

### 1. MEDLL

Paper:

```text
The Multipath Estimating Delay Lock Loop: Approaching Theoretical Accuracy Limits
R. D. J. van Nee, J. Siereveld, P. C. Fenton, B. R. Townsend
PLANS 1994
```

What it does:

- Treats the received GNSS signal as a sum of LOS plus one or more multipath
  components.
- Estimates path parameters simultaneously rather than using only the classic
  early-minus-late discriminator.
- Fits a synthetic correlation function to the measured distorted correlation
  function.
- Aims to estimate at least:
  - LOS delay;
  - multipath delay;
  - relative amplitude;
  - relative carrier phase.

Why it matters to us:

- Our current acquisition Top-2 logic assumes the two paths form two visible
  peaks. In close multipath, this assumption breaks.
- MEDLL attacks the exact problem we now see in the field: the peak shape is
  distorted, not cleanly split.
- It also explains why reducing early-late spacing or relaxing lock thresholds
  is not enough. Those techniques may reduce bias or hold lock, but they do not
  explicitly estimate the multipath component.

What to learn:

- Add dense correlator taps around the prompt point.
- Fit a two-path correlation model instead of selecting a second local maximum.
- Use fit residual as a confidence indicator.
- Expect close-delay multipath to remain difficult; do not promise perfect 50 m
  separation on L1 C/A or heavily merged peaks.

How this maps to code:

```text
src/algorithms/tracking/gnuradio_blocks/dll_pll_veml_tracking.*
src/algorithms/tracking/libs/cpu_multicorrelator_*.*
```

Likely next prototype:

```text
tracking block exports multi-correlator samples
offline Python fits a two-path model
then C++ real-time estimator is added only after the offline fit is credible
```

### 2. CADLL

Paper:

```text
An Innovative Multipath Mitigation Method Using Coupled Amplitude Delay Lock Loops
in GNSS Receivers
```

What it does:

- Uses coupled Amplitude Lock Loops (ALL) and Delay Lock Loops (DLL).
- Builds multiple tracking units, where each unit estimates one signal path.
- Uses feedback / wipe-off between units so the estimate of one path helps
  isolate the next path.

Why it matters to us:

- Our current "two channels for one PRN" approach is not truly coupled.
- Path0 and path1 can both lock to the same distorted maximum.
- A real two-path tracker should know that path0 and path1 belong to one
  composite signal and should estimate them jointly.

What to learn:

- Do not model path1 as a completely independent satellite channel.
- Maintain two path states inside one PRN tracking context:
  - delay;
  - amplitude;
  - carrier phase / Doppler;
  - lock confidence.
- Subtract or account for the strongest estimated path before estimating the
  weaker one.

Design warning:

- CADLL-style coupling is more invasive than config tuning. It probably belongs
  in tracking-domain code, not in acquisition config.
- It also needs robust initialization, otherwise the second loop can chase noise.

### 3. RAKE-Style GNSS Multipath Acquisition

Paper:

```text
一种基于Rake结构的GNSS多径信号捕获方法
```

What it does:

- Brings the RAKE receiver idea into GNSS multipath acquisition.
- Treats multiple delayed components as multiple "fingers".
- Searches/uses several path components instead of only the strongest one.

Why it matters to us:

- Our Stage-A implementation is similar in spirit: acquisition finds a primary
  peak and a second candidate peak.
- It supports the idea that multipath can be detected/initialized in acquisition.

Limitations for our current problem:

- Acquisition-domain separation is coarse.
- Close multipath may not create a reliable second local peak.
- It is sensitive to false peaks, correlation sidelobes, grid resolution, and
  relative phase.

What to learn:

- Use acquisition to initialize candidates, not as the final estimator.
- Add time consistency checks before trusting a "second peak".
- Treat RAKE acquisition as a front-end to a tracking-domain estimator.

### 4. GBDT-Based GPS Signal Reception Classification

Paper:

```text
A Gradient Boosting Decision Tree Based GPS Signal Reception Classification Algorithm
```

What it does:

- Classifies signal reception types such as LOS, multipath, and NLOS.
- Uses multiple features rather than only C/N0.
- Relevant feature families include:
  - C/N0 and C/N0 temporal variation;
  - pseudorange residual;
  - pseudorange rate / Doppler consistency;
  - satellite elevation / azimuth;
  - DOP or geometry-related features.

Why it matters to us:

- It is not a raw signal separation method.
- It is useful after we have path estimates, to decide whether an observation is
  trustworthy and how it should affect PVT.

What to learn:

- Do not use one threshold alone to judge multipath.
- Build a reliability score from multiple features:
  - primary C/N0;
  - second-path C/N0;
  - amplitude ratio;
  - delay difference;
  - fit residual;
  - lock duration;
  - Doppler consistency;
  - time stability of the estimated second path.

Possible later output:

```text
MULTIPATH_CLASS prn=... los_prob=... multipath_prob=... nlos_prob=...
```

This should come after a credible estimator, not before.

### 5. Three-Frequency SNR Multipath Detection

Paper:

```text
GNSS multipath detection using three-frequency signal-to-noise measurements
```

What it does:

- Uses multi-frequency SNR/CN0 behavior to detect multipath.
- Does not directly estimate two path pseudoranges.

Why it matters to us:

- Our project already touches B1I/B1C/L1/L5. Multi-frequency features could help
  distinguish real multipath from receiver/config artifacts.
- It can be useful for validation and classification, especially if multiple
  bands are available at the same site.

Limitations:

- It is a detection/diagnostic approach, not the core path-separation algorithm.
- It requires comparable observations across frequencies, which is not always
  true in our simulator/field setup.

> The three references below were added on 2026-07-23 (Claude). They are not
> classical "multipath mitigation" papers; they cover the reframed goal
> (multipath as useful multi-source signals) and the system-level context.

### 6. Channel-SLAM (Multipath-Assisted Positioning + SLAM)

Paper:

```text
Multipath Assisted Positioning with Simultaneous Localization and Mapping
C. Gentner, T. Jost, W. Wang, S. Zhang, A. Dammann, U.-C. Fiebig (DLR)
IEEE Trans. Wireless Communications, 2016
```

What it does:

- Treats every multipath component as a signal emitted from a "virtual
  transmitter" (VT) that is time-synchronized to the physical transmitter and
  static in position (a reflection VT is the physical Tx mirrored at the surface).
- Jointly estimates the receiver position and all VT positions with a
  Rao-Blackwellized particle filter (a superordinate PF for the receiver state,
  a subordinate PF per VT). This is SLAM with radio signals: VTs are landmarks.
- Low level: a super-resolution estimator (KEST) tracks each MPC's delay and
  angle-of-arrival (AoA) over time.

Why it matters to us:

- This is the textbook realization of our reframe: not "keep LOS, suppress
  reflections" but "each path is an extra transmitter you can use". A single
  physical transmitter is enough to position when several MPCs are available.

What to learn (and the hardware gap it exposes):

- Enablers: a linear antenna array (for AoA) OR a single antenna + gyroscope +
  receiver MOTION; wideband signals (100 MHz in the paper); known physical Tx
  position and initial receiver position/heading.
- Results: < 0.3 m (simulation, SNR > 20 dB), < 1.1 m (indoor measurement) with
  one physical transmitter.
- Our single-antenna, ~20 MHz, near-static B210 lacks the two key ingredients:
  aperture (array/motion -> AoA) and bandwidth (-> delay resolution). Even KEST
  cannot resolve all paths when bandwidth is limited and MPCs are close to LOS.

### 7. RIS-Aided Passive Detection (GNSS Multipath-Assisted)

Paper:

```text
RIS-Aided Passive Detection for LSS Targets: A GNSS Multipath-Assisted Scheme
X. Xu, Y. Zhou, H. Li, A. Peng, Q. Ye, Q. Yang (Xiamen University)
IEEE JSAC, 2024
```

What it does:

- Uses GNSS multipath as signals of opportunity for passive radar (detecting
  low/slow/small targets such as drones).
- Models reflected paths with virtual anchors (VA = mirror image of the static
  receiver), learned offline; online detection is a binary hypothesis test
  (target present -> new "targeted MPCs" appear over the environmental MPCs).
- Extracts the channel impulse response with an M-tap pattern-matching filter
  (a multi-correlator) and tracks VA positions with an EKF + super-resolution.

Why it matters to us:

- It explicitly cites MEDLL as the baseband structure that can track LOS plus
  several NLOS components simultaneously, and it uses the exact stack we are
  heading toward: multi-correlator observations + geometric (VA) model + filter.
- It states sub-metre multipath parameter estimation is achievable when
  C/N0 > 30 dB-Hz -- external support for our note that C/N0 ~30 is a workable
  regime, not "too weak".

Limitations for us:

- RIS is hardware we do not have. The transferable parts are the VA/mirror
  geometry, the M-tap PMF multi-correlator, and the offline-learn / online-detect
  structure. The end goal is detection, not multi-source separation for PVT.

### 8. SuperGPS (Hybrid Optical–Wireless Terrestrial Positioning)

Paper:

```text
A hybrid optical–wireless network for decimetre-level terrestrial positioning
J. C. J. Koelemeij et al. (VU Amsterdam / TU Delft)
Nature 611, 2022
```

What it does:

- A constellation of six terrestrial USRP transmitters (pseudolites),
  sub-nanosecond time-synchronized over fibre with White Rabbit, transmitting
  multiband-OFDM with 160 MHz virtual bandwidth. Each Tx has a unique Gold code
  for identification; positioning by TDOA/MLE.
- Achieves decimetre-level time-delay positioning and centimetre-level
  carrier-phase positioning in a multipath-prone outdoor site.

Why it matters to us:

- It is the system-level answer for "multiple antennas transmit signals for
  positioning" done correctly: identifiable per-source codes + tight sync + wide
  bandwidth. If the sources are cooperative and controllable (like our
  simulators), this is not blind multipath separation -- it is pseudolite
  positioning.
- It quantifies the bandwidth lever: GPS L5 (20.46 MHz) shows up to 4 m multipath
  error; the 160 MHz virtual-BW OFDM shows 0.5 m. Bandwidth, not parameter
  tuning, is what buys multipath robustness.

What to learn:

- If our indoor multi-antenna scenario can control the transmitted waveform, copy
  this recipe: distinct codes per source, wide (or sparse-wide) bandwidth, good
  time sync. That reframes the whole problem away from "separate two blended
  same-code paths".

## What These Papers Say About Our Current Pain Points

### Pain Point A: Top-2 Acquisition Peaks Are Not Stable

Relevant papers:

- MEDLL
- RAKE acquisition

Interpretation:

When the two delays are far apart, acquisition Top-2 can work. When the delays
are close, the measured correlation is a merged/distorted shape. A second local
maximum may not exist, or may be a sidelobe/noise artifact.

Project implication:

Do not keep tuning `multipath_threshold_fraction` as the main solution. Use
acquisition Top-2 only as candidate initialization.

### Pain Point B: Two Channels Can Track the Same Path

Relevant papers:

- CADLL
- MEDLL

Interpretation:

Two independent channels do not enforce a two-path model. If both channels see
the same distorted composite signal, both can converge to the same delay.

Project implication:

The next real algorithm should be "one PRN, multi-path state" rather than "two
independent channels that happen to share one PRN".

### Pain Point C: Loss-of-Lock Tuning Does Not Prove Multipath

Relevant papers:

- GBDT classification
- MEDLL

Interpretation:

Relaxing `cn0_min`, `carrier_lock_th`, or lock-fail counters can make tracking
less jumpy, but it does not prove the second path is real.

Project implication:

We need objective validity fields:

```text
delay_diff_m
amplitude_ratio_db
phase_diff_rad
fit_residual
path_time_stability
same_peak_risk
```

### Pain Point D: Close Multipath Needs Tracking-Domain Processing

Relevant papers:

- MEDLL
- CADLL

Interpretation:

Close-delay multipath is a tracking-domain estimation problem. The correlator
shape near prompt contains more information than a single peak location.

Project implication:

Move from "peak search" to "correlation-shape estimation".

## Proposed Research-Driven Development Plan

This is not a final design. It is a conservative path for avoiding blind
parameter tuning.

### Step 1: Freeze Experiment Baselines

Keep known working L1/L5/B1I configs for repeatable tests. Avoid changing five
tracking parameters at once.

Minimum outputs to preserve:

```text
DUALPATH_OBS
DUALPATH_PAIR
run log
optional acquisition dump for diagnostics
```

### Step 2: Export Dense Tracking Correlator Samples

Add a diagnostic mode that outputs a small correlator vector around prompt:

```text
-2.0, -1.5, -1.0, -0.75, -0.5, -0.25, 0,
 0.25, 0.5, 0.75, 1.0, 1.5, 2.0 chips
```

Start with offline logging. Do not immediately wire this into PVT.

### Step 3: Build Offline Two-Path Fitting

Prototype in Python first:

```text
observed_corr(tau) ~= A0 * R(tau - tau0)
                   + A1 * R(tau - tau1) * exp(j * phi)
```

Outputs:

```text
tau0, tau1, delta_m, amplitude_ratio_db, phase_diff, fit_residual
```

Validation grid:

```text
signals: L1 C/A, L5, B1I
delay: 50m, 100m, 200m, 350m, 700m, 1000m
power ratio: 0, -3, -6, -10 dB
phase: same, opposite, random
```

### Step 4: Add Time Consistency

A single frame fit is not enough. Track whether the estimated second path is
stable over time.

Candidate fields:

```text
delta_m_median
delta_m_std
amp_ratio_median
fit_residual_median
valid_ratio
```

### Step 5: Integrate a Minimal Tracking-Domain Estimator

Only after offline fitting is credible:

- add estimator into tracking block;
- output path0/path1 observables;
- keep path1 out of PVT initially;
- use path1 to label/correct path0 only after validation.

## Guardrails

- Do not claim "50m multipath separation" until repeated controlled tests show
  stable estimates with known geometry or known delay injection.
- Do not treat phone C/N0 as equivalent to USRP tracking health. Phone receiver
  processing is closed and optimized differently.
- Do not use `--expected-delay-m` to select the answer when evaluating an
  unknown field result. It is only valid for controlled experiments.
- Do not confuse physical transmitter antenna spacing with receiver-observed
  path delay difference. Geometry matters.
- Do not merge two path measurements into PVT as two independent satellites.
  Reflected paths are biased measurements.
- Single-antenna, same-code, sub-chip multipath separation is a physical wall,
  not a tuning problem. Resolution is set by bandwidth (L5 chip = 29.3 m at
  ~20 MHz; L1 C/A chip = 293 m); separability is set by aperture/diversity. To
  beat it: add bandwidth, add aperture (antenna array or receiver motion), or
  make the sources identifiable (distinct codes). Reference points: 50 m @ L5 =
  1.7 chip (above the wall, feasible); 50 m @ L1 = 0.17 chip (below the wall at
  20 MHz, effectively unresolvable). (Added 2026-07-23, Claude.)

## Open Questions For Paper Discussion

- Which model should be implemented first: MEDLL-like nonlinear fit or CADLL-like
  coupled loops?
- How many correlator taps are enough for L1 C/A, L5, and B1I?
- Should the estimator use complex I/Q correlators or magnitude-only values?
- How should relative carrier phase be handled when two paths destructively
  interfere?
- What is the minimum delay separation we can honestly support per signal?
- How do we label LOS when the strongest path is not always the earliest path?

## Working Opinion As Of 2026-07-23

The next algorithmic step should be a MEDLL-inspired offline two-path fitting
prototype using dense tracking correlator outputs.

Reason:

- It directly attacks the current failure mode: merged/distorted peaks.
- It can be validated offline before destabilizing the receiver.
- It provides objective confidence fields, not just "has second peak".
- CADLL is also valuable, but it is more invasive; it is better treated as a
  later real-time tracking architecture after the fitting problem is understood.

In short:

```text
Stop treating multipath as "find another acquisition peak".
Start treating it as "estimate the parameters of a distorted correlation shape".
```

## Discussion Log

Maintenance rule:

- Every meaningful paper/algorithm discussion should add one entry here.
- Record the user's question, the working answer/opinion, and what it changes
  for the project direction.
- Keep entries evidence-oriented. If something is only a hypothesis, mark it as
  such. Do not turn discussion notes into premature design decisions.
- Every judgment/opinion entry must include date and author signature
  (`Codex`, `Claude`, or user-provided author) so handoff readers can see who
  made the assessment and when.

### 2026-07-23 · MEDLL for close-delay multi-source separation

Author: Codex. Date: 2026-07-23.

User question:

```text
MEDLL fits the whole correlation shape. Does that help separate close-delay
paths when the first and second path are blended together? The project goal is
not just positioning: in indoor positioning, multiple antennas may transmit the
same signal, so the "multipath" is actually meaningful multi-source signals.
We need to separate two or more paths and obtain their information.
```

Working answer / opinion:

- MEDLL is relevant because its useful idea is not "suppress multipath", but
  "model the received correlation shape as a sum of multiple delayed signal
  components".
- For this project, the goal should be reframed from traditional multipath
  mitigation to multi-source parameter estimation:

```text
not: keep only LOS and suppress all reflections
but: estimate every resolvable source/path and output delay, power/CN0, Doppler,
phase/fit confidence, and time stability
```

- The current two-channel path0/path1 design is not enough for this goal because
  two independent channels can lock to the same composite peak.
- A more suitable architecture is "one PRN, multiple internal path components",
  where all components are estimated jointly from dense correlator observations.
- MEDLL gives the right modeling direction; CADLL gives the right coupling idea.
  Neither should be copied blindly as-is, because our use case treats second and
  third paths as potentially useful transmitters rather than pure interference.

Important constraints:

- If multiple transmitters are truly same PRN, same carrier, same navigation
  data, nearly same Doppler, close in delay, and observed by only one receive
  antenna, the separation problem can become ill-conditioned or even practically
  unidentifiable.
- Useful separation information can come from:
  - delay difference;
  - amplitude difference;
  - relative carrier phase;
  - Doppler difference;
  - time continuity;
  - multi-frequency observations;
  - multi-antenna/spatial diversity;
  - known transmitter geometry or synchronization constraints.

Project implication:

- Do not continue treating `pfa`, `cn0_min`, or lock-fail counters as the main
  solution.
- The next algorithm experiment should be offline first:

```text
export dense tracking correlator samples
-> fit 2-path / 3-path correlation models in Python
-> test known 50m, 100m, 200m, 700m cases
-> only then integrate a real-time estimator into GNSS-SDR
```

Terminology update:

```text
traditional wording: multipath mitigation
project wording: same-signal multi-source / multi-path separation and estimation
```

-- Codex, 2026-07-23

### 2026-07-29 · Review of adaptive channel-estimation techniques (Space 0278)

Author: Codex. Date: 2026-07-29.

Reference:

```text
P. M. C. Pereira, H. D. M. da Silva, and C. M. G. S. Lima,
"Advancements in Multipath Mitigation for GNSS Receivers:
Review of Channel Estimation Techniques,"
Space: Science & Technology, vol. 5, Article 0278, 2025.
DOI: 10.34133/space.0278
```

This is a review paper rather than a new estimator. Its useful contribution for
this project is a structured comparison of correlator geometry, inverse-channel
adaptive estimation, maximum-likelihood channel estimation, EKF, and particle
filtering.

#### Directly relevant conclusions

The paper models each component by:

```text
path_n = {complex amplitude alpha_n, delay tau_n, phase phi_n}
```

and estimates the sum of all components from correlation-domain observations.
Although the paper's application objective is normally to preserve LOS and
mitigate echoes, the estimator itself is compatible with our DAS interpretation:
keep every component as a meaningful transmitter and output every state.

Its review supports several decisions already made here:

- Dense post-correlation observations are the right interface. Post-correlation
  EKF designs reduce the raw sample space to a correlator vector while retaining
  the channel parameters we need.
- Narrow/double-delta correlators remain geometry-only methods. They improve
  ordinary tracking but remain unreliable for short-delay dense multipath and
  are not a substitute for multi-component estimation.
- Real channels are nonstationary; path count and path state can change at
  different rates. A one-shot two-path fit is therefore not the final receiver
  architecture.
- Literature results often assume high SNR, a few weak echoes, stationarity, and
  clean synthetic models. This agrees with our finding that ideal synthetic
  tests passed while measured path0 texture broke several estimators.

#### Methods worth borrowing

1. **Post-correlation EKF as the next Track B baseline**

   State per path:

   ```text
   x_n = [delay, delay_rate or Doppler, complex amplitude]
   ```

   Measurement:

   ```text
   y_k(tap) = sum_n a_n,k * K(tap - tau_n,k) + noise
   ```

   This turns the current Track B dynamic-programming path into a probabilistic
   recursive estimator. It can propagate delay/Doppler continuity, produce
   covariance, and reject a path when innovation remains inconsistent.

2. **Rao-Blackwellized particle filter for ambiguous/static-near-wall cases**

   The surveyed RBPF split is particularly relevant:

   ```text
   PF/grid hypotheses: nonlinear path delay and possibly path count
   KF/least squares: conditionally linear complex amplitudes
   ```

   This is preferable to forcing one delay solution when several `32..85 m`
   candidates survive path0 removal. Multiple particles can preserve those
   hypotheses until receiver motion makes one trajectory dominant. Effective
   sample size and resampling also provide a natural uncertainty/degeneracy
   signal.

3. **RLS/APA for adaptive kernel or residual-channel tracking**

   RLS converges faster than LMS and follows nonstationary channels better;
   APA reuses recent correlated observations at intermediate complexity. A
   limited application here is online adaptation of the single-source kernel or
   low-dimensional path0 residual basis. Do not use the traditional
   "inverse-filter and annihilate multipath" objective because our second/third
   sources must be retained.

4. **Explicit birth/death and model-order handling**

   The review repeatedly exposes the weakness of fixed path assumptions. Track
   B should eventually support:

   ```text
   one source <-> two sources <-> three or more sources
   ```

   with evidence-based birth, persistence, and pruning rather than always
   instantiating exactly two paths.

#### What the paper does not solve

- It does not remove the static same-code same-clock sub-bandwidth
  identifiability wall. EKF/PF can accumulate information and represent
  uncertainty, but cannot create diversity absent from the measurements.
- Most reviewed methods are framed as LOS estimation and echo removal. Our state
  output, labels, and downstream use must be rewritten for cooperative
  multi-source estimation.
- PF is computationally expensive. It should first be an offline research
  benchmark, not immediately inserted into the real-time GNSS-SDR loop.
- RLS/inverse-channel methods commonly assume a known ideal ACF and known direct
  component. Our Phase A measured per-condition kernel and faithful path0 tests
  remain necessary.

#### Recommendation after Track B prototype

Do not replace the current trajectory prototype immediately. Use it to define
the state and measurement interfaces, then compare three estimators on the same
benchmark:

```text
A. current delay-Doppler candidates + physical dynamic programming
B. post-correlation EKF with 1/2-path model gating
C. offline RBPF: particles for delay/model order, linear update for amplitudes
```

The first implementation should be `B`, because it is much cheaper than PF and
directly adds uncertainty to Track B. Add `C` only for cases where the posterior
is visibly multi-modal and EKF linearization collapses to the wrong solution.

Success must be measured on both moving and static controls:

```text
moving: trajectory RMSE, path detection rate, false alarm rate, covariance calibration
static: separability floor and correct UNRELIABLE probability
```

Codex judgment:

```text
The paper strengthens, rather than replaces, the Track B direction.
Its most valuable borrow is recursive probabilistic channel-state estimation
in the post-correlation domain. The practical next step is an EKF baseline over
the existing dense complex taps, with RBPF retained as an offline multi-modal
reference. It does not justify claiming that static 0.5-chip separation is
solved.
```

-- Codex, 2026-07-29

### 2026-07-23 · Cross-checking the reading list against the source PDFs

Contributor: Claude (Opus 4.8). Date: 2026-07-23.

Task: read the five reading-list PDFs plus the three multi-source papers in the
folder, verify whether the notes above match the actual papers, and record an
opinion on what to learn.

Verification verdict -- all five one-line characterizations hold. Two hard facts
from the papers themselves are worth pinning down:

- CADLL explicitly degrades to a plain E-P-L loop for very short delays
  (~35 ns ~= 10 m in its C/N0=40, BT=16, 10 ms-integration simulation) and needs
  a clean standard PLL+DLL lock to initialize, or it diverges to a local minimum.
  This is exactly the field failure we saw: two *independent* channels with no
  shared two-path model thrash / lock to the same distorted peak. It is a
  predicted failure mode, not a mystery.
- MEDLL needs a clean reference correlation function and averages the correlation
  over ~1 s (batch/snapshot ML). RAKE (Sun) is actually serial interference
  cancellation (acquire finger-0 -> reconstruct -> subtract -> re-search), i.e.
  closer to MEDLL than to plain Top-2, but simulation-only, L1 C/A.

Two problems were being conflated; the papers separate them cleanly:

- Blind multipath (unknown reflectors, one antenna): MEDLL / CADLL. Hard wall at
  close delay + narrow bandwidth; both papers state sub-~0.1-chip same-code
  separation is not achievable.
- Cooperative multi-source (transmitters we control emit known signals) = our
  reframed goal. This is NOT blind multipath separation. It is pseudolite/TDOA
  positioning (SuperGPS) or multipath-as-virtual-transmitter SLAM (Channel-SLAM).
  Once sources are identifiable and time-synchronized, the problem collapses to
  ordinary multi-source ranging.

Resolution reality per signal (bandwidth sets resolution, aperture sets
separability):

- L5: chip = 29.3 m at ~20 MHz. 50 m = 1.7 chip -> above the wall, feasible; the
  field difficulty was tracking architecture (independent channels), not
  resolution.
- L1 C/A: chip = 293 m. 50 m = 0.17 chip -> below the wall at 20 MHz, basically
  unresolvable no matter how parameters are tuned.
- SuperGPS quantifies the lever: GPS L5 (20 MHz) max multipath error 4 m vs
  160 MHz virtual BW 0.5 m.

Recommended technical-stack progression (makes Steps 3->5 above explicit):

```text
MEDLL (offline snapshot ML fit, needs a clean reference correlation)
  -> CADLL or KEST (recursive closed-loop / state-space super-resolution)
    -> Channel-SLAM (adds geometry/position layer, joint multi-source)
```

RIS-Aided (2024) is essentially this whole stack in one paper (MEDLL-like
multi-correlator + virtual anchor + EKF), which is evidence the path is real and
published.

Opinion / what to learn:

- Stop tuning acquisition thresholds. The Step-2/Step-3 dense-correlator +
  offline two-path fit is the right first move, and it is supported by MEDLL,
  KEST (Channel-SLAM) and the M-tap PMF (RIS-Aided), not MEDLL alone.
- If the application allows, the cheapest win is to make the two sources
  identifiable (distinct PRNs/codes) -- that dissolves the separation problem
  into normal multi-satellite ranging. The "same signal" constraint is the source
  of the hardness.
- To keep the "same signal" constraint and still separate, we need one of: wider
  bandwidth, an antenna array, or receiver motion (Channel-SLAM gets AoA from an
  array or from motion + gyro). A single static antenna has zero angular
  resolution, so two equal-power same-code sub-chip paths from one static antenna
  are close to unidentifiable.

-- Claude (Opus 4.8), 2026-07-23

### 2026-07-23 · Is the literature discussion enough to start coding?

Author: Codex. Date: 2026-07-23.

User question:

```text
Review Claude's additions in this file. Based on the current papers, have we
discussed the borrowable ideas thoroughly enough? Can we start implementation?
```

Codex assessment:

- Claude's additions are directionally important and correct the biggest
  conceptual risk: our indoor case is not ordinary "suppress multipath"; it is
  often cooperative same-signal multi-source estimation.
- The discussion is now enough to stop blind parameter tuning and choose the
  first research-driven engineering step.
- It is not yet enough to justify a full receiver rewrite, a PVT-layer design,
  or a claimed final multi-source algorithm.

What is sufficiently clear:

- Acquisition Top-2 is only a candidate initializer. It cannot be the final
  estimator for close or merged paths.
- Independent path0/path1 tracking channels are structurally weak because they
  do not enforce a joint multi-component model.
- The next useful observable is a dense tracking-domain correlator vector, not
  more `pfa` / `cn0_min` / lock-counter tuning.
- MEDLL/CADLL/KEST/RIS-style PMF all point to the same first step: collect
  multi-correlator samples and fit/track a multi-component correlation model.
- If transmitters are controllable, distinct PRNs/codes or wider bandwidth are
  system-level levers that can make the problem much easier than blind same-code
  separation.

What is still not fully settled:

- The exact estimator: nonlinear MEDLL-style batch fit, SIC/RAKE subtraction,
  CADLL-style recursive loops, or a state-space estimator such as KEST/EKF.
- Whether to fit complex I/Q correlators or magnitude-only correlators first.
- How to choose the number and spacing of correlator taps per signal
  (L1 C/A, L5, B1I, B1C).
- How to decide model order: one path, two paths, or more paths.
- How to define an objective success/failure criterion for same-code indoor
  multi-source tests.

Implementation recommendation:

Start coding only the minimal diagnostic / offline-validation layer:

```text
1. Add a tracking-domain dense-correlator dump/monitor mode.
2. Build a Python offline fitter for 1-path vs 2-path vs 3-path correlation
   models.
3. Validate on controlled captures/simulations with known delays and power
   ratios.
4. Only after offline estimates are stable, integrate the estimator into the
   real-time tracking loop.
```

Do not start with:

- PVT integration;
- replacing the whole tracking loop;
- claiming 50 m separation on all signals;
- adding more empirical tracking thresholds;
- merging second/third paths as normal independent satellite observations.

Codex opinion:

```text
Yes, we can start implementation, but only the first, reversible step:
dense tracking correlator export + offline fitting. That is an algorithm
instrumentation prototype, not the final multi-source receiver.
```

-- Codex, 2026-07-23

# Coherent GNSS MUSIC and Spatial-Smoothing Reproduction

**Date:** 2026-08-12  
**Author:** Codex  
**Branch:** `research/coherent-music-parking-array`

## 1. Question and Application Boundary

The application is an underground parking garage with two active DAS antennas
that transmit the same GNSS signal. The DAS antennas are 20 m apart. Both paths
are useful transmitters and must be detected, separated, and eventually tracked;
the goal is not to keep a LOS path and suppress the other path.

This report answers:

1. Why ordinary MUSIC fails for highly correlated/coherent GNSS paths even
   though MUSIC is mature and some GNSS papers use it directly.
2. Why spatial smoothing can restore coherent-source DOA estimation and what it
   costs.
3. What a paper reproduction and an initial four-element ULA/UCA parking-garage
   simulation say about receiver-array design.

## 2. Why Conventional MUSIC Fails

For `K` incoming paths and `M` antenna elements:

```text
x(t) = A s(t) + n(t)
A = [a(theta_1), ..., a(theta_K)]
R_x = E[x x^H] = A R_s A^H + sigma^2 I
```

`a(theta_k)` is the spatial phase signature of path `k`. Conventional MUSIC
needs the signal part of `R_x` to have rank `K`, so the eigendecomposition has:

- a `K`-dimensional signal subspace;
- an `(M-K)`-dimensional noise subspace;
- every true steering vector orthogonal to that noise subspace.

For two independent sources:

```text
R_s = [[P0, 0],
       [0, P1]]                 rank = 2
```

For two perfectly coherent copies of one GNSS waveform, `s1(t)=alpha*s0(t)`:

```text
R_s = P0 * [[1, alpha*],
            [alpha, |alpha|^2]] rank = 1
```

Therefore `A R_s A^H` also has only one independent signal dimension. MUSIC is
asked to find two steering vectors from a one-dimensional signal subspace. More
SNR or more snapshots estimate that wrong-rank matrix more accurately; they do
not restore the missing dimension.

This resolves the apparent contradiction in `GNSS 2x2 antenna array with
beamforming for multipath detection` (Razgunas et al., 2023). Its theoretical
MUSIC model explicitly assumes uncorrelated or partially correlated sources.
Its receiver also uses ephemeris-derived satellite directions for pre-correlation
beamforming. It is evidence that MUSIC works in its processed/partially
decorrelated conditions, not evidence that ordinary MUSIC universally separates
two same-code, same-clock DAS transmitters.

Some papers saying that MUSIC handles coherent GNSS paths first create another
observation structure: spatial smoothing, Toeplitz reconstruction, code-delay
cross-correlation, beamspace transformation, carrier-phase differencing, or
post-correlation blocks. MUSIC is the final eigenspace search, but it is not
operating on the original rank-one covariance matrix.

## 3. Why Spatial Smoothing Works

Take an `M`-element half-wavelength ULA and choose overlapping subarrays of
length `P`. There are `L=M-P+1` forward subarrays. For each subarray, select its
covariance block `R_l`, then average:

```text
R_F = (1/L) * sum_l R_l
```

The same coherent waveform enters every shifted subarray, but path `k` gains a
different spatial phase factor in subarray `l`:

```text
exp(j * l * omega_k),  omega_k = pi * sin(theta_k)
```

Those phase factors differ between directions. Averaging the translated
subarrays creates an equivalent source covariance containing multiple outer
products of different phase vectors. When the directions and dimensions satisfy
the identifiability conditions, the equivalent covariance becomes full rank.

Forward-backward spatial smoothing adds conjugate-reversed subarrays:

```text
J = anti-identity matrix
R_FB = 0.5 * (R_F + J R_F* J)
```

This uses ULA conjugate symmetry and increases coherent-source identifiability.
It does not physically decorrelate the transmitted signals; it constructs an
equivalent covariance with restored rank.

The cost is important:

- MUSIC sees only a `P`-element aperture after smoothing, not the full `M`;
- enough shifted subarrays are required to restore `K` paths;
- ULA shift invariance/Vandermonde structure is required by the direct method;
- a UCA needs phase-mode/beamspace transformation or another coherent-source
  estimator before spatial smoothing can be applied;
- coherent sources with identical spatial signatures remain unidentifiable.

The classical forward-backward result gives a theoretical minimum of roughly
`ceil(3K/2)` sensors for `K` coherent sources. Thus four sensors are the minimum
for two coherent paths, but have little redundancy. Three paths require at least
five sensors theoretically; six to eight channels are a safer engineering
starting point when calibration errors and more sources are expected.

## 4. Reproduced Paper Experiment

Primary reproduction: Wang, Zhang, and Hu, *A Multipath Mitigation Method for
Array Antenna-Based GPS Receiver*, Journal of Astronautics, 2014.

Paper parameters used:

| Parameter | Value |
|---|---:|
| ULA elements | 10 |
| Element spacing | `lambda/2` |
| FBSS subarrays | 3 overlapping subarrays of 8 elements |
| Desired path | `30 deg`, 0 dB |
| Coherent paths | `-60/-30/5 deg`, `-3/-4/-6 dB` |
| Paper path delays | `0.5/0.7/0.9 chip` |

The paper uses C/A-code-period delayed cross-correlation to reduce noise, FBSS
to handle coherence, and its Eq. (12) principal-eigenvector spectrum to estimate
only the strongest LOS direction. This reproduction also adds conventional and
FBSS multi-source MUSIC spectra to expose rank restoration directly.

Result:

```text
ordinary coherent covariance signal rank: 1
FBSS covariance signal rank:               4
truth DOAs:                                -60, -30, 5, 30 deg
FBSS-MUSIC recovered DOAs:                 -60, -30, 5, 30 deg
paper strongest-path estimate after FBSS:  30.6 deg
```

The effective post-cross-correlation SNR is modeled as 30 dB. This reproduces
the paper's spatial argument, not its complete RF C/A-code generation or GSC/DLL
multipath-suppression stage. Because our DAS goal retains both sources, the GSC
suppression stage is deliberately not copied.

## 5. Correlation Monte Carlo

Two paths at `-25/35 deg`, path1 at `-6 dB`, four-element half-wavelength ULA,
512 snapshots, 100 trials per cell. Success means both DOAs are within 2 deg.

For fully coherent sources (`rho=1`), conventional MUSIC success from
`SNR=-5/0/5/10/15 dB` was:

```text
0%, 1%, 4%, 1%, 2%
```

FBSS-MUSIC was:

```text
41%, 86%, 100%, 100%, 100%
```

This confirms that conventional MUSIC's failure at high correlation is a rank
problem, not merely a low-SNR problem.

## 6. Parking-Garage Geometry Study

First-pass geometry:

```text
TX0 = (-10, 0) m
TX1 = (+10, 0) m
receiver grid: x in [-30,30] m, y in [-20,20] m
four sensors, adjacent spacing lambda/2
```

Both far-field ULA and far-field four-element circular-array spatial coherence
were mapped:

```text
mu_s = |a0^H a1| / (||a0|| ||a1||)
```

Low `mu_s` means the spatial signatures are distinguishable. `mu_s` near one
means no spatial estimator can reliably separate them under that array model.

Important representative positions:

| Receiver | Geometry | ULA `mu_s` | UCA `mu_s` | Four-element ULA FBSS |
|---|---|---:|---:|---|
| `(0,0)` between TXs | opposite bearings | 1.000 | 0.367 | ULA `UNRESOLVED` |
| `(0,5)` offset from center | `126.9 deg` apart | 0.745 | 0.163 | recovered both DOAs |
| `(-20,0)` outside one side | same bearing | 1.000 | 1.000 | fundamentally unresolved |
| `(-10,5)` beside TX0 | `76.0 deg` apart | 0.047 | 0.332 | recovered both DOAs |
| `(0,20)` far side | `53.1 deg` apart | 0.156 | 0.298 | recovered both DOAs |

The ULA center-line failure is not a contradiction: a ULA measures only one
direction projection and has front/back ambiguity. Two opposite world bearings
can produce identical ULA phase progressions. A circular/planar array removes
that continuous ULA mirror ambiguity, but a receiver outside both transmitters
on their common line sees the two sources in the same bearing; no compact array
can separate them by angle alone there.

The plotted grid fraction with `mu_s<0.8` was 66.1% for the chosen ULA orientation
and 66.7% for the four-element circular array. These percentages are exploratory,
not deployment coverage claims: the garage dimensions, array orientation,
height/elevation, obstacles, near-field response, and measured manifold are not
yet included.

## 7. Array Recommendation Before Fabrication

Do not freeze a production array from this first simulation.

Recommended staged hardware decision:

1. **Algorithm reproduction fixture:** four-element ULA, L5 half-wavelength
   spacing (`~12.7 cm`), rigid rail, identical antenna elements and cables. It
   directly supports FBSS and is the minimum two-coherent-source proof.
2. **Parking deployment candidate:** prefer a planar geometry over a four-element
   UCA if both azimuth and elevation matter. A `2x2` square is compact and removes
   the ULA's continuous front/back ambiguity, but four elements still provide
   very little coherent-source redundancy.
3. **Future three-or-more-source design:** reserve six to eight coherent RF
   channels. A six/eight-element UCA or rectangular array can provide wider
   azimuth coverage, but coherent-source processing must use measured-manifold
   ML/SAGE or UCA beamspace transformation; direct ULA FBSS cannot simply be
   copied.
4. **Do not exceed `lambda/2` adjacent spacing** in the first fixture. Wider
   spacing increases aperture but introduces grating ambiguities.
5. **Gate 0 is calibration:** synchronized complex channels, common code/carrier
   wipeoff, and measured frequency-dependent complex channel calibration are
   required before any real MUSIC spectrum is meaningful.

At GPS L5 (`1176.45 MHz`), `lambda/2` is about `12.74 cm`. At GPS L1 it is about
`9.51 cm`. A fixed L5-spaced array is wider than `lambda/2` at L1 and can create
L1 spatial ambiguity; a multi-band physical design must choose spacing for the
highest operating frequency or explicitly handle grating lobes.

## 8. What Remains Before the Specification Is Final

1. Replace far-field phase with exact spherical-wave distance for receiver
   positions close to a DAS antenna; quantify the near-field boundary.
2. Add height/elevation and a parking-garage 3-D layout.
3. Sweep array rotation, spacing, gain/phase errors, mutual-coupling perturbation,
   power ratio, CN0, and two/three/four source count.
4. Compare four-element ULA, `2x2` planar, six/eight-element UCA/rectangular
   geometries using probability of detection, false alarm, DOA RMSE, and
   `UNRESOLVED` coverage.
5. Extend from DOA-only separation to joint space-delay estimation, then give
   each recovered path its own correlator/tracker and pseudorange/CN0 output.
6. Perform coherent multi-channel calibration and OTA validation using a known
   two-transmitter geometry.

The following site information is still required: approximate garage dimensions,
TX coordinates and mounting heights, receiver operating region/height, intended
band(s), and whether the final receiver can provide more than four coherent RF
channels.

## 9. Reproduction

From the `gnss-sdr-lya` directory:

```bash
python3 dev_notes/sim/simulate_coherent_music_parking.py --output-dir dev_notes/sim/results/coherent_music_parking
python3 -m unittest -v dev_notes/sim/test_coherent_music_parking.py
```

Outputs:

- `paper_music_vs_fbss.png`
- `music_correlation_monte_carlo.png`
- `parking_20m_array_condition_map.png`
- `parking_representative_music_spectra.png`
- `parking_representative_positions.csv`
- `summary.json`

## 10. References

- Wang, Zhang, Hu, 2014, *A Multipath Mitigation Method for Array
  Antenna-Based GPS Receiver*, DOI `10.3873/j.issn.1000-1328.2014.07.014`.
- Shan, Wax, Kailath, 1985, *On Spatial Smoothing for Direction-of-Arrival
  Estimation of Coherent Signals*, DOI `10.1109/TASSP.1985.1164649`.
- Pillai, Kwon, 1989, *Forward/Backward Spatial Smoothing Techniques for
  Coherent Signal Identification*, DOI `10.1109/29.17496`.
- Razgunas et al., 2023, *GNSS 2x2 Antenna Array with Beamforming for
  Multipath Detection*, DOI `10.1016/j.asr.2022.12.035`.
- Rougerie et al., 2012, *A New Multipath Mitigation Method for GNSS Receivers
  Based on an Antenna Array*, DOI `10.1155/2012/804732`.


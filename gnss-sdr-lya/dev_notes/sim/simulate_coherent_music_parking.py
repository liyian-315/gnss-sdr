#!/usr/bin/env python3
"""Reproduce coherent-source MUSIC failure and spatial-smoothing recovery.

The script has two experiments:

1. A paper-oriented ULA experiment based on Wang et al. (2014): a 10-element
   half-wavelength ULA, one desired GPS path at 30 deg and three coherent paths
   at -60/-30/5 deg. Conventional MUSIC is compared with forward-backward
   spatial smoothing (FBSS), using three overlapping 8-element subarrays.
2. A parking-garage geometry study: two same-code transmit antennas are 20 m
   apart and a four-element receive array is moved over a two-dimensional grid.
   ULA and four-element circular-array spatial coherence is mapped, and selected
   ULA positions are checked with conventional MUSIC and FBSS.

This is an array-processing simulation, not a full RF/GNSS waveform simulator.
The two sources share one complex waveform, which is the fully coherent case
that makes the ordinary source covariance rank one.
"""

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks


def steering_ula(theta_deg, n_elements, spacing_wl=0.5):
    """ULA steering vector; theta is measured from array broadside."""
    index = np.arange(n_elements, dtype=float)
    phase = 2.0 * np.pi * spacing_wl * index * np.sin(np.radians(theta_deg))
    return np.exp(1j * phase)


def steering_from_positions(element_xy_wl, bearing_deg):
    """Far-field steering vector for arbitrary 2-D element coordinates."""
    bearing = np.radians(bearing_deg)
    direction = np.array([np.cos(bearing), np.sin(bearing)])
    return np.exp(1j * 2.0 * np.pi * (element_xy_wl @ direction))


def ula_positions(n_elements, spacing_wl=0.5, axis_deg=0.0):
    axis = np.radians(axis_deg)
    unit = np.array([np.cos(axis), np.sin(axis)])
    offsets = (np.arange(n_elements) - (n_elements - 1) / 2.0) * spacing_wl
    return offsets[:, None] * unit[None, :]


def uca_positions(n_elements, adjacent_spacing_wl=0.5):
    """Circular array whose adjacent chord length equals adjacent_spacing_wl."""
    radius = adjacent_spacing_wl / (2.0 * np.sin(np.pi / n_elements))
    angle = 2.0 * np.pi * np.arange(n_elements) / n_elements
    return radius * np.column_stack([np.cos(angle), np.sin(angle)])


def normalized_coherence(first, second):
    denom = np.linalg.norm(first) * np.linalg.norm(second)
    return float(abs(np.vdot(first, second)) / max(denom, 1e-30))


def coherent_snapshots(
    angles_deg,
    amplitudes,
    n_elements,
    n_snapshots,
    snr_db,
    rng,
    correlation=1.0,
):
    """Generate ULA snapshots with the requested source correlation.

    correlation=1 means every source is a scaled copy of one waveform. For
    correlation<1, each source also receives an independent component.
    """
    angles = np.asarray(angles_deg, dtype=float)
    amplitudes = np.asarray(amplitudes, dtype=complex)
    manifold = np.column_stack([steering_ula(a, n_elements) for a in angles])
    common = (
        rng.standard_normal(n_snapshots) + 1j * rng.standard_normal(n_snapshots)
    ) / np.sqrt(2.0)
    independent = (
        rng.standard_normal((len(angles), n_snapshots))
        + 1j * rng.standard_normal((len(angles), n_snapshots))
    ) / np.sqrt(2.0)
    rho = float(np.clip(correlation, 0.0, 1.0))
    # The resulting pairwise normalized source correlation is rho.
    sources = np.sqrt(rho) * common[None, :] + np.sqrt(1.0 - rho) * independent
    sources *= amplitudes[:, None]
    clean = manifold @ sources
    signal_power = float(np.mean(np.abs(clean) ** 2))
    noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    noise = np.sqrt(noise_power / 2.0) * (
        rng.standard_normal(clean.shape) + 1j * rng.standard_normal(clean.shape)
    )
    return clean + noise


def covariance(samples):
    return samples @ samples.conj().T / samples.shape[1]


def forward_backward_spatial_smoothing(covariance_matrix, subarray_size):
    """Forward spatial smoothing followed by forward-backward averaging."""
    n_elements = covariance_matrix.shape[0]
    n_subarrays = n_elements - subarray_size + 1
    if not (1 < subarray_size <= n_elements):
        raise ValueError("subarray_size must be in [2, n_elements]")
    smoothed = np.zeros((subarray_size, subarray_size), dtype=complex)
    for start in range(n_subarrays):
        smoothed += covariance_matrix[
            start : start + subarray_size, start : start + subarray_size
        ]
    smoothed /= n_subarrays
    reversal = np.fliplr(np.eye(subarray_size))
    return 0.5 * (smoothed + reversal @ smoothed.conj() @ reversal)


def music_spectrum(covariance_matrix, n_sources, angle_grid_deg, manifold=None):
    """Return normalized MUSIC pseudospectrum and descending eigenvalues."""
    hermitian = 0.5 * (covariance_matrix + covariance_matrix.conj().T)
    eigenvalues, eigenvectors = np.linalg.eigh(hermitian)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = np.real(eigenvalues[order])
    eigenvectors = eigenvectors[:, order]
    if n_sources >= covariance_matrix.shape[0]:
        raise ValueError("n_sources must be smaller than array dimension")
    noise_subspace = eigenvectors[:, n_sources:]
    if manifold is None:
        manifold = np.column_stack(
            [steering_ula(angle, covariance_matrix.shape[0]) for angle in angle_grid_deg]
        )
    denominator = np.sum(abs(noise_subspace.conj().T @ manifold) ** 2, axis=0)
    spectrum = 1.0 / np.maximum(denominator, 1e-15)
    spectrum /= np.max(spectrum)
    return spectrum, eigenvalues


def principal_eigenvector_spectrum(covariance_matrix, angle_grid_deg):
    """Wang et al. (2014), Eq. (12): estimate only the strongest LOS DOA."""
    hermitian = 0.5 * (covariance_matrix + covariance_matrix.conj().T)
    eigenvalues, eigenvectors = np.linalg.eigh(hermitian)
    principal = eigenvectors[:, np.argmax(eigenvalues)]
    manifold = np.column_stack(
        [steering_ula(angle, covariance_matrix.shape[0]) for angle in angle_grid_deg]
    )
    energy = np.sum(abs(manifold) ** 2, axis=0)
    denominator = energy - abs(principal.conj() @ manifold) ** 2
    spectrum = energy / np.maximum(denominator, 1e-15)
    spectrum /= np.max(spectrum)
    return spectrum


def strongest_peaks(angle_grid_deg, spectrum, count, minimum_separation_deg=3.0):
    grid_step = float(np.median(np.diff(angle_grid_deg)))
    distance = max(1, int(round(minimum_separation_deg / grid_step)))
    peaks, _ = find_peaks(spectrum, distance=distance)
    if len(peaks) < count:
        candidates = np.argsort(spectrum)[::-1]
        selected = list(peaks)
        for candidate in candidates:
            if all(abs(candidate - old) >= distance for old in selected):
                selected.append(int(candidate))
            if len(selected) >= count:
                break
        peaks = np.asarray(selected, dtype=int)
    peaks = peaks[np.argsort(spectrum[peaks])[::-1]][:count]
    return np.sort(angle_grid_deg[peaks])


def estimated_signal_rank(eigenvalues, max_sources, noise_multiplier=5.0):
    """Simple diagnostic rank using trailing eigenvalues as the noise floor."""
    eigenvalues = np.asarray(eigenvalues, dtype=float)
    if max_sources >= len(eigenvalues):
        raise ValueError("max_sources must be smaller than covariance dimension")
    noise_floor = float(np.median(eigenvalues[max_sources:]))
    return int(np.sum(eigenvalues[:max_sources] > noise_multiplier * noise_floor))


def run_paper_reproduction(output_dir, rng):
    angles = np.array([30.0, -60.0, -30.0, 5.0])
    amplitudes = 10.0 ** (np.array([0.0, -3.0, -4.0, -6.0]) / 20.0)
    n_elements = 10
    subarray_size = 8
    angle_grid = np.linspace(-90.0, 90.0, 1801)

    # Cross-code accumulation in the paper raises effective SNR. The simulation
    # uses 30 dB after that processing instead of pretending raw -20 dB samples
    # are directly suitable for MUSIC.
    samples = coherent_snapshots(
        angles, amplitudes, n_elements, 4096, 30.0, rng, correlation=1.0
    )
    raw_covariance = covariance(samples)
    smooth_covariance = forward_backward_spatial_smoothing(
        raw_covariance, subarray_size
    )
    conventional, raw_eigenvalues = music_spectrum(
        raw_covariance, len(angles), angle_grid
    )
    smoothed, smooth_eigenvalues = music_spectrum(
        smooth_covariance, len(angles), angle_grid
    )
    principal_raw = principal_eigenvector_spectrum(raw_covariance, angle_grid)
    principal_fbss = principal_eigenvector_spectrum(smooth_covariance, angle_grid)

    fig, axes = plt.subplots(2, 2, figsize=(13, 9.0))
    flat_axes = axes.flat
    flat_axes[0].plot(angle_grid, 10.0 * np.log10(np.maximum(conventional, 1e-12)))
    flat_axes[0].set_title("Conventional MUSIC: coherent-source rank loss")
    flat_axes[1].plot(angle_grid, 10.0 * np.log10(np.maximum(smoothed, 1e-12)))
    flat_axes[1].set_title("FBSS-MUSIC: four coherent paths restored")
    flat_axes[2].plot(angle_grid, 10.0 * np.log10(np.maximum(principal_raw, 1e-12)))
    flat_axes[2].set_title("Paper Eq. (12), before smoothing: strongest path only")
    flat_axes[3].plot(angle_grid, 10.0 * np.log10(np.maximum(principal_fbss, 1e-12)))
    flat_axes[3].set_title("Paper Eq. (12), after smoothing: LOS estimate")
    for axis in axes.flat:
        for angle in angles:
            axis.axvline(angle, color="tab:red", linestyle="--", linewidth=0.8)
        axis.set_xlim(-90, 90)
        axis.set_ylim(-45, 1)
        axis.set_xlabel("DOA from ULA broadside (deg)")
        axis.set_ylabel("Normalized spectrum (dB)")
        axis.grid(True, alpha=0.25)
    fig.suptitle("Wang et al. (2014) parameter reproduction: M=10, P=8, L=3")
    fig.tight_layout()
    figure_path = output_dir / "paper_music_vs_fbss.png"
    fig.savefig(figure_path, dpi=180)
    plt.close(fig)

    return {
        "angles_deg": angles.tolist(),
        "conventional_signal_rank": estimated_signal_rank(raw_eigenvalues, len(angles)),
        "fbss_signal_rank": estimated_signal_rank(smooth_eigenvalues, len(angles)),
        "conventional_peaks_deg": strongest_peaks(
            angle_grid, conventional, len(angles)
        ).round(2).tolist(),
        "fbss_peaks_deg": strongest_peaks(
            angle_grid, smoothed, len(angles)
        ).round(2).tolist(),
        "paper_los_before_smoothing_deg": float(angle_grid[np.argmax(principal_raw)]),
        "paper_los_after_smoothing_deg": float(angle_grid[np.argmax(principal_fbss)]),
        "figure": str(figure_path),
    }


def match_two_doa(truth_deg, estimate_deg, tolerance_deg=2.0):
    truth = np.sort(np.asarray(truth_deg, dtype=float))
    estimate = np.sort(np.asarray(estimate_deg, dtype=float))
    return bool(len(estimate) == 2 and np.max(np.abs(truth - estimate)) <= tolerance_deg)


def run_correlation_monte_carlo(output_dir, seed):
    """Quantify ordinary MUSIC collapse as source correlation approaches one."""
    correlations = np.array([0.0, 0.5, 0.9, 0.99, 1.0])
    snr_values = np.array([-5.0, 0.0, 5.0, 10.0, 15.0])
    truth = np.array([-25.0, 35.0])
    angle_grid = np.linspace(-90.0, 90.0, 901)
    raw_manifold = np.column_stack([steering_ula(a, 4) for a in angle_grid])
    smooth_manifold = np.column_stack([steering_ula(a, 3) for a in angle_grid])
    trials = 100
    conventional_rate = np.zeros((len(snr_values), len(correlations)))
    fbss_rate = np.zeros_like(conventional_rate)
    for snr_index, snr_db in enumerate(snr_values):
        for rho_index, rho in enumerate(correlations):
            conventional_success = 0
            fbss_success = 0
            for trial in range(trials):
                rng = np.random.default_rng(seed + 10000 * snr_index + 100 * rho_index + trial)
                samples = coherent_snapshots(
                    truth, [1.0, 10.0 ** (-6.0 / 20.0)], 4, 512,
                    snr_db, rng, correlation=rho
                )
                raw = covariance(samples)
                smooth = forward_backward_spatial_smoothing(raw, 3)
                conventional, _ = music_spectrum(
                    raw, 2, angle_grid, manifold=raw_manifold
                )
                fbss, _ = music_spectrum(
                    smooth, 2, angle_grid, manifold=smooth_manifold
                )
                conventional_success += match_two_doa(
                    truth, strongest_peaks(angle_grid, conventional, 2)
                )
                fbss_success += match_two_doa(
                    truth, strongest_peaks(angle_grid, fbss, 2)
                )
            conventional_rate[snr_index, rho_index] = conventional_success / trials
            fbss_rate[snr_index, rho_index] = fbss_success / trials

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8), constrained_layout=True)
    for axis, values, title in [
        (axes[0], conventional_rate, "Conventional MUSIC success rate"),
        (axes[1], fbss_rate, "FBSS-MUSIC success rate"),
    ]:
        image = axis.imshow(
            values, origin="lower", aspect="auto",
            vmin=0.0, vmax=1.0, cmap="viridis"
        )
        for row, snr_db in enumerate(snr_values):
            for column, rho in enumerate(correlations):
                axis.text(column, row, "%.0f%%" % (100 * values[row, column]),
                          ha="center", va="center", color="white" if values[row, column] < 0.55 else "black")
        axis.set_title(title)
        axis.set_xlabel("source correlation coefficient")
        axis.set_ylabel("array SNR (dB)")
        axis.set_xticks(np.arange(len(correlations)), [str(v) for v in correlations])
        axis.set_yticks(np.arange(len(snr_values)), [str(v) for v in snr_values])
        fig.colorbar(image, ax=axis, label="both DOAs within 2 deg")
    figure_path = output_dir / "music_correlation_monte_carlo.png"
    fig.savefig(figure_path, dpi=180)
    plt.close(fig)
    return {
        "truth_deg": truth.tolist(),
        "trials_per_cell": trials,
        "correlations": correlations.tolist(),
        "snr_db": snr_values.tolist(),
        "conventional_success_rate": conventional_rate.tolist(),
        "fbss_success_rate": fbss_rate.tolist(),
        "figure": str(figure_path),
    }


def bearing_from_receiver(receiver_xy, transmitter_xy):
    delta = np.asarray(transmitter_xy) - np.asarray(receiver_xy)
    return float(np.degrees(np.arctan2(delta[1], delta[0])))


def pair_coherence(receiver_xy, transmitters_xy, element_xy_wl):
    bearings = [bearing_from_receiver(receiver_xy, tx) for tx in transmitters_xy]
    first = steering_from_positions(element_xy_wl, bearings[0])
    second = steering_from_positions(element_xy_wl, bearings[1])
    return normalized_coherence(first, second), bearings


def circular_angle_difference(first_deg, second_deg):
    return abs((first_deg - second_deg + 180.0) % 360.0 - 180.0)


def parking_grid(transmitters_xy, x_values, y_values, element_xy_wl):
    coherence = np.full((len(y_values), len(x_values)), np.nan)
    angle_separation = np.full_like(coherence, np.nan)
    for row, y in enumerate(y_values):
        for column, x in enumerate(x_values):
            receiver = np.array([x, y])
            if min(np.linalg.norm(receiver - tx) for tx in transmitters_xy) < 0.5:
                continue
            value, bearings = pair_coherence(receiver, transmitters_xy, element_xy_wl)
            coherence[row, column] = value
            angle_separation[row, column] = circular_angle_difference(*bearings)
    return coherence, angle_separation


def simulate_ula_position(receiver_xy, transmitters_xy, rng, snr_db=15.0):
    """Two-source ULA check at one receiver position."""
    bearings = [bearing_from_receiver(receiver_xy, tx) for tx in transmitters_xy]
    # Convert world bearing to the broadside convention used by steering_ula.
    doa = np.array([((90.0 - b + 180.0) % 360.0) - 180.0 for b in bearings])
    # A ULA cannot distinguish front/back. Fold to [-90, 90].
    doa = np.where(doa > 90.0, 180.0 - doa, doa)
    doa = np.where(doa < -90.0, -180.0 - doa, doa)
    samples = coherent_snapshots(doa, [1.0, 0.5], 4, 2048, snr_db, rng, 1.0)
    raw = covariance(samples)
    smooth = forward_backward_spatial_smoothing(raw, 3)
    grid = np.linspace(-90.0, 90.0, 1801)
    conventional, raw_eigenvalues = music_spectrum(raw, 2, grid)
    fbss, smooth_eigenvalues = music_spectrum(smooth, 2, grid)
    manifold = [steering_ula(angle, 4) for angle in doa]
    coherence = normalized_coherence(manifold[0], manifold[1])
    state = "UNRESOLVED" if coherence > 0.98 else "SEPARABLE_CANDIDATE"
    return {
        "bearings_deg": bearings,
        "folded_doa_deg": doa.tolist(),
        "conventional_peaks_deg": strongest_peaks(grid, conventional, 2).tolist(),
        "fbss_peaks_deg": strongest_peaks(grid, fbss, 2).tolist(),
        "spatial_coherence": coherence,
        "state": state,
        "raw_rank": estimated_signal_rank(raw_eigenvalues, 2),
        "fbss_rank": estimated_signal_rank(smooth_eigenvalues, 2),
        "grid": grid,
        "conventional_spectrum": conventional,
        "fbss_spectrum": fbss,
    }


def run_parking_study(output_dir, rng, tx_separation_m):
    transmitters = np.array(
        [[-tx_separation_m / 2.0, 0.0], [tx_separation_m / 2.0, 0.0]]
    )
    x_values = np.linspace(-30.0, 30.0, 121)
    y_values = np.linspace(-20.0, 20.0, 81)
    ula = ula_positions(4, 0.5, axis_deg=0.0)
    uca = uca_positions(4, 0.5)
    ula_coherence, angle_separation = parking_grid(
        transmitters, x_values, y_values, ula
    )
    uca_coherence, _ = parking_grid(transmitters, x_values, y_values, uca)

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), constrained_layout=True)
    extent = [x_values[0], x_values[-1], y_values[0], y_values[-1]]
    panels = [
        (angle_separation, "Geometric bearing separation (deg)", "viridis", 0, 180),
        (ula_coherence, "4-element ULA spatial coherence", "magma_r", 0, 1),
        (uca_coherence, "4-element circular-array coherence", "magma_r", 0, 1),
    ]
    for axis, (data, title, cmap, vmin, vmax) in zip(axes, panels):
        image = axis.imshow(
            data,
            origin="lower",
            extent=extent,
            aspect="auto",
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
        )
        axis.scatter(transmitters[:, 0], transmitters[:, 1], marker="^", s=70,
                     color="cyan", edgecolor="black", label="DAS TX")
        axis.set_title(title)
        axis.set_xlabel("receiver x (m)")
        axis.set_ylabel("receiver y (m)")
        axis.legend(loc="upper right")
        fig.colorbar(image, ax=axis, shrink=0.85)
    map_path = output_dir / "parking_20m_array_condition_map.png"
    fig.savefig(map_path, dpi=180)
    plt.close(fig)

    representative = {
        "between_center": np.array([0.0, 0.0]),
        "between_offset": np.array([0.0, 5.0]),
        "outside_left": np.array([-20.0, 0.0]),
        "beside_tx0": np.array([-10.0, 5.0]),
        "far_side": np.array([0.0, 20.0]),
    }
    rows = []
    spectra = {}
    for name, receiver in representative.items():
        ula_mu, bearings = pair_coherence(receiver, transmitters, ula)
        uca_mu, _ = pair_coherence(receiver, transmitters, uca)
        result = simulate_ula_position(receiver, transmitters, rng)
        rows.append(
            {
                "name": name,
                "x_m": receiver[0],
                "y_m": receiver[1],
                "bearing0_deg": bearings[0],
                "bearing1_deg": bearings[1],
                "bearing_separation_deg": circular_angle_difference(*bearings),
                "ula_coherence": ula_mu,
                "uca_coherence": uca_mu,
                "ula_state": result["state"],
                "raw_rank": result["raw_rank"],
                "fbss_rank": result["fbss_rank"],
                "true_folded_ula_doa_deg": result["folded_doa_deg"],
                "conventional_peaks_deg": result["conventional_peaks_deg"],
                "fbss_peaks_deg": result["fbss_peaks_deg"],
            }
        )
        spectra[name] = result

    csv_path = output_dir / "parking_representative_positions.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    fig, axes = plt.subplots(len(representative), 1, figsize=(10, 13), sharex=True)
    for axis, (name, result) in zip(axes, spectra.items()):
        axis.plot(
            result["grid"],
            10.0 * np.log10(np.maximum(result["conventional_spectrum"], 1e-12)),
            label="conventional MUSIC",
            alpha=0.75,
        )
        axis.plot(
            result["grid"],
            10.0 * np.log10(np.maximum(result["fbss_spectrum"], 1e-12)),
            label="FBSS MUSIC",
        )
        for truth in result["folded_doa_deg"]:
            axis.axvline(truth, color="black", linestyle="--", linewidth=0.8)
        axis.set_title(name)
        axis.set_ylim(-45, 1)
        axis.set_ylabel("dB")
        axis.grid(True, alpha=0.25)
    axes[0].legend(loc="lower left")
    axes[-1].set_xlabel("folded ULA DOA (deg)")
    fig.tight_layout()
    spectra_path = output_dir / "parking_representative_music_spectra.png"
    fig.savefig(spectra_path, dpi=180)
    plt.close(fig)

    finite_ula = ula_coherence[np.isfinite(ula_coherence)]
    finite_uca = uca_coherence[np.isfinite(uca_coherence)]
    return {
        "transmitters_xy_m": transmitters.tolist(),
        "ula_fraction_mu_below_0_8": float(np.mean(finite_ula < 0.8)),
        "ula_fraction_mu_below_0_95": float(np.mean(finite_ula < 0.95)),
        "uca_fraction_mu_below_0_8": float(np.mean(finite_uca < 0.8)),
        "uca_fraction_mu_below_0_95": float(np.mean(finite_uca < 0.95)),
        "condition_map": str(map_path),
        "representative_csv": str(csv_path),
        "representative_spectra": str(spectra_path),
        "representative": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="space_array_reproduction")
    parser.add_argument("--tx-separation-m", type=float, default=20.0)
    parser.add_argument("--seed", type=int, default=20260812)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    paper = run_paper_reproduction(output_dir, rng)
    monte_carlo = run_correlation_monte_carlo(output_dir, args.seed + 1000000)
    parking = run_parking_study(output_dir, rng, args.tx_separation_m)
    summary = {
        "paper_reproduction": paper,
        "correlation_monte_carlo": monte_carlo,
        "parking_study": parking,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("paper conventional signal rank:", paper["conventional_signal_rank"])
    print("paper FBSS signal rank:", paper["fbss_signal_rank"])
    print("paper truth angles:", paper["angles_deg"])
    print("paper conventional peaks:", paper["conventional_peaks_deg"])
    print("paper FBSS peaks:", paper["fbss_peaks_deg"])
    print("paper LOS before/after FBSS: %.1f / %.1f deg" % (
        paper["paper_los_before_smoothing_deg"], paper["paper_los_after_smoothing_deg"]))
    print("parking ULA mu<0.8 coverage: %.1f%%" % (100 * parking["ula_fraction_mu_below_0_8"]))
    print("parking UCA mu<0.8 coverage: %.1f%%" % (100 * parking["uca_fraction_mu_below_0_8"]))
    conventional_coherent = np.asarray(monte_carlo["conventional_success_rate"])[:, -1]
    fbss_coherent = np.asarray(monte_carlo["fbss_success_rate"])[:, -1]
    print("fully coherent conventional success by SNR:", conventional_coherent.tolist())
    print("fully coherent FBSS success by SNR:", fbss_coherent.tolist())
    print("wrote", summary_path)


if __name__ == "__main__":
    main()

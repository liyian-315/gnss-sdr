#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulate_coherent_music_parking as sim


class CoherentMusicParkingTest(unittest.TestCase):
    def test_fully_coherent_source_covariance_loses_rank(self):
        rng = np.random.default_rng(1)
        samples = sim.coherent_snapshots(
            [-25.0, 35.0], [1.0, 0.7], 6, 8192, 60.0, rng, correlation=1.0
        )
        eigenvalues = np.linalg.eigvalsh(sim.covariance(samples))[::-1]
        self.assertEqual(sim.estimated_signal_rank(eigenvalues, 2), 1)

    def test_spatial_smoothing_restores_two_signal_rank(self):
        rng = np.random.default_rng(2)
        samples = sim.coherent_snapshots(
            [-25.0, 35.0], [1.0, 0.7], 6, 8192, 45.0, rng, correlation=1.0
        )
        raw = sim.covariance(samples)
        smooth = sim.forward_backward_spatial_smoothing(raw, 5)
        eigenvalues = np.linalg.eigvalsh(smooth)[::-1]
        self.assertGreaterEqual(sim.estimated_signal_rank(eigenvalues, 2), 2)

        grid = np.linspace(-90.0, 90.0, 3601)
        spectrum, _ = sim.music_spectrum(smooth, 2, grid)
        peaks = sim.strongest_peaks(grid, spectrum, 2)
        np.testing.assert_allclose(peaks, [-25.0, 35.0], atol=0.5)

    def test_four_element_fbss_resolves_non_degenerate_two_source_case(self):
        rng = np.random.default_rng(3)
        transmitters = np.array([[-10.0, 0.0], [10.0, 0.0]])
        result = sim.simulate_ula_position(
            np.array([0.0, 5.0]), transmitters, rng, snr_db=30.0
        )
        truth = np.sort(result["folded_doa_deg"])
        recovered = np.sort(result["fbss_peaks_deg"])
        np.testing.assert_allclose(recovered, truth, atol=1.0)

    def test_same_spatial_signature_is_unidentifiable(self):
        first = sim.steering_ula(20.0, 4)
        second = sim.steering_ula(20.0, 4)
        self.assertAlmostEqual(sim.normalized_coherence(first, second), 1.0)


if __name__ == "__main__":
    unittest.main()

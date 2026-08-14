#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ula_gnss_waveform_fbss_lab as lab


class UlaGnssWaveformFbssLabTest(unittest.TestCase):
    def test_ca_code_is_balanced_and_periodic_gold_code(self):
        code = lab.gps_l1_ca_code(28)
        self.assertEqual(len(code), 1023)
        self.assertEqual(set(code), {-1.0, 1.0})
        self.assertEqual(abs(int(np.sum(code))), 1)
        normalized = np.array([np.dot(code, np.roll(code, shift)) for shift in range(1023)]) / 1023.0
        self.assertAlmostEqual(normalized[0], 1.0)
        self.assertLess(np.max(abs(normalized[1:])), 0.1)

    def test_cn0_conversion_matches_one_ms_snr(self):
        self.assertAlmostEqual(lab.CN0_A_AT_REFERENCE_DB_HZ + 10.0 * np.log10(0.001), 0.0)
        self.assertLess(lab.CN0_A_AT_REFERENCE_DB_HZ - 10.0 * np.log10(lab.SAMPLE_RATE_HZ), -40.0)

    def test_equal_geometry_and_cables_have_zero_relative_delay(self):
        receiver = np.array([0.0, 5.0])
        a = lab.effective_path_length_m(receiver, [-10.0, 0.0], 10.0)
        b = lab.effective_path_length_m(receiver, [10.0, 0.0], 10.0)
        self.assertAlmostEqual(a, b)

    def test_small_waveform_run_has_expected_shapes(self):
        old_periods = lab.CODE_PERIODS
        old_rate = lab.SAMPLE_RATE_HZ
        try:
            lab.CODE_PERIODS = 4
            lab.SAMPLE_RATE_HZ = 4.092e6
            correlators, taps, positions, truth = lab.simulate_correlators(
                [0.0, 5.0], np.random.default_rng(1))
            self.assertEqual(correlators.shape, (4, 4, len(taps)))
            self.assertEqual(positions.shape, (4, 2))
            self.assertEqual(len(truth["bearings_deg"]), 2)
        finally:
            lab.CODE_PERIODS = old_periods
            lab.SAMPLE_RATE_HZ = old_rate

    def test_fbss_restores_rank_for_two_coherent_sources(self):
        positions = lab.ula_positions_m()
        bearings = [206.565051177078, 333.434948822922]
        manifold = lab.steering_manifold(positions, bearings)
        # 两源共用同一复快拍，因此原始阵列信号严格相干、协方差秩为 1。
        common = np.exp(1j * np.linspace(0.0, 4.0 * np.pi, 64))
        snapshots = (manifold @ np.array([1.0, 0.8j]))[:, None] * common[None, :]
        raw = lab.array_tools.covariance(snapshots)
        smoothed = lab.array_tools.forward_backward_spatial_smoothing(raw, 3)
        raw_eigenvalues = np.linalg.eigvalsh(raw)
        smooth_eigenvalues = np.linalg.eigvalsh(smoothed)
        self.assertLess(raw_eigenvalues[-2], raw_eigenvalues[-1] * 1e-10)
        self.assertGreater(smooth_eigenvalues[-2], smooth_eigenvalues[-1] * 0.05)

        grid = np.arange(180.0, 360.0 + 0.25, 0.5)
        sub_positions = positions[:3] - np.mean(positions[:3], axis=0)
        spectrum, _ = lab.array_tools.music_spectrum(
            smoothed, 2, grid,
            manifold=lab.steering_manifold(sub_positions, grid))
        peaks = lab.strongest_peaks(grid, spectrum)
        self.assertEqual(len(peaks), 2)
        for truth in bearings:
            self.assertLess(min(lab.array_tools.circular_angle_difference(truth, peak)
                                for peak in peaks), 1.0)


if __name__ == "__main__":
    unittest.main()

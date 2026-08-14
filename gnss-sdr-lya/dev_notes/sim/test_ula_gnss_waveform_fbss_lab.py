#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ula_gnss_waveform_fbss_lab as lab


class UlaGnssWaveformFbssLabTest(unittest.TestCase):
    @staticmethod
    def _octal(bits):
        return "".join(str(int("".join(str(int(bit)) for bit in bits[i:i + 3]), 2))
                       for i in range(0, len(bits), 3))

    def test_b2a_pilot_primary_code_matches_icd(self):
        expected = {
            11: ("24752054", "60410454"),
            28: ("55613763", "37225071"),
        }
        for prn, (first, last) in expected.items():
            with self.subTest(prn=prn):
                code = lab.b2a_pilot_primary_code(prn)
                bits = (code < 0).astype(int)
                self.assertEqual(len(code), 10230)
                self.assertEqual(set(code), {-1.0, 1.0})
                self.assertEqual(self._octal(bits[:24]), first)
                self.assertEqual(self._octal(bits[-24:]), last)

    def test_b2a_pilot_secondary_code_matches_icd(self):
        expected = {
            11: ("36242432", "16314440"),
            28: ("11326621", "43507041"),
        }
        for prn, (first, last) in expected.items():
            with self.subTest(prn=prn):
                code = lab.b2a_pilot_secondary_code(prn)
                bits = (code < 0).astype(int)
                self.assertEqual(len(code), 100)
                self.assertEqual(self._octal(bits[:24]), first)
                self.assertEqual(self._octal(bits[-24:]), last)

    def test_b2a_data_primary_code_matches_icd(self):
        expected = {
            11: ("24751346", "12470110"),
            28: ("55611514", "30732736"),
        }
        for prn, (first, last) in expected.items():
            with self.subTest(prn=prn):
                code = lab.b2a_data_primary_code(prn)
                bits = (code < 0).astype(int)
                self.assertEqual(self._octal(bits[:24]), first)
                self.assertEqual(self._octal(bits[-24:]), last)

    def test_cn0_conversion_matches_one_ms_snr(self):
        self.assertAlmostEqual(lab.CN0_A_AT_REFERENCE_DB_HZ + 10.0 * np.log10(0.001), 0.0)
        self.assertLess(lab.CN0_A_AT_REFERENCE_DB_HZ - 10.0 * np.log10(lab.SAMPLE_RATE_HZ), -40.0)

    def test_equal_geometry_and_cables_have_zero_relative_delay(self):
        receiver = np.array([0.0, 5.0])
        a = lab.effective_path_length_m(receiver, [-10.0, 0.0], 10.0)
        b = lab.effective_path_length_m(receiver, [10.0, 0.0], 10.0)
        self.assertAlmostEqual(a, b)

    def test_receiver_at_tx_a_has_twenty_meter_planar_path_difference(self):
        receiver = np.array([-10.0, 0.0])
        a = lab.effective_path_length_m(receiver, [-10.0, 0.0], 10.0)
        b = lab.effective_path_length_m(receiver, [10.0, 0.0], 10.0)
        self.assertAlmostEqual(b - a, 20.0)

    def test_small_waveform_run_has_expected_shapes(self):
        old_periods = lab.CODE_PERIODS
        old_rate = lab.SAMPLE_RATE_HZ
        try:
            lab.CODE_PERIODS = 4
            lab.SAMPLE_RATE_HZ = 20.46e6
            correlators, taps, positions, truth = lab.simulate_correlators(
                [0.0, 5.0], np.random.default_rng(1))
            self.assertEqual(correlators.shape, (4, 4, len(taps)))
            self.assertEqual(positions.shape, (4, 2))
            self.assertEqual(len(truth["bearings_deg"]), 2)
            self.assertEqual(truth["signal"], "BDS B2a pilot")
            _, profiles, _ = lab.estimate_delays(
                correlators, positions, truth["bearings_deg"], taps,
                lab.b2a_pilot_primary_code(lab.B2A_PRN))
            self.assertTrue(np.iscomplexobj(profiles))
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

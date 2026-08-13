#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sage_stap_array_comparison as lab


class SageStapArrayComparisonTest(unittest.TestCase):
    def test_paper_slice_recovers_two_paths_and_decreases_residual(self):
        result = lab.paper_reproduction(seed=7)
        estimate = result["estimates"]
        self.assertAlmostEqual(estimate[0]["bearing_deg"], 131.0, delta=2.1)
        self.assertAlmostEqual(estimate[1]["bearing_deg"], -65.0, delta=2.1)
        self.assertAlmostEqual(estimate[1]["delay_chips"], 0.1, delta=0.021)
        self.assertAlmostEqual(estimate[1]["doppler_hz"], 5.0, delta=1.1)
        self.assertLessEqual(result["residual_history"][-1], result["residual_history"][0] + 1e-9)

    def test_fbss_uses_three_element_subarrays_with_noise_subspace(self):
        ktaps, kernel = lab.load_kernel()
        taps = np.arange(-1.5, 1.5001, 0.1)
        positions = lab.ula_positions()
        paths = [dict(bearing_deg=120.0, delay_chips=0.0),
                 dict(bearing_deg=60.0, delay_chips=0.5, ratio_db=-3.0, phase_deg=30.0)]
        data = lab.synthesize(paths, positions, taps, ktaps, kernel, 128, 0.02,
                              np.random.default_rng(3))
        estimates, _spectrum, _grid, eigenvalues = lab.ula_fbss(
            data, positions, taps, ktaps, kernel, None, np.arange(0, 0.81, 0.02))
        self.assertEqual(len(eigenvalues), 3)
        self.assertEqual(len(estimates), 2)
        self.assertLess(lab.match_errors(estimates, paths)[0], 5.0)

    def test_both_methods_share_kernel_loader(self):
        taps, kernel = lab.load_kernel()
        np.testing.assert_allclose(kernel, np.maximum(0.0, 1.0 - np.abs(taps)))


if __name__ == "__main__":
    unittest.main()

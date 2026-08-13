#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import square_array_coherent_separation_lab as lab


class SquareArrayCoherentSeparationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = lab.current_config()
        cls.config.update(
            n_blocks=32,
            search_angle_step=5.0,
            search_delay_step=0.1,
        )
        cls.dense, cls.taps, cls.kernel, cls.positions = lab.synthesize_scene(
            cls.config
        )

    def test_two_by_two_standard_smoothing_has_no_noise_subspace(self):
        raw = lab.raw_music(self.dense, self.taps, self.positions)
        diagnostic = lab.square_smoothing_diagnostic(raw[0])
        self.assertEqual(diagnostic["subarray_dimension"], 2)
        self.assertEqual(diagnostic["noise_subspace_dimension"], 0)
        self.assertFalse(diagnostic["usable_for_two_source_music"])

    def test_coherent_raw_covariance_loses_second_signal_rank(self):
        raw = lab.raw_music(self.dense, self.taps, self.positions)
        self.assertEqual(lab.covariance_rank(raw[3]), 1)

    def test_space_delay_glrt_recovers_coherent_pair(self):
        result = lab.fit_space_delay_glrt(
            self.dense, self.taps, self.kernel, self.positions, self.config
        )
        self.assertAlmostEqual(result["angle_a_deg"], -30.0, delta=5.0)
        self.assertAlmostEqual(result["angle_b_deg"], 30.0, delta=5.0)
        self.assertAlmostEqual(result["delay_b_chips"], 0.5, delta=0.1)
        self.assertGreater(result["improvement_db"], 6.0)
        self.assertEqual(result["state"], "RELIABLE")

    def test_support_constrained_reconstruction_restores_rank_and_peaks(self):
        result = lab.fit_space_delay_glrt(
            self.dense, self.taps, self.kernel, self.positions, self.config
        )
        rebuilt = lab.reconstructed_music(
            result, self.positions, self.config["noise_sigma"]
        )
        self.assertEqual(lab.covariance_rank(rebuilt[3]), 2)
        np.testing.assert_allclose(rebuilt[4], [-30.0, 30.0], atol=1.0)

    def test_single_source_control_rejects_second_source(self):
        config = dict(self.config)
        config["emit_second_source"] = False
        dense, taps, kernel, positions = lab.synthesize_scene(config)
        result = lab.fit_space_delay_glrt(dense, taps, kernel, positions, config)
        self.assertEqual(result["state"], "NO_SECOND_SOURCE")
        self.assertLess(result["improvement_db"], 6.0)


if __name__ == "__main__":
    unittest.main()

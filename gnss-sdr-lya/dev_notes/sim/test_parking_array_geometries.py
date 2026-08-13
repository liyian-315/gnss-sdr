#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_parking_array_geometries as comparison
import simulate_coherent_music_parking as core


class ParkingArrayGeometryTest(unittest.TestCase):
    def test_two_by_two_has_no_valid_translated_smoothing_subarray(self):
        _, shape, subarray = comparison.geometry_definition("UPA", 4)
        self.assertEqual(shape, (2, 2))
        self.assertIsNone(subarray)

    def test_two_by_three_smoothing_restores_rank(self):
        rng = np.random.default_rng(7)
        positions = comparison.upa_positions(2, 3)
        manifold = np.column_stack(
            [core.steering_from_positions(positions, angle) for angle in (210, 330)]
        )
        samples = core.coherent_snapshots_from_manifold(
            manifold, [1.0, 0.5j], 8192, 40.0, rng, correlation=1.0
        )
        smoothed, count = comparison.rectangular_spatial_smoothing(
            core.covariance(samples), (2, 3), (2, 2)
        )
        eigenvalues = np.linalg.eigvalsh(smoothed)[::-1]
        self.assertEqual(count, 2)
        self.assertGreaterEqual(core.estimated_signal_rank(eigenvalues, 2), 2)

    def test_all_raw_covariances_lose_rank_for_coherent_sources(self):
        transmitters = np.array([[-10.0, 0.0], [10.0, 0.0]])
        receiver = np.array([0.0, 5.0])
        for kind in ("ULA", "UCA", "UPA"):
            result = comparison.simulate_method_set(
                kind, 4, receiver, transmitters, np.random.default_rng(9), 0.4,
                snr_db=40.0
            )
            self.assertEqual(result["raw_rank"], 1, kind)

    def test_comparison_rejects_non_four_element_inputs(self):
        with self.assertRaises(ValueError):
            comparison.geometry_definition("UCA", 8)

    def test_four_element_uca_equals_square_array_up_to_rotation(self):
        uca, _, _ = comparison.geometry_definition("UCA", 4, 0.0)
        square, _, _ = comparison.geometry_definition("UPA", 4, 45.0)
        # Point ordering differs, so compare sorted coordinate sets.
        sort_rows = lambda values: values[np.lexsort((values[:, 1], values[:, 0]))]
        np.testing.assert_allclose(sort_rows(uca), sort_rows(square), atol=1e-12)


if __name__ == "__main__":
    unittest.main()

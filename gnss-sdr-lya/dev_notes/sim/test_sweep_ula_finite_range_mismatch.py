#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep_ula_finite_range_mismatch as sweep
import ula_gnss_waveform_fbss_lab as lab


class FiniteRangeMismatchSweepTest(unittest.TestCase):
    def test_spherical_phase_mismatch_decreases_with_distance(self):
        positions = lab.ula_positions_m()
        values = []
        for distance in (5.0, 10.0, 20.0):
            receiver, tx_a, _ = sweep.scaled_geometry(distance)
            values.append(sweep.phase_mismatch_deg(receiver, tx_a, positions)[0])
        self.assertGreater(values[0], values[1])
        self.assertGreater(values[1], values[2])
        self.assertAlmostEqual(values[0], 4.58504461849691, places=6)

    def test_cable_adjustment_keeps_effective_delay_fixed(self):
        names = ("TX_A_X_M", "TX_A_Y_M", "TX_B_X_M", "TX_B_Y_M",
                 "CABLE_A_LENGTH_M", "CABLE_B_LENGTH_M")
        original = {name: getattr(lab, name) for name in names}
        try:
            receiver, _, _, _ = sweep.configure_geometry(20.0)
            a = lab.effective_path_length_m(
                receiver, [lab.TX_A_X_M, lab.TX_A_Y_M], lab.CABLE_A_LENGTH_M)
            b = lab.effective_path_length_m(
                receiver, [lab.TX_B_X_M, lab.TX_B_Y_M], lab.CABLE_B_LENGTH_M)
            self.assertAlmostEqual(b - a, sweep.FIXED_RELATIVE_DELAY_M, places=9)
        finally:
            for name, value in original.items():
                setattr(lab, name, value)

    def test_wilson_interval_contains_observed_rate(self):
        rate, low, high = sweep.wilson_interval(21, 30)
        self.assertAlmostEqual(rate, 0.7)
        self.assertLessEqual(low, rate)
        self.assertGreaterEqual(high, rate)


if __name__ == "__main__":
    unittest.main()

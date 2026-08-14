#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_ula_hardware_boundary_campaign as campaign
import ula_gnss_waveform_fbss_lab as lab


class UlaHardwareBoundaryCampaignTest(unittest.TestCase):
    def test_five_degree_local_peaks_are_not_rejected_by_configuration(self):
        grid = np.arange(240.0, 300.0 + 0.25, 0.25)
        spectrum = np.exp(-0.5 * ((grid - 267.5) / 0.35) ** 2)
        spectrum += 0.8 * np.exp(-0.5 * ((grid - 272.5) / 0.35) ** 2)
        peaks = lab.strongest_peaks(grid, spectrum)
        np.testing.assert_allclose(peaks, [267.5, 272.5], atol=0.25)

    def test_controlled_scene_keeps_both_sources_at_twenty_metres(self):
        saved = (
            lab.TX_A_X_M,
            lab.TX_A_Y_M,
            lab.TX_B_X_M,
            lab.TX_B_Y_M,
            lab.CABLE_A_LENGTH_M,
            lab.CABLE_B_LENGTH_M,
            lab.SPATIAL_WAVE_MODEL,
            lab.KNOWN_HALF_PLANE,
            lab.CHANNEL_PHASE_ERROR_DEG_RMS,
            lab.CHANNEL_GAIN_ERROR_DB_RMS,
        )
        try:
            receiver, bearings = campaign.configure_scene(20.0, 3.0, 0.5)
            tx_a = np.array([lab.TX_A_X_M, lab.TX_A_Y_M])
            tx_b = np.array([lab.TX_B_X_M, lab.TX_B_Y_M])
            self.assertAlmostEqual(np.linalg.norm(tx_a - receiver), 20.0)
            self.assertAlmostEqual(np.linalg.norm(tx_b - receiver), 20.0)
            self.assertAlmostEqual(bearings[1] - bearings[0], 20.0)
            self.assertEqual(lab.SPATIAL_WAVE_MODEL, "spherical")
            self.assertEqual(lab.KNOWN_HALF_PLANE, "negative_y")
        finally:
            (
                lab.TX_A_X_M,
                lab.TX_A_Y_M,
                lab.TX_B_X_M,
                lab.TX_B_Y_M,
                lab.CABLE_A_LENGTH_M,
                lab.CABLE_B_LENGTH_M,
                lab.SPATIAL_WAVE_MODEL,
                lab.KNOWN_HALF_PLANE,
                lab.CHANNEL_PHASE_ERROR_DEG_RMS,
                lab.CHANNEL_GAIN_ERROR_DB_RMS,
            ) = saved

    def test_controlled_scene_keeps_effective_delay_fixed(self):
        saved = (
            lab.TX_A_X_M,
            lab.TX_A_Y_M,
            lab.TX_B_X_M,
            lab.TX_B_Y_M,
            lab.CABLE_A_LENGTH_M,
            lab.CABLE_B_LENGTH_M,
        )
        try:
            receiver, _ = campaign.configure_scene(60.0, 0.0, 0.0)
            path_a = lab.effective_path_length_m(
                receiver, [lab.TX_A_X_M, lab.TX_A_Y_M], lab.CABLE_A_LENGTH_M)
            path_b = lab.effective_path_length_m(
                receiver, [lab.TX_B_X_M, lab.TX_B_Y_M], lab.CABLE_B_LENGTH_M)
            self.assertAlmostEqual(
                path_b - path_a, campaign.FIXED_RELATIVE_DELAY_M, places=9)
        finally:
            (
                lab.TX_A_X_M,
                lab.TX_A_Y_M,
                lab.TX_B_X_M,
                lab.TX_B_Y_M,
                lab.CABLE_A_LENGTH_M,
                lab.CABLE_B_LENGTH_M,
            ) = saved

    def test_each_scan_changes_only_its_named_axis(self):
        self.assertEqual(campaign.task_condition("angle", 10.0), (10.0, 0.0, 0.0, 0.0))
        self.assertEqual(campaign.task_condition("power", -6.0), (60.0, -6.0, 0.0, 0.0))
        self.assertEqual(campaign.task_condition("phase", 5.0), (60.0, 0.0, 5.0, 0.0))
        self.assertEqual(campaign.task_condition("gain", 0.5), (60.0, 0.0, 0.0, 0.5))

    def test_single_peak_is_padded_for_csv_instead_of_crashing(self):
        first, second = campaign.padded_pair([271.5])
        self.assertEqual(first, 271.5)
        self.assertTrue(np.isnan(second))

    def test_summary_reports_unresolved_separately_from_finite_rmse(self):
        old_groups = campaign.ENABLED_GROUPS
        old_angles = campaign.ANGLE_DIFFERENCE_DEG
        try:
            campaign.ENABLED_GROUPS = ("angle",)
            campaign.ANGLE_DIFFERENCE_DEG = (5.0,)
            rows = [
                {"group": "angle", "level": 5.0, "doa_success": 1,
                 "estimator_state": "RESOLVED", "angle_rmse_deg": 1.0,
                 "delay_error_m": 2.0},
                {"group": "angle", "level": 5.0, "doa_success": 0,
                 "estimator_state": "UNRESOLVED_ONE_PEAK", "angle_rmse_deg": float("inf"),
                 "delay_error_m": float("nan")},
            ]
            summary = campaign.summarize(rows)[0]
            self.assertEqual(summary["unresolved_one_peak_count"], 1)
            self.assertEqual(summary["finite_angle_estimate_count"], 1)
            self.assertEqual(summary["p95_angle_rmse_deg"], 1.0)
            self.assertEqual(summary["full_success_count"], 1)
        finally:
            campaign.ENABLED_GROUPS = old_groups
            campaign.ANGLE_DIFFERENCE_DEG = old_angles


if __name__ == "__main__":
    unittest.main()

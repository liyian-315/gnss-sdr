/*!
 * \file second_peak_gate.h
 * \brief Quality gate for a candidate second acquisition peak.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef GNSS_SDR_SECOND_PEAK_GATE_H
#define GNSS_SDR_SECOND_PEAK_GATE_H

struct SecondPeakGateConfig
{
    float threshold_fraction;
    float min_peak_to_noise_db;
    float max_power_ratio_db;
    unsigned int reject_boundary_bins;
};

struct SecondPeakMetrics
{
    float test_statistic;
    float main_to_second_db;
    float peak_to_noise_db;
    unsigned int boundary_distance_bins;
};

inline bool second_peak_passes_gate(const SecondPeakGateConfig& config,
    const SecondPeakMetrics& metrics,
    float main_threshold)
{
    return metrics.test_statistic > config.threshold_fraction * main_threshold &&
           metrics.peak_to_noise_db >= config.min_peak_to_noise_db &&
           metrics.main_to_second_db <= config.max_power_ratio_db &&
           metrics.boundary_distance_bins >= config.reject_boundary_bins;
}

#endif  // GNSS_SDR_SECOND_PEAK_GATE_H

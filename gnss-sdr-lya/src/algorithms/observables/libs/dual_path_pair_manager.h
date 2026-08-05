/*!
 * \file dual_path_pair_manager.h
 * \brief Stateful quality manager for primary/second GNSS observables.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef GNSS_SDR_DUAL_PATH_PAIR_MANAGER_H
#define GNSS_SDR_DUAL_PATH_PAIR_MANAGER_H

#include <cstddef>
#include <cstdint>
#include <deque>
#include <map>
#include <string>
#include <vector>

enum class DualPathState
{
    SEARCHING,
    CANDIDATE,
    RELIABLE,
    DEGRADED,
    NO_SECOND_SOURCE,
    LOST
};

const char* dual_path_state_name(DualPathState state);

struct DualPathKey
{
    char system{'?'};
    std::string signal;
    uint32_t prn{0U};

    bool operator<(const DualPathKey& other) const;
};

struct DualPathObservation
{
    DualPathKey key;
    uint32_t channel{0U};
    uint32_t path{0U};
    double rx_time_s{0.0};
    double pseudorange_m{0.0};
    double cn0_db_hz{0.0};
    double doppler_hz{0.0};
    bool valid{false};
};

struct DualPathPairConfig
{
    size_t window_size{15U};
    uint32_t reliable_confirmations{5U};
    uint32_t no_second_confirmations{3U};
    uint32_t lost_confirmations{5U};
    double max_time_difference_s{0.050};
    double min_primary_cn0_db_hz{0.0};
    double min_second_cn0_db_hz{0.0};
    double max_doppler_difference_hz{1000000.0};
    double min_abs_delta_m{1.0};
    double max_delta_jump_m{1000000.0};
    double max_delta_mad_m{1000000.0};
};

struct DualPathPairStatus
{
    DualPathKey key;
    DualPathState state{DualPathState::SEARCHING};
    uint32_t primary_channel{0U};
    uint32_t second_channel{0U};
    uint32_t reacquisition_count{0U};
    uint32_t consecutive_good{0U};
    uint32_t consecutive_bad{0U};
    size_t window_samples{0U};
    double primary_pseudorange_m{0.0};
    double second_pseudorange_m{0.0};
    double primary_cn0_db_hz{0.0};
    double second_cn0_db_hz{0.0};
    double primary_doppler_hz{0.0};
    double second_doppler_hz{0.0};
    double doppler_delta_hz{0.0};
    double track_age_s{0.0};
    double delta_m{0.0};
    double delta_median_m{0.0};
    double delta_mad_m{0.0};
    double primary_cn0_median_db_hz{0.0};
    double second_cn0_median_db_hz{0.0};
    double primary_doppler_median_hz{0.0};
    double second_doppler_median_hz{0.0};
    bool primary_valid{false};
    bool second_valid{false};
    bool pair_time_aligned{false};
};

class DualPathPairManager
{
public:
    explicit DualPathPairManager(DualPathPairConfig config = {});

    std::vector<DualPathPairStatus> update(const std::vector<DualPathObservation>& observations);
    void reset();

private:
    struct PairRecord
    {
        DualPathState state{DualPathState::SEARCHING};
        uint32_t consecutive_good{0U};
        uint32_t consecutive_bad{0U};
        uint32_t primary_only_count{0U};
        uint32_t reacquisition_count{0U};
        bool has_seen_second{false};
        double pair_start_time_s{0.0};
        std::deque<double> deltas_m;
        std::deque<double> primary_cn0_db_hz;
        std::deque<double> second_cn0_db_hz;
        std::deque<double> primary_doppler_hz;
        std::deque<double> second_doppler_hz;
    };

    DualPathPairConfig d_config;
    std::map<DualPathKey, PairRecord> d_records;
};

#endif  // GNSS_SDR_DUAL_PATH_PAIR_MANAGER_H

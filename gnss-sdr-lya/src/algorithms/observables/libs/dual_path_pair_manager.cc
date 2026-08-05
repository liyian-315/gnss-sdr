/*!
 * \file dual_path_pair_manager.cc
 * \brief Stateful quality manager for primary/second GNSS observables.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "dual_path_pair_manager.h"
#include <algorithm>
#include <cmath>
#include <utility>

namespace
{
double median(const std::deque<double>& values)
{
    if (values.empty())
        {
            return 0.0;
        }
    std::vector<double> sorted(values.begin(), values.end());
    std::sort(sorted.begin(), sorted.end());
    const size_t middle = sorted.size() / 2U;
    if ((sorted.size() % 2U) == 0U)
        {
            return (sorted[middle - 1U] + sorted[middle]) / 2.0;
        }
    return sorted[middle];
}

double median_absolute_deviation(const std::deque<double>& values)
{
    if (values.empty())
        {
            return 0.0;
        }
    const double center = median(values);
    std::deque<double> deviations;
    for (const double value : values)
        {
            deviations.push_back(std::abs(value - center));
        }
    return median(deviations);
}

void append_bounded(std::deque<double>& values, double value, size_t capacity)
{
    values.push_back(value);
    while (values.size() > capacity)
        {
            values.pop_front();
        }
}

struct CurrentPair
{
    DualPathObservation primary;
    DualPathObservation second;
    bool has_primary{false};
    bool has_second{false};
};
}  // namespace

const char* dual_path_state_name(DualPathState state)
{
    switch (state)
        {
        case DualPathState::SEARCHING:
            return "SEARCHING";
        case DualPathState::CANDIDATE:
            return "CANDIDATE";
        case DualPathState::RELIABLE:
            return "RELIABLE";
        case DualPathState::DEGRADED:
            return "DEGRADED";
        case DualPathState::NO_SECOND_SOURCE:
            return "NO_SECOND_SOURCE";
        case DualPathState::LOST:
            return "LOST";
        }
    return "SEARCHING";
}

bool DualPathKey::operator<(const DualPathKey& other) const
{
    if (system != other.system)
        {
            return system < other.system;
        }
    if (signal != other.signal)
        {
            return signal < other.signal;
        }
    return prn < other.prn;
}

DualPathPairManager::DualPathPairManager(DualPathPairConfig config) : d_config(std::move(config))
{
    d_config.window_size = std::max<size_t>(1U, d_config.window_size);
    d_config.reliable_confirmations = std::max(1U, d_config.reliable_confirmations);
    d_config.no_second_confirmations = std::max(1U, d_config.no_second_confirmations);
    d_config.lost_confirmations = std::max(1U, d_config.lost_confirmations);
}

void DualPathPairManager::reset()
{
    d_records.clear();
}

std::vector<DualPathPairStatus> DualPathPairManager::update(const std::vector<DualPathObservation>& observations)
{
    std::map<DualPathKey, CurrentPair> current;
    for (const auto& observation : observations)
        {
            if (observation.path > 1U || observation.key.prn == 0U)
                {
                    continue;
                }
            auto& pair = current[observation.key];
            if (observation.path == 0U)
                {
                    if (!pair.has_primary || observation.valid)
                        {
                            pair.primary = observation;
                        }
                    pair.has_primary = true;
                }
            else
                {
                    if (!pair.has_second || observation.valid)
                        {
                            pair.second = observation;
                        }
                    pair.has_second = true;
                }
        }

    std::vector<DualPathPairStatus> statuses;
    statuses.reserve(current.size());
    for (auto& item : current)
        {
            const DualPathKey& key = item.first;
            const CurrentPair& pair = item.second;
            PairRecord& record = d_records[key];

            const bool primary_valid = pair.has_primary && pair.primary.valid;
            const bool second_valid = pair.has_second && pair.second.valid;
            const bool time_aligned = primary_valid && second_valid &&
                                      std::abs(pair.primary.rx_time_s - pair.second.rx_time_s) <= d_config.max_time_difference_s;
            const bool cn0_valid = primary_valid && second_valid &&
                                   pair.primary.cn0_db_hz >= d_config.min_primary_cn0_db_hz &&
                                   pair.second.cn0_db_hz >= d_config.min_second_cn0_db_hz;
            const bool doppler_valid = primary_valid && second_valid &&
                                       std::abs(pair.primary.doppler_hz - pair.second.doppler_hz) <= d_config.max_doppler_difference_hz;
            const bool pair_valid = time_aligned && cn0_valid && doppler_valid;

            if (pair_valid)
                {
                    if (record.state == DualPathState::LOST)
                        {
                            record.reacquisition_count++;
                            record.deltas_m.clear();
                            record.primary_cn0_db_hz.clear();
                            record.second_cn0_db_hz.clear();
                            record.primary_doppler_hz.clear();
                            record.second_doppler_hz.clear();
                        }
                    record.has_seen_second = true;
                    record.primary_only_count = 0U;
                    record.consecutive_bad = 0U;
                    record.consecutive_good++;
                    append_bounded(record.deltas_m, pair.second.pseudorange_m - pair.primary.pseudorange_m, d_config.window_size);
                    append_bounded(record.primary_cn0_db_hz, pair.primary.cn0_db_hz, d_config.window_size);
                    append_bounded(record.second_cn0_db_hz, pair.second.cn0_db_hz, d_config.window_size);
                    append_bounded(record.primary_doppler_hz, pair.primary.doppler_hz, d_config.window_size);
                    append_bounded(record.second_doppler_hz, pair.second.doppler_hz, d_config.window_size);

                    if (record.consecutive_good >= d_config.reliable_confirmations &&
                        median_absolute_deviation(record.deltas_m) <= d_config.max_delta_mad_m)
                        {
                            record.state = DualPathState::RELIABLE;
                        }
                    else
                        {
                            record.state = DualPathState::CANDIDATE;
                        }
                }
            else
                {
                    record.consecutive_good = 0U;
                    record.consecutive_bad++;
                    if (primary_valid && !second_valid)
                        {
                            record.primary_only_count++;
                            if (record.has_seen_second)
                                {
                                    record.state = record.consecutive_bad >= d_config.lost_confirmations ? DualPathState::LOST : DualPathState::DEGRADED;
                                }
                            else
                                {
                                    record.state = record.primary_only_count >= d_config.no_second_confirmations ? DualPathState::NO_SECOND_SOURCE : DualPathState::SEARCHING;
                                }
                        }
                    else if (record.has_seen_second)
                        {
                            record.state = record.consecutive_bad >= d_config.lost_confirmations ? DualPathState::LOST : DualPathState::DEGRADED;
                        }
                    else
                        {
                            record.state = DualPathState::SEARCHING;
                        }
                }

            DualPathPairStatus status;
            status.key = key;
            status.state = record.state;
            status.primary_valid = primary_valid;
            status.second_valid = second_valid;
            status.pair_time_aligned = time_aligned;
            status.primary_channel = pair.has_primary ? pair.primary.channel : 0U;
            status.second_channel = pair.has_second ? pair.second.channel : 0U;
            status.reacquisition_count = record.reacquisition_count;
            status.consecutive_good = record.consecutive_good;
            status.consecutive_bad = record.consecutive_bad;
            status.window_samples = record.deltas_m.size();
            status.primary_pseudorange_m = primary_valid ? pair.primary.pseudorange_m : 0.0;
            status.second_pseudorange_m = second_valid ? pair.second.pseudorange_m : 0.0;
            status.delta_m = pair_valid ? pair.second.pseudorange_m - pair.primary.pseudorange_m : 0.0;
            status.delta_median_m = median(record.deltas_m);
            status.delta_mad_m = median_absolute_deviation(record.deltas_m);
            status.primary_cn0_median_db_hz = median(record.primary_cn0_db_hz);
            status.second_cn0_median_db_hz = median(record.second_cn0_db_hz);
            status.primary_doppler_median_hz = median(record.primary_doppler_hz);
            status.second_doppler_median_hz = median(record.second_doppler_hz);
            statuses.push_back(std::move(status));
        }
    return statuses;
}

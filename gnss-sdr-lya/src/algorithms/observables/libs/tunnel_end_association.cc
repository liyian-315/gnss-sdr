/*!
 * \file tunnel_end_association.cc
 * \brief Associates already-separated dual-path observables with the two physical
 *        ends of a tunnel DAS installation.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "tunnel_end_association.h"
#include <algorithm>
#include <cmath>
#include <cmath>
#include <iomanip>
#include <locale>
#include <sstream>
#include <utility>

namespace
{
void append_value_or_na(std::ostream& stream, bool valid, double value, int precision)
{
    if (valid)
        {
            stream << std::fixed << std::setprecision(precision) << value;
        }
    else
        {
            stream << "N/A";
        }
}

const char* tunnel_field_state_name(const TunnelEndStatus& status)
{
    switch (status.pair_state)
        {
        case DualPathState::LOST:
            return "LOST";
        case DualPathState::NO_SECOND_SOURCE:
            return "NO_SECOND_SOURCE";
        case DualPathState::SEARCHING:
            return "SEARCHING";
        case DualPathState::CANDIDATE:
            return "CANDIDATE";
        case DualPathState::DEGRADED:
            return "DEGRADED";
        case DualPathState::RELIABLE:
            return status.identity == TunnelIdentityState::RELIABLE ? "RELIABLE" : "UNRESOLVED";
        default:
            break;
        }
    return "UNRESOLVED";
}
}  // namespace

const char* tunnel_identity_state_name(TunnelIdentityState state)
{
    switch (state)
        {
        case TunnelIdentityState::UNKNOWN:
            return "UNKNOWN";
        case TunnelIdentityState::CANDIDATE:
            return "CANDIDATE";
        case TunnelIdentityState::RELIABLE:
            return "RELIABLE";
        }
    return "UNKNOWN";
}

double tunnel_expected_delta_b_minus_a_m(const TunnelSiteConfig& config)
{
    const double distance_to_a_m = config.measurement_position_m;
    const double distance_to_b_m = config.length_m - config.measurement_position_m;
    return (distance_to_b_m + config.end_b_fixed_delay_m) - (distance_to_a_m + config.end_a_fixed_delay_m);
}

std::string validate_tunnel_site_config(const TunnelSiteConfig& config)
{
    if (!config.enable)
        {
            return {};
        }
    if (!std::isfinite(config.length_m) || config.length_m <= 0.0)
        {
            return "Tunnel.length_m must be finite and > 0";
        }
    if (!std::isfinite(config.measurement_position_m) ||
        config.measurement_position_m < 0.0 || config.measurement_position_m > config.length_m)
        {
            return "Tunnel.measurement_position_m must be within [0, Tunnel.length_m]";
        }
    if (!std::isfinite(config.end_a_fixed_delay_m))
        {
            return "Tunnel.end_a_fixed_delay_m must be finite";
        }
    if (!std::isfinite(config.end_b_fixed_delay_m))
        {
            return "Tunnel.end_b_fixed_delay_m must be finite";
        }
    if (!std::isfinite(config.identity_max_error_m) || config.identity_max_error_m <= 0.0)
        {
            return "Tunnel.identity_max_error_m must be finite and > 0";
        }
    if (!std::isfinite(config.identity_margin_m) || config.identity_margin_m < 0.0)
        {
            return "Tunnel.identity_margin_m must be finite and >= 0";
        }
    if (config.identity_confirm_epochs < 1)
        {
            return "Tunnel.identity_confirm_epochs must be >= 1";
        }
    return {};
}

TunnelEndAssociation::TunnelEndAssociation(TunnelSiteConfig config) : d_config(std::move(config))
{
    if (d_config.end_a_name.empty())
        {
            d_config.end_a_name = "END_A";
        }
    if (d_config.end_b_name.empty())
        {
            d_config.end_b_name = "END_B";
        }
}

void TunnelEndAssociation::reset()
{
    d_records.clear();
}

std::vector<TunnelEndStatus> TunnelEndAssociation::update(const std::vector<DualPathPairStatus>& pairs)
{
    const double expected_delta_m = tunnel_expected_delta_b_minus_a_m(d_config);

    std::vector<TunnelEndStatus> statuses;
    statuses.reserve(pairs.size());
    for (const auto& pair : pairs)
        {
            Record& record = d_records[pair.key];

            TunnelEndStatus status;
            status.key = pair.key;
            status.pair_state = pair.state;
            status.position_m = d_config.measurement_position_m;
            status.tunnel_length_m = d_config.length_m;
            status.expected_delta_b_minus_a_m = expected_delta_m;
            status.reacquisition_count = pair.reacquisition_count;
            status.path0_valid = pair.primary_valid;
            status.path1_valid = pair.second_valid;
            status.path0_cn0_db_hz = pair.primary_cn0_db_hz;
            status.path1_cn0_db_hz = pair.second_cn0_db_hz;

            // A reacquisition means the receiver may have re-ordered the peaks. Keep the
            // held physical assignment but force it to be re-confirmed before the formal
            // END_A / END_B fields are published again.
            if (!record.has_reacquisition_baseline)
                {
                    record.last_reacquisition_count = pair.reacquisition_count;
                    record.has_reacquisition_baseline = true;
                }
            else if (pair.reacquisition_count != record.last_reacquisition_count)
                {
                    record.last_reacquisition_count = pair.reacquisition_count;
                    record.confirm_count = 0U;
                    if (record.identity == TunnelIdentityState::RELIABLE)
                        {
                            record.identity = TunnelIdentityState::CANDIDATE;
                        }
                }

            // The tunnel layer never invents a pair the dual-path layer rejected.
            const bool pair_usable = pair.primary_valid && pair.second_valid &&
                                     pair.pair_time_aligned &&
                                     pair.state != DualPathState::LOST &&
                                     pair.state != DualPathState::NO_SECOND_SOURCE &&
                                     pair.state != DualPathState::SEARCHING;

            if (!pair_usable)
                {
                    record.confirm_count = 0U;
                    record.identity = TunnelIdentityState::UNKNOWN;
                    if (pair.state == DualPathState::LOST || pair.state == DualPathState::NO_SECOND_SOURCE)
                        {
                            // The second end is gone: drop the assignment entirely rather
                            // than keep showing a stale END_B.
                            record.has_assignment = false;
                        }
                    status.identity = record.identity;
                    status.ends_valid = false;
                    status.end_a_is_path0 = record.end_a_is_path0;
                    status.identity_confirm_count = record.confirm_count;
                    statuses.push_back(std::move(status));
                    continue;
                }

            // Hypothesis 1: path0 is END_A, so END_B - END_A = rho1 - rho0 = delta_m.
            // Hypothesis 2: path1 is END_A, so END_B - END_A = rho0 - rho1 = -delta_m.
            const double observed_if_path0_is_a_m = pair.delta_m;
            const double error_path0_is_a_m = std::abs(observed_if_path0_is_a_m - expected_delta_m);
            const double error_path1_is_a_m = std::abs(-observed_if_path0_is_a_m - expected_delta_m);
            const bool path0_is_a = error_path0_is_a_m <= error_path1_is_a_m;
            const double best_error_m = std::min(error_path0_is_a_m, error_path1_is_a_m);
            const double margin_m = std::abs(error_path1_is_a_m - error_path0_is_a_m);

            status.identity_best_error_m = best_error_m;
            status.identity_margin_m = margin_m;

            // Near the tunnel midpoint the two hypotheses explain the geometry equally
            // well, so margin_m collapses to zero and the ends stay UNKNOWN by design.
            const bool geometry_decisive = best_error_m <= d_config.identity_max_error_m &&
                                           margin_m >= d_config.identity_margin_m;

            if (!geometry_decisive)
                {
                    record.confirm_count = 0U;
                    record.identity = TunnelIdentityState::UNKNOWN;
                }
            else
                {
                    if (record.has_assignment && record.end_a_is_path0 != path0_is_a)
                        {
                            // The receiver swapped path0/path1. Adopt the new mapping, which
                            // is what keeps END_A pointing at the same physical end, but
                            // require a fresh confirmation run before publishing again.
                            record.end_a_is_path0 = path0_is_a;
                            record.confirm_count = 1U;
                            record.identity = TunnelIdentityState::CANDIDATE;
                        }
                    else
                        {
                            record.end_a_is_path0 = path0_is_a;
                            record.has_assignment = true;
                            record.confirm_count++;
                            const bool pair_reliable = pair.state == DualPathState::RELIABLE;
                            record.identity = (pair_reliable && d_config.identity_confirm_epochs > 0 &&
                                                  record.confirm_count >= static_cast<uint32_t>(d_config.identity_confirm_epochs)) ?
                                                  TunnelIdentityState::RELIABLE :
                                                  TunnelIdentityState::CANDIDATE;
                        }
                }

            status.identity = record.identity;
            status.end_a_is_path0 = record.end_a_is_path0;
            status.identity_confirm_count = record.confirm_count;
            status.ends_valid = record.identity == TunnelIdentityState::RELIABLE;

            if (status.ends_valid)
                {
                    const bool a_is_path0 = record.end_a_is_path0;
                    status.end_a_cn0_db_hz = a_is_path0 ? pair.primary_cn0_db_hz : pair.second_cn0_db_hz;
                    status.end_b_cn0_db_hz = a_is_path0 ? pair.second_cn0_db_hz : pair.primary_cn0_db_hz;
                    status.end_a_pseudorange_m = a_is_path0 ? pair.primary_pseudorange_m : pair.second_pseudorange_m;
                    status.end_b_pseudorange_m = a_is_path0 ? pair.second_pseudorange_m : pair.primary_pseudorange_m;
                    status.end_a_doppler_hz = a_is_path0 ? pair.primary_doppler_hz : pair.second_doppler_hz;
                    status.end_b_doppler_hz = a_is_path0 ? pair.second_doppler_hz : pair.primary_doppler_hz;
                    status.cn0_delta_a_minus_b_db = status.end_a_cn0_db_hz - status.end_b_cn0_db_hz;
                    status.pseudorange_delta_b_minus_a_m = status.end_b_pseudorange_m - status.end_a_pseudorange_m;
                    status.delta_residual_m = status.pseudorange_delta_b_minus_a_m - expected_delta_m;
                }

            statuses.push_back(std::move(status));
        }
    return statuses;
}

std::string format_tunnel_das_banner(const TunnelSiteConfig& config)
{
    std::ostringstream stream;
    stream.imbue(std::locale::classic());
    stream << "TUNNEL_DAS_CONFIG"
           << " length_m=" << std::fixed << std::setprecision(1) << config.length_m
           << " position_m=" << config.measurement_position_m
           << " distance_to_a_m=" << config.measurement_position_m
           << " distance_to_b_m=" << config.length_m - config.measurement_position_m
           << " end_a_name=" << config.end_a_name
           << " end_b_name=" << config.end_b_name
           << " end_a_fixed_delay_m=" << config.end_a_fixed_delay_m
           << " end_b_fixed_delay_m=" << config.end_b_fixed_delay_m
           << " expected_delta_b_minus_a_m=" << tunnel_expected_delta_b_minus_a_m(config)
           << " prn=" << config.prn;
    return stream.str();
}

std::string format_tunnel_das_status_v1(const TunnelEndStatus& status)
{
    const bool ends = status.ends_valid;
    std::ostringstream stream;
    stream.imbue(std::locale::classic());
    stream << "TUNNEL_DAS_STATUS version=1"
           << " position_m=" << std::fixed << std::setprecision(1) << status.position_m
           << " prn=" << status.key.prn
           << " state=" << tunnel_field_state_name(status)
           << " identity=" << tunnel_identity_state_name(status.identity)
           << " end_a_path=";
    if (ends) stream << (status.end_a_is_path0 ? 0 : 1); else stream << "N/A";
    stream << " end_b_path=";
    if (ends) stream << (status.end_a_is_path0 ? 1 : 0); else stream << "N/A";
    stream << " end_a_cn0_db_hz=";
    append_value_or_na(stream, ends, status.end_a_cn0_db_hz, 2);
    stream << " end_b_cn0_db_hz=";
    append_value_or_na(stream, ends, status.end_b_cn0_db_hz, 2);
    stream << " cn0_delta_a_minus_b_db=";
    append_value_or_na(stream, ends, status.cn0_delta_a_minus_b_db, 2);
    stream << " end_a_pseudorange_m=";
    append_value_or_na(stream, ends, status.end_a_pseudorange_m, 3);
    stream << " end_b_pseudorange_m=";
    append_value_or_na(stream, ends, status.end_b_pseudorange_m, 3);
    stream << " pseudorange_delta_b_minus_a_m=";
    append_value_or_na(stream, ends, status.pseudorange_delta_b_minus_a_m, 3);
    stream << " expected_delta_b_minus_a_m=" << std::fixed << std::setprecision(1) << status.expected_delta_b_minus_a_m;
    stream << " delta_residual_m=";
    append_value_or_na(stream, ends, status.delta_residual_m, 3);
    stream << " end_a_doppler_hz=";
    append_value_or_na(stream, ends, status.end_a_doppler_hz, 3);
    stream << " end_b_doppler_hz=";
    append_value_or_na(stream, ends, status.end_b_doppler_hz, 3);
    // Raw path diagnostics: never labelled A/B, always available for triage.
    stream << " path0_cn0_db_hz=";
    append_value_or_na(stream, status.path0_valid, status.path0_cn0_db_hz, 2);
    stream << " path1_cn0_db_hz=";
    append_value_or_na(stream, status.path1_valid, status.path1_cn0_db_hz, 2);
    stream << " identity_error_m=";
    append_value_or_na(stream, status.path0_valid && status.path1_valid, status.identity_best_error_m, 1);
    stream << " identity_margin_m=";
    append_value_or_na(stream, status.path0_valid && status.path1_valid, status.identity_margin_m, 1);
    stream << " identity_confirm=" << status.identity_confirm_count
           << " reacquisition_count=" << status.reacquisition_count;
    return stream.str();
}

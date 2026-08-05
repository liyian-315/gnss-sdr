/*!
 * \file dual_path_status_formatter.cc
 * \brief Stable versioned text and CSV output for dual-path status.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "dual_path_status_formatter.h"
#include <iomanip>
#include <locale>
#include <sstream>

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
}  // namespace

std::string format_dual_path_status_v1(const DualPathPairStatus& status)
{
    const bool pair_valid = status.primary_valid && status.second_valid && status.pair_time_aligned;
    const bool history_valid = status.window_samples > 0U;
    std::ostringstream stream;
    stream.imbue(std::locale::classic());
    stream << "DUALPATH_STATUS version=1"
           << " system=" << status.key.system
           << " signal=" << status.key.signal
           << " prn=" << status.key.prn
           << " state=" << dual_path_state_name(status.state)
           << " primary_ch=";
    if (status.primary_valid) stream << status.primary_channel; else stream << "N/A";
    stream << " second_ch=";
    if (status.second_valid) stream << status.second_channel; else stream << "N/A";
    stream << " primary_pseudorange_m=";
    append_value_or_na(stream, status.primary_valid, status.primary_pseudorange_m, 3);
    stream << " second_pseudorange_m=";
    append_value_or_na(stream, status.second_valid, status.second_pseudorange_m, 3);
    stream << " delta_m=";
    append_value_or_na(stream, pair_valid, status.delta_m, 3);
    stream << " delta_median_m=";
    append_value_or_na(stream, history_valid, status.delta_median_m, 3);
    stream << " delta_mad_m=";
    append_value_or_na(stream, history_valid, status.delta_mad_m, 3);
    stream << " primary_cn0_db_hz=";
    append_value_or_na(stream, history_valid, status.primary_cn0_median_db_hz, 2);
    stream << " second_cn0_db_hz=";
    append_value_or_na(stream, history_valid, status.second_cn0_median_db_hz, 2);
    stream << " primary_doppler_hz=";
    append_value_or_na(stream, history_valid, status.primary_doppler_median_hz, 3);
    stream << " second_doppler_hz=";
    append_value_or_na(stream, history_valid, status.second_doppler_median_hz, 3);
    stream << " doppler_delta_hz=";
    append_value_or_na(stream, pair_valid, status.doppler_delta_hz, 3);
    stream << " valid_count=" << status.window_samples
           << " track_age_s=" << std::fixed << std::setprecision(1) << status.track_age_s
           << " reacquisition_count=" << status.reacquisition_count;
    return stream.str();
}

std::string dual_path_csv_header_v1()
{
    return "version,system,signal,prn,state,primary_channel,second_channel,primary_pseudorange_m,second_pseudorange_m,delta_m,delta_median_m,delta_mad_m,primary_cn0_median_db_hz,second_cn0_median_db_hz,primary_doppler_median_hz,second_doppler_median_hz,doppler_delta_hz,valid_count,track_age_s,reacquisition_count";
}

std::string format_dual_path_csv_v1(const DualPathPairStatus& status)
{
    const bool pair_valid = status.primary_valid && status.second_valid && status.pair_time_aligned;
    const bool history_valid = status.window_samples > 0U;
    std::ostringstream stream;
    stream.imbue(std::locale::classic());
    stream << "1," << status.key.system << ',' << status.key.signal << ',' << status.key.prn << ','
           << dual_path_state_name(status.state) << ',';
    if (status.primary_valid) stream << status.primary_channel; else stream << "N/A";
    stream << ',';
    if (status.second_valid) stream << status.second_channel; else stream << "N/A";
    stream << ',';
    append_value_or_na(stream, status.primary_valid, status.primary_pseudorange_m, 3);
    stream << ',';
    append_value_or_na(stream, status.second_valid, status.second_pseudorange_m, 3);
    stream << ',';
    append_value_or_na(stream, pair_valid, status.delta_m, 3);
    stream << ',';
    append_value_or_na(stream, history_valid, status.delta_median_m, 3);
    stream << ',';
    append_value_or_na(stream, history_valid, status.delta_mad_m, 3);
    stream << ',';
    append_value_or_na(stream, history_valid, status.primary_cn0_median_db_hz, 2);
    stream << ',';
    append_value_or_na(stream, history_valid, status.second_cn0_median_db_hz, 2);
    stream << ',';
    append_value_or_na(stream, history_valid, status.primary_doppler_median_hz, 3);
    stream << ',';
    append_value_or_na(stream, history_valid, status.second_doppler_median_hz, 3);
    stream << ',';
    append_value_or_na(stream, pair_valid, status.doppler_delta_hz, 3);
    stream << ',' << status.window_samples
           << ',' << std::fixed << std::setprecision(1) << status.track_age_s
           << ',' << status.reacquisition_count;
    return stream.str();
}

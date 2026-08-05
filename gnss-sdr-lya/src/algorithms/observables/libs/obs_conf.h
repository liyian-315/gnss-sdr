/*!
 * \file obs_conf.h
 * \brief Class that contains all the configuration parameters for generic
 * observables block
 * \author Javier Arribas, 2020. jarribas(at)cttc.es
 *
 * -----------------------------------------------------------------------------
 *
 * GNSS-SDR is a Global Navigation Satellite System software-defined receiver.
 * This file is part of GNSS-SDR.
 *
 * Copyright (C) 2010-2020  (see AUTHORS file for a list of contributors)
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * -----------------------------------------------------------------------------
 */

#ifndef GNSS_SDR_OBS_CONF_H
#define GNSS_SDR_OBS_CONF_H

#include <cstdint>
#include <string>

/** \addtogroup Observables
 * \{ */
/** \addtogroup Observables_libs observables_libs
 * Utilities for GNSS observables configuration.
 * \{ */

class Obs_Conf
{
public:
    Obs_Conf();

    std::string dump_filename{"obs_dump.dat"};
    std::string dual_path_csv_filename{"dual_path_status.csv"};
    int32_t smoothing_factor{0};
    uint32_t nchannels_in{0U};
    uint32_t nchannels_out{0U};
    uint32_t observable_interval_ms{20U};
    uint32_t stdout_interval_ms{1000U};
    uint32_t dual_path_interval_ms{1000U};
    uint32_t dual_path_window_size{15U};
    uint32_t dual_path_reliable_confirmations{5U};
    uint32_t dual_path_no_second_confirmations{3U};
    uint32_t dual_path_lost_confirmations{5U};
    double dual_path_max_time_difference_s{0.050};
    double dual_path_min_primary_cn0_db_hz{0.0};
    double dual_path_min_second_cn0_db_hz{0.0};
    double dual_path_max_doppler_difference_hz{1000000.0};
    double dual_path_max_delta_mad_m{1000000.0};
    bool enable_carrier_smoothing{false};
    bool always_output_gs{false};
    bool stdout{false};
    bool dual_path_csv{false};
    bool dump{false};
    bool dump_mat{false};
    bool dump_extended{false};
    bool enable_E6{false};
};

/** \} */
/** \} */
#endif  // GNSS_SDR_OBS_CONF_H

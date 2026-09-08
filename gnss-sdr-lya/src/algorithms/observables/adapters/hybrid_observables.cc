/*!
 * \file hybrid_observables.cc
 * \brief Implementation of an adapter of a Galileo E1 observables block
 * to a ObservablesInterface
 * \author Javier Arribas, 2011. jarribas(at)cttc.es
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

#include "hybrid_observables.h"
#include "configuration_interface.h"
#include "gnss_sdr_flags.h"
#include "obs_conf.h"
#include <ostream>  // for operator<<
#include <utility>

#if USE_GLOG_AND_GFLAGS
#include <glog/logging.h>
#else
#include <absl/log/log.h>
#endif

HybridObservables::HybridObservables(const ConfigurationInterface* configuration,
    const std::string& role,
    unsigned int in_streams,
    unsigned int out_streams) : role_(role),
                                in_streams_(in_streams),
                                out_streams_(out_streams),
                                dump_(configuration->property(role + ".dump", false)),
                                dump_mat_(configuration->property(role + ".dump_mat", true))
{
    const std::string default_dump_filename("./observables.dat");
    dump_filename_ = configuration->property(role + ".dump_filename", default_dump_filename);

    Obs_Conf conf{};
    conf.dump = dump_;
    conf.dump_mat = dump_mat_;
    conf.dump_extended = configuration->property(role + ".dump_extended", conf.dump_extended);
    conf.dump_filename = dump_filename_;
    conf.nchannels_in = in_streams_;
    conf.nchannels_out = out_streams_;
    conf.observable_interval_ms = configuration->property("GNSS-SDR.observable_interval_ms", conf.observable_interval_ms);
    conf.stdout = configuration->property(role + ".stdout", conf.stdout);
    conf.stdout_interval_ms = configuration->property(role + ".stdout_interval_ms", conf.stdout_interval_ms);
    conf.dual_path_interval_ms = configuration->property(role + ".dual_path_interval_ms", conf.stdout_interval_ms);
    conf.dual_path_csv = configuration->property(role + ".dual_path_csv", conf.dual_path_csv);
    conf.dual_path_csv_filename = configuration->property(role + ".dual_path_csv_filename", conf.dual_path_csv_filename);
    conf.dual_path_window_size = configuration->property(role + ".dual_path_window_size", conf.dual_path_window_size);
    conf.dual_path_reliable_confirmations = configuration->property(role + ".dual_path_reliable_confirmations", conf.dual_path_reliable_confirmations);
    conf.dual_path_no_second_confirmations = configuration->property(role + ".dual_path_no_second_confirmations", conf.dual_path_no_second_confirmations);
    conf.dual_path_lost_confirmations = configuration->property(role + ".dual_path_lost_confirmations", conf.dual_path_lost_confirmations);
    conf.dual_path_auto_reacquire = configuration->property(role + ".dual_path_auto_reacquire", conf.dual_path_auto_reacquire);
    conf.dual_path_auto_reacquire_confirmations = configuration->property(role + ".dual_path_auto_reacquire_confirmations", conf.dual_path_auto_reacquire_confirmations);
    conf.dual_path_auto_reacquire_cooldown_ms = configuration->property(role + ".dual_path_auto_reacquire_cooldown_ms", conf.dual_path_auto_reacquire_cooldown_ms);
    conf.dual_path_second_path_freshness_limit_s = configuration->property(role + ".dual_path_second_path_freshness_limit_s", conf.dual_path_second_path_freshness_limit_s);
    conf.dual_path_max_time_difference_s = configuration->property(role + ".dual_path_max_time_difference_s", conf.dual_path_max_time_difference_s);
    conf.dual_path_min_primary_cn0_db_hz = configuration->property(role + ".dual_path_min_primary_cn0_db_hz", conf.dual_path_min_primary_cn0_db_hz);
    conf.dual_path_min_second_cn0_db_hz = configuration->property(role + ".dual_path_min_second_cn0_db_hz", conf.dual_path_min_second_cn0_db_hz);
    conf.dual_path_max_doppler_difference_hz = configuration->property(role + ".dual_path_max_doppler_difference_hz", conf.dual_path_max_doppler_difference_hz);
    conf.dual_path_min_abs_delta_m = configuration->property(role + ".dual_path_min_abs_delta_m", conf.dual_path_min_abs_delta_m);
    conf.dual_path_max_delta_jump_m = configuration->property(role + ".dual_path_max_delta_jump_m", conf.dual_path_max_delta_jump_m);
    conf.dual_path_max_delta_mad_m = configuration->property(role + ".dual_path_max_delta_mad_m", conf.dual_path_max_delta_mad_m);
    conf.enable_carrier_smoothing = configuration->property(role + ".enable_carrier_smoothing", conf.enable_carrier_smoothing);
    conf.always_output_gs = configuration->property("PVT.an_output_enabled", conf.always_output_gs) || configuration->property(role + ".always_output_gs", conf.always_output_gs);
    conf.enable_E6 = configuration->property("PVT.use_e6_for_pvt", conf.enable_E6);

#if USE_GLOG_AND_GFLAGS
    if (FLAGS_carrier_smoothing_factor == DEFAULT_CARRIER_SMOOTHING_FACTOR)
#else
    if (absl::GetFlag(FLAGS_carrier_smoothing_factor) == DEFAULT_CARRIER_SMOOTHING_FACTOR)
#endif
        {
            conf.smoothing_factor = configuration->property(role + ".smoothing_factor", conf.smoothing_factor);
        }
    DLOG(INFO) << "role " << role;
    if (conf.enable_carrier_smoothing == true)
        {
            LOG(INFO) << "Observables carrier smoothing enabled with smoothing factor " << conf.smoothing_factor;
        }
    observables_ = hybrid_observables_gs_make(conf);
    DLOG(INFO) << "Observables block ID (" << observables_->unique_id() << ")";
}


void HybridObservables::connect(gr::top_block_sptr top_block)
{
    if (top_block)
        { /* top_block is not null */
        };
    // Nothing to connect internally
    DLOG(INFO) << "nothing to connect internally";
}


void HybridObservables::disconnect(gr::top_block_sptr top_block)
{
    if (top_block)
        { /* top_block is not null */
        };
    // Nothing to disconnect
}


gr::basic_block_sptr HybridObservables::get_left_block()
{
    return observables_;
}


gr::basic_block_sptr HybridObservables::get_right_block()
{
    return observables_;
}

/*!
 * \file beidou_b1c_dummy_telemetry_decoder_gs.cc
 * \brief Pass-through telemetry block for BeiDou B1C tracking experiments.
 */

#include "beidou_b1c_dummy_telemetry_decoder_gs.h"
#include <gnuradio/io_signature.h>
#include <algorithm>

#if USE_GLOG_AND_GFLAGS
#include <glog/logging.h>
#else
#include <absl/log/log.h>
#endif

beidou_b1c_dummy_telemetry_decoder_gs_sptr beidou_b1c_make_dummy_telemetry_decoder_gs(
    const Gnss_Satellite& satellite,
    const Tlm_Conf& conf)
{
    return beidou_b1c_dummy_telemetry_decoder_gs_sptr(new beidou_b1c_dummy_telemetry_decoder_gs(satellite, conf));
}


beidou_b1c_dummy_telemetry_decoder_gs::beidou_b1c_dummy_telemetry_decoder_gs(
    const Gnss_Satellite& satellite,
    const Tlm_Conf& conf) : telemetry_impl_interface("beidou_b1c_dummy_telemetry_decoder_gs",
                                 gr::io_signature::make(1, 1, sizeof(Gnss_Synchro)),
                                 gr::io_signature::make(1, 1, sizeof(Gnss_Synchro))),
                             d_satellite(satellite)
{
    if (conf.dump)
        {
            LOG(WARNING) << "BEIDOU B1C dummy telemetry decoder ignores telemetry dump settings.";
        }
    configure_basic_outputs();
}


void beidou_b1c_dummy_telemetry_decoder_gs::set_satellite(const Gnss_Satellite& satellite)
{
    d_satellite = Gnss_Satellite(satellite.get_system(), satellite.get_PRN());
}


void beidou_b1c_dummy_telemetry_decoder_gs::set_channel(int32_t channel)
{
    d_channel = channel;
    LOG(INFO) << "BeiDou B1C dummy telemetry channel set to " << d_channel;
}


void beidou_b1c_dummy_telemetry_decoder_gs::reset()
{
}


int beidou_b1c_dummy_telemetry_decoder_gs::general_work(int noutput_items,
    gr_vector_int& ninput_items,
    gr_vector_const_void_star& input_items,
    gr_vector_void_star& output_items)
{
    const auto available = std::min(noutput_items, ninput_items[0]);
    const auto* in = reinterpret_cast<const Gnss_Synchro*>(input_items[0]);
    auto* out = reinterpret_cast<Gnss_Synchro*>(output_items[0]);

    for (int i = 0; i < available; ++i)
        {
            out[i] = in[i];
            out[i].Flag_valid_word = false;
            out[i].Flag_valid_pseudorange = false;
        }

    consume_each(available);
    return available;
}

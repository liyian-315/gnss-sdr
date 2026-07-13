/*!
 * \file beidou_b1c_dummy_telemetry_decoder_gs.h
 * \brief Pass-through telemetry block for BeiDou B1C tracking experiments.
 */

#ifndef GNSS_SDR_BEIDOU_B1C_DUMMY_TELEMETRY_DECODER_GS_H
#define GNSS_SDR_BEIDOU_B1C_DUMMY_TELEMETRY_DECODER_GS_H

#include "gnss_synchro.h"
#include "telemetry_impl_interface.h"
#include "tlm_conf.h"
#include <gnuradio/types.h>

class beidou_b1c_dummy_telemetry_decoder_gs;

using beidou_b1c_dummy_telemetry_decoder_gs_sptr = gnss_shared_ptr<beidou_b1c_dummy_telemetry_decoder_gs>;

beidou_b1c_dummy_telemetry_decoder_gs_sptr beidou_b1c_make_dummy_telemetry_decoder_gs(
    const Gnss_Satellite& satellite,
    const Tlm_Conf& conf);

class beidou_b1c_dummy_telemetry_decoder_gs : public telemetry_impl_interface
{
public:
    ~beidou_b1c_dummy_telemetry_decoder_gs() override = default;
    void set_satellite(const Gnss_Satellite& satellite) override;
    void set_channel(int32_t channel) override;
    void reset() override;

    int general_work(int noutput_items,
        gr_vector_int& ninput_items,
        gr_vector_const_void_star& input_items,
        gr_vector_void_star& output_items) override;

private:
    friend beidou_b1c_dummy_telemetry_decoder_gs_sptr beidou_b1c_make_dummy_telemetry_decoder_gs(
        const Gnss_Satellite& satellite,
        const Tlm_Conf& conf);

    beidou_b1c_dummy_telemetry_decoder_gs(const Gnss_Satellite& satellite, const Tlm_Conf& conf);

    Gnss_Satellite d_satellite;
    int32_t d_channel = 0;
};

#endif  // GNSS_SDR_BEIDOU_B1C_DUMMY_TELEMETRY_DECODER_GS_H

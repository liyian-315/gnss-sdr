/*!
 * \file beidou_b1c_dummy_telemetry_decoder.cc
 * \brief Adapter of a pass-through telemetry block for BeiDou B1C.
 */

#include "beidou_b1c_dummy_telemetry_decoder.h"
#include "beidou_b1c_dummy_telemetry_decoder_gs.h"

BeidouB1cDummyTelemetryDecoder::BeidouB1cDummyTelemetryDecoder(
    const ConfigurationInterface* configuration,
    const std::string& role,
    unsigned int in_streams,
    unsigned int out_streams)
    : TelemetryDecoderAdapterBase(configuration,
          role,
          in_streams,
          out_streams)
{
    InitializeDecoder(beidou_b1c_make_dummy_telemetry_decoder_gs(satellite(), tlm_parameters_));
}

/*!
 * \file beidou_b1c_dummy_telemetry_decoder.h
 * \brief Adapter of a pass-through telemetry block for BeiDou B1C.
 */

#ifndef GNSS_SDR_BEIDOU_B1C_DUMMY_TELEMETRY_DECODER_H
#define GNSS_SDR_BEIDOU_B1C_DUMMY_TELEMETRY_DECODER_H

#include "telemetry_decoder_adapter_base.h"

class ConfigurationInterface;

class BeidouB1cDummyTelemetryDecoder : public TelemetryDecoderAdapterBase
{
public:
    BeidouB1cDummyTelemetryDecoder(const ConfigurationInterface* configuration,
        const std::string& role,
        unsigned int in_streams,
        unsigned int out_streams);

    inline std::string implementation() override
    {
        return "BEIDOU_B1C_Dummy_Telemetry_Decoder";
    }
};

#endif  // GNSS_SDR_BEIDOU_B1C_DUMMY_TELEMETRY_DECODER_H

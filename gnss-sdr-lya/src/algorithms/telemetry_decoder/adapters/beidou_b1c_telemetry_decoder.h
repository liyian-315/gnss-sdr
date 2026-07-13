/*!
 * \file beidou_b1c_telemetry_decoder.h
 * \brief Adapter of a BeiDou B1C CNAV1 data decoder block.
 *
 * GNSS-SDR is a Global Navigation Satellite System software-defined receiver.
 * This file is part of GNSS-SDR.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef GNSS_SDR_BEIDOU_B1C_TELEMETRY_DECODER_H
#define GNSS_SDR_BEIDOU_B1C_TELEMETRY_DECODER_H

#include "telemetry_decoder_adapter_base.h"
#include <string>

class ConfigurationInterface;

/*! \brief This class implements a NAV data decoder for BeiDou B1C CNAV1. */
class BeidouB1cTelemetryDecoder : public TelemetryDecoderAdapterBase
{
public:
    BeidouB1cTelemetryDecoder(
        const ConfigurationInterface* configuration,
        const std::string& role,
        unsigned int in_streams,
        unsigned int out_streams);

    inline std::string implementation() override
    {
        return "BEIDOU_B1C_Telemetry_Decoder";
    }
};

#endif  // GNSS_SDR_BEIDOU_B1C_TELEMETRY_DECODER_H

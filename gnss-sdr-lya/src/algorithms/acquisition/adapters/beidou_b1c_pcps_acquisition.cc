/*!
 * \file beidou_b1c_pcps_acquisition.cc
 * \brief Adapts a PCPS acquisition block to an AcquisitionInterface for
 *  BeiDou B1C signals.
 *
 * -----------------------------------------------------------------------------
 *
 * GNSS-SDR is a Global Navigation Satellite System software-defined receiver.
 * This file is part of GNSS-SDR.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * -----------------------------------------------------------------------------
 */

#include "beidou_b1c_pcps_acquisition.h"
#include "Beidou_B1C.h"
#include "beidou_b1c_signal_processing.h"


BeidouB1cPcpsAcquisition::BeidouB1cPcpsAcquisition(
    const ConfigurationInterface* configuration,
    const std::string& role,
    unsigned int in_streams,
    unsigned int out_streams)
    : BasePcpsAcquisition(configuration,
          role,
          in_streams,
          out_streams,
          BEIDOU_B1Cd_CODE_RATE_HZ,
          BEIDOU_B1C_OPT_ACQ_FS_HZ,
          BEIDOU_B1Cd_CODE_LENGTH_CHIPS,
          BEIDOU_B1Cd_CODE_PERIOD_MS)
{
}


void BeidouB1cPcpsAcquisition::code_gen_complex_sampled(own::span<std::complex<float>> dest, uint32_t prn, int32_t sampling_freq)
{
    beidou_b1c_code_gen_complex_sampled_boc(dest, prn, sampling_freq);
}

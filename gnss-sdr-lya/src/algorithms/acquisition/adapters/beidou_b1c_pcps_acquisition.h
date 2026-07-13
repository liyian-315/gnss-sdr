/*!
 * \file beidou_b1c_pcps_acquisition.h
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

#ifndef GNSS_SDR_BEIDOU_B1C_PCPS_ACQUISITION_H
#define GNSS_SDR_BEIDOU_B1C_PCPS_ACQUISITION_H

#include "base_pcps_acquisition.h"

/** \addtogroup Acquisition
 * \{ */
/** \addtogroup Acq_adapters
 * \{ */

/*!
 * \brief This class adapts a PCPS acquisition block to an AcquisitionInterface
 *  for BeiDou B1C signals.
 */
class BeidouB1cPcpsAcquisition : public BasePcpsAcquisition
{
public:
    BeidouB1cPcpsAcquisition(const ConfigurationInterface* configuration,
        const std::string& role, unsigned int in_streams,
        unsigned int out_streams);

    ~BeidouB1cPcpsAcquisition() = default;

    /*! \brief Returns "BEIDOU_B1C_PCPS_Acquisition" */
    inline std::string implementation() override
    {
        return "BEIDOU_B1C_PCPS_Acquisition";
    }

private:
    void code_gen_complex_sampled(own::span<std::complex<float>> dest, uint32_t prn, int32_t sampling_freq) override;
};


/** \} */
/** \} */
#endif  // GNSS_SDR_BEIDOU_B1C_PCPS_ACQUISITION_H

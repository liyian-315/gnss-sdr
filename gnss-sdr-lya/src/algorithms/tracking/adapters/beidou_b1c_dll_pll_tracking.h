/*!
 * \file beidou_b1c_dll_pll_tracking.h
 * \brief Interface of an adapter of a DLL+PLL tracking loop block
 * for BeiDou B1C to a TrackingInterface
 */

#ifndef GNSS_SDR_BEIDOU_B1C_DLL_PLL_TRACKING_H
#define GNSS_SDR_BEIDOU_B1C_DLL_PLL_TRACKING_H

#include "base_dll_pll_tracking.h"

class ConfigurationInterface;

class BeidouB1cDllPllTracking : public BaseDllPllTracking
{
public:
    BeidouB1cDllPllTracking(const ConfigurationInterface* configuration,
        const std::string& role,
        unsigned int in_streams,
        unsigned int out_streams);

    inline std::string implementation() override
    {
        return "BEIDOU_B1C_DLL_PLL_Tracking";
    }

private:
    void configure_tracking_parameters(const ConfigurationInterface* configuration) override;
    void create_tracking_block() override;
};

#endif  // GNSS_SDR_BEIDOU_B1C_DLL_PLL_TRACKING_H

/*!
 * \file beidou_b1c_dll_pll_tracking.cc
 * \brief Implementation of a DLL+PLL tracking adapter for BeiDou B1C.
 */

#include "beidou_b1c_dll_pll_tracking.h"
#include "Beidou_B1C.h"
#include "configuration_interface.h"
#include "display.h"
#include <algorithm>
#include <array>
#include <cmath>

#if USE_GLOG_AND_GFLAGS
#include <glog/logging.h>
#else
#include <absl/log/log.h>
#endif

BeidouB1cDllPllTracking::BeidouB1cDllPllTracking(
    const ConfigurationInterface* configuration,
    const std::string& role,
    unsigned int in_streams,
    unsigned int out_streams)
    : BaseDllPllTracking(configuration, role, in_streams, out_streams)
{
    configure_tracking_parameters(configuration);
    create_tracking_block();
}


void BeidouB1cDllPllTracking::configure_tracking_parameters(
    const ConfigurationInterface* configuration)
{
    const auto vector_length = static_cast<int>(std::round(static_cast<double>(config_params().fs_in) / (BEIDOU_B1Cp_CODE_RATE_HZ / BEIDOU_B1Cp_CODE_LENGTH_CHIPS)));
    config_params().vector_length = vector_length;
    config_params().system = 'C';
    const std::array<char, 3> sig{'C', '1', '\0'};
    std::copy_n(sig.data(), 3, config_params().signal);

    if (config_params().extend_correlation_symbols < 1)
        {
            config_params().extend_correlation_symbols = 1;
            std::cout << TEXT_RED << "WARNING: BEIDOU B1C. extend_correlation_symbols must be at least 1. Coherent integration has been set to 1 symbol (10 ms)" << TEXT_RESET << '\n';
        }
    else if (config_params().extend_correlation_symbols > 18)
        {
            config_params().extend_correlation_symbols = 18;
            std::cout << TEXT_RED << "WARNING: BEIDOU B1C. extend_correlation_symbols must be lower than 19. Coherent integration has been set to 18 symbols (180 ms)" << TEXT_RESET << '\n';
        }

    config_params().track_pilot = configuration->property(role() + ".track_pilot", true);
    if ((config_params().extend_correlation_symbols > 1) && (config_params().pll_bw_narrow_hz > config_params().pll_bw_hz or config_params().dll_bw_narrow_hz > config_params().dll_bw_hz))
        {
            std::cout << TEXT_RED << "WARNING: BEIDOU B1C. PLL or DLL narrow tracking bandwidth is higher than wide tracking one" << TEXT_RESET << '\n';
        }
}


void BeidouB1cDllPllTracking::create_tracking_block()
{
    if (config_params().item_type == "gr_complex")
        {
            tracking_sptr_ = dll_pll_veml_make_tracking(config_params());
            DLOG(INFO) << "tracking(" << tracking_sptr_->unique_id() << ")";
        }
    else
        {
            set_item_size(0);
            tracking_sptr_ = nullptr;
            LOG(WARNING) << config_params().item_type << " unknown tracking item type.";
        }
}

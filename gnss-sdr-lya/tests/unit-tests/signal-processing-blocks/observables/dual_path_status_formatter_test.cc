/*!
 * \file dual_path_status_formatter_test.cc
 * \brief Stability tests for dual-path status text and CSV formats.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "dual_path_status_formatter.h"
#include <gtest/gtest.h>

namespace
{
DualPathPairStatus reliable_status()
{
    DualPathPairStatus status;
    status.key = {'G', "5I", 18U};
    status.state = DualPathState::RELIABLE;
    status.primary_channel = 0U;
    status.second_channel = 1U;
    status.reacquisition_count = 2U;
    status.window_samples = 8U;
    status.primary_pseudorange_m = 1000.125;
    status.second_pseudorange_m = 1060.5;
    status.delta_m = 60.375;
    status.delta_median_m = 60.25;
    status.delta_mad_m = 0.75;
    status.primary_cn0_median_db_hz = 48.125;
    status.second_cn0_median_db_hz = 42.875;
    status.primary_doppler_median_hz = -1200.125;
    status.second_doppler_median_hz = -1198.5;
    status.doppler_delta_hz = 1.625;
    status.track_age_s = 12.4;
    status.primary_valid = true;
    status.second_valid = true;
    status.pair_time_aligned = true;
    return status;
}
}

TEST(DualPathStatusFormatter, StableVersionOneTextFormat)
{
    EXPECT_EQ(format_dual_path_status_v1(reliable_status()),
        "DUALPATH_STATUS version=1 system=G signal=5I prn=18 state=RELIABLE primary_ch=0 second_ch=1 primary_pseudorange_m=1000.125 second_pseudorange_m=1060.500 delta_m=60.375 delta_median_m=60.250 delta_mad_m=0.750 primary_cn0_db_hz=48.12 second_cn0_db_hz=42.88 primary_doppler_hz=-1200.125 second_doppler_hz=-1198.500 doppler_delta_hz=1.625 valid_count=8 track_age_s=12.4 reacquisition_count=2");
}

TEST(DualPathStatusFormatter, UsesNaForMissingSecondSource)
{
    DualPathPairStatus status;
    status.key = {'G', "5I", 18U};
    status.state = DualPathState::NO_SECOND_SOURCE;
    status.primary_channel = 0U;
    status.primary_pseudorange_m = 1000.0;
    status.primary_valid = true;
    EXPECT_EQ(format_dual_path_status_v1(status),
        "DUALPATH_STATUS version=1 system=G signal=5I prn=18 state=NO_SECOND_SOURCE primary_ch=0 second_ch=N/A primary_pseudorange_m=1000.000 second_pseudorange_m=N/A delta_m=N/A delta_median_m=N/A delta_mad_m=N/A primary_cn0_db_hz=N/A second_cn0_db_hz=N/A primary_doppler_hz=N/A second_doppler_hz=N/A doppler_delta_hz=N/A valid_count=0 track_age_s=0.0 reacquisition_count=0");
}

TEST(DualPathStatusFormatter, StableVersionOneCsvFormat)
{
    EXPECT_EQ(format_dual_path_csv_v1(reliable_status()),
        "1,G,5I,18,RELIABLE,0,1,1000.125,1060.500,60.375,60.250,0.750,48.12,42.88,-1200.125,-1198.500,1.625,8,12.4,2");
}

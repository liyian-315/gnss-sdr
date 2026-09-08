/*!
 * \file dual_path_pair_manager_test.cc
 * \brief Unit tests for the dual-path observables quality state machine.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "dual_path_pair_manager.h"
#include <gtest/gtest.h>

namespace
{
DualPathObservation make_observation(uint32_t path, double pseudorange_m, double time_s = 1.0)
{
    return {{'G', "5I", 18U}, path, path, time_s, pseudorange_m, 45.0, -1000.0, true};
}
}

TEST(DualPathPairManager, ConfirmsReliablePairAndComputesRobustDelta)
{
    DualPathPairConfig config;
    config.reliable_confirmations = 3U;
    config.max_delta_mad_m = 2.0;
    DualPathPairManager manager(config);

    auto status = manager.update({make_observation(0U, 1000.0), make_observation(1U, 1060.0)}).front();
    EXPECT_EQ(status.state, DualPathState::CANDIDATE);
    manager.update({make_observation(0U, 1001.0), make_observation(1U, 1062.0)});
    status = manager.update({make_observation(0U, 1002.0), make_observation(1U, 1062.0)}).front();
    EXPECT_EQ(status.state, DualPathState::RELIABLE);
    EXPECT_DOUBLE_EQ(status.delta_median_m, 60.0);
    EXPECT_DOUBLE_EQ(status.delta_mad_m, 0.0);
}

TEST(DualPathPairManager, ReportsNoSecondSourceWithoutInventingPair)
{
    DualPathPairConfig config;
    config.no_second_confirmations = 2U;
    DualPathPairManager manager(config);

    EXPECT_EQ(manager.update({make_observation(0U, 1000.0)}).front().state, DualPathState::SEARCHING);
    const auto status = manager.update({make_observation(0U, 1001.0)}).front();
    EXPECT_EQ(status.state, DualPathState::NO_SECOND_SOURCE);
    EXPECT_FALSE(status.second_valid);
}

TEST(DualPathPairManager, TracksIndependentLossAndReacquisition)
{
    DualPathPairConfig config;
    config.reliable_confirmations = 1U;
    config.lost_confirmations = 2U;
    DualPathPairManager manager(config);

    EXPECT_EQ(manager.update({make_observation(0U, 1000.0), make_observation(1U, 1060.0)}).front().state, DualPathState::RELIABLE);
    manager.update({make_observation(0U, 1001.0)});
    EXPECT_EQ(manager.update({make_observation(0U, 1002.0)}).front().state, DualPathState::LOST);
    auto status = manager.update({make_observation(0U, 1003.0), make_observation(1U, 1063.0)}).front();
    EXPECT_EQ(status.state, DualPathState::CANDIDATE);
    EXPECT_EQ(status.reacquisition_count, 1U);
    status = manager.update({make_observation(0U, 1004.0), make_observation(1U, 1064.0)}).front();
    EXPECT_EQ(status.state, DualPathState::RELIABLE);
    EXPECT_EQ(status.reacquisition_count, 1U);
}

TEST(DualPathPairManager, RejectsTimeMismatchAndKeepsSignalsSeparate)
{
    DualPathPairConfig config;
    config.reliable_confirmations = 1U;
    config.max_time_difference_s = 0.01;
    DualPathPairManager manager(config);

    auto second = make_observation(1U, 1060.0, 1.1);
    const auto statuses = manager.update({make_observation(0U, 1000.0, 1.0), second});
    ASSERT_EQ(statuses.size(), 1U);
    EXPECT_NE(statuses.front().state, DualPathState::RELIABLE);
    EXPECT_FALSE(statuses.front().pair_time_aligned);

    second = make_observation(1U, 1060.0);
    second.key.signal = "1C";
    EXPECT_EQ(manager.update({make_observation(0U, 1000.0), second}).size(), 2U);
}

TEST(DualPathPairManager, EqualPseudorangesNeverBecomeReliablePair)
{
    DualPathPairConfig config;
    config.reliable_confirmations = 1U;
    config.min_abs_delta_m = 1.0;
    DualPathPairManager manager(config);
    const auto status = manager.update({make_observation(0U, 1000.0), make_observation(1U, 1000.0)}).front();
    EXPECT_NE(status.state, DualPathState::RELIABLE);
    EXPECT_EQ(status.window_samples, 0U);
}

TEST(DualPathPairManager, RejectsWeakSecondAndExcessiveDopplerDifference)
{
    DualPathPairConfig config;
    config.reliable_confirmations = 1U;
    config.min_second_cn0_db_hz = 35.0;
    config.max_doppler_difference_hz = 10.0;
    DualPathPairManager manager(config);

    auto weak = make_observation(1U, 1060.0);
    weak.cn0_db_hz = 30.0;
    EXPECT_NE(manager.update({make_observation(0U, 1000.0), weak}).front().state, DualPathState::RELIABLE);

    auto wrong_doppler = make_observation(1U, 1060.0);
    wrong_doppler.doppler_hz = -950.0;
    EXPECT_NE(manager.update({make_observation(0U, 1000.0), wrong_doppler}).front().state, DualPathState::RELIABLE);
}

TEST(DualPathPairManager, SuddenDelayJumpDegradesReliablePair)
{
    DualPathPairConfig config;
    config.reliable_confirmations = 1U;
    config.max_delta_jump_m = 10.0;
    DualPathPairManager manager(config);

    EXPECT_EQ(manager.update({make_observation(0U, 1000.0), make_observation(1U, 1060.0)}).front().state, DualPathState::RELIABLE);
    const auto status = manager.update({make_observation(0U, 1001.0), make_observation(1U, 1101.0)}).front();
    EXPECT_EQ(status.state, DualPathState::DEGRADED);
    EXPECT_DOUBLE_EQ(status.delta_m, 100.0);
    EXPECT_EQ(status.window_samples, 1U);
}

TEST(DualPathPairManager, KeepsSeparatePrnsFromCrossPairing)
{
    DualPathPairConfig config;
    config.reliable_confirmations = 1U;
    DualPathPairManager manager(config);

    auto other_primary = make_observation(0U, 2000.0);
    other_primary.key.prn = 20U;
    auto other_second = make_observation(1U, 2075.0);
    other_second.key.prn = 20U;

    const auto statuses = manager.update({make_observation(0U, 1000.0), make_observation(1U, 1060.0),
        other_primary, other_second});
    ASSERT_EQ(statuses.size(), 2U);
    EXPECT_EQ(statuses[0].key.prn, 18U);
    EXPECT_DOUBLE_EQ(statuses[0].delta_m, 60.0);
    EXPECT_EQ(statuses[1].key.prn, 20U);
    EXPECT_DOUBLE_EQ(statuses[1].delta_m, 75.0);

    // PRN 20 keeps only its second path: it must not borrow the PRN 18 primary.
    other_second.pseudorange_m = 2076.0;
    const auto follow_up = manager.update({make_observation(0U, 1001.0), make_observation(1U, 1061.0), other_second});
    ASSERT_EQ(follow_up.size(), 2U);
    EXPECT_DOUBLE_EQ(follow_up[0].delta_m, 60.0);
    EXPECT_EQ(follow_up[1].key.prn, 20U);
    EXPECT_FALSE(follow_up[1].primary_valid);
    EXPECT_NE(follow_up[1].state, DualPathState::RELIABLE);
}

// REVIEW 2026-08-08 (see dev_notes/18_l5_dualpath_product_review.md, BLOCKING-1).
// update() only visits keys present in the current epoch. When both paths of a PRN
// disappear together the record is never revisited, so state, consecutive_good and the
// rolling windows freeze. This happens in normal operation: a PVT clock correction calls
// d_gnss_synchro_history->clear() on every channel, so every PRN vanishes for several
// epochs. The first epoch after the gap is then republished as RELIABLE carrying a
// pre-gap delta window, a track_age_s spanning the outage, and reacquisition_count=0.
// Required fix: age records out when they are absent from an update (or drive them with
// an explicit "no observation" tick), then re-enter CANDIDATE with cleared windows and a
// fresh pair_start_time_s. Drop the DISABLED_ prefix once that lands.
TEST(DualPathPairManager, TotalOutageMustNotRepublishStaleReliable)
{
    DualPathPairConfig config;
    config.reliable_confirmations = 3U;
    config.window_size = 8U;
    DualPathPairManager manager(config);

    for (int i = 0; i < 5; i++)
        {
            const double time_s = 1.0 + 0.1 * static_cast<double>(i);
            manager.update({make_observation(0U, 1000.0 + i, time_s), make_observation(1U, 1060.0 + i, time_s)});
        }

    // The PRN produces no observation at all for a minute.
    for (int i = 0; i < 10; i++)
        {
            manager.update({});
        }

    const auto status = manager.update({make_observation(0U, 5000.0, 61.0), make_observation(1U, 5060.0, 61.0)}).front();
    EXPECT_NE(status.state, DualPathState::RELIABLE);
    EXPECT_LE(status.window_samples, 1U);
    EXPECT_LT(status.track_age_s, 1.0);
}

TEST(DualPathPairManager, SecondPathOutageAndReacquisitionUseFreshGeneration)
{
    DualPathPairConfig config;
    config.reliable_confirmations = 3U;
    config.lost_confirmations = 3U;
    config.report_interval_s = 1.0;
    config.second_path_freshness_limit_s = 3.0;
    DualPathPairManager manager(config);

    DualPathPairStatus status;
    for (int i = 0; i < 3; i++)
        {
            const double time_s = 1.0 + static_cast<double>(i);
            status = manager.update({make_observation(0U, 1000.0 + i, time_s),
                make_observation(1U, 1060.0 + i, time_s)}).front();
        }
    ASSERT_EQ(status.state, DualPathState::RELIABLE);
    ASSERT_EQ(status.window_samples, 3U);

    status = manager.update({make_observation(0U, 1003.0, 4.0)}).front();
    EXPECT_EQ(status.state, DualPathState::DEGRADED);
    EXPECT_TRUE(status.primary_valid);
    EXPECT_FALSE(status.second_valid);
    EXPECT_DOUBLE_EQ(status.primary_pseudorange_m, 1003.0);

    status = manager.update({make_observation(0U, 1004.0, 5.0)}).front();
    EXPECT_EQ(status.state, DualPathState::DEGRADED);
    status = manager.update({make_observation(0U, 1005.0, 6.0)}).front();
    EXPECT_EQ(status.state, DualPathState::LOST);
    EXPECT_TRUE(status.primary_valid);
    EXPECT_FALSE(status.second_valid);
    EXPECT_EQ(status.window_samples, 0U);
    EXPECT_DOUBLE_EQ(status.second_pseudorange_m, 0.0);
    EXPECT_DOUBLE_EQ(status.delta_m, 0.0);
    EXPECT_DOUBLE_EQ(status.delta_median_m, 0.0);

    status = manager.update({make_observation(0U, 1006.0, 7.0)}).front();
    EXPECT_EQ(status.state, DualPathState::LOST);
    EXPECT_EQ(status.reacquisition_count, 0U);

    status = manager.update({make_observation(0U, 1007.0, 8.0),
        make_observation(1U, 1067.0, 8.0)}).front();
    EXPECT_EQ(status.state, DualPathState::CANDIDATE);
    EXPECT_EQ(status.window_samples, 1U);
    EXPECT_EQ(status.reacquisition_count, 1U);
    EXPECT_LT(status.track_age_s, 0.1);

    status = manager.update({make_observation(0U, 1008.0, 9.0),
        make_observation(1U, 1068.0, 9.0)}).front();
    EXPECT_EQ(status.state, DualPathState::CANDIDATE);
    EXPECT_EQ(status.reacquisition_count, 1U);
    status = manager.update({make_observation(0U, 1009.0, 10.0),
        make_observation(1U, 1069.0, 10.0)}).front();
    EXPECT_EQ(status.state, DualPathState::RELIABLE);
    EXPECT_EQ(status.window_samples, 3U);
    EXPECT_EQ(status.reacquisition_count, 1U);
}

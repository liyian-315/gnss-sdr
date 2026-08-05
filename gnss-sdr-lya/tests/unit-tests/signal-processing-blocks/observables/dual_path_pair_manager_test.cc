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
    const auto status = manager.update({make_observation(0U, 1003.0), make_observation(1U, 1063.0)}).front();
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

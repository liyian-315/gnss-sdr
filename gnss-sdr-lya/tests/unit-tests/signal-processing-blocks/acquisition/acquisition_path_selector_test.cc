/*!
 * \file acquisition_path_selector_test.cc
 * \brief Unit tests for primary/second acquisition path selection.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "acquisition_path_selector.h"
#include <gtest/gtest.h>

TEST(AcquisitionPathSelector, PrimaryAcceptsOnlyValidMainPeak)
{
    const auto accepted = select_acquisition_path(false, true, false);
    EXPECT_TRUE(accepted.accepted);
    EXPECT_FALSE(accepted.use_second);

    const auto rejected = select_acquisition_path(false, false, true);
    EXPECT_FALSE(rejected.accepted);
    EXPECT_FALSE(rejected.use_second);
}

TEST(AcquisitionPathSelector, SecondPathNeverFallsBackToMainPeak)
{
    const auto result = select_acquisition_path(true, true, false);
    EXPECT_FALSE(result.accepted);
    EXPECT_FALSE(result.use_second);
}

TEST(AcquisitionPathSelector, SecondPathUsesOnlyAcceptedSecondPeak)
{
    const auto result = select_acquisition_path(true, true, true);
    EXPECT_TRUE(result.accepted);
    EXPECT_TRUE(result.use_second);

    const auto without_main = select_acquisition_path(true, false, true);
    EXPECT_FALSE(without_main.accepted);
    EXPECT_FALSE(without_main.use_second);
}

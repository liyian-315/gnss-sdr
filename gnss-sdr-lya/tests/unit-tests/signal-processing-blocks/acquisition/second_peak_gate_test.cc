/*!
 * \file second_peak_gate_test.cc
 * \brief Unit tests for second acquisition peak quality gates.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "second_peak_gate.h"
#include <gtest/gtest.h>

namespace
{
const SecondPeakGateConfig gate{0.3F, 6.0F, 12.0F, 2U};
}

TEST(SecondPeakGate, AcceptsCandidateThatPassesEveryGate)
{
    EXPECT_TRUE(second_peak_passes_gate(gate, {4.0F, 6.0F, 8.0F, 3U}, 10.0F));
}

TEST(SecondPeakGate, RejectsWeakOrNoiseLikeCandidate)
{
    EXPECT_FALSE(second_peak_passes_gate(gate, {2.0F, 6.0F, 8.0F, 3U}, 10.0F));
    EXPECT_FALSE(second_peak_passes_gate(gate, {4.0F, 6.0F, 5.0F, 3U}, 10.0F));
    EXPECT_FALSE(second_peak_passes_gate(gate, {4.0F, 13.0F, 8.0F, 3U}, 10.0F));
}

TEST(SecondPeakGate, RejectsSearchWindowBoundaryCandidate)
{
    EXPECT_FALSE(second_peak_passes_gate(gate, {4.0F, 6.0F, 8.0F, 1U}, 10.0F));
}

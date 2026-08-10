/*!
 * \file tunnel_end_association_test.cc
 * \brief Unit tests for the tunnel DAS END_A / END_B physical association.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "tunnel_end_association.h"
#include <gtest/gtest.h>

namespace
{
//! 1 km tunnel, receiver 300 m from END_A, so expected END_B - END_A = +400 m.
TunnelSiteConfig site_at_300m()
{
    TunnelSiteConfig config;
    config.enable = true;
    config.length_m = 1000.0;
    config.measurement_position_m = 300.0;
    config.identity_max_error_m = 75.0;
    config.identity_margin_m = 50.0;
    config.identity_confirm_epochs = 3U;
    return config;
}

/*!
 * \brief Build a RELIABLE dual-path pair whose path1 - path0 delay is \p delta_m.
 *
 * primary_* are the path0 values and second_* the path1 values, exactly as
 * DualPathPairManager emits them.
 */
DualPathPairStatus reliable_pair(double delta_m, double path0_cn0 = 45.0, double path1_cn0 = 40.0)
{
    DualPathPairStatus pair;
    pair.key = {'G', "5I", 18U};
    pair.state = DualPathState::RELIABLE;
    pair.primary_valid = true;
    pair.second_valid = true;
    pair.pair_time_aligned = true;
    pair.primary_channel = 0U;
    pair.second_channel = 1U;
    pair.primary_pseudorange_m = 20000000.0;
    pair.second_pseudorange_m = 20000000.0 + delta_m;
    pair.delta_m = delta_m;
    pair.primary_cn0_db_hz = path0_cn0;
    pair.second_cn0_db_hz = path1_cn0;
    pair.primary_doppler_hz = -1200.0;
    pair.second_doppler_hz = -1199.0;
    return pair;
}

TunnelEndStatus settle(TunnelEndAssociation& association, const DualPathPairStatus& pair, int epochs)
{
    TunnelEndStatus status;
    for (int i = 0; i < epochs; i++)
        {
            status = association.update({pair}).front();
        }
    return status;
}
}  // namespace

TEST(TunnelEndAssociation, ExpectedDeltaFollowsPositionAndFixedDelays)
{
    EXPECT_DOUBLE_EQ(tunnel_expected_delta_b_minus_a_m(site_at_300m()), 400.0);

    TunnelSiteConfig midpoint = site_at_300m();
    midpoint.measurement_position_m = 500.0;
    EXPECT_DOUBLE_EQ(tunnel_expected_delta_b_minus_a_m(midpoint), 0.0);
}

TEST(TunnelEndAssociation, IdentifiesEndsFromMeasurementPosition)
{
    TunnelEndAssociation association(site_at_300m());
    // path1 is 400 m further away than path0, which is exactly the END_B geometry.
    const auto status = settle(association, reliable_pair(400.0), 3);

    EXPECT_EQ(status.identity, TunnelIdentityState::RELIABLE);
    EXPECT_TRUE(status.ends_valid);
    EXPECT_TRUE(status.end_a_is_path0);
    EXPECT_DOUBLE_EQ(status.expected_delta_b_minus_a_m, 400.0);
    EXPECT_DOUBLE_EQ(status.pseudorange_delta_b_minus_a_m, 400.0);
    EXPECT_NEAR(status.delta_residual_m, 0.0, 1e-9);
    EXPECT_DOUBLE_EQ(status.end_a_cn0_db_hz, 45.0);
    EXPECT_DOUBLE_EQ(status.end_b_cn0_db_hz, 40.0);
    EXPECT_DOUBLE_EQ(status.cn0_delta_a_minus_b_db, 5.0);
}

TEST(TunnelEndAssociation, PathSwapKeepsPhysicalEndLabels)
{
    TunnelEndAssociation association(site_at_300m());
    auto before = settle(association, reliable_pair(400.0, 45.0, 40.0), 3);
    ASSERT_EQ(before.identity, TunnelIdentityState::RELIABLE);
    ASSERT_TRUE(before.end_a_is_path0);
    const double end_a_pseudorange_before = before.end_a_pseudorange_m;
    const double end_b_pseudorange_before = before.end_b_pseudorange_m;

    // The receiver now reports the same two physical sources with path0/path1
    // exchanged: the near end became path1, so delta_m flips sign.
    DualPathPairStatus swapped = reliable_pair(-400.0, 40.0, 45.0);
    swapped.primary_pseudorange_m = end_b_pseudorange_before;
    swapped.second_pseudorange_m = end_a_pseudorange_before;

    // A proposed flip must be re-confirmed before the formal ends are published.
    const auto during = association.update({swapped}).front();
    EXPECT_EQ(during.identity, TunnelIdentityState::CANDIDATE);
    EXPECT_FALSE(during.ends_valid);

    const auto after = settle(association, swapped, 3);
    EXPECT_EQ(after.identity, TunnelIdentityState::RELIABLE);
    EXPECT_FALSE(after.end_a_is_path0);
    // The physical END_A is unchanged even though it is now carried by path1.
    EXPECT_DOUBLE_EQ(after.end_a_pseudorange_m, end_a_pseudorange_before);
    EXPECT_DOUBLE_EQ(after.end_b_pseudorange_m, end_b_pseudorange_before);
    EXPECT_DOUBLE_EQ(after.pseudorange_delta_b_minus_a_m, 400.0);
}

TEST(TunnelEndAssociation, Cn0SwapDoesNotSwapEndIdentity)
{
    TunnelEndAssociation association(site_at_300m());
    auto status = settle(association, reliable_pair(400.0, 45.0, 40.0), 3);
    ASSERT_EQ(status.identity, TunnelIdentityState::RELIABLE);
    ASSERT_TRUE(status.end_a_is_path0);

    // END_B is now the stronger end. Geometry is untouched, so the labels must not move.
    status = settle(association, reliable_pair(400.0, 38.0, 47.0), 3);
    EXPECT_EQ(status.identity, TunnelIdentityState::RELIABLE);
    EXPECT_TRUE(status.end_a_is_path0);
    EXPECT_DOUBLE_EQ(status.end_a_cn0_db_hz, 38.0);
    EXPECT_DOUBLE_EQ(status.end_b_cn0_db_hz, 47.0);
    EXPECT_DOUBLE_EQ(status.cn0_delta_a_minus_b_db, -9.0);
}

TEST(TunnelEndAssociation, MidpointIsReportedUnknown)
{
    TunnelSiteConfig midpoint = site_at_300m();
    midpoint.measurement_position_m = 500.0;
    TunnelEndAssociation association(midpoint);

    // Both assignments explain a symmetric geometry equally well: margin collapses.
    const auto status = settle(association, reliable_pair(30.0), 5);
    EXPECT_EQ(status.identity, TunnelIdentityState::UNKNOWN);
    EXPECT_FALSE(status.ends_valid);
    EXPECT_DOUBLE_EQ(status.identity_margin_m, 0.0);
    // Raw diagnostics stay available so the operator can still see both paths.
    EXPECT_TRUE(status.path0_valid);
    EXPECT_TRUE(status.path1_valid);
}

TEST(TunnelEndAssociation, DeltaFarFromExpectedIsReportedUnknown)
{
    TunnelEndAssociation association(site_at_300m());
    // Expected +400 m, observed +90 m: both hypotheses miss by more than 75 m.
    const auto status = settle(association, reliable_pair(90.0), 5);
    EXPECT_EQ(status.identity, TunnelIdentityState::UNKNOWN);
    EXPECT_FALSE(status.ends_valid);
    EXPECT_GT(status.identity_best_error_m, 75.0);
}

TEST(TunnelEndAssociation, ReacquisitionMustReconfirmBeforeReliable)
{
    TunnelEndAssociation association(site_at_300m());
    auto status = settle(association, reliable_pair(400.0), 3);
    ASSERT_EQ(status.identity, TunnelIdentityState::RELIABLE);

    DualPathPairStatus reacquired = reliable_pair(400.0);
    reacquired.reacquisition_count = 1U;
    status = association.update({reacquired}).front();
    EXPECT_EQ(status.identity, TunnelIdentityState::CANDIDATE);
    EXPECT_FALSE(status.ends_valid);

    status = association.update({reacquired}).front();
    EXPECT_EQ(status.identity, TunnelIdentityState::CANDIDATE);
    status = association.update({reacquired}).front();
    EXPECT_EQ(status.identity, TunnelIdentityState::RELIABLE);
    EXPECT_TRUE(status.ends_valid);
}

TEST(TunnelEndAssociation, SecondEndLossClearsFormalResult)
{
    TunnelEndAssociation association(site_at_300m());
    auto status = settle(association, reliable_pair(400.0), 3);
    ASSERT_TRUE(status.ends_valid);

    DualPathPairStatus lost;
    lost.key = {'G', "5I", 18U};
    lost.state = DualPathState::LOST;
    lost.primary_valid = true;
    lost.primary_pseudorange_m = 20000000.0;
    lost.primary_cn0_db_hz = 45.0;

    status = association.update({lost}).front();
    EXPECT_EQ(status.identity, TunnelIdentityState::UNKNOWN);
    EXPECT_FALSE(status.ends_valid);
    EXPECT_DOUBLE_EQ(status.end_b_cn0_db_hz, 0.0);
    const std::string line = format_tunnel_das_status_v1(status);
    EXPECT_NE(line.find("state=LOST"), std::string::npos) << line;
    EXPECT_NE(line.find("end_b_cn0_db_hz=N/A"), std::string::npos) << line;
}

TEST(TunnelEndAssociation, AsymmetricFixedDelaysShiftExpectedDelta)
{
    TunnelSiteConfig config = site_at_300m();
    config.end_a_fixed_delay_m = 120.0;
    config.end_b_fixed_delay_m = 20.0;
    // (700 + 20) - (300 + 120) = 300 m
    EXPECT_DOUBLE_EQ(tunnel_expected_delta_b_minus_a_m(config), 300.0);

    TunnelEndAssociation association(config);
    const auto status = settle(association, reliable_pair(300.0), 3);
    EXPECT_EQ(status.identity, TunnelIdentityState::RELIABLE);
    EXPECT_TRUE(status.end_a_is_path0);
    EXPECT_NEAR(status.delta_residual_m, 0.0, 1e-9);

    // Without the asymmetric compensation the same observation would be rejected.
    TunnelEndAssociation uncompensated(site_at_300m());
    EXPECT_EQ(settle(uncompensated, reliable_pair(300.0), 3).identity, TunnelIdentityState::UNKNOWN);
}

TEST(TunnelEndAssociation, DegradedPairNeverPublishesFormalEnds)
{
    TunnelEndAssociation association(site_at_300m());
    DualPathPairStatus degraded = reliable_pair(400.0);
    degraded.state = DualPathState::DEGRADED;

    const auto status = settle(association, degraded, 5);
    EXPECT_NE(status.identity, TunnelIdentityState::RELIABLE);
    EXPECT_FALSE(status.ends_valid);
    const std::string line = format_tunnel_das_status_v1(status);
    EXPECT_NE(line.find("end_a_cn0_db_hz=N/A"), std::string::npos) << line;
}

TEST(TunnelEndAssociation, StableVersionOneFieldOutput)
{
    TunnelEndAssociation association(site_at_300m());
    const auto status = settle(association, reliable_pair(400.0, 42.6, 39.8), 3);
    EXPECT_EQ(format_tunnel_das_status_v1(status),
        "TUNNEL_DAS_STATUS version=1 position_m=300.0 prn=18 state=RELIABLE identity=RELIABLE "
        "end_a_path=0 end_b_path=1 end_a_cn0_db_hz=42.60 end_b_cn0_db_hz=39.80 "
        "cn0_delta_a_minus_b_db=2.80 end_a_pseudorange_m=20000000.000 "
        "end_b_pseudorange_m=20000400.000 pseudorange_delta_b_minus_a_m=400.000 "
        "expected_delta_b_minus_a_m=400.0 delta_residual_m=0.000 end_a_doppler_hz=-1200.000 "
        "end_b_doppler_hz=-1199.000 path0_cn0_db_hz=42.60 path1_cn0_db_hz=39.80 "
        "identity_error_m=0.0 identity_margin_m=800.0 identity_confirm=3 reacquisition_count=0");
}

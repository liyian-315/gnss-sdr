/*!
 * \file tunnel_temporal_integration_test.cc
 * \brief Deterministic report-epoch integration tests for the tunnel DAS product.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "dual_path_pair_manager.h"
#include "tunnel_end_association.h"
#include <gtest/gtest.h>
#include <string>
#include <vector>

namespace tunnel_temporal_test
{
TunnelSiteConfig site(double position_m = 300.0)
{
    TunnelSiteConfig config;
    config.enable = true;
    config.length_m = 1000.0;
    config.measurement_position_m = position_m;
    config.identity_max_error_m = 75.0;
    config.identity_margin_m = 50.0;
    config.identity_confirm_epochs = 3U;
    return config;
}

DualPathPairConfig pair_config()
{
    DualPathPairConfig config;
    config.window_size = 8U;
    config.reliable_confirmations = 3U;
    config.no_second_confirmations = 3U;
    config.lost_confirmations = 3U;
    config.report_interval_s = 1.0;
    config.second_path_freshness_limit_s = 3.0;
    config.max_time_difference_s = 0.05;
    config.min_abs_delta_m = 1.0;
    return config;
}

DualPathObservation observation(uint32_t path, double pseudorange_m, double cn0_db_hz, double time_s)
{
    return {{'G', "5I", 18U}, path, path, time_s, pseudorange_m, cn0_db_hz, -1200.0 + path, true};
}

class ProductHarness
{
public:
    explicit ProductHarness(TunnelSiteConfig tunnel = site())
        : pair_manager(pair_config()), association(std::move(tunnel))
    {
    }

    TunnelEndStatus tick(const std::vector<DualPathObservation>& observations)
    {
        const auto pairs = pair_manager.update(observations);
        EXPECT_FALSE(pairs.empty());
        const auto tunnel = association.update(pairs);
        EXPECT_FALSE(tunnel.empty());
        return tunnel.front();
    }

    DualPathPairManager pair_manager;
    TunnelEndAssociation association;
};

std::vector<DualPathObservation> both(double time_s, double path0_rho = 20000000.0,
    double delta_m = 400.0, double path0_cn0 = 42.0, double path1_cn0 = 39.0)
{
    return {observation(0U, path0_rho, path0_cn0, time_s),
        observation(1U, path0_rho + delta_m, path1_cn0, time_s)};
}

TunnelEndStatus settle(ProductHarness& product, int epochs = 10)
{
    TunnelEndStatus status;
    for (int epoch = 1; epoch <= epochs; ++epoch)
        {
            status = product.tick(both(static_cast<double>(epoch)));
        }
    return status;
}
}  // namespace tunnel_temporal_test

TEST(TunnelTemporalIntegration, Scenario1StableDualEndBecomesReliable)
{
    using namespace tunnel_temporal_test;
    ProductHarness product;
    const auto status = settle(product);
    EXPECT_EQ(status.pair_state, DualPathState::RELIABLE);
    EXPECT_EQ(status.identity, TunnelIdentityState::RELIABLE);
    EXPECT_TRUE(status.end_a_is_path0);
    EXPECT_DOUBLE_EQ(status.cn0_delta_a_minus_b_db, 3.0);
    EXPECT_DOUBLE_EQ(status.pseudorange_delta_b_minus_a_m, 400.0);
}

TEST(TunnelTemporalIntegration, Scenario2PowerCrossingDoesNotSwapPhysicalEnds)
{
    using namespace tunnel_temporal_test;
    ProductHarness product;
    settle(product, 5);
    const double a_cn0[] = {45.0, 42.0, 40.0, 37.0, 34.0};
    const double b_cn0[] = {35.0, 38.0, 40.0, 43.0, 46.0};
    TunnelEndStatus status;
    for (int i = 0; i < 5; ++i)
        {
            status = product.tick(both(6.0 + i, 20000000.0 + i, 400.0, a_cn0[i], b_cn0[i]));
        }
    EXPECT_EQ(status.identity, TunnelIdentityState::RELIABLE);
    EXPECT_TRUE(status.end_a_is_path0);
    EXPECT_DOUBLE_EQ(status.end_a_cn0_db_hz, 34.0);
    EXPECT_DOUBLE_EQ(status.end_b_cn0_db_hz, 46.0);
}

TEST(TunnelTemporalIntegration, Scenario3PathNumberSwapReconfirmsPhysicalEnds)
{
    using namespace tunnel_temporal_test;
    ProductHarness product;
    const auto before = settle(product, 5);
    ASSERT_TRUE(before.end_a_is_path0);

    TunnelEndStatus status;
    for (int epoch = 6; epoch <= 10; ++epoch)
        {
            status = product.tick(both(static_cast<double>(epoch), 20000400.0, -400.0, 39.0, 42.0));
        }
    EXPECT_EQ(status.identity, TunnelIdentityState::RELIABLE);
    EXPECT_FALSE(status.end_a_is_path0);
    EXPECT_DOUBLE_EQ(status.end_a_pseudorange_m, 20000000.0);
    EXPECT_DOUBLE_EQ(status.end_b_pseudorange_m, 20000400.0);
}

TEST(TunnelTemporalIntegration, Scenario4SecondEndLossProgressesDegradedThenLost)
{
    using namespace tunnel_temporal_test;
    ProductHarness product;
    settle(product, 5);

    auto status = product.tick({observation(0U, 20000006.0, 42.0, 6.0)});
    EXPECT_EQ(status.pair_state, DualPathState::DEGRADED);
    EXPECT_EQ(status.identity, TunnelIdentityState::UNKNOWN);
    EXPECT_FALSE(status.ends_valid);
    EXPECT_NE(format_tunnel_das_status_v1(status).find("state=DEGRADED"), std::string::npos);

    product.tick({observation(0U, 20000007.0, 42.0, 7.0)});
    status = product.tick({observation(0U, 20000008.0, 42.0, 8.0)});
    EXPECT_EQ(status.pair_state, DualPathState::LOST);
    const std::string line = format_tunnel_das_status_v1(status);
    EXPECT_NE(line.find("identity=UNKNOWN"), std::string::npos);
    EXPECT_NE(line.find("end_b_cn0_db_hz=N/A"), std::string::npos);
    EXPECT_NE(line.find("cn0_delta_a_minus_b_db=N/A"), std::string::npos);
    EXPECT_NE(line.find("pseudorange_delta_b_minus_a_m=N/A"), std::string::npos);
    EXPECT_NE(line.find("delta_residual_m=N/A"), std::string::npos);
}

TEST(TunnelTemporalIntegration, Scenario5EmptyEpochsAdvanceStateInsteadOfFreezing)
{
    using namespace tunnel_temporal_test;
    ProductHarness product;
    settle(product, 5);

    auto status = product.tick({});
    EXPECT_EQ(status.pair_state, DualPathState::DEGRADED);
    status = product.tick({});
    EXPECT_EQ(status.pair_state, DualPathState::DEGRADED);
    status = product.tick({});
    EXPECT_EQ(status.pair_state, DualPathState::LOST);
    status = product.tick({});
    EXPECT_EQ(status.pair_state, DualPathState::LOST);
    status = product.tick({});
    EXPECT_EQ(status.pair_state, DualPathState::LOST);
    EXPECT_EQ(status.identity, TunnelIdentityState::UNKNOWN);
    EXPECT_FALSE(status.path0_valid);
    EXPECT_FALSE(status.path1_valid);
}

TEST(TunnelTemporalIntegration, Scenario6ReappearanceStartsFreshCandidateGeneration)
{
    using namespace tunnel_temporal_test;
    ProductHarness product;
    settle(product, 5);
    product.tick({});
    product.tick({});
    product.tick({});
    product.tick({});
    auto status = product.tick({});
    ASSERT_EQ(status.pair_state, DualPathState::LOST);

    status = product.tick(both(11.0, 21000000.0));
    EXPECT_EQ(status.pair_state, DualPathState::CANDIDATE);
    EXPECT_EQ(status.identity, TunnelIdentityState::CANDIDATE);
    EXPECT_FALSE(status.ends_valid);
    EXPECT_EQ(status.reacquisition_count, 1U);

    status = product.tick(both(12.0, 21000001.0));
    EXPECT_EQ(status.pair_state, DualPathState::CANDIDATE);
    EXPECT_EQ(status.reacquisition_count, 1U);
    status = product.tick(both(13.0, 21000002.0));
    EXPECT_EQ(status.pair_state, DualPathState::RELIABLE);
    EXPECT_EQ(status.identity, TunnelIdentityState::RELIABLE);
    EXPECT_EQ(status.reacquisition_count, 1U);
}

TEST(TunnelTemporalIntegration, Scenario7MidpointRemainsUnknown)
{
    using namespace tunnel_temporal_test;
    ProductHarness product(site(500.0));
    TunnelEndStatus status;
    for (int epoch = 1; epoch <= 10; ++epoch)
        {
            status = product.tick(both(static_cast<double>(epoch), 20000000.0, 30.0));
        }
    EXPECT_EQ(status.pair_state, DualPathState::RELIABLE);
    EXPECT_EQ(status.identity, TunnelIdentityState::UNKNOWN);
    EXPECT_FALSE(status.ends_valid);
}

TEST(TunnelTemporalIntegration, Scenario8FixedDelaysShiftExpectedGeometry)
{
    using namespace tunnel_temporal_test;
    auto config = site();
    config.end_a_fixed_delay_m = 50.0;
    config.end_b_fixed_delay_m = 120.0;
    EXPECT_DOUBLE_EQ(tunnel_expected_delta_b_minus_a_m(config), 470.0);
}

TEST(TunnelTemporalIntegration, Scenario10PositionChangeReversesExpectedDeltaAfterRestart)
{
    using namespace tunnel_temporal_test;
    EXPECT_DOUBLE_EQ(tunnel_expected_delta_b_minus_a_m(site(300.0)), 400.0);
    EXPECT_DOUBLE_EQ(tunnel_expected_delta_b_minus_a_m(site(700.0)), -400.0);
}

namespace tunnel_temporal_test
{
//! Exactly the thresholds shipped in product/tunnel_das/conf/gps_l5_tunnel_dual_end_b210.conf.
DualPathPairConfig field_pair_config()
{
    DualPathPairConfig config;
    config.window_size = 15U;
    config.reliable_confirmations = 5U;
    config.no_second_confirmations = 3U;
    config.lost_confirmations = 5U;
    config.report_interval_s = 1.0;
    config.second_path_freshness_limit_s = 5.0;
    config.max_time_difference_s = 0.05;
    config.min_primary_cn0_db_hz = 20.0;
    config.min_second_cn0_db_hz = 15.0;
    config.max_doppler_difference_hz = 500.0;
    config.min_abs_delta_m = 10.0;
    config.max_delta_jump_m = 100.0;
    config.max_delta_mad_m = 25.0;
    return config;
}

TunnelSiteConfig field_site()
{
    auto config = site(300.0);
    config.identity_confirm_epochs = 5;
    return config;
}
}  // namespace tunnel_temporal_test

TEST(TunnelTemporalIntegration, FieldConfigPathSwapKeepsPhysicalEndsThroughLostGeneration)
{
    using namespace tunnel_temporal_test;
    DualPathPairManager manager(field_pair_config());
    TunnelEndAssociation association(field_site());

    TunnelEndStatus status;
    const auto tick = [&](const std::vector<DualPathObservation>& observations) {
        const auto tunnel = association.update(manager.update(observations));
        EXPECT_FALSE(tunnel.empty());
        status = tunnel.front();
    };

    for (int epoch = 1; epoch <= 5; ++epoch)
        {
            tick(both(static_cast<double>(epoch)));
        }
    ASSERT_EQ(status.identity, TunnelIdentityState::RELIABLE);
    ASSERT_TRUE(status.end_a_is_path0);
    ASSERT_DOUBLE_EQ(status.end_a_pseudorange_m, 20000000.0);

    // Reversing delta by 800 m exceeds the shipped 100 m jump gate. The old
    // generation must age through DEGRADED and LOST before the swap is accepted.
    for (int epoch = 6; epoch <= 9; ++epoch)
        {
            tick(both(static_cast<double>(epoch), 20000400.0, -400.0, 39.0, 42.0));
            EXPECT_EQ(status.pair_state, DualPathState::DEGRADED) << "epoch " << epoch;
            EXPECT_EQ(status.identity, TunnelIdentityState::UNKNOWN);
            EXPECT_FALSE(status.ends_valid);
        }
    tick(both(10.0, 20000400.0, -400.0, 39.0, 42.0));
    ASSERT_EQ(status.pair_state, DualPathState::LOST);

    for (int epoch = 11; epoch <= 14; ++epoch)
        {
            tick(both(static_cast<double>(epoch), 20000400.0, -400.0, 39.0, 42.0));
            EXPECT_EQ(status.pair_state, DualPathState::CANDIDATE) << "epoch " << epoch;
            EXPECT_FALSE(status.ends_valid);
        }
    tick(both(15.0, 20000400.0, -400.0, 39.0, 42.0));
    EXPECT_EQ(status.pair_state, DualPathState::RELIABLE);
    EXPECT_EQ(status.identity, TunnelIdentityState::RELIABLE);
    EXPECT_FALSE(status.end_a_is_path0);
    EXPECT_DOUBLE_EQ(status.end_a_pseudorange_m, 20000000.0);
    EXPECT_DOUBLE_EQ(status.end_b_pseudorange_m, 20000400.0);
    EXPECT_DOUBLE_EQ(status.pseudorange_delta_b_minus_a_m, 400.0);
    EXPECT_EQ(status.reacquisition_count, 1U);
}

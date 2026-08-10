/*!
 * \file tunnel_end_association.h
 * \brief Associates already-separated dual-path observables with the two physical
 *        ends of a tunnel DAS installation.
 *
 * This is a second layer on top of DualPathPairManager. It never re-does
 * acquisition, tracking, CN0 estimation or pseudorange computation: it only
 * decides which of the two paths currently corresponds to which tunnel end, using
 * the known measurement position and the observed pseudorange difference.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef GNSS_SDR_TUNNEL_END_ASSOCIATION_H
#define GNSS_SDR_TUNNEL_END_ASSOCIATION_H

#include "dual_path_pair_manager.h"
#include <cstdint>
#include <map>
#include <string>
#include <vector>

/*!
 * \brief Confidence in the physical END_A / END_B assignment.
 *
 * This is independent of DualPathState: the receiver can hold a perfectly
 * RELIABLE pair whose two ends still cannot be told apart (for example near the
 * tunnel midpoint, where both assignments explain the geometry equally well).
 */
enum class TunnelIdentityState
{
    UNKNOWN,
    CANDIDATE,
    RELIABLE
};

const char* tunnel_identity_state_name(TunnelIdentityState state);

struct TunnelSiteConfig
{
    bool enable{false};
    double length_m{0.0};
    double measurement_position_m{0.0};
    //! Fixed feeder/amplifier/digital-link delay of each end, expressed in metres.
    //! The two ends are NOT assumed to be equal.
    double end_a_fixed_delay_m{0.0};
    double end_b_fixed_delay_m{0.0};
    //! PROVISIONAL gate values: not calibrated against field measurements yet.
    double identity_max_error_m{75.0};
    double identity_margin_m{50.0};
    int32_t identity_confirm_epochs{5};
    uint32_t prn{0U};
    std::string end_a_name{"END_A"};
    std::string end_b_name{"END_B"};
};

/*!
 * \brief Expected END_B minus END_A propagation difference at the configured position.
 *
 * d_A = measurement_position_m, d_B = length_m - measurement_position_m, and each
 * end adds its own fixed delay:
 *   expected = (d_B + delay_B) - (d_A + delay_A)
 */
double tunnel_expected_delta_b_minus_a_m(const TunnelSiteConfig& config);

//! Empty on success; otherwise a field-specific reason suitable for TUNNEL_CONFIG_ERROR.
std::string validate_tunnel_site_config(const TunnelSiteConfig& config);

struct TunnelEndStatus
{
    DualPathKey key;
    DualPathState pair_state{DualPathState::SEARCHING};
    TunnelIdentityState identity{TunnelIdentityState::UNKNOWN};

    //! True only when the formal END_A / END_B fields below may be used.
    bool ends_valid{false};
    bool end_a_is_path0{true};

    double position_m{0.0};
    double tunnel_length_m{0.0};
    double expected_delta_b_minus_a_m{0.0};

    double end_a_cn0_db_hz{0.0};
    double end_b_cn0_db_hz{0.0};
    double cn0_delta_a_minus_b_db{0.0};
    double end_a_pseudorange_m{0.0};
    double end_b_pseudorange_m{0.0};
    double pseudorange_delta_b_minus_a_m{0.0};
    double end_a_doppler_hz{0.0};
    double end_b_doppler_hz{0.0};
    double delta_residual_m{0.0};

    //! Identity cost diagnostics: best hypothesis error and its separation from the
    //! runner-up. Both are always populated when the pair itself is usable.
    double identity_best_error_m{0.0};
    double identity_margin_m{0.0};
    uint32_t identity_confirm_count{0U};
    uint32_t reacquisition_count{0U};

    //! Raw path diagnostics, always emitted so the operator can see the receiver
    //! is alive even while the ends cannot be told apart.
    bool path0_valid{false};
    bool path1_valid{false};
    double path0_cn0_db_hz{0.0};
    double path1_cn0_db_hz{0.0};
};

/*!
 * \brief Stateful END_A / END_B associator, one record per (system, signal, PRN).
 *
 * Identity is driven by delay geometry and its continuity across epochs, never by
 * which path is currently stronger.
 */
class TunnelEndAssociation
{
public:
    explicit TunnelEndAssociation(TunnelSiteConfig config = {});

    std::vector<TunnelEndStatus> update(const std::vector<DualPathPairStatus>& pairs);
    void reset();

    const TunnelSiteConfig& config() const { return d_config; }

private:
    struct Record
    {
        TunnelIdentityState identity{TunnelIdentityState::UNKNOWN};
        bool has_assignment{false};
        bool end_a_is_path0{true};
        uint32_t confirm_count{0U};
        uint32_t last_reacquisition_count{0U};
        bool has_reacquisition_baseline{false};
    };

    TunnelSiteConfig d_config;
    std::map<DualPathKey, Record> d_records;
};

//! Stable one-line field output for the tunnel operator. Rendering only.
std::string format_tunnel_das_status_v1(const TunnelEndStatus& status);

//! Startup banner: TUNNEL_DAS_CONFIG length_m=... position_m=...
std::string format_tunnel_das_banner(const TunnelSiteConfig& config);

#endif  // GNSS_SDR_TUNNEL_END_ASSOCIATION_H

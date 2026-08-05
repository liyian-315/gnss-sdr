/*!
 * \file acquisition_path_selector.h
 * \brief Selection policy for primary and second-path acquisition results.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef GNSS_SDR_ACQUISITION_PATH_SELECTOR_H
#define GNSS_SDR_ACQUISITION_PATH_SELECTOR_H

struct AcquisitionPathSelection
{
    bool accepted;
    bool use_second;
};

inline AcquisitionPathSelection select_acquisition_path(bool requires_second_path,
    bool main_peak_valid,
    bool second_peak_valid)
{
    if (requires_second_path)
        {
            const bool accepted = main_peak_valid && second_peak_valid;
            return {accepted, accepted};
        }
    return {main_peak_valid, false};
}

#endif  // GNSS_SDR_ACQUISITION_PATH_SELECTOR_H

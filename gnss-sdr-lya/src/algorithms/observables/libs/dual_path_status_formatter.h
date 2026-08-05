/*!
 * \file dual_path_status_formatter.h
 * \brief Stable versioned text and CSV output for dual-path status.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef GNSS_SDR_DUAL_PATH_STATUS_FORMATTER_H
#define GNSS_SDR_DUAL_PATH_STATUS_FORMATTER_H

#include "dual_path_pair_manager.h"
#include <string>

std::string format_dual_path_status_v1(const DualPathPairStatus& status);
std::string dual_path_csv_header_v1();
std::string format_dual_path_csv_v1(const DualPathPairStatus& status);

#endif  // GNSS_SDR_DUAL_PATH_STATUS_FORMATTER_H

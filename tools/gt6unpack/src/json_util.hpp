// SPDX-License-Identifier: GPL-2.0-only
// Small JSON helpers shared by the build log and the manifest writers.
#pragma once
#include <string>

namespace gt6 {

// A JSON string literal (with quotes) for s: escapes '"', '\\' and control characters.
std::string json_str(const std::string& s);

}  // namespace gt6

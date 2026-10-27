// SPDX-License-Identifier: GPL-2.0-only
// PARAM.SFO parser. Format per the public PS3 developer wiki; no third-party code.
#pragma once
#include <cstdint>
#include <map>
#include <span>
#include <stdexcept>
#include <string>
#include <variant>

namespace gt6 {

class SfoError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

using Sfo = std::map<std::string, std::variant<std::string, uint32_t>>;

// Parses a PARAM.SFO. String entries (formats 0x0004 and 0x0204) come back as std::string
// without trailing NULs, integer entries (0x0404) as uint32_t. Throws SfoError on bad input.
Sfo parse_sfo(std::span<const uint8_t> data);

}  // namespace gt6

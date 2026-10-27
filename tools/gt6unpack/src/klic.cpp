// SPDX-License-Identifier: GPL-2.0-only
// Finding a game's NPDRM klicensee in its own decrypted executable. No third-party code.
#include "klic.hpp"

#include <algorithm>

namespace gt6 {
namespace {

int hex_value(uint8_t c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

}  // namespace

std::vector<KlicCandidate> klicensee_strings(std::span<const uint8_t> d) {
    constexpr size_t kDigits = 32;
    std::vector<KlicCandidate> out;
    for (size_t i = 0; i + 2 + kDigits <= d.size(); ++i) {
        if (d[i] != '0' || (d[i + 1] != 'x' && d[i + 1] != 'X')) continue;
        if (i > 0 && hex_value(d[i - 1]) >= 0) continue;  // "0x" inside a longer hex run
        const size_t end = i + 2 + kDigits;
        if (!std::all_of(d.begin() + i + 2, d.begin() + end, [](uint8_t c) { return hex_value(c) >= 0; }))
            continue;
        if (end < d.size() && hex_value(d[end]) >= 0) continue;  // more than 32 digits
        KlicCandidate c{{}, i};
        for (size_t k = 0; k < 16; ++k)
            c.key[k] = uint8_t(hex_value(d[i + 2 + 2 * k]) << 4 | hex_value(d[i + 3 + 2 * k]));
        const bool zero = std::all_of(c.key.begin(), c.key.end(), [](uint8_t b) { return b == 0; });
        const bool seen = std::any_of(out.begin(), out.end(), [&](const KlicCandidate& o) { return o.key == c.key; });
        if (!zero && !seen) out.push_back(c);
        i = end - 1;
    }
    return out;
}

}  // namespace gt6

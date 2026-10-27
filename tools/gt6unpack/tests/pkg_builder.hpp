// SPDX-License-Identifier: GPL-2.0-only
// Test-only synthetic PS3 package writer. Writes only where the caller points it (tmp dirs);
// never commit its output.
#pragma once
#include "crypto.hpp"
#include "keys.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <utility>
#include <vector>

namespace gt6test {

using PkgFiles = std::vector<std::pair<std::string, std::vector<uint8_t>>>;

inline void be_put(std::vector<uint8_t>& b, size_t off, uint64_t v, int bytes) {
    for (int i = 0; i < bytes; ++i) b[off + i] = uint8_t(v >> (8 * (bytes - 1 - i)));
}

// Builds a finalized retail PS3 package. A name ending in '/' becomes a folder entry (its
// data is ignored). Names are written verbatim, so tests can build hostile packages.
inline void write_test_pkg(const std::filesystem::path& path, const std::string& title_id,
                           const PkgFiles& files) {
    constexpr size_t kHeader = 0x140;
    const std::string content_id = "EP9001-" + title_id + "_00-0000000000000000";
    std::vector<uint8_t> plain(files.size() * 32, 0);
    auto align16 = [&] { plain.resize((plain.size() + 15) & ~size_t(15), 0); };
    for (size_t i = 0; i < files.size(); ++i) {
        const auto& [name, data] = files[i];
        const bool dir = !name.empty() && name.back() == '/';
        align16();
        const uint64_t name_off = plain.size();
        plain.insert(plain.end(), name.begin(), name.end());
        align16();
        const uint64_t data_off = plain.size();
        if (!dir) plain.insert(plain.end(), data.begin(), data.end());
        align16();
        const size_t e = i * 32;
        be_put(plain, e + 0, name_off, 4);
        be_put(plain, e + 4, name.size(), 4);
        be_put(plain, e + 8, data_off, 8);
        be_put(plain, e + 16, dir ? 0 : data.size(), 8);
        be_put(plain, e + 24, dir ? 4 : 3, 4);
    }

    std::vector<uint8_t> hdr(kHeader, 0);
    hdr[0] = 0x7f; hdr[1] = 'P'; hdr[2] = 'K'; hdr[3] = 'G';
    be_put(hdr, 4, 0x8000, 2);   // retail
    be_put(hdr, 6, 1, 2);        // PS3
    be_put(hdr, 8, 0xC0, 4);     // meta offset
    be_put(hdr, 12, 0, 4);       // meta count
    be_put(hdr, 16, 0, 4);       // meta size
    be_put(hdr, 20, files.size(), 4);
    be_put(hdr, 24, kHeader + plain.size() + 32, 8);  // pkg_size, with 32-byte trailer
    be_put(hdr, 32, kHeader, 8);                       // data offset
    be_put(hdr, 40, plain.size(), 8);                  // data size
    std::copy(content_id.begin(), content_id.end(), hdr.begin() + 48);
    // klicensee / counter start: arbitrary non-trivial value near a carry boundary
    for (int i = 0; i < 16; ++i) hdr[0x70 + i] = i < 8 ? uint8_t(0x11 * (i + 1)) : 0xff;

    const std::span<const uint8_t> iv(hdr.data() + 0x70, 16);
    // Independent keystream: AES-ECB of a true 128-bit big-endian counter, block by block.
    std::vector<uint8_t> enc(plain.size());
    std::array<uint8_t, 16> ctr;
    std::copy(iv.begin(), iv.end(), ctr.begin());
    for (size_t off = 0; off < plain.size(); off += 16) {
        auto ks = gt6::crypto::aes128_ecb_encrypt_block(gt6::pkg_retail_key(), ctr);
        for (size_t j = 0; j < 16; ++j) enc[off + j] = plain[off + j] ^ ks[j];
        for (int j = 15; j >= 0 && ++ctr[j] == 0; --j) {}
    }

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out.write(reinterpret_cast<const char*>(hdr.data()), std::streamsize(hdr.size()));
    out.write(reinterpret_cast<const char*>(enc.data()), std::streamsize(enc.size()));
    const std::vector<uint8_t> trailer(32, 0);
    out.write(reinterpret_cast<const char*>(trailer.data()), 32);
}

// Minimal PARAM.SFO writer for tests.
struct SfoItem {
    std::string key;
    std::string str;
    uint32_t num = 0;
    bool is_num = false;
};

inline std::vector<uint8_t> build_sfo(const std::vector<SfoItem>& items) {
    std::vector<uint8_t> keys, data;
    std::vector<uint8_t> table;
    auto le = [](std::vector<uint8_t>& b, uint64_t v, int n) {
        for (int i = 0; i < n; ++i) b.push_back(uint8_t(v >> (8 * i)));
    };
    for (const auto& it : items) {
        le(table, keys.size(), 2);
        keys.insert(keys.end(), it.key.begin(), it.key.end());
        keys.push_back(0);
        const uint32_t max = it.is_num ? 4 : 64;
        le(table, it.is_num ? 0x0404 : 0x0204, 2);
        le(table, it.is_num ? 4 : it.str.size() + 1, 4);
        le(table, max, 4);
        le(table, data.size(), 4);
        if (it.is_num) {
            le(data, it.num, 4);
        } else {
            data.insert(data.end(), it.str.begin(), it.str.end());
            data.resize(data.size() + (max - it.str.size()), 0);
        }
    }
    while (keys.size() % 4) keys.push_back(0);
    std::vector<uint8_t> out = {0, 'P', 'S', 'F'};
    le(out, 0x0101, 4);
    const uint32_t ktab = 20 + uint32_t(table.size());
    le(out, ktab, 4);
    le(out, ktab + keys.size(), 4);
    le(out, items.size(), 4);
    out.insert(out.end(), table.begin(), table.end());
    out.insert(out.end(), keys.begin(), keys.end());
    out.insert(out.end(), data.begin(), data.end());
    return out;
}

}  // namespace gt6test

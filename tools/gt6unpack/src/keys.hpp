// Copyright (C) the RPCS3 project (https://github.com/RPCS3/rpcs3), licensed GPL-2.0.
// Adapted from RPCS3 (GPL-2.0), rpcs3/Crypto/key_vault.cpp, commit c365ea76a552961ff078ea1a46da9d4b07729674
// Public PS3 key material, kept in source per owner decision D15.
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace gt6 {

enum class SelfKeyType { App, Npdrm, Lv2, Isolated };

struct SelfKey {
    std::array<uint8_t, 32> erk;
    std::array<uint8_t, 16> riv;
    uint16_t revision;
};

// nullptr if unknown. Only App and Npdrm tables are populated.
const SelfKey* find_self_key(SelfKeyType type, uint16_t revision);

std::span<const uint8_t, 16> pkg_retail_key();
std::span<const uint8_t, 16> npdrm_klic_free();
std::span<const uint8_t, 16> npdrm_klic_key();

}  // namespace gt6

// SPDX-License-Identifier: GPL-2.0-only
// Copyright (C) the RPCS3 project (https://github.com/RPCS3/rpcs3), licensed GPL-2.0-only.
// Adapted from RPCS3 (GPL-2.0-only), rpcs3/Crypto/unpkg.cpp, commit c365ea76a552961ff078ea1a46da9d4b07729674
// Declarations follow rpcs3/Crypto/unpkg.h (same commit). Retail, finalized PS3 packages only.
#pragma once
#include "sfo.hpp"

#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

namespace gt6 {

class PkgError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct PkgEntry {
    std::string name;
    uint64_t offset;  // relative to the start of the encrypted data region
    uint64_t size;
    uint32_t type;    // raw entry type; low byte is the kind
    bool is_dir;
};

struct PkgInfo {
    std::string content_id;  // e.g. EP9001-BCES01977_00-0000000000000000-A0102-V0101-PE
    std::string title_id;    // e.g. BCES01977
    std::vector<PkgEntry> entries;
};

// Reads and validates the header and decrypts the file table (names included).
// Throws PkgError for anything that is not a retail PS3 package.
PkgInfo read_pkg(const std::filesystem::path& pkg);

// Decrypts every entry into dest (created if missing), streaming in 4 MiB chunks.
// Throws PkgError for entry names that are absolute or contain "." / ".." components.
void extract_pkg(const std::filesystem::path& pkg, const std::filesystem::path& dest);

// Decrypts and parses only PARAM.SFO. Throws PkgError if the package has none.
Sfo pkg_param_sfo(const std::filesystem::path& pkg);

}  // namespace gt6

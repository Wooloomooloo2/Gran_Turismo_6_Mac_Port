// Copyright (C) the RPCS3 project (https://github.com/RPCS3/rpcs3), licensed GPL-2.0.
// Adapted from RPCS3 (GPL-2.0), rpcs3/Crypto/unself.cpp, commit c365ea76a552961ff078ea1a46da9d4b07729674
// Declarations follow rpcs3/Crypto/unself.h (same commit).
// PS3 SELF/SPRX decryption to a plain ELF64.
#pragma once
#include <array>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace gt6 {

class SelfError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct SelfInfo {
    uint16_t key_revision;   // SCE header bytes 8-9
    uint16_t header_type;    // SCE header bytes 10-11 (1 = SELF)
    uint32_t program_type;   // 4 = application, 8 = NPDRM application
    bool npdrm;              // an NPDRM supplemental header is present
    uint32_t npdrm_license;  // 1 network, 2 local, 3 free; 0 when not NPDRM
    std::string content_id;  // NPDRM content ID; empty when not NPDRM
};

// Parses the plaintext SELF headers. Throws SelfError on non-"SCE\0" input, truncated
// headers, unsupported program types, and key revisions with no known key.
SelfInfo inspect_self(std::span<const uint8_t> self);

// A 16-byte NPDRM klicensee, as a game passes it to sceNpDrmIsAvailable.
using Klicensee = std::array<uint8_t, 16>;

// Decrypts a retail SELF/SPRX (application or free-licence NPDRM) into an ELF64.
// Every program segment's HMAC-SHA1 is checked against the metadata (D16); a mismatch throws
// SelfError("section N hash mismatch"). A free-licence NPDRM SELF is opened with `klic` when
// given, else with the public NP_KLIC_FREE (as RPCS3's decrypt_self(file, klic_key)); a wrong
// klicensee throws SelfError("failed to decrypt SELF metadata info (wrong key?)"). NPDRM
// licence types other than free throw SelfError("needs a licence file (paid content, out of scope)").
std::vector<uint8_t> decrypt_self(std::span<const uint8_t> self, const Klicensee* klic = nullptr);

}  // namespace gt6

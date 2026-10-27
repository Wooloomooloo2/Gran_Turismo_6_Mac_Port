// Finding a game's NPDRM klicensee in its own decrypted executable. No third-party code.
//
// GT6's update EBOOT.BIN keeps the klicensee it passes to sceNpDrmIsAvailable for EMAIN.SELF
// as the default of a "KeyLicensee" config entry: a "0x" + 32 hex digit string in its data
// segment (docs/FINDINGS.md). The key is never stored in this repository; the build looks for
// it in the player's own files and accepts a candidate only when it opens the SELF and every
// program segment HMAC matches.
#pragma once
#include "self.hpp"

#include <cstdint>
#include <span>
#include <vector>

namespace gt6 {

struct KlicCandidate {
    Klicensee key;
    uint64_t offset;  // where the "0x" string starts in the searched data
};

// Every "0x"/"0X" followed by exactly 32 hex digits (not part of a longer hex run), in order of
// first appearance, without duplicates or the all-zero value.
std::vector<KlicCandidate> klicensee_strings(std::span<const uint8_t> data);

}  // namespace gt6

// Test-only synthetic SELF writer (retail-style, public revision 0x001C keys). Output goes to
// memory or tmp dirs only; never commit it.
#pragma once
#include "doctest.h"
#include "crypto.hpp"
#include "keys.hpp"
#include "self.hpp"

#include <CommonCrypto/CommonCryptor.h>
#include <zlib.h>

#include <algorithm>
#include <cstdint>
#include <span>
#include <string_view>
#include <vector>

namespace gt6test {

using namespace gt6;
using Buf = std::vector<uint8_t>;

// ---- big-endian writers -------------------------------------------------
inline void put16(Buf& b, size_t off, uint16_t v) {
    for (int i = 0; i < 2; ++i) b[off + i] = static_cast<uint8_t>(v >> (8 * (1 - i)));
}
inline void put32(Buf& b, size_t off, uint32_t v) {
    for (int i = 0; i < 4; ++i) b[off + i] = static_cast<uint8_t>(v >> (8 * (3 - i)));
}
inline void put64(Buf& b, size_t off, uint64_t v) {
    for (int i = 0; i < 8; ++i) b[off + i] = static_cast<uint8_t>(v >> (8 * (7 - i)));
}
inline void put(Buf& b, size_t off, std::span<const uint8_t> src) {
    std::copy(src.begin(), src.end(), b.begin() + static_cast<std::ptrdiff_t>(off));
}
inline uint16_t get16(const Buf& b, size_t off) { return static_cast<uint16_t>(b[off] << 8 | b[off + 1]); }
inline uint32_t get32(const Buf& b, size_t off) {
    return uint32_t(b[off]) << 24 | uint32_t(b[off + 1]) << 16 | uint32_t(b[off + 2]) << 8 | b[off + 3];
}

// ---- independent crypto for building fixtures (CommonCrypto directly) ----
inline Buf cc(CCOperation op, CCOptions opts, std::span<const uint8_t> key, const uint8_t* iv,
       std::span<const uint8_t> data) {
    Buf out(data.size());
    size_t moved = 0;
    REQUIRE(CCCrypt(op, kCCAlgorithmAES, opts, key.data(), key.size(), iv, data.data(), data.size(),
                    out.data(), out.size(), &moved) == kCCSuccess);
    return out;
}
inline Buf cbc_encrypt(std::span<const uint8_t> key, std::span<const uint8_t> iv, std::span<const uint8_t> d) {
    return cc(kCCEncrypt, 0, key, iv.data(), d);
}
inline Buf ecb_decrypt(std::span<const uint8_t> key, std::span<const uint8_t> d) {
    return cc(kCCDecrypt, kCCOptionECBMode, key, nullptr, d);
}

inline Buf zcompress(const Buf& in) {
    uLongf len = compressBound(static_cast<uLong>(in.size()));
    Buf out(len);
    REQUIRE(compress2(out.data(), &len, in.data(), static_cast<uLong>(in.size()), 9) == Z_OK);
    out.resize(len);
    return out;
}

// ---- synthetic SELF fixture ---------------------------------------------
// A two-segment ELF64 (one plain segment, one zlib segment) plus two section headers,
// wrapped in a retail-style SELF encrypted with the public revision 0x001C keys.
struct Fixture {
    Buf elf;   // the expected decrypted ELF
    Buf self;  // the SELF built from it
};

inline constexpr size_t kElfSize = 0x580;
inline constexpr size_t kSeg0Off = 0x100, kSeg0Size = 0x80;
inline constexpr size_t kSeg1Off = 0x200, kSeg1Size = 0x300;
inline constexpr size_t kShOff = 0x500;

enum class Kind { App, NpdrmFree, NpdrmLocal };

// A game-supplied klicensee (what sceNpDrmIsAvailable receives); arbitrary test value.
inline const gt6::Klicensee kGameKlic = {0x10, 0x32, 0x54, 0x76, 0x98, 0xba, 0xdc, 0xfe,
                             0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef};

// `embed` is written into the second (zlib) segment, for tests that need known bytes in the ELF.
inline Buf make_elf(std::string_view embed = {}) {
    Buf e(kElfSize, 0);
    const uint8_t ident[] = {0x7f, 'E', 'L', 'F', 2, 2, 1, 0x66};
    put(e, 0, ident);
    put16(e, 0x10, 2);       // ET_EXEC
    put16(e, 0x12, 0x15);    // EM_PPC64
    put32(e, 0x14, 1);
    put64(e, 0x18, 0x10200); // entry
    put64(e, 0x20, 0x40);    // phoff
    put64(e, 0x28, kShOff);  // shoff
    put16(e, 0x34, 0x40);
    put16(e, 0x36, 0x38);
    put16(e, 0x38, 2);
    put16(e, 0x3A, 0x40);
    put16(e, 0x3C, 2);
    put16(e, 0x3E, 1);
    const size_t offs[2] = {kSeg0Off, kSeg1Off}, sizes[2] = {kSeg0Size, kSeg1Size};
    for (int i = 0; i < 2; ++i) {
        const size_t p = 0x40 + 0x38 * size_t(i);
        put32(e, p, 1);  // PT_LOAD
        put32(e, p + 4, i == 0 ? 5 : 6);
        put64(e, p + 8, offs[i]);
        put64(e, p + 0x10, 0x10000 + 0x10000 * uint64_t(i));
        put64(e, p + 0x18, 0x10000 + 0x10000 * uint64_t(i));
        put64(e, p + 0x20, sizes[i]);
        put64(e, p + 0x28, sizes[i] + 0x40);
        put64(e, p + 0x30, 0x10000);
    }
    for (size_t i = 0; i < kSeg0Size; ++i) e[kSeg0Off + i] = static_cast<uint8_t>(i * 7 + 3);
    for (size_t i = 0; i < kSeg1Size; ++i) e[kSeg1Off + i] = static_cast<uint8_t>((i / 16) ^ 0x5A);
    REQUIRE(embed.size() <= kSeg1Size - 0x10);
    std::copy(embed.begin(), embed.end(), e.begin() + kSeg1Off + 0x10);
    for (int i = 0; i < 2; ++i) {
        const size_t s = kShOff + 0x40 * size_t(i);
        put32(e, s, uint32_t(i));
        put32(e, s + 4, i == 0 ? 0 : 1);
        put64(e, s + 0x18, i == 0 ? 0 : kSeg0Off);
        put64(e, s + 0x20, i == 0 ? 0 : kSeg0Size);
    }
    return e;
}

inline Fixture make_fixture(Kind kind, const Klicensee* klic = nullptr, std::string_view embed = {}) {
    Fixture f;
    f.elf = make_elf(embed);
    const bool npdrm = kind != Kind::App;
    const SelfKey* key = find_self_key(npdrm ? SelfKeyType::Npdrm : SelfKeyType::App, 0x001C);
    REQUIRE(key != nullptr);

    // Segment plaintexts as stored in the SELF: seg0 plain, seg1 zlib.
    const Buf seg0(f.elf.begin() + kSeg0Off, f.elf.begin() + kSeg0Off + kSeg0Size);
    const Buf seg1 = zcompress(Buf(f.elf.begin() + kSeg1Off, f.elf.begin() + kSeg1Off + kSeg1Size));
    const Buf* segs[2] = {&seg0, &seg1};

    // Layout.
    constexpr size_t kExt = 0x20, kProg = 0x70, kEhdr = 0x90, kPhdr = 0xD0, kSegExt = 0x140,
                     kVer = 0x180, kSupp = 0x190;
    const size_t supp_size = npdrm ? 0x90 : 0x30;
    const size_t shdr_off = kSupp + supp_size;
    const size_t meta_info_off = shdr_off + 0x80;          // = se_meta + 0x20
    const size_t meta_hdr_off = meta_info_off + 0x40;
    const size_t key_count = 22;  // 8 per segment section, 6 for the section-header section
    const size_t hsize = meta_hdr_off + 0x20 + 3 * 0x30 + key_count * 16;
    const size_t data0 = (hsize + 0x7F) & ~size_t(0x7F);
    const size_t data1 = data0 + ((seg0.size() + 0xF) & ~size_t(0xF));
    const size_t datas[2] = {data0, data1};

    Buf& s = f.self;
    s.assign(data1 + seg1.size(), 0);
    put32(s, 0, 0x53434500);
    put32(s, 4, 2);
    put16(s, 8, 0x001C);
    put16(s, 10, 1);
    put32(s, 12, static_cast<uint32_t>(meta_info_off - 0x20));
    put64(s, 0x10, hsize);
    put64(s, 0x18, s.size() - hsize);
    // Extended header.
    put64(s, kExt, 3);
    put64(s, kExt + 0x08, kProg);
    put64(s, kExt + 0x10, kEhdr);
    put64(s, kExt + 0x18, kPhdr);
    put64(s, kExt + 0x20, shdr_off);
    put64(s, kExt + 0x28, kSegExt);
    put64(s, kExt + 0x30, kVer);
    put64(s, kExt + 0x38, kSupp);
    put64(s, kExt + 0x40, supp_size);
    // Program identification header.
    put64(s, kProg, 0x1010000001000003ULL);
    put32(s, kProg + 8, 0x01000002);
    put32(s, kProg + 12, npdrm ? 8 : 4);
    put64(s, kProg + 16, 0x0001000000000000ULL);
    // ELF header, program headers and section headers copied from the ELF.
    put(s, kEhdr, std::span(f.elf).subspan(0, 0x40));
    put(s, kPhdr, std::span(f.elf).subspan(0x40, 2 * 0x38));
    put(s, shdr_off, std::span(f.elf).subspan(kShOff, 0x80));
    // Segment extended headers.
    for (int i = 0; i < 2; ++i) {
        const size_t p = kSegExt + 0x20 * size_t(i);
        put64(s, p, datas[i]);
        put64(s, p + 8, segs[i]->size());
        put32(s, p + 16, i == 0 ? 1 : 2);
        put64(s, p + 24, 1);
    }
    // Version header.
    put32(s, kVer, 1);
    put32(s, kVer + 8, 0x10);
    // Supplemental header.
    if (npdrm) {
        put32(s, kSupp, 3);
        put32(s, kSupp + 4, 0x90);
        put32(s, kSupp + 0x10, 0x4E504400);  // "NPD\0"
        put32(s, kSupp + 0x14, 3);
        put32(s, kSupp + 0x18, kind == Kind::NpdrmFree ? 3 : 2);
        put32(s, kSupp + 0x1C, 0);
        const std::string cid = "EP9000-BCES01977_00-GRANTURISMO6000";
        put(s, kSupp + 0x20, std::span(reinterpret_cast<const uint8_t*>(cid.data()), cid.size()));
    } else {
        put32(s, kSupp, 1);
        put32(s, kSupp + 4, 0x30);
    }

    // Metadata: header, section headers, keys; encrypted with AES-128-CTR.
    Buf meta(hsize - meta_hdr_off, 0);
    put64(meta, 0, meta_hdr_off);  // signature input length (not used by decryption)
    put32(meta, 12, 3);
    put32(meta, 16, static_cast<uint32_t>(key_count));
    Buf keys(key_count * 16);
    for (size_t i = 0; i < keys.size(); ++i) keys[i] = static_cast<uint8_t>(i * 13 + 1);
    for (int i = 0; i < 2; ++i) {
        const size_t h = 0x20 + 0x30 * size_t(i);
        const uint32_t base = 8 * uint32_t(i);  // sha1 idx; hmac key = base+2..5, key = +6, iv = +7
        put64(meta, h, datas[i]);
        put64(meta, h + 8, segs[i]->size());
        put32(meta, h + 16, 2);
        put32(meta, h + 20, uint32_t(i));
        put32(meta, h + 24, 2);
        put32(meta, h + 28, base);
        put32(meta, h + 32, 3);
        put32(meta, h + 36, base + 6);
        put32(meta, h + 40, base + 7);
        put32(meta, h + 44, i == 0 ? 1 : 2);
        // HMAC-SHA1 of the decrypted, still-compressed section data.
        const auto hmac = crypto::hmac_sha1(std::span(keys).subspan(base * 16 + 32, 64), *segs[i]);
        std::fill_n(keys.begin() + base * 16, 32, 0);
        std::copy(hmac.begin(), hmac.end(), keys.begin() + base * 16);
        // Encrypt the section data.
        const auto ct = crypto::aes128_ctr(std::span(keys).subspan((base + 6) * 16, 16),
                                           std::span(keys).subspan((base + 7) * 16, 16), *segs[i]);
        put(s, datas[i], ct);
    }
    // Third section: the section header table, unencrypted, flagged hashed with a hash that
    // does not match (as on the real disc executables). It must be ignored.
    {
        const size_t h = 0x20 + 0x30 * 2;
        put64(meta, h, shdr_off);
        put64(meta, h + 8, 0x80);
        put32(meta, h + 16, 1);
        put32(meta, h + 20, 3);
        put32(meta, h + 24, 2);
        put32(meta, h + 28, 16);
        put32(meta, h + 32, 1);
        put32(meta, h + 36, 0xFFFFFFFF);
        put32(meta, h + 40, 0xFFFFFFFF);
        put32(meta, h + 44, 1);
        std::fill_n(keys.begin() + 16 * 16, 32, 0xEE);
    }
    put(meta, 0x20 + 3 * 0x30, keys);

    Buf mkey(16), miv(16);
    for (int i = 0; i < 16; ++i) { mkey[i] = uint8_t(0xA0 + i); miv[i] = uint8_t(0x30 + i); }
    put(s, meta_hdr_off, crypto::aes128_ctr(mkey, miv, meta));

    // Metadata info: key, pad, iv, pad; AES-256-CBC with erk/riv, then the NPDRM layer.
    Buf info(0x40, 0);
    put(info, 0, mkey);
    put(info, 0x20, miv);
    info = cbc_encrypt(key->erk, key->riv, info);
    if (npdrm) {
        const Buf npdrm_key = klic ? ecb_decrypt(npdrm_klic_key(), *klic) : ecb_decrypt(npdrm_klic_key(), npdrm_klic_free());
        info = cbc_encrypt(npdrm_key, Buf(16, 0), info);
    }
    put(s, meta_info_off, info);
    return f;
}

}  // namespace gt6test

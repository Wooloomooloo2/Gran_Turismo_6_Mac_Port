// Copyright (C) the RPCS3 project (https://github.com/RPCS3/rpcs3), licensed GPL-2.0.
// Adapted from RPCS3 (GPL-2.0), rpcs3/Crypto/unself.cpp, commit c365ea76a552961ff078ea1a46da9d4b07729674
// Port of SELFDecrypter (LoadHeaders, LoadMetadata, DecryptNPDRM, DecryptData, MakeElf) working
// on spans with exceptions. Differences from RPCS3: ELF64 retail SELFs only (no ELF32, no
// debug/fake SELFs); every bound is checked; program segment hashes are verified; each metadata
// section is decrypted on its own instead of through one shared buffer.
#include "self.hpp"

#include "crypto.hpp"
#include "keys.hpp"

#include <algorithm>
#include <array>
#include <cstdio>
#include <limits>

namespace gt6 {

namespace {

using Bytes = std::span<const uint8_t>;

constexpr uint32_t kSceMagic = 0x53434500;  // "SCE\0"
constexpr uint32_t kNpdMagic = 0x4E504400;  // "NPD\0"
constexpr size_t kSceHeaderSize = 0x20;
constexpr size_t kExtHeaderSize = 0x50;
constexpr size_t kMetaInfoSize = 0x40;
constexpr size_t kMetaHeaderSize = 0x20;
constexpr size_t kMetaSectionSize = 0x30;
constexpr size_t kEhdrSize = 0x40;
constexpr size_t kPhdrSize = 0x38;
constexpr size_t kShdrSize = 0x40;
constexpr size_t kSegExtSize = 0x20;

std::string hex16(uint32_t v) {
    char buf[16];
    std::snprintf(buf, sizeof buf, "0x%04X", v);
    return buf;
}

uint64_t add(uint64_t a, uint64_t b) {
    if (a > std::numeric_limits<uint64_t>::max() - b) throw SelfError("SELF offset overflow");
    return a + b;
}
uint64_t mul(uint64_t a, uint64_t b) {
    if (b != 0 && a > std::numeric_limits<uint64_t>::max() / b) throw SelfError("SELF size overflow");
    return a * b;
}

// Bounds-checked big-endian access to a byte span.
class Reader {
public:
    explicit Reader(Bytes d) : d_(d) {}
    Bytes slice(uint64_t off, uint64_t len, const char* what) const {
        if (off > d_.size() || len > d_.size() - off)
            throw SelfError(std::string("SELF truncated (") + what + ")");
        return d_.subspan(static_cast<size_t>(off), static_cast<size_t>(len));
    }
    uint16_t u16(uint64_t off, const char* what) const { return static_cast<uint16_t>(be(off, 2, what)); }
    uint32_t u32(uint64_t off, const char* what) const { return static_cast<uint32_t>(be(off, 4, what)); }
    uint64_t u64(uint64_t off, const char* what) const { return be(off, 8, what); }
    size_t size() const { return d_.size(); }

private:
    uint64_t be(uint64_t off, size_t n, const char* what) const {
        uint64_t v = 0;
        for (uint8_t b : slice(off, n, what)) v = v << 8 | b;
        return v;
    }
    Bytes d_;
};

struct Phdr {
    uint64_t offset;
    uint64_t filesz;
};

struct Headers {
    // SCE header.
    uint16_t key_revision;
    uint16_t header_type;
    uint32_t meta_offset;
    uint64_t header_size;
    // Extended header offsets.
    uint64_t ehdr_offset;
    uint64_t phdr_offset;
    uint64_t shdr_offset;
    // Program identification.
    uint32_t program_type;
    // ELF header fields.
    uint64_t e_phoff;
    uint64_t e_shoff;
    uint16_t e_phnum;
    uint16_t e_shnum;
    std::vector<Phdr> phdrs;
    // NPDRM supplemental header.
    bool npdrm = false;
    uint32_t npdrm_license = 0;
    std::string content_id;
    const SelfKey* key = nullptr;
};

// SELFDecrypter::LoadHeaders, plus key lookup (KeyVault::FindSelfKey).
Headers load_headers(const Reader& r) {
    Headers h{};
    if (r.size() < 4 || r.u32(0, "SCE header") != kSceMagic) throw SelfError("not a SELF (no SCE magic)");
    h.key_revision = r.u16(8, "SCE header");
    h.header_type = r.u16(10, "SCE header");
    h.meta_offset = r.u32(12, "SCE header");
    h.header_size = r.u64(16, "SCE header");
    if (h.header_type != 1) throw SelfError("not a SELF (SCE header type " + std::to_string(h.header_type) + ")");
    if (h.key_revision & 0x8000) throw SelfError("debug/fake SELFs are not supported");

    const uint64_t ext = kSceHeaderSize;
    r.slice(ext, kExtHeaderSize, "extended header");
    const uint64_t prog_offset = r.u64(ext + 0x08, "extended header");
    h.ehdr_offset = r.u64(ext + 0x10, "extended header");
    h.phdr_offset = r.u64(ext + 0x18, "extended header");
    h.shdr_offset = r.u64(ext + 0x20, "extended header");
    const uint64_t segext_offset = r.u64(ext + 0x28, "extended header");
    const uint64_t supp_offset = r.u64(ext + 0x38, "extended header");
    const uint64_t supp_size = r.u64(ext + 0x40, "extended header");

    h.program_type = r.u32(add(prog_offset, 12), "program identification header");

    const Bytes ehdr = r.slice(h.ehdr_offset, kEhdrSize, "ELF header");
    if (ehdr[0] != 0x7f || ehdr[1] != 'E' || ehdr[2] != 'L' || ehdr[3] != 'F')
        throw SelfError("embedded ELF header has no ELF magic");
    if (ehdr[4] != 2) throw SelfError("only ELF64 SELFs are supported");
    h.e_phoff = r.u64(h.ehdr_offset + 0x20, "ELF header");
    h.e_shoff = r.u64(h.ehdr_offset + 0x28, "ELF header");
    const uint16_t phentsize = r.u16(h.ehdr_offset + 0x36, "ELF header");
    h.e_phnum = r.u16(h.ehdr_offset + 0x38, "ELF header");
    const uint16_t shentsize = r.u16(h.ehdr_offset + 0x3A, "ELF header");
    h.e_shnum = r.u16(h.ehdr_offset + 0x3C, "ELF header");
    if (h.e_phnum && (h.e_phoff == 0 || phentsize != kPhdrSize)) throw SelfError("bad ELF program header table");
    if (h.e_shnum && h.e_shoff != 0 && shentsize != kShdrSize) throw SelfError("bad ELF section header table");

    for (uint16_t i = 0; i < h.e_phnum; ++i) {
        const uint64_t p = add(h.phdr_offset, mul(i, kPhdrSize));
        r.slice(p, kPhdrSize, "ELF program headers");
        h.phdrs.push_back({r.u64(p + 0x08, ""), r.u64(p + 0x20, "")});
    }
    // Segment extended headers are not needed to decrypt a retail SELF, but RPCS3
    // rejects files whose table runs past the end; keep that check.
    r.slice(segext_offset, mul(h.e_phnum, kSegExtSize), "segment extended headers");

    // Supplemental headers (RPCS3 "control info"); only the NPDRM one matters here.
    for (uint64_t i = 0; i < supp_size;) {
        const uint64_t p = add(supp_offset, i);
        const uint32_t type = r.u32(p, "supplemental header");
        const uint32_t size = r.u32(p + 4, "supplemental header");
        if (size == 0) throw SelfError("supplemental header of size 0");
        r.slice(p, size, "supplemental header");
        if (type == 3) {
            if (size < 0x90) throw SelfError("NPDRM supplemental header too small");
            const uint64_t npd = p + 0x10;
            if (r.u32(npd, "NPD header") != kNpdMagic) throw SelfError("NPDRM header has no NPD magic");
            h.npdrm = true;
            h.npdrm_license = r.u32(npd + 0x08, "NPD header");
            const Bytes cid = r.slice(npd + 0x10, 0x30, "NPD header");
            h.content_id.assign(cid.begin(), std::find(cid.begin(), cid.end(), uint8_t{0}));
        }
        i = add(i, size);
    }

    SelfKeyType key_type;
    switch (h.program_type) {
        case 4: key_type = SelfKeyType::App; break;
        case 8: key_type = SelfKeyType::Npdrm; break;
        default: throw SelfError("unsupported SELF program type " + std::to_string(h.program_type));
    }
    h.key = find_self_key(key_type, h.key_revision);
    if (!h.key)
        throw SelfError("no key for SELF key revision " + hex16(h.key_revision) + " (program type " +
                        std::to_string(h.program_type) + ")");
    return h;
}

struct Section {
    uint64_t data_offset;
    uint64_t data_size;
    uint32_t type;  // 2 = program segment
    uint32_t program_idx;
    uint32_t hashed;  // 2 = hashed
    uint32_t sha1_idx;
    uint32_t encrypted;  // 3 = AES-128-CTR
    uint32_t key_idx;
    uint32_t iv_idx;
    uint32_t compressed;  // 2 = zlib
};

struct Metadata {
    std::vector<Section> sections;
    std::vector<uint8_t> keys;  // key_count * 16 bytes
};

// SELFDecrypter::DecryptNPDRM: strips the NPDRM layer from the metadata info.
std::vector<uint8_t> decrypt_npdrm(const Headers& h, Bytes info) {
    if (h.npdrm_license == 1 || h.npdrm_license == 2)
        throw SelfError("needs a licence file (paid content, out of scope)");
    if (h.npdrm_license != 3) throw SelfError("invalid NPDRM licence type " + std::to_string(h.npdrm_license));
    const std::array<uint8_t, 16> zero_iv{};
    // ECB-decrypt the free klicensee with NP_KLIC_KEY (one CBC block with a zero IV is ECB).
    const auto npdrm_key = crypto::aes_cbc_decrypt(npdrm_klic_key(), zero_iv, npdrm_klic_free());
    return crypto::aes_cbc_decrypt(npdrm_key, zero_iv, info);
}

// SELFDecrypter::LoadMetadata (retail path).
Metadata load_metadata(const Reader& r, const Headers& h) {
    const uint64_t info_off = add(h.meta_offset, kSceHeaderSize);
    const uint64_t headers_off = add(info_off, kMetaInfoSize);
    if (h.header_size > r.size() || add(headers_off, kMetaHeaderSize) > h.header_size)
        throw SelfError("invalid SELF metadata header size");

    const Bytes raw_info = r.slice(info_off, kMetaInfoSize, "metadata info");
    std::vector<uint8_t> info(raw_info.begin(), raw_info.end());
    if (h.npdrm) info = decrypt_npdrm(h, info);
    info = crypto::aes_cbc_decrypt(h.key->erk, h.key->riv, info);
    // Layout: key[16], key_pad[16], iv[16], iv_pad[16]. Non-zero padding means a wrong key.
    const auto zero = [](auto first, auto last) { return std::all_of(first, last, [](uint8_t b) { return b == 0; }); };
    if (!zero(info.begin() + 0x10, info.begin() + 0x20) || !zero(info.begin() + 0x30, info.end()))
        throw SelfError("failed to decrypt SELF metadata info (wrong key?)");

    const Bytes meta_key = Bytes(info).subspan(0x00, 16);
    const Bytes meta_iv = Bytes(info).subspan(0x20, 16);
    const auto hdrs = crypto::aes128_ctr(meta_key, meta_iv,
                                         r.slice(headers_off, h.header_size - headers_off, "metadata headers"));
    const Reader m(hdrs);
    const uint32_t section_count = m.u32(12, "metadata header");
    const uint32_t key_count = m.u32(16, "metadata header");
    const uint64_t keys_off = add(kMetaHeaderSize, mul(section_count, kMetaSectionSize));

    Metadata md;
    for (uint32_t i = 0; i < section_count; ++i) {
        const uint64_t p = kMetaHeaderSize + uint64_t(i) * kMetaSectionSize;
        m.slice(p, kMetaSectionSize, "metadata section headers");
        md.sections.push_back({m.u64(p, ""), m.u64(p + 8, ""), m.u32(p + 16, ""), m.u32(p + 20, ""),
                               m.u32(p + 24, ""), m.u32(p + 28, ""), m.u32(p + 32, ""), m.u32(p + 36, ""),
                               m.u32(p + 40, ""), m.u32(p + 44, "")});
    }
    const Bytes keys = m.slice(keys_off, mul(key_count, 16), "metadata keys");
    md.keys.assign(keys.begin(), keys.end());
    return md;
}

Bytes key_slot(const Metadata& md, uint64_t idx, uint64_t len, const std::string& sec) {
    const uint64_t off = mul(idx, 16);
    if (off > md.keys.size() || len > md.keys.size() - off) throw SelfError(sec + " key index out of range");
    return Bytes(md.keys).subspan(static_cast<size_t>(off), static_cast<size_t>(len));
}

// SELFDecrypter::DecryptData for one program segment (type 2) section, plus the hash check
// RPCS3 omits. The 96-byte hash slot at sha1_idx is SHA-1[20], padding[12], HMAC key[64]
// (RPCS3 SectionHash). The HMAC-SHA1 covers the decrypted data as stored, still compressed;
// confirmed on the real GT6 disc executables. The other hashed sections in those files
// (type 1 = section header table, type 3 = SCE version data; both stored unencrypted) do not
// match HMAC-SHA1 of their bytes under any coverage tried (see docs/FINDINGS.md), so they are
// not decrypted or checked; the caller skips them, as RPCS3 does.
std::vector<uint8_t> decrypt_section(const Reader& r, const Metadata& md, const Section& s, size_t n) {
    const std::string sec = "section " + std::to_string(n);
    const Bytes stored = r.slice(s.data_offset, s.data_size, "section data");
    std::vector<uint8_t> data;
    if (s.encrypted == 3)
        data = crypto::aes128_ctr(key_slot(md, s.key_idx, 16, sec), key_slot(md, s.iv_idx, 16, sec), stored);
    else if (s.encrypted == 1)
        data.assign(stored.begin(), stored.end());
    else
        throw SelfError(sec + ": unknown encryption flag " + std::to_string(s.encrypted));

    if (s.hashed == 2) {
        const Bytes slot = key_slot(md, s.sha1_idx, 0x60, sec);
        const auto mac = crypto::hmac_sha1(slot.subspan(0x20, 0x40), data);
        if (!std::equal(mac.begin(), mac.end(), slot.begin())) throw SelfError(sec + " hash mismatch");
    } else if (s.hashed != 1) {
        throw SelfError(sec + ": unknown hash flag " + std::to_string(s.hashed));
    }
    return data;
}

void write_at(std::vector<uint8_t>& out, uint64_t off, Bytes src) {
    const uint64_t end = add(off, src.size());
    if (end > out.size()) out.resize(static_cast<size_t>(end), 0);
    std::copy(src.begin(), src.end(), out.begin() + static_cast<std::ptrdiff_t>(off));
}

}  // namespace

SelfInfo inspect_self(std::span<const uint8_t> self) {
    const Headers h = load_headers(Reader(self));
    return {h.key_revision, h.header_type, h.program_type, h.npdrm, h.npdrm_license, h.content_id};
}

std::vector<uint8_t> decrypt_self(std::span<const uint8_t> self) {
    const Reader r(self);
    const Headers h = load_headers(r);
    const Metadata md = load_metadata(r, h);

    // SELFDecrypter::MakeElf / WriteElf.
    std::vector<uint8_t> elf;
    write_at(elf, 0, r.slice(h.ehdr_offset, kEhdrSize, "ELF header"));

    for (size_t n = 0; n < md.sections.size(); ++n) {
        const Section& s = md.sections[n];
        // Only program segments go into the ELF; RPCS3 also ignores the other section types.
        if (s.type != 2) continue;
        const std::vector<uint8_t> data = decrypt_section(r, md, s, n);
        if (s.program_idx >= h.phdrs.size())
            throw SelfError("section " + std::to_string(n) + ": program index out of range");
        const Phdr& ph = h.phdrs[s.program_idx];
        if (s.compressed == 2) {
            try {
                write_at(elf, ph.offset, crypto::inflate_zlib(data, static_cast<size_t>(ph.filesz)));
            } catch (const SelfError&) {
                throw;
            } catch (const std::runtime_error& e) {
                throw SelfError("section " + std::to_string(n) + ": " + e.what());
            }
        } else {
            write_at(elf, ph.offset, data);
        }
    }

    if (h.shdr_offset != 0 && h.e_shoff != 0)
        write_at(elf, h.e_shoff, r.slice(h.shdr_offset, mul(h.e_shnum, kShdrSize), "ELF section headers"));
    // Program headers go last so segment data cannot overwrite them (as in RPCS3).
    if (h.e_phnum)
        write_at(elf, h.e_phoff, r.slice(h.phdr_offset, mul(h.e_phnum, kPhdrSize), "ELF program headers"));
    return elf;
}

}  // namespace gt6

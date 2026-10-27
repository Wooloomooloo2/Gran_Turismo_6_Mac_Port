// SPDX-License-Identifier: GPL-2.0-only
// Copyright (C) the RPCS3 project (https://github.com/RPCS3/rpcs3), licensed GPL-2.0-only.
// Adapted from RPCS3 (GPL-2.0-only), rpcs3/Crypto/unpkg.cpp, commit c365ea76a552961ff078ea1a46da9d4b07729674
// Header/entry layout, validation rules and the CTR-style keystream (AES-128-ECB of
// klicensee + block index, keyed with the retail PKG key) follow package_reader there.
// Retail finalized PS3 packages only; debug, PSP and Vita paths are out of scope.
#include "pkg.hpp"

#include "crypto.hpp"
#include "keys.hpp"

#include <algorithm>
#include <array>
#include <cstring>
#include <fstream>
#include <string_view>

namespace gt6 {
namespace {

namespace fs = std::filesystem;

constexpr size_t kHeaderSize = 0x80;      // fields we read end at klicensee (0x70..0x80)
constexpr size_t kEntrySize = 32;
constexpr uint32_t kMaxFilenameSize = 256;
constexpr uint32_t kMaxFileCount = 0x7FFFFFFF;
constexpr size_t kChunk = 4u << 20;       // 4 MiB streaming chunk
constexpr uint64_t kMaxSfoSize = 1u << 20;

constexpr uint16_t kReleaseRetail = 0x8000;
constexpr uint16_t kPlatformPs3 = 0x0001;

// Entry kinds (low byte of the entry type), per unpkg.h PKG_FILE_ENTRY_*.
constexpr uint32_t kKindFolder = 4;
constexpr uint32_t kKindFolderAlt = 0x12;
constexpr uint32_t kEntryPsp = 0x10000000;

uint64_t be(const uint8_t* p, int n) {
    uint64_t v = 0;
    for (int i = 0; i < n; ++i) v = v << 8 | p[i];
    return v;
}

// iv += v as 128-bit big-endian integers (wrapping).
void add_be128(std::array<uint8_t, 16>& iv, uint64_t v) {
    for (int i = 15; i >= 0 && v; --i) {
        v += iv[i];
        iv[i] = uint8_t(v);
        v >>= 8;
    }
}

// AES-CTR with a full 128-bit big-endian counter. CommonCrypto's counter may wrap within the
// low 64 bits, so split the data where those bits would roll over and restart with an
// explicitly carried IV, as RPCS3's u128 increment does.
std::vector<uint8_t> ctr128(std::array<uint8_t, 16> iv, std::span<const uint8_t> data) {
    std::vector<uint8_t> out;
    out.reserve(data.size());
    size_t pos = 0;
    while (pos < data.size()) {
        const uint64_t low = be(iv.data() + 8, 8);
        const uint64_t blocks_to_wrap = low == 0 ? UINT64_MAX : (0 - low);  // blocks before low wraps
        const uint64_t seg_blocks = std::min<uint64_t>(blocks_to_wrap, (data.size() - pos + 15) / 16);
        const size_t seg = size_t(std::min<uint64_t>(data.size() - pos, seg_blocks * 16));
        auto part = crypto::aes128_ctr(pkg_retail_key(), iv, data.subspan(pos, seg));
        out.insert(out.end(), part.begin(), part.end());
        pos += seg;
        add_be128(iv, seg_blocks);
    }
    return out;
}

struct Header {
    uint32_t file_count;
    uint64_t pkg_size, data_offset, data_size;
    std::string content_id;
    std::array<uint8_t, 16> klicensee;
};

// Random-access decrypting reader over the package's data region.
class Reader {
public:
    explicit Reader(const fs::path& p) : f_(p, std::ios::binary) {
        if (!f_) throw PkgError("cannot open " + p.string());
        f_.seekg(0, std::ios::end);
        file_size_ = uint64_t(f_.tellg());
        parse_header();
    }

    const Header& header() const { return h_; }

    // Reads n plaintext bytes at `off` within the data region.
    void read(uint64_t off, uint8_t* out, size_t n) {
        if (n == 0) return;
        if (off > h_.data_size || h_.data_size - off < n) throw PkgError("read past end of package data");
        const size_t prefix = size_t(off & 15);
        scratch_.assign(prefix + n, 0);
        f_.seekg(std::streamoff(h_.data_offset + off));
        f_.read(reinterpret_cast<char*>(scratch_.data() + prefix), std::streamsize(n));
        if (size_t(f_.gcount()) != n) throw PkgError("package is truncated");
        // Counter = klicensee + block index, 128-bit big-endian.
        std::array<uint8_t, 16> iv = h_.klicensee;
        add_be128(iv, off / 16);
        auto dec = ctr128(iv, scratch_);
        std::memcpy(out, dec.data() + prefix, n);
    }

private:
    void parse_header() {
        uint8_t b[kHeaderSize];
        f_.seekg(0);
        f_.read(reinterpret_cast<char*>(b), sizeof b);
        if (size_t(f_.gcount()) != sizeof b) throw PkgError("file too short to be a package");
        if (std::memcmp(b, "\x7f" "PKG", 4) != 0) throw PkgError("not a PKG file");
        if (be(b + 4, 2) != kReleaseRetail) throw PkgError("only retail packages are supported");
        if (be(b + 6, 2) != kPlatformPs3) throw PkgError("only PS3 packages are supported");
        h_.file_count = uint32_t(be(b + 20, 4));
        h_.pkg_size = be(b + 24, 8);
        h_.data_offset = be(b + 32, 8);
        h_.data_size = be(b + 40, 8);
        const char* id = reinterpret_cast<const char*>(b + 48);
        h_.content_id.assign(id, strnlen(id, 48));
        std::memcpy(h_.klicensee.data(), b + 0x70, 16);

        if (h_.file_count > kMaxFileCount || uint64_t(h_.file_count) > h_.data_size / kEntrySize)
            throw PkgError("invalid file count");
        if (h_.pkg_size > file_size_) throw PkgError("package is truncated (size mismatch)");
        if (h_.data_offset > h_.pkg_size || h_.data_size > h_.pkg_size - h_.data_offset)
            throw PkgError("data region exceeds package size");
    }

    std::ifstream f_;
    uint64_t file_size_ = 0;
    Header h_{};
    std::vector<uint8_t> scratch_;
};

// A name that could reach outside the directory it is joined to: a leading "/", a NUL, a
// backslash, or a "." / ".." component.
bool leaves_directory(std::string_view name) {
    if (name.starts_with('/')) return true;
    if (name.find('\0') != std::string_view::npos || name.find('\\') != std::string_view::npos) return true;
    for (std::string_view rest = name; !rest.empty();) {
        const size_t sep = rest.find('/');
        const std::string_view c = rest.substr(0, sep);
        rest = sep == std::string_view::npos ? std::string_view{} : rest.substr(sep + 1);
        if (c == "." || c == "..") return true;
    }
    return false;
}

PkgInfo read_info(Reader& r) {
    const Header& h = r.header();
    PkgInfo info;
    info.content_id = h.content_id;
    // Title ID is the 9 characters at file offset 55 (content ID bytes 7..16).
    if (info.content_id.size() >= 16) info.title_id = info.content_id.substr(7, 9);

    std::vector<uint8_t> table(size_t(h.file_count) * kEntrySize);
    r.read(0, table.data(), table.size());

    for (uint32_t i = 0; i < h.file_count; ++i) {
        const uint8_t* e = table.data() + size_t(i) * kEntrySize;
        const uint64_t name_off = be(e, 4), name_size = be(e + 4, 4);
        const uint64_t off = be(e + 8, 8), size = be(e + 16, 8);
        const uint32_t type = uint32_t(be(e + 24, 4));

        if (type & kEntryPsp) throw PkgError("PSP package entries are not supported");
        if (name_size == 0 || name_size > kMaxFilenameSize) throw PkgError("invalid entry name size");
        if (name_off > h.data_size || h.data_size - name_off < name_size)
            throw PkgError("entry name exceeds package data");
        if (off > h.data_size || h.data_size - off < size) throw PkgError("entry data exceeds package data");

        const uint32_t kind = type & 0xff;
        const bool is_dir = kind == kKindFolder || kind == kKindFolderAlt;
        switch (kind) {
            case 1: case 2: case 3: case 5: case 6: case 9: case kKindFolder: case kKindFolderAlt: break;
            default: throw PkgError("unknown entry type " + std::to_string(kind));
        }

        std::string name(name_size, '\0');
        r.read(name_off, reinterpret_cast<uint8_t*>(name.data()), name.size());
        while (!name.empty() && name.back() == '\0') name.pop_back();
        info.entries.push_back({std::move(name), off, size, type, is_dir});
    }
    return info;
}

}  // namespace

PkgInfo read_pkg(const fs::path& pkg) {
    Reader r(pkg);
    return read_info(r);
}

void extract_pkg(const fs::path& pkg, const fs::path& dest) {
    Reader r(pkg);
    const PkgInfo info = read_info(r);
    // Validate every name before touching the disk.
    for (const auto& e : info.entries)
        if (leaves_directory(e.name)) throw PkgError("entry name escapes destination: " + e.name);

    fs::create_directories(dest);
    std::vector<uint8_t> buf(kChunk);
    for (const auto& e : info.entries) {
        const fs::path target = dest / e.name;
        if (e.is_dir) {
            fs::create_directories(target);
            continue;
        }
        fs::create_directories(target.parent_path());
        std::ofstream out(target, std::ios::binary | std::ios::trunc);
        if (!out) throw PkgError("cannot create " + target.string());
        for (uint64_t pos = 0; pos < e.size;) {
            const size_t n = size_t(std::min<uint64_t>(kChunk, e.size - pos));
            r.read(e.offset + pos, buf.data(), n);
            out.write(reinterpret_cast<const char*>(buf.data()), std::streamsize(n));
            pos += n;
        }
        out.close();
        if (!out) throw PkgError("write failed for " + target.string());
    }
}

Sfo pkg_param_sfo(const fs::path& pkg) {
    Reader r(pkg);
    const PkgInfo info = read_info(r);
    for (const auto& e : info.entries) {
        if (e.is_dir) continue;
        const size_t skip = e.name.find_first_not_of('/');
        if (skip == std::string::npos || e.name.substr(skip) != "PARAM.SFO") continue;
        if (e.size > kMaxSfoSize) throw PkgError("PARAM.SFO is implausibly large");
        std::vector<uint8_t> data(size_t(e.size));
        r.read(e.offset, data.data(), data.size());
        try {
            return parse_sfo(data);
        } catch (const SfoError& ex) {
            throw PkgError(std::string("bad PARAM.SFO: ") + ex.what());
        }
    }
    throw PkgError("package has no PARAM.SFO");
}

}  // namespace gt6

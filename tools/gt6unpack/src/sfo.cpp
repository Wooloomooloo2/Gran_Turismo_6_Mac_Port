// PARAM.SFO parser. Format per the public PS3 developer wiki; no third-party code.
#include "sfo.hpp"

#include <cstring>

namespace gt6 {
namespace {

uint32_t rd32(std::span<const uint8_t> d, size_t off) {
    if (off > d.size() || d.size() - off < 4) throw SfoError("SFO truncated");
    return uint32_t(d[off]) | uint32_t(d[off + 1]) << 8 | uint32_t(d[off + 2]) << 16 |
           uint32_t(d[off + 3]) << 24;
}
uint16_t rd16(std::span<const uint8_t> d, size_t off) {
    if (off > d.size() || d.size() - off < 2) throw SfoError("SFO truncated");
    return uint16_t(d[off] | d[off + 1] << 8);
}

}  // namespace

Sfo parse_sfo(std::span<const uint8_t> d) {
    if (d.size() < 20 || std::memcmp(d.data(), "\0PSF", 4) != 0) throw SfoError("not a PARAM.SFO");
    const uint64_t key_table = rd32(d, 8);
    const uint64_t data_table = rd32(d, 12);
    const uint32_t count = rd32(d, 16);
    if (count > (d.size() - 20) / 16) throw SfoError("SFO entry count exceeds file size");

    Sfo out;
    for (uint32_t i = 0; i < count; ++i) {
        const size_t e = 20 + size_t(i) * 16;
        const uint64_t koff = key_table + rd16(d, e);
        const uint16_t fmt = rd16(d, e + 2);
        const uint32_t len = rd32(d, e + 4);
        const uint64_t doff = data_table + rd32(d, e + 12);

        if (koff >= d.size()) throw SfoError("SFO key offset out of range");
        const auto* kb = d.data() + koff;
        const size_t kmax = d.size() - koff;
        const size_t klen = strnlen(reinterpret_cast<const char*>(kb), kmax);
        if (klen == kmax) throw SfoError("SFO key not terminated");
        std::string key(reinterpret_cast<const char*>(kb), klen);

        if (doff > d.size() || d.size() - doff < len) throw SfoError("SFO data out of range");
        const uint8_t* p = d.data() + doff;
        if (fmt == 0x0404) {
            if (len != 4) throw SfoError("SFO integer entry must be 4 bytes");
            out[key] = rd32(d, size_t(doff));
        } else if (fmt == 0x0004 || fmt == 0x0204) {
            size_t n = len;
            while (n > 0 && p[n - 1] == 0) --n;
            out[key] = std::string(reinterpret_cast<const char*>(p), n);
        } else {
            throw SfoError("SFO entry has unknown format");
        }
    }
    return out;
}

}  // namespace gt6

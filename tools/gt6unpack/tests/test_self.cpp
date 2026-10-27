// SPDX-License-Identifier: GPL-2.0-only
#include "doctest.h"
#include "crypto.hpp"
#include "keys.hpp"
#include "self.hpp"
#include "self_builder.hpp"
#include "test_env.hpp"

#include <CommonCrypto/CommonCryptor.h>
#include <zlib.h>

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

using namespace gt6;
using namespace gt6test;

namespace {

std::string message_of(std::span<const uint8_t> self) {
    try {
        decrypt_self(self);
    } catch (const SelfError& e) {
        return e.what();
    }
    return "<no SelfError>";
}

Buf read_file(const std::filesystem::path& p) {
    std::ifstream in(p, std::ios::binary);
    REQUIRE(in.good());
    return Buf(std::istreambuf_iterator<char>(in), {});
}

}  // namespace

TEST_CASE("inspect_self rejects a plain ELF") {
    Buf elf = make_elf();
    CHECK_THROWS_AS(inspect_self(elf), SelfError);
    CHECK_THROWS_AS(decrypt_self(elf), SelfError);
}

TEST_CASE("inspect_self names an unknown key revision") {
    Buf s = make_fixture(Kind::App).self;
    put16(s, 8, 0x7FFF);
    try {
        inspect_self(s);
        FAIL("expected SelfError");
    } catch (const SelfError& e) {
        CHECK(std::string(e.what()).find("0x7FFF") != std::string::npos);
    }
    CHECK(message_of(s).find("0x7FFF") != std::string::npos);
}

TEST_CASE("inspect_self rejects truncated headers") {
    const Buf s = make_fixture(Kind::App).self;
    CHECK_THROWS_AS(inspect_self(std::span(s).subspan(0, 0x30)), SelfError);
    CHECK_THROWS_AS(decrypt_self(std::span(s).subspan(0, 0x300)), SelfError);
}

TEST_CASE("inspect_self reports application SELF fields") {
    const SelfInfo i = inspect_self(make_fixture(Kind::App).self);
    CHECK(i.key_revision == 0x001C);
    CHECK(i.header_type == 1);
    CHECK(i.program_type == 4);
    CHECK_FALSE(i.npdrm);
    CHECK(i.npdrm_license == 0);
    CHECK(i.content_id.empty());
}

TEST_CASE("decrypt_self rebuilds the exact ELF from an application SELF") {
    const Fixture f = make_fixture(Kind::App);
    CHECK(decrypt_self(f.self) == f.elf);
}

TEST_CASE("decrypt_self handles free-licence NPDRM") {
    const Fixture f = make_fixture(Kind::NpdrmFree);
    const SelfInfo i = inspect_self(f.self);
    CHECK(i.program_type == 8);
    CHECK(i.npdrm);
    CHECK(i.npdrm_license == 3);
    CHECK(i.content_id == "EP9000-BCES01977_00-GRANTURISMO6000");
    CHECK(decrypt_self(f.self) == f.elf);
}

TEST_CASE("decrypt_self opens free-licence NPDRM with a game-supplied klicensee") {
    // As RPCS3 decrypt_self(file, klic_key): the given klicensee replaces NP_KLIC_FREE.
    const Fixture f = make_fixture(Kind::NpdrmFree, &kGameKlic);
    CHECK_THROWS_WITH_AS(decrypt_self(f.self), doctest::Contains("wrong key"), SelfError);
    CHECK(decrypt_self(f.self, &kGameKlic) == f.elf);
    const Fixture plain = make_fixture(Kind::NpdrmFree);
    CHECK_THROWS_AS(decrypt_self(plain.self, &kGameKlic), SelfError);
}

TEST_CASE("decrypt_self refuses paid NPDRM licences") {
    const Fixture f = make_fixture(Kind::NpdrmLocal);
    CHECK(inspect_self(f.self).npdrm_license == 2);
    CHECK(message_of(f.self) == "needs a licence file (paid content, out of scope)");
}

TEST_CASE("decrypt_self detects tampered section data") {
    for (int section = 0; section < 2; ++section) {
        Buf s = make_fixture(Kind::App).self;
        const size_t seg_ext = 0x140 + 0x20 * size_t(section);
        uint64_t off = 0;
        for (int b = 0; b < 8; ++b) off = off << 8 | s[seg_ext + size_t(b)];
        s[off + 5] ^= 0x01;
        CHECK(message_of(s) == "section " + std::to_string(section) + " hash mismatch");
    }
}

TEST_CASE("decrypt_self detects a wrong metadata key") {
    Buf s = make_fixture(Kind::App).self;
    const size_t meta_info_off = get32(s, 12) + 0x20;
    s[meta_info_off + 0x3F] ^= 0x80;  // corrupts the decrypted iv padding
    CHECK_THROWS_AS(decrypt_self(s), SelfError);
}

namespace {
std::string hex_of(std::span<const uint8_t> b) {
    static const char* hx = "0123456789abcdef";
    std::string out;
    for (uint8_t c : b) { out += hx[c >> 4]; out += hx[c & 15]; }
    return out;
}

// expected_sha256: the ELF RPCS3 c365ea76 produces from the same file (docs/FINDINGS.md).
void check_disc_executable(const char* name, const char* expected_sha256) {
    const auto disc = require_env("GT6_DISC_DIR");
    const Buf self = read_file(disc / "PS3_GAME" / "USRDIR" / name);
    const SelfInfo info = inspect_self(self);
    CHECK(info.key_revision == 0x001C);
    CHECK(info.program_type == 4);

    const Buf elf = decrypt_self(self);
    REQUIRE(elf.size() >= 0x40);
    const uint8_t magic[] = {0x7f, 0x45, 0x4c, 0x46, 0x02, 0x02};
    CHECK(std::equal(std::begin(magic), std::end(magic), elf.begin()));
    CHECK(get16(elf, 0x12) == 0x15);
    uint64_t phoff = 0;
    for (int b = 0; b < 8; ++b) phoff = phoff << 8 | elf[0x20 + size_t(b)];
    const uint16_t phnum = get16(elf, 0x38);
    REQUIRE(phoff + size_t(phnum) * 0x38 <= elf.size());
    int loads = 0;
    for (uint16_t i = 0; i < phnum; ++i)
        if (get32(elf, phoff + size_t(i) * 0x38) == 1) ++loads;
    CHECK(loads >= 1);

    CHECK(crypto::sha256(decrypt_self(self)) == crypto::sha256(elf));
    CHECK(hex_of(crypto::sha256(elf)) == expected_sha256);
}
}  // namespace

TEST_CASE("integration: decrypt disc EMAIN.SELF" * needs_env("GT6_DISC_DIR")) {
    check_disc_executable("EMAIN.SELF", "3b543f22062d078a30ec2e5c15d16e7c8a2389cdc32375a58fec6c6842896729");
}
TEST_CASE("integration: decrypt disc EBOOT.BIN" * needs_env("GT6_DISC_DIR")) {
    check_disc_executable("EBOOT.BIN", "241c3e8c805049474dcb337914928d6552a3a4087a70cccda018356d73285b28");
}

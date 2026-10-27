// SPDX-License-Identifier: GPL-2.0-only
#include "doctest.h"
#include "klic.hpp"
#include "pkg.hpp"
#include "test_env.hpp"

#include <fstream>
#include <iterator>
#include <random>

#include <string>

using namespace gt6;

namespace {
std::vector<uint8_t> b(const std::string& s) { return {s.begin(), s.end()}; }
}  // namespace

TEST_CASE("klicensee_strings finds 0x + 32 hex digit strings") {
    const std::string k1 = "0x1032547698badcfe0123456789ABCDEF";
    const std::string data = std::string("junk\0", 5) + k1 + std::string("\0", 1) +
                             "0x00000000000000000000000000000000" + std::string("\0", 1) +  // zero: skipped
                             "0x123" + std::string("\0", 1) +                              // too short
                             "0x1032547698badcfe0123456789abcdef0" +                       // 33 digits
                             " a0x" + std::string(32, 'f') +                               // after a hex digit
                             " " + k1;                                                     // duplicate
    const auto c = klicensee_strings(b(data));
    REQUIRE(c.size() == 1);
    CHECK(c[0].offset == 5);
    const Klicensee want = {0x10, 0x32, 0x54, 0x76, 0x98, 0xba, 0xdc, 0xfe,
                            0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef};
    CHECK(c[0].key == want);
}

TEST_CASE("klicensee_strings handles data shorter than a key") {
    CHECK(klicensee_strings(b("0x12")).empty());
    CHECK(klicensee_strings({}).empty());
}

TEST_CASE("integration: the 1.22 EBOOT.BIN holds the klicensee that opens EMAIN.SELF" * needs_env("GT6_UPDATES_DIR")) {
    const auto updates = require_env("GT6_UPDATES_DIR");
    namespace fs = std::filesystem;
    const fs::path tmp = fs::temp_directory_path() / ("gt6klic-" + std::to_string(std::random_device{}()));
    extract_pkg(updates / "EP9001-BCES01977_00-0000000000000000-A0122-V0100-PE.pkg", tmp);
    auto read = [](const fs::path& p) {
        std::ifstream f(p, std::ios::binary);
        return std::vector<uint8_t>(std::istreambuf_iterator<char>(f), {});
    };
    const auto eboot = decrypt_self(read(tmp / "USRDIR" / "EBOOT.BIN"));
    const auto emain = read(tmp / "USRDIR" / "TPPS-01.22" / "EMAIN.SELF");
    std::error_code ec;
    fs::remove_all(tmp, ec);

    CHECK_THROWS_WITH_AS(decrypt_self(emain), doctest::Contains("wrong key"), SelfError);
    const auto cands = klicensee_strings(eboot);
    REQUIRE(cands.size() == 1);
    CHECK(cands[0].offset == 0x42000);  // data segment, file offset of va 0x52000
    const auto elf = decrypt_self(emain, &cands[0].key);
    CHECK(elf.size() == 23787792);
}

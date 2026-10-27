// SPDX-License-Identifier: GPL-2.0-only
#include "doctest.h"
#include "pkg.hpp"
#include "pkg_builder.hpp"
#include "test_env.hpp"

#include <fstream>
#include <iterator>
#include <random>

using namespace gt6;
using namespace gt6test;
namespace fs = std::filesystem;

namespace {

struct TmpDir {
    fs::path root;
    TmpDir() {
        root = fs::temp_directory_path() / ("gt6pkgtest-" + std::to_string(std::random_device{}()));
        fs::create_directories(root);
    }
    ~TmpDir() { std::error_code ec; fs::remove_all(root, ec); }
};

std::vector<uint8_t> slurp(const fs::path& p) {
    std::ifstream f(p, std::ios::binary);
    return {std::istreambuf_iterator<char>(f), {}};
}

std::vector<uint8_t> random_bytes(size_t n, uint32_t seed) {
    std::mt19937 rng(seed);
    std::vector<uint8_t> v(n);
    for (auto& b : v) b = uint8_t(rng());
    return v;
}

}  // namespace

TEST_CASE("pkg round trip is byte identical") {
    TmpDir t;
    auto eboot = random_bytes(3'000'001, 1);  // not a multiple of 16
    auto sfo = build_sfo({{"TITLE_ID", "BCES01977"}, {"APP_VER", "01.22"}});
    fs::path pkg = t.root / "a.pkg";
    write_test_pkg(pkg, "BCES01977",
                   {{"USRDIR/", {}}, {"USRDIR/EBOOT.BIN", eboot}, {"PARAM.SFO", sfo}, {"empty", {}}});

    PkgInfo info = read_pkg(pkg);
    CHECK(info.title_id == "BCES01977");
    CHECK(info.content_id == "EP9001-BCES01977_00-0000000000000000");
    REQUIRE(info.entries.size() == 4);
    CHECK(info.entries[0].is_dir);
    CHECK(info.entries[1].name == "USRDIR/EBOOT.BIN");
    CHECK(info.entries[1].size == eboot.size());
    CHECK_FALSE(info.entries[1].is_dir);

    fs::path out = t.root / "Gran Turismo 6 (UK) test" / "out";
    extract_pkg(pkg, out);
    CHECK(fs::is_directory(out / "USRDIR"));
    CHECK(slurp(out / "USRDIR" / "EBOOT.BIN") == eboot);
    CHECK(slurp(out / "PARAM.SFO") == sfo);
    CHECK(fs::file_size(out / "empty") == 0);
}

TEST_CASE("pkg entries that escape the destination are rejected") {
    TmpDir t;
    for (const char* bad : {"../escape", "/abs/path", "a/../../b", "./x"}) {
        fs::path pkg = t.root / "bad.pkg";
        write_test_pkg(pkg, "BCES01977", {{bad, {1, 2, 3}}});
        fs::path out = t.root / "Gran Turismo 6 (UK) test" / "out";
        CHECK_THROWS_AS(extract_pkg(pkg, out), PkgError);
        CHECK_FALSE(fs::exists(t.root / "escape"));
    }
}

TEST_CASE("pkg_param_sfo returns APP_VER") {
    TmpDir t;
    auto sfo = build_sfo({{"TITLE_ID", "BCES01977"}, {"APP_VER", "01.22"}});
    fs::path pkg = t.root / "a.pkg";
    write_test_pkg(pkg, "BCES01977", {{"USRDIR/EBOOT.BIN", random_bytes(100, 2)}, {"PARAM.SFO", sfo}});
    Sfo m = pkg_param_sfo(pkg);
    CHECK(std::get<std::string>(m.at("APP_VER")) == "01.22");
    CHECK(std::get<std::string>(m.at("TITLE_ID")) == "BCES01977");
}

TEST_CASE("pkg_param_sfo throws when there is no PARAM.SFO") {
    TmpDir t;
    fs::path pkg = t.root / "a.pkg";
    write_test_pkg(pkg, "BCES01977", {{"x", {1}}});
    CHECK_THROWS_AS(pkg_param_sfo(pkg), PkgError);
}

TEST_CASE("read_pkg rejects non-packages and corrupt packages") {
    TmpDir t;
    fs::path junk = t.root / "junk.pkg";
    { std::ofstream(junk, std::ios::binary) << std::string(512, 'x'); }
    CHECK_THROWS_AS(read_pkg(junk), PkgError);
    CHECK_THROWS_AS(read_pkg(t.root / "missing.pkg"), PkgError);

    fs::path pkg = t.root / "a.pkg";
    write_test_pkg(pkg, "BCES01977", {{"a", random_bytes(64, 3)}});
    auto bytes = slurp(pkg);
    bytes.resize(bytes.size() - 100);  // truncated: pkg_size no longer matches
    fs::path cut = t.root / "cut.pkg";
    { std::ofstream f(cut, std::ios::binary); f.write(reinterpret_cast<char*>(bytes.data()), std::streamsize(bytes.size())); }
    CHECK_THROWS_AS(read_pkg(cut), PkgError);
}

TEST_CASE("integration: update 1.02 PARAM.SFO" * needs_env("GT6_UPDATES_DIR")) {
    const auto dir = require_env("GT6_UPDATES_DIR");
    Sfo m = pkg_param_sfo(dir / "EP9001-BCES01977_00-0000000000000000-A0102-V0101-PE.pkg");
    CHECK(std::get<std::string>(m.at("TITLE_ID")) == "BCES01977");
    CHECK(std::get<std::string>(m.at("APP_VER")) == "01.02");
}

// SPDX-License-Identifier: GPL-2.0-only
#include "crypto.hpp"
#include "doctest.h"
#include "manifest.hpp"
#include "pkg_builder.hpp"

#include <unistd.h>

#include <fstream>
#include <string>

using namespace gt6;
namespace fs = std::filesystem;

namespace {

struct Tree {
    fs::path root;
    Tree() {
        root = fs::temp_directory_path() / ("gt6_manifest_" + std::to_string(::getpid()));
        fs::remove_all(root);
        put("dev_bdvd/PS3_GAME/USRDIR/a.bin", "alpha");
        put("dev_hdd0/game/BCES01977/USRDIR/b \"q\".bin", "bravo");
        put("decrypted/c.elf", std::string(100000, 'c'));
        put("build.json", "{}");
        sfo("BCES01977", "01.22");
    }
    void sfo(const std::string& title, const std::string& ver) {
        const auto b = gt6test::build_sfo({{"TITLE_ID", title}, {"APP_VER", ver}});
        put("dev_hdd0/game/BCES01977/PARAM.SFO", std::string(b.begin(), b.end()));
    }
    ~Tree() { fs::remove_all(root); }
    void put(const std::string& rel, const std::string& data) {
        fs::create_directories((root / rel).parent_path());
        std::ofstream(root / rel, std::ios::binary) << data;
    }
};

}  // namespace

TEST_CASE("manifest covers the three roots, sorted, without build.json") {
    Tree t;
    const Manifest m = make_manifest(t.root, "BCES01977", "01.22");
    REQUIRE(m.files.size() == 4);
    CHECK(m.files[0].path == "decrypted/c.elf");
    CHECK(m.files[1].path == "dev_bdvd/PS3_GAME/USRDIR/a.bin");
    CHECK(m.files[2].path == "dev_hdd0/game/BCES01977/PARAM.SFO");
    CHECK(m.files[3].path == "dev_hdd0/game/BCES01977/USRDIR/b \"q\".bin");
    CHECK(m.files[1].size == 5);
    const std::string a = "alpha";
    CHECK(m.files[1].sha256 == crypto::to_hex(crypto::sha256({reinterpret_cast<const uint8_t*>(a.data()), a.size()})));
}

TEST_CASE("manifest round-trips through its file") {
    Tree t;
    const Manifest m = make_manifest(t.root, "BCES01977", "01.22");
    write_manifest(t.root / "m.json", m);
    const Manifest r = read_manifest(t.root / "m.json");
    CHECK(r.title_id == "BCES01977");
    CHECK(r.app_ver == "01.22");
    REQUIRE(r.files.size() == m.files.size());
    for (size_t i = 0; i < m.files.size(); ++i) {
        CHECK(r.files[i].path == m.files[i].path);
        CHECK(r.files[i].size == m.files[i].size);
        CHECK(r.files[i].sha256 == m.files[i].sha256);
    }
    std::ofstream(t.root / "bad.json") << "{\"files\": [";
    CHECK_THROWS_AS(read_manifest(t.root / "bad.json"), ManifestError);
}

TEST_CASE("verify: matching tree is ok") {
    Tree t;
    const Manifest m = make_manifest(t.root, "BCES01977", "01.22");
    t.put("build.json", "{\"timings\": 123}");  // never counted
    const VerifyReport r = verify_tree(t.root, m);
    CHECK(r.ok());
    CHECK(r.mismatched.empty());
    CHECK(r.missing.empty());
    CHECK(r.extra.empty());
}

TEST_CASE("verify: one changed byte is a MISMATCH") {
    Tree t;
    const Manifest m = make_manifest(t.root, "BCES01977", "01.22");
    t.put("dev_bdvd/PS3_GAME/USRDIR/a.bin", "alphA");  // same size
    const VerifyReport r = verify_tree(t.root, m);
    CHECK_FALSE(r.ok());
    REQUIRE(r.mismatched.size() == 1);
    CHECK(r.mismatched[0] == "dev_bdvd/PS3_GAME/USRDIR/a.bin");
}

TEST_CASE("verify: a deleted file is MISSING") {
    Tree t;
    const Manifest m = make_manifest(t.root, "BCES01977", "01.22");
    fs::remove(t.root / "decrypted/c.elf");
    const VerifyReport r = verify_tree(t.root, m);
    CHECK_FALSE(r.ok());
    REQUIRE(r.missing.size() == 1);
    CHECK(r.missing[0] == "decrypted/c.elf");
}

TEST_CASE("verify: an added file is EXTRA and still ok") {
    Tree t;
    const Manifest m = make_manifest(t.root, "BCES01977", "01.22");
    t.put("dev_hdd0/new.txt", "x");
    const VerifyReport r = verify_tree(t.root, m);
    CHECK(r.ok());
    REQUIRE(r.extra.size() == 1);
    CHECK(r.extra[0] == "dev_hdd0/new.txt");
}

TEST_CASE("verify: an empty manifest fails") {
    Tree t;
    const Manifest m{"BCES01977", "01.22", {}};
    const VerifyReport r = verify_tree(t.root, m);
    CHECK_FALSE(r.ok());
    REQUIRE(r.problems.size() == 1);
    CHECK(r.problems[0].find("no files") != std::string::npos);
}

TEST_CASE("verify: the tree's PARAM.SFO must match the manifest's title and version") {
    Tree t;
    const Manifest m = make_manifest(t.root, "BCES01977", "01.22");
    CHECK(verify_tree(t.root, m).problems.empty());
    for (const auto& [title, ver] : {std::pair{"BCES01977", "01.21"}, std::pair{"BCUS98394", "01.22"}}) {
        CAPTURE(title);
        CAPTURE(ver);
        Manifest other = m;
        other.title_id = title;
        other.app_ver = ver;
        const VerifyReport r = verify_tree(t.root, other);
        CHECK_FALSE(r.ok());
        REQUIRE(r.problems.size() == 1);
        CHECK(r.problems[0].find("BCES01977 01.22") != std::string::npos);
    }
    fs::remove(t.root / "dev_hdd0/game/BCES01977/PARAM.SFO");
    const VerifyReport r = verify_tree(t.root, m);
    CHECK_FALSE(r.ok());
    REQUIRE_FALSE(r.problems.empty());
    CHECK(r.problems[0].find("PARAM.SFO") != std::string::npos);
}

TEST_CASE("tree_identity reads TITLE_ID and APP_VER from the game's PARAM.SFO") {
    Tree t;
    t.sfo("BCES01977", "01.07");
    const TreeIdentity id = tree_identity(t.root);
    CHECK(id.title_id == "BCES01977");
    CHECK(id.app_ver == "01.07");
    fs::remove_all(t.root / "dev_hdd0");
    CHECK_THROWS_AS(tree_identity(t.root), ManifestError);
}

// SPDX-License-Identifier: GPL-2.0-only
#include "doctest.h"
#include "build_tree.hpp"
#include "crypto.hpp"
#include "pkg_builder.hpp"
#include "self.hpp"
#include "self_builder.hpp"
#include "sfo.hpp"
#include "updates.hpp"

#include <cerrno>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <map>
#include <random>
#include <string>

using namespace gt6;
using namespace gt6test;
namespace fs = std::filesystem;

namespace {

Buf slurp(const fs::path& p) {
    std::ifstream f(p, std::ios::binary);
    return {std::istreambuf_iterator<char>(f), {}};
}

void spit(const fs::path& p, const Buf& data) {
    fs::create_directories(p.parent_path());
    std::ofstream f(p, std::ios::binary | std::ios::trunc);
    f.write(reinterpret_cast<const char*>(data.data()), std::streamsize(data.size()));
}

void spit(const fs::path& p, const std::string& s) { spit(p, Buf(s.begin(), s.end())); }

Buf bytes(const std::string& s) { return Buf(s.begin(), s.end()); }

std::string hex(std::span<const uint8_t> d) {
    static const char* k = "0123456789abcdef";
    std::string s;
    for (uint8_t b : d) {
        s += k[b >> 4];
        s += k[b & 15];
    }
    return s;
}

// Writes a synthetic update package with a Sony-style trailer: the last 32 bytes are the SHA-1
// of everything before them, then 12 zero bytes. Returns that SHA-1 as hex.
std::string make_update(const fs::path& path, const std::string& app_ver, PkgFiles files) {
    files.push_back({"PARAM.SFO", build_sfo({{"TITLE_ID", "BCES01977"}, {"APP_VER", app_ver}})});
    write_test_pkg(path, "BCES01977", files);
    Buf all = slurp(path);
    const auto digest = crypto::sha1(std::span<const uint8_t>(all.data(), all.size() - 32));
    std::copy(digest.begin(), digest.end(), all.end() - 32);
    std::fill(all.end() - 12, all.end(), uint8_t{0});
    spit(path, all);
    return hex(digest);
}

struct World {
    fs::path root, base, disc, updates, out, edition;
    std::vector<std::pair<std::string, std::string>> shas;  // app_ver -> sha1

    World() {
        root = fs::temp_directory_path() / ("gt6buildtest-" + std::to_string(std::random_device{}()));
        base = root / "Gran Turismo 6 (UK) test";
        disc = base / "disc";
        updates = base / "updates";
        out = base / "build" / "BCES01977-v1.04";
        edition = base / "edition.json";

        spit(disc / "PS3_DISC.SFB", std::string(".SFB disc marker"));
        spit(disc / "PS3_GAME" / "PARAM.SFO", build_sfo({{"TITLE_ID", "BCES01977"}, {"APP_VER", "01.00"}}));
        spit(disc / "PS3_GAME" / "USRDIR" / "EBOOT.BIN", std::string("disc eboot (not SCE)"));
        spit(disc / "PS3_UPDATE" / "PS3UPDAT.PUP", std::string("firmware, not copied"));

        // File names chosen so alphabetical order is the wrong order.
        fs::create_directories(updates);
        shas.push_back({"01.02", make_update(updates / "z-first.pkg", "01.02",
                                             {{"USRDIR/", {}}, {"USRDIR/DATA.BIN", bytes("from 01.02")}})});
        shas.push_back({"01.03", make_update(updates / "m-second.pkg", "01.03",
                                             {{"USRDIR/ONLY103.BIN", bytes("only in 01.03")}})});
        shas.push_back({"01.04", make_update(updates / "a-third.pkg", "01.04",
                                             {{"USRDIR/DATA.BIN", bytes("from 01.04")}})});
        spit(updates / "notes.txt", std::string("not a package"));
        write_edition("01.04");
    }
    ~World() {
        std::error_code ec;
        for (auto it = fs::recursive_directory_iterator(root, ec); !ec && it != fs::recursive_directory_iterator();
             it.increment(ec))
            fs::permissions(it->path(), fs::perms::owner_all, fs::perm_options::add, ec);
        fs::remove_all(root, ec);
    }

    // Mounted disc images are read-only all the way down (r-xr-xr-x files and folders).
    void make_disc_read_only() {
        std::vector<fs::path> all;
        for (const auto& e : fs::recursive_directory_iterator(disc)) all.push_back(e.path());
        all.push_back(disc);
        for (auto it = all.rbegin(); it != all.rend(); ++it)
            fs::permissions(*it, fs::perms::owner_read | fs::perms::owner_exec | fs::perms::group_read |
                                     fs::perms::group_exec | fs::perms::others_read | fs::perms::others_exec);
    }

    void write_edition(const std::string& target) {
        std::string j = "{\n  \"title_id\": \"BCES01977\",\n  \"target_app_ver\": \"" + target +
                        "\",\n  \"updates\": [\n";
        for (size_t i = 0; i < shas.size(); ++i)
            j += std::string(i ? ",\n" : "") + "    {\"app_ver\": \"" + shas[i].first + "\", \"sha1\": \"" +
                 shas[i].second + "\"}";
        j += "\n  ]\n}\n";
        spit(edition, j);
    }

    BuildOptions opts() const { return {disc, updates, out, edition, false}; }
    fs::path staging() const { return fs::path(out.string() + ".staging"); }
    fs::path old() const { return fs::path(out.string() + ".old"); }
    fs::path game() const { return out / "dev_hdd0" / "game" / "BCES01977"; }
};

std::string app_ver(const fs::path& sfo) {
    return std::get<std::string>(parse_sfo(slurp(sfo)).at("APP_VER"));
}

}  // namespace

TEST_CASE("test_order_by_app_ver_not_filename") {
    World w;
    const Edition ed = load_edition(w.edition);
    CHECK(ed.title_id == "BCES01977");
    CHECK(ed.target_app_ver == "01.04");
    REQUIRE(ed.updates.size() == 3);
    const auto ordered = order_updates(
        ed, {w.updates / "a-third.pkg", w.updates / "m-second.pkg", w.updates / "z-first.pkg"});
    REQUIRE(ordered.size() == 3);
    CHECK(ordered[0].filename() == "z-first.pkg");
    CHECK(ordered[1].filename() == "m-second.pkg");
    CHECK(ordered[2].filename() == "a-third.pkg");
}

TEST_CASE("test_missing_update_named") {
    World w;
    fs::remove(w.updates / "m-second.pkg");
    CHECK_THROWS_WITH_AS(build_tree(w.opts()), doctest::Contains("missing update 01.03"), UpdateError);
    CHECK_FALSE(fs::exists(w.out));
    CHECK_FALSE(fs::exists(w.staging()));
}

TEST_CASE("test_sha1_rule") {
    World w;
    const fs::path pkg = w.updates / "z-first.pkg";
    const Buf all = slurp(pkg);
    // The trailer holds the SHA-1 of everything before it, then 12 zero bytes.
    const auto digest = crypto::sha1(std::span<const uint8_t>(all.data(), all.size() - 32));
    CHECK(std::equal(digest.begin(), digest.end(), all.end() - 32));
    CHECK(std::all_of(all.end() - 12, all.end(), [](uint8_t b) { return b == 0; }));
    // Sony's SHA-1 is over the package minus its last 32 bytes, not the whole file.
    CHECK(sony_pkg_sha1(pkg) == hex(digest));
    CHECK(sony_pkg_sha1(pkg) == w.shas[0].second);
    CHECK(sony_pkg_sha1(pkg) != hex(crypto::sha1(all)));
    CHECK_NOTHROW(order_updates(load_edition(w.edition),
                                {w.updates / "a-third.pkg", w.updates / "m-second.pkg", pkg}));
}

TEST_CASE("test_sha1_mismatch_before_extract") {
    World w;
    Buf b = slurp(w.updates / "m-second.pkg");
    b[b.size() - 40] ^= 0x01;  // inside the covered range, outside the header and file table
    spit(w.updates / "m-second.pkg", b);
    CHECK_THROWS_WITH_AS(build_tree(w.opts()), doctest::Contains("sha1 mismatch"), UpdateError);
    CHECK_FALSE(fs::exists(w.staging()));
    CHECK_FALSE(fs::exists(w.out));
}

TEST_CASE("test_later_update_overwrites") {
    World w;
    build_tree(w.opts());
    CHECK(slurp(w.game() / "USRDIR" / "DATA.BIN") == bytes("from 01.04"));
    CHECK(slurp(w.game() / "USRDIR" / "ONLY103.BIN") == bytes("only in 01.03"));
    CHECK(app_ver(w.game() / "PARAM.SFO") == "01.04");
    // The disc layer is left as it was.
    CHECK(slurp(w.out / "dev_bdvd" / "PS3_DISC.SFB") == bytes(".SFB disc marker"));
    CHECK(app_ver(w.out / "dev_bdvd" / "PS3_GAME" / "PARAM.SFO") == "01.00");
    CHECK_FALSE(fs::exists(w.out / "dev_bdvd" / "PS3_UPDATE"));
    CHECK_FALSE(fs::exists(w.staging()));

    const std::string json = [&] { Buf j = slurp(w.out / "build.json"); return std::string(j.begin(), j.end()); }();
    CHECK(json.find("\"final_app_ver\": \"01.04\"") != std::string::npos);
    CHECK(json.find("\"tool_version\": \"" + std::string(kToolVersion) + "\"") != std::string::npos);
    for (const auto& [ver, sha] : w.shas) CHECK(json.find(sha) != std::string::npos);
    CHECK(json.find("\"disc_copy\": \"clonefile\"") != std::string::npos);
}

TEST_CASE("test_refuses_existing_out_without_force") {
    World w;
    spit(w.out / "stray.txt", std::string("keep me"));
    CHECK_THROWS_AS(build_tree(w.opts()), BuildError);
    CHECK(slurp(w.out / "stray.txt") == bytes("keep me"));
    CHECK_FALSE(fs::exists(w.staging()));
}

TEST_CASE("test_force_rebuilds_cleanly") {
    World w;
    spit(w.out / "build.json", std::string("{\n  \"tool\": \"gt6unpack\",\n  \"tool_version\": \"0.0.1\"\n}\n"));
    spit(w.out / "stray.txt", std::string("old build"));
    BuildOptions o = w.opts();
    o.force = true;
    build_tree(o);
    CHECK_FALSE(fs::exists(w.out / "stray.txt"));
    CHECK(app_ver(w.game() / "PARAM.SFO") == "01.04");
    CHECK_FALSE(fs::exists(w.staging()));
}

TEST_CASE("test_clone_fallback_copies") {
    World w;
    BuildOptions o = w.opts();
    int calls = 0;
    o.clone = [&](const fs::path&, const fs::path&) { ++calls; return EXDEV; };
    build_tree(o);
    CHECK(calls > 0);
    CHECK(slurp(w.out / "dev_bdvd" / "PS3_DISC.SFB") == bytes(".SFB disc marker"));
    CHECK(slurp(w.out / "dev_bdvd" / "PS3_GAME" / "USRDIR" / "EBOOT.BIN") == bytes("disc eboot (not SCE)"));
    const Buf j = slurp(w.out / "build.json");
    CHECK(std::string(j.begin(), j.end()).find("\"disc_copy\": \"copy\"") != std::string::npos);
}

TEST_CASE("test_final_app_ver_checked") {
    World w;
    w.write_edition("01.05");
    CHECK_THROWS_WITH_AS(build_tree(w.opts()), doctest::Contains("01.05"), BuildError);
    CHECK_FALSE(fs::exists(w.out));
    CHECK_FALSE(fs::exists(w.staging()));
}

TEST_CASE("unexpected or duplicate packages are rejected") {
    World w;
    const Edition ed = load_edition(w.edition);
    make_update(w.updates / "extra.pkg", "01.05", {});
    CHECK_THROWS_WITH_AS(order_updates(ed, {w.updates / "z-first.pkg", w.updates / "m-second.pkg",
                                            w.updates / "a-third.pkg", w.updates / "extra.pkg"}),
                         doctest::Contains("01.05"), UpdateError);
    fs::copy_file(w.updates / "z-first.pkg", w.updates / "copy.pkg");
    CHECK_THROWS_WITH_AS(order_updates(ed, {w.updates / "z-first.pkg", w.updates / "copy.pkg",
                                            w.updates / "m-second.pkg", w.updates / "a-third.pkg"}),
                         doctest::Contains("duplicate"), UpdateError);
}

TEST_CASE("SCE containers that are not SELFs are skipped and recorded") {
    World w;
    // SCE header type 3 (not a SELF) in an update.
    Buf blob = {'S', 'C', 'E', 0, 0, 0, 0, 2, 0, 0, 0, 3};
    blob.resize(64, 0);
    w.shas[2].second = make_update(w.updates / "a-third.pkg", "01.04",
                                   {{"USRDIR/DATA.BIN", bytes("from 01.04")}, {"USRDIR/BLOB.DAT", blob}});
    w.write_edition("01.04");
    build_tree(w.opts());
    const Buf j = slurp(w.out / "build.json");
    const std::string json(j.begin(), j.end());
    CHECK(json.find("dev_hdd0/game/BCES01977/USRDIR/BLOB.DAT") != std::string::npos);
    CHECK(json.find("SCE header type 3") != std::string::npos);
    CHECK_FALSE(fs::exists(w.out / "decrypted" / "dev_hdd0" / "game" / "BCES01977" / "USRDIR" / "BLOB.DAT.elf"));
}

TEST_CASE("a SELF that does not decrypt fails the build") {
    World w;
    Buf bad = {'S', 'C', 'E', 0, 0, 0, 0, 2, 0, 0x1C, 0, 1};
    bad.resize(256, 0xAB);
    w.shas[2].second = make_update(w.updates / "a-third.pkg", "01.04", {{"USRDIR/EBOOT.BIN", bad}});
    w.write_edition("01.04");
    CHECK_THROWS_AS(build_tree(w.opts()), SelfError);
    CHECK_FALSE(fs::exists(w.out));
    CHECK_FALSE(fs::exists(w.staging()));
}

TEST_CASE("a read-only disc tree copies, clones and rebuilds") {
    World w;
    w.make_disc_read_only();
    for (bool clone : {false, true}) {
        CAPTURE(clone);
        BuildOptions o = w.opts();
        o.force = true;
        if (!clone) o.clone = [](const fs::path&, const fs::path&) { return EXDEV; };
        build_tree(o);
        CHECK(slurp(w.out / "dev_bdvd" / "PS3_GAME" / "USRDIR" / "EBOOT.BIN") == bytes("disc eboot (not SCE)"));
        // The built tree is writable by its owner, so a later --force rebuild can replace it.
        const auto perms = fs::status(w.out / "dev_bdvd" / "PS3_GAME" / "USRDIR").permissions();
        CHECK((perms & fs::perms::owner_write) != fs::perms::none);
    }
    build_tree([&] { BuildOptions o = w.opts(); o.force = true; return o; }());
    CHECK_FALSE(fs::exists(w.staging()));
}

namespace {
// The klicensee kGameKlic as the game's EBOOT stores it: a hex string in its data.
const std::string kGameKlicText = "0x1032547698badcfe0123456789abcdef";
}  // namespace

TEST_CASE("an NPDRM SELF opens with the klicensee found in the update EBOOT") {
    World w;
    const Fixture eboot = make_fixture(Kind::NpdrmFree, nullptr, kGameKlicText + std::string(1, '\0'));
    const Fixture emain = make_fixture(Kind::NpdrmFree, &kGameKlic);
    w.shas[2].second = make_update(w.updates / "a-third.pkg", "01.04",
                                   {{"USRDIR/EBOOT.BIN", eboot.self}, {"USRDIR/TPPS/EMAIN.SELF", emain.self}});
    w.write_edition("01.04");
    build_tree(w.opts());
    const fs::path dec = w.out / "decrypted" / "dev_hdd0" / "game" / "BCES01977" / "USRDIR";
    CHECK(slurp(dec / "EBOOT.BIN.elf") == eboot.elf);
    CHECK(slurp(dec / "TPPS" / "EMAIN.SELF.elf") == emain.elf);
    const Buf j = slurp(w.out / "build.json");
    const std::string json(j.begin(), j.end());
    CHECK(json.find("\"klicensee_from\": \"decrypted/dev_hdd0/game/BCES01977/USRDIR/EBOOT.BIN.elf\"") !=
          std::string::npos);
    CHECK(json.find(kGameKlicText.substr(2)) == std::string::npos);  // the key itself is never written
}

TEST_CASE("an NPDRM SELF whose klicensee is nowhere fails the build, naming the file") {
    World w;
    const Fixture eboot = make_fixture(Kind::NpdrmFree);
    const Fixture emain = make_fixture(Kind::NpdrmFree, &kGameKlic);
    w.shas[2].second = make_update(w.updates / "a-third.pkg", "01.04",
                                   {{"USRDIR/EBOOT.BIN", eboot.self}, {"USRDIR/EMAIN.SELF", emain.self}});
    w.write_edition("01.04");
    CHECK_THROWS_WITH_AS(build_tree(w.opts()),
                         doctest::Contains("dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF"), SelfError);
    CHECK_FALSE(fs::exists(w.out));
    CHECK_FALSE(fs::exists(w.staging()));
}

namespace {
// Every file under root (relative path -> contents), for byte-for-byte tree comparisons.
std::map<std::string, Buf> snapshot(const fs::path& root) {
    std::map<std::string, Buf> m;
    for (const auto& e : fs::recursive_directory_iterator(root))
        if (e.is_regular_file()) m[fs::relative(e.path(), root).generic_string()] = slurp(e.path());
    return m;
}
}  // namespace

TEST_CASE("a --force rebuild that fails late leaves the old tree intact") {
    World w;
    build_tree(w.opts());
    const auto before = snapshot(w.out);
    REQUIRE(before.count("build.json"));
    w.write_edition("01.05");  // fails at the final APP_VER check, after the whole build
    BuildOptions o = w.opts();
    o.force = true;
    CHECK_THROWS_WITH_AS(build_tree(o), doctest::Contains("01.05"), BuildError);
    CHECK(snapshot(w.out) == before);
    CHECK_FALSE(fs::exists(w.staging()));
    CHECK_FALSE(fs::exists(w.old()));
}

TEST_CASE("an interrupted swap is recovered, not deleted") {
    World w;
    build_tree(w.opts());
    const auto before = snapshot(w.out);
    // As if killed between moving the old tree aside and moving the new one in.
    fs::rename(w.out, w.old());
    spit(w.staging() / ".gt6unpack-staging", std::string(""));
    spit(w.staging() / "partial.bin", std::string("half a build"));
    CHECK_THROWS_WITH_AS(build_tree(w.opts()), doctest::Contains("already exists"), BuildError);
    CHECK(snapshot(w.out) == before);  // the old tree is back in place
    CHECK_FALSE(fs::exists(w.old()));

    BuildOptions o = w.opts();
    o.force = true;
    build_tree(o);
    CHECK(app_ver(w.game() / "PARAM.SFO") == "01.04");
    CHECK_FALSE(fs::exists(w.out / "partial.bin"));
    CHECK_FALSE(fs::exists(w.staging()));
    CHECK_FALSE(fs::exists(w.old()));
}

TEST_CASE("a relative --out or one with a trailing slash works") {
    World w;
    struct Cwd {
        fs::path saved = fs::current_path();
        ~Cwd() { fs::current_path(saved); }
    } cwd;
    fs::current_path(w.base);
    BuildOptions o = w.opts();
    o.out_dir = "BCES01977-rel";
    build_tree(o);
    CHECK(app_ver(w.base / "BCES01977-rel" / "dev_hdd0" / "game" / "BCES01977" / "PARAM.SFO") == "01.04");
    CHECK_FALSE(fs::exists(w.base / "BCES01977-rel.staging"));

    o.out_dir = w.out.string() + "/";
    build_tree(o);
    CHECK(app_ver(w.game() / "PARAM.SFO") == "01.04");
    CHECK_FALSE(fs::exists(w.staging()));
}

// ---- C1: --force only ever replaces a previous gt6unpack build ----

namespace {
BuildOptions forced(const World& w, const fs::path& out) {
    BuildOptions o = w.opts();
    o.out_dir = out;
    o.force = true;
    return o;
}
std::string error_of(const BuildOptions& o) {
    try {
        build_tree(o);
    } catch (const std::exception& e) {
        return e.what();
    }
    return "";
}
}  // namespace

TEST_CASE("--force refuses to replace a folder that is not a gt6unpack build") {
    World w;
    spit(w.out / "precious.txt", std::string("keep me"));
    const std::string err = error_of(forced(w, w.out));
    CHECK(err.find("not a gt6unpack build") != std::string::npos);
    CHECK(slurp(w.out / "precious.txt") == bytes("keep me"));
    CHECK_FALSE(fs::exists(w.old()));
    CHECK_FALSE(fs::exists(w.staging()));
    // A build.json from something else does not count.
    spit(w.out / "build.json", std::string("{\"tool\": \"other\"}"));
    CHECK(error_of(forced(w, w.out)).find("not a gt6unpack build") != std::string::npos);
    CHECK(slurp(w.out / "precious.txt") == bytes("keep me"));
}

TEST_CASE("without --force, a non-build folder is refused without suggesting --force") {
    World w;
    spit(w.out / "precious.txt", std::string("keep me"));
    const std::string err = error_of(w.opts());
    CHECK(err.find("not a gt6unpack build") != std::string::npos);
    CHECK(err.find("--force") == std::string::npos);
    // A previous build is refused with the hint.
    fs::remove(w.out / "precious.txt");
    build_tree(forced(w, w.out));
    CHECK(error_of(w.opts()).find("use --force") != std::string::npos);
}

TEST_CASE("--force replaces an empty folder") {
    World w;
    fs::create_directories(w.out);
    build_tree(forced(w, w.out));
    CHECK(app_ver(w.game() / "PARAM.SFO") == "01.04");
}

TEST_CASE("--out may not be or contain the disc, the updates or the current folder") {
    World w;
    struct Cwd {
        fs::path saved = fs::current_path();
        ~Cwd() { fs::current_path(saved); }
    } cwd;
    spit(w.base / "build.json", std::string("{\"tool\": \"gt6unpack\"}"));  // even if it looks like a build
    for (const fs::path& out : {w.disc, w.updates, w.base, w.root}) {
        CAPTURE(out);
        for (bool force : {false, true}) {
            BuildOptions o = forced(w, out);
            o.force = force;
            const std::string err = error_of(o);
            CHECK(err.find("--out") != std::string::npos);
            CHECK(err.find("--force") == std::string::npos);
        }
    }
    CHECK(fs::exists(w.disc / "PS3_GAME" / "PARAM.SFO"));
    CHECK(fs::exists(w.updates / "z-first.pkg"));
    CHECK_FALSE(fs::exists(fs::path(w.base.string() + ".old")));

    fs::create_directories(w.base / "work");
    fs::current_path(w.base / "work");
    for (const char* rel : {".", "..", "./"}) {
        CAPTURE(rel);
        CHECK(error_of(forced(w, rel)).find("current folder") != std::string::npos);
    }
    CHECK(fs::exists(w.base / "work"));
    CHECK(fs::exists(w.disc / "PS3_GAME" / "PARAM.SFO"));
}

TEST_CASE("--out may not be inside or contain a git work tree") {
    World w;
    const fs::path repo = w.root / "repo";
    fs::create_directories(repo / ".git");
    CHECK(error_of(forced(w, repo / "build" / "BCES01977")).find("git work tree") != std::string::npos);
    CHECK(error_of(forced(w, repo)).find("git work tree") != std::string::npos);
    CHECK_FALSE(fs::exists(repo / "build"));
    // A git worktree or submodule has a .git file instead of a folder.
    const fs::path wt = w.root / "worktree";
    spit(wt / ".git", std::string("gitdir: /somewhere/else\n"));
    CHECK(error_of(forced(w, wt / "out")).find("git work tree") != std::string::npos);
    // A previous build with a work tree inside it is not replaced.
    build_tree(w.opts());
    fs::create_directories(w.out / "dev_hdd0" / "mine" / ".git");
    CHECK(error_of(forced(w, w.out)).find("git work tree") != std::string::npos);
    CHECK(fs::exists(w.out / "dev_hdd0" / "mine" / ".git"));
}

TEST_CASE("leftover .old and .staging folders that are not ours are not deleted") {
    World w;
    spit(w.old() / "precious.txt", std::string("keep me"));
    CHECK(error_of(w.opts()).find(w.old().string()) != std::string::npos);
    CHECK(slurp(w.old() / "precious.txt") == bytes("keep me"));
    CHECK_FALSE(fs::exists(w.out));  // not restored over: it is not a build
    fs::remove_all(w.old());
    spit(w.staging() / "precious.txt", std::string("keep me"));
    CHECK(error_of(w.opts()).find(w.staging().string()) != std::string::npos);
    CHECK(slurp(w.staging() / "precious.txt") == bytes("keep me"));
}

TEST_CASE("dotfiles in the updates folder (AppleDouble ._*.pkg) are ignored") {
    World w;
    spit(w.updates / "._a-third.pkg", std::string("\0\5\26\7 AppleDouble resource fork", 30));
    spit(w.updates / ".hidden.pkg", std::string("not a package"));
    build_tree(w.opts());
    CHECK(app_ver(w.game() / "PARAM.SFO") == "01.04");
}

TEST_CASE("any error while decrypting a SELF is that file's failure, named") {
    World w;
    const Fixture eboot = make_fixture(Kind::App);
    w.shas[2].second = make_update(w.updates / "a-third.pkg", "01.04", {{"USRDIR/EBOOT.BIN", eboot.self}});
    w.write_edition("01.04");
    BuildOptions o = w.opts();
    o.decrypt = [](std::span<const uint8_t>, const Klicensee*) -> std::vector<uint8_t> {
        throw std::length_error("vector too long");
    };
    CHECK_THROWS_WITH_AS(build_tree(o),
                         doctest::Contains("dev_hdd0/game/BCES01977/USRDIR/EBOOT.BIN: vector too long"), SelfError);
    CHECK_FALSE(fs::exists(w.out));
    CHECK_FALSE(fs::exists(w.staging()));
}

TEST_CASE("an error while trying a klicensee candidate is recorded for that file") {
    World w;
    const Fixture eboot = make_fixture(Kind::NpdrmFree, nullptr, kGameKlicText + std::string(1, '\0'));
    const Fixture emain = make_fixture(Kind::NpdrmFree, &kGameKlic);
    w.shas[2].second = make_update(w.updates / "a-third.pkg", "01.04",
                                   {{"USRDIR/EBOOT.BIN", eboot.self}, {"USRDIR/EMAIN.SELF", emain.self}});
    w.write_edition("01.04");
    BuildOptions o = w.opts();
    o.decrypt = [](std::span<const uint8_t> d, const Klicensee* k) -> std::vector<uint8_t> {
        if (k) throw std::bad_alloc();
        return decrypt_self(d, k);
    };
    CHECK_THROWS_WITH_AS(build_tree(o), doctest::Contains("dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF"), SelfError);
    CHECK_FALSE(fs::exists(w.out));
    CHECK_FALSE(fs::exists(w.staging()));
}

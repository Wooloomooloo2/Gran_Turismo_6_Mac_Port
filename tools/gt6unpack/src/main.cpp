// SPDX-License-Identifier: GPL-2.0-only
// gt6unpack command line.
#include "build_tree.hpp"
#include "manifest.hpp"

#include <exception>
#include <iostream>
#include <string>

namespace fs = std::filesystem;

namespace {

int usage() {
    std::cerr << "usage: gt6unpack build --disc <dir> --updates <dir> --out <dir> "
                 "[--edition editions/BCES01977.json] [--force]\n"
                 "       gt6unpack manifest <out> -o <file>\n"
                 "       gt6unpack verify <out> --manifest <file>\n";
    return 2;
}

// The default edition file: ./editions/BCES01977.json, else the one in the source tree.
fs::path default_edition() {
    const fs::path local = fs::path("editions") / "BCES01977.json";
    if (fs::exists(local)) return local;
    return fs::path(GT6_REPO_EDITIONS) / "BCES01977.json";
}

int manifest_cmd(int argc, char** argv) {
    if (argc != 5 || std::string(argv[3]) != "-o") return usage();
    const fs::path out = argv[2];
    const gt6::TreeIdentity id = gt6::tree_identity(out);
    const gt6::Manifest m = gt6::make_manifest(out, id.title_id, id.app_ver);
    gt6::write_manifest(argv[4], m);
    std::cerr << "gt6unpack: wrote " << m.files.size() << " entries to " << argv[4] << "\n";
    return 0;
}

int verify_cmd(int argc, char** argv) {
    if (argc != 5 || std::string(argv[3]) != "--manifest") return usage();
    const fs::path out = argv[2];
    const gt6::Manifest m = gt6::read_manifest(argv[4]);
    const gt6::VerifyReport r = gt6::verify_tree(out, m);
    for (const auto& p : r.problems) std::cout << "PROBLEM " << p << "\n";
    for (const auto& p : r.mismatched) std::cout << "MISMATCH " << p << "\n";
    for (const auto& p : r.missing) std::cout << "MISSING " << p << "\n";
    for (const auto& p : r.extra) std::cout << "EXTRA " << p << "\n";
    std::cerr << "gt6unpack: " << m.files.size() << " files checked: " << r.mismatched.size() << " mismatched, "
              << r.missing.size() << " missing, " << r.extra.size() << " extra\n";
    return r.ok() ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc >= 2 && (std::string(argv[1]) == "manifest" || std::string(argv[1]) == "verify")) {
        try {
            return std::string(argv[1]) == "manifest" ? manifest_cmd(argc, argv) : verify_cmd(argc, argv);
        } catch (const std::exception& e) {
            std::cerr << "gt6unpack: error: " << e.what() << "\n";
            return 1;
        }
    }
    if (argc < 2 || std::string(argv[1]) != "build") return usage();
    gt6::BuildOptions o;
    for (int i = 2; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&]() -> const char* { return i + 1 < argc ? argv[++i] : nullptr; };
        const char* v = nullptr;
        if (a == "--force") {
            o.force = true;
            continue;
        }
        if (a != "--disc" && a != "--updates" && a != "--out" && a != "--edition") return usage();
        if (!(v = next())) return usage();
        if (a == "--disc") o.disc_dir = v;
        else if (a == "--updates") o.updates_dir = v;
        else if (a == "--out") o.out_dir = v;
        else o.edition_file = v;
    }
    if (o.disc_dir.empty() || o.updates_dir.empty() || o.out_dir.empty()) return usage();
    if (o.edition_file.empty()) o.edition_file = default_edition();
    o.log = [](const std::string& line) { std::cerr << "gt6unpack: " << line << std::endl; };

    try {
        gt6::build_tree(o);
    } catch (const std::exception& e) {
        std::cerr << "gt6unpack: error: " << e.what() << "\n";
        return 1;
    }
    return 0;
}

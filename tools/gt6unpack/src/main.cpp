// gt6unpack command line.
#include "build_tree.hpp"

#include <cstdio>
#include <exception>
#include <iostream>
#include <string>

namespace fs = std::filesystem;

namespace {

int usage() {
    std::cerr << "usage: gt6unpack build --disc <dir> --updates <dir> --out <dir> "
                 "[--edition editions/BCES01977.json] [--force]\n";
    return 2;
}

// The default edition file: ./editions/BCES01977.json, else the one in the source tree.
fs::path default_edition() {
    const fs::path local = fs::path("editions") / "BCES01977.json";
    if (fs::exists(local)) return local;
    return fs::path(GT6_REPO_EDITIONS) / "BCES01977.json";
}

}  // namespace

int main(int argc, char** argv) {
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

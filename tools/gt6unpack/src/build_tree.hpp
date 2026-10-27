// SPDX-License-Identifier: GPL-2.0-only
// Assembles a game tree: disc copy (dev_bdvd), updates installed in APP_VER order
// (dev_hdd0/game/<title>), decrypted executables, and build.json. Layout per design D14.
#pragma once
#include <filesystem>
#include <functional>
#include <stdexcept>
#include <string>

namespace gt6 {

class BuildError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

inline constexpr const char* kToolVersion = "0.1.0";

// Clones src to dst (dst must not exist). Returns 0 on success or an errno value.
using CloneFn = std::function<int(const std::filesystem::path& src, const std::filesystem::path& dst)>;

// The default CloneFn: clonefile(2).
int clone_with_clonefile(const std::filesystem::path& src, const std::filesystem::path& dst);

struct BuildOptions {
    std::filesystem::path disc_dir, updates_dir, out_dir, edition_file;
    bool force = false;
    CloneFn clone = clone_with_clonefile;  // tests inject failures here
    std::function<void(const std::string&)> log = [](const std::string&) {};  // progress lines
};

// Builds into "<out>.staging" and renames it over <out> only when everything succeeded:
// updates verified (before anything is written), disc cloned (or copied after a free-space
// check), updates installed, every SELF decrypted (all failures are collected, then thrown
// together as one SelfError), final PARAM.SFO APP_VER equal to the
// edition's target. On failure nothing is left at <out>.staging and <out> is untouched. With
// --force the old tree is renamed to <out>.old, the new one renamed in, then the old one
// removed; a run killed in between is repaired at the next start. A relative <out> or one with
// a trailing separator is accepted.
// Refused before anything is written: an <out> that is or contains the current folder, the
// disc or the updates folder; an <out> inside a git work tree; an existing <out> that is not
// empty and has no gt6unpack build.json (never replaced, even with --force); a previous build
// with a git work tree inside it; <out>.old or <out>.staging folders not left by gt6unpack.
// Throws BuildError, UpdateError, PkgError or SelfError.
void build_tree(const BuildOptions& opts);

}  // namespace gt6

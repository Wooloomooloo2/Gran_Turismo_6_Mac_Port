// SPDX-License-Identifier: GPL-2.0-only
// Hashes-only manifest of a built tree, and verification of a tree against one.
// The manifest holds paths, sizes and SHA-256 values, never file contents, so it can be committed.
#pragma once
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

namespace gt6 {

class ManifestError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct ManifestFile {
    std::string path;  // relative to <out>, '/' separated
    uint64_t size = 0;
    std::string sha256;  // 64 lower-case hex digits
};

struct Manifest {
    std::string title_id, app_ver;
    std::vector<ManifestFile> files;  // sorted by path
};

struct VerifyReport {
    std::vector<std::string> mismatched, missing, extra;  // each sorted
    // Whole-tree problems: an empty manifest, or a tree whose PARAM.SFO is not the manifest's
    // title and version.
    std::vector<std::string> problems;
    // Extra files are only a warning.
    bool ok() const { return problems.empty() && mismatched.empty() && missing.empty(); }
};

struct TreeIdentity {
    std::string title_id, app_ver;
};

// TITLE_ID and APP_VER from the first dev_hdd0/game/<title>/PARAM.SFO of a built tree.
// Throws ManifestError when there is none or it lacks either field.
TreeIdentity tree_identity(const std::filesystem::path& out);

// Hashes every regular file under <out>/dev_bdvd, <out>/dev_hdd0 and <out>/decrypted
// (symlinks are not followed). build.json is deliberately left out: it holds timings and
// paths that change on every run.
Manifest make_manifest(const std::filesystem::path& out, const std::string& title_id, const std::string& app_ver);

void write_manifest(const std::filesystem::path& file, const Manifest& m);
Manifest read_manifest(const std::filesystem::path& file);  // throws ManifestError

// Compares <out> with m. Files outside the three roots (build.json included) are never listed
// as extra. Not ok when m lists no files, or when tree_identity(out) is not m's title_id and
// app_ver (or cannot be read).
VerifyReport verify_tree(const std::filesystem::path& out, const Manifest& m);

}  // namespace gt6

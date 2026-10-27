// Edition files and update ordering/verification. No third-party code.
#pragma once
#include <filesystem>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace gt6 {

class UpdateError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// One game edition: its title ID, the APP_VER a finished build must reach, and every
// official update as (APP_VER, Sony SHA-1 in lowercase hex).
struct Edition {
    std::string title_id, target_app_ver;
    std::vector<std::pair<std::string, std::string>> updates;
};

// Reads an edition JSON file. Throws UpdateError on malformed content.
Edition load_edition(const std::filesystem::path& path);

// Sony's update checksum: SHA-1 of the package minus its last 32 bytes, lowercase hex.
std::string sony_pkg_sha1(const std::filesystem::path& pkg);

// Returns the packages ordered by each package's own PARAM.SFO APP_VER (never by file name).
// Every update in the edition must be present exactly once, belong to the edition's title and
// match its SHA-1. Throws UpdateError("missing update 01.07"), UpdateError("... sha1 mismatch
// ..."), and so on. Reads only; nothing is written.
std::vector<std::filesystem::path> order_updates(const Edition& edition,
                                                 const std::vector<std::filesystem::path>& pkgs);

}  // namespace gt6

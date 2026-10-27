// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <cstdlib>
#include <filesystem>
#include <optional>

// Returns the path named by environment variable `name`, or nullopt when unset/empty.
// Integration tests use this for GT6_DISC_DIR / GT6_UPDATES_DIR and skip when absent.
inline std::optional<std::filesystem::path> env_path(const char* name) {
    const char* v = std::getenv(name);
    if (!v || !*v) return std::nullopt;
    return std::filesystem::path(v);
}

// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include "doctest.h"

#include <cstdlib>
#include <filesystem>
#include <optional>

// Returns the path named by environment variable `name`, or nullopt when unset/empty.
// Integration tests use this for GT6_DISC_DIR / GT6_UPDATES_DIR.
inline std::optional<std::filesystem::path> env_path(const char* name) {
    const char* v = std::getenv(name);
    if (!v || !*v) return std::nullopt;
    return std::filesystem::path(v);
}

// Decorator for integration test cases: marks the case skipped (counted in doctest's
// "skipped" total, not as passed) when environment variable `name` is unset, e.g.
//   TEST_CASE("integration: ..." * needs_env("GT6_DISC_DIR")) { const auto d = require_env("GT6_DISC_DIR"); ... }
inline doctest::skip needs_env(const char* name) { return doctest::skip(!env_path(name)); }

// The path for a case decorated with needs_env (fails, rather than passes, if run with --no-skip).
inline std::filesystem::path require_env(const char* name) {
    const auto p = env_path(name);
    REQUIRE_MESSAGE(p.has_value(), name << " is unset");
    return *p;
}

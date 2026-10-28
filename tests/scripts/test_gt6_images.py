# SPDX-License-Identifier: GPL-2.0-or-later
"""port/gt6_images.h: the port's lookup of the build for an EMAIN.SELF (D44, D47).

Compiles a small host program against the header and checks: the matching build is found,
a build from another patch set is refused (stale), an entry with no patch set is stale, an
unknown SELF is none, malformed entries are skipped, and a hash prefix does not match."""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

PROGRAM = r'''
#include "gt6_images.h"
#include <cstdio>
#include <cstring>
static int fails = 0;
#define CHECK(c, m) do { if (!(c)) { std::printf("FAIL %s\n", m); fails++; } } while (0)
int main() {
    std::string bin, elf, stale;
    const char* list = "junk;aa=/b/one|/e/one|P1;bb=/b/two|/e/two|P0;cc=/b/three|/e/three;dd";
    CHECK(gt6_find_image(list, "aa", "P1", bin, elf, stale) == GT6_IMAGE_FOUND, "found");
    CHECK(bin == "/b/one" && elf == "/e/one", "bin and elf");
    CHECK(gt6_find_image(list, "bb", "P1", bin, elf, stale) == GT6_IMAGE_STALE, "stale");
    CHECK(bin == "/b/two" && stale == "P0", "stale names the build and its patch set");
    CHECK(gt6_find_image(list, "cc", "P1", bin, elf, stale) == GT6_IMAGE_STALE, "no patch set is stale");
    CHECK(gt6_find_image(list, "ee", "P1", bin, elf, stale) == GT6_IMAGE_NONE, "unknown");
    CHECK(gt6_find_image(list, "a", "P1", bin, elf, stale) == GT6_IMAGE_NONE, "a prefix is no match");
    CHECK(gt6_find_image(nullptr, "aa", "P1", bin, elf, stale) == GT6_IMAGE_NONE, "no list");
    CHECK(gt6_find_image("", "aa", "P1", bin, elf, stale) == GT6_IMAGE_NONE, "empty list");
    std::printf(fails ? "FAIL\n" : "PASS\n");
    return fails ? 1 : 0;
}
'''


@pytest.mark.skipif(shutil.which("c++") is None, reason="no C++ compiler")
def test_gt6_find_image(tmp_path):
    src = tmp_path / "t.cpp"
    src.write_text(PROGRAM)
    exe = tmp_path / "t"
    subprocess.run(["c++", "-std=c++17", "-I", str(REPO / "port"), "-o", str(exe), str(src)],
                   check=True, capture_output=True)
    r = subprocess.run([str(exe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout

# SPDX-License-Identifier: GPL-2.0-or-later
"""The README tells a developer how to unpack their copy, with the commands that work."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_readme_has_unpack_usage():
    readme = (ROOT / "README.md").read_text()
    assert "## Unpack your copy (developer preview)" in readme
    for needle in ["cmake -S . -B build", "cmake --build build",
                   "hdiutil attach -readonly -nobrowse -mountpoint",
                   "build/tools/gt6unpack/gt6unpack build --disc", "--updates", "--out",
                   "build/tools/gt6unpack/gt6unpack verify",
                   "--manifest manifests/BCES01977-v1.22.json", "hdiutil detach",
                   "21 packages", "outside this repository", "docs/BACKLOG.md"]:
        assert needle in readme, needle


def test_backlog_does_not_say_the_tool_runs_hdiutil():
    backlog = (ROOT / "docs" / "BACKLOG.md").read_text()
    assert "without `hdiutil`" not in backlog

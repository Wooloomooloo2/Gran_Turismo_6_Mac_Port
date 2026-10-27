# SPDX-License-Identifier: GPL-2.0-or-later
"""Every source file states its licence (decision D24).

gt6unpack links code adapted from RPCS3, which is GPL-2.0-only, so all of gt6unpack is
GPL-2.0-only. The project's own scripts and build files are GPL-2.0-or-later.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RPCS3_DERIVED = {
    "tools/gt6unpack/src/keys.cpp": ["key_vault.cpp", "key_vault.h"],
    "tools/gt6unpack/src/keys.hpp": ["key_vault.cpp", "key_vault.h"],
    "tools/gt6unpack/src/self.cpp": ["unself.cpp"],
    "tools/gt6unpack/src/self.hpp": ["unself.cpp", "unself.h"],
    "tools/gt6unpack/src/pkg.cpp": ["unpkg.cpp"],
    "tools/gt6unpack/src/pkg.hpp": ["unpkg.cpp", "unpkg.h"],
}


def source_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    for name in (x.decode() for x in out.split(b"\0") if x):
        if name.startswith(("third_party/", "tests/scripts/fixtures/")):
            continue
        if name.endswith((".cpp", ".hpp", ".py", ".sh")) or Path(name).name == "CMakeLists.txt":
            yield name


def spdx(name):
    for line in (ROOT / name).read_text().splitlines()[:3]:
        if "SPDX-License-Identifier:" in line:
            return line.split("SPDX-License-Identifier:", 1)[1].strip()
    return None


def test_every_source_file_has_the_right_spdx_line():
    wrong = []
    for name in source_files():
        want = "GPL-2.0-only" if name.startswith("tools/gt6unpack/") else "GPL-2.0-or-later"
        if spdx(name) != want:
            wrong.append(f"{name}: {spdx(name)} (want {want})")
    assert not wrong, "\n".join(wrong)


def test_rpcs3_derived_files_name_every_source_file():
    for name, sources in RPCS3_DERIVED.items():
        head = "\n".join((ROOT / name).read_text().splitlines()[:6])
        assert "Adapted from RPCS3 (GPL-2.0-only)" in head, name
        assert "c365ea76a552961ff078ea1a46da9d4b07729674" in head, name
        for src in sources:
            assert f"rpcs3/Crypto/{src}" in head, f"{name} does not credit {src}"


def test_notices_and_readme_state_the_split():
    notices = (ROOT / "THIRD-PARTY-NOTICES.md").read_text()
    readme = (ROOT / "README.md").read_text()
    decisions = (ROOT / "docs" / "DECISIONS.md").read_text()
    assert "GPL-2.0-only" in notices and "key_vault.h" in notices
    assert "GPL-2.0-only" in readme and "GPL-2.0-or-later" in readme
    assert "**D24" in decisions

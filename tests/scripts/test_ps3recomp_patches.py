# SPDX-License-Identifier: GPL-2.0-or-later
"""ps3recomp's own tests for the code our patches change (D28).

Exports the pinned ps3recomp commit (the superproject's gitlink, not the submodule's
working tree) with `git archive`, applies patches/ps3recomp/*.patch in filename order, and
runs every `tools/test_*.py` that a patch adds or changes, plus every one that names a
file a patch changes (a C test it builds, or the source it pulls code out of). A runner
that reports `SKIP` (no compiler or other toolchain) is a visible pytest skip.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SUB = REPO / "third_party" / "ps3recomp"
PATCHES = sorted((REPO / "patches" / "ps3recomp").glob("*.patch"))


def _git(*args, cwd=REPO):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def pinned_commit():
    out = _git("ls-tree", "HEAD", "third_party/ps3recomp").split()
    return out[2] if len(out) >= 3 and out[1] == "commit" else None


def touched_files(patch):
    return [m.group(1) for m in re.finditer(r"^\+\+\+ b/(\S+)", patch.read_text(), re.M)]


def runners():
    """The tools/test_*.py scripts that exercise what the patches change."""
    pin = pinned_commit()
    if not pin or not (SUB / ".git").exists() or shutil.which("git") is None:
        return []
    touched = sorted({f for p in PATCHES for f in touched_files(p)})
    found = {f for f in touched if re.fullmatch(r"tools/test_[^/]+\.py", f)}
    for f in touched:
        if f.startswith("tools/test_"):
            continue
        name = Path(f).name
        r = subprocess.run(["git", "grep", "-l", "-F", name, pin, "--", "tools/test_*.py"],
                           cwd=SUB, capture_output=True, text=True)
        found |= {line.split(":", 1)[1] for line in r.stdout.splitlines()}
    return sorted(found)


@pytest.fixture(scope="module")
def patched_tree(tmp_path_factory):
    pin = pinned_commit()
    if not pin or not (SUB / ".git").exists():
        pytest.skip("no ps3recomp checkout (git submodule update --init third_party/ps3recomp)")
    tree = tmp_path_factory.mktemp("ps3recomp")
    archive = subprocess.run(["git", "archive", pin], cwd=SUB, check=True,
                             capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
    for p in PATCHES:
        r = subprocess.run(["git", "apply", "--whitespace=nowarn", str(p)], cwd=tree,
                           capture_output=True, text=True)
        assert r.returncode == 0, f"{p.name} does not apply after the earlier patches: {r.stderr}"
    return tree


def test_runners_found():
    if not pinned_commit() or not (SUB / ".git").exists():
        pytest.skip("no ps3recomp checkout")
    found = runners()
    # every runner a patch adds or edits is in the set
    for p in PATCHES:
        for f in touched_files(p):
            if re.fullmatch(r"tools/test_[^/]+\.py", f):
                assert f in found
    assert "tools/test_lwcond_wakeup.py" in found
    assert "tools/test_cellfiber_ppu.py" in found   # patch 0011, PPU fiber contexts (D36)
    assert "tools/test_avconf_screen_size.py" in found   # patch 0012
    assert "tools/test_spurs_workload_flag.py" in found   # patch 0013
    assert "tools/test_usbd_extra_ldd.py" in found   # patch 0014
    assert "tools/test_mempool_module_list.py" in found   # patch 0015
    assert "tools/test_music2.py" in found   # patch 0016
    assert "tools/test_trophy_sound_level.py" in found   # patch 0017
    assert "tools/test_mmapper_hle_heap.py" in found   # patch 0018 (upstream runner, extended)
    assert "tools/test_exitspawn.py" in found   # patch 0019
    assert "tools/test_event_queue_destroy.py" in found   # patch 0021
    assert "tools/test_game_category.py" in found   # patch 0022


@pytest.mark.parametrize("runner", runners())
def test_ps3recomp_runner(patched_tree, runner):
    r = subprocess.run([sys.executable, "-E", "-s", runner], cwd=patched_tree, capture_output=True,
                       text=True, timeout=600)
    out = r.stdout + r.stderr
    if r.returncode == 0 and re.search(r"^SKIP\b", out, re.M):
        pytest.skip(f"{runner}: " + re.search(r"^SKIP\b.*$", out, re.M).group(0))
    assert r.returncode == 0, f"{runner} failed:\n{out[-4000:]}"

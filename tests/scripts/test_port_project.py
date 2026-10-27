# SPDX-License-Identifier: GPL-2.0-or-later
"""The port project (port/): configure-time guards, patch application, and the real build."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APPLY = REPO / "scripts" / "apply_ps3recomp_patches.sh"
CMAKE = shutil.which("cmake")
NINJA = shutil.which("ninja")

needs_cmake = pytest.mark.skipif(not (CMAKE and NINJA), reason="cmake and ninja not installed")


def configure(build, *defs):
    return subprocess.run([CMAKE, "-S", str(REPO), "-B", str(build), "-G", "Ninja", *defs],
                          capture_output=True, text=True)


@needs_cmake
def test_configure_refuses_tree_inside_repo(tmp_path):
    p = configure(tmp_path / "b", "-DGT6_BUILD_PORT=ON", f"-DGT6_TREE={REPO}/tmp-tree")
    assert p.returncode != 0
    assert "GT6_TREE must be outside the repository" in p.stderr, p.stderr
    assert not (REPO / "tmp-tree").exists()


@needs_cmake
def test_configure_refuses_stale_lift(tmp_path):
    tree = tmp_path / "tree with space"
    (tree / "recomp").mkdir(parents=True)
    (tree / "recomp" / "translate.json").write_text(json.dumps({
        "elf": "decrypted/x.elf", "elf_sha256": "0" * 64, "ps3recomp_commit": "0000000",
        "ps3recomp_patches": "0" * 64}))
    p = configure(tmp_path / "b", "-DGT6_BUILD_PORT=ON", f"-DGT6_TREE={tree}")
    assert p.returncode != 0
    assert "translated with a different ps3recomp" in p.stderr, p.stderr


@needs_cmake
def test_configure_refuses_lift_with_other_patches(tmp_path):
    commit = subprocess.run(["git", "-C", str(REPO / "third_party/ps3recomp"), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    tree = tmp_path / "tree"
    (tree / "recomp").mkdir(parents=True)
    (tree / "recomp" / "translate.json").write_text(json.dumps({
        "elf": "decrypted/x.elf", "elf_sha256": "0" * 64, "ps3recomp_commit": commit,
        "ps3recomp_patches": "f" * 64}))
    p = configure(tmp_path / "b", "-DGT6_BUILD_PORT=ON", f"-DGT6_TREE={tree}")
    assert p.returncode != 0
    assert "translated with a different ps3recomp" in p.stderr, p.stderr
    assert "patches" in p.stderr


@needs_cmake
def test_root_build_without_port_unchanged(tmp_path):
    b = tmp_path / "b"
    p = configure(b)
    assert p.returncode == 0, p.stderr
    targets = subprocess.run([NINJA, "-C", str(b), "-t", "targets", "all"],
                             capture_output=True, text=True, check=True).stdout
    names = {line.split(":")[0] for line in targets.splitlines()}
    assert "tools/gt6unpack/gt6unpack" in names
    assert not any(n == "port/gt6" or n.startswith("port/") for n in names)
    assert not any("ps3recomp" in n for n in names)


def test_patches_apply_check():
    p = subprocess.run(["bash", str(APPLY), "--check"], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert sorted((REPO / "patches" / "ps3recomp").glob("*.patch")), "no patches found"


def test_every_patch_names_its_upstream_status():
    for patch in sorted((REPO / "patches" / "ps3recomp").glob("*.patch")):
        assert "Upstream: not yet submitted" in patch.read_text().split("diff --git", 1)[0], patch


def test_apply_check_fails_on_a_patch_that_does_not_apply(tmp_path):
    patches = tmp_path / "patches"
    patches.mkdir()
    (patches / "0001-bad.patch").write_text(
        "Upstream: not yet submitted\n"
        "diff --git a/no/such/file.c b/no/such/file.c\n"
        "--- a/no/such/file.c\n+++ b/no/such/file.c\n@@ -1 +1 @@\n-x\n+y\n")
    env = dict(os.environ, GT6_PS3RECOMP_PATCHES=str(patches))
    p = subprocess.run(["bash", str(APPLY), "--check"], capture_output=True, text=True, env=env)
    assert p.returncode != 0
    assert "0001-bad.patch" in p.stdout + p.stderr


@pytest.mark.slow
@needs_cmake
@pytest.mark.skipif(not os.environ.get("GT6_TREE"), reason="GT6_TREE not set (needs the translated v1.22 tree)")
def test_real_port_builds():
    tree = Path(os.environ["GT6_TREE"])
    build = tree / "port-build"
    p = configure(build, "-DGT6_BUILD_PORT=ON", f"-DGT6_TREE={tree}", "-DCMAKE_BUILD_TYPE=Release")
    assert p.returncode == 0, p.stdout[-4000:] + p.stderr[-4000:]
    p = subprocess.run([CMAKE, "--build", str(build), "--target", "gt6"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout[-6000:] + p.stderr[-4000:]
    exe = build / "port" / "gt6"
    assert exe.is_file()
    p = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    assert p.returncode != 0
    assert "usage:" in (p.stdout + p.stderr)
    # /dev_hdd0 defaults to the play folder (D32), and a missing one stops the start.
    assert f'"{tree}/play/dev_hdd0"' in (build / "port" / "gt6_paths.h").read_text()
    env = dict(os.environ, PS3_HDD0_ROOT=str(tree / "no-such-play" / "dev_hdd0"))
    p = subprocess.run([str(exe), "unused.elf"], capture_output=True, text=True, timeout=30,
                       env=env)
    assert p.returncode != 0
    assert "scripts/prepare_play.py" in (p.stdout + p.stderr)


def test_port_runs_on_the_play_folder():
    """The port's /dev_hdd0 is <tree>/play/dev_hdd0, never the verified tree (D31, D32)."""
    cmake = (REPO / "port" / "CMakeLists.txt").read_text()
    assert 'gt6_c_string(GT6_DEFAULT_HDD0_ROOT "${GT6_TREE}/play/dev_hdd0")' in cmake
    main = (REPO / "port" / "main.cpp").read_text()
    assert "run scripts/prepare_play.py first" in main

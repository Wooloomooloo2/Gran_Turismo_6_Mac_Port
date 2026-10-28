# SPDX-License-Identifier: GPL-2.0-or-later
"""The port project (port/): configure-time guards, patch application, and the real build."""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
_spec = importlib.util.spec_from_file_location("translate_game", REPO / "scripts" / "translate_game.py")
translate_game = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(translate_game)
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


def sub_commit():
    return subprocess.run(["git", "-C", str(REPO / "third_party/ps3recomp"), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def fake_tree(tree, elf_bytes=b"elf", **spu_files):
    """A translated tree as far as configure reads it before the ps3recomp runtime: a
    translate.json with this checkout's commit and translate_game.patches_hash(), the ELF it
    names, ppu/ppu_recomp.h and one lifted source, and the given recomp/spu files."""
    elf = tree / "decrypted" / "x.elf"
    elf.parent.mkdir(parents=True)
    elf.write_bytes(elf_bytes)
    (tree / "recomp" / "ppu").mkdir(parents=True)
    (tree / "recomp" / "ppu" / "ppu_recomp.h").write_text("")
    (tree / "recomp" / "ppu" / "ppu_recomp_000.cpp").write_text("")
    (tree / "recomp" / "spu").mkdir()
    for name, text in spu_files.items():
        (tree / "recomp" / "spu" / name).write_text(text)
    (tree / "recomp" / "translate.json").write_text(json.dumps({
        "elf": "decrypted/x.elf", "elf_sha256": hashlib.sha256(elf_bytes).hexdigest(),
        "ps3recomp_commit": sub_commit(),
        "ps3recomp_patches": translate_game.patches_hash()}))
    return tree


@needs_cmake
def test_configure_accepts_the_patches_hash_translate_records(tmp_path):
    """CMake's hash of patches/ps3recomp equals translate_game.patches_hash() (item 10)."""
    tree = fake_tree(tmp_path / "tree")
    (tree / "decrypted" / "x.elf").unlink()          # stop at the next check
    p = configure(tmp_path / "b", "-DGT6_BUILD_PORT=ON", f"-DGT6_TREE={tree}")
    assert p.returncode != 0
    assert "translated with a different ps3recomp" not in p.stderr, p.stderr
    assert "The translated ELF is missing" in p.stderr, p.stderr


@needs_cmake
def test_configure_refuses_firmware_policy_bytes(tmp_path):
    """taskset_policy_bytes.c holds libsre firmware bytes: never compiled or linked (D27)."""
    tree = fake_tree(tmp_path / "tree", **{"taskset_policy_bytes.c": "/* firmware */"})
    p = configure(tmp_path / "b", "-DGT6_BUILD_PORT=ON", f"-DGT6_TREE={tree}")
    assert p.returncode != 0
    assert "taskset_policy_bytes.c" in p.stderr and "firmware" in p.stderr, p.stderr


@needs_cmake
def test_configure_refuses_any_git_work_tree(tmp_path):
    """GT6_TREE and the build folder must be outside every git work tree, through symlinks."""
    other = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    tree = fake_tree(other / "tree")
    p = configure(tmp_path / "b", "-DGT6_BUILD_PORT=ON", f"-DGT6_TREE={tree}")
    assert p.returncode != 0
    assert "git work tree" in p.stderr, p.stderr
    # A symlink outside the work tree pointing into it is refused as well.
    (tmp_path / "link").symlink_to(tree)
    p = configure(tmp_path / "b2", "-DGT6_BUILD_PORT=ON", f"-DGT6_TREE={tmp_path / 'link'}")
    assert p.returncode != 0
    assert "git work tree" in p.stderr, p.stderr
    # And so is a build folder inside one, by its real path.
    good = fake_tree(tmp_path / "tree")
    (other / "b").mkdir()
    (tmp_path / "blink").symlink_to(other / "b")
    p = configure(tmp_path / "blink", "-DGT6_BUILD_PORT=ON", f"-DGT6_TREE={good}")
    assert p.returncode != 0
    assert "git work tree" in p.stderr, p.stderr


def test_undo_hint_removes_the_files_the_patches_add():
    """A plain checkout leaves the patches' new files, and a later apply then fails (item 3)."""
    undo = "git -C third_party/ps3recomp checkout . && git -C third_party/ps3recomp clean -fd"
    assert undo in APPLY.read_text()
    assert "clean -fd" in (REPO / "port" / "CMakeLists.txt").read_text()


def test_apply_verify_needs_every_patch_applied(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    subprocess.run(["git", "init", "-q", str(sub)], check=True)
    (sub / "f.txt").write_text("a\n")
    patches = tmp_path / "patches"
    patches.mkdir()
    (patches / "0001-f.patch").write_text(
        "Upstream: not yet submitted\n"
        "diff --git a/f.txt b/f.txt\n--- a/f.txt\n+++ b/f.txt\n@@ -1 +1 @@\n-a\n+b\n")
    env = dict(os.environ, GT6_PS3RECOMP_PATCHES=str(patches), GT6_PS3RECOMP_DIR=str(sub))
    p = subprocess.run(["bash", str(APPLY), "--verify"], capture_output=True, text=True, env=env)
    assert p.returncode != 0 and "0001-f.patch" in p.stderr
    assert (sub / "f.txt").read_text() == "a\n"         # --verify changes nothing
    assert subprocess.run(["bash", str(APPLY)], env=env, capture_output=True).returncode == 0
    p = subprocess.run(["bash", str(APPLY), "--verify"], capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr


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
def test_real_port_builds(tmp_path):
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
    # A dev_hdd0 folder without the prepare.json beside it is refused too.
    bare = tmp_path / "bare"
    (bare / "dev_hdd0").mkdir(parents=True)
    env = dict(os.environ, PS3_HDD0_ROOT=str(bare / "dev_hdd0"))
    p = subprocess.run([str(exe), "unused.elf"], capture_output=True, text=True, timeout=30,
                       env=env)
    assert p.returncode != 0
    assert "prepare.json" in (p.stdout + p.stderr)
    # With the play folder prepared, the guest command line is the launch contract (D31).
    if (tree / "play" / "prepare.json").is_file():
        env = {k: v for k, v in os.environ.items()
               if k not in ("PS3_HDD0_ROOT", "PS3_BOOT_PATH", "PS3_ARGV")}
        p = subprocess.run([str(exe), str(tmp_path / "no-such.elf")], capture_output=True,
                           text=True, timeout=60, env=env)
        out = p.stdout + p.stderr
        assert p.returncode != 0   # the ELF does not exist; the line comes first
        assert ("[boot] guest argv: argc=2 /dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF "
                "/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF; envp empty") in out, out[-2000:]
        # /dev_hdd1 is the play folder's dev_hdd1, beside dev_hdd0, never the disc layer (D39).
        assert f"[boot] /dev_hdd1: {tree}/play/dev_hdd0/../dev_hdd1" in out, out[-2000:]
        assert (tree / "play" / "dev_hdd1").is_dir()


def test_port_runs_on_the_play_folder():
    """The port's /dev_hdd0 is <tree>/play/dev_hdd0, never the verified tree (D31, D32)."""
    cmake = (REPO / "port" / "CMakeLists.txt").read_text()
    assert 'gt6_c_string(GT6_DEFAULT_HDD0_ROOT "${GT6_TREE}/play/dev_hdd0")' in cmake
    main = (REPO / "port" / "main.cpp").read_text()
    assert "run scripts/prepare_play.py first" in main
    assert "prepare.json" in main and "S_ISDIR" in main
    # /dev_hdd1 (the cache partition) is mapped for both file layers, beside dev_hdd0 (D39).
    assert 'cellfs_add_path_mapping("/dev_hdd1/"' in main
    assert 'setenv("PS3_HDD1_ROOT"' in main and '"%s/../dev_hdd1"' in main


def test_port_passes_the_launch_contract():
    """argc 2, argv[0] = argv[1] = the EMAIN path, empty envp (FINDINGS, D31)."""
    main = (REPO / "port" / "main.cpp").read_text()
    assert '"/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF"' in main
    assert 'setenv("PS3_BOOT_PATH"' in main and 'setenv("PS3_ARGV"' in main

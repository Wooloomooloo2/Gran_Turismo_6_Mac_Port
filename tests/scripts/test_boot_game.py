# SPDX-License-Identifier: GPL-2.0-or-later
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import boot_game  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "boot"
REPO = Path(__file__).resolve().parents[2]
LOG = """# ps3recomp milestone log v1
0\tboot:start
1\tfs:open
kv\tspurs:groups\t3
2\tgcm:flip
# counts
count\tgcm:flip\t10-99
# end
"""


@pytest.fixture
def tree(tmp_path):
    t = tmp_path / "tree"
    (t / "play").mkdir(parents=True)
    (t / "play" / "prepare.json").write_text("{}")
    elf = t / boot_game.ELF_REL
    elf.parent.mkdir(parents=True)
    elf.write_bytes(b"x")
    return t


def fake(name, tmp_path):
    w = tmp_path / ("gt6_" + name)
    w.write_text(f"#!/bin/sh\nexec {sys.executable} {FIX / (name + '.py')} \"$@\"\n")
    w.chmod(0o755)
    return w


def test_parse_milestones():
    m = boot_game.parse_milestones(LOG)
    assert m == {"keys": ["boot:start", "fs:open", "gcm:flip"],
                 "kv": {"spurs:groups": 3}, "ended": True}


def test_parse_milestones_truncated():
    m = boot_game.parse_milestones("# ps3recomp milestone log v1\n0\ta\n1\tb")
    assert m["keys"] == ["a"] and not m["ended"]   # the last line may be half written


@pytest.mark.parametrize("rc,to,hung,keys,want", [
    (0, False, False, ["a", "gcm:flip"], "first_frame"),
    (-11, False, False, ["a", "gcm:flip"], "crashed"),
    (0, False, False, ["a"], "exited"),
    (None, True, False, ["gcm:flip"], "first_frame"),
    (None, True, False, ["a"], "timeout"),
    (None, False, True, ["a"], "hung"),
    (139, False, False, ["a"], "crashed"),
    (1, False, False, ["a"], "exited"),
])
def test_classify(rc, to, hung, keys, want):
    assert boot_game.classify(rc, to, hung, keys) == want


def pid_gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_boot_fake_hang_is_killed(tree, tmp_path):
    rep = boot_game.boot(fake("hang", tmp_path), tree, seconds=30, idle=2)
    assert rep["outcome"] == "hung"
    assert pid_gone(rep["pid"])
    assert rep["backtraces"].strip()


def test_boot_fake_crash(tree, tmp_path):
    rep = boot_game.boot(fake("crash", tmp_path), tree, seconds=30, idle=20)
    assert rep["outcome"] == "crashed"
    assert rep["last_keys"][-1] == "spurs:init"
    assert pid_gone(rep["pid"])


def test_boot_collects_unresolved(tree, tmp_path):
    rep = boot_game.boot(fake("unresolved", tmp_path), tree, seconds=30, idle=20)
    assert rep["outcome"] == "exited"
    assert rep["unresolved_nids"] == ["0x1234ABCD", "0xDEADBEEF"]
    assert rep["unimplemented_syscalls"] == [891]
    run = Path(rep["run"])
    assert json.loads((run / "report.json").read_text())["outcome"] == "exited"
    assert (run / "summary.md").read_text().startswith("The game")


def test_first_flip_stops_early_and_counts_frames(tree, tmp_path, monkeypatch):
    monkeypatch.setattr(boot_game, "FLIP_GRACE", 1.0)
    monkeypatch.setenv("FAKE_FRAME", "1")
    rep = boot_game.boot(fake("flip", tmp_path), tree, seconds=60, idle=30)
    assert rep["outcome"] == "first_frame"
    assert rep["seconds"] < 20
    assert rep["frames"] == 1
    assert pid_gone(rep["pid"])


def test_default_environment(tree, tmp_path):
    env = boot_game.build_env(tree, Path(tmp_path / "run"), True, None)
    assert env["PS3RECOMP_METAL_HEADLESS"] == "1"
    assert env["PS3_MILESTONE_OUT"].endswith("milestones.log")
    assert env["PS3RECOMP_METAL_FRAME_DUMP"].endswith("frames/frame.ppm")
    assert boot_game.build_env(tree, tmp_path, False, {"A": "b"})["A"] == "b"
    assert "PS3RECOMP_METAL_HEADLESS" not in boot_game.build_env(tree, tmp_path, False, None)


def test_refuses_tree_inside_repo():
    with pytest.raises(SystemExit) as e:
        boot_game.boot(Path("/bin/true"), REPO / "x")
    assert "inside a git work tree" in str(e.value)


def test_refuses_unprepared_play_folder(tree, tmp_path):
    (tree / "play" / "prepare.json").unlink()
    with pytest.raises(SystemExit) as e:
        boot_game.boot(fake("hang", tmp_path), tree)
    assert "prepare_play.py" in str(e.value)


@pytest.mark.slow
def test_real_smoke(tmp_path):
    tree = os.environ.get("GT6_TREE")
    if not tree:
        pytest.skip("GT6_TREE is not set")
    gt6 = Path(tree) / "port-build" / "port" / "gt6"
    if not gt6.is_file():
        pytest.skip(f"{gt6} is not built")
    rep = boot_game.boot(gt6, Path(tree), seconds=60, idle=60)
    assert rep["outcome"] in boot_game.OUTCOMES
    assert (Path(rep["run"]) / "report.json").is_file()

# SPDX-License-Identifier: GPL-2.0-or-later
import json
import os
import shutil
import sys
import time
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
                 "kv": {"spurs:groups": 3}, "counts": {"gcm:flip": "10-99"}, "ended": True}


def test_parse_milestones_truncated():
    m = boot_game.parse_milestones("# ps3recomp milestone log v1\n0\ta\n1\tb")
    assert m["keys"] == ["a"] and not m["ended"]   # the last line may be half written


@pytest.mark.parametrize("rc,to,hung,keys,frames,want", [
    (0, False, False, ["a", "gcm:flip"], 1, "first_frame"),
    (-11, False, False, ["a", "gcm:flip"], 1, "crashed"),
    (0, False, False, ["a"], 0, "exited"),
    (None, True, False, ["gcm:flip"], 1, "first_frame"),
    (None, True, False, ["a"], 0, "timeout"),
    (None, False, True, ["a"], 0, "hung"),
    (139, False, False, ["a"], 0, "crashed"),
    (1, False, False, ["a"], 0, "exited"),
    # A flip with no frame dumped is not a first frame (run 20261027-195826).
    (0, False, False, ["a", "gcm:flip"], 0, "flip_no_frame"),
    (None, False, False, ["gcm:flip"], 0, "flip_no_frame"),
])
def test_classify(rc, to, hung, keys, frames, want):
    assert want in boot_game.OUTCOMES
    assert boot_game.classify(rc, to, hung, keys, frames) == want


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
    assert rep["unresolved_nids"] == ["0x1234ABCD", "0xDEADBEEF", "0x0D5B4A14", "0x30AA96C4"]
    assert rep["unimplemented_syscalls"] == [891]
    assert rep["spu_interpreted"] == {"F523F26F69764538": "100-999", "CB9BD0241BB0DE67": "1"}
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


def test_flip_without_a_dump_is_not_a_first_frame(tree, tmp_path, monkeypatch):
    monkeypatch.setattr(boot_game, "FLIP_GRACE", 1.0)
    monkeypatch.delenv("FAKE_FRAME", raising=False)
    rep = boot_game.boot(fake("flip", tmp_path), tree, seconds=60, idle=30)
    assert rep["frames"] == 0
    assert rep["outcome"] == "flip_no_frame"
    assert boot_game.main([str(tree), "--gt6", str(fake("flip", tmp_path))]) == 1


def test_boot_records_itself_and_warns_on_a_used_play_folder(tree, tmp_path, capsys):
    rep = boot_game.boot(fake("crash", tmp_path), tree, seconds=30, idle=20)
    run = Path(rep["run"]).name
    rec = json.loads((tree / "play" / "prepare.json").read_text())
    assert rec["booted"] == run
    assert rep["play_reused"] is None
    assert "prepare_play.py" not in capsys.readouterr().err
    # A second boot on the same play folder still runs, but warns and says so in the report.
    rec["booted"] = "20000101-000000"
    (tree / "play" / "prepare.json").write_text(json.dumps(rec))
    rep = boot_game.boot(fake("crash", tmp_path), tree, seconds=30, idle=20)
    err = capsys.readouterr().err
    assert "20000101-000000" in err and "prepare_play.py" in err and "--force" in err
    assert rep["play_reused"] == "20000101-000000"
    assert json.loads((tree / "play" / "prepare.json").read_text())["booted"] == Path(rep["run"]).name
    assert "used by run 20000101-000000" in (Path(rep["run"]) / "summary.md").read_text()


def test_default_environment(tree, tmp_path, monkeypatch):
    monkeypatch.delenv("PS3RECOMP_METAL_FRAME_DUMP", raising=False)
    env = boot_game.build_env(tree, Path(tmp_path / "run"), True, None)
    assert env["PS3RECOMP_METAL_HEADLESS"] == "1"
    assert env["PS3_MILESTONE_OUT"].endswith("milestones.log")
    # The numbered series replaces milestone 2's single overwritten dump.
    assert env["PS3RECOMP_METAL_FRAME_DIR"] == str(tmp_path / "run" / "frames")
    assert env["PS3RECOMP_METAL_FRAME_EVERY"] == "60"
    assert env["PS3RECOMP_METAL_FRAME_MAX"] == "300"
    assert env["PS3RECOMP_DRAW_STATS"] == str(tmp_path / "run" / "draw_stats.txt")
    assert "PS3RECOMP_METAL_FRAME_DUMP" not in env
    env = boot_game.build_env(tree, tmp_path, True, None, frame_every=7, frame_max=9)
    assert env["PS3RECOMP_METAL_FRAME_EVERY"] == "7" and env["PS3RECOMP_METAL_FRAME_MAX"] == "9"
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


@pytest.mark.parametrize("rc,to,keys,frames,want", [
    (None, True, ["gcm:flip"], 3, "timeout"),     # ran to the end: frames kept, still timeout
    (None, True, ["a"], 0, "timeout"),
    (-11, False, ["gcm:flip"], 3, "crashed"),
    (0, False, ["gcm:flip"], 3, "exited"),        # ended by itself before the time was up
    (0, False, ["gcm:flip"], 0, "exited"),
    (0, False, ["a"], 0, "exited"),
])
def test_classify_time_mode(rc, to, keys, frames, want):
    assert boot_game.classify(rc, to, False, keys, frames, until="time") == want


def test_until_time_ignores_flip(tree, tmp_path, monkeypatch):
    monkeypatch.setattr(boot_game, "FLIP_GRACE", 0.5)
    rep = boot_game.boot(fake("series", tmp_path), tree, seconds=4, idle=30, until="time",
                         frame_every=10)
    assert rep["outcome"] == "timeout"
    assert 3.5 <= rep["seconds"] < 15
    assert rep["frames"] >= 2                      # present 1, 10, 20, ...
    assert rep["returncode"] is None
    assert rep["dump_stopped"] is None
    assert pid_gone(rep["pid"])
    names = [f["file"] for f in rep["frames_list"]]
    assert names[0] == "frame_000001.ppm" and names == sorted(names)
    assert rep["frames_list"][0]["presented"] == 1


def test_until_flip_keeps_stopping_early(tree, tmp_path, monkeypatch):
    monkeypatch.setattr(boot_game, "FLIP_GRACE", 1.0)
    rep = boot_game.boot(fake("series", tmp_path), tree, seconds=60, idle=30)
    assert rep["outcome"] == "first_frame" and rep["seconds"] < 20


def test_drawn_needs_draw_calls(tree, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NONZERO", "1")
    monkeypatch.setenv("FAKE_DRAWS", "0")
    rep = boot_game.boot(fake("series", tmp_path), tree, seconds=2, idle=30, until="time")
    assert rep["frames"] >= 1
    first = rep["frames_list"][0]
    assert first["draws"] == 0 and first["clears"] == 1
    assert first["nonzero_share"] == 1.0
    assert rep["drawn_frames"] == 0 and rep["first_drawn"] is None


def test_drawn_needs_non_black_pixels(tree, tmp_path, monkeypatch):
    monkeypatch.delenv("FAKE_NONZERO", raising=False)
    monkeypatch.setenv("FAKE_DRAWS", "12")
    rep = boot_game.boot(fake("series", tmp_path), tree, seconds=2, idle=30, until="time")
    assert rep["frames_list"][0]["nonzero_share"] == 0.0
    assert rep["drawn_frames"] == 0 and rep["first_drawn"] is None


def test_drawn_frame_counted(tree, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NONZERO", "1")
    monkeypatch.setenv("FAKE_DRAWS", "12")
    rep = boot_game.boot(fake("series", tmp_path), tree, seconds=2, idle=30, until="time")
    assert rep["frames_list"][0]["draws"] == 12
    assert rep["drawn_frames"] == rep["frames"] >= 1
    assert rep["first_drawn"] == 1
    assert "drawn" in (Path(rep["run"]) / "summary.md").read_text()


def test_frame_stats_and_share():
    stats = boot_game.parse_draw_stats("1 0 2\n2 12 3\nbad line\n3 4")
    assert stats == {1: (0, 2), 2: (12, 3)}       # a last line without newline is ignored
    assert boot_game.nonzero_share(b"P6\n2 2\n255\n" + b"\0\0\0" * 3 + b"\0\0\1") == 0.25
    assert boot_game.nonzero_share(b"P6\n# comment\n1 1\n255\n\5\0\0") == 1.0
    assert boot_game.nonzero_share(b"P6\n2 2\n255\n\0") is None   # truncated
    assert boot_game.nonzero_share(b"not a ppm") is None


def test_frame_bytes_cap_stops_dumping(tree, tmp_path):
    rep = boot_game.boot(fake("series", tmp_path), tree, seconds=3, idle=30, until="time",
                         frame_every=1, frame_bytes=200)
    assert rep["dump_stopped"] == "bytes"
    assert rep["outcome"] == "timeout" and rep["returncode"] is None   # not killed for it
    assert rep["seconds"] >= 2.5
    run = Path(rep["run"])
    assert (run / "frames" / "STOP").is_file()
    assert 1 <= rep["frames"] < 20                 # a present every 0.05 s, dumps stopped
    stats = boot_game.parse_draw_stats((run / "draw_stats.txt").read_text())
    assert len(stats) > rep["frames"]              # the stats go on
    assert "bytes" in (run / "summary.md").read_text()


def test_free_space_floor(tree, tmp_path, monkeypatch):
    real = shutil.disk_usage
    def low(path):
        u = real(path)
        return type(u)(u.total, u.total - 10 * 2**30, 10 * 2**30)
    monkeypatch.setattr(boot_game.shutil, "disk_usage", low)
    rep = boot_game.boot(fake("series", tmp_path), tree, seconds=2, idle=30, until="time",
                         frame_every=1)
    assert rep["dump_stopped"] == "disk"
    assert rep["frames"] == 0                      # below the floor before it started
    assert (Path(rep["run"]) / "frames" / "STOP").is_file()


def test_prune_keeps_ten(tree):
    runs = tree / "runs"
    names = [f"202610{d:02d}-120000" for d in range(1, 14)]
    for n in names:
        (runs / n).mkdir(parents=True)
        (runs / n / "report.json").write_text("{}")
    (runs / "eboot-effects").mkdir()               # not a run: never touched
    (runs / "notes.txt").write_text("x")
    removed = boot_game.prune_runs(runs, keep=10)
    assert sorted(p.name for p in removed) == names[:3]
    left = sorted(p.name for p in runs.iterdir())
    assert left == names[3:] + ["eboot-effects", "notes.txt"]
    assert boot_game.prune_runs(runs, keep=10) == []


def test_prune_flag_runs_after_the_boot(tree, tmp_path, monkeypatch):
    monkeypatch.setattr(boot_game, "FLIP_GRACE", 0.5)
    monkeypatch.setenv("FAKE_FRAME", "1")
    for d in range(1, 13):
        (tree / "runs" / f"200001{d:02d}-000000").mkdir(parents=True)
    assert boot_game.main([str(tree), "--gt6", str(fake("flip", tmp_path)), "--prune"]) == 0
    runs = sorted(p.name for p in (tree / "runs").iterdir())
    assert len(runs) == 10 and not runs[-1].startswith("2000")   # the new run is kept


def test_stop_file_write_failure_is_not_fatal(tree, tmp_path, monkeypatch):
    real = Path.write_text
    def failing(self, *a, **k):
        if self.name == boot_game.STOP_NAME:
            raise OSError(28, "No space left on device")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "write_text", failing)
    rep = boot_game.boot(fake("series", tmp_path), tree, seconds=2, idle=30, until="time",
                         frame_every=1, frame_bytes=200)
    assert rep["dump_stopped"] == "bytes"
    assert rep["outcome"] == "timeout"
    assert (Path(rep["run"]) / "report.json").is_file()
    assert not (Path(rep["run"]) / "frames" / boot_game.STOP_NAME).exists()


def test_prune_skips_symlinks_and_files(tree, tmp_path):
    runs = tree / "runs"
    names = [f"202610{d:02d}-120000" for d in range(1, 13)]
    for n in names:
        (runs / n).mkdir(parents=True)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("x")
    (runs / "20000101-000000").symlink_to(target)        # run-like name, a symlink
    (runs / "20000102-000000").write_text("not a run")   # run-like name, a regular file
    removed = boot_game.prune_runs(runs, keep=10)
    assert sorted(p.name for p in removed) == names[:2]
    assert (runs / "20000101-000000").is_symlink() and (target / "keep.txt").is_file()
    assert (runs / "20000102-000000").read_text() == "not a run"


def test_prune_survives_rmtree_errors(tree, monkeypatch, capsys):
    runs = tree / "runs"
    for d in range(1, 13):
        (runs / f"202610{d:02d}-120000").mkdir(parents=True)
    def boom(path, *a, **k):
        raise OSError(13, "Permission denied")
    monkeypatch.setattr(boot_game.shutil, "rmtree", boom)
    assert boot_game.prune_runs(runs, keep=10) == []
    assert "could not delete" in capsys.readouterr().err
    assert len(list(runs.iterdir())) == 12


def test_group_killed_on_timeout_in_time_mode(tree, tmp_path, monkeypatch):
    pidfile = tmp_path / "child.pid"
    monkeypatch.setenv("FAKE_CHILD_PID", str(pidfile))
    rep = boot_game.boot(fake("series", tmp_path), tree, seconds=2, idle=30, until="time")
    assert rep["outcome"] == "timeout"
    child = int(pidfile.read_text())
    assert pid_gone(rep["pid"])
    for _ in range(50):                            # reparented to launchd, reaped soon
        if pid_gone(child):
            break
        time.sleep(0.1)
    assert pid_gone(child)


@pytest.mark.skipif(shutil.which("sips") is None, reason="sips is macOS only")
def test_png_flag_converts_frames(tree, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NONZERO", "1")
    rc = boot_game.main([str(tree), "--gt6", str(fake("series", tmp_path)), "--until", "time",
                         "--seconds", "2", "--frame-every", "5", "--frame-max", "3", "--png"])
    run = sorted((tree / "runs").iterdir())[-1]
    rep = json.loads((run / "report.json").read_text())
    assert rc == 0                                 # time mode: a frame was presented and kept
    assert rep["frames"] == 3                      # --frame-max reached the runtime
    pngs = sorted(p.name for p in (run / "frames_png").iterdir())
    assert pngs == [f["file"].replace(".ppm", ".png") for f in rep["frames_list"]]
    assert (run / "frames_png" / pngs[0]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


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


def test_parse_press_and_pad_script():
    """--press S:BUTTON maps to ps3recomp's PAD_SCRIPT masks (CELL_PAD_CTRL_*, D40)."""
    assert boot_game.parse_press("480:cross") == (480.0, "cross", 1)
    assert boot_game.parse_press("2.5:START") == (2.5, "start", 1)
    assert boot_game.parse_press("2@30:cross") == (30.0, "cross", 2)
    for bad in ("cross", "10:", "10:x", "-1:cross", "abc:cross", "inf:cross", "nan:cross",
                "0@5:cross", "x@5:cross"):
        with pytest.raises(ValueError):
            boot_game.parse_press(bad)
    assert boot_game.pad_script([(30, "start"), (2.5, "cross")]) == "2.5:0x4000,30:0x0008"
    # each image gets only its own presses (Task 5 batch 1 review, I3)
    assert boot_game.press_env([(30, "start", 1), (5, "cross", 2), (2.5, "cross", 1)]) == {
        "PAD_SCRIPT": "2.5:0x4000,30:0x0008", "GT6_PAD_SCRIPT_IMAGE2": "5:0x4000"}
    assert boot_game.press_env([(5, "cross", 2)]) == {"GT6_PAD_SCRIPT_IMAGE2": "5:0x4000"}
    # the masks are cellPad.h's: START is DIGITAL1 bit 3, CROSS DIGITAL2 bit 6
    assert boot_game.PAD_BUTTONS["start"] == 1 << 3 and boot_game.PAD_BUTTONS["cross"] == 1 << 14
    assert boot_game.PAD_BUTTONS["circle"] == 1 << 13 and boot_game.PAD_BUTTONS["select"] == 1


def test_press_reaches_the_game_and_the_report(tree, tmp_path):
    rc = boot_game.main([str(tree), "--gt6", str(fake("padenv", tmp_path)), "--until", "time",
                         "--seconds", "2", "--press", "45:cross", "--press", "5:start"])
    run = sorted((tree / "runs").iterdir())[-1]
    assert rc == 0
    assert "PAD_SCRIPT=5:0x0008,45:0x4000" in (run / "stdout.log").read_text()
    rep = json.loads((run / "report.json").read_text())
    assert rep["presses"] == [{"image": 1, "seconds": 5.0, "button": "start"},
                              {"image": 1, "seconds": 45.0, "button": "cross"}]
    assert "Pad presses" in (run / "summary.md").read_text()


def test_bad_press_is_a_usage_error(tree, tmp_path):
    with pytest.raises(SystemExit) as e:
        boot_game.main([str(tree), "--gt6", str(fake("padenv", tmp_path)), "--press", "5:jump"])
    assert e.value.code == 2
    assert not (tree / "runs").exists() or not any((tree / "runs").iterdir())


def test_exit_spawned_image_is_reported(tree, tmp_path):
    """An image the game exit-spawns (D41) writes under spawn<n>; the report keeps both."""
    rc = boot_game.main([str(tree), "--gt6", str(fake("spawn", tmp_path)), "--until", "time",
                         "--seconds", "2", "--png"])
    run = sorted((tree / "runs").iterdir())[-1]
    rep = json.loads((run / "report.json").read_text())
    assert rc == 0 and rep["frames"] == 1 and rep["drawn_frames"] == 1
    assert len(rep["spawns"]) == 1
    sp = rep["spawns"][0]
    assert sp["image"] == 2 and sp["flipped"] and sp["frames"] == 2 and sp["drawn_frames"] == 1
    assert sp["last_keys"][-1] == "hle:cellPadInit"
    assert (run / "frames_png" / "spawn1" / "frame_000061.png").is_file()
    assert "Image 2 (after an exit-spawn" in (run / "summary.md").read_text()


def test_stop_file_reaches_spawned_images(tmp_path):
    frames = tmp_path / "frames"
    (frames / "spawn1").mkdir(parents=True)
    (frames / "spawn10").mkdir()
    (frames / "spawnx").mkdir()
    assert [d.name for d in boot_game.spawn_dirs(frames)] == ["spawn1", "spawn10"]
    (frames / "spawn1" / "frame_000001.ppm").write_bytes(b"x" * 100)
    assert boot_game._frames_bytes(frames) == 100
    boot_game._stop_dumps(frames, "bytes")
    assert (frames / boot_game.STOP_NAME).is_file() and (frames / "spawn10" / boot_game.STOP_NAME).is_file()

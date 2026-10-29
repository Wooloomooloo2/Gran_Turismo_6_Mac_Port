# SPDX-License-Identifier: GPL-2.0-or-later
"""prepare_play.py clones the verified tree into <tree>/play and applies the 1.22 EBOOT's
on-disk effects there (FINDINGS, "What the 1.22 EBOOT leaves on disk"; D31, D32)."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "prepare_play.py"
sys.path.insert(0, str(REPO / "scripts"))

_spec = importlib.util.spec_from_file_location("prepare_play", SCRIPT)
prepare_play = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prepare_play)

GAME = "dev_hdd0/game/BCES01977/USRDIR"
HASH = "0123456789abcdef0123456789abcdef"  # invented 16-byte digest, as text


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def line7(i, size, typ, ref, flag, size7):
    return f"{i:06d} {size:010d} {typ} {ref:06d} {HASH} {flag} {size7:010d}\n"


def line8(i, size, typ, ref, flag, size7, size8):
    return f"{i:06d} {size:010d} {typ} {ref:06d} {HASH} {flag} {size7:010d} {size8:010d}\n"


def make_tree(root):
    """A fake gt6unpack tree with invented values in the layout the EBOOT reads."""
    u = root / GAME
    (u / "PDIPFS" / "9").mkdir(parents=True)
    (u / "UPDATENODEINFO").mkdir()
    ids = list(range(40000, 40010))
    old = "".join(line7(i, 100 + i % 7, 0, i - 100, 0, 100 + i % 7) for i in ids)
    new = [line8(i, 100 + i % 7, 0, i - 100, 0, 100 + i % 7, 100 + i % 7) for i in ids]
    new[8] = line8(ids[8], 100 + ids[8] % 7, 0, ids[8] - 100, 0, 100 + ids[8] % 7, 55)
    for v in ("07", "12"):
        t = u / f"TPPS-01.{v}"
        (t / "PDIPFS" / "K").mkdir(parents=True)
        (t / "PDIPFS" / "K" / "4D").write_bytes(b"k")
        (t / "PDIPFS" / "UPDATENODEINFO").write_text(old)
        (t / "update.txt").write_text("01.06 01.07" if v == "07" else "99.98 99.99")
    (u / "UPDATENODEINFO" / "UPDATENODEINFO.0107").write_text("".join(new))
    # The second entry's file is already in the main PDIPFS with its new size: dropped.
    target = u / "PDIPFS" / prepare_play.node_name(ids[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x" * (100 + ids[1] % 7))
    (root / "build.json").write_text(json.dumps(
        {"tool": "gt6unpack", "tool_version": "0.1.0", "title_id": "BCES01977",
         "final_app_ver": "01.22"}))
    return ids, old, new


def test_node_name_matches_the_eboot():
    # The six names the 1.22 EBOOT stats for TPPS-01.09 (RPCS3 log), and K/4D.
    assert [prepare_play.node_name(i) for i in range(42258, 42264)] == [
        "9/JF/OC", "9/VQ/95", "9/BB/BN", "9/8V/CZ", "9/M2/MG", "9/QD/OS"]
    assert prepare_play.node_name(1) == "K/4D"


def test_merge_keeps_tpps_records_after_six_kept_and_drops_installed():
    a =[prepare_play.parse_node_line(l) for l in
         [line7(i, 10, 0, 1, 0, 10) for i in range(9)]]
    b = [prepare_play.parse_node_line(l) for l in
         [line8(i, 10, 0, 1, 0, 10, 77) for i in range(9)]]
    sizes = {prepare_play.node_name(2): 10}   # entry 2 is already installed (size == col 2)
    out = prepare_play.merge_node_info(a, b, lambda name: sizes.get(name))
    # 0,1 from B; 2 dropped; 3..6 from B (6 kept then); 7,8 from A (col 8 = col 7).
    assert [e[0] for e in out] == [0, 1, 3, 4, 5, 6, 7, 8]
    assert [e[7] for e in out] == [77, 77, 77, 77, 77, 77, 10, 10]
    assert prepare_play.format_node_line(out[0]) == line8(0, 10, 0, 1, 0, 10, 77)


def test_prepare_clones_and_applies(tmp_path):
    tree = tmp_path / "tree"
    ids, old, new = make_tree(tree)
    before = {p: sha(p) for p in tree.rglob("*") if p.is_file()}
    result = prepare_play.prepare(tree)
    play = tree / "play" / GAME
    # The verified tree is untouched.
    assert {p: sha(p) for p in tree.rglob("*") if p.is_file() and "play" not in p.parts} == before
    assert (play / "TPPS-01.07" / "update.txt").read_text() == "99.98 99.99"
    assert (play / "TPPS-01.12" / "update.txt").read_text() == "99.98 99.99"
    # 01.07 merged: entry 1 dropped (installed), entries kept until 6, then TPPS records.
    expect = [new[0]] + new[2:7] + [old.splitlines(keepends=True)[k].rstrip("\n") +
                                    " " + old.splitlines()[k].split()[6] + "\n" for k in (7, 8, 9)]
    assert (play / "TPPS-01.07" / "PDIPFS" / "UPDATENODEINFO").read_text() == "".join(expect)
    assert not (play / "TPPS-01.07" / "PDIPFS" / "UPDATENODEINFO.upd").exists()
    # 01.12 has no UPDATENODEINFO.0112: untouched.
    assert (play / "TPPS-01.12" / "PDIPFS" / "UPDATENODEINFO").read_text() == old
    rec = json.loads((tree / "play" / "prepare.json").read_text())
    assert rec["source"]["build_json_sha256"] == sha(tree / "build.json")
    assert rec["source"]["final_app_ver"] == "01.22"
    assert [a["path"] for a in rec["applied"]] == [
        f"{GAME}/TPPS-01.07/update.txt", f"{GAME}/TPPS-01.07/PDIPFS/UPDATENODEINFO"]
    assert rec["applied"][1]["dropped"] == [ids[1]]
    assert rec["applied"][1]["sha256"] == sha(play / "TPPS-01.07" / "PDIPFS" / "UPDATENODEINFO")
    assert "time" in rec and rec == result


def test_refuses_existing_play_without_force(tmp_path):
    tree = tmp_path / "tree"
    make_tree(tree)
    prepare_play.prepare(tree)
    marker = tree / "play" / GAME / "TPPS-01.07" / "update.txt"
    marker.write_text("changed by a first run")
    with pytest.raises(SystemExit, match="--force"):
        prepare_play.prepare(tree)
    assert marker.read_text() == "changed by a first run"
    prepare_play.prepare(tree, force=True)
    assert marker.read_text() == "99.98 99.99"


def test_force_refuses_a_folder_this_tool_did_not_make(tmp_path):
    tree = tmp_path / "tree"
    make_tree(tree)
    (tree / "play").mkdir()
    (tree / "play" / "keep.txt").write_text("not ours")
    with pytest.raises(SystemExit, match="prepare.json"):
        prepare_play.prepare(tree, force=True)
    assert (tree / "play" / "keep.txt").read_text() == "not ours"
    # A prepare.json written by something else does not count either.
    (tree / "play" / "prepare.json").write_text('{"tool": "something else"}')
    with pytest.raises(SystemExit, match="prepare.json"):
        prepare_play.prepare(tree, force=True)
    assert (tree / "play" / "keep.txt").read_text() == "not ours"


def test_force_refuses_a_play_folder_that_is_a_symlink(tmp_path):
    """A symlinked play folder is refused, not followed (review M-5): --force would
    otherwise delete and replace the link's target, a play folder of another tree."""
    tree = tmp_path / "tree"
    make_tree(tree)
    other = tmp_path / "other"
    make_tree(other)
    prepare_play.prepare(other)
    target = other / "play"
    marker = target / GAME / "TPPS-01.07" / "update.txt"
    marker.write_text("another tree's first run")
    (tree / "play-x").symlink_to(target)
    with pytest.raises(SystemExit, match="symlink"):
        prepare_play.prepare(tree, out=tree / "play-x", force=True)
    with pytest.raises(SystemExit, match="symlink"):
        prepare_play.main([str(tree), "--force", "--name", "play-x"])
    assert (tree / "play-x").is_symlink()
    assert marker.read_text() == "another tree's first run"


def test_force_never_deletes_the_tree_or_its_ancestors(tmp_path):
    tree = tmp_path / "tree"
    make_tree(tree)
    for target in (tree, tmp_path):
        (target / "prepare.json").write_text('{"tool": "scripts/prepare_play.py"}')
        with pytest.raises(SystemExit, match="verified tree"):
            prepare_play.prepare(tree, out=target, force=True)
        assert (tree / "build.json").is_file()


def test_failure_leaves_no_half_prepared_folder(tmp_path, monkeypatch):
    tree = tmp_path / "tree"
    make_tree(tree)

    def boom(root):
        raise RuntimeError("interrupted")

    monkeypatch.setattr(prepare_play, "apply_eboot_effects", boom)
    with pytest.raises(RuntimeError):
        prepare_play.prepare(tree)
    assert not (tree / "play").exists()
    assert sorted(p.name for p in tree.iterdir()) == ["build.json", "dev_hdd0"]
    # An existing play folder survives a failed --force.
    monkeypatch.undo()
    prepare_play.prepare(tree)
    first = (tree / "play" / "prepare.json").read_text()
    monkeypatch.setattr(prepare_play, "apply_eboot_effects", boom)
    with pytest.raises(RuntimeError):
        prepare_play.prepare(tree, force=True)
    assert (tree / "play" / "prepare.json").read_text() == first
    assert sorted(p.name for p in tree.iterdir()) == ["build.json", "dev_hdd0", "play"]


def test_cli_has_no_out_option(tmp_path):
    tree = tmp_path / "tree"
    make_tree(tree)
    r = subprocess.run([sys.executable, str(SCRIPT), str(tree), "--out", str(tmp_path / "x")],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "--out" in r.stderr
    assert not (tmp_path / "x").exists()


def test_cli_name_makes_a_sibling_play_folder(tmp_path):
    """D49: --name play-SUFFIX makes <tree>/play-SUFFIX and leaves <tree>/play alone."""
    tree = tmp_path / "tree"
    make_tree(tree)
    r = subprocess.run([sys.executable, str(SCRIPT), str(tree)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    before = (tree / "play" / "prepare.json").read_text()
    r = subprocess.run([sys.executable, str(SCRIPT), str(tree), "--name", "play-fresh-1"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads((tree / "play-fresh-1" / "prepare.json").read_text())["tool"] == prepare_play.TOOL
    assert (tree / "play-fresh-1" / "dev_hdd0").is_dir()
    assert (tree / "play" / "prepare.json").read_text() == before
    r = subprocess.run([sys.executable, str(SCRIPT), str(tree), "--name", "play-fresh-1"],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "--force" in r.stderr


@pytest.mark.parametrize("name", ["../play-x", "/tmp/play-x", "play/x", "other", "playx",
                                  "play-", "", "dev_hdd0", "play-a/../../x",
                                  "play-.", "play-..", "play--x", "play-.x"])
def test_name_must_be_a_play_folder_name(tmp_path, name):
    tree = tmp_path / "tree"
    make_tree(tree)
    with pytest.raises(SystemExit, match="play folder name"):
        prepare_play.play_folder(tree, name or "x y")
    r = subprocess.run([sys.executable, str(SCRIPT), str(tree), "--name", name or "x y"],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "play folder name" in r.stderr
    assert sorted(p.name for p in tree.iterdir()) == ["build.json", "dev_hdd0"]


def test_play_folder_default(tmp_path):
    assert prepare_play.play_folder(tmp_path) == tmp_path.resolve() / "play"
    assert prepare_play.play_folder(tmp_path, "play-b4.1") == tmp_path.resolve() / "play-b4.1"


def test_refuses_output_inside_a_git_work_tree(tmp_path):
    tree = tmp_path / "tree"
    make_tree(tree)
    with pytest.raises(SystemExit, match="git work tree"):
        prepare_play.prepare(tree, out=REPO / "build" / "play-test")
    assert not (REPO / "build" / "play-test").exists()


def test_cli(tmp_path):
    tree = tmp_path / "tree"
    make_tree(tree)
    r = subprocess.run([sys.executable, str(SCRIPT), str(tree)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (tree / "play" / "prepare.json").is_file()
    r = subprocess.run([sys.executable, str(SCRIPT), str(tree)], capture_output=True, text=True)
    assert r.returncode != 0 and "--force" in r.stderr
    r = subprocess.run([sys.executable, str(SCRIPT), str(tree), "--force"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# SHA-256 of the files the real 1.22 EBOOT produced under RPCS3 (FINDINGS run 1).
EBOOT_RESULTS = {
    "TPPS-01.07/update.txt": "3365e309d248f7b70fddf5d520c7b589860b764377c832a10929ea54171019d8",
    "TPPS-01.07/PDIPFS/UPDATENODEINFO": "631f3a178020740d3525dbc20f3a2b6d902a834343b9e348dbdbe372cf770b83",
    "TPPS-01.08/PDIPFS/UPDATENODEINFO": "db0b7ebe68d058cd7840d69036e62568f5210adbfe59bce68238d9b822f91fb3",
    "TPPS-01.09/PDIPFS/UPDATENODEINFO": "dbc8a8b9f0c9a34acbf611f6334a74d77eacdb8e619ce64ceb37eabd2a65ce1f",
    "TPPS-01.10/PDIPFS/UPDATENODEINFO": "2e58124ebec7261b9fce4494ee474d3094c66f9e76ad3676d7828e1a59d82788",
    "TPPS-01.11/PDIPFS/UPDATENODEINFO": "44faf0dd2885cd61a9a3963dfbf16917a0dc81cd025d5010cf10fad381e9168d",
}


@pytest.mark.slow
@pytest.mark.skipif(not os.environ.get("GT6_TREE"), reason="GT6_TREE not set (needs the built v1.22 tree)")
def test_real_tree_matches_the_eboot(tmp_path):
    tree = Path(os.environ["GT6_TREE"])
    out = tmp_path / "play"
    rec = prepare_play.prepare(tree, out=out)
    usr = out / GAME
    for rel, digest in EBOOT_RESULTS.items():
        assert sha(usr / rel) == digest, rel
    assert len(rec["applied"]) == 6
    assert all(a["dropped"] == [] for a in rec["applied"][1:])


def test_leftovers_of_a_killed_run_are_ours_only_with_prepare_json_or_marker(tmp_path):
    """A run killed after the staging marker is dropped (prepare.json written, renames not
    done) leaves a staging folder that is still ours; a .play.old is removed only if ours."""
    tree = tmp_path / "tree"
    make_tree(tree)
    prepare_play.prepare(tree)
    staging, old = tree / ".play.staging", tree / ".play.old"
    staging.mkdir()
    (staging / "prepare.json").write_text('{"tool": "scripts/prepare_play.py"}')
    prepare_play.prepare(tree, force=True)
    assert not staging.exists()
    # A .play.old that is not ours is refused before anything is changed.
    old.mkdir()
    (old / "keep.txt").write_text("not ours")
    first = (tree / "play" / "prepare.json").read_text()
    with pytest.raises(SystemExit, match="not made by"):
        prepare_play.prepare(tree, force=True)
    assert (old / "keep.txt").read_text() == "not ours"
    assert (tree / "play" / "prepare.json").read_text() == first
    assert not staging.exists()
    # One that is ours (left between the two renames) is replaced.
    (old / "keep.txt").unlink()
    (old / "prepare.json").write_text('{"tool": "scripts/prepare_play.py"}')
    prepare_play.prepare(tree, force=True)
    assert not old.exists() and not staging.exists()


def test_force_discards_saves_and_trophies(tmp_path):
    """D50: saves and trophies live in the play folder, so --force starts with none."""
    tree = tmp_path / "tree"
    make_tree(tree)
    prepare_play.prepare(tree)
    save = tree / "play" / "dev_hdd0" / "home" / "00000001" / "savedata" / "X-GAME6" / "D"
    save.parent.mkdir(parents=True)
    save.write_text("s")
    (tree / "play" / "trophies").mkdir()
    (tree / "play" / "trophies" / "NPWR00000.json").write_text("{}")
    prepare_play.prepare(tree, force=True)
    assert not (tree / "play" / "dev_hdd0" / "home").exists()
    assert not (tree / "play" / "trophies").exists()


def test_play_names_with_a_dotted_suffix_are_accepted(tmp_path):
    """Final review m-6: a suffix may hold dots, but not start with one."""
    tree = tmp_path / "tree"
    make_tree(tree)
    assert prepare_play.play_folder(tree, "play-fresh-20261028.1") == tree / "play-fresh-20261028.1"
    assert prepare_play.play_folder(tree, "play-x") == tree / "play-x"


def test_disc_layer_write_access_by_acl_counts(tmp_path, monkeypatch):
    """Final review m-7: a disc layer whose mode bits are read-only but which the host still
    lets this user write (an ACL) counts as writable."""
    root = tmp_path / "dev_bdvd"
    root.mkdir()
    (root / "f").write_text("x")
    try:
        for p in (root / "f", root):
            p.chmod(0o555 if p.is_dir() else 0o444)
        assert prepare_play.disc_layer_writable(tmp_path) is None
        monkeypatch.setattr(prepare_play.os, "access", lambda path, mode: True)
        assert "is writable" in prepare_play.disc_layer_writable(tmp_path)
    finally:
        for p in (root, root / "f"):
            p.chmod(0o755 if p.is_dir() else 0o644)

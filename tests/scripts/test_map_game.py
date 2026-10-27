# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "map_game.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"

_spec = importlib.util.spec_from_file_location("map_game", SCRIPT)
map_game = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(map_game)


def by_path(summary, suffix):
    return next(e for e in summary["elfs"] if e["path"].endswith(suffix))


# ---- summarize: the pure function over tool outputs ----

def test_summarize_totals_match_fixtures():
    s = map_game.summarize(FIXTURES)
    assert [e["path"] for e in s["elfs"]] == [
        "dev_hdd0/USRDIR/EBOOT.BIN.elf", "dev_hdd0/USRDIR/EMAIN.SELF.elf"]
    assert s["totals"] == {
        "functions": 3 + 5,
        "imports": 3 + 6,
        "unresolved_nids": 1 + 2,
        "spu_images": 2,
        "spu_bytes": 17400 + 21332,
        "jobmods": 2,
        "jobmod_bytes": 10896 + 4880,
    }


def test_summarize_per_elf_fields():
    s = map_game.summarize(FIXTURES)
    emain = by_path(s, "EMAIN.SELF.elf")
    assert emain["functions"] == 5
    assert emain["opd_functions"] == 4
    assert emain["imports"] == {"cellSpurs": 3, "cellGcmSys": 1, "sys_fs": 1, "cellSail": 1}
    assert list(emain["imports"]) == ["cellSpurs", "cellGcmSys", "cellSail", "sys_fs"]
    assert emain["unresolved_nids"] == 2
    assert emain["unresolved_by_module"] == {"cellSail": 1, "cellSpurs": 1}
    assert emain["spu_images"] == [{"name": "spu_0000_at_01286F00.elf", "size": 17400},
                                   {"name": "spu_0001_at_013F9580.elf", "size": 21332}]
    assert emain["jobmods"] == 2
    assert emain["jobmod_bytes"] == 15776
    assert emain["bytes"] == 5000 and emain["sha256"] == "bb"
    assert "error" not in emain


def test_summarize_reports_tool_failures():
    s = map_game.summarize(FIXTURES)
    assert by_path(s, "EMAIN.SELF.elf")["tool_failures"] == ["extract_spu_images"]
    assert by_path(s, "EBOOT.BIN.elf")["tool_failures"] == []


def test_summarize_carries_identity_and_run_info():
    s = map_game.summarize(FIXTURES)
    assert len(s["identity"]) == 3
    assert s["run_seconds"] == 12.5
    assert s["ps3recomp_commit"] == "4e8f3ca87a3e1d87bb83b8b7e9348fe2685cd514"


def test_missing_tool_output_gives_error_not_crash(tmp_path):
    work = tmp_path / "map"
    shutil.copytree(FIXTURES, work)
    (work / "EMAIN_SELF" / "functions.json").unlink()
    (work / "EMAIN_SELF" / "spu_images.json").unlink()
    s = map_game.summarize(work)
    emain = by_path(s, "EMAIN.SELF.elf")
    assert "functions.json" in emain["error"]
    assert "spu_images.json" in emain["error"]
    assert emain["functions"] is None
    assert emain["spu_images"] is None
    assert emain["imports"]["cellSpurs"] == 3          # what is there is still read
    assert "error" not in by_path(s, "EBOOT.BIN.elf")
    assert s["totals"]["functions"] == 3                 # only the ELF that has it
    assert s["totals"]["spu_images"] == 0
    assert s["totals"]["imports"] == 9


def test_unreadable_tool_output_gives_error(tmp_path):
    work = tmp_path / "map"
    shutil.copytree(FIXTURES, work)
    (work / "EBOOT_BIN" / "imports_named.json").write_text("{not json")
    eboot = by_path(map_game.summarize(work), "EBOOT.BIN.elf")
    assert "imports_named.json" in eboot["error"]
    assert eboot["imports"] is None


def test_summarize_empty_dir(tmp_path):
    s = map_game.summarize(tmp_path)
    assert s["elfs"] == []
    assert s["totals"]["functions"] == 0


# ---- helpers used by the real run ----

def jobmod(entry, image_size, fill=b"\x11"):
    """A WWS job module header as ps3recomp's extract_jobmods.py defines it."""
    h = bytearray(0x30)
    h[0] = 0x42
    struct.pack_into(">II", h, 0x10, entry, image_size)
    h[0x20:0x24] = b"\xc0\xde\xc0\xde"
    return bytes(h) + fill * (image_size - 32 - 0x30)


def test_find_embedded_jobmods():
    m1 = jobmod(0x30, 0x200)
    m2 = jobmod(0x40, 0x120, b"\x22")
    buf = b"\0" * 0x100 + m1 + b"\0" * 0x50 + m2 + b"\0" * 0x40
    found = map_game.find_embedded_jobmods(buf)
    assert [(o, len(b)) for o, b in found] == [(0x100, 0x200 - 32), (0x100 + len(m1) + 0x50, 0x120 - 32)]
    assert found[0][1] == m1


def test_find_embedded_jobmods_ignores_bad_headers():
    good = jobmod(0x30, 0x100)
    bad_lead = b"\x00" + good[1:]                      # not an ila
    too_big = good[:0x14] + struct.pack(">I", 0x10000000) + good[0x18:]
    assert map_game.find_embedded_jobmods(bad_lead) == []
    assert map_game.find_embedded_jobmods(too_big) == []
    assert map_game.find_embedded_jobmods(b"\xc0\xde\xc0\xde") == []


def test_jobmod_name_matches_ps3recomp_convention():
    m = jobmod(0x30, 0x100)
    h = hashlib.sha1(m).hexdigest()[:12]
    assert map_game.jobmod_name(m) == f"jobmod_{h}_e0030.bin"


def test_identity_groups_identical_files(tmp_path):
    dec = tmp_path / "decrypted"
    (dec / "a").mkdir(parents=True)
    (dec / "b").mkdir()
    (dec / "a" / "X.elf").write_bytes(b"same")
    (dec / "b" / "X.elf").write_bytes(b"same")
    (dec / "b" / "Y.elf").write_bytes(b"other")
    ident = map_game.identity(dec, mapped={dec / "a" / "X.elf"})
    rows = {r["path"]: r for r in ident}
    assert rows["a/X.elf"]["same_as"] == ["b/X.elf"]
    assert rows["a/X.elf"]["mapped"] is True
    assert rows["b/X.elf"]["mapped"] is False
    assert rows["b/Y.elf"]["same_as"] == []
    assert rows["b/Y.elf"]["bytes"] == 5
    assert rows["b/Y.elf"]["sha256"] == hashlib.sha256(b"other").hexdigest()


def test_slug_avoids_ignored_suffixes():
    s = map_game.slug("dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF.elf")
    assert s == "dev_hdd0__game__BCES01977__USRDIR__EMAIN_SELF"
    assert not s.lower().endswith((".elf", ".self"))


def test_default_elfs_are_the_launched_pair(tmp_path):
    assert map_game.default_elfs(tmp_path) == [
        tmp_path / "decrypted/dev_hdd0/game/BCES01977/USRDIR/EBOOT.BIN.elf",
        tmp_path / "decrypted/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF.elf",
    ]


# ---- command line ----

def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)


def test_cli_refuses_output_inside_repo(tmp_path):
    (tmp_path / "decrypted").mkdir()
    r = run_cli(tmp_path, "-o", REPO / "out-map-test")
    assert r.returncode == 2
    assert "inside the repository" in r.stderr
    assert not (REPO / "out-map-test").exists()


def test_cli_reports_missing_elf(tmp_path):
    (tmp_path / "decrypted").mkdir()
    r = run_cli(tmp_path, "--elf", tmp_path / "decrypted" / "nope.elf")
    assert r.returncode == 2
    assert "nope.elf" in r.stderr


@pytest.mark.skipif(not (REPO / "third_party/ps3recomp/tools/ppu_loader.py").exists(),
                    reason="ps3recomp submodule not checked out")
def test_cli_runs_tools_on_a_tiny_elf(tmp_path):
    """End to end on a synthetic ELF: no game data. The tools must run and the
    summary must be written, even though they find almost nothing."""
    out = tmp_path / "build"
    dec = out / "decrypted"
    dec.mkdir(parents=True)
    elf = dec / "tiny.elf"
    elf.write_bytes(tiny_ppu_elf())
    r = run_cli(out, "--elf", elf)
    assert r.returncode == 0, r.stderr
    s = json.loads((out / "map" / "summary.json").read_text())
    (e,) = s["elfs"]
    assert e["path"] == "tiny.elf"
    assert e["imports"] == {}
    assert e["spu_images"] == []
    assert e["jobmods"] == 0
    tools = json.loads((out / "map" / "tiny" / "tools.json").read_text())
    assert set(tools) == {"ppu_loader", "find_functions", "gen_imports",
                          "extract_spu_images", "extract_jobmods"}
    assert s["run_seconds"] >= 0


def tiny_ppu_elf():
    """ELF64 big-endian PPC64 ET_EXEC with one executable segment holding `blr`."""
    code = struct.pack(">I", 0x4E800020) * 4
    ehsize, phsize = 64, 56
    off = ehsize + phsize
    h = bytearray(ehsize)
    h[0:4] = b"\x7fELF"
    h[4], h[5], h[6] = 2, 2, 1
    struct.pack_into(">HHIQQQIHHHHHH", h, 16, 2, 21, 1, 0x10000 + off, ehsize, 0,
                     0, ehsize, phsize, 1, 64, 0, 0)
    ph = struct.pack(">IIQQQQQQ", 1, 5, 0, 0x10000, 0x10000, off + len(code),
                     off + len(code), 0x10000)
    return bytes(h) + ph + code

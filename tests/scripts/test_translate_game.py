# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util
import json
import os
import struct
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "translate_game.py"
sys.path.insert(0, str(REPO / "scripts"))

_spec = importlib.util.spec_from_file_location("translate_game", SCRIPT)
translate_game = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(translate_game)

ELF_REL = "decrypted/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF.elf"


def make_elf(sections):
    """Big-endian ELF64 with only a section header table. sections: [(flags, addr, size)]."""
    shoff = 64
    sh = bytearray(64)  # null section
    for flags, addr, size in sections:
        sh += struct.pack(">IIQQQQIIQQ", 0, 1, flags, addr, 0, size, 0, 0, 0, 0)
    hdr = bytearray(64)
    hdr[:16] = b"\x7fELF\x02\x02\x01" + bytes(9)
    struct.pack_into(">HHIQQQIHHHHHH", hdr, 16, 2, 21, 1, 0, 0, shoff, 0, 64, 0, 0,
                     64, len(sections) + 1, 0)
    return bytes(hdr) + bytes(sh)


FIXTURE_SECTIONS = [(0x6, 0x10200, 0x100), (0x6, 0x10300, 0x20), (0x2, 0x10400, 0x1000)]


def test_code_end_uses_last_exec_section():
    assert translate_game.code_end(make_elf(FIXTURE_SECTIONS)) == 0x10320


def test_code_end_no_exec_raises():
    with pytest.raises(ValueError):
        translate_game.code_end(make_elf([(0x2, 0x10400, 0x1000)]))


LOADER = '''import json, sys, pathlib
out = pathlib.Path(sys.argv[sys.argv.index("-o") + 1]); out.mkdir(parents=True)
for s in ("functions", "imports", "image", "loader"):
    (out / f"EMAIN.SELF.{s}.json").write_text("[]")
'''
LIFTER = '''import sys, pathlib
a = sys.argv
out = pathlib.Path(a[a.index("-o") + 1]); out.mkdir(parents=True)
assert "--code-end" in a and a[a.index("--code-end") + 1] == "0x10320", a
assert a[a.index("--functions") + 1].endswith("EMAIN.SELF.functions.json")
assert a[a.index("--hle-stubs") + 1].endswith("EMAIN.SELF.imports.json")
(out / "ppu_recomp_000.cpp").write_text("{tag}")
{extra}
print("  {n} functions lifted")
'''


def fake_tools(root, tag, n, two=False):
    tools = root / "tools"
    tools.mkdir(exist_ok=True)
    (tools / "ppu_loader.py").write_text(LOADER)
    extra = '(out / "ppu_recomp_001.cpp").write_text("x")' if two else ""
    (tools / "ppu_lifter.py").write_text(LIFTER.format(tag=tag, n=n, extra=extra))
    return tools


@pytest.fixture
def tree(tmp_path):
    t = tmp_path / "tree"
    elf = t / ELF_REL
    elf.parent.mkdir(parents=True)
    elf.write_bytes(make_elf(FIXTURE_SECTIONS))
    return t


def test_refuses_out_inside_git_tree(tree, tmp_path):
    tools = fake_tools(tmp_path, "a", 1)
    target = REPO / "x"
    with pytest.raises(SystemExit) as e:
        translate_game.translate(tree, target, sys.executable, tools)
    assert "inside a git work tree" in str(e.value)
    assert not target.exists() and not Path(str(target) + ".staging").exists()


def test_rerun_replaces_atomically(tree, tmp_path):
    out = tmp_path / "out"
    translate_game.translate(tree, out, sys.executable, fake_tools(tmp_path, "one", 5, two=True))
    assert sorted(p.name for p in (out / "ppu").iterdir()) == [
        "ppu_recomp_000.cpp", "ppu_recomp_001.cpp"]
    translate_game.translate(tree, out, sys.executable, fake_tools(tmp_path, "two", 7))
    assert sorted(p.name for p in (out / "ppu").iterdir()) == ["ppu_recomp_000.cpp"]
    assert (out / "ppu" / "ppu_recomp_000.cpp").read_text() == "two"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out", "tools", "tree"]


def test_record_fields(tree, tmp_path):
    out = tmp_path / "out"
    rec = translate_game.translate(tree, out, sys.executable, fake_tools(tmp_path, "a", 4242))
    assert json.loads((out / "translate.json").read_text()) == rec
    assert set(rec) == {"elf", "elf_sha256", "ps3recomp_commit", "ps3recomp_patches",
                        "code_end", "chunks", "functions", "seconds", "spu"}
    assert rec["elf"] == ELF_REL
    assert rec["code_end"] == "0x10320"
    assert rec["functions"] == 4242 and rec["chunks"] == 64 and rec["spu"] is None
    assert set(rec["seconds"]) == {"loader", "lifter"}
    assert len(rec["elf_sha256"]) == 64
    assert len(rec["ps3recomp_patches"]) == 64
    assert (out / "loader" / "EMAIN.SELF.functions.json").is_file()
    assert (out / "logs" / "ppu_lifter.log").is_file()


def test_patches_hash_is_sorted_concatenation(tmp_path):
    import hashlib
    d = tmp_path / "p"
    d.mkdir()
    assert translate_game.patches_hash(d) == hashlib.sha256(b"").hexdigest()
    (d / "b.patch").write_bytes(b"B")
    (d / "a.patch").write_bytes(b"A")
    assert translate_game.patches_hash(d) == hashlib.sha256(b"AB").hexdigest()


@pytest.mark.skipif(not os.environ.get("GT6_TREE"), reason="GT6_TREE not set (needs the built v1.22 tree)")
def test_real_emain(tmp_path):
    out = tmp_path / "recomp"
    rec = translate_game.translate(
        Path(os.environ["GT6_TREE"]), out, sys.executable,
        translate_game.map_game.DEFAULT_PS3RECOMP / "tools")
    assert rec["functions"] > 60000
    assert rec["code_end"] == "0x101bea0"
    total = sum(p.stat().st_size for p in (out / "ppu").rglob("*") if p.is_file())
    assert total < 600 * 1024 * 1024

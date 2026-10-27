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


# Fake build_spu_workloads.py --input: two images; with partial=True the second one is
# unsupported, the tool prints its incomplete marker and exits 0 only under --allow-partial.
SPU_WORKLOADS = '''import json, sys, pathlib
a = sys.argv
lifted = pathlib.Path(a[a.index("--lifted") + 1])
out = pathlib.Path(a[a.index("--out") + 1])
assert out.parent == lifted and out.name == "spu_workloads.c", a
assert a[a.index("--input") + 1].endswith("EMAIN.SELF.elf"), a
assert "--constructor" in a and "--allow-partial" in a, a
assert not lifted.exists() or not any(lifted.iterdir()), "lifted dir must start empty"
lifted.mkdir(parents=True, exist_ok=True)
partial = {partial}
progs = []
for i, name in enumerate(("spu_aaaa", "spu_bbbb")):
    bad = partial and i == 1
    if not bad:
        (lifted / name).mkdir()
        (lifted / name / "spu_recomp.c").write_text("x")
    progs.append(dict(name=name, status="unsupported" if bad else "registered"))
progs.append(dict(status="invalid", reason="not an ELF", occurrences=[]))
out.write_text("registry")
(lifted / "inventory.json").write_text(json.dumps(dict(complete=not partial, programs=progs)))
print(f"[build_spu_workloads] {{2 - partial}}/3 candidates registered; complete={{not partial}}")
'''
# Fake lift_jobmods.py --jobmods: one lift folder and manifest entry per module file.
JOBMODS = '''import json, sys, pathlib
a = sys.argv
src = pathlib.Path(a[a.index("--jobmods") + 1])
out = pathlib.Path(a[a.index("--out") + 1])
reg = pathlib.Path(a[a.index("--register") + 1])
assert reg == out / "jobmods_register.c", a
assert (out / "spu_workloads.c").is_file(), "runs after build_spu_workloads"
man = []
for i, p in enumerate(sorted(src.glob("*.bin"))):
    (out / p.stem).mkdir()
    (out / p.stem / "spu_recomp.c").write_text("x")
    man.append(dict(name=p.stem, funcs=3, unsupported=1 if {unsup} and i == 0 else 0))
(out / "jobmods_manifest.json").write_text(json.dumps(man))
reg.write_text("register")
print(f"Lifted {{len(man)}} module(s)")
'''


# Fake wrap_spu_elf.py and spu_lifter.py for the spu-missed step (D33).
WRAP = '''import sys, pathlib
a = sys.argv
raw = pathlib.Path(a[1]).read_bytes()
pathlib.Path(a[a.index("--out") + 1]).write_bytes(b"ELF" + a[a.index("--base") + 1].encode() + raw)
'''
SPU_LIFTER = '''import sys, pathlib
a = sys.argv
out = pathlib.Path(a[a.index("-o") + 1]); out.mkdir(parents=True)
base = a[a.index("--base") + 1]
assert a[a.index("--extra-funcs") + 1] == base, a
assert a[a.index("--symbol-prefix") + 1] == out.name + "_", a
(out / "spu_recomp.c").write_text("lifted at " + base)
print("  3 function(s) lifted")
if base == "0xa00":
    print("  2 unsupported instruction(s)")
'''


def fake_tools(root, tag, n, two=False, partial=False, unsup=False):
    tools = root / "tools"
    tools.mkdir(exist_ok=True)
    (tools / "ppu_loader.py").write_text(LOADER)
    extra = '(out / "ppu_recomp_001.cpp").write_text("x")' if two else ""
    (tools / "ppu_lifter.py").write_text(LIFTER.format(tag=tag, n=n, extra=extra))
    (tools / "build_spu_workloads.py").write_text(SPU_WORKLOADS.format(partial=partial))
    (tools / "lift_jobmods.py").write_text(JOBMODS.format(unsup=unsup))
    (tools / "wrap_spu_elf.py").write_text(WRAP)
    (tools / "spu_lifter.py").write_text(SPU_LIFTER)
    return tools


def make_jobmod(tag, size=0x80):
    """A raw job module: four `ila`, entry 0x30 at +0x10, image size at +0x14, C0DEC0DE."""
    m = bytearray(size)
    for k in range(4):
        m[4 * k] = 0x42
    struct.pack_into(">II", m, 0x10, 0x30, size + 32)
    m[0x20:0x24] = b"\xc0\xde\xc0\xde"
    m[0x40] = tag
    return bytes(m)


@pytest.fixture
def tree(tmp_path):
    t = tmp_path / "tree"
    elf = t / ELF_REL
    elf.parent.mkdir(parents=True)
    elf.write_bytes(make_elf(FIXTURE_SECTIONS) + make_jobmod(1) + make_jobmod(2))
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
    assert rec["functions"] == 4242 and rec["chunks"] == 64
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


def test_spu_record_with_fake_tools(tree, tmp_path):
    out = tmp_path / "out"
    rec = translate_game.translate(tree, out, sys.executable, fake_tools(tmp_path, "a", 1))
    spu = rec["spu"]
    assert set(spu) == {"images", "jobmods", "partial", "missed", "seconds"}
    assert spu["missed"] == {"found": 0, "lifted": 0, "partial": [], "rejected": [], "failed": []}
    assert spu["images"] == 2
    manifest = json.loads((out / "spu" / "jobmods_manifest.json").read_text())
    assert spu["jobmods"] == len(manifest) == 2
    assert spu["partial"] == []
    assert isinstance(spu["seconds"], float)
    # the layout the template's SPU_DIR expects
    for f in ("spu_aaaa/spu_recomp.c", "spu_bbbb/spu_recomp.c", "spu_workloads.c",
              "jobmods_register.c"):
        assert (out / "spu" / f).is_file(), f
    assert len(list((out / "spu").glob("jobmod_*/spu_recomp.c"))) == 2
    assert (out / "logs" / "build_spu_workloads.log").is_file()
    assert (out / "logs" / "lift_jobmods.log").is_file()


def test_spu_partial_is_recorded_not_fatal(tree, tmp_path):
    out = tmp_path / "out"
    rec = translate_game.translate(tree, out, sys.executable,
                                   fake_tools(tmp_path, "a", 1, partial=True, unsup=True))
    assert rec["spu"]["images"] == 2
    first = sorted(p.name for p in (out / "spu").glob("jobmod_*"))[0]
    assert rec["spu"]["partial"] == ["spu_bbbb", first]
    assert json.loads((out / "translate.json").read_text())["spu"]["partial"] == rec["spu"]["partial"]


def test_spu_tool_failure_keeps_previous_output(tree, tmp_path):
    out = tmp_path / "out"
    translate_game.translate(tree, out, sys.executable, fake_tools(tmp_path, "one", 1))
    tools = fake_tools(tmp_path, "two", 1)
    (tools / "lift_jobmods.py").write_text("import sys; sys.exit('boom')")
    with pytest.raises(SystemExit) as e:
        translate_game.translate(tree, out, sys.executable, tools)
    assert "lift_jobmods failed" in str(e.value)
    assert (out / "ppu" / "ppu_recomp_000.cpp").read_text() == "one"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out", "tools", "tree"]


def test_fnv1a64_matches_the_runtime():
    # runtime/spu/spu_workload.c spu_workload_fingerprint, offset basis 1469598103934665603
    assert translate_game.fnv1a64(b"") == 1469598103934665603
    assert translate_game.fnv1a64(b"a") == 0x44BD8AD473CD9906


def test_spu_missed_images_are_lifted(tree, tmp_path):
    """Images dumped to <tree>/spu-missed are lifted at their link base and registered by
    fingerprint; a file whose bytes do not match its name is rejected, others ignored."""
    missed = tree / "spu-missed"
    missed.mkdir()
    job, pm = b"\x40\x80\x00\x05" * 8, b"\x24\x00\x40\x80" * 16
    fj, fp = translate_game.fnv1a64(job), translate_game.fnv1a64(pm)
    (missed / f"spujob_{fj:016X}_{len(job)}.bin").write_bytes(job)
    (missed / f"spupm_{fp:016X}_{len(pm)}.bin").write_bytes(pm)
    (missed / f"spujob_{fj ^ 1:016X}_{len(job)}.bin").write_bytes(job)   # wrong fingerprint
    (missed / "notes.txt").write_text("not an image")
    out = tmp_path / "out"
    rec = translate_game.translate(tree, out, sys.executable, fake_tools(tmp_path, "a", 1))
    m = rec["spu"]["missed"]
    assert m["found"] == 3 and m["lifted"] == 2
    assert m["rejected"] == [f"spujob_{fj ^ 1:016X}_{len(job)}.bin"]
    assert m["partial"] == [f"missed_{fp:016x}"] and m["failed"] == []
    man = json.loads((out / "spu" / "spu_missed_manifest.json").read_text())
    by = {e["kind"]: e for e in man}
    assert by["spujob"]["base"] == 0 and by["spupm"]["base"] == 0xA00
    assert by["spujob"]["fingerprint"] == f"0x{fj:016X}"
    assert (out / "spu" / f"missed_{fj:016x}" / "spu_recomp.c").read_text() == "lifted at 0x0"
    assert (out / "spu" / f"missed_{fp:016x}" / "spu_recomp.c").read_text() == "lifted at 0xa00"
    reg = (out / "spu" / "spu_missed_register.c").read_text()
    assert f"spu_workload_register_img(0x{fj:016X}ULL, missed_{fj:016x}_spu_func_00000000," in reg
    assert f"spu_workload_register_img(0x{fp:016X}ULL, missed_{fp:016x}_spu_func_00000A00," in reg
    assert "__attribute__((constructor))" in reg
    assert len({e["image_id"] for e in man}) == 2
    assert all(0x58000000 <= e["image_id"] < 0x59000000 for e in man)


@pytest.mark.skipif(not os.environ.get("GT6_TREE"), reason="GT6_TREE not set (needs the built v1.22 tree)")
def test_real_spu(tmp_path):
    out = tmp_path / "recomp"
    rec = translate_game.translate(
        Path(os.environ["GT6_TREE"]), out, sys.executable,
        translate_game.map_game.DEFAULT_PS3RECOMP / "tools")
    spu = rec["spu"]
    print(f"\nSPU: {spu}")
    assert spu["images"] == 4
    assert spu["jobmods"] == 57
    assert len(list((out / "spu").glob("jobmod_*/spu_recomp.c"))) == 57
    assert (out / "spu" / "spu_workloads.c").is_file()
    assert (out / "spu" / "jobmods_register.c").is_file()


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

# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util
import json
import os
import struct
import subprocess
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
REAL_PATCHES = translate_game.PATCHES
SUB = REPO / "third_party" / "ps3recomp"


@pytest.fixture(autouse=True)
def no_patches(tmp_path, monkeypatch):
    """Fake-tool tests apply an empty patch set; the real ones pass patches=REAL_PATCHES."""
    d = tmp_path / "no-patches"
    d.mkdir()
    monkeypatch.setattr(translate_game, "PATCHES", d)
    return d


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
    """Fake ps3recomp tools in root/ps3recomp/tools; root/ps3recomp is a git work tree, as
    the submodule is, so the patch step (apply_ps3recomp_patches.sh) can run on it."""
    tools = root / "ps3recomp" / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    if not (tools.parent / ".git").exists():
        subprocess.run(["git", "init", "-q", str(tools.parent)], check=True)
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
    assert sorted(p.name for p in tmp_path.iterdir()) == ["no-patches", "out", "ps3recomp", "tree"]


def test_record_fields(tree, tmp_path):
    out = tmp_path / "out"
    rec = translate_game.translate(tree, out, sys.executable, fake_tools(tmp_path, "a", 4242))
    assert json.loads((out / "translate.json").read_text()) == rec
    assert set(rec) == {"tool", "elf", "elf_sha256", "ps3recomp_commit", "ps3recomp_patches",
                        "code_end", "chunks", "functions", "sjlj", "seconds", "spu"}
    assert rec["tool"] == "scripts/translate_game.py"
    assert rec["sjlj"] == {"setjmp": [], "longjmp": []}
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
    assert spu["missed"] == {"found": 0, "lifted": 0, "partial": [], "rejected": [], "failed": [],
                             "duplicate": []}
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
    assert sorted(p.name for p in tmp_path.iterdir()) == ["no-patches", "out", "ps3recomp", "tree"]


def make_elf_with_code(words, addr=0x10200):
    """Big-endian ELF64 with one executable section holding `words` at `addr`."""
    code = b"".join(struct.pack(">I", w) for w in words)
    shoff = 64 + len(code)
    sh = bytearray(64) + struct.pack(">IIQQQQIIQQ", 0, 1, 0x6, addr, 64, len(code), 0, 0, 0, 0)
    hdr = bytearray(64)
    hdr[:16] = b"\x7fELF\x02\x02\x01" + bytes(9)
    struct.pack_into(">HHIQQQIHHHHHH", hdr, 16, 2, 21, 1, 0, 0, shoff, 0, 64, 0, 0, 64, 2, 0)
    return bytes(hdr) + code + bytes(sh)


def test_find_sjlj():
    nop = 0x60000000
    words = [nop] + list(translate_game.SETJMP_SIG) + [nop, nop] + list(translate_game.LONGJMP_SIG)
    sj, lj = translate_game.find_sjlj(make_elf_with_code(words))
    assert sj == [0x10204] and lj == [0x10204 + 4 * 8]
    assert translate_game.find_sjlj(make_elf_with_code([nop] * 8)) == ([], [])


def test_sjlj_passed_to_the_lifter(tmp_path):
    t = tmp_path / "tree"
    elf = t / ELF_REL
    elf.parent.mkdir(parents=True)
    words = list(translate_game.SETJMP_SIG) + list(translate_game.LONGJMP_SIG)
    elf.write_bytes(make_elf_with_code(words, addr=0x10300))
    tools = fake_tools(tmp_path, "a", 1)
    old = 'assert "--code-end" in a and a[a.index("--code-end") + 1] == "0x10320", a'
    original = (tools / "ppu_lifter.py").read_text()
    assert old in original, "the fake lifter's code-end check moved; update this test"
    lifter = original.replace(
        old, 'assert a[a.index("--setjmp") + 1] == "0x10300" and a[a.index("--longjmp") + 1] == "0x10318", a')
    assert lifter != original
    # Without the longjmp rewrite in ppu/ the translate fails (item 13): a lifter that took
    # --longjmp but rewrote nothing would silently stop unwinding.
    (tools / "ppu_lifter.py").write_text(lifter)
    with pytest.raises(SystemExit, match="ppu_sjlj_longjmp"):
        translate_game.translate(t, tmp_path / "out", sys.executable, tools)
    assert not (tmp_path / "out").exists()
    (tools / "ppu_lifter.py").write_text(lifter.replace(
        '(out / "ppu_recomp_000.cpp").write_text("{tag}")'.format(tag="a"),
        '(out / "ppu_recomp_000.cpp").write_text("ppu_sjlj_longjmp(ctx, 0);")'))
    rec = translate_game.translate(t, tmp_path / "out", sys.executable, tools)
    assert rec["sjlj"] == {"setjmp": ["0x10300"], "longjmp": ["0x10318"]}


def test_missed_image_ids_do_not_collide():
    a = translate_game.missed_image_id(0xAAAA000000123456)
    b = translate_game.missed_image_id(0xBBBB000000123456, {a})
    assert a == 0x58123456 and b == 0x58123457
    assert translate_game.missed_image_id(0x00FFFFFF, {0x58FFFFFF}) == 0x58000000


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
        translate_game.map_game.DEFAULT_PS3RECOMP / "tools", patches=REAL_PATCHES)
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
        translate_game.map_game.DEFAULT_PS3RECOMP / "tools", patches=REAL_PATCHES)
    assert rec["functions"] > 60000
    assert rec["code_end"] == "0x101bea0"
    total = sum(p.stat().st_size for p in (out / "ppu").rglob("*") if p.is_file())
    assert total < 600 * 1024 * 1024


def test_spu_missed_same_bytes_as_job_and_policy_module_is_lifted_once(tree, tmp_path):
    """The same bytes dumped as spujob_ and spupm_ share a fingerprint; the registry keys on
    it, so only the first is lifted and the other is listed as a duplicate (item 11)."""
    missed = tree / "spu-missed"
    missed.mkdir()
    img = b"\x40\x80\x00\x05" * 8
    fp = translate_game.fnv1a64(img)
    (missed / f"spujob_{fp:016X}_{len(img)}.bin").write_bytes(img)
    (missed / f"spupm_{fp:016X}_{len(img)}.bin").write_bytes(img)
    rec = translate_game.translate(tree, tmp_path / "out", sys.executable, fake_tools(tmp_path, "a", 1))
    m = rec["spu"]["missed"]
    assert m["found"] == 2 and m["lifted"] == 1 and m["failed"] == []
    assert m["duplicate"] == [f"spupm_{fp:016X}_{len(img)}.bin"]
    man = json.loads((tmp_path / "out" / "spu" / "spu_missed_manifest.json").read_text())
    assert [e["kind"] for e in man] == ["spujob"]


# ---- ps3recomp patches (item 1): applied and verified before the lifter runs -------------

UNPATCHED = 'import sys; sys.exit("unpatched lifter: no --setjmp")\n'


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def make_patch(repo, rel, new_text, patches, name="0001-fix.patch"):
    """A patch (git diff) taking repo/rel to new_text; repo/rel is left unchanged."""
    f = repo / rel
    old = f.read_text()
    git("add", rel, cwd=repo)
    f.write_text(new_text)
    diff = git("diff", "--", rel, cwd=repo)
    f.write_text(old)
    patches.mkdir(exist_ok=True)
    (patches / name).write_text("Upstream: not yet submitted\n\n" + diff)
    return patches / name


def unpatched_tools(tmp_path):
    """Fake tools whose lifter only works once the patch in tmp_path/patches is applied."""
    tools = fake_tools(tmp_path, "a", 3)
    lifter = (tools / "ppu_lifter.py").read_text()
    (tools / "ppu_lifter.py").write_text(UNPATCHED + lifter)
    patches = tmp_path / "patches"
    make_patch(tools.parent, "tools/ppu_lifter.py", lifter, patches)
    return tools, patches, lifter


def test_translate_applies_the_patches_first(tree, tmp_path):
    tools, patches, lifter = unpatched_tools(tmp_path)
    out = tmp_path / "out"
    rec = translate_game.translate(tree, out, sys.executable, tools, patches=patches)
    assert (tools / "ppu_lifter.py").read_text() == lifter     # patched in place
    assert rec["functions"] == 3
    assert rec["ps3recomp_patches"] == translate_game.patches_hash(patches)
    # Already applied: a second run skips the patch and records the same hash.
    rec = translate_game.translate(tree, out, sys.executable, tools, patches=patches)
    assert rec["ps3recomp_patches"] == translate_game.patches_hash(patches)


def test_translate_refuses_when_a_patch_does_not_apply(tree, tmp_path):
    tools, patches, _ = unpatched_tools(tmp_path)
    (patches / "0002-bad.patch").write_text(
        "Upstream: not yet submitted\n"
        "diff --git a/no/such/file.c b/no/such/file.c\n"
        "--- a/no/such/file.c\n+++ b/no/such/file.c\n@@ -1 +1 @@\n-x\n+y\n")
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as e:
        translate_game.translate(tree, out, sys.executable, tools, patches=patches)
    assert "0002-bad.patch" in str(e.value) and "clean -fd" in str(e.value)
    # Nothing ran and nothing was written.
    assert not out.exists() and not (tmp_path / "out.staging").exists()


def test_ensure_patches_on_an_unpatched_export_of_the_pin(tmp_path):
    """A fresh export of the pinned ps3recomp (no patches): translate's patch step applies
    every patch in patches/ps3recomp, then verifies all of them, then gives the hash."""
    if not (SUB / ".git").exists():
        pytest.skip("no ps3recomp checkout")
    pin = git("ls-tree", "HEAD", "third_party/ps3recomp", cwd=REPO).split()[2]
    export = tmp_path / "ps3recomp"
    export.mkdir()
    archive = subprocess.run(["git", "archive", pin], cwd=SUB, check=True,
                             capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(export)], input=archive, check=True)
    subprocess.run(["git", "init", "-q", str(export)], check=True)
    assert "--setjmp" not in (export / "tools" / "ppu_lifter.py").read_text()
    h = translate_game.ensure_patches(export, REAL_PATCHES)
    assert h == translate_game.patches_hash(REAL_PATCHES)
    assert "--setjmp" in (export / "tools" / "ppu_lifter.py").read_text()
    assert (export / "runtime" / "ppu" / "ppu_sjlj.h").is_file()
    assert translate_game.ensure_patches(export, REAL_PATCHES) == h


# ---- the output folder (item 2): only ever replace what this tool made ------------------

def test_refuses_an_existing_out_this_tool_did_not_make(tree, tmp_path):
    tools = fake_tools(tmp_path, "a", 1)
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("not ours")
    with pytest.raises(SystemExit, match="translate.json"):
        translate_game.translate(tree, out, sys.executable, tools)
    assert (out / "keep.txt").read_text() == "not ours"
    (out / "translate.json").write_text('{"tool": "something else"}')
    with pytest.raises(SystemExit, match="translate.json"):
        translate_game.translate(tree, out, sys.executable, tools)
    assert (out / "keep.txt").read_text() == "not ours"
    assert not (tmp_path / "out.staging").exists()


def test_replaces_an_out_from_before_the_tool_field(tree, tmp_path):
    """A translate.json written before "tool" was recorded still counts as ours."""
    tools = fake_tools(tmp_path, "a", 1)
    out = tmp_path / "out"
    translate_game.translate(tree, out, sys.executable, tools)
    rec = json.loads((out / "translate.json").read_text())
    del rec["tool"]
    (out / "translate.json").write_text(json.dumps(rec))
    translate_game.translate(tree, out, sys.executable, tools)
    assert json.loads((out / "translate.json").read_text())["tool"] == "scripts/translate_game.py"


def test_never_replaces_the_tree_or_its_ancestors(tree, tmp_path):
    tools = fake_tools(tmp_path, "a", 1)
    for target in (tree, tmp_path):
        (target / "translate.json").write_text(json.dumps({"tool": "scripts/translate_game.py"}))
        with pytest.raises(SystemExit, match="game tree"):
            translate_game.translate(tree, target, sys.executable, tools)
        assert (tree / ELF_REL).is_file()
        (target / "translate.json").unlink()
    # Nor when out's staging or .old name is the tree.
    for suffix in (".staging", ".old"):
        other = tmp_path / ("g" + suffix)
        other.mkdir()
        (tree / "decrypted").rename(other / "decrypted")
        (other / ".translate_game-staging").write_text("")
        with pytest.raises(SystemExit, match="game tree"):
            translate_game.translate(other, tmp_path / "g", sys.executable, tools)
        assert (other / ELF_REL).is_file()
        (other / "decrypted").rename(tree / "decrypted")


def test_staging_and_old_are_removed_only_when_ours(tree, tmp_path):
    tools = fake_tools(tmp_path, "a", 1)
    out = tmp_path / "out"
    for leftover in ("out.staging", "out.old"):
        d = tmp_path / leftover
        d.mkdir()
        (d / "keep.txt").write_text("not ours")
        with pytest.raises(SystemExit, match="not made by"):
            translate_game.translate(tree, out, sys.executable, tools)
        assert (d / "keep.txt").read_text() == "not ours"
        assert not out.exists()
        (d / "keep.txt").unlink()
        d.rmdir()
    # Left by a killed run: a staging folder with the marker, or (killed after the marker
    # was dropped) with this tool's translate.json, and an old folder with translate.json.
    translate_game.translate(tree, out, sys.executable, tools)
    for leftover, mark in (("out.staging", ".translate_game-staging"),
                           ("out.staging", "translate.json"), ("out.old", "translate.json")):
        d = tmp_path / leftover
        d.mkdir()
        (d / mark).write_text(json.dumps({"tool": "scripts/translate_game.py"}))
        translate_game.translate(tree, out, sys.executable, tools)
        assert not d.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["no-patches", "out", "ps3recomp", "tree"]
    assert not (out / ".translate_game-staging").exists()


def test_elf_option_translates_another_executable(tree, tmp_path):
    """--elf picks the executable (D44: the post-install TPPS-01.22 EMAIN), recorded as "elf"."""
    other = Path("decrypted") / "dev_hdd0/game/BCES01977/USRDIR/TPPS-01.22/EMAIN.SELF.elf"
    (tree / other).parent.mkdir(parents=True)
    (tree / other).write_bytes((tree / ELF_REL).read_bytes())
    out = tmp_path / "out"
    rec = translate_game.translate(tree, out, sys.executable, fake_tools(tmp_path, "a", 1),
                                   elf_rel=other)
    assert rec["elf"] == other.as_posix()
    with pytest.raises(SystemExit) as e:
        translate_game.translate(tree, tmp_path / "out2", sys.executable,
                                 fake_tools(tmp_path, "b", 1), elf_rel="decrypted/missing.elf")
    assert "ELF not found" in str(e.value)

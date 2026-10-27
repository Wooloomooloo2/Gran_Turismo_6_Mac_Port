# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_no_game_files.py"


def run(path):
    return subprocess.run([sys.executable, str(SCRIPT), str(path)],
                          capture_output=True, text=True)


def make(tmp_path, name, data):
    d = tmp_path / "Gran Turismo 6 (UK) test"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_bytes(data)
    return p


def elf(machine):
    h = bytearray(64)
    h[0:4] = b"\x7fELF"
    h[4] = 2  # 64-bit
    h[5] = 2  # big endian
    struct.pack_into(">H", h, 18, machine)
    return bytes(h)


def assert_blocked(p, r):
    assert r.returncode == 1
    assert f"BLOCKED {p}:" in r.stdout


def test_blocks_self(tmp_path):
    p = make(tmp_path, "EMAIN.SELF", b"SCE\0" + bytes(60))
    assert_blocked(p, run(p))


def test_blocks_pkg(tmp_path):
    p = make(tmp_path, "update.bin", b"\x7fPKG" + bytes(60))
    assert_blocked(p, run(p))


def test_blocks_pup(tmp_path):
    p = make(tmp_path, "fw.bin", b"SCEUF" + bytes(60))
    assert_blocked(p, run(p))


def test_blocks_sfo(tmp_path):
    p = make(tmp_path, "PARAM.SFO", b"\x00PSF" + bytes(60))
    assert_blocked(p, run(p))


def test_blocks_ppc64_elf(tmp_path):
    p = make(tmp_path, "a.bin", elf(0x15))
    assert_blocked(p, run(p))


def test_blocks_spu_elf(tmp_path):
    p = make(tmp_path, "b.bin", elf(0x17))
    assert_blocked(p, run(p))


def test_allows_arm64_elf(tmp_path):
    p = make(tmp_path, "c.bin", elf(0xB7))
    r = run(p)
    assert r.returncode == 0 and "BLOCKED" not in r.stdout


def test_allows_text(tmp_path):
    p = make(tmp_path, "notes.txt", b"hello\n")
    r = run(p)
    assert r.returncode == 0 and "BLOCKED" not in r.stdout


def test_blocks_large_file(tmp_path):
    p = make(tmp_path, "big.dat", b"")
    with open(p, "r+b") as f:
        f.truncate(51 * 1024 * 1024)
    assert_blocked(p, run(p))


def test_blocks_edat_sdat(tmp_path):
    p = make(tmp_path, "data.sdat", b"NPD\0" + bytes(60))
    assert_blocked(p, run(p))


def test_blocks_trophy_trp(tmp_path):
    p = make(tmp_path, "TROPHY.TRP", b"\xdc\xa2\x4d\x00" + bytes(60))
    assert_blocked(p, run(p))


# ---- files listed by hash in a committed manifest ----

def guard_with_manifest(tmp_path, entries):
    """A copy of the guard in <tmp>/repo/scripts with <tmp>/repo/manifests/m.json."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "manifests").mkdir()
    shutil.copy(SCRIPT, repo / "scripts" / SCRIPT.name)
    files = [{"path": f"dev_hdd0/x{i}", "size": len(d), "sha256": hashlib.sha256(d).hexdigest()}
             for i, d in enumerate(entries)]
    m = repo / "manifests" / "m.json"
    m.write_text(json.dumps({"title_id": "BCES01977", "app_ver": "01.22", "files": files}))
    return repo / "scripts" / SCRIPT.name, m


def run_with(script, *paths):
    return subprocess.run([sys.executable, str(script), *map(str, paths)], capture_output=True, text=True)


def test_blocks_file_listed_in_a_manifest(tmp_path):
    game = b"PDIPFS chunk without any magic" * 10
    script, _ = guard_with_manifest(tmp_path, [game, b"1.22\n"])
    p = make(tmp_path, "PATCHSEQUENCE", game)
    r = run_with(script, p)
    assert_blocked(p, r)
    assert "manifest" in r.stdout
    q = make(tmp_path, "update.txt", b"1.22\n")
    assert_blocked(q, run_with(script, q))


def test_allows_same_size_different_content(tmp_path):
    script, _ = guard_with_manifest(tmp_path, [b"aaaa"])
    p = make(tmp_path, "notes.txt", b"bbbb")
    r = run_with(script, p)
    assert r.returncode == 0 and "BLOCKED" not in r.stdout


def test_empty_files_are_never_blocked_by_hash(tmp_path):
    script, _ = guard_with_manifest(tmp_path, [b""])
    p = make(tmp_path, "__init__.py", b"")
    r = run_with(script, p)
    assert r.returncode == 0 and "BLOCKED" not in r.stdout


def test_manifests_themselves_are_allowed(tmp_path):
    script, m = guard_with_manifest(tmp_path, [b"game data"])
    r = run_with(script, m)
    assert r.returncode == 0 and "BLOCKED" not in r.stdout


def test_works_without_a_manifests_folder(tmp_path):
    script, m = guard_with_manifest(tmp_path, [b"game data"])
    shutil.rmtree(m.parent)
    p = make(tmp_path, "notes.txt", b"game data")
    r = run_with(script, p)
    assert r.returncode == 0 and "BLOCKED" not in r.stdout

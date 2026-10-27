# SPDX-License-Identifier: GPL-2.0-or-later
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

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail if any file looks like PS3 game content (Sony/Polyphony property).

Usage: check_no_game_files.py [paths...]
With no paths, checks the files staged in git (git diff --cached --name-only).
Prints "BLOCKED <path>: <reason>" and exits 1 if anything is found.

A file is blocked when it is larger than 50 MB, starts with a PS3 file signature (SCE
container, PKG, PUP, PARAM.SFO, EDAT/SDAT, trophy TRP, PS3 PPU or SPU ELF), or its SHA-256
is listed in any manifests/*.json (a hashes-only list of every file of a built game tree,
which catches game files with no signature at all). Empty files are never matched by hash.
The manifests themselves are not checked. Stdlib only.
"""
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 50 * 1024 * 1024
MANIFEST_DIR = Path(__file__).resolve().parent.parent / "manifests"
MACHINES = {0x15: "ELF for PPC64 (PS3 PPU)", 0x17: "ELF for SPU (PS3 SPU)"}
SIGNATURES = [
    (b"SCE\0", "SCE container (SELF/SPRX/PKG)"),
    (b"\x7fPKG", "PS3 PKG"),
    (b"SCEUF", "PS3 firmware PUP"),
    (b"\x00PSF", "PARAM.SFO"),
    (b"NPD\0", "PS3 EDAT/SDAT"),
    (b"\xdc\xa2\x4d\x00", "PS3 trophy file (TRP)"),
]

_manifest_hashes = None  # size -> {sha256: manifest name}, loaded once


def manifest_hashes():
    global _manifest_hashes
    if _manifest_hashes is None:
        _manifest_hashes = {}
        for m in sorted(MANIFEST_DIR.glob("*.json")):
            for f in json.loads(m.read_text()).get("files", []):
                if f["size"]:
                    _manifest_hashes.setdefault(f["size"], {})[f["sha256"]] = m.name
    return _manifest_hashes


def is_manifest(p):
    return p.suffix == ".json" and p.resolve().parent == MANIFEST_DIR


def check(path):
    p = Path(path)
    if not p.is_file():
        return None
    size = p.stat().st_size
    if size > MAX_BYTES:
        return "file larger than 50 MB"
    with open(p, "rb") as f:
        head = f.read(64)
    for sig, why in SIGNATURES:
        if head.startswith(sig):
            return why
    if head.startswith(b"\x7fELF") and len(head) >= 20:
        order = "<" if head[5] == 1 else ">"
        machine = struct.unpack_from(order + "H", head, 18)[0]
        if machine in MACHINES:
            return MACHINES[machine]
    candidates = manifest_hashes().get(size)
    if candidates and not is_manifest(p):
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest in candidates:
            return f"game file listed in manifests/{candidates[digest]}"
    return None


def staged_files():
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
                         capture_output=True, check=True).stdout
    return [x.decode() for x in out.split(b"\0") if x]


def main(argv):
    paths = argv or staged_files()
    bad = 0
    for path in paths:
        reason = check(path)
        if reason:
            print(f"BLOCKED {path}: {reason}")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

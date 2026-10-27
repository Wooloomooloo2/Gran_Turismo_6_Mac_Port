#!/usr/bin/env python3
"""Fail if any file looks like PS3 game content (Sony/Polyphony property).

Usage: check_no_game_files.py [paths...]
With no paths, checks the files staged in git (git diff --cached --name-only).
Prints "BLOCKED <path>: <reason>" and exits 1 if anything is found.
Stdlib only.
"""
import struct
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 50 * 1024 * 1024
MACHINES = {0x15: "ELF for PPC64 (PS3 PPU)", 0x17: "ELF for SPU (PS3 SPU)"}
# Longer signatures first is not required; all are checked.
SIGNATURES = [
    (b"SCE\0", "SCE container (SELF/SPRX/PKG)"),
    (b"\x7fPKG", "PS3 PKG"),
    (b"SCEUF", "PS3 firmware PUP"),
    (b"\x00PSF", "PARAM.SFO"),
]


def check(path):
    p = Path(path)
    if not p.is_file():
        return None
    if p.stat().st_size > MAX_BYTES:
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

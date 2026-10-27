#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Translate GT6's PPU program to C++ with ps3recomp (dev-only, never shipped).

Usage:
    .venv/bin/python scripts/translate_game.py <tree> [-o <tree>/recomp] [--chunks 64] [--jobs N]

<tree> is a gt6unpack build tree (it has decrypted/). The program translated is
USRDIR/EMAIN.SELF.elf, the executable a v1.22 console launches. Two steps:
ppu_loader (function list, import stubs, image manifest), then ppu_lifter with
--code-end set to the end of the last executable ELF section, read from the section
headers (D25). Without it the lifter promotes call targets inside read-only data and
the embedded SPU programs to functions and writes 3.7 GB of bogus code.

Output (replaced as a whole on every run, via <out>.staging and <out>.old):

    <out>/ppu/        ppu_recomp.h, ppu_recomp_NNN.cpp, ppu_recomp_table.cpp
    <out>/loader/     EMAIN.SELF.{functions,imports,image,loader}.json
    <out>/logs/       one log per tool
    <out>/translate.json   what was translated, with what, and how long it took

The outputs are derived from the game, so <out> must not be inside a git work
tree (D26). Tools run through map_game.run_tool (isolated Python, D22).
"""
import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import map_game  # noqa: E402

REPO = map_game.REPO
PATCHES = REPO / "patches" / "ps3recomp"
ELF_REL = Path("decrypted") / map_game.TITLE_USRDIR / "EMAIN.SELF.elf"
SHF_EXECINSTR = 0x4


def code_end(elf_bytes):
    """Highest sh_addr + sh_size over executable sections of a big-endian ELF64."""
    if elf_bytes[:4] != b"\x7fELF" or elf_bytes[4] != 2 or elf_bytes[5] != 2:
        raise ValueError("not a big-endian ELF64")
    shoff, = struct.unpack_from(">Q", elf_bytes, 0x28)
    shentsize, shnum = struct.unpack_from(">HH", elf_bytes, 0x3A)
    end = None
    for i in range(shnum):
        # sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size
        _, _, flags, addr, _, size = struct.unpack_from(">IIQQQQ", elf_bytes, shoff + i * shentsize)
        if flags & SHF_EXECINSTR:
            end = max(end or 0, addr + size)
    if end is None:
        raise ValueError("no executable sections")
    return end


def patches_hash(folder=PATCHES):
    """SHA-256 over the *.patch files of folder, concatenated in filename order."""
    h = hashlib.sha256()
    folder = Path(folder)
    for p in sorted(folder.glob("*.patch")) if folder.is_dir() else []:
        h.update(p.read_bytes())
    return h.hexdigest()


def in_git_work_tree(path):
    """True if path (which may not exist yet) is inside the repo or any git work tree."""
    path = path.resolve()
    if map_game._inside(path, REPO):
        return True
    probe = path
    while not probe.exists():
        probe = probe.parent
    p = subprocess.run(["git", "-C", str(probe), "rev-parse", "--is-inside-work-tree"],
                       capture_output=True, text=True)
    return p.returncode == 0 and p.stdout.strip() == "true"


def _swap_in(staging, out):
    """Replace out with staging, keeping out.old until the swap has succeeded."""
    old = out.with_name(out.name + ".old")
    if old.exists():
        if not out.exists():
            old.rename(out)  # an earlier run died between the two renames
        else:
            shutil.rmtree(old)
    if out.exists():
        out.rename(old)
    try:
        staging.rename(out)
    except BaseException:
        if old.exists() and not out.exists():
            old.rename(out)
        raise
    if old.exists():
        shutil.rmtree(old)


def translate(tree, out, python, tools, chunks=64, jobs=None):
    tree = Path(tree).resolve()
    out = Path(out).resolve()
    tools = Path(tools)
    if in_git_work_tree(out):
        raise SystemExit(f"error: {out} is inside a git work tree; translated code is "
                         f"derived from the game and must live outside it")
    elf = tree / ELF_REL
    if not elf.is_file():
        raise SystemExit(f"error: ELF not found: {elf}")
    data = elf.read_bytes()
    end = code_end(data)

    staging = out.with_name(out.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    logs = staging / "logs"
    logs.mkdir(parents=True)
    try:
        seconds, status = {}, {}
        status["loader"] = map_game.run_tool(python, tools, "ppu_loader",
                                             [elf, "-o", staging / "loader"], logs)
        if not status["loader"]["ok"]:
            raise SystemExit(f"error: ppu_loader failed, see {logs / 'ppu_loader.log'}")
        loader = staging / "loader"
        args = [elf, "--functions", loader / "EMAIN.SELF.functions.json",
                "--hle-stubs", loader / "EMAIN.SELF.imports.json",
                "--code-end", hex(end), "--chunks", chunks]
        if jobs:
            args += ["-j", jobs]
        args += ["-o", staging / "ppu"]
        status["lifter"] = map_game.run_tool(python, tools, "ppu_lifter", args, logs)
        if not status["lifter"]["ok"]:
            raise SystemExit(f"error: ppu_lifter failed, see {logs / 'ppu_lifter.log'}")
        m = re.search(r"(\d+) functions lifted", (logs / "ppu_lifter.log").read_text())
        if not m:
            raise SystemExit("error: ppu_lifter did not report a function count")
        record = {
            "elf": ELF_REL.as_posix(),
            "elf_sha256": map_game.sha256_file(elf),
            "ps3recomp_commit": map_game.ps3recomp_commit(tools.parent),
            "ps3recomp_patches": patches_hash(),
            "code_end": hex(end),
            "chunks": chunks,
            "functions": int(m.group(1)),
            "seconds": {k: v["seconds"] for k, v in status.items()},
            "spu": None,
        }
        (staging / "translate.json").write_text(json.dumps(record, indent=1))
        _swap_in(staging, out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description="Translate GT6's PPU program (dev-only).")
    ap.add_argument("tree", help="gt6unpack build tree (holds decrypted/)")
    ap.add_argument("-o", "--output", help="output folder (default: <tree>/recomp)")
    ap.add_argument("--chunks", type=int, default=64)
    ap.add_argument("--jobs", type=int)
    ap.add_argument("--ps3recomp", default=str(map_game.DEFAULT_PS3RECOMP))
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter with ps3recomp's dependencies (default: this one)")
    args = ap.parse_args(argv)
    tree = Path(args.tree).expanduser().resolve()
    out = Path(args.output).expanduser() if args.output else tree / "recomp"
    tools = Path(args.ps3recomp) / "tools"
    if not (tools / "ppu_lifter.py").is_file():
        ap.exit(2, f"error: no ps3recomp tools at {tools} "
                   f"(git submodule update --init third_party/ps3recomp)\n")
    rec = translate(tree, out, args.python, tools, args.chunks, args.jobs)
    print(f"{rec['functions']} functions, code end {rec['code_end']}, "
          f"{rec['seconds']['loader']} s + {rec['seconds']['lifter']} s -> {out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

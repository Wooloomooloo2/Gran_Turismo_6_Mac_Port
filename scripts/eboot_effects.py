#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Record what a run changes in a folder (dev-only, never shipped).

Usage:
    .venv/bin/python scripts/eboot_effects.py snapshot <dir> -o <json>
    .venv/bin/python scripts/eboot_effects.py diff <before.json> <after.json>

Used to measure what the 1.22 EBOOT.BIN changes in the game folder before it
spawns EMAIN.SELF (docs/FINDINGS.md, "What the 1.22 EBOOT leaves on disk").
A snapshot maps each file's path, relative to <dir>, to its SHA-256, and each
folder to "<dir>/" (value "dir"). Snapshots of a game folder describe game
files, so the snapshot refuses an output inside any git work tree (D26).
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translate_game import in_git_work_tree  # noqa: E402

DIR = "dir"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def snapshot(root: Path) -> dict:
    """Relative path -> SHA-256 for every file, and "<dir>/" -> "dir" for every folder."""
    root = Path(root)
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel = Path(dirpath).relative_to(root).as_posix()
        if rel != ".":
            out[rel + "/"] = DIR
        for name in sorted(filenames):
            p = Path(dirpath) / name
            key = p.relative_to(root).as_posix()
            out[key] = DIR if p.is_dir() else _sha256(p)
    return dict(sorted(out.items()))


def diff(before: dict, after: dict) -> dict:
    """Paths only in after (added), only in before (removed), or with a new hash (changed)."""
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k]),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot", help="hash every file under a folder")
    s.add_argument("dir", type=Path)
    s.add_argument("-o", "--output", type=Path, required=True)
    d = sub.add_parser("diff", help="compare two snapshots")
    d.add_argument("before", type=Path)
    d.add_argument("after", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "snapshot":
        if in_git_work_tree(args.output):
            ap.exit(2, f"error: {args.output} is inside a git work tree; a snapshot of a game "
                       "folder lists game files and must be written outside it (D26)\n")
        args.output.write_text(json.dumps(snapshot(args.dir), indent=1) + "\n")
    else:
        result = diff(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
        json.dump(result, sys.stdout, indent=1)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Make the play folder the port runs on (dev-only, never shipped).

Usage:
    .venv/bin/python scripts/prepare_play.py <tree> [--force]

<tree> is a verified gt6unpack build tree. The game never runs on it: EMAIN's first
run moves thousands of files inside dev_hdd0 (FINDINGS, "What the 1.22 EBOOT leaves
on disk"). This script clones <tree>/dev_hdd0 to <tree>/play/dev_hdd0 as an
APFS clone (cp -c -R, no extra space), then applies exactly what
the 1.22 EBOOT.BIN changes on disk before it spawns EMAIN.SELF (D31, D32):

1. TPPS-01.07/update.txt is overwritten with "99.98 99.99" (boot function 0x123e0).
2. For each TPPS-MM.mm folder that has a USRDIR/UPDATENODEINFO/UPDATENODEINFO.MMmm
   with as many entries as TPPS-MM.mm/PDIPFS/UPDATENODEINFO, the node info is rebuilt
   as the EBOOT's 0x1143c does (merge_node_info), written to UPDATENODEINFO.upd and
   renamed over UPDATENODEINFO.

<tree>/play/prepare.json records what was applied, the source tree's build.json identity and
the time. An existing play folder is refused without --force (a first run has changed
it); --force replaces it, and only if it holds this tool's prepare.json. The folder is
built beside it and renamed into place once complete, so an interrupted run leaves
no half-prepared play folder. It must be outside any git work tree.
"""
import argparse
import os
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GAME = "dev_hdd0/game/BCES01977/USRDIR"
UPDATE_TXT = "99.98 99.99"           # va 0x3d100 in the 1.22 EBOOT
TPPS_RE = re.compile(r"^TPPS-(\d\d)\.(\d\d)$")
KEEP_CHECKED = 6                      # 0x11fe0: checking stops once 6 entries are kept

# PDIPatchFileSystem node id -> file name (EBOOT 0x169a4 with 0x1659c and 0x168b0).
# Per id range: prefix character, Galois polynomial, bits, base-36 digits.
_RANGES = [
    (0x0, 0x400, "K", 0x499, 10, 2),
    (0x400, 0x8400, "5", 0x8891, 15, 3),
    (0x8400, 0x108400, "9", 0x111889, 20, 4),
    (0x108400, 0x2108400, "W", 0x2242211, 25, 5),
    (0x2108400, 0x2108400 + 0x80000000, "4", 0x88891111, 31, 6),
]
_DIGITS = "K59W4S6H7DOVJPERUQMT8BAIC2YLG30Z1FNX"   # va 0x3d110


def _scramble(poly, bits, x):
    """0x1659c: shift x left `bits` times, reducing by poly whenever bit `bits` is set."""
    for _ in range(bits):
        x <<= 1
        if x & (1 << bits):
            x ^= poly
    return x


def node_name(node_id):
    """The PDIPFS path of a node, for example 1 -> "K/4D", 42258 -> "9/JF/OC"."""
    for lo, hi, prefix, poly, bits, n in _RANGES:
        if lo <= node_id < hi:
            v = _scramble(poly, bits, node_id - lo)
            digits = []
            for _ in range(n):
                digits.append(_DIGITS[v % 36])
                v //= 36
            s, k = prefix, n
            if k % 2:
                s += digits[k - 1]
                k -= 1
            while k:
                s += "/" + digits[k - 1] + digits[k - 2]
                k -= 2
            return s
    raise ValueError(f"node id out of range: {node_id}")


def parse_node_line(line):
    """One UPDATENODEINFO entry: id size type ref hash flag size7 [size8].

    The installed TPPS copies have 7 columns; a missing 8th column equals the 7th
    (measured: the EBOOT writes it so, FINDINGS)."""
    f = line.split()
    size8 = int(f[7]) if len(f) > 7 else int(f[6])
    return [int(f[0]), int(f[1]), int(f[2]), int(f[3]), f[4], int(f[5]), int(f[6]), size8]


def format_node_line(e):
    """The EBOOT's writer format (va 0x3ed28)."""
    return "%06d %010d %1d %06d %s %1d %010d %010d\n" % tuple(e)


def read_node_info(path):
    return [parse_node_line(l) for l in Path(path).read_text().splitlines() if l.strip()]


def merge_node_info(staged, current, installed_size):
    """EBOOT 0x1143c's merge of TPPS node info (staged) with UPDATENODEINFO.MMmm (current).

    Walking staged in order while still checking: the entry with the same id in current
    replaces it and is removed from current; if PDIPFS/<name> exists with size equal to
    the entry's column 2 or column 8 the file is already installed and the entry is
    dropped. Checking stops once 6 entries are kept; later entries are kept as staged.
    installed_size(name) returns the main PDIPFS file's size, or None if absent.
    Returns the kept entries; the dropped ids are those missing from the result."""
    current = list(current)
    out, checking = [], True
    for entry in staged:
        if checking and current:
            match = next((j for j, c in enumerate(current) if c[0] == entry[0]), None)
            if match is not None:
                entry = current.pop(match)
                size = installed_size(node_name(entry[0]))
                if size is not None and size in (entry[1], entry[7]):
                    continue
        out.append(entry)
        if len(out) >= KEEP_CHECKED:
            checking = False
    return out


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def in_git_work_tree(path):
    """True if path (which may not exist yet) is inside the repo or any git work tree."""
    path = Path(path).resolve()
    if path == REPO or REPO in path.parents:
        return True
    probe = path
    while not probe.exists():
        probe = probe.parent
    p = subprocess.run(["git", "-C", str(probe), "rev-parse", "--is-inside-work-tree"],
                       capture_output=True, text=True)
    return p.returncode == 0 and p.stdout.strip() == "true"


def apply_eboot_effects(root):
    """Apply the 1.22 EBOOT's on-disk effects in root (the folder holding dev_hdd0). Returns
    the list of applied changes (path relative to the play folder, sha256, details)."""
    usr = Path(root) / GAME
    applied = []
    upd = usr / "TPPS-01.07" / "update.txt"
    if upd.is_file():                       # opened write+truncate, never created
        upd.write_text(UPDATE_TXT)
        applied.append({"path": f"{GAME}/TPPS-01.07/update.txt", "sha256": _sha256(upd),
                        "change": f"rewritten to {UPDATE_TXT!r}"})

    main = usr / "PDIPFS"

    def installed_size(name):
        p = main / name
        return p.stat().st_size if p.exists() else None

    for d in sorted(usr.iterdir()):
        m = TPPS_RE.match(d.name)
        if not m or not d.is_dir():
            continue
        node = d / "PDIPFS" / "UPDATENODEINFO"
        src = usr / "UPDATENODEINFO" / f"UPDATENODEINFO.{m.group(1)}{m.group(2)}"
        if not (node.is_file() and src.is_file() and (d / "PDIPFS" / "K" / "4D").is_file()):
            continue
        staged, current = read_node_info(node), read_node_info(src)
        if len(staged) != len(current):     # 0x11b00: counts must match
            continue
        merged = merge_node_info(staged, current, installed_size)
        tmp = node.with_name("UPDATENODEINFO.upd")
        tmp.write_text("".join(format_node_line(e) for e in merged))
        node.unlink()
        tmp.rename(node)
        kept = {e[0] for e in merged}
        applied.append({
            "path": f"{GAME}/{d.name}/PDIPFS/UPDATENODEINFO", "sha256": _sha256(node),
            "change": f"rebuilt from UPDATENODEINFO/{src.name}",
            "entries": len(merged), "dropped": [e[0] for e in staged if e[0] not in kept]})
    return applied


TOOL = "scripts/prepare_play.py"
STAGING_MARK = ".prepare_play-staging"


def _made_by_us(folder):
    """True if folder holds a prepare.json written by this tool."""
    try:
        return json.loads((Path(folder) / "prepare.json").read_text()).get("tool") == TOOL
    except (OSError, ValueError, AttributeError):
        return False


def _ours(folder):
    """A staging or .old folder this tool left: it has the staging marker or prepare.json
    (a run killed after the marker was dropped, or between the two renames)."""
    return (Path(folder) / STAGING_MARK).is_file() or _made_by_us(folder)


def prepare(tree, out=None, force=False):
    """Make the play folder (default <tree>/play; out= is for tests only, the CLI has none).

    The folder is built in a staging folder beside it and renamed into place only after
    prepare.json is written, so an interrupted run never leaves a play folder without the
    EBOOT's effects. Only a folder holding this tool's prepare.json is ever replaced, and
    never the tree itself or a folder that contains it."""
    tree = Path(tree).resolve()
    out = Path(out).resolve() if out else tree / "play"
    if out == tree or out in tree.parents:
        raise SystemExit(f"error: {out} is the verified tree or contains it; refusing")
    if in_git_work_tree(out):
        raise SystemExit(f"error: {out} is inside a git work tree; the play folder holds "
                         "game files and must be outside the repository (D26)")
    hdd0 = tree / "dev_hdd0"
    if not (tree / GAME).is_dir():
        raise SystemExit(f"error: {tree} has no {GAME} (not a gt6unpack build tree?)")
    if out.exists():
        if not force:
            raise SystemExit(f"error: {out} exists (a first run has changed it); "
                             "use --force to delete it and clone the verified tree again")
        if not _made_by_us(out):
            raise SystemExit(f"error: {out} has no prepare.json written by {TOOL}; "
                             "refusing to delete a folder this tool did not make")
    staging = out.with_name("." + out.name + ".staging")
    old = out.with_name("." + out.name + ".old")
    for p in (staging, old):
        if p == tree or p in tree.parents:
            raise SystemExit(f"error: {p} is the verified tree or contains it; refusing")
        if p.exists() and not _ours(p):
            raise SystemExit(f"error: {p} exists and was not made by {TOOL}; refusing")
    if staging.exists():
        shutil.rmtree(staging)                 # left behind by a killed run
    staging.mkdir(parents=True)
    try:
        (staging / STAGING_MARK).write_text("")
        subprocess.run(["cp", "-c", "-R", str(hdd0), str(staging / "dev_hdd0")], check=True)
        applied = apply_eboot_effects(staging)
        build = tree / "build.json"
        info = json.loads(build.read_text()) if build.is_file() else {}
        record = {
            "tool": TOOL,
            "source": {"tree": str(tree),
                       "build_json_sha256": _sha256(build) if build.is_file() else None,
                       **{k: info.get(k) for k in ("tool", "tool_version", "title_id",
                                                   "final_app_ver")}},
            "applied": applied,
            "notes": ["The EBOOT also reads TPPS-MM.mm/PDIPFS/K/4D and compares it before the "
                      "merge (0x161ac, 0x32b88); that check is not reproduced, only that K/4D "
                      "exists. It passed for all five versions in the measured run (FINDINGS)."],
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        }
        (staging / "prepare.json").write_text(json.dumps(record, indent=1) + "\n")
        (staging / STAGING_MARK).unlink()
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if old.exists():                            # checked above: ours, from a killed run
        shutil.rmtree(old)
    if out.exists():                            # checked above: ours, and --force given
        out.rename(old)
    staging.rename(out)
    if old.exists():
        shutil.rmtree(old)
    return record



def disc_layer_writable(tree):
    """None when <tree>/dev_bdvd, the verified disc layer, is read-only on the host (D46);
    otherwise what is writable there (the folder itself or the first writable entry)."""
    root = Path(tree).expanduser() / "dev_bdvd"
    if not root.is_dir():
        return None
    for d, dirs, files in os.walk(root):
        for name in [d] + [os.path.join(d, f) for f in dirs + files]:
            if not os.path.islink(name) and os.stat(name).st_mode & 0o222:
                return f"{name} is writable; the verified disc layer must be read-only"
    return None

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tree", type=Path, help="verified gt6unpack build tree")
    ap.add_argument("--force", action="store_true", help="delete an existing play folder first")
    args = ap.parse_args(argv)
    rec = prepare(args.tree, force=args.force)
    guard = disc_layer_writable(args.tree)
    if guard:
        print(f"WARNING: {guard} (D46). The game's file calls cannot write there, but a stray "
              f"host write could change the verified copy. Run: chmod -R a-w "
              f"\"{Path(args.tree).expanduser() / 'dev_bdvd'}\" (boot_game.py refuses until then)",
              file=sys.stderr)
    for a in rec["applied"]:
        print(f"applied {a['path']}: {a['change']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

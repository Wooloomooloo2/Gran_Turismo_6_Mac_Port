#!/usr/bin/env python3
"""Map GT6's code with ps3recomp's analysis tools (dev-only, never shipped).

Usage:
    .venv/bin/python scripts/map_game.py <out> [-o <out>/map] [--elf PATH ...]

<out> is a gt6unpack build tree (it has decrypted/). By default the two
executables that run on a v1.22 console are mapped: the update EBOOT.BIN and the
USRDIR/EMAIN.SELF it launches (docs/FINDINGS.md, "What the 1.22 EBOOT launches").
--elf (repeatable) maps other decrypted ELFs instead.

For each ELF it runs ps3recomp's ppu_loader, find_functions, gen_imports,
extract_spu_images and extract_jobmods, then scans the ELF for job modules stored
raw (extract_jobmods only looks inside SDATA archives). Every decrypted ELF under
<out>/decrypted also gets a size and SHA-256 identity row. Results:

    <map>/<slug>/            per-ELF tool outputs, logs/ and tools.json
    <map>/identity.json      size + SHA-256 of every decrypted ELF
    <map>/summary.json       summarize(<map>)

The outputs hold game code, so <map> must be outside the repository.
"""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PS3RECOMP = REPO / "third_party" / "ps3recomp"
TITLE_USRDIR = Path("dev_hdd0/game/BCES01977/USRDIR")
LAUNCHED_PAIR = ("EBOOT.BIN.elf", "EMAIN.SELF.elf")

# python -I leaves the script's own folder off sys.path, and some ps3recomp tools
# (extract_spu_images.py) import siblings without adding it themselves. This runs
# a tool in isolated mode with only its own tools/ folder added.
RUNNER = ("import os, runpy, sys; t = sys.argv[1]; "
          "sys.path.insert(0, os.path.dirname(os.path.abspath(t))); "
          "sys.argv = sys.argv[1:]; runpy.run_path(t, run_name='__main__')")

JOBMOD_MARKER = b"\xc0\xde\xc0\xde"
SPU_LOCAL_STORE = 256 * 1024
REQUIRED = ("functions.json", "imports_named.json", "spu_images.json",
            "jobmods.json", "tools.json")


# ---------------------------------------------------------------- summarize

def _load(path, errors):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        errors.append(f"missing {path.name}")
    except (OSError, ValueError) as e:
        errors.append(f"unreadable {path.name}: {e}")
    return None


def _ranked(counter):
    return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))


def summarize_elf(d):
    """One ELF's entry, from the tool outputs in folder d."""
    errors = []
    meta = _load(d / "elf.json", errors) or {}
    got = {name: _load(d / name, errors) for name in REQUIRED}
    loaders = sorted((d / "loader").glob("*.loader.json"))
    loader = _load(loaders[0], errors) if loaders else None
    if not loaders:
        errors.append("missing loader/<name>.loader.json")

    entry = {"path": meta.get("path"), "bytes": meta.get("bytes"),
             "sha256": meta.get("sha256"), "functions": None, "opd_functions": None,
             "imports": None, "unresolved_nids": None, "unresolved_by_module": None,
             "spu_images": None, "jobmods": None, "jobmod_bytes": None,
             "tool_failures": None}
    if got["functions.json"] is not None:
        entry["functions"] = len(got["functions.json"])
    if loader is not None:
        entry["opd_functions"] = loader.get("function_count")
    imports = got["imports_named.json"]
    if imports is not None:
        entry["imports"] = _ranked(Counter(i["lib"] for i in imports))
        missing = Counter(i["lib"] for i in imports if not i.get("name"))
        entry["unresolved_nids"] = sum(missing.values())
        entry["unresolved_by_module"] = _ranked(missing)
    if got["spu_images.json"] is not None:
        entry["spu_images"] = [{"name": s["name"], "size": s["size"]}
                               for s in got["spu_images.json"]]
    if got["jobmods.json"] is not None:
        entry["jobmods"] = len(got["jobmods.json"])
        entry["jobmod_bytes"] = sum(j["size"] for j in got["jobmods.json"])
    if got["tools.json"] is not None:
        entry["tool_failures"] = sorted(n for n, t in got["tools.json"].items()
                                        if not t.get("ok"))
    if errors:
        entry["error"] = "; ".join(errors)
    return entry


def summarize(tool_outputs_dir):
    """Summary dict from a map folder: one entry per <slug>/elf.json, plus totals."""
    root = Path(tool_outputs_dir)
    elfs = [summarize_elf(p.parent) for p in root.glob("*/elf.json")]
    elfs.sort(key=lambda e: e["path"] or "")

    def total(key, fn=lambda v: v):
        return sum(fn(e[key]) for e in elfs if e[key] is not None)

    totals = {
        "functions": total("functions"),
        "imports": total("imports", lambda v: sum(v.values())),
        "unresolved_nids": total("unresolved_nids"),
        "spu_images": total("spu_images", len),
        "spu_bytes": total("spu_images", lambda v: sum(s["size"] for s in v)),
        "jobmods": total("jobmods"),
        "jobmod_bytes": total("jobmod_bytes"),
    }
    ignored = []
    run = _load(root / "run.json", ignored) or {}
    identity = _load(root / "identity.json", ignored) or []
    return {"elfs": elfs, "totals": totals, "identity": identity,
            "run_seconds": run.get("seconds"),
            "ps3recomp_commit": run.get("ps3recomp_commit")}


# ---------------------------------------------------------------- helpers

def find_embedded_jobmods(buf):
    """[(offset, bytes)] of WWS job modules stored raw in buf.

    Header as in ps3recomp tools/extract_jobmods.py: four `ila` words (first byte
    0x42/0x43), entry offset at 0x10, image size at 0x14, 0xC0DEC0DE at 0x20; the
    initialised image is image size - 32 bytes.
    """
    found = []
    i = buf.find(JOBMOD_MARKER)
    while i != -1:
        h = i - 0x20
        if h >= 0 and buf[h] in (0x42, 0x43):
            entry, image = struct.unpack_from(">II", buf, h + 0x10)
            size = image - 32
            if 0x30 <= size <= SPU_LOCAL_STORE and entry < size and h + size <= len(buf):
                found.append((h, buf[h:h + size]))
        i = buf.find(JOBMOD_MARKER, i + 1)
    return found


def jobmod_name(module):
    """File name ps3recomp's extract_jobmods.py gives a module."""
    entry = struct.unpack_from(">I", module, 0x10)[0]
    return f"jobmod_{hashlib.sha1(module).hexdigest()[:12]}_e{entry:04X}.bin"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def identity(decrypted_dir, mapped=()):
    """Size and SHA-256 of every *.elf under decrypted_dir, with identical copies."""
    root = Path(decrypted_dir)
    mapped = {Path(m).resolve() for m in mapped}
    rows = []
    for p in sorted(root.rglob("*.elf")):
        rows.append({"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size,
                     "sha256": sha256_file(p), "mapped": p.resolve() in mapped})
    for r in rows:
        r["same_as"] = [o["path"] for o in rows if o is not r and o["sha256"] == r["sha256"]]
    return rows


def slug(rel):
    """Folder name for an ELF's outputs. Avoids the .elf/.self names git ignores."""
    rel = rel[:-4] if rel.lower().endswith(".elf") else rel
    return rel.replace("/", "__").replace(".", "_")


def default_elfs(out):
    d = Path(out) / "decrypted" / TITLE_USRDIR
    return [d / name for name in LAUNCHED_PAIR]


def _inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- real run

def run_tool(python, tools, name, args, logs):
    cmd = [python, "-I", "-c", RUNNER, str(tools / f"{name}.py"), *map(str, args)]
    t0 = time.monotonic()
    p = subprocess.run(cmd, capture_output=True, text=True)
    seconds = round(time.monotonic() - t0, 2)
    log = logs / f"{name}.log"
    log.write_text(f"$ {' '.join(cmd)}\nexit {p.returncode}\n--- stdout\n{p.stdout}"
                   f"--- stderr\n{p.stderr}")
    ok = p.returncode == 0
    if name == "extract_spu_images" and p.returncode == 1 and "No SPU images found." in p.stdout:
        ok = True  # the tool exits 1 when it finds none
    if not ok:
        last = (p.stderr.strip() or p.stdout.strip()).splitlines()[-1:] or [""]
        print(f"  {name} FAILED (exit {p.returncode}): {last[0]}", file=sys.stderr)
    return {"cmd": cmd, "exit": p.returncode, "ok": ok, "seconds": seconds,
            "log": log.name}


def map_one(elf, out, map_dir, python, tools):
    dec = out / "decrypted"
    rel = elf.relative_to(dec).as_posix() if _inside(elf, dec) else elf.name
    usrdir = out / Path(rel).parent if _inside(elf, dec) else elf.parent
    d = map_dir / slug(rel)
    if d.exists():
        shutil.rmtree(d)
    logs = d / "logs"
    logs.mkdir(parents=True)
    print(f"{rel}")

    data = elf.read_bytes()
    (d / "elf.json").write_text(json.dumps(
        {"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
        indent=1))

    status = {}
    status["ppu_loader"] = run_tool(python, tools, "ppu_loader", [elf, "-o", d / "loader"], logs)
    status["find_functions"] = run_tool(python, tools, "find_functions",
                                        [elf, "-o", d / "functions.json"], logs)
    status["gen_imports"] = run_tool(python, tools, "gen_imports",
                                     [elf, "-o", d / "imports_named.json"], logs)
    spu = d / "spu_images"
    status["extract_spu_images"] = run_tool(python, tools, "extract_spu_images",
                                            [elf, "-o", spu], logs)
    if status["extract_spu_images"]["ok"]:
        imgs = sorted(spu.glob("*.elf")) if spu.is_dir() else []
        (d / "spu_images.json").write_text(json.dumps(
            [{"name": p.name, "size": p.stat().st_size} for p in imgs], indent=1))
    sdata = d / "jobmods_sdata"
    status["extract_jobmods"] = run_tool(python, tools, "extract_jobmods",
                                         ["--usrdir", usrdir, "--out", sdata], logs)
    (d / "tools.json").write_text(json.dumps(status, indent=1))

    jobmods = {}
    for p in sorted(sdata.glob("*.bin")) if sdata.is_dir() else []:
        jobmods[p.name] = {"name": p.name, "size": p.stat().st_size, "source": "sdata"}
    emb = d / "jobmods_embedded"
    emb.mkdir()
    for off, mod in find_embedded_jobmods(data):
        name = jobmod_name(mod)
        if name not in jobmods:
            (emb / name).write_bytes(mod)
            jobmods[name] = {"name": name, "size": len(mod), "source": "embedded",
                             "offset": off}
    (d / "jobmods.json").write_text(json.dumps(list(jobmods.values()), indent=1))


def ps3recomp_commit(root):
    p = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return p.stdout.strip() or None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Map GT6's code with ps3recomp (dev-only).")
    ap.add_argument("out", help="gt6unpack build tree (holds decrypted/)")
    ap.add_argument("-o", "--output", help="map folder (default: <out>/map)")
    ap.add_argument("--elf", action="append", default=[], metavar="PATH",
                    help="decrypted ELF to map (repeatable; default: the launched "
                         "EBOOT.BIN + USRDIR/EMAIN.SELF)")
    ap.add_argument("--ps3recomp", default=str(DEFAULT_PS3RECOMP),
                    help="ps3recomp checkout (default: the submodule)")
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter with ps3recomp's dependencies (default: this one)")
    args = ap.parse_args(argv)

    out = Path(args.out).expanduser().resolve()
    map_dir = Path(args.output).expanduser().resolve() if args.output else out / "map"
    if _inside(map_dir, REPO):
        ap.exit(2, f"error: {map_dir} is inside the repository; map outputs hold game "
                   f"code and must live outside it\n")
    elfs = [Path(e).expanduser().resolve() for e in args.elf] or default_elfs(out)
    missing = [str(e) for e in elfs if not e.is_file()]
    if missing:
        ap.exit(2, "error: ELF not found: " + ", ".join(missing) + "\n")
    tools = Path(args.ps3recomp) / "tools"
    if not (tools / "ppu_loader.py").is_file():
        ap.exit(2, f"error: no ps3recomp tools at {tools} "
                   f"(git submodule update --init third_party/ps3recomp)\n")

    t0 = time.monotonic()
    map_dir.mkdir(parents=True, exist_ok=True)
    for elf in elfs:
        map_one(elf, out, map_dir, args.python, tools)
    dec = out / "decrypted"
    rows = identity(dec, mapped=elfs) if dec.is_dir() else []
    (map_dir / "identity.json").write_text(json.dumps(rows, indent=1))
    (map_dir / "run.json").write_text(json.dumps(
        {"seconds": round(time.monotonic() - t0, 1),
         "ps3recomp_commit": ps3recomp_commit(Path(args.ps3recomp))}, indent=1))
    summary = summarize(map_dir)
    (map_dir / "summary.json").write_text(json.dumps(summary, indent=1))

    for e in summary["elfs"]:
        note = f"  ERROR {e['error']}" if "error" in e else ""
        print(f"{e['path']}: {e['functions']} functions, "
              f"{sum((e['imports'] or {}).values())} imports "
              f"({e['unresolved_nids']} unresolved), "
              f"{len(e['spu_images'] or [])} SPU images, {e['jobmods']} job modules{note}")
    print(f"summary -> {map_dir / 'summary.json'} ({summary['run_seconds']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

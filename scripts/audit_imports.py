#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Which of EMAIN's imports ps3recomp handles, and which ones GT6 called in boot runs.

Usage:
    .venv/bin/python scripts/audit_imports.py "$GT6_TREE" [--runs] [--calls FILE] [-o OUT]

Prints one row per import, `module, name, nid, handled, called_in_runs`, then the counts,
and writes `<tree>/recomp/import_audit.json` (or OUT, which must lie outside any git work
tree: the audit names the title's imports and is generated output, D26).

An import is handled when ps3recomp's runtime has a handler registered for its NID. Two
registration paths exist, and both are read:
  - the generic table that `tools/gen_hle_nids.py --all` writes from libs/** (the port's
    build runs exactly that; every non-static cell*/sys*/sce* function is registered under
    the NID computed from its name);
  - the handlers the runtime registers itself with ps3_hle_register_ctx /
    ps3_hle_register_fast (runtime/**, libs/**, and the port's own sources), which the
    dispatcher tries first.
An unhandled import takes the dispatcher's unresolved path: it is logged as
`hle:unresolved:0x<NID>` and answers CELL_OK with its out-parameters untouched.

Miscount guards (plan, review focus 5):
  - `collisions`: one NID registered under two different names. The first registration
    wins at run time, so the second name is silently not what runs; flagged, never merged.
  - `mismatches`: a literal NID whose name hashes to a different NID.
  - `unresolved_but_handled`: a run logged a NID unresolved that the audit counts handled
    (the run predates the patches, or the audit is wrong).
  - `generated_table`: with a built tree, the port's real `ppu_hle_nids.cpp` is compared
    with the audit's own reading of libs/**.
  - `capacity`: ps3_hle_register_ctx keeps at most HLE_CTX_CAP handlers and drops the rest.

`--runs` reads `<tree>/runs/*/milestones.log`: a run called an import if it logged
`hle:<name>` (or `hle:unresolved:0x<NID>`) for it. `--calls` takes a list of function names
(one per line, as in the RPCS3 reference's calls.txt) and marks the imports RPCS3 saw called.
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translate_game import in_git_work_tree  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PS3RECOMP = REPO / "third_party" / "ps3recomp"
PORT = REPO / "port"
DEFAULT_RPCS3 = Path.home() / "Developer" / "others" / "rpcs3"

_gen = None


def _gen_module():
    """ps3recomp's own gen_hle_nids.py (its scanner and NID function), from the submodule."""
    global _gen
    if _gen is None:
        tools = PS3RECOMP / "tools"
        sys.path.insert(0, str(tools))
        spec = importlib.util.spec_from_file_location("gen_hle_nids", tools / "gen_hle_nids.py")
        _gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_gen)
    return _gen


def compute_nid(name):
    return _gen_module().compute_nid(name)


REG_RE = re.compile(
    r"\bps3_hle_register(_ctx|_fast)?\s*\(\s*"
    r"(?:ps3_compute_nid\s*\(\s*\"(\w+)\"\s*\)|0x([0-9A-Fa-f]{1,8})[uU]?)\s*,\s*"
    r"(?:\"(\w+)\")?")
SOURCE_GLOBS = ("**/*.c", "**/*.cpp", "**/*.cc", "**/*.m", "**/*.mm")


def _table_registrations(root):
    """What gen_hle_nids.py --all registers for the ps3recomp at root, in its order, keeping
    every (nid, name) it sees, so a second name for one NID is not lost (gen keeps the first)."""
    gen = _gen_module()
    saved = gen.ROOT
    gen.ROOT = str(root)
    try:
        libs = gen.discover_all()
    finally:
        gen.ROOT = saved
    out = []
    for lib in libs:
        cs = glob.glob(os.path.join(str(root), "libs", "**", lib + ".c"), recursive=True)
        if not cs:
            continue
        rel = Path(cs[0]).relative_to(root).as_posix()
        for nid, name in gen.scan(cs[0]):
            out.append({"nid": nid, "name": name, "kind": "table", "source": rel})
    return out


def _source_registrations(base, label):
    out = []
    for pattern in SOURCE_GLOBS:
        for p in sorted(Path(base).glob(pattern)):
            rel = p.relative_to(base).as_posix()
            if "/tests/" in "/" + rel or rel.startswith("tests/"):
                continue
            text = p.read_text(encoding="latin1")
            for m in REG_RE.finditer(text):
                kind = {"_ctx": "ctx", "_fast": "fast"}.get(m.group(1), "direct")
                computed, literal, name = m.group(2), m.group(3), m.group(4)
                nid = compute_nid(computed) if computed else int(literal, 16)
                line = text.count("\n", 0, m.start()) + 1
                out.append({"nid": nid, "name": name or computed, "kind": kind,
                            "source": f"{label}{rel}:{line}", "literal": literal is not None})
    return out


def registrations(ps3recomp, extra=()):
    """Every handler registration: the generated table, then the runtime's own calls."""
    root = Path(ps3recomp)
    regs = _table_registrations(root)
    for d in ("runtime", "libs"):
        if (root / d).is_dir():
            regs += _source_registrations(root / d, d + "/")
    for e in extra:
        if Path(e).is_dir():
            regs += _source_registrations(Path(e), Path(e).name + "/")
    return regs


def parse_generated_table(text):
    """[(nid, name)] from a ppu_hle_nids.cpp written by gen_hle_nids.py."""
    return [(int(m.group(1), 16), m.group(2)) for m in
            re.finditer(r'ps3_hle_register\(0x([0-9A-Fa-f]+)u, "(\w+)"', text)]


def capacity(ps3recomp, regs):
    """ps3_hle_register_ctx drops registrations past HLE_CTX_CAP (runtime/ppu/ppu_hle.cpp)."""
    src = Path(ps3recomp) / "runtime" / "ppu" / "ppu_hle.cpp"
    caps = {}
    if src.exists():
        text = src.read_text(encoding="latin1")
        for key in ("HLE_CTX_CAP", "HLE_NID_CAP"):
            m = re.search(rf"#define {key} (\d+)", text)
            if m:
                caps[key] = int(m.group(1))
    used = {"HLE_CTX_CAP": sum(r["kind"] == "ctx" for r in regs),
            "HLE_NID_CAP": len({r["nid"] for r in regs if r["kind"] == "table"})}
    return {k: {"cap": caps[k], "used": used[k], "over": used[k] > caps[k]} for k in caps}


def known_names(ps3recomp=PS3RECOMP, rpcs3=None):
    """NID -> name for imports with no handler: ps3recomp's NID database and, when given, the
    function names RPCS3's HLE modules register (names only; the NID is the name's hash)."""
    tools = Path(ps3recomp) / "tools"
    names = {}
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    spec = importlib.util.spec_from_file_location("nid_database", tools / "nid_database.py")
    nd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nd)
    db = nd.NIDDatabase()
    db.load_builtins()
    protos = tools / "nid_from_protos.json"
    if protos.exists():
        db.load_json(str(protos))
    for nid, _mod, name in db.all_entries():
        names.setdefault(nid, name)
    if rpcs3 and Path(rpcs3).is_dir():
        mods = Path(rpcs3) / "rpcs3" / "Emu" / "Cell" / "Modules"
        lv2 = Path(rpcs3) / "rpcs3" / "Emu" / "Cell" / "lv2"
        for p in sorted(list(mods.glob("*.cpp")) + list(lv2.glob("*.cpp"))):
            for m in re.finditer(r"\bREG_(?:FUNC|VAR)\s*\(\s*\w+\s*,\s*(\w+)\s*\)",
                                 p.read_text(encoding="latin1")):
                names.setdefault(compute_nid(m.group(1)), m.group(1))
    return names


def load_runs(runs_dir):
    """run id -> the set of milestone keys it logged (every `hle:`/`sys:` key, any count)."""
    out = {}
    for log in sorted(Path(runs_dir).glob("*/milestones.log")):
        keys = set()
        for line in log.read_text(errors="replace").splitlines():
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 3 and parts[0] == "count":
                keys.add(parts[1])
            elif len(parts) >= 2:
                keys.add(parts[1])
        out[log.parent.name] = keys
    return out


def audit(imports, regs, runs=None, names=None, calls=None):
    """The audit result: one row per distinct (module, NID) import, plus the miscount guards."""
    runs = runs or {}
    names = names or {}
    calls = set(calls or ())
    by_nid = {}
    for r in regs:
        by_nid.setdefault(r["nid"], [])
        if r["name"] and r["name"] not in by_nid[r["nid"]]:
            by_nid[r["nid"]].append(r["name"])
    collisions = [{"nid": f"0x{nid:08X}", "names": sorted(ns)}
                  for nid, ns in sorted(by_nid.items()) if len(ns) > 1]
    collided = {int(c["nid"], 16) for c in collisions}
    mismatches = [{"nid": f"0x{r['nid']:08X}", "name": r["name"], "source": r["source"]}
                  for r in regs if r.get("literal") and r["name"]
                  and compute_nid(r["name"]) != r["nid"]]

    seen, rows = set(), []
    for imp in imports:
        nid = int(str(imp["nid"]), 16)
        key = (imp["library"], nid)
        if key in seen:
            continue
        seen.add(key)
        handled = nid in by_nid
        regnames = by_nid.get(nid, [])
        name = "|".join(regnames) if regnames else names.get(nid, "?")
        unresolved_key = f"hle:unresolved:0x{nid:08X}"
        hit_keys = {unresolved_key} | {f"hle:{n}" for n in regnames}
        if nid in names:
            hit_keys.add(f"hle:{names[nid]}")
        called = sorted(run for run, keys in runs.items() if keys & hit_keys)
        rows.append({"module": imp["library"], "name": name, "nid": f"0x{nid:08X}",
                     "handled": handled, "collision": nid in collided,
                     "called_in_runs": len(called), "runs": called,
                     "unresolved_in": sorted(run for run, keys in runs.items()
                                             if unresolved_key in keys),
                     "called_in_rpcs3": bool(calls & ({names.get(nid)} | set(regnames)))})
    rows.sort(key=lambda r: (r["handled"], -r["called_in_runs"], r["module"], r["name"]))
    stale = [{"nid": r["nid"], "runs": r["unresolved_in"]}
             for r in rows if r["handled"] and r["unresolved_in"]]
    summary = {
        "imports": len(rows),
        "handled": sum(r["handled"] for r in rows),
        "unhandled": sum(not r["handled"] for r in rows),
        "unhandled_called": sum(not r["handled"] and r["called_in_runs"] > 0 for r in rows),
        "unhandled_called_in_rpcs3": sum(not r["handled"] and r["called_in_rpcs3"] for r in rows),
        "runs": len(runs),
        "registrations": len(regs),
        "collisions": len(collisions),
        "mismatches": len(mismatches),
    }
    return {"summary": summary, "rows": rows, "collisions": collisions,
            "mismatches": mismatches, "unresolved_but_handled": stale}


def _table(rows):
    w = max([len(r["name"]) for r in rows] + [4])
    m = max([len(r["module"]) for r in rows] + [6])
    lines = [f"{'module':<{m}}  {'name':<{w}}  {'nid':<10}  handled  called_in_runs"]
    for r in rows:
        mark = " (collision)" if r["collision"] else ""
        lines.append(f"{r['module']:<{m}}  {r['name']:<{w}}  {r['nid']:<10}  "
                     f"{'yes' if r['handled'] else 'no':<7}  {r['called_in_runs']}{mark}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tree", type=Path, help="the GT6 build tree ($GT6_TREE)")
    ap.add_argument("--runs", action="store_true", help="count calls in <tree>/runs/*")
    ap.add_argument("--calls", type=Path, help="function names a reference run called")
    ap.add_argument("--ps3recomp", type=Path, default=PS3RECOMP)
    ap.add_argument("--rpcs3", type=Path, default=DEFAULT_RPCS3,
                    help="RPCS3 source, for import names only (skipped if absent)")
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args(argv)

    out = args.output or args.tree / "recomp" / "import_audit.json"
    if in_git_work_tree(out):
        ap.exit(2, f"error: {out} is inside a git work tree; the audit lists the title's imports "
                   "and must be written outside it (D26)\n")
    imports_json = args.tree / "recomp" / "loader" / "EMAIN.SELF.imports.json"
    if not imports_json.exists():
        ap.exit(2, f"error: no {imports_json} (run scripts/translate_game.py first)\n")
    imports = json.loads(imports_json.read_text())

    regs = registrations(args.ps3recomp, extra=(PORT,))
    runs = load_runs(args.tree / "runs") if args.runs else {}
    calls = args.calls.read_text().split() if args.calls else ()
    result = audit(imports, regs, runs=runs, names=known_names(args.ps3recomp, args.rpcs3),
                   calls=calls)
    result["capacity"] = capacity(args.ps3recomp, regs)
    gen_table = args.tree / "port-build" / "port" / "ppu_hle_nids.cpp"
    if gen_table.exists():
        built = {nid for nid, _ in parse_generated_table(gen_table.read_text())}
        mine = {r["nid"] for r in regs if r["kind"] == "table"}
        result["generated_table"] = {"path": str(gen_table),
                                     "only_in_build": sorted(f"0x{n:08X}" for n in built - mine),
                                     "only_in_audit": sorted(f"0x{n:08X}" for n in mine - built)}

    print(_table(result["rows"]))
    s = result["summary"]
    print(f"\n{s['imports']} imports: {s['handled']} handled, {s['unhandled']} unhandled "
          f"({s['unhandled_called']} of them called in {s['runs']} run(s), "
          f"{s['unhandled_called_in_rpcs3']} called by the reference run); "
          f"{s['registrations']} registrations, {s['collisions']} NID collision(s), "
          f"{s['mismatches']} literal NID mismatch(es)")
    for c in result["collisions"]:
        print(f"collision: {c['nid']} registered as {', '.join(c['names'])}")
    for m in result["mismatches"]:
        print(f"mismatch: {m['nid']} registered as {m['name']} ({m['source']})")
    for k, v in result["capacity"].items():
        if v["over"]:
            print(f"capacity: {v['used']} registrations exceed {k} {v['cap']}; the rest are dropped")
    g = result.get("generated_table")
    if g and (g["only_in_build"] or g["only_in_audit"]):
        print(f"generated table differs from the audit's reading: {len(g['only_in_build'])} only "
              f"in the build, {len(g['only_in_audit'])} only in the audit (stale build?)")
    if result["unresolved_but_handled"]:
        print(f"{len(result['unresolved_but_handled'])} import(s) logged unresolved in a run but "
              "handled now (older runs, or a miscount)")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

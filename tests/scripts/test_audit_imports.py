# SPDX-License-Identifier: GPL-2.0-or-later
"""The import audit counts handled and unhandled imports the way ps3recomp's runtime does.

A handled import is one with an entry in ps3recomp's registration table: the generic table that
gen_hle_nids.py writes from libs/**, plus the handlers the runtime registers itself
(ps3_hle_register_ctx / ps3_hle_register_fast). The real-table tests use a pristine export of
the pinned ps3recomp with our patches applied, so they do not depend on the submodule's working
tree.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "audit_imports.py"
SUB = REPO / "third_party" / "ps3recomp"
PATCHES = sorted((REPO / "patches" / "ps3recomp").glob("*.patch"))

_spec = importlib.util.spec_from_file_location("audit_imports", SCRIPT)
audit_imports = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit_imports)


def _pin():
    out = subprocess.run(["git", "ls-tree", "HEAD", "third_party/ps3recomp"], cwd=REPO,
                         capture_output=True, text=True).stdout.split()
    return out[2] if len(out) >= 3 and out[1] == "commit" else None


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    """The pinned ps3recomp, exported with git archive, with patches/ps3recomp applied."""
    pin = _pin()
    if not pin or not (SUB / ".git").exists():
        pytest.skip("no ps3recomp checkout (git submodule update --init third_party/ps3recomp)")
    tree = tmp_path_factory.mktemp("ps3recomp")
    archive = subprocess.run(["git", "archive", pin], cwd=SUB, check=True,
                             capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
    for p in PATCHES:
        subprocess.run(["git", "apply", "--whitespace=nowarn", str(p)], cwd=tree, check=True,
                       capture_output=True)
    return tree


@pytest.fixture(scope="module")
def real_table(pristine, tmp_path_factory):
    """The NIDs in the table gen_hle_nids.py --all writes for that export (what the port links)."""
    out = tmp_path_factory.mktemp("gen") / "ppu_hle_nids.cpp"
    subprocess.run([sys.executable, str(pristine / "tools" / "gen_hle_nids.py"), "--all",
                    "--out", str(out)], check=True, capture_output=True)
    return audit_imports.parse_generated_table(out.read_text())


def _imports(*pairs):
    return [{"library": lib, "nid": hex(nid), "stub": hex(0x1000 + 8 * i)}
            for i, (lib, nid) in enumerate(pairs)]


def test_known_handled_nid(pristine, real_table):
    regs = audit_imports.registrations(pristine)
    table = {r["nid"] for r in regs if r["kind"] == "table"}
    # every entry of the generated table is a table registration, and nothing more
    assert table == {nid for nid, _ in real_table}
    nid, name = real_table[0]
    ctx = next(r for r in regs if r["kind"] == "ctx")   # one the runtime registers itself
    result = audit_imports.audit(_imports(("lib", nid), ("other", ctx["nid"])), regs)
    rows = {r["nid"]: r for r in result["rows"]}
    assert rows[f"0x{nid:08X}"]["handled"] is True
    assert rows[f"0x{nid:08X}"]["name"] == name
    assert rows[f"0x{ctx['nid']:08X}"]["handled"] is True
    assert result["summary"]["handled"] == 2 and result["summary"]["unhandled"] == 0


def test_known_unhandled_nid(pristine, real_table):
    regs = audit_imports.registrations(pristine)
    handled = {r["nid"] for r in regs}
    names = audit_imports.known_names(pristine)
    # a named NID the runtime does not register (picked from the real table's complement)
    nid = next(n for n in sorted(names) if n not in handled)
    result = audit_imports.audit(_imports(("lib", nid)), regs, names=names)
    row = result["rows"][0]
    assert row["handled"] is False and row["name"] == names[nid]
    assert result["summary"] == {**result["summary"], "imports": 1, "handled": 0, "unhandled": 1}


def test_collision_reported(tmp_path):
    lib = tmp_path / "libs" / "system"
    lib.mkdir(parents=True)
    (lib / "cellFoo.c").write_text("int cellFooInit(void) { return 0; }\n")
    rt = tmp_path / "runtime" / "ppu"
    rt.mkdir(parents=True)
    nid = audit_imports.compute_nid("cellFooInit")
    # a second name registered under the same NID (a literal that does not match its name)
    (rt / "reg.cpp").write_text(
        f'void f(void) {{ ps3_hle_register_ctx(0x{nid:08X}u, "cellFooStart", foo_start); }}\n')
    regs = audit_imports.registrations(tmp_path)
    result = audit_imports.audit(_imports(("cellFoo", nid)), regs)
    assert result["collisions"] == [{"nid": f"0x{nid:08X}",
                                     "names": ["cellFooInit", "cellFooStart"]}]
    assert result["summary"]["collisions"] == 1
    row = result["rows"][0]
    assert row["handled"] is True
    assert row["collision"] is True and "cellFooStart" in row["name"]
    # the literal whose hash is not its name's is flagged too
    assert [m["name"] for m in result["mismatches"]] == ["cellFooStart"]


def test_same_name_twice_is_not_a_collision(tmp_path):
    lib = tmp_path / "libs" / "system"
    lib.mkdir(parents=True)
    (lib / "cellFoo.c").write_text("int cellFooInit(void) { return 0; }\n")
    rt = tmp_path / "runtime" / "ppu"
    rt.mkdir(parents=True)
    (rt / "reg.cpp").write_text(
        'void f(void) { ps3_hle_register_ctx(ps3_compute_nid("cellFooInit"), "cellFooInit", g); }\n')
    result = audit_imports.audit(_imports(("cellFoo", audit_imports.compute_nid("cellFooInit"))),
                                 audit_imports.registrations(tmp_path))
    assert result["collisions"] == [] and result["rows"][0]["collision"] is False


def test_called_in_runs(tmp_path):
    lib = tmp_path / "libs" / "system"
    lib.mkdir(parents=True)
    (lib / "cellFoo.c").write_text("int cellFooInit(void) { return 0; }\n")
    regs = audit_imports.registrations(tmp_path)
    a, b = audit_imports.compute_nid("cellFooInit"), 0x12345678
    runs = tmp_path / "runs"
    for run, lines in {"r1": ["1\thle:cellFooInit", f"2\thle:unresolved:0x{b:08X}"],
                       "r2": ["# counts", "count\thle:cellFooInit\t4"]}.items():
        (runs / run).mkdir(parents=True)
        (runs / run / "milestones.log").write_text("# ps3recomp milestone log v1\n"
                                                   + "\n".join(lines) + "\n")
    result = audit_imports.audit(_imports(("cellFoo", a), ("x", b)), regs,
                                 runs=audit_imports.load_runs(runs))
    rows = {r["nid"]: r for r in result["rows"]}
    assert rows[f"0x{a:08X}"]["called_in_runs"] == 2
    assert rows[f"0x{b:08X}"]["called_in_runs"] == 1
    assert result["summary"]["unhandled_called"] == 1


def test_unresolved_but_handled_is_flagged(tmp_path):
    """A run that logged a NID unresolved which the audit counts handled: an older run, or a miscount."""
    lib = tmp_path / "libs" / "system"
    lib.mkdir(parents=True)
    (lib / "cellFoo.c").write_text("int cellFooInit(void) { return 0; }\n")
    a = audit_imports.compute_nid("cellFooInit")
    (tmp_path / "runs" / "r1").mkdir(parents=True)
    (tmp_path / "runs" / "r1" / "milestones.log").write_text(f"1\thle:unresolved:0x{a:08X}\n")
    result = audit_imports.audit(_imports(("cellFoo", a)), audit_imports.registrations(tmp_path),
                                 runs=audit_imports.load_runs(tmp_path / "runs"))
    assert result["unresolved_but_handled"] == [{"nid": f"0x{a:08X}", "runs": ["r1"]}]


def test_refuses_output_in_git_tree(tmp_path):
    tree = tmp_path / "tree"
    (tree / "recomp" / "loader").mkdir(parents=True)
    (tree / "recomp" / "loader" / "EMAIN.SELF.imports.json").write_text("[]")
    out = REPO / "import_audit.json"
    r = subprocess.run([sys.executable, str(SCRIPT), str(tree), "-o", str(out)],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "git work tree" in r.stderr
    assert not out.exists()


def test_cli_writes_json(tmp_path):
    tree = tmp_path / "tree"
    (tree / "recomp" / "loader").mkdir(parents=True)
    (tree / "recomp" / "loader" / "EMAIN.SELF.imports.json").write_text(
        json.dumps(_imports(("cellGcmSys", audit_imports.compute_nid("cellGcmGetConfiguration")),
                            ("x", 0x12345678))))
    r = subprocess.run([sys.executable, str(SCRIPT), str(tree), "--runs"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "module" in r.stdout and "handled" in r.stdout
    data = json.loads((tree / "recomp" / "import_audit.json").read_text())
    assert data["summary"]["imports"] == 2
    assert data["summary"]["handled"] == 1


@pytest.mark.skipif(not os.environ.get("GT6_TREE"), reason="GT6_TREE not set (needs the built v1.22 tree)")
def test_real_tree_counts_match_latest_run():
    """On the real tree, every EMAIN NID a run logged unresolved (the newest run, then every older
    one) is counted unhandled, or listed in unresolved_but_handled for that run (handled since)."""
    tree = Path(os.environ["GT6_TREE"])
    imports = json.loads((tree / "recomp" / "loader" / "EMAIN.SELF.imports.json").read_text())
    result = audit_imports.audit(imports, audit_imports.registrations(SUB),
                                 runs=audit_imports.load_runs(tree / "runs"))
    runs = audit_imports.load_runs(tree / "runs")
    if not runs:
        pytest.skip("no runs in the tree")
    rows = {int(r["nid"], 16): r for r in result["rows"]}
    stale = {int(s["nid"], 16): s["runs"] for s in result["unresolved_but_handled"]}
    checked = 0
    # The newest run first, then every older one (the newest may log none once all are handled).
    for run in sorted(runs, reverse=True):
        logged = {int(k.rsplit(":", 1)[1], 16) for k in runs[run] if k.startswith("hle:unresolved:0x")}
        for nid in sorted(logged & rows.keys()):   # EBOOT's own imports are logged too; only EMAIN's are audited
            row = rows[nid]
            assert run in row["unresolved_in"], f"0x{nid:08X}: run {run} not recorded as unresolved"
            assert (not row["handled"]) or run in stale.get(nid, ()), \
                f"0x{nid:08X} logged unresolved in {run} but counted handled and not in unresolved_but_handled"
            checked += 1
    assert checked or not any(k.startswith("hle:unresolved:") for keys in runs.values() for k in keys)

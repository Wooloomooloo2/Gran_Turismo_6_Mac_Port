# SPDX-License-Identifier: GPL-2.0-or-later
"""snapshot/diff tell exactly which files a run added, removed or changed."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "eboot_effects.py"

_spec = importlib.util.spec_from_file_location("eboot_effects", SCRIPT)
eboot_effects = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eboot_effects)


def test_snapshot_and_diff(tmp_path):
    root = tmp_path / "game"
    (root / "USRDIR" / "TPPS-01.07").mkdir(parents=True)
    (root / "USRDIR" / "TPPS-01.07" / "update.txt").write_text("01.06 01.07")
    (root / "USRDIR" / "gone.bin").write_bytes(b"x")
    (root / "USRDIR" / "same.bin").write_bytes(b"same")

    before = eboot_effects.snapshot(root)
    assert before["USRDIR/same.bin"] == hashlib.sha256(b"same").hexdigest()
    assert "USRDIR/" in before and "USRDIR/TPPS-01.07/" in before

    (root / "USRDIR" / "TPPS-01.07" / "update.txt").write_text("99.98 99.99")
    (root / "USRDIR" / "gone.bin").unlink()
    (root / "USRDIR" / "NEW").mkdir()
    (root / "USRDIR" / "NEW" / "UPDATENODEINFO.upd").write_bytes(b"n")
    after = eboot_effects.snapshot(root)

    d = eboot_effects.diff(before, after)
    assert d == {
        "added": ["USRDIR/NEW/", "USRDIR/NEW/UPDATENODEINFO.upd"],
        "removed": ["USRDIR/gone.bin"],
        "changed": ["USRDIR/TPPS-01.07/update.txt"],
    }
    assert eboot_effects.diff(after, after) == {"added": [], "removed": [], "changed": []}


def test_cli_round_trip(tmp_path):
    root = tmp_path / "game"
    root.mkdir()
    (root / "a").write_text("1")
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    py = sys.executable
    subprocess.run([py, str(SCRIPT), "snapshot", str(root), "-o", str(a)], check=True)
    (root / "a").write_text("2")
    subprocess.run([py, str(SCRIPT), "snapshot", str(root), "-o", str(b)], check=True)
    assert json.loads(a.read_text())["a"] == hashlib.sha256(b"1").hexdigest()
    out = subprocess.run([py, str(SCRIPT), "diff", str(a), str(b)], check=True,
                         capture_output=True, text=True).stdout
    assert json.loads(out) == {"added": [], "removed": [], "changed": ["a"]}

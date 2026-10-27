#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run the native gt6 binary unattended and record how far it got (dev-only).

Usage:
    .venv/bin/python scripts/boot_game.py <tree> [--gt6 PATH] [--seconds N] [--idle N] [--window]

<tree> is the player's game folder ($GT6_TREE). It needs the play folder from
prepare_play.py and the decrypted EMAIN.SELF.elf. The binary defaults to
<tree>/port-build/port/gt6 and is run as `gt6 <EMAIN.SELF.elf>`; the port sets the guest
argv and the file roots itself, so only the log, headless and frame-dump variables are set here.

Each run writes <tree>/runs/<UTC yyyymmdd-HHMMSS>/ with stdout.log, stderr.log,
milestones.log, frames/, report.json and summary.md. Nothing is written inside a git work
tree. The run stops when:
- the first guest flip (milestone key gcm:flip) appeared 5 s ago: outcome first_frame;
- the process exits on its own (exited, or crashed if a signal ended it);
- stdout, stderr and the milestone log all stopped growing for --idle seconds: hung
  (ps3recomp logs only the first occurrence of each key, so growth of any of the three counts);
- --seconds elapsed: timeout.
The whole process group is killed on every way out, and the harness waits for it. Windows
stay hidden (PS3RECOMP_METAL_HEADLESS=1) unless --window is given.
The frame dump is one file the renderer overwrites every 120th frame, so frames/ holds the
latest dump (frame.ppm).
Exit status: 0 on first_frame, otherwise 1.
"""
import argparse
import datetime
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import map_game  # noqa: E402
from translate_game import in_git_work_tree  # noqa: E402

ELF_REL = Path("decrypted") / map_game.TITLE_USRDIR / "EMAIN.SELF.elf"
GT6_REL = Path("port-build") / "port" / "gt6"
OUTCOMES = ("first_frame", "exited", "crashed", "hung", "timeout")
FLIP_KEY = "gcm:flip"
FLIP_GRACE = 5.0        # seconds to keep running after the first flip so frames get dumped
POLL = 0.2
# ps3recomp prints both "[hle] UNRESOLVED NID 0x... -> faking" and the dispatcher's
# "[hle] unresolved NID 0x..." (stderr, first 40 only); the milestone log has every one.
UNRESOLVED_RE = re.compile(r"\[hle\] unresolved NID (0x[0-9A-Fa-f]+)", re.IGNORECASE)
UNRESOLVED_KEY = "hle:unresolved:"
INTERP_KEY = "spu:interp:"     # an SPU image run in the interpreter (D9, D33): key per image
SYSCALL_RE = re.compile(r"lv2_syscall (\d+) \(stub\)")


def parse_milestones(text):
    """Read a ps3recomp milestone log (v1). A last line without a newline may be half
    written and is ignored."""
    keys, kv, counts, ended = [], {}, {}, False
    lines = text.split("\n")
    lines.pop()                     # text after the final newline: empty, or a partial line
    for line in lines:
        if line == "# end":
            ended = True
        elif line.startswith("count\t"):
            parts = line.split("\t")
            if len(parts) == 3:
                counts[parts[1]] = parts[2]   # the runtime writes a number or a range
        elif line.startswith("#"):
            continue
        elif line.startswith("kv\t"):
            parts = line.split("\t")
            if len(parts) == 3 and re.fullmatch(r"-?\d+", parts[2]):
                kv[parts[1]] = int(parts[2])
        elif "\t" in line:
            keys.append(line.split("\t", 1)[1])
    return {"keys": keys, "kv": kv, "counts": counts, "ended": ended}


def classify(returncode, timed_out, hung, keys):
    """One of OUTCOMES. returncode is None when the harness killed the process."""
    if returncode is not None and (returncode < 0 or returncode > 128):
        return "crashed"
    if FLIP_KEY in keys:
        return "first_frame"
    if hung:
        return "hung"
    if timed_out:
        return "timeout"
    return "exited"


def build_env(tree, run, headless, env):
    e = dict(os.environ)
    e["PS3_MILESTONE_OUT"] = str(run / "milestones.log")
    e["PS3RECOMP_METAL_FRAME_DUMP"] = str(run / "frames" / "frame.ppm")
    if headless:
        e["PS3RECOMP_METAL_HEADLESS"] = "1"
    e.update(env or {})
    return e


def _kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def _read(path):
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def _sizes(run):
    out = []
    for n in ("milestones.log", "stdout.log", "stderr.log"):
        try:
            out.append((run / n).stat().st_size)
        except OSError:
            out.append(0)
    return tuple(out)


def _sample(pid, path):
    try:
        p = subprocess.run(["/usr/bin/sample", str(pid), "3", "-file", str(path)],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return f"sample failed: {e}"
    text = _read(path)
    if text.strip():
        return text
    return f"sample produced no output (exit {p.returncode}): {(p.stderr or p.stdout).strip()}"


def _summary(rep, tree):
    said = {
        "first_frame": "The game reached its first frame.",
        "exited": "The game ended by itself before drawing a frame.",
        "crashed": "The game crashed before drawing a frame.",
        "hung": "The game stopped making progress and was stopped.",
        "timeout": "The game was still running without a frame when time ran out and was stopped.",
    }[rep["outcome"]]
    if rep["outcome"] == "crashed" and FLIP_KEY in rep["last_keys"]:
        said = "The game crashed after reaching its first frame."
    lines = [said, "",
             f"- Ran for {rep['seconds']} s, exit code {rep['returncode']}, "
             f"{rep['frames']} frame dump(s)",
             f"- Last milestones: {', '.join(rep['last_keys'][-5:]) or 'none'}",
             f"- Unresolved imports: {len(rep['unresolved_nids'])}; "
             f"unimplemented system calls: {len(rep['unimplemented_syscalls'])}",
             f"- SPU images run in the interpreter (lift them: translate_game.py): "
             f"{len(rep['spu_interpreted'])}",
             f"- Run folder: {rep['run']}"]
    if rep["backtraces"]:
        lines += ["", "Where it was stuck (first lines):", "", "```"]
        lines += rep["backtraces"].splitlines()[:40] + ["```"]
    return "\n".join(lines) + "\n"


def boot(gt6, tree, seconds=300, idle=60, headless=True, env=None):
    gt6 = Path(gt6).expanduser().resolve()
    tree = Path(tree).expanduser().resolve()
    if in_git_work_tree(tree):
        raise SystemExit(f"error: {tree} is inside a git work tree; run logs and frame dumps "
                         f"are derived from the game and must live outside it")
    if not (tree / "play" / "prepare.json").is_file():
        raise SystemExit(f"error: {tree}/play/prepare.json is missing: "
                         f"run scripts/prepare_play.py first")
    elf = tree / ELF_REL
    if not elf.is_file():
        raise SystemExit(f"error: ELF not found: {elf}")
    if not gt6.is_file():
        raise SystemExit(f"error: gt6 binary not found: {gt6}")
    run = tree / "runs" / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    run.mkdir(parents=True, exist_ok=False)
    (run / "frames").mkdir()
    child_env = build_env(tree, run, headless, env)
    start = time.monotonic()
    timed_out = hung = False
    backtraces = ""
    returncode = None
    with open(run / "stdout.log", "wb") as so, open(run / "stderr.log", "wb") as se:
        proc = subprocess.Popen([str(gt6), str(elf)], stdout=so, stderr=se, env=child_env,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            last_sizes, last_growth, flip_at = _sizes(run), start, None
            while True:
                time.sleep(POLL)
                now = time.monotonic()
                if proc.poll() is not None:
                    returncode = proc.returncode
                    break
                sizes = _sizes(run)
                if sizes != last_sizes:
                    last_sizes, last_growth = sizes, now
                    if flip_at is None and FLIP_KEY in parse_milestones(
                            _read(run / "milestones.log"))["keys"]:
                        flip_at = now
                if flip_at is not None and now - flip_at >= FLIP_GRACE:
                    break
                if now - start >= seconds:
                    timed_out = True
                    break
                if flip_at is None and now - last_growth >= idle:
                    hung = True
                    backtraces = _sample(proc.pid, run / "sample.txt")
                    break
        finally:
            _kill_group(proc)
    elapsed = round(time.monotonic() - start, 1)
    ms = parse_milestones(_read(run / "milestones.log"))
    keys = ms["keys"]
    err = _read(run / "stderr.log") + _read(run / "stdout.log")
    rep = {
        "outcome": classify(returncode, timed_out, hung, keys),
        "seconds": elapsed,
        "returncode": returncode,
        "last_keys": keys[-20:],
        "unresolved_nids": _unresolved(err, keys),
        "unimplemented_syscalls": sorted({int(n) for n in SYSCALL_RE.findall(err)}),
        "spu_interpreted": {k[len(INTERP_KEY):]: ms["counts"].get(k, "1")
                            for k in keys if k.startswith(INTERP_KEY)},
        "frames": sum(1 for f in (run / "frames").iterdir() if f.is_file()),
        "backtraces": backtraces,
        "pid": proc.pid,
        "run": str(run),
    }
    (run / "report.json").write_text(json.dumps(rep, indent=2) + "\n")
    (run / "summary.md").write_text(_summary(rep, tree))
    return rep


def _unresolved(err, keys):
    """Distinct unresolved import NIDs, first seen first, as 0x%08X."""
    found = UNRESOLVED_RE.findall(err) + [k[len(UNRESOLVED_KEY):] for k in keys
                                          if k.startswith(UNRESOLVED_KEY)]
    return list(dict.fromkeys(f"0x{int(n, 16):08X}" for n in found))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run gt6 unattended and report how far it got.")
    ap.add_argument("tree", help="the player's game folder ($GT6_TREE)")
    ap.add_argument("--gt6", help="binary (default: <tree>/port-build/port/gt6)")
    ap.add_argument("--seconds", type=int, default=300)
    ap.add_argument("--idle", type=int, default=60)
    ap.add_argument("--window", action="store_true", help="show the game window")
    args = ap.parse_args(argv)
    tree = Path(args.tree).expanduser()
    gt6 = Path(args.gt6) if args.gt6 else tree / GT6_REL
    rep = boot(gt6, tree, args.seconds, args.idle, headless=not args.window)
    print((Path(rep["run"]) / "summary.md").read_text(), end="")
    return 0 if rep["outcome"] == "first_frame" else 1


if __name__ == "__main__":
    sys.exit(main())

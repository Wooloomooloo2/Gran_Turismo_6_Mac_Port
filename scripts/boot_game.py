#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run the native gt6 binary unattended and record how far it got (dev-only).

Usage:
    .venv/bin/python scripts/boot_game.py <tree> [--gt6 PATH] [--seconds N] [--idle N] [--window]
        [--until {flip,time}] [--frame-every N] [--frame-max N] [--png] [--prune]

<tree> is the player's game folder ($GT6_TREE). It needs the play folder from
prepare_play.py and the decrypted EMAIN.SELF.elf. The binary defaults to
<tree>/port-build/port/gt6 and is run as `gt6 <EMAIN.SELF.elf>`; the port sets the guest
argv and the file roots itself, so only the log, headless and frame-dump variables are set here.

Each run writes <tree>/runs/<UTC yyyymmdd-HHMMSS>/ with stdout.log, stderr.log,
milestones.log, draw_stats.txt, frames/, report.json and summary.md. Nothing is written
inside a git work tree. The run stops when:
- with --until flip (the default), the first guest flip (milestone key gcm:flip) appeared
  5 s ago: outcome first_frame if at least one frame was dumped, otherwise flip_no_frame;
  with --until time a flip does not stop the run, and a run that reaches --seconds without
  crashing is timeout, its frames kept;
- the process exits on its own (exited, or crashed if a signal ended it);
- stdout, stderr and the milestone log all stopped growing for --idle seconds: hung
  (ps3recomp logs only the first occurrence of each key, so growth of any of the three counts);
- --seconds elapsed: timeout.
The whole process group is killed on every way out, and the harness waits for it. Windows
stay hidden (PS3RECOMP_METAL_HEADLESS=1) unless --window is given.
Frames (patch 0010, D35): the renderer dumps presented frame 1 and every --frame-every-th
after it (default 60) as frames/frame_<presented>.ppm, at most --frame-max (default 300),
and writes one "<presented> <draw calls> <clears>" line per present to draw_stats.txt. The
harness stops the dumps (a STOP file in frames/, which the renderer checks before each
dump) once frames/ holds more than 2 GB or the disk has less than 20 GB free, and records
why in report.json "dump_stopped". report.json "frames_list" gives each dump's draw calls,
clears and share of non-black pixels; a frame is "drawn" when it had at least one draw call
and more than 1% non-black pixels. --png converts the dumps to frames_png/*.png with sips;
--prune then deletes all but the newest 10 runs.
A process that exits by itself after a flip with no frame dumped is flip_no_frame too.
The run is recorded in <tree>/play/prepare.json as "booted": <run>. A play folder an earlier
run used is not clean (the game's first run changes it): the boot still runs, but warns,
names the earlier run in report.json ("play_reused") and summary.md, and points at
`prepare_play.py --force`.
Exit status: 0 on first_frame (with --until time also on a timeout after a flip with at
least one frame kept), otherwise 1.
"""
import argparse
import datetime
import json
import os
import re
import shutil
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
OUTCOMES = ("first_frame", "flip_no_frame", "exited", "crashed", "hung", "timeout")
FLIP_KEY = "gcm:flip"
FLIP_GRACE = 5.0        # seconds to keep running after the first flip so frames get dumped
POLL = 0.2
# ps3recomp prints both "[hle] UNRESOLVED NID 0x... -> faking" and the dispatcher's
# "[hle] unresolved NID 0x..." (stderr, first 40 only); the milestone log has every one.
UNRESOLVED_RE = re.compile(r"\[hle\] unresolved NID (0x[0-9A-Fa-f]+)", re.IGNORECASE)
UNRESOLVED_KEY = "hle:unresolved:"
INTERP_KEY = "spu:interp:"     # an SPU image run in the interpreter (D9, D33): key per image
SYSCALL_RE = re.compile(r"lv2_syscall (\d+) \(stub\)")
UNTIL = ("flip", "time")
FRAME_RE = re.compile(r"frame_(\d{6,})\.ppm")
RUN_RE = re.compile(r"\d{8}-\d{6}")           # a run folder; anything else in runs/ is kept
STATS_NAME = "draw_stats.txt"
STOP_NAME = "STOP"           # in frames/: the renderer stops dumping when it appears (D35)
FRAME_BYTES = 2 * 1024**3    # default cap on frames/ per run
FREE_FLOOR = 20 * 1024**3    # stop dumping below this much free disk space
DRAWN_SHARE = 0.01           # a drawn frame has more than this share of non-black pixels
PRUNE_KEEP = 10


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


def classify(returncode, timed_out, hung, keys, frames, until="flip"):
    """One of OUTCOMES. returncode is None when the harness killed the process. A first
    frame needs both the flip key and at least one dumped frame. With until="time" a run
    that reached its time limit is timeout whatever it showed (its frames are kept)."""
    if returncode is not None and (returncode < 0 or returncode > 128):
        return "crashed"
    if until == "time" and timed_out:
        return "timeout"
    if FLIP_KEY in keys:
        return "first_frame" if frames >= 1 else "flip_no_frame"
    if hung:
        return "hung"
    if timed_out:
        return "timeout"
    return "exited"


def build_env(tree, run, headless, env, frame_every=60, frame_max=300):
    e = dict(os.environ)
    e["PS3_MILESTONE_OUT"] = str(run / "milestones.log")
    # The numbered series (patch 0010) replaces milestone 2's single overwritten dump.
    e.pop("PS3RECOMP_METAL_FRAME_DUMP", None)
    e["PS3RECOMP_METAL_FRAME_DIR"] = str(run / "frames")
    e["PS3RECOMP_METAL_FRAME_EVERY"] = str(frame_every)
    e["PS3RECOMP_METAL_FRAME_MAX"] = str(frame_max)
    e["PS3RECOMP_DRAW_STATS"] = str(run / STATS_NAME)
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


def parse_draw_stats(text):
    """{presented: (draws, clears)} from a PS3RECOMP_DRAW_STATS file. A last line without a
    newline may be half written and is ignored, as are lines that are not three numbers."""
    out = {}
    lines = text.split("\n")
    lines.pop()
    for line in lines:
        parts = line.split()
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            out[int(parts[0])] = (int(parts[1]), int(parts[2]))
    return out


def nonzero_share(data):
    """Share of pixels in a binary PPM (P6, 8-bit) with any non-zero channel, or None if it
    is not one or is cut short."""
    m = re.match(rb"P6(?:\s+|#[^\n]*\n)+(\d+)(?:\s+|#[^\n]*\n)+(\d+)"
                 rb"(?:\s+|#[^\n]*\n)+(\d+)\s", data)
    if not m or int(m.group(3)) != 255:
        return None
    n = int(m.group(1)) * int(m.group(2))
    px = data[m.end():m.end() + 3 * n]
    if n == 0 or len(px) != 3 * n:
        return None
    # Big integers OR the three channels bytewise; a zero byte left is a black pixel.
    ored = (int.from_bytes(px[0::3], "big") | int.from_bytes(px[1::3], "big")
            | int.from_bytes(px[2::3], "big")).to_bytes(n, "big")
    return round(1 - ored.count(0) / n, 6)


def frame_files(frames_dir):
    """The dumped frames in presented order, as (presented, path)."""
    try:
        found = [(int(m.group(1)), p) for p in Path(frames_dir).iterdir()
                 if (m := FRAME_RE.fullmatch(p.name)) and p.is_file()]
    except OSError:
        return []
    return sorted(found)


def frames_report(run):
    """report.json's frames_list, drawn_frames and first_drawn for a finished run."""
    stats = parse_draw_stats(_read(run / STATS_NAME))
    rows = []
    for presented, path in frame_files(run / "frames"):
        try:
            share = nonzero_share(path.read_bytes())
        except OSError:
            share = None
        draws, clears = stats.get(presented, (None, None))
        rows.append({"file": path.name, "presented": presented, "draws": draws,
                     "clears": clears, "nonzero_share": share})
    drawn = [r["presented"] for r in rows
             if (r["draws"] or 0) > 0 and (r["nonzero_share"] or 0) > DRAWN_SHARE]
    return rows, len(drawn), (drawn[0] if drawn else None)


def _frames_bytes(frames_dir):
    total = 0
    try:
        with os.scandir(frames_dir) as it:
            for e in it:
                try:
                    if e.is_file(follow_symlinks=False):
                        total += e.stat(follow_symlinks=False).st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _dump_check(frames_dir, frame_bytes):
    """Why the frame dumps must stop now ("bytes" or "disk"), or None."""
    try:
        if shutil.disk_usage(frames_dir).free < FREE_FLOOR:
            return "disk"
    except OSError:
        pass
    if _frames_bytes(frames_dir) > frame_bytes:
        return "bytes"
    return None


def _stop_dumps(frames_dir, reason):
    (Path(frames_dir) / STOP_NAME).write_text(reason + "\n")
    print(f"note: frame dumps stopped ({reason}: "
          + ("frames/ passed its size cap" if reason == "bytes"
             else f"less than {FREE_FLOOR // 1024**3} GB of free disk space") + ")",
          file=sys.stderr)


def to_png(run):
    """Convert run/frames/*.ppm to run/frames_png/*.png with sips; returns how many."""
    out = Path(run) / "frames_png"
    out.mkdir(exist_ok=True)
    n = 0
    for _, ppm in frame_files(Path(run) / "frames"):
        png = out / (ppm.stem + ".png")
        r = subprocess.run(["sips", "-s", "format", "png", str(ppm), "--out", str(png)],
                           capture_output=True, text=True)
        if r.returncode == 0 and png.is_file():
            n += 1
        else:
            print(f"warning: sips could not convert {ppm.name}: {r.stderr.strip()}",
                  file=sys.stderr)
    return n


def prune_runs(runs, keep=PRUNE_KEEP):
    """Delete all but the newest `keep` run folders (<UTC yyyymmdd-HHMMSS>) in runs/.
    Anything else there, and symlinks, is left alone. Returns the folders removed."""
    try:
        found = sorted(p for p in Path(runs).iterdir()
                       if RUN_RE.fullmatch(p.name) and p.is_dir() and not p.is_symlink())
    except OSError:
        return []
    old = found[:-keep] if keep > 0 else found
    for p in old:
        shutil.rmtree(p)
    return old


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
        "flip_no_frame": "The game presented a frame (a guest flip), but no frame was dumped.",
        "exited": "The game ended by itself before drawing a frame.",
        "crashed": "The game crashed before drawing a frame.",
        "hung": "The game stopped making progress and was stopped.",
        "timeout": "The game was still running without a frame when time ran out and was stopped.",
    }[rep["outcome"]]
    if rep["outcome"] == "crashed" and FLIP_KEY in rep["last_keys"]:
        said = "The game crashed after reaching its first frame."
    if rep["outcome"] == "timeout" and rep["flipped"]:
        said = "The game was still running, presenting frames, when time ran out, and was stopped."
    if rep["first_drawn"] is not None:
        drawn = (f"{rep['drawn_frames']} of them drawn (the first at present "
                 f"{rep['first_drawn']})")
    else:
        drawn = "none of them drawn (a draw call and more than 1% non-black pixels)"
    lines = [said, "",
             f"- Ran for {rep['seconds']} s, exit code {rep['returncode']}, "
             f"{rep['frames']} frame dump(s), {drawn}",
             f"- Last milestones: {', '.join(rep['last_keys'][-5:]) or 'none'}",
             f"- Unresolved imports: {len(rep['unresolved_nids'])}; "
             f"unimplemented system calls: {len(rep['unimplemented_syscalls'])}",
             f"- SPU images run in the interpreter (lift them: translate_game.py): "
             f"{len(rep['spu_interpreted'])}",
             f"- Run folder: {rep['run']}"]
    if rep.get("dump_stopped"):
        lines.append(f"- Frame dumps stopped before the end ({rep['dump_stopped']}: "
                     + {"bytes": "frames/ reached its size cap",
                        "disk": "free disk space fell below the 20 GB floor",
                        "max": "the --frame-max cap was reached"}[rep["dump_stopped"]] + ")")
    if rep.get("play_reused"):
        lines.append(f"- Warning: the play folder was already used by run {rep['play_reused']}; "
                     f"run scripts/prepare_play.py --force for a clean one")
    if rep["backtraces"]:
        lines += ["", "Where it was stuck (first lines):", "", "```"]
        lines += rep["backtraces"].splitlines()[:40] + ["```"]
    return "\n".join(lines) + "\n"


def boot(gt6, tree, seconds=300, idle=60, headless=True, env=None, until="flip",
         frame_every=60, frame_max=300, frame_bytes=FRAME_BYTES):
    if until not in UNTIL:
        raise ValueError(f"until must be one of {UNTIL}, not {until!r}")
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
    reused = _mark_booted(tree / "play" / "prepare.json", None)
    run = _new_run(tree / "runs")
    _mark_booted(tree / "play" / "prepare.json", run.name)
    if reused:
        print(f"warning: {tree}/play was already used by run {reused}; the game's first run "
              f"changes it. For a clean boot run: scripts/prepare_play.py \"{tree}\" --force",
              file=sys.stderr)
    frames_dir = run / "frames"
    frames_dir.mkdir()
    child_env = build_env(tree, run, headless, env, frame_every, frame_max)
    dump_stopped = _dump_check(frames_dir, frame_bytes)
    if dump_stopped:
        _stop_dumps(frames_dir, dump_stopped)
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
                if dump_stopped is None:
                    dump_stopped = _dump_check(frames_dir, frame_bytes)
                    if dump_stopped:
                        _stop_dumps(frames_dir, dump_stopped)
                if until == "flip" and flip_at is not None and now - flip_at >= FLIP_GRACE:
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
    frames_list, drawn, first_drawn = frames_report(run)
    frames = len(frames_list)
    if dump_stopped is None and frame_max >= 0 and frames >= frame_max:
        dump_stopped = "max"
    rep = {
        "outcome": classify(returncode, timed_out, hung, keys, frames, until),
        "until": until,
        "seconds": elapsed,
        "returncode": returncode,
        "last_keys": keys[-20:],
        "unresolved_nids": _unresolved(err, keys),
        "unimplemented_syscalls": sorted({int(n) for n in SYSCALL_RE.findall(err)}),
        "spu_interpreted": {k[len(INTERP_KEY):]: ms["counts"].get(k, "1")
                            for k in keys if k.startswith(INTERP_KEY)},
        "flipped": FLIP_KEY in keys,
        "frames": frames,
        "frames_list": frames_list,
        "drawn_frames": drawn,
        "first_drawn": first_drawn,
        "dump_stopped": dump_stopped,
        "play_reused": reused,
        "backtraces": backtraces,
        "pid": proc.pid,
        "run": str(run),
    }
    (run / "report.json").write_text(json.dumps(rep, indent=2) + "\n")
    (run / "summary.md").write_text(_summary(rep, tree))
    return rep


def _new_run(runs):
    """A new <runs>/<UTC yyyymmdd-HHMMSS> folder (waits for the next second if taken)."""
    runs.mkdir(parents=True, exist_ok=True)
    while True:
        run = runs / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
        try:
            run.mkdir()
            return run
        except FileExistsError:
            time.sleep(0.2)


def _mark_booted(prepare_json, run_name):
    """With run_name None, return the run an earlier boot recorded in prepare.json (or None);
    otherwise record run_name there as "booted". An unreadable prepare.json is left alone."""
    try:
        rec = json.loads(Path(prepare_json).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict):
        return None
    if run_name is None:
        return rec.get("booted")
    rec["booted"] = run_name
    tmp = Path(prepare_json).with_name(".prepare.json.tmp")
    tmp.write_text(json.dumps(rec, indent=1) + "\n")
    tmp.rename(prepare_json)
    return run_name


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
    ap.add_argument("--until", choices=UNTIL, default="flip",
                    help="flip: stop 5 s after the first flip (default); time: run to --seconds")
    ap.add_argument("--frame-every", type=int, default=60, metavar="N",
                    help="dump presented frame 1 and every N-th after it (default 60)")
    ap.add_argument("--frame-max", type=int, default=300, metavar="N",
                    help="dump at most N frames (default 300)")
    ap.add_argument("--png", action="store_true",
                    help="convert the dumped frames to frames_png/*.png (sips) for viewing")
    ap.add_argument("--prune", action="store_true",
                    help=f"after the run, delete all but the newest {PRUNE_KEEP} runs")
    args = ap.parse_args(argv)
    if args.frame_every < 1 or args.frame_max < 0:
        ap.error("--frame-every must be at least 1 and --frame-max at least 0")
    tree = Path(args.tree).expanduser()
    gt6 = Path(args.gt6) if args.gt6 else tree / GT6_REL
    rep = boot(gt6, tree, args.seconds, args.idle, headless=not args.window, until=args.until,
               frame_every=args.frame_every, frame_max=args.frame_max)
    run = Path(rep["run"])
    if args.png:
        rep["frames_png"] = to_png(run)
        (run / "report.json").write_text(json.dumps(rep, indent=2) + "\n")
        with open(run / "summary.md", "a") as f:
            f.write(f"- PNG copies of the frames: {rep['frames_png']} in {run / 'frames_png'}\n")
    print((run / "summary.md").read_text(), end="")
    if args.prune:
        for p in prune_runs(tree.resolve() / "runs"):
            print(f"pruned {p}")
    ok = rep["outcome"] == "first_frame" or (
        args.until == "time" and rep["outcome"] == "timeout" and rep["flipped"]
        and rep["frames"] >= 1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

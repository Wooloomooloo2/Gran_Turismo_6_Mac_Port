#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run the native gt6 binary unattended and record how far it got (dev-only).

Usage:
    .venv/bin/python scripts/boot_game.py <tree> [--gt6 PATH] [--seconds N] [--idle N] [--window]
        [--until {flip,time}] [--frame-every N] [--frame-max N] [--png] [--prune]
        [--press [IMAGE@]SECONDS:BUTTON ...]

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
  crashing is timeout, its frames kept (one that ends by itself first is exited);
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
When the game exit-spawns itself (D41) the port re-executes in the same process, so the run
goes on; the new image's milestone log, frames and draw statistics go to
milestones.log.spawn<n>, frames/spawn<n>/ and draw_stats.txt.spawn<n>, and report.json
"spawns" (and summary.md) describe each image after the first.
--press [N@]S:BUTTON (repeatable; D40) presses a pad button S seconds after image N (default 1,
the first; 2 is the first exit-spawned image, D41) first polls the pad, through ps3recomp's
PAD_SCRIPT (cellPad: held for 40 polls, about 0.4 s at GT6's rate). Each image gets only its
own presses: the port hands image N the script in GT6_PAD_SCRIPT_IMAGE<N> and clears
PAD_SCRIPT when there is none. BUTTON is a CELL_PAD_CTRL_* name: cross, circle, triangle,
square, start, select, up, down, left, right, l1, l2, l3, r1, r2, r3. report.json records
them in "presses".
Host controllers (a pad paired with the Mac) are ignored unless --host-pad is given (D65):
cellPad is told PAD_NO_HOST=1, so only --press drives the game's pad.
The run is recorded in <tree>/play/prepare.json as "booted": <run>. A play folder an earlier
run used is not clean (the game's first run changes it): the boot still runs, but warns,
names the earlier run in report.json ("play_reused") and summary.md, and points at
`prepare_play.py --force`.
Exit status: 0 on first_frame (with --until time also on a timeout after a flip with at
least one frame kept), otherwise 1.
"""
import argparse
import hashlib
import datetime
import json
import math
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
SPAWN_RE = re.compile(r"spawn[1-9][0-9]*")   # frames/spawn<n>/: image n+1 after an exit-spawn
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
    that reached its time limit is timeout whatever it showed (its frames are kept), and one
    that ended by itself before that is exited: the run was meant to last."""
    if returncode is not None and (returncode < 0 or returncode > 128):
        return "crashed"
    if until == "time":
        if timed_out:
            return "timeout"
        if returncode is not None:
            return "exited"
    if FLIP_KEY in keys:
        return "first_frame" if frames >= 1 else "flip_no_frame"
    if hung:
        return "hung"
    if timed_out:
        return "timeout"
    return "exited"


# CELL_PAD_CTRL_* as ps3recomp's PAD_SCRIPT packs them: (DIGITAL2 << 8) | DIGITAL1.
PAD_BUTTONS = {
    "select": 0x0001, "l3": 0x0002, "r3": 0x0004, "start": 0x0008,
    "up": 0x0010, "right": 0x0020, "down": 0x0040, "left": 0x0080,
    "l2": 0x0100, "r2": 0x0200, "l1": 0x0400, "r1": 0x0800,
    "triangle": 0x1000, "circle": 0x2000, "cross": 0x4000, "square": 0x8000,
}


def parse_press(text):
    """'[<image>@]<seconds>:<button>' -> (seconds, button name, image); ValueError if bad.

    The image is 1 (the first) unless given; 2 is the first exit-spawned image (D41)."""
    image, at, rest = text.partition("@")
    if not at:
        image, rest = "1", text
    if not image.strip().isdigit() or int(image) < 1:
        raise ValueError(f"--press image must be 1 or more, not {image!r}")
    sec, sep, name = rest.partition(":")
    name = name.strip().lower()
    if not sep or name not in PAD_BUTTONS:
        raise ValueError(f"--press wants [IMAGE@]SECONDS:BUTTON with BUTTON one of "
                         f"{', '.join(sorted(PAD_BUTTONS))}, not {text!r}")
    t = float(sec)
    if not (math.isfinite(t) and t >= 0):
        raise ValueError(f"--press time must be a finite 0 or more seconds, not {sec!r}")
    return t, name, int(image)


def pad_script(presses):
    """ps3recomp's PAD_SCRIPT value for [(seconds, button), ...], in time order."""
    return ",".join(f"{t:g}:0x{PAD_BUTTONS[b]:04X}" for t, b in sorted(presses))


def press_env(presses):
    """The environment for [(seconds, button, image), ...]: PAD_SCRIPT for image 1 and
    GT6_PAD_SCRIPT_IMAGE<n> for each later image with presses (the port moves it into
    PAD_SCRIPT when it re-executes as image n, and clears PAD_SCRIPT otherwise)."""
    env = {}
    for image in sorted({i for _, _, i in presses}):
        script = pad_script([(t, b) for t, b, i in presses if i == image])
        env["PAD_SCRIPT" if image == 1 else f"GT6_PAD_SCRIPT_IMAGE{image}"] = script
    return env


IMAGE_NAME = "gt6.image"   # written by port/CMakeLists.txt beside each binary (D44)
# The port's lines when the play folder's EMAIN.SELF has no build, or only a stale one (D47).
NO_BUILD_RE = re.compile(r"\[image\] no-matching-build sha256=([0-9a-f]{64})")
STALE_RE = re.compile(r"\[image\] stale-build (\S+)")


from prepare_play import disc_layer_writable, play_folder   # noqa: E402  (D46, D49)


def image_info(gt6):
    """The gt6.image beside a port binary ({self, self_sha256, elf}), or None."""
    try:
        return json.loads((Path(gt6).parent / IMAGE_NAME).read_text())
    except (OSError, ValueError):
        return None


REPO = Path(__file__).resolve().parents[1]
PATCHES = REPO / "patches" / "ps3recomp"
PS3RECOMP = REPO / "third_party" / "ps3recomp"


def current_patch_set():
    """(ps3recomp commit, patch-set SHA-256) of this checkout, as translate_game.py and
    port/CMakeLists.txt compute them (D28)."""
    from translate_game import patches_hash
    try:
        commit = subprocess.run(["git", "-C", str(PS3RECOMP), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return commit, patches_hash(PATCHES)


def ps3recomp_tree_hash(sub=None):
    """SHA-256 of the ps3recomp submodule's working tree as port/write_image.cmake records it
    in gt6.image ("ps3recomp_tree"): `git diff --no-ext-diff --no-textconv HEAD --binary` (no
    user diff driver can change it, review M-2), then "<path>\n<sha256>\n" for
    each untracked file git lists (--exclude-standard; __pycache__ and .pyc left out). It
    changes with any edit, inside the patch series or not (D47). None without git."""
    sub = Path(sub or PS3RECOMP)
    try:
        diff = subprocess.run(["git", "-C", str(sub), "diff", "--no-ext-diff", "--no-textconv",
                               "HEAD", "--binary"],
                              capture_output=True, check=True).stdout
        others = subprocess.run(["git", "-C", str(sub), "ls-files", "--others",
                                 "--exclude-standard"], capture_output=True, check=True,
                                text=True).stdout.split("\n")
    except (OSError, subprocess.CalledProcessError):
        return None
    # CMake's execute_process drops carriage returns from what it captures, so
    # write_image.cmake hashes the diff without them; so does this (CRLF files exist).
    state = bytearray(diff.replace(b"\r", b""))
    for f in others:
        if not f or "/__pycache__/" in "/" + f or f.endswith(".pyc"):
            continue
        h = hashlib.sha256((sub / f).read_bytes()).hexdigest()
        state += f"{f}\n{h}\n".encode()
    return hashlib.sha256(bytes(state)).hexdigest()


IMAGE_FIELDS = ("self_sha256", "elf", "ps3recomp_commit", "ps3recomp_patches", "ps3recomp_tree")


def build_problem(gt6, info, commit, patches, tree_state):
    """Why the build gt6 (its gt6.image info) must not run, or None (D47)."""
    missing = [k for k in IMAGE_FIELDS if not (info or {}).get(k)]
    if tree_state is None and "ps3recomp_tree" in missing:
        missing.remove("ps3recomp_tree")
    if missing:
        return (f"{gt6} has no complete {IMAGE_NAME} (missing {', '.join(missing)}): it was "
                f"built before D47 or its build failed; rebuild it")
    if info.get("ps3recomp_patches") != patches or info.get("ps3recomp_commit") != commit:
        return (f"{gt6} was built from ps3recomp {info.get('ps3recomp_commit')} with patch set "
                f"{info.get('ps3recomp_patches')}; this checkout is {commit} with {patches}")
    if tree_state is not None and info.get("ps3recomp_tree") != tree_state:
        return (f"{gt6} was built from another ps3recomp working tree (tree hash "
                f"{info.get('ps3recomp_tree')}, now {tree_state}): the submodule was edited "
                f"outside the patch series, or this build was not redone after it")
    return None


def check_images(tree, commit=None, patches=None, tree_state=None):
    """Every build under <tree>/port-build*/port: (current, problems).
    current is [(sha, binary, elf)] for the builds made from this checkout's ps3recomp commit,
    patch set and submodule working tree; problems names each build that is not (stale: it
    would silently lack the current fixes, or carry a debug edit the others lack), each binary
    with no complete gt6.image, and each SELF more than one build claims (D47). With commit
    and patches given (tests), the working tree is compared only when tree_state is given."""
    if commit is None and patches is None:
        commit, patches = current_patch_set()
        tree_state = ps3recomp_tree_hash()
    current, problems, seen = [], [], {}
    for gt6 in sorted(Path(tree).glob("port-build*/port/gt6")):
        if not gt6.is_file():
            continue
        info = image_info(gt6)
        problem = build_problem(gt6, info, commit, patches, tree_state)
        if problem:
            problems.append(problem)
            continue
        sha = info["self_sha256"]
        if sha in seen:
            problems.append(f"{gt6} and {seen[sha]} are both builds of the SELF {sha}")
            continue
        seen[sha] = gt6
        current.append((sha, gt6, Path(tree) / info["elf"]))
    return current, problems


def images_env(tree, commit=None, patches=None):
    """GT6_IMAGES for the port (D44): every current build under <tree>/port-build*/port, as
    "<self sha256>=<binary>|<elf>|<patch set>;...", so the port can start the build of whichever
    EMAIN.SELF the play folder holds (the first-run install replaces it). Stale builds are left
    out (boot() refuses to run while there is one)."""
    if commit is None and patches is None:
        commit, patches = current_patch_set()
    current, _ = check_images(tree, commit, patches)
    return ";".join(f"{sha}={gt6}|{elf}|{patches}" for sha, gt6, elf in current)


def build_env(tree, run, headless, env, frame_every=60, frame_max=300, play=None, host_pad=False):
    e = dict(os.environ)
    # D65: an unattended run reads no host controller. A pad paired with this Mac (the
    # owner's DualSense) reaches the game even with its window in the background, so a
    # run's outcome could depend on what someone did with it; only --press drives the pad.
    if not host_pad:
        e["PAD_NO_HOST"] = "1"
    else:
        # A PAD_NO_HOST exported in the shell would otherwise still hide the pad.
        e.pop("PAD_NO_HOST", None)
    images = images_env(tree)
    if images:
        e["GT6_IMAGES"] = images
    # D50: saves (<root>/dev_hdd0/home/00000001/savedata) and trophies (<root>/trophies) go
    # into the play folder, never the folder the harness was started from.
    e["PS3_GAMEDATA_ROOT"] = str(Path(play) if play is not None else Path(tree) / "play")
    if play is not None:
        # D49: run on <tree>/play-<suffix>; both file layers take their roots from here, so
        # the folder whose prepare.json was checked is the one the game writes to.
        e["PS3_HDD0_ROOT"] = str(Path(play) / "dev_hdd0")
        e["PS3_HDD1_ROOT"] = str(Path(play) / "dev_hdd1")
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


def frames_report(run, frames_dir=None, stats_file=None):
    """report.json's frames_list, drawn_frames and first_drawn for a finished run (or, with
    frames_dir and stats_file, for one re-executed image of it)."""
    stats = parse_draw_stats(_read(stats_file or run / STATS_NAME))
    rows = []
    for presented, path in frame_files(frames_dir or run / "frames"):
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


def spawn_dirs(frames_dir):
    """frames/spawn<n>/ folders a re-executed game image dumps into (D41), in order."""
    try:
        found = [p for p in Path(frames_dir).iterdir()
                 if SPAWN_RE.fullmatch(p.name) and p.is_dir() and not p.is_symlink()]
    except OSError:
        return []
    return sorted(found, key=lambda p: int(p.name[5:]))


def _frames_bytes(frames_dir):
    total = 0
    for d in [Path(frames_dir)] + spawn_dirs(frames_dir):
        try:
            with os.scandir(d) as it:
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
    """Ask the renderer to stop dumping. Never raises: a STOP file that cannot be written
    (disk full, frames/ gone) is reported, and the run goes on to write its report."""
    for d in [Path(frames_dir)] + spawn_dirs(frames_dir):
        try:
            (d / STOP_NAME).write_text(reason + "\n")
        except OSError as e:
            print(f"warning: could not write {d / STOP_NAME} ({e}); "
                  f"the renderer may keep dumping", file=sys.stderr)
    print(f"note: frame dumps stopped ({reason}: "
          + ("frames/ passed its size cap" if reason == "bytes"
             else f"less than {FREE_FLOOR // 1024**3} GB of free disk space") + ")",
          file=sys.stderr)


def to_png(run):
    """Convert run/frames/*.ppm to run/frames_png/*.png with sips (frames/spawn<n>/ to
    frames_png/spawn<n>/); returns how many."""
    out = Path(run) / "frames_png"
    out.mkdir(exist_ok=True)
    todo = [(Path(run) / "frames", out)] + [(d, out / d.name)
                                            for d in spawn_dirs(Path(run) / "frames")]
    n = 0
    for src, dst in todo:
        dst.mkdir(exist_ok=True)
        for _, ppm in frame_files(src):
            png = dst / (ppm.stem + ".png")
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
    removed = []
    for p in (found[:-keep] if keep > 0 else found):
        try:
            shutil.rmtree(p)
            removed.append(p)
        except OSError as e:
            print(f"warning: could not delete {p}: {e}", file=sys.stderr)
    return removed


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
             f"- Run folder: {rep['run']}",
             "- Host controllers: " + ("read (--host-pad)" if rep.get("host_pad")
                                       else "ignored (D65)")]
    for sha in rep.get("no_matching_build", []):
        lines.append(f"- **No build for the play folder's EMAIN.SELF** (sha256 {sha[:16]}...): "
                     f"the image ran another executable's translation (D44)")
    for b in rep.get("stale_build", []):
        lines.append(f"- **Refused a stale build**: {b} (another patch set, D47)")
    if rep.get("dump_stopped"):
        lines.append(f"- Frame dumps stopped before the end ({rep['dump_stopped']}: "
                     + {"bytes": "frames/ reached its size cap",
                        "disk": "free disk space fell below the 20 GB floor",
                        "max": "the --frame-max cap was reached"}[rep["dump_stopped"]] + ")")
    for sp in rep.get("spawns", []):
        lines.append(f"- Image {sp['image']} (after an exit-spawn, D41): {sp['frames']} frame "
                     f"dump(s) in frames/spawn{sp['image'] - 1}, {sp['drawn_frames']} drawn; "
                     f"last milestones: {', '.join(sp['last_keys'][-5:]) or 'none'}")
    if rep.get("play_reused"):
        lines.append(f"- Warning: the play folder was already used by run {rep['play_reused']}; "
                     f"run scripts/prepare_play.py --force for a clean one")
    if rep["backtraces"]:
        lines += ["", "Where it was stuck (first lines):", "", "```"]
        lines += rep["backtraces"].splitlines()[:40] + ["```"]
    return "\n".join(lines) + "\n"


def boot(gt6, tree, seconds=300, idle=60, headless=True, env=None, until="flip",
         frame_every=60, frame_max=300, frame_bytes=FRAME_BYTES, play="play", host_pad=False):
    if until not in UNTIL:
        raise ValueError(f"until must be one of {UNTIL}, not {until!r}")
    gt6 = Path(gt6).expanduser().resolve()
    tree = Path(tree).expanduser().resolve()
    if in_git_work_tree(tree):
        raise SystemExit(f"error: {tree} is inside a git work tree; run logs and frame dumps "
                         f"are derived from the game and must live outside it")
    play_dir = play_folder(tree, play)
    if not (play_dir / "prepare.json").is_file():
        raise SystemExit(f"error: {play_dir}/prepare.json is missing: "
                         f"run scripts/prepare_play.py first")
    info = image_info(gt6)
    _, problems = check_images(tree)
    # A --gt6 binary outside <tree>/port-build*/port is checked too (D47): refused when its
    # gt6.image is stale, and run with a loud warning when it has none (a test or debug build).
    unchecked = None
    if gt6.parent.parent.parent != tree or not gt6.parent.parent.name.startswith("port-build"):
        if info is None:
            unchecked = str(gt6)
            print(f"WARNING: {gt6} has no {IMAGE_NAME}, so it cannot be checked against this "
                  f"checkout's ps3recomp patches (D47); it may lack the current fixes",
                  file=sys.stderr)
        else:
            commit, patches = current_patch_set()
            problem = build_problem(gt6, info, commit, patches, ps3recomp_tree_hash())
            if problem:
                problems.append(problem)
    if problems:
        raise SystemExit("error: a port build does not match this checkout's ps3recomp patches, "
                         "so it would run without the current fixes (D47). Re-translate and "
                         "rebuild every image (README steps 2, 4 and 4b):\n  "
                         + "\n  ".join(problems))
    guard = disc_layer_writable(tree)
    if guard:
        raise SystemExit(f"error: {guard} (D46). Make it read-only first: "
                         f"chmod -R a-w \"{tree / 'dev_bdvd'}\"")
    elf = tree / (info["elf"] if info and "elf" in info else ELF_REL)
    if not elf.is_file():
        raise SystemExit(f"error: ELF not found: {elf}")
    if not gt6.is_file():
        raise SystemExit(f"error: gt6 binary not found: {gt6}")
    reused = _mark_booted(play_dir / "prepare.json", None)
    run = _new_run(tree / "runs")
    _mark_booted(play_dir / "prepare.json", run.name)
    if reused:
        print(f"warning: {play_dir} was already used by run {reused}; the game's first run "
              f"changes it. For a clean boot run: scripts/prepare_play.py \"{tree}\" --force"
              + ("" if play == "play" else f" --name {play}"),
              file=sys.stderr)
    frames_dir = run / "frames"
    frames_dir.mkdir()
    child_env = build_env(tree, run, headless, env, frame_every, frame_max,
                          play=None if play == "play" else play_dir, host_pad=host_pad)
    dump_stopped = _dump_check(frames_dir, frame_bytes)
    if dump_stopped:
        _stop_dumps(frames_dir, dump_stopped)
    start = time.monotonic()
    timed_out = hung = False
    backtraces = ""
    returncode = None
    with open(run / "stdout.log", "wb") as so, open(run / "stderr.log", "wb") as se:
        # cwd: anything the runtime still writes relative to its folder lands in the run
        # folder, never the repository (D50).
        proc = subprocess.Popen([str(gt6), str(elf)], stdout=so, stderr=se, env=child_env,
                                stdin=subprocess.DEVNULL, start_new_session=True, cwd=run)
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
                    if flip_at is None and any(
                            FLIP_KEY in parse_milestones(_read(m))["keys"]
                            for m in [run / "milestones.log"]
                            + sorted(run.glob("milestones.log.spawn*"))):
                        flip_at = now   # a flip by any image (D41) counts
                if dump_stopped is None:
                    dump_stopped = _dump_check(frames_dir, frame_bytes)
                    if dump_stopped:
                        _stop_dumps(frames_dir, dump_stopped)
                else:   # an image started since (D41) must stop too
                    for d in spawn_dirs(frames_dir):
                        if not (d / STOP_NAME).exists():
                            _stop_dumps(d, dump_stopped)
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
        "play": str(play_dir),
        "play_reused": reused,
        "unchecked_build": unchecked,
        "host_pad": bool(host_pad),
        "backtraces": backtraces,
        "pid": proc.pid,
        "run": str(run),
    }
    rep["no_matching_build"] = sorted(set(NO_BUILD_RE.findall(err)))
    rep["stale_build"] = sorted(set(STALE_RE.findall(err)))
    rep["spawns"] = []
    for d in spawn_dirs(frames_dir):
        n = d.name[5:]
        sms = parse_milestones(_read(run / f"milestones.log.spawn{n}"))
        flist, sdrawn, sfirst = frames_report(run, d, run / f"{STATS_NAME}.spawn{n}")
        rep["spawns"].append({"image": int(n) + 1, "last_keys": sms["keys"][-20:],
                              "flipped": FLIP_KEY in sms["keys"], "frames": len(flist),
                              "frames_list": flist, "drawn_frames": sdrawn,
                              "first_drawn": sfirst})
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
    ap.add_argument("--play", default="play", metavar="play-SUFFIX",
                    help="run on <tree>/play-SUFFIX (from prepare_play.py --name) instead of "
                         "<tree>/play (D49)")
    ap.add_argument("--host-pad", action="store_true",
                    help="let a controller paired with this Mac reach the game (default: ignored, D65)")
    ap.add_argument("--press", action="append", default=[], metavar="[IMAGE@]SECONDS:BUTTON",
                    help="press a pad button SECONDS after image IMAGE (default 1; 2 is the "
                         "first exit-spawned one) first polls the pad (repeatable), "
                         "e.g. 480:cross or 2@30:cross")
    args = ap.parse_args(argv)
    if args.frame_every < 1 or args.frame_max < 0:
        ap.error("--frame-every must be at least 1 and --frame-max at least 0")
    try:
        presses = [parse_press(p) for p in args.press]
    except ValueError as e:
        ap.error(str(e))
    env = press_env(presses) if presses else None
    tree = Path(args.tree).expanduser()
    gt6 = Path(args.gt6) if args.gt6 else tree / GT6_REL
    rep = boot(gt6, tree, args.seconds, args.idle, headless=not args.window, until=args.until,
               frame_every=args.frame_every, frame_max=args.frame_max, env=env,
               play=args.play, host_pad=args.host_pad)
    run = Path(rep["run"])
    if presses:
        rep["presses"] = [{"image": i, "seconds": t, "button": b}
                          for t, b, i in sorted(presses, key=lambda p: (p[2], p[0]))]
        (run / "report.json").write_text(json.dumps(rep, indent=2) + "\n")
        with open(run / "summary.md", "a") as f:
            f.write("- Pad presses (seconds after that image's first pad poll): "
                    + ", ".join(f"image {i} {t:g} s {b}"
                                for t, b, i in sorted(presses, key=lambda p: (p[2], p[0])))
                    + "\n")
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

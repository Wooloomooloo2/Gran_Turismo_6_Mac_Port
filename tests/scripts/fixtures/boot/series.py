#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""A fake gt6 that flips and keeps presenting, like the frame-series runtime (patch 0010):
one PS3RECOMP_DRAW_STATS line per present, and frame_<n>.ppm dumps in
PS3RECOMP_METAL_FRAME_DIR for present 1 and every FRAME_EVERY-th, at most FRAME_MAX, until a
STOP file appears. FAKE_DRAWS sets the draw count, FAKE_NONZERO makes the frames non-black,
FAKE_CHILD_PID makes it start a child in its process group and write the child's pid there."""
import os
import subprocess
import sys
import time
sys.path.insert(0, os.path.dirname(__file__))
import _common

f = _common.open_log()
_common.key(f, 0, "boot:start")
_common.key(f, 1, "gcm:flip")
if os.environ.get("FAKE_CHILD_PID"):
    child = subprocess.Popen(["sleep", "3600"])
    open(os.environ["FAKE_CHILD_PID"], "w").write(str(child.pid))
d = os.environ.get("PS3RECOMP_METAL_FRAME_DIR")
every = int(os.environ.get("PS3RECOMP_METAL_FRAME_EVERY", "60"))
cap = int(os.environ.get("PS3RECOMP_METAL_FRAME_MAX", "300"))
draws = int(os.environ.get("FAKE_DRAWS", "0"))
px = b"\x40\x80\xc0" if os.environ.get("FAKE_NONZERO") else b"\0\0\0"
stats = open(os.environ["PS3RECOMP_DRAW_STATS"], "w", buffering=1)
n = dumped = 0
stopped = False
while True:
    n += 1
    stats.write(f"{n} {draws} 1\n")
    if d and not stopped and (n == 1 or n % every == 0) and dumped < cap:
        if os.path.exists(os.path.join(d, "STOP")):
            stopped = True
        else:
            with open(os.path.join(d, f"frame_{n:06d}.ppm"), "wb") as o:
                o.write(b"P6\n4 4\n255\n" + px * 16)
            dumped += 1
    time.sleep(0.05)

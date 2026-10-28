#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Imitates GT6 exit-spawning itself (D41): image 1 flips and dumps a frame, then "image 2"
# writes where the port's exec points it (frames/spawn1/, milestones.log.spawn1, stats.spawn1).
import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import _common
f = _common.open_log()
_common.key(f, 0, "boot:start")
_common.key(f, 1, "gcm:flip")
fd = os.environ["PS3RECOMP_METAL_FRAME_DIR"]
open(os.path.join(fd, "frame_000001.ppm"), "wb").write(b"P6\n1 1\n255\n\xff\xff\xff")
open(os.environ["PS3RECOMP_DRAW_STATS"], "w").write("1 3 1\n")
sd = os.path.join(fd, "spawn1")
os.mkdir(sd)
with open(os.environ["PS3_MILESTONE_OUT"] + ".spawn1", "w") as g:
    g.write("# ps3recomp milestone log v1\n0\tboot:start\n1\tgcm:flip\n2\thle:cellPadInit\n")
open(os.path.join(sd, "frame_000001.ppm"), "wb").write(b"P6\n1 1\n255\n\xff\xff\xff")
open(os.path.join(sd, "frame_000061.ppm"), "wb").write(b"P6\n1 1\n255\n\0\0\0")
open(os.environ["PS3RECOMP_DRAW_STATS"] + ".spawn1", "w").write("1 5 1\n61 0 1\n")
time.sleep(3600)

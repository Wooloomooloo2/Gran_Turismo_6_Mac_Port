#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Records the PAD_SCRIPT, PS3_GAMEDATA_ROOT and folder it was given, then flips and presents a frame like series.py.
import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import _common
f = _common.open_log()
print("PAD_SCRIPT=" + os.environ.get("PAD_SCRIPT", "<unset>"), flush=True)
print("PS3_GAMEDATA_ROOT=" + os.environ.get("PS3_GAMEDATA_ROOT", "<unset>"), flush=True)
print("CWD=" + os.getcwd(), flush=True)
_common.key(f, 0, "boot:start")
_common.key(f, 1, "gcm:flip")
d = os.path.join(os.environ["PS3RECOMP_METAL_FRAME_DIR"], "frame_000001.ppm")
open(d, "wb").write(b"P6\n1 1\n255\n\xff\xff\xff")
time.sleep(3600)

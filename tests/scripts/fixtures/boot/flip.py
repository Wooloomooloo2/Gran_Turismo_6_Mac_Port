#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import _common
f = _common.open_log()
_common.key(f, 0, "boot:start")
_common.key(f, 1, "gcm:flip")
if os.environ.get("FAKE_FRAME"):
    d = os.path.join(os.environ["PS3RECOMP_METAL_FRAME_DIR"], "frame_000001.ppm")
    open(d, "wb").write(b"P6\n1 1\n255\n\0\0\0")
time.sleep(3600)

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import os, signal, sys
sys.path.insert(0, os.path.dirname(__file__))
import _common
f = _common.open_log()
for i, k in enumerate(["boot:start", "fs:open", "spurs:init"]):
    _common.key(f, i, k)
os.kill(os.getpid(), signal.SIGSEGV)

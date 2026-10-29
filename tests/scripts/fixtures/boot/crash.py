#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import os, signal, sys
sys.path.insert(0, os.path.dirname(__file__))
import _common
f = _common.open_log()
for i, k in enumerate(["boot:start", "fs:open", "spurs:init"]):
    _common.key(f, i, k)
# Dies by a signal, as a crashed game does, but by SIGKILL: macOS writes a crash
# report (and shows a "Python quit unexpectedly" dialog) for a death by SIGSEGV,
# SIGBUS, SIGABRT and the like, never for SIGKILL (D63). boot_game sees -9 here
# and calls it "crashed" the same way it would -11.
os.kill(os.getpid(), signal.SIGKILL)

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import sys, time
sys.path.insert(0, __import__("os").path.dirname(__file__))
import _common
f = _common.open_log()
_common.key(f, 0, "boot:start")
time.sleep(3600)

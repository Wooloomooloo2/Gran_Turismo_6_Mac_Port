#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import _common
f = _common.open_log()
_common.key(f, 0, "boot:start")
print("[hle] UNRESOLVED NID 0x1234ABCD -> faking cellFoo", file=sys.stderr)
print("[hle] UNRESOLVED NID 0xDEADBEEF -> faking cellBar", file=sys.stderr)
print("[ppu] lv2_syscall 891 (stub)", file=sys.stderr)
print("[ppu] lv2_syscall 891 (stub)", file=sys.stderr)
f.write("# end\n")

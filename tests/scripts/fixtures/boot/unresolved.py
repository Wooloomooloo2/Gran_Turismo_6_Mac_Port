#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import _common
f = _common.open_log()
_common.key(f, 0, "boot:start")
print("[hle] UNRESOLVED NID 0x1234ABCD -> faking cellFoo", file=sys.stderr)
print("[hle] UNRESOLVED NID 0xDEADBEEF -> faking cellBar", file=sys.stderr)
# the dispatcher's own form (ppu_hle.cpp), and its milestone key
print("[hle] unresolved NID 0x0D5B4A14", file=sys.stderr)
_common.key(f, 1, "hle:unresolved:0x30AA96C4")
print("[ppu] lv2_syscall 891 (stub)", file=sys.stderr)
print("[ppu] lv2_syscall 891 (stub)", file=sys.stderr)
# SPU images run in the interpreter (D33): one key per image, the counts at the end
_common.key(f, 2, "spu:interp:F523F26F69764538")
_common.key(f, 3, "spu:interp:CB9BD0241BB0DE67")
f.write("# counts\ncount\tspu:interp:F523F26F69764538\t100-999\n")
f.write("# end\n")

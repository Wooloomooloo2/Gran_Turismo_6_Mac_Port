# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared helper for the fake gt6 programs: writes the real v1 milestone log format."""
import os


def open_log():
    f = open(os.environ["PS3_MILESTONE_OUT"], "w", buffering=1)
    f.write("# ps3recomp milestone log v1\n")
    return f


def key(f, ordinal, name):
    f.write(f"{ordinal}\t{name}\n")
    f.flush()

// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Adapted from ps3recomp templates/project/stubs.cpp at commit
 * 4e8f3ca87a3e1d87bb83b8b7e9348fe2685cd514. That file:
 * Copyright (c) 2026 Ned Heller / sp00nznet, MIT licence
 * (full text in THIRD-PARTY-NOTICES.md and third_party/ps3recomp/LICENSE).
 *
 * GT6-specific hooks and overrides: the PRX loading hook main.cpp calls, HLE overrides for
 * firmware functions the runtime gets wrong for GT6, and patches over lifted code. Each
 * override added here is a hand-written replacement and is recorded in docs/DECISIONS.md
 * (D10). It starts empty. The template's commented examples (NID overrides, module-load
 * hooks, code patches) are in third_party/ps3recomp/templates/project/stubs.cpp.
 */

#include <cstdio>
#include <cstring>

#include "ps3emu/ps3types.h"
#include "ps3emu/error_codes.h"

/* ---------------------------------------------------------------------------
 * PRX loading
 *
 * main.cpp calls this once, after the lifted function table is registered and vm_base is
 * live, before the game runs. GT6 loads no system PRX: no Sony firmware module (liblv2,
 * libsre, any PRX from dev_flash) is loaded or required (D27); the HLE library answers
 * those modules instead.
 * -----------------------------------------------------------------------*/

extern "C" void ps3_load_prx_modules(void)
{
}

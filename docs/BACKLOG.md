# Backlog

Shortcuts taken, with the proper fix logged. Priority order: 1) Stability, 2) Performance,
3) Mac GUI.

## 1) Stability

- SPU lift: 3 of 4 SPU programs and 8 of 57 job modules lift only partly, because data inside
  their code is decoded as instructions (FINDINGS, "Translating EMAIN"). The three programs then
  run fully interpreted. Proper fix: a code end per image (as D25 does for the PPU), or the
  data ranges found by disassembly, passed to the lifter; then drop them from the partial list.
- `scripts/prepare_play.py` does not reproduce the EBOOT's `K/4D` comparison before each node-info merge (0x161ac, 0x32b88); it only checks that `K/4D` exists. It is exact for v1.22 (hash-checked against the real EBOOT's output), but decode the check before using the script on any other edition or version.
- EMAIN's first run installs the staged `TPPS-*` data into `USRDIR/PDIPFS` (more than 5 minutes under RPCS3). It runs in the play folder (D32), but check that a cut-off install resumes safely, and decide what the player's app does when the play folder is stale.

- SPURS job chains: GT6 dispatches at least 16 distinct raw SPU job binaries (in EMAIN's data, e.g. 0x0146B400 64,912 B, 0x014C0F00 53,280 B) and a `Wws_Job` policy module (0x01468200, 12,160 B) that the translate step does not find or lift, so the HLE job chain drops them and fabricates completion events (`jc_signal_done`: data2 = job index). GT6's event-queue-3 worker (func_00A96028) uses data2 as a callback index, so a made-up event can call garbage (seen once, round 5). Proper fix: find and lift these images at translate time and let the real job code send its own events (FINDINGS, bring-up log).
- 312 of EMAIN's 740 imports have no ps3recomp handler (scratch audit by NID hash against the runtime's registrations; most are online, Sail/Rec, NP, USB). Boot-relevant ones still unresolved after round 6: `cellVideoOutGetScreenSize`, `cellSpursInitializeWithAttribute2`, `cellSpursGetWorkloadFlag`, `_cellSpursWorkloadFlagReceiver2`, `cellSpursDestroyTaskset2`, `sys_mempool_create`, `sys_prx_get_module_list`, three `cellUsbd*`. Each faked CELL_OK today; implement or give explicit "not available" answers (RPCS3-modelled), and make the audit a script.
- `scripts/apply_ps3recomp_patches.sh` detects "already applied" by reverse-applying each patch to the final tree, so a later patch whose hunks sit within 3 lines of an earlier patch's makes the earlier one read as "neither applies". Patches 0002/0003 were laid out to avoid this. Proper fix: apply onto a clean checkout in order (or record applied patches) instead of reverse-checking each.
- ps3recomp's `cellKb` reports a keyboard always connected on port 0 and caps `CELL_KB_MAX_KEYBOARDS` at 2 (SDK: 127). Check what GT6 does with a keyboard present versus RPCS3's default null keyboard.

## 2) Performance

- The lwcond waiter queue (patch 0005) is one lock and one condition variable for every lwcond; each signal wakes all waiters to check their own flag. Fine for boot; give each lwcond its own channel if a profile shows wakeup storms.

- Lifted PPU code is compiled at `-O1` (D30). Measure `-O2`/`-O3` compile time and frame
  time in milestone 5 (locked 60) and pick the level from that.

## 3) Mac GUI

- The port builds with the developer's own tools (D29): Apple clang, CMake, Ninja, and
  Homebrew's sdl2, glslang and spirv-cross. Players must not need any of them: bundle a
  pinned toolchain and the libraries, or fetch them checksummed on first setup (D12).
- Players need Python for translation today (`scripts/translate_game.py` and ps3recomp's
  tools, plus capstone etc. from `scripts/requirements-dev.txt`), and the port build runs
  ps3recomp's `gen_hle_nids.py` with whichever Python CMake finds. Ship a self-contained
  translator, or bundle a pinned Python, before any player build.

## Unpacker

- Disc check against the community IRD file (per-file MD5s keyed by ISO sector; needs an ISO directory reader). Until then, the disc's GT.VOL is unverified against an independent source.
- Encrypted redump-style images plus disc keys or IRD files (needs a separate key-handling decision).
- Other regions (US BCUS-98394, Japan, Asia): per-edition hash manifests, update lists, address tables.
- Paid DLC needing PSN licence files or console-bound decryption.
- Player-side update download: fetch the updates directly, with TLS checked against Sony root certificates taken from the disc's update package, and without RPCS3 (spec section 6.1).
- Read the `.iso` directly. Today the player mounts it first (`hdiutil attach`, macOS only) and `gt6unpack` reads the mounted folder.

## Milestone 2 open questions

- Answered: the 1.22 launcher's data-patch step rewrites 6 files that EMAIN needs (FINDINGS, "What the 1.22 EBOOT leaves on disk"; D31). Reproduced by `scripts/prepare_play.py` (D32).
- GT.VOL may hold more helper-chip (SPU) code that the game loads while running. Unknown.
- 217 imported functions in EMAIN are missing from ps3recomp's name list. RPCS3 names all but 5, so feed the names back to ps3recomp upstream.

## Polish (from milestone 1 reviews)

- Fix the stale "O1" numbering in decision D9's text (D1 to D12 were O1 to O12).
- `check_no_game_files.py` prints a traceback on an unreadable file instead of a clean error; fix a stale comment near line 11.
- `install_hooks.sh` overwrites an existing hook and uses `.git/hooks` rather than asking git where hooks live.
- Add tests for the guard's staged mode, a file of exactly 50 MB, and little-endian ELF.
- Decompression with an expected size of zero passes a null buffer; the encryption call's "done" count is unchecked; no empty-input tests for hmac/sha256.
- The key-table test "every entry found by its own revision" is close to circular; pin the NPDRM key and IV and the entry counts.
- SELF reader: sizes taken from untrusted file fields are not capped, so a bad file can raise a non-SELF error.
- SELF reader is stricter than RPCS3 on some flags and short decompressed output; it may reject odd but valid files. Watch for this.
- SELF reader: a header comment is stale after D16; some error paths (offset past end of file, out-of-range indexes, empty supplemental data) are untested.
- Package reader: an all-NUL file name becomes empty and passes checks; the hostile-package test for `/abs` and `./x` asserts nothing useful.
- Package reader: no test crosses the 4 MiB chunk or an unaligned offset; file count allocation is uncapped; filesystem errors are not wrapped as package errors; leading "/" is stripped inconsistently in `pkg_param_sfo`.
- Build: the "not enough disk space" refusal is untested; the space estimate omits decrypted executables; duplicate JSON keys are accepted; `hex()` is copied in three places; one redundant `.gitignore` line; `build_tree.cpp` is 480 lines and should be split; the edition path is compiled into `main.cpp`.
- Build: a failed restore rename hides the original error.
- Verify: duplicate or `../` manifest paths are unchecked; static 8 MiB buffer; the reader accepts trailing garbage; no test for empty files or size-only mismatch.
- `manifest.cpp` has a redundant `<cstdio>` include.
- The map CLI test should skip when capstone is missing; test fixture values copy real GT6 metadata (use invented ones); `requirements-dev.txt` copies ps3recomp's dependencies (update on a pin bump).

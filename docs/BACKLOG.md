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

- SPURS images found only at run time (D33): GT6's 16 job binaries and its `Wws_Job` policy module are dumped to `<tree>/spu-missed/` on first use and lifted by the next translate. All 17 sit byte for byte in EMAIN's read-only segment (FINDINGS), so a fresh tree needs one boot before they run native. Proper fix: find them statically (the job CRT's fixed prologue, or the job descriptors' `eaBinary`) in the translate step. All 17 lift only partly (data decoded as code, 4 to 1,258 words each): give each image a code end, as for the 8 partial job modules.
- `cellFiberPpuContext*` (`_cellFiberPpuContextAttributeInitialize`, `cellFiberPpuContextInitialize`, `cellFiberPpuContextRun`) are unresolved and fake CELL_OK; GT6 calls them during the first-run install, right after its first frame. Implement them (PPU fibers: a guest context switch, which a static recompilation has to run on host fibers or threads).
- 312 of EMAIN's 740 imports have no ps3recomp handler (scratch audit by NID hash against the runtime's registrations; most are online, Sail/Rec, NP, USB). The 12 GT6 called in the first-frame runs (20261027-202305/202348), all faking CELL_OK today: `cellVideoOutGetScreenSize`, `_cellSpursWorkloadFlagReceiver2`, `cellSpursGetWorkloadFlag`, `cellSpursInitializeWithAttribute2`, `cellUsbdSetThreadPriority2`, `cellUsbdRegisterExtraLdd`, `sys_mempool_create`, `cellUsbdRegisterExtraLdd2`, `sys_prx_get_module_list`, `_cellFiberPpuContextAttributeInitialize`, `cellFiberPpuContextInitialize`, `cellFiberPpuContextRun` (`cellSpursDestroyTaskset2` was also called in the runs that exited). Implement each or give it an explicit "not available" answer (RPCS3-modelled), and make the audit a script.
- Teardown SIGBUS, not chased (controller ruling): runs 20261027-191824 and 20261027-193740 crashed with SIGBUS (exit -10) about 2.3 s in, after GT6 called `exit(1)` and the runtime began tearing down. Last keys: `hle:cellFsRename`, `hle:sys_ppu_thread_exit`, `sys:988`, `hle:sys_prx_exitspawn_with_level`, `hle:cellAudioRemoveNotifyEventQueue`, `hle:unresolved:0x1EBCF459` (`cellSpursDestroyTaskset2`). The leaked lwcond statics (patch 0005) were not the cause; the crash stopped once the SPURS images ran (D33, the exit itself then was clean), and GT6 no longer exits since D34. Expect it back whenever the game exits for real (quit from the menu): exit-time teardown with guest threads still running is untested.
- `scripts/apply_ps3recomp_patches.sh` detects "already applied" by reverse-applying each patch to the final tree, so a later patch whose hunks sit within 3 lines of an earlier patch's makes the earlier one read as "neither applies". Patches 0002/0003 were laid out to avoid this. Proper fix: apply onto a clean checkout in order (or record applied patches) instead of reverse-checking each.
- Patch 0008: neither SPURS job path checks the `spu_run_spurs_job` stage result. The interpreted path (`runtime/spu/spu_workload.c` ~1168) ignores it, and the lifted path (~1189) only logs it under `SPU_JOBPROF`. Make both treat a negative (error) stage result as a failed job.
- Guest `setjmp`/`longjmp` (patch 0009): a frame re-armed after a newer site is dropped by a longjmp to that newer site. Not seen in GT6's 22 call sites; fix if a title needs it.
- `g_sjlj_top` is not reset when the interrupt-handler loop re-enters after a thread-exit unwind (`runtime/syscalls/sys_ppu_thread.c` ~229-233 and ~647). Reset it there.
- `port/CMakeLists.txt` runs the patch script with the caller's environment, so an exported `GT6_PS3RECOMP_DIR` or `GT6_PS3RECOMP_PATCHES` would patch a different checkout than the one being built while the hash check still passes. Run it through `cmake -E env` with those set explicitly.
- `scripts/translate_game.py` still accepts a `translate.json` with no `tool` field (written before the milestone 2 final fixes) as its own output, so `-o` would replace a copied backup of `recomp/`. The owner's tree has been re-translated with `tool` set; drop the legacy rule.
- Two upstream ps3recomp runners in `tests/scripts/test_ps3recomp_patches.py` are load-sensitive: `test_gcm_walker_prof` (1 s sampler timing) and `test_spu_context_registries` (`test_spu_lockline_peer`, 30 s timeout). On 2026-10-27, with another app using about 450% CPU, both failed on an unpatched `git archive` of 4e8f3ca8 too; they pass on an idle machine (172 passed). Skip or retry them when the load is high, and report the timing assumptions upstream.
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

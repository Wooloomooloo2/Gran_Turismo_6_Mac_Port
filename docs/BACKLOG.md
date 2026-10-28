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
- Fixed (bring-up round 1, D38): the fiber-context deadlock in the first-run install was GT6's realloc failing on a heap reservation that crossed 0x80000000, which leaked the C library's atexit lock.
- GT6 draws no text in its own dialogs (install, install error): the frame, icon, progress bar and buttons are drawn, the title ("Please wait..."), the message ("Installing...", "Installation complete.") and the button labels are missing, while the legal text behind them is drawn (FINDINGS, bring-up round 2). Find how GT6 renders dialog text (a font texture or glyph cache built at run time, perhaps by an SPU job) and why ours stays empty.
- Fixed (bring-up round 3, patches 0019-0021): GT6's shutdown after "Installation complete." hung on a forced event-queue destroy that woke nobody; it now completes and exit-spawns EMAIN.SELF, which the port re-executes (D41).
- Post-install, EMAIN shuts down by itself 1.5-2 s after starting, in the re-executed image and in a fresh boot on the installed play folder (FINDINGS, bring-up round 4). Find why main returns; check `cellGameBootCheck`'s title id (`BLES00000` instead of BCES01977) and what the 1.22 EBOOT does before a post-install launch.
- The exit-spawned image gets an empty envp and no data block, and the port knows only EMAIN.SELF as a target (D41).
- Fixed (Task 5 batch 2): the empty `<tree>/dev_bdvd/game/BCES01977/USRDIR` and `.../BCES01893/USRDIR` folders came from `cellGameContentPermit`, which also made each game-data folder under the VFS root (the disc layer), and made one for game data `cellGameDataCheck` had not found. Patch 0022 stops both; the folders were deleted, and `gt6unpack verify` reports 0 mismatched, 0 missing, 0 extra.
- `cellFsGetBlockSize` in `runtime/ppu/ppu_fs.cpp` reports a 4096-byte sector where /dev_hdd0 has 512 (RPCS3's mount table). Make it follow lv2.
- Fixed (Task 5 batch 3): `mkdir`, `rename`, path `truncate` and opens with write access, `O_CREAT` or `O_TRUNC` now go through the D42 allowlist (patch 0024, D45). Before, `rename` and `truncate` were `cellFs.c`'s (its prefix map sends `/dev_bdvd` into the disc layer, with no `..` handling) and `mkdir` and write-opens went through `ppu_fs.cpp`'s `host_path()`, so the disc layer could gain, lose, be overwritten or emptied, not only gain folders. Still unguarded upstream code GT6 does not reach: `cellFs.c`'s own unlink/rmdir/mkdir/open and the raw `sys_fs_*` syscalls in `sys_fs.c`; the host guard (D46) covers them.
- Read-only `cellFsOpen`, `cellFsStat` and `cellFsOpendir` still resolve a relative path (GT6 stats `database/gt6` and `specdb/GT6`) or an unknown device into the VFS root, where lv2 answers ENOENT / ENOTMOUNTED. Harmless to the tree (reads only, and D46), but not the console's answer: give reads the same canonical lookup.
- ppu_fs's descriptor calls read the fd's `FILE*` outside `g_fd_lock` and do not re-check it under the lock (`cellFsFtruncate` and the rest; review m7): a close racing a call is a use-after-free. Re-read under the lock throughout.
- Fiber contexts (patch 0011, D36): `sys_ppu_thread_exit` called inside a context does not end the PPU thread that ran it (the context's host thread has no exit point armed; the call returns). The Windows path (CreateThread, SRW lock) is untested. ps3recomp's scheduler API (`cellFiberPpuRunFibers`, ucontext) still shares host thread-locals (`g_sjlj_top`, indirect-call depth, trampoline, callback stack slot) between the fibers of one thread; GT6 does not import it.
- Fiber contexts (patch 0011): the per-guest-thread-id diagnostics (`g_hle_inflight`, `ftrace`, `prof`) key on `thread_id`, so a PPU thread and the fiber context it is running alias each other there. Key them on the host context (or add a context id) if a diagnosis needs to tell them apart.
- Imports (`scripts/audit_imports.py`, FINDINGS "Import audit"): 280 of EMAIN's 740 have no handler; none of them is called in any run so far or by the RPCS3 reference run. Re-run the audit with `--runs` after each boot that gets further: any new caller of an unhandled import is the next one to implement. Shortcuts taken in patches 0012-0017 (all listed in D37): the SPURS runtime still has 16 workload slots (a CellSpurs2's workloads 16-31 cannot be added); `cellMusicSetVolume2` does not read its float (f1; nothing plays).
- ps3recomp error codes that are not the PS3 SDK's: `libs/video/cellVideoOut.h` builds `CELL_VIDEO_OUT_ERROR_*` from 0x8002B100 (SDK 0x8002b220); in `libs/network/sceNpTrophy.h` every name with an SDK code now has the SDK's value (patch 0017), but `ALREADY_EXISTS`, `NOT_FOUND`, `CONTEXT_ALREADY_REG`, `PROCESSING` and `UNKNOWN` have no SDK code and keep 0x805516xx: check which SDK code each call site should return instead. Fix each module's header and check its callers.
- The audit's miscount guards report 3 NIDs registered under two names and 15 literal NIDs labelled with a name that does not hash to them (the `sys_net`/`net*` block in `runtime/ppu/ppu_sysprx.cpp`). None is on GT6's path; tidy them upstream.
- System call 327 (`sys_mmapper_enable_page_fault_notification`) is unimplemented and called at boot (RPCS3 sees it too). Implement it as lv2 does.
- RPCS3 reference stops before the menu (FINDINGS, "RPCS3 reference: boot to the first menu"). After the first-run install, GT6 v1.22 under RPCS3 0.0.43-20410 shows a fatal "Insufficient free space on Hard Disk Drive (HDD). At least 32MB required. 0x0000000b [68]" at 14.6 s, although RPCS3 reports 40 GB free. Until the cause is found, the menu has no reference frame. Next steps: find which call fails just before `cellMsgDialogOpen2` (the db and `/dev_hdd1/game024.db` creation, trophy registration, or a call inside a firmware-run library), or try RPCS3 with GT6's libraries in HLE. Also, each newly compiled EMAIN stalls on its first RPCS3 boot (a SPURS event never arrives) and needs a second launch.
- The first-run install ends on GT6's "Installation complete." dialog, which waits for Cross. Unattended port runs must inject a Cross press (pad input) to get past it; EMAIN then exit-spawns itself, so the harness must follow a second `EMAIN.SELF` start.
- Teardown SIGBUS, not chased (controller ruling): runs 20261027-191824 and 20261027-193740 crashed with SIGBUS (exit -10) about 2.3 s in, after GT6 called `exit(1)` and the runtime began tearing down. Last keys: `hle:cellFsRename`, `hle:sys_ppu_thread_exit`, `sys:988`, `hle:sys_prx_exitspawn_with_level`, `hle:cellAudioRemoveNotifyEventQueue`, `hle:unresolved:0x1EBCF459` (`cellSpursDestroyTaskset2`). The leaked lwcond statics (patch 0005) were not the cause; the crash stopped once the SPURS images ran (D33, the exit itself then was clean), and GT6 no longer exits since D34. Expect it back whenever the game exits for real (quit from the menu): exit-time teardown with guest threads still running is untested.
- `scripts/apply_ps3recomp_patches.sh` detects "already applied" by reverse-applying each patch to the final tree, so a later patch whose hunks sit within 3 lines of an earlier patch's makes the earlier one read as "neither applies". Patches 0002/0003 were laid out to avoid this. Proper fix: apply onto a clean checkout in order (or record applied patches) instead of reverse-checking each.
- Patch 0008: neither SPURS job path checks the `spu_run_spurs_job` stage result. The interpreted path (`runtime/spu/spu_workload.c` ~1168) ignores it, and the lifted path (~1189) only logs it under `SPU_JOBPROF`. Make both treat a negative (error) stage result as a failed job.
- Guest `setjmp`/`longjmp` (patch 0009): a frame re-armed after a newer site is dropped by a longjmp to that newer site. Not seen in GT6's 22 call sites; fix if a title needs it.
- `g_sjlj_top` is not reset when the interrupt-handler loop re-enters after a thread-exit unwind (`runtime/syscalls/sys_ppu_thread.c` ~229-233 and ~647). Reset it there.
- `port/CMakeLists.txt` runs the patch script with the caller's environment, so an exported `GT6_PS3RECOMP_DIR` or `GT6_PS3RECOMP_PATCHES` would patch a different checkout than the one being built while the hash check still passes. Run it through `cmake -E env` with those set explicitly.
- `scripts/translate_game.py` still accepts a `translate.json` with no `tool` field (written before the milestone 2 final fixes) as its own output, so `-o` would replace a copied backup of `recomp/`. The owner's tree has been re-translated with `tool` set; drop the legacy rule.
- Two upstream ps3recomp runners in `tests/scripts/test_ps3recomp_patches.py` are load-sensitive: `test_gcm_walker_prof` (1 s sampler timing) and `test_spu_context_registries` (`test_spu_lockline_peer`, 30 s timeout). On 2026-10-27, with another app using about 450% CPU, both failed on an unpatched `git archive` of 4e8f3ca8 too; they pass on an idle machine (172 passed). Skip or retry them when the load is high, and report the timing assumptions upstream.
- The frame series and draw statistics (patch 0010, D35) cover the draw-engine render path only. The legacy vtable path (`PS3RECOMP_RSX_ENGINE=vtable`) counts nothing and dumps no series; add it there if that path is ever used again.
- ps3recomp's `cellKb` reports a keyboard always connected on port 0 and caps `CELL_KB_MAX_KEYBOARDS` at 2 (SDK: 127). Check what GT6 does with a keyboard present versus RPCS3's default null keyboard.

- Writers outside the cellFs allowlist (D45, batch 3 review m5): `cellSysCacheMount` and cellGame CreateGameData join a guest-supplied name to a host root without canonicalising it (a `../` in a cache id or game-data folder name would leave the play folder; GT6 passes its title id). The EDAT `.dec` cache is written beside the encrypted file wherever that is (refused on the read-only disc layer, D46). `cellFsUtil*` (`cellFsUtility.c`) uses the raw guest path as a host path (GT6 does not import it). Proper fix: route all four through ppu_fs.cpp's resolver.
- The `GT6_IMAGE_SWITCHED` guard and the per-image `PAD_SCRIPT` hand-over in `port/main.cpp` have no automated test (batch 3 review m7); they are exercised only by the end-to-end install run.

- ps3recomp's SPURS coordinator (`spurs_kernel_thread`) uses up one ready count per dispatch; RPCS3's kernel treats `wklReadyCount1` as the number of SPUs requested (selectable while it exceeds the current contention) and never decrements it. Not the cause of the round 13 stall (an experiment that keeps the count stalls the same way), but a known difference.
- `cellFsAllocateFileAreaWithoutZeroFill` answers CELL_OK and does nothing (ps3recomp: "host files grow on write"). RPCS3 models it as lv2 fcntl 0xE0000017, which truncates the named file to the size; the fcntl itself answers CELL_OK, and a missing file is reported in its `out_code` (ENOENT), not as the call's result. GT6 calls it on its PDIPFS cache copies (`*.fdupi`) just before writing exactly that many bytes, so it is harmless so far (FINDINGS round 13). Make it a truncate through the D45 allowlist.
- Movies (D57, patch 0034): GT6's opening movie is not played. Real playback needs a guest-ABI PAMF demuxer (`cellDmuxOpenEx` with a demux thread delivering the title's DEMUX_DONE / AU_FOUND callbacks, `EnableEs`, `GetAu`/`ReleaseAu`), the AVC decoder (`libvdec`, VideoToolbox) and the audio decoder (`cellAdec`: ATRAC3plus has no macOS decoder, AC3 does). Until then `cellDmuxQueryAttr`/`OpenEx` answer FATAL. ps3recomp's `cellPamfReader*` still parse an invented header layout (0 streams for GT6's file) and its `cellDmuxOpen`/`SetStream` are host-layout toys; both must be rewritten on the real formats with the demuxer. `cellPamfVerify` checks only the header's top level.

- The SPU interpreter and the lifted copy of GT6's WWS policy module (`missed_5510dcb89c1e98c2`) disagree on the module's first queue check (LS 0x23F0): interpreted, it finds no work and exits every time (FINDINGS round 14). Compare them step by step; other interpreted images may share the cause.
- First boots on a busy machine stop on the screen-adjust page before the opening movie, with every SPURS worker idle (FINDINGS round 14 (b)). Find the job or wake-up that is lost.
- `cellFsGetFreeSize` reports exactly 32 GiB (8 M blocks of 4 KiB). A title that multiplies block size and count in 32 bits gets 0 from any exact multiple of 4 GiB; check GT6's use before the second-boot HDD-space dialog is chased (FINDINGS round 13 (b)), and prefer a value that is not one.

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
- Two executables (D44): the player app must also run the build of whichever EMAIN.SELF the play folder holds, and the code map (D21) should map `TPPS-01.22/EMAIN.SELF`. The README's "Translate and boot" lists the second translation; a single script step that translates and builds both would stop them drifting apart.
- Syscall 988 is treated by `ppu_loader.cpp` as a second `sys_tty_write`; under lv2/RPCS3 it is a debug PPU-exception-handler call (unimplemented in RPCS3). It reads a NULL buffer and logs "[tty] suspicious len". Make it a logged no-op.
- Fixed (Task 5 batch 3): the post-install EMAIN's unresolved imports are `cellKey2CharSetArrangement` (0x0DFBADFA), `inet_pton` (0x8AF3825E) and `getsockname` (0x13EFE7F5) (sys_net), found by hashing RPCS3's symbol names. Patch 0026 implements them (D48).
- Fixed (Task 5 batch 3): the two empty folder trees `<tree>/dev_bdvd/database/gt6` and `specdb/GT6` came from GT6 building paths on an empty root: it checks for another title's game data (`cellGameDataCheck` of BCES01893, absent, so ContentPermit answers empty paths as the console does) and then makes `/database` and `/specdb` and stats `database/gt6` and `specdb/GT6` (run 20261028-061356, `PS3_FSLOG`). Patch 0024 answers as lv2 does (ENOTMOUNTED for the device-less mkdirs, ENOENT for relative paths); the folders were removed with `rmdir` after `gt6unpack verify` reported 0 mismatched, 0 missing, 0 extra (before and after), and the disc layer is now read-only on the host (D46).
- Page-fault notification (patches 0029, 0033, D52): a fault from a thread with no guest PPU identity (SPU worker, HLE host thread, guest callback on a host thread) is sent as a PPU-type fault under a host fault id (0x7FFE0001 on) and printed as `[pf] NON-PPU thread ...`; lv2 would send an SPU thread's fault with its SPU type and resume it with 198. Do that once SPU threads carry their lv2 id. None seen in GT6 so far. Memory objects are lenient (64 KB rounding, no 1 MB pages, container ignored; D52). A thread that faults while holding a host lock the pager needs (e.g. a `stwcx` reservation shard) still deadlocks. An object is mapped at most once inside a page-fault area (lv2 allows aliases), and outside such areas unmap remembers only an object's latest mapping. The shared-memory syscalls (332/334/335) keep their own id table and flat behaviour.
- GT6 issues no text draws: no vecfont pipeline is ever created (`/font/vecfont_shaders.bin`, the vecfont SPU overlay at 0x0141B680 runs). Find where the font pack load or the text pass stops (FINDINGS round 10).
- Fixed (Task 5 batch 6, patch 0034, D57; batch 6 review M-7): the five movie imports (`cellDmuxOpenEx`, `cellDmuxQueryAttr`, `cellPamfVerify`, `cellPamfGetHeaderSize2`, `cellPamfGetStreamOffsetAndSize`) no longer fake CELL_OK and the white screen is gone. Real playback is the "Movies" item below.
- Task 5 batch 4 review M-1 (rest): the CMake and Python tree hashes are now tested against each other, and both drop carriage returns (a CRLF diff made every build stale); a path git quotes (`core.quotepath`, non-ASCII names) is still untested on both sides.
- Task 5 batch 4 review M-3: files the submodule's `.gitignore` covers are outside the tree hash, and an edit between compile and link is recorded as compiled.
- Task 5 batch 4 review M-6: for the default play folder the harness sets `PS3_GAMEDATA_ROOT` but no HDD roots; set all three roots for whichever folder it checked.
- Task 5 batch 4 review M-7: `--gt6` outside `port-build*` with no `gt6.image` still runs with a warning; consider requiring `--allow-unchecked`.
- Task 5 batch 4 review M-8: `GT6_IMAGE_SWITCHED` and the per-image `PAD_SCRIPT` hand-over in `port/main.cpp` (batch 3 m7) are exercised only by the real install run.

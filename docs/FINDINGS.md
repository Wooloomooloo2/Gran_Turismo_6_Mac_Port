# Findings

## Owner summary: milestone 2 (2026-10-27)

**The game now starts on the Mac and reaches its first screen update, but the one picture we
captured is solid black, so "draws something" is not yet shown.** It ran three times, each on a
fresh play folder (runs 20261027-202305 and 20261027-202348, then 20261027-203953 after the
review fixes), with no crash, for about 5 seconds each time, and then the test harness stopped it.

| Question | Answer |
|---|---|
| Does it start and run? | Yes. The translated program boots, loads its data and presents its first frame (`first_frame`) on every fresh run after round 8's fix. Eight bring-up rounds, nine patches to the runtime we borrow (listed in the bring-up log). |
| Does it draw something? | Not shown yet. The first dumped frame is solid black. GT6 is running its first-run data install at that moment (more than 5 minutes under RPCS3), and a black frame cannot tell "cleared to black" from "nothing drawn". The next step is to compare against an RPCS3 capture of the same moment. |
| Biggest risk | Three calls that let the game run helper "fibers" are not implemented and pretend to succeed. They are the likely next blocker; the install cannot finish without them. 12 imports in all are faked this way (backlog). |
| What milestone 3 needs | Your go-ahead. It starts with the RPCS3 comparison, then the fiber calls, and aims at the first menu. |

One smaller risk: the disc has not yet been checked against an independent source (backlog).

## Owner summary: milestone 1 (2026-10-27)

**Milestone 1 is done.** Your copy of the game now turns into a verified version 1.22 game
folder, and the game's code is fully mapped. Nothing failed outright.

| Question | Answer |
|---|---|
| Is it really v1.22? | Yes. All 21 updates matched Sony's own published checksums before they were installed, and the installed result is byte-identical to what RPCS3's own installer produces from the same packages (16,536 files). Every game program was unlocked. The folder's checksums are now recorded, so any later build can be checked against this one. |
| How big is the game's code? | One 23 MB program made of about 72,000 separate routines. All of it has to be translated for the Mac. |
| Biggest risk | The game also runs many small programs on the PS3's helper chips. Recreating those on the Mac is the hardest part of what comes next. |
| What milestone 2 needs | Your go-ahead. It starts by settling three things: a data-patching step the launcher runs, how to handle the helper-chip programs, and how long the translation takes. |

One smaller risk: the disc has not yet been checked against an independent source (backlog).

Measurements and facts, newest first within each section.

### Test run, milestone 2 handover

- `ctest --test-dir build`: 2/2 passed (also with `GT6_TREE` set; the two ctest cases do not use it).
- `.venv/bin/python -m pytest tests -q`: `153 passed, 5 skipped` (the skips need the game folder).
- Same with `GT6_TREE="~/Gran Turismo 6/build/BCES01977-v1.22"`: `158 passed`, 0 skipped.
- C++ integration cases (`GT6_DISC_DIR`, `GT6_UPDATES_DIR`) were not re-run: milestone 2 changed no C++ unpacker code (last full run above: 71/71).
- `scripts/check_no_game_files.py $(git ls-files)`: clean.

### Test run, milestone 1

Full suite with the real disc and all updates (re-run after the final review fixes):

- `ctest --test-dir build`: 2/2 passed. `gt6unpack_tests`: `test cases: 71 | 71 passed | 0 failed | 0 skipped`; `assertions: 424 | 424 passed | 0 failed`.
  Integration cases are marked skipped when `GT6_DISC_DIR`/`GT6_UPDATES_DIR` are unset
  (`67 passed | 4 skipped` without the data), so "0 skipped" here means all 4 ran.
- `.venv/bin/python -m pytest tests -q`: `37 passed`.
- `gt6unpack verify ~/Gran\ Turismo\ 6/build/BCES01977-v1.22 --manifest manifests/BCES01977-v1.22.json`: `16568 files checked: 0 mismatched, 0 missing, 0 extra` (now also checks the tree's PARAM.SFO is BCES01977 01.22).
- `scripts/check_no_game_files.py $(git ls-files)`: clean.

## Bring-up log (milestone 3)

One row per bring-up round of Task 5, newest first. Runs are `scripts/boot_game.py` on a fresh
play folder (`prepare_play.py --force`) unless the row says otherwise; run folders are under
`<tree>/runs/`.

| Round | What stopped it | Root cause | Fix | Outcome after |
|---|---|---|---|---|
| 6 (open; runs 20261028-052337, 20261028-052422) | 1.6-4.9 s after the start of the post-install image, GT6 aborts: `Assertion failed: (advance > 0), function substitute, file process.c, line 462.`, then `abort() is called from 0x...c6a09c` and `sys_process_exit(1)` from 0x00C58C60 | Not found yet. The assertion text is in neither EMAIN image (it comes from data loaded at run time); `substitute` with a glyph `advance` reads like text shaping, which fits GT6's dialogs drawing no text (batch 1). Three imports are unresolved and fake CELL_OK just before: 0x0DFBADFA (after the keyboard set-up, lr 0x00B0F9E4), 0x8AF3825E and 0x13EFE7F5 (lr 0x0095xxxx, beside the unnamed 0x9C056962/0xB0A59804/0x88F03575). Syscall 988 (RPCS3: a debug exception-handler call, unimplemented) is read by ps3recomp as a tty write and prints a NULL-buffer warning | none yet | next batch |
| 5 (run 20261028-051358) | The post-install image stops at GT6's "Insufficient free space on HDD. At least 32MB required." dialog (also where RPCS3's attempt C ends, with another code) | `cellFsFtruncate` (sizing `USRDIR/db/userdb0101.dat` to 8 MB) was only registered in `cellFs.c`, whose descriptor table never holds the fds `ppu_fs.cpp` hands out, so it answered EBADF and GT6 read that as a full disk | patch 0023: `ppu_fs.cpp` registers `cellFsFtruncate` on its own fds (EBADF for a closed or read-only fd, as lv2); test in `test_fs_imports.cpp` | run 20261028-052337: no dialog; GT6 goes on (threads `PDI`, `ZYWr6`, I/O mappings) to round 6 |
| 4 (runs 20261028-041621, 20261028-044549 to 20261028-050847) | After the install, EMAIN (the exit-spawned image, and a fresh boot of the installed play folder) shuts down within 1.5-2 s | Not a crash and not the title id: main's stage runner completes and its last stage runs the adhoc script `scripts/gt6/main` (func_00013B38), which stops with an adhoc fatal error, `undefined attribute (Array)([]).'reserve'` in `scripts/gt6/MiniNoticeUtil.ad` (found by tracing the error formatter's pieces). The install replaces `USRDIR/EMAIN.SELF` with `TPPS-01.22/EMAIN.SELF` (9,001,952 -> 9,209,104 bytes; the clone after the install has the TPPS one), and the port kept running its translation of the old executable, whose interpreter predates `Array.reserve`. RPCS3's attempt C ran the new one (its BootCheck out-pointers lie in the TPPS image's data segment). Also fixed on the way: cellGame answered with its placeholders (BLES00000, APP_VER 01.00) instead of the update's PARAM.SFO (D43) | D44: one build per executable; the port execs the build of whichever EMAIN.SELF the play folder holds, at start and on exit-spawn (`translate_game.py --elf`, `-DGT6_RECOMP`, `gt6.image`, `GT6_IMAGES`). Patch 0022 + `port/main.cpp`: the update's PARAM.SFO (GD, PATCH attribute; D43) | run 20261028-051358 (installed folder, 120 s): the TPPS build starts, stays up the whole run, draws 120 of 122 frames, loads the save data (none yet), registers trophies, creates `userdb0101.dat` and `game024.db`, and then shows "Insufficient free space on Hard Disk Drive (HDD). At least 32MB required. 0x0000001a [166]" over "Sony Computer Entertainment presents": the state RPCS3's attempt C ends in (round 5) |
| 3 (run 20261028-033627, 1000 s, Cross every 60 s from 300 s) | The install runs to the end, about 470 s, close to RPCS3's 7 minutes. The dialog reaches its "complete" state (full bar, cursor on OK) and Cross is accepted. GT6 then shuts down its input, USB and sysutil, as under RPCS3, but stops there: the respawn of EMAIN.SELF never happens, and frames are dumped to the end of the run | Three faults on this path. (a) The shutdown hangs in thread joins. The main thread joins tid 24 (func_00831D38); tid 24 stops tid 25, its event thread (func_00831DA0: clear the run flag at 0x0165F560+0x4C, then `sys_event_queue_destroy(queue, SYS_EVENT_QUEUE_DESTROY_FORCE)`), then joins it. ps3recomp's destroy ignored the mode, woke nobody and destroyed the lock under the waiter, so tid 25 stayed in `sys_event_queue_receive` (func_00832060). (b) The respawn that follows (`sys_game_process_exitspawn2` / `sceNpDrmProcessExitSpawn2`, both imported) had no handler and no host support. (c) `cellFsUnlink` and `cellFsRmdir` answered CELL_OK and removed nothing, so the install's leftovers (more than 10,000 unlinks; `TPPS-01.07/update.txt` and `UPDATING` among them) would have stayed for the post-install boot | patch 0021: destroy follows lv2 (EBUSY / FORCE wakes the receivers with ECANCELED / EINVAL). Patch 0019 + `port/main.cpp`: the exit-spawn calls, with the port exec'ing itself on EMAIN.SELF.elf (D41); `boot_game.py` follows the new image (`spawns`). Patch 0020: real unlink and rmdir. Tests: `test_event_queue_destroy.c`, `test_exitspawn.c`, `test_fs_imports.cpp`, and a fake respawn in `test_boot_game.py` | run 20261028-040705 (fresh play folder, Cross at 480/540/600 s): the install ends, Cross is taken, the shutdown completes (tid 25 leaves its receive with ECANCELED), and GT6 calls `sys_game_process_exitspawn2("/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF", argc 3)`. Its atexitspawn function runs and the port re-executes as image 2 (`frames/spawn1`). With real unlink, the install now leaves the TPPS folders, `update.txt` and `UPDATING` gone, as under RPCS3. Image 2 boots (game data check, cache mount, GCM, SPURS, first flip) and then ends by itself after about 2 s (round 4). Smoke boot 20261028-042509 after the last 0018 change: the install runs as before |
| 2 (runs 20261028-031719, 20261028-032801) | GT6 shows its own one-button dialog with a warning icon and no text over the dimmed legal text, from present 120 to the end of a 300 s run. Pressing Cross makes GT6 shut down (pad, USB, sysutil end). Only 10-99 renames happen in 300 s; RPCS3's install makes 594 and shows "Installing..." with a progress bar | The install decodes each patched file into the cache partition (`/APP_CACHE_RAW` = `/dev_hdd1/cache/BCES01977`): func_00A34B00 writes `<file>.plain`, then renames it over `<file>` (func_00A7CE30). The port set no root for `/dev_hdd1`. `ppu_fs.cpp` resolved it into the disc layer (`<tree>/dev_bdvd/cache/...`, inside the verified tree, 8 stray files, now deleted), and `cellFs.c` had no mapping, so `cellFsRename` answered ENOENT (0x80010006). func_00A34B00 failed, the install aborted (failure branch at 0xA3520C in the apply loop) and GT6 opened its install-error dialog. Ruled out first: free space (`cellFsGetFreeSize` reports 32 GB, and all five callers multiply in 64 bits) and the fiber handoff (no Run waits more than 2 s) | `port/main.cpp`: `/dev_hdd1` is `<tree>/play/dev_hdd1` for both file layers (`PS3_HDD1_ROOT` and a `cellFs.c` mapping), made when missing (D39). `boot_game.py --press SECONDS:BUTTON` through ps3recomp's existing `PAD_SCRIPT` (D40). Test: the real-port test checks the `[boot] /dev_hdd1:` line; `test_boot_game.py` covers `--press` | run 20261028-033051: 298 decode-and-rename steps succeed in 60 s, and the dialog is now the install dialog (progress section, OK button) over the legal text and Polyphony logo, still with no dialog text |
| 1 (runs 20261028-023739, 20261028-025905, 20261028-030151, 20261028-030307) | The deadlock of Task 4: the fiber context (guest thread 26) blocks in `sys_lwmutex_lock(0x01765788)` from func_00841978; the main thread holds that lwmutex while it waits in `sys_lwcond_wait` (func_00A5F3DC) | 0x01765788 is the C library's lock, taken by atexit (func_00BD3E6C). When atexit's table is full it grows it with realloc and, if realloc fails, returns 1 without releasing the lock. GT6's realloc (func_00A89220) failed every time: its page lookup (func_00A85D00) returned "not found" (-194) for every block. GT6's heap numbers its 8 KB pages as `(address >> 13) & 0xFFFF` within its 512 MB reservation (`sys_mmapper_allocate_address(0x20000000, align 0x10000000)`), and ps3recomp put that reservation at 0x70000000, across 0x80000000, where the page numbers wrap. Under RPCS3 the same request lands at 0x40000000. The lwcond wait itself was correct (it releases the lwmutex and takes it again). The free-space and fiber leads were not it | patch 0018: a power-of-two reservation larger than its alignment is placed on its own size, falling back to the requested alignment (D38); the heap is now at 0x80000000. Test: the mapper fixture gains the 256 MB + 512 MB sequence and the 16-bit page check; the new checks fail without the change | run 20261028-031028 (300 s): no deadlock; every realloc lookup succeeds; 149 of 150 frames drawn; GT6 draws its own dialog over the dimmed legal text (round 2) |

## Bring-up log (milestone 2)

One row per bring-up round, newest first. Runs are `scripts/boot_game.py` on a fresh play
folder (`prepare_play.py --force`) unless the row says otherwise; run folders are under
`<tree>/runs/`.

| Round | What stopped it | Root cause | Fix | Outcome after |
|---|---|---|---|---|
| 8 (run 20261027-200531) | GT6 exits (`sys_process_exit`) at 1.9 s on its Thrustmaster force-feedback thread (`TM_FFB_WorkerThread`, func_00AADA2C): `Fail: sys_mutex_lock (-2147418107)`, ESRCH, because the mutex id at driver+0x144C reads 0; the driver's state is overwritten with decompressed data, or, in other runs, the inflater writes through NULL (`[null-write]` by func_00A5A1B0) | GT6's file worker decodes with an inflater (func_00A5AA84) whose output-full callback (func_00A46524) asks the consumer thread for the next buffer. When the consumer has none (size 0, seen with `PPU_WWATCH` on req+0x1C38), the callback aborts the decode with the C library's `longjmp` (func_00BDD050) back to the `setjmp` (func_00BDCF2C) in func_00A46FB4. Lifted, every guest call is a host call, so the longjmp only returned from itself: the inflater went on with the setjmp's registers into a NULL or stale output buffer, ran past it, and clobbered the next driver's state | patch 0009: `ppu_lifter --setjmp/--longjmp`; each direct setjmp call takes a host `_setjmp` frame (dropped on every return of its function), and the guest longjmp ends in a host `_longjmp` to it, restoring the indirect-call depth. `translate_game.py` finds the two functions by their first six instructions (one each in EMAIN) and records them in `translate.json` `sjlj`. Test: `tools/test_ppu_sjlj.py` | run 20261027-202305, repeated in 20261027-202348 and, after the review fixes for patches 0008/0009 (D34), in 20261027-203953: **first frame**. No NULL writes, no exit; 100-999 guest flips in about 5 s, 1 frame dump (solid black, described below). The harness stops 5 s after the first flip; GT6 is then in its first-run install, calling the unresolved `cellFiberPpuContext*` imports |
| 7 (run 20261027-193740, after the review follow-ups) | GT6 calls `exit(1)` at 2.3 s on its USB driver thread (func_00AADA2C), then the teardown crashes (SIGBUS) | The exit is `Fail: sys_mutex_lock (-2147418107)`: `sys_mutex_lock` answers ESRCH because the mutex id at driver+0x144C (0x01736A2C) reads 0. A watchpoint shows the id is overwritten by GT6's inflater (func_00A5A1B0, called from the file worker via func_00A46FB4), which runs past its static work area at 0x016FF140 into the driver's state; in other runs it writes through a NULL output pointer instead. Alongside: the 16 SPURS job binaries and the `Wws_Job` policy module GT6 runs were dropped, and the job-chain walker made up a completion event per job, which GT6's event-queue worker reads as its own callback index | ruling A, D33, patch 0008: unlifted job binaries and policy modules run in the SPU interpreter (counted per run, `spu:interp:<fp>`), no synthetic job events, images dumped to `<tree>/spu-missed/` and lifted by the next `translate_game.py` (17 found, 17 lifted, all partly). `boot_game.py` reports `spu_interpreted` | run 20261027-195826 (interpreted) and 20261027-200531 (lifted, 0 interpreted runs): no teardown crash; GT6 reaches `cellGcmSetFlipImmediate` (`gcm:flip` key, 0 frame dumps) and then exits cleanly (`sys_process_exit`, exit 0) at 1.9 s on the same USB-mutex failure. The inflater overrun is the next blocker |
| 6 (run 20261027-191305) | SIGBUS (1.9 s) in func_00A8BD40 reading guest 0xD00C9899, past the top of its 16 KB stack (sp 0xD00C7B10), right after unresolved `0x1F71ECBE` and `0xFF0A21B7` | GT6 imports the keyboard read as `cellKbRead` (0xFF0A21B7) and the layout query as `cellKbGetConfiguration` (0x1F71ECBE). ps3recomp has the read only as `cellKbGetData`, whose name hashes to a NID nothing imports, and no configuration call. Both faked CELL_OK without writing their structs, and func_00A8BD40 walked an uninitialised keycode count off the stack | patch 0007: `cellKbRead` (the existing read under the SDK name) and `cellKbGetConfiguration` (RPCS3's checks, layout 101); new `tools/test_kb_read.py` checks both NIDs and the guest structs | run 20261027-191824: keyboard calls answer; the PDIPFS install starts (`.fdupi` renames in `PDIPFS/K`), then a GT6 thread calls `exit()` at 2.3 s (`sys_prx_exitspawn_with_level`), and the teardown crashes (SIGBUS) after `cellSpursDestroyTaskset2` (unresolved). Why it exits is the next blocker |
| 5 (run 20261027-190653) | SIGBUS (1.9 s) on tid 9 inside `ps3_indirect_call_impl`, reading guest 0xD0044000, while it reported `unresolved indirect call -> 0x7FFBA1C0` from func_00A96598 | The report's stack dump and scans read guest memory raw. On macOS a scan up a shallow 16 KB stack runs into the PROT_NONE guard page below the next stack, so the diagnostic itself killed the process. (The bad call is GT6's event-queue-3 dispatcher indexing its callback table with `data2` of a completion event the HLE job chain made up; open, BACKLOG.) | patch 0006: the report reads through `ppu_diag_read32`, which probes each host page once per report and answers 0 for unreadable bytes; new `tools/test_diag_read_guard.py` | run 20261027-191305: the report no longer crashes (and the bad call did not recur in this run); boot runs on to SIGBUS (1.9 s) in func_00A8BD40 after the unresolved `cellKbGetConfiguration`/`cellKbRead` |
| 4 (run 20261027-185857) | SIGBUS (1.7 s); first anomaly a `[null-write]` to 0x55 by func_00A46320 on worker tid 4, and NULL reads by func_00A2A6D4 on tid 5 | ps3recomp's `sys_lwcond_wait` was a 1 ms poll and every `sys_lwcond_signal*` a no-op, so every wait woke spuriously. GT6's event object (func_00A5F3DC) waits once with no predicate loop, so its file workers (loop func_00A45E64) woke with no request posted and used the NULL request at +0x1C2C | patch 0005: a real waiter queue; wait blocks until signalled or timed out, signals wake the oldest / all / the named thread, answers from RPCS3; new `tools/test_lwcond_wakeup.py` | run 20261027-190653: no NULL accesses; boot reaches the first RSX surface clear, pad and keyboard setup and save-file writes; still SIGBUS (1.9 s), now after `unresolved indirect call -> 0x7FFBA1C0` on tid 9; 11 unresolved imports listed |
| 3 (run 20261027-185010) | SIGBUS (1.9 s), EXC_BAD_ACCESS in func_00A5AA84 reading 0xD001C110, 0x110 past the top of a 16 KB worker stack; earlier, 5 unresolved imports, the first that matters `cellFsReadWithOffset` (0x0D5B4A14) right after GT.VOL opens | ps3recomp has no `cellFsReadWithOffset`/`cellFsWriteWithOffset`. The import faked CELL_OK with nothing read, so GT6 parsed zeroed GT.VOL and PDIPFS headers. The harness also missed the runtime's lowercase `[hle] unresolved NID` lines, so `report.json` said 0 unresolved | patch 0004: both as pread/pwrite (seek, transfer, seek back under the stream lock), error answers from RPCS3; cases in `test_fs_aio.cpp`. `boot_game.py` now reads both log forms and the `hle:unresolved:` milestone keys | run 20261027-185857: GT.VOL and `PDIPFS/K/4D` read; boot reaches `cellFsUnlink`, `sys_lwcond_*`; still SIGBUS (1.7 s); unresolved now listed: `0xFAA275A4` |
| 2 (run 20261027-184429) | SIGBUS (1.6 s), same last key; 12 unresolved indirect calls, e.g. `-> 0x00A3FF5C` from func_00A3FEE0, `-> 0x00A6D854` | Switch tables whose base is a constant (`lis r9,hi; addi r9,r9,lo; lwzx; extsw; add; mtctr; bctr`, table inline after the bctr). The lifter only accepted a TOC-loaded base, so the dispatchers were dropped and every case lifted to an unresolved indirect call | patch 0003: `discover_jump_tables` takes a `lis`/`addi` constant as the table base; test `test_constant_table_base` | run 20261027-185010: no unresolved indirect calls at all; still SIGBUS (1.9 s), same last key |
| 1 (run 20261027-183727, Task 5 smoke) | SIGBUS after 0.2 s, last key `hle:cellSysutilRegisterCallback`; the first anomaly is earlier: `unresolved indirect call -> 0x00A8DFF0` from func_00FD7724, then 7 more into 0x00A8Dxxx | GT6's memset (func_00A8DE98) enters its unrolled `stb`/`std` runs with `lis/addi rC; subf rC,rOff,rC; mtctr; bctr` (the run's end minus the length). The lifter only knew the additive form, so all three bctrs lifted to unresolved indirect calls and short memsets stored nothing (static constructors left objects unzeroed) | patch 0002: `_const_base_targets` accepts `subf`, landing sites from the base back to the dispatching bctr; test `test_const_base_subtracted` | run 20261027-184429: memset calls resolve; still SIGBUS (1.6 s), same last key; 12 unresolved indirect calls left, other addresses |

## First presented frame (2026-10-27)

Runs 20261027-202305 and 20261027-202348 (fresh play folder each): `report.json` `outcome`
`first_frame`, `frames` 1. 100 to 999 guest flips are counted by the time the harness stops
the game, 5 s after the first one (runs of 6.8 s and 5.4 s). The process was still running.

- The dumped frame (`frames/frame.ppm`, 1440 x 1080, the latest frame the Metal backend
  dumped) is **solid black**: every one of its 4,665,600 colour bytes is 0. Viewed as PNG in a
  scratch folder, not kept.
- What GT6 is doing at that point: the first-run PDIPFS install (`.fdupm`/`.fdupi` files in
  `PDIPFS/K`, renames, `cellFsGetFreeSize`) while it flips. Under RPCS3 the same install ran
  for more than 300 s; what the screen shows meanwhile was not recorded, so compare the next
  dumps against an RPCS3 capture. A black dump cannot tell "cleared to black" from "nothing
  drawn" yet.
- The last milestones are three unresolved `cellFiber` imports
  (`_cellFiberPpuContextAttributeInitialize`, `cellFiberPpuContextInitialize`,
  `cellFiberPpuContextRun`), which fake CELL_OK. They are the likely next blocker.

## Long runs (2026-10-27)

**Answer to milestone 2's question: the black screen is drawn, not just left empty, but what
is drawn comes out black.** Every frame GT6 presents after its first few has one clear and one
draw call, and every pixel of every dumped frame is exactly zero.

Run 20261027-234511, on a fresh play folder (`prepare_play.py --force`), after re-translating
and rebuilding with patch 0010: `boot_game.py "$GT6_TREE" --until time --seconds 240 --png`.

- Outcome `timeout` after 240.2 s: no crash, no exit, still running when the harness stopped
  it. 14,851 frames presented (about 62 a second). 248 frames dumped (present 1 and every
  60th), 1.3 GB; the dump caps were not reached (`dump_stopped` null).
- `drawn_frames` **0**, `first_drawn` **null**. That is not because nothing was drawn: 247 of
  the 248 dumped frames had a draw call (only present 1 had none). It is because no dumped frame
  has a single non-black pixel (`nonzero_share` 0.0 in all 248).
- Draw statistics over all 14,851 presents: 14,830 draw calls and 14,830 clears. 14,747
  presents had exactly one draw and one clear (a few had two of each); 104 had no draw, all of
  them in the first 20 or so presents.
- Three frames viewed as PNG: present 1 (1280 x 720), present 7200 (1440 x 1080, two
  minutes in) and present 14820 (1536 x 1408, the last dumped). All three are a plain black
  rectangle, with no shape, text, gradient or noise anywhere.
- The presented picture changes size during the run: 1280 x 720 for present 1, 1440 x 1080
  from present 60, 1536 x 1408 from present 8040 (about 2 minutes in) to the end. 1536 x 1408
  is the size of the surface the engine met at RSX offset 0x00CC0000, an odd size for a
  display buffer. So the port may be presenting a surface other than the one the game flips.
  This is a lead for the bring-up rounds, not checked yet.
- What the one draw is. A 40 s diagnostic run (20261027-235022, with
  `PS3RECOMP_METAL_SHADER_DUMP` into `$GT6_TREE/shader-dump`) shows GT6 uses one shader pair
  the whole time. The vertex program multiplies the position by a 4 x 4 matrix from its
  constants, and passes vertex attribute 3 through as texture coordinate 0. The fragment
  program outputs that value as the colour, with no texture. So each frame is a clear plus one
  flat-coloured shape whose colour comes from the vertex data: the shape of a full-screen fade
  or loading cover. A black result fits a black fade during the first-run install. It also
  fits wrong vertex data, a zero matrix (the shape then covers nothing, and the black clear
  shows), or the size switch above. The RPCS3 capture of the same moment (milestone 3, task 2)
  tells which.
- The game's progress looks the same as in milestone 2: the last new calls are still the three
  faked `cellFiberPpuContext*` imports, then `cellFsGetFreeSize` (12 unresolved imports, one
  stubbed system call, 327).

## PPU fiber contexts (2026-10-28)

**With the fiber calls implemented (patch 0011, D36), GT6 shows its first picture: "Sony
Computer Entertainment presents", grey on black.** It then stays on that screen, because the
job its fiber runs deadlocks with the main thread (below).

**How GT6 uses fibers.** EMAIN imports six `cellFiber` calls: `_cellFiberPpuInitialize`,
`_cellFiberPpuContextAttributeInitialize`, `cellFiberPpuContextInitialize`,
`cellFiberPpuContextRun`, `cellFiberPpuContextReturnToThread` and
`cellFiberPpuContextFinalize` (NIDs in `recomp/loader/EMAIN.SELF.imports.json`). It imports
no scheduler call (`cellFiberPpuCreateFiber`, `RunFibers` and so on) and no `Switch` or `Self`.
The calls sit in one small coroutine class (func_00A6CADC to func_00A6D018):
- Its init (func_00A6CD88) names the attribute, then calls Initialize with entry OPD 0x015A1498
  (func_00A6CADC), the object as the argument, and a guest stack the object owns. In the run
  below: context 0x7FEEFA90, stack 0x72198000 + 0x10000 (64 KB).
- Its step (func_00A6CEE8) puts the object in a TLS slot (r13 - 0x6FF4), calls
  `Run(context, &cause, NULL, NULL)`, and clears the slot. So the context must see the calling
  thread's r13.
- The entry (func_00A6C9FC) calls the job function at object+0x28 once, then loops: poll
  (func_00A4F9FC), then the virtual at vtable+0x18 (func_00A6CD64,
  `ReturnToThread(0)`), until a state word reads 1; then it sets the state to 2 and yields for
  ever. It never returns. Finalize is in the destructor (func_00A6CAF0, func_00A6D018), on a
  suspended context.
- So GT6 only runs and returns to the thread; it never switches between contexts. While Run was
  faked it called Run 1k-9k times in 40 s (run 20261027-235022), about once a frame. Under
  patch 0011 it called Run once, and the context has not returned yet.

RPCS3 has stubs only for these calls (argument checks, then CELL_OK; `cellFiber.cpp`), and
its reference runs load Sony's `libfiber` from firmware instead, so its log shows no calls.

**Run 20261028-011330**, on a fresh play folder after re-translating and rebuilding with
patch 0011: `boot_game.py "$GT6_TREE" --until time --seconds 300 --png`.
- Outcome `timeout` after 300.2 s, no crash; 18,659 presents (about 62 a second); 300 frames
  dumped (the cap, reached at present 17,940).
- The fiber calls are in the milestone log and none are unresolved:
  `hle:_cellFiberPpuContextAttributeInitialize`, `hle:cellFiberPpuContextInitialize`,
  `hle:cellFsGetFreeSize`, `hle:cellFiberPpuContextRun` (count 1 each), then a new call,
  `hle:sys_lwmutex_trylock`. Unresolved imports are down from 12 to 9.
- **The screen.** From present 60 every frame has 12 to 19 draw calls and 2 clears (before
  patch 0011: one draw and one clear, all black). Present 60 shows "Sony Computer
  Entertainment / presents" fading in; presents 120 to 17,940 show it fully, grey on black,
  identical to the end (`nonzero_share` 0.0049 in all of them). The text is centred about
  x = 640 of the 1440-pixel-wide frame, so it is laid out for 1280 x 720 (the presented-size
  question in "Long runs"). `drawn_frames` is 0 only because the text covers under 1% of
  the pixels. RPCS3 shows the legal text and GT6's "Installing..." dialog at this point
  (13 s); the splash was not in its 10 s screenshots.
- The install did not get far: 24 files opened after the fiber started (the open log is not
  capped), then none. It did
  not reach "Installation complete." (Task 5's dialog).

**The new blocker: a lock-order deadlock between the main thread and the fiber's job.**
A host `sample` of a second run (20261028-012030, 50 s in) and a run with every contended
lwmutex logged (20261028-012412, diagnostic build, since reverted):
- The thread that called Run (guest thread 26, `9qstY`, in run 20261028-012412; thread ids
  vary between runs) is blocked in `cellFiberPpuContextRun`, as it should be while its
  context runs.
- The context, on its own host thread with guest thread id 26, runs the job (func_005A6CA8,
  func_005A6894 and on through the resource code). It is blocked in `sys_lwmutex_lock` on
  0x01765788, owned by thread 1, from func_00841978: a one-time static initialiser (guard byte
  at 0x01680258) that registers its destructor (func_00BD3FCC -> func_00BD3E6C), which takes
  lock 1 of the C library's lock table (func_00BDC2D4 -> func_00BDD694).
- Thread 1, GT6's main thread, holds that lock while it waits in `sys_lwcond_wait` on GT6's
  event object (func_00A5F3DC, from func_005A7FA4 via func_00735DC4). Every other guest thread
  is idle in an event queue, a condition or a sleep.
- The fiber's identity is correct: the context has thread 26's id, and the lwmutex's owner
  stamp 1 was written by thread 1, so the lock is genuinely held by another thread. Whether the
  console ever reaches this order is unknown; the likely cause is ordering or timing (an
  earlier call path that differs, or a wait that ends sooner on the console). That is the next
  bring-up round (BACKLOG).

**Test evidence for patch 0011** (`tools/test_cellfiber_ppu.py`): a Run plus ReturnToThread
round trip takes 5.6 µs and a Switch A -> B -> A 5.1 µs on the M4 Max (20,000 of each).

## Import audit and the menu-path imports (2026-10-28)

**Every import GT6 calls on its way to the menu now has a real handler; the boot still stops on
the same deadlock.** `scripts/audit_imports.py "$GT6_TREE" --runs` reads EMAIN's import table and
ps3recomp's two registration paths (the table `gen_hle_nids.py --all` writes, and the runtime's
own `ps3_hle_register_ctx`/`_fast` calls), and counts each import's calls in every run's
milestone log.

| | Before (patches 0001-0011) | After (0001-0017) |
|---|---|---|
| EMAIN imports | 740 | 740 |
| Handled | 437 | 460 |
| Unhandled | 303 | 280 |
| Unhandled and called in a run (30 runs) | 10 | 0 |
| Unhandled and called by the RPCS3 reference run (`calls.txt`) | 4 | 0 |

- The 10 called: the 9 still unresolved in run 20261028-011330 plus `cellSpursDestroyTaskset2`
  (called only in the old runs that exited). The RPCS3 reference adds `cellMusicInitialize2`,
  `cellMusicSetVolume2` and `sceNpTrophySetSoundLevel` (with `cellVideoOutGetScreenSize`).
- Miscount guards: 3 NIDs are registered under two names (`netInitializeNetworkEx` /
  `sys_net_initialize_network_ex`, `netFinalizeNetwork` / `sys_net_finalize_network`,
  `_sys_spu_image_import` / `sys_spu_image_import`; the first registration runs) and 15 literal
  NIDs carry a label that is not their name (the PSL1GHT `net*`/`sys_net_bnet_*` labels in
  `ppu_sysprx.cpp`). None is on GT6's path. The ctx table holds 85 of its 256 slots. The built
  `ppu_hle_nids.cpp` matches the audit's reading of `libs/**` once rebuilt. 16 NIDs logged
  unresolved in older runs are handled now (patches 0007, 0011 and this task).
- Patches 0012-0017, one per library: `cellVideoOutGetScreenSize` (VALUE_IS_NOT_SET, as RPCS3),
  the SPURS workload flag, `cellSpursInitializeWithAttribute2` and `cellSpursDestroyTaskset2`,
  the `cellUsbd` extra LDDs (no device attached), `sys_mempool_*` and `sys_prx_get_module_list`
  (empty: no PRX is loaded), the `cellMusic*2` player (no music library) and
  `sceNpTrophySetSoundLevel`.

**Boot, run 20261028-021830** (`--until time --seconds 300 --png`, fresh play folder):
- `timeout` after 300.1 s, no crash, flips, 300 frames dumped (cap), `unresolved_nids` empty.
  The one unimplemented system call is still 327 (`sys_mmapper_enable_page_fault_notification`).
- The new calls run: `cellVideoOutGetScreenSize` (once), `cellSpursInitializeWithAttribute2`
  (a second SPURS instance at 0x01682E00, 1 SPU, now with a kernel), `sys_mempool_create`,
  `sys_prx_get_module_list`, and 8 USB drivers registered (two Logitech force-feedback
  ranges, five Thrustmaster wheels and an "Oculus" entry), none probed (no device attached).
- **The screen is unchanged:** "Sony Computer Entertainment / presents" fades in by present 60
  and stays to the last dump (present 17,940; 17 draws and 2 clears per frame).
- **The deadlock persists.** A host `sample` 50 s into a second run: the context's host thread is
  in `sys_lwmutex_lock` from func_00841978, the thread that called Run waits in
  `cellFiberPpuContextRun`, and the main thread waits in `sys_lwcond_wait` from func_00A5F3DC
  (via func_005A7FA4 and func_00735DC4), as in run 20261028-012412.
- **The workload flag is not the main thread's event.** GT6 takes the flag's address
  (func_00BB35xx, right after `_cellSpursWorkloadFlagReceiver2`), converts it to an RSX I/O
  offset with its own copy of the GCM address table (func_00BBB8E0) and stores it (0x0173E468),
  apparently for the GPU to release the flag and wake the GPU-sync workload. With the faked call
  that offset came from an unwritten stack slot.
- **The first boot with these patches hung earlier** (run 20261028-020741): no flip, stuck right
  after `cellSpursGetWorkloadFlag`. The SPURS kernel reset the flag with `vm_write32` while
  holding the lock-line lock, and `vm_write32` takes that lock again when an SPU holds a
  reservation on the line. Fixed in patch 0013 (plain stores), with a test that holds the
  reservation and hung before the fix.

## RPCS3 reference: boot to the first menu (2026-10-28)

**RPCS3 did not reach the first menu either.** It ran the first-run install to the end. After
the player confirms it, the next boot stops at a fatal GT6 message: "Insufficient free space
on Hard Disk Drive (HDD). At least 32MB required. 0x0000000b [68]". So there is a reference for
the install screens, but none yet for the menu.

**The main comparison: our port shows black where RPCS3 already shows the install screen.**
At 0-3 minutes, RPCS3 shows the dimmed legal text with GT6's own "Installing..." dialog and
progress bar. Our port draws one flat black full-screen quad per frame. RPCS3's display buffers
stay 1280 x 720 the whole time; the port's presented size of 1440 x 1080, then 1536 x 1408,
is not a display-buffer size.

Run outputs are in `$GT6_TREE/reference/rpcs3-20261028-000710/`: `timeline.md`,
`first-run-install.png`, `post-install-error.png`, `calls.txt`, the syscall lists and one folder
per launch. RPCS3 0.0.43-20410 ran with firmware 4.50 on a fresh APFS clone of the verified
`dev_hdd0/game/BCES01977`, as in the section below. It used a copy of the owner's config with
every Cell log channel at Trace, in a window. The window was screenshotted every 10 s.
RPCS3's log was read in place, and only through a filter that drops any line with 32 or more
hex digits (once separators and `0x` are removed) or a key word. The log was deleted afterwards.

**Timeline** (seconds from launch; full detail in `timeline.md`):

- **Launch A**, pristine clone with cold caches. RPCS3 compiled for 72 s, then the EBOOT ran
  and spawned EMAIN. RPCS3 compiled EMAIN until 145 s. At 149 s, after setting up SPURS,
  EMAIN's main thread waited on a SPURS event that never came, and the screen stayed black. It
  was stopped at 740 s. FINDINGS run 1 (below) saw the same thing on a cold first boot.
- **Launch B**, the first-run install, with warm caches.
  - From 2 to 11 s RPCS3 built its SPU cache.
  - **The first non-black screen came at about 13 s.** It shows the legal text, dimmed, behind
    a dialog that GT6 draws itself (it is not the system message dialog). The dialog reads
    "Please wait... / Installing... / Please do not switch off the system while the HDD access
    indicator is flashing." It has a progress bar, an "Approx. N mins. left" line, a greyed OK
    button and a "Close" hint.
  - The install began at 13.8 s and **finished between 430 and 440 s**, after about 7 minutes.
    The dialog then read "Installation complete. / Done", with the OK button active.
  - **One button press was needed: Cross** (the X key on RPCS3's default keyboard pad).
    Enter, which RPCS3 maps to Start, did nothing.
  - EMAIN then shut down its input, audio and network, and exit-spawned `EMAIN.SELF` again.
    The new process was compiled fresh and stalled the same way as launch A, so it was stopped
    at 1440 s.
- **Launch C**, the boot after the install.
  - The EBOOT found no `TPPS-01.07/update.txt` this time (the install removes it).
  - EMAIN ran `cellSaveDataAutoLoad2` for `BCJS37016-GAME6` and `BCJS37016-BKUP6`. There is no
    save yet, so the status callback returned -4.
  - EMAIN registered trophy context NPWR04712, then created `USRDIR/db/userdb0101.dat` (8 MB)
    and `/dev_hdd1/game024.db`.
  - **At 14.6 s it opened the fatal error dialog** (type 0x80: an error with no buttons that
    cannot be cancelled), over a faint "Sony Computer Entertainment" logo. Pressing X or Enter
    did nothing.
  - RPCS3 reports 40 GB free to every free-space query, so this message stands for some other
    failure, which this run did not find. RPCS3's compatibility list rates GT6 "Ingame" and
    advises against updates past 1.05.
- No intro movie or title screen was reached, because none comes before this point.

**Display.**
- The EBOOT sets 2 display buffers of 1280 x 720 with pitch 5120.
- EMAIN sets 3 display buffers of 1280 x 720 with pitch 6144, at RSX offsets 0, 0x660000 and
  0xcc0000. 6144 is 1536 x 4, so the port's 1536-wide surface at 0xcc0000 is probably EMAIN's
  third display buffer, sized from its pitch rather than its width. That is a lead for the
  bring-up loop, not yet checked.
- Video out is configured for 720p (resolutionId 2), the only mode this RPCS3 config offers.

**Calls before the error.**
- `calls.txt` lists 93 distinct HLE function names, from launches B and C.
- In this RPCS3 setup, GT6 itself loads libgcm_sys, libsre (SPURS), libfiber, libfs, libnet,
  libssl, libhttp, libusbd and libkey2char from `dev_flash`, and RPCS3 runs liblv2 as firmware
  code. Calls into those libraries are not logged by name; only the lv2 syscalls they make
  are. Those are listed in `syscalls-all.txt` (118); `syscalls-from-game.txt` (82) has the
  ones made from GT6's own code.
- Compared with the 12 imports the port fakes (BACKLOG), Task 4's audit script not being
  written yet:
  - `cellVideoOutGetScreenSize` is called, and **RPCS3 answers
    `CELL_VIDEO_OUT_ERROR_VALUE_IS_NOT_SET` (0x8002b228), not CELL_OK**. The port's faked
    success is therefore wrong for an ordinary TV setup.
  - The other 11 live in libraries that run as firmware code here, so they are not logged by
    name. Their use is visible from the syscalls instead:
    - SPURS (libsre) creates SPU thread groups and starts and joins them 138,825 times during
      the install.
    - `sys_prx_get_module_list` reaches its syscall `_sys_prx_get_module_list` (6 calls).
    - the `cellUsbd*Ldd` calls reach `sys_usbd_register_extra_ldd` (8 calls) and
      `sys_usbd_unregister_extra_ldd`.
    - fibers and `sys_mempool_create` make no syscall of their own.
- Other calls on the path that later tasks must answer correctly:
  - `cellNetCtlAddHandler`, `cellAudioOutGetDeviceInfo`, `cellMusicInitialize2` and
    `sceNpTrophySetSoundLevel` are RPCS3 TODO stubs.
  - `cellNetCtlGetInfo` returns `CELL_NET_CTL_ERROR_NOT_CONNECTED`.
  - `cellSaveDataAutoLoad2` returns `CELL_SAVEDATA_ERROR_CBRESULT` when there is no save.
  - `cellGameDataCheck` is called for `BCES01893` (absent) and for `BCES01977`.

**RPCS3's state afterwards.**
- RPCS3's `dev_hdd0/game/BCES01977` is now this post-install copy (12 GB on disk, mostly
  clone-shared). Nothing was there before this run, and no GT6 save existed.
- The run also added a trophy folder (NPWR04712_00) and `dev_hdd1/caches/BCES01977_BCES01977`.
- `games.yml` was pointed at `$GT6_TREE/dev_bdvd` for the run and then restored. The SHA-256
  of `config.yml` and `games.yml` match the values taken before the run.
- RPCS3's GT6 playtime grew from 946,248 ms to 3,572,157 ms, about 44 minutes added.

**How to put RPCS3 back** to its state before this run. Quit RPCS3 first. Paths are under
`~/Library/Application Support/rpcs3/` unless they start with `~`.

1. Delete everything this run added:
   - `dev_hdd0/game/BCES01977` (the post-install game folder);
   - `dev_hdd0/game/＄locks/BCES01977_v01.00` (a 0-byte lock marker; the `＄locks` folder
     existed before);
   - `dev_hdd0/home/00000001/trophy/NPWR04712_00`;
   - `dev_hdd1/caches/BCES01977_BCES01977`;
   - `~/Library/Caches/rpcs3/cache/BCES01977` (GT6's PPU and SPU caches). The other `cache/`
     entries are firmware caches that existed before the run, and `ppu_progs` and `spu_progs`
     are still empty, so this run created nothing else there.
2. Restore the playtime: copy
   `$GT6_TREE/reference/rpcs3-save-backup-20261028-000710/persistent_settings.dat.before` over
   `GuiConfigs/persistent_settings.dat`.
3. `games.yml` and `config.yml` need nothing. `games.yml` was restored from `games.yml.orig` in
   the same folder, and `sha256-before.txt` there holds the hashes to check both files against.

## Where GT6's run-time SPU images come from (2026-10-27)

The SPU images GT6 runs that the translate step did not find (D33) were dumped by the runtime on
first use (`SPU_DUMP_MISS`, run 20261027-195826) and then searched for in the decrypted
`EMAIN.SELF.elf`. All 17 are there byte for byte, in the first PT_LOAD segment (read-only and
executable, file offset = VA - 0x10000), above the PPU code end 0x101BEA0. They are not built at
run time and not loaded from GT.VOL.

| Kind | Count | VA range | Sizes |
|---|---|---|---|
| SPURS job binaries (`soc-job` chains, entered at LS 0) | 16 | 0x0134B700 to 0x014C0F00 | 9,488 to 72,464 B |
| `Wws_Job` policy module (5 workloads `ElemSetRenderHP`, `ElemSetRender`, `ElemSetUpdate`, ..., entered at LS 0xA00) | 1 | 0x01468200 | 12,160 B |

- None has the job-module header `map_game.find_embedded_jobmods` looks for (no `C0DEC0DE` at
  +0x20); they are plain job binaries linked against the SDK's job CRT, so the static scan
  misses them. The job descriptors' `eaBinary` points straight at them.
- ps3recomp's image fingerprint is FNV-1a 64 with offset basis 1469598103934665603, one digit
  short of the standard basis; `translate_game.py` matches it.
- Lifted with `spu_lifter --auto-functions` at their link base, all 17 lift partly (4 to 1,258
  unsupported words each, data decoded as code); the bad words fall to the interpreter.
- With them running, interpreted or lifted, the job chains no longer get made-up completions,
  and no `[spu-evt]` user event reached an unbound port in these runs.

## What the 1.22 EBOOT leaves on disk, and how EMAIN is launched (2026-10-27)

**Verdict: EMAIN needs what the EBOOT changes.** The EBOOT rewrites 6 small files in the
`TPPS-01.07` to `TPPS-01.11` folders. EMAIN's first run reads exactly those files and uses them
to decide which update data it installs. Started without them, EMAIN skips the 1.07 data
patch (971 MB) completely.

**Reproduced exactly.** `scripts/prepare_play.py <tree>` clones `<tree>/dev_hdd0` to
`<tree>/play/dev_hdd0` (APFS clone, 2.6 s, no extra space) and applies the EBOOT's changes
there, using the rule decoded from 0x1143c (below). The resulting `play/dev_hdd0/game/BCES01977`
is byte-identical to the folder the real EBOOT left under RPCS3: `eboot_effects.py diff` of
the two snapshots shows nothing added, removed or changed (21,653 entries). The SHA-256 of the
6 files are pinned in `tests/scripts/test_prepare_play.py`, which checks them when `GT6_TREE`
is set. The port runs on the play folder; the verified tree is never run (D32).
- `prepare_play.py` builds the folder in `<tree>/.play.staging` and writes `prepare.json`
  last, then renames the folder into place. An interrupted run leaves no half-prepared
  folder.
- `--force` replaces only a folder holding this tool's `prepare.json`, and never the tree or a
  folder that contains it.
- The port refuses a `/dev_hdd0` folder that has no `prepare.json` beside it. For the default
  that is `<tree>/play/prepare.json`; for a `PS3_HDD0_ROOT` override it is
  `$PS3_HDD0_ROOT/../prepare.json`.

Measured with RPCS3 0.0.43-20410 (official build, firmware 4.50) on an APFS clone (`cp -c -R`)
of the verified `dev_hdd0/game/BCES01977`, installed as RPCS3's `dev_hdd0/game/BCES01977`,
with `games.yml` pointing BCES01977's disc at the built `dev_bdvd`. `sys_fs` and `sys_process`
were logged at Trace through `--config` (a copy of the owner's config, so `config.yml` was
never edited). Snapshots and diffs come from `scripts/eboot_effects.py` (SHA-256 of every file,
plus every folder). Run outputs are in `<tree>/runs/eboot-effects/`. RPCS3's log holds the
klicensee, so only non-key lines of it are quoted here.

| Run | Boot | Time | Result |
|---|---|---|---|
| 1 | `USRDIR/EBOOT.BIN`, pristine clone | EBOOT reached the spawn at 76 s (it compiled PPU caches first); EMAIN ran 150 s more, but its own PPU cache compile took about 108 s, so it executed for about 40 s | the EBOOT's changes (below); EMAIN made no further change in the folder |
| 2 | `USRDIR/EBOOT.BIN` again, on run 1's result | spawn at 2 s (cached); EMAIN ran 300 s | the EBOOT changed nothing this time; EMAIN began its data install (below) |
| 3 | `USRDIR/EMAIN.SELF` directly, pristine clone | RPCS3 refused: "Failed to decrypt SELF" (the klicensee only reaches RPCS3 through the EBOOT's spawn) | none |
| 3b | the decrypted EMAIN ELF, saved as `USRDIR/EMAIN.SELF` in a pristine clone (the port's case) | about 108 s PPU compile, then about 190 s of EMAIN | EMAIN skipped `TPPS-01.07` (below) |

**What the EBOOT changes** (run 1 diff: nothing added, nothing removed, 6 files changed;
the order is from the log):

1. `USRDIR/TPPS-01.07/update.txt`: `01.06 01.07` becomes `99.98 99.99` (opened write+truncate).
2. For each of `TPPS-01.07`, `01.08`, `01.09`, `01.10`, `01.11` (the versions that have a
   `USRDIR/UPDATENODEINFO/UPDATENODEINFO.01xx`): it reads `TPPS-01.xx/PDIPFS/UPDATENODEINFO`,
   `TPPS-01.xx/PDIPFS/K/4D` and `UPDATENODEINFO.01xx`, checks the size of 6 files in the main
   `USRDIR/PDIPFS/9/...`, writes `TPPS-01.xx/PDIPFS/UPDATENODEINFO.upd`, deletes
   `UPDATENODEINFO` and renames the `.upd` over it.
   - The node-info files are text, one entry per line. The installed `TPPS` copies have 7
     columns; the `USRDIR/UPDATENODEINFO/*.01xx` copies and the results have 8.
   - For 01.07, 01.08, 01.10 and 01.11 the result is byte-identical to
     `UPDATENODEINFO.01xx`. For 01.09 it differs from `UPDATENODEINFO.0109` in one entry
     (line 440 of 581): its last column is the entry's own size (column 2) instead of the value
     in `.0109`. The decoded rule below explains it.
   - `TPPS-01.12` to `01.22` are read (`UPDATENODEINFO` and `K/4D`) but not changed. There is
     no `UPDATENODEINFO.0112` or later, and their `update.txt` already reads `99.98 99.99`.
3. Nothing else: no `FIXEDELF114` swap (as predicted below), and no change outside
   `TPPS-01.07` to `TPPS-01.11`. On a second boot the EBOOT changes nothing.

**The node-info rule** (decoded from 0x1143c and its helpers, in `prepare_play.py`):

- A version `TPPS-MM.mm` is processed when `TPPS-MM.mm/PDIPFS/UPDATENODEINFO`,
  `TPPS-MM.mm/PDIPFS/K/4D` and `USRDIR/UPDATENODEINFO/UPDATENODEINFO.MMmm` exist and the two
  node-info files have the same number of entries (0x11b00).
  - The EBOOT also reads `K/4D` and compares something from it before the merge (0x161ac,
    0x32b88). That check is not decoded. It passed for all five versions, and
    `prepare.json` notes it.
- An entry is `id size type ref hash flag size7 size8`. It is written with
  `%06d %010llu %1d %06d %s %1d %010llu %010llu` (va 0x3ed28), the hash as 16 bytes of `%02x`.
  A 7-column entry's missing `size8` equals `size7`.
- The merge walks the TPPS entries in order while it is still checking:
  - The `.MMmm` entry with the same id replaces the TPPS entry.
  - The EBOOT stats the main `USRDIR/PDIPFS/<name>`. If that file exists and its size equals
    the entry's `size` or `size8`, it is already installed and the entry is dropped.
  - Checking stops once 6 entries have been kept (0x11fe0). Every later entry stays as the
    TPPS copy.
  - That is why 1.09's entry 440 keeps `size8 = size7`. The other 4 versions have no entry
    whose `size8` differs, and none of the 30 checked entries was dropped.
- `<name>` comes from the node id (0x169a4).
  - Each id range has a prefix, a Galois-field polynomial and a digit count: below 0x400 `K`,
    0x499, 10 bits, 2 digits; then `5`, 0x8891, 15, 3; `9`, 0x111889, 20, 4; `W`, 0x2242211,
    25, 5; `4`, 0x88891111, 31, 6.
  - The id minus the range start is shifted left once per bit, XOR-ing the polynomial each
    time the top bit appears (0x1659c).
  - The result is written in base 36 over the alphabet `K59W4S6H7DOVJPERUQMT8BAIC2YLG30Z1FNX`
    (va 0x3d110), most significant digit first, with a `/` before each pair of digits
    (0x168b0).
  - So 1 gives `K/4D`, and 42258 to 42263 give the 6 names the EBOOT stats for 1.09
    (`9/JF/OC` ... `9/QD/OS`).

**What EMAIN does with them.** On its first run EMAIN installs the staged update data itself.
It stats `USRDIR/update.txt`, lists `USRDIR`, then reads every `TPPS-01.xx/update.txt` and
`TPPS-01.xx/PDIPFS/UPDATENODEINFO` in order. It then moves (rename) or patches (bsdiff, with
`.bsdiff`, `.fdupm` and `.fdupi` temporaries) each staged file into the main `USRDIR/PDIPFS` and
deletes the staged copy. It also creates `USRDIR/PDIPFS_bdmark/` and RPCS3's per-game
`dev_hdd1` cache (`/dev_hdd1/pditsm`, `/dev_hdd1/PDIPFS/...`). After 300 s in run 2 it had
removed 4,396 staged files from `TPPS-01.07` to `01.12` and added 6,972 files under `PDIPFS`
and `PDIPFS_bdmark`, and was still working inside `TPPS-01.12`. The full install takes longer
than 5 minutes under RPCS3.

- **With the EBOOT's changes** (run 2), `TPPS-01.07/update.txt` is followed by
  `TPPS-01.07/PDIPFS/UPDATENODEINFO`, and EMAIN installs 01.07's files.
- **Without them** (run 3b), EMAIN reads `TPPS-01.07/update.txt` (`01.06 01.07`), never opens
  `TPPS-01.07/PDIPFS/UPDATENODEINFO`, and goes straight to `TPPS-01.08`. The first 309
  file-system calls of both runs are identical; this is where they part.
- So `update.txt` reads as "from to": `01.06 01.07` is a step that needs 1.06 data, and
  `99.98 99.99` marks a step that always applies. The node-info rewrite feeds the same
  install; whether EMAIN would install `TPPS-01.08` to `01.11` correctly from the old 7-column
  files was not measured.
- EMAIN deletes staged files with a path that has **no leading slash**
  (`dev_hdd0/game/BCES01977/USRDIR/TPPS-01.xx/PDIPFS/...`, 6,933 `sys_fs_unlink` calls in
  run 2). RPCS3 accepts it and the files go. **The port's file layer must accept it too
  (Task 6):** map `dev_hdd0/...` like `/dev_hdd0/...`.
- EMAIN holds the same strings (`TPPS-%02d.%02d`, `UPDATENODEINFO`, `update.txt`) and the
  `PDIPFSStoragePatchHddGame` / `PDIPFSPatchInstaller` classes. The installer is EMAIN's own
  code, so the port runs it natively; only the EBOOT's prior rewrite is missing.
- **The install changes the game folder.** That is why the port runs on `<tree>/play` (D32).
  After the first launch the play folder no longer matches `manifests/BCES01977-v1.22.json`.
  The verified tree still does. `prepare_play.py --force` makes a fresh play folder.

**The launch contract** (run 1; RPCS3 lines quoted from `sys_process`, which logs the
arguments `_sys_process_exit2` receives):

- The EBOOT spawns through `sceNpDrmProcessExitSpawn2` (the DRM branch, not
  `sys_game_process_exitspawn2`), with `path` = the static buffer at 0x52a10, a non-null
  `argv`, `envp` = NULL, no data block (`data_size` 0), `prio` 1001 and `flags` 0x40.
- Process path: `/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF` (RPCS3: `Process finished ->
  /dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF`, then the same `Elf path` for the new boot).
- **argv** (argc = 2): `argv[0]` = `/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF`,
  `argv[1]` = `/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF`. RPCS3 logged
  `*** arg: “/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF”` twice: the spawn puts the path
  first, then the EBOOT's one-entry `argv`, which is the path again.
- **envp**: empty (no `*** env:` line). No exit-spawn data block.
- The disc stays mounted at `/dev_bdvd` across the spawn (EMAIN opens
  `/dev_bdvd/PS3_GAME/USRDIR/GT.VOL` first), and the game folder is
  `/dev_hdd0/game/BCES01977/`.
- Booted directly (run 3b), RPCS3 gives EMAIN argc = 1 (the path only). EMAIN behaved the
  same up to the `TPPS-01.07` decision above, so argc 1 or 2 made no visible difference there.
  The port follows the contract (argc = 2). `port/main.cpp` sets `PS3_BOOT_PATH` and
  `PS3_ARGV` to the EMAIN path, unless the caller has set them. From those, ps3recomp's
  `ppu_run` builds the entry's argc, argv and empty envp in lv2's layout. Without this, the
  guest's `argv[0]` was ps3recomp's default, `/dev_bdvd/PS3_GAME/USRDIR/EBOOT.BIN`. The port
  prints `[boot] guest argv: argc=2 ...; envp empty` at start, and the real port test checks
  that line.

## Building the port (2026-10-27)

`port/` builds the native `gt6` executable from the translated tree (M4 Max, Apple clang 21,
CMake 4.4.4, Ninja 1.13.2):

| Step | Result |
|---|---|
| Configure (`-DGT6_BUILD_PORT=ON -DCMAKE_BUILD_TYPE=Release`, fresh folder) | 1.2 s, including the patch step and the SHA-256 of EMAIN |
| Full build of `gt6` (295 steps: 65 lifted PPU chunks, 58 SPU images, the ps3recomp runtime, the HLE NID table) | **78 s wall**, 1,025 s CPU, peak 1.19 GB per compiler process, 0 errors |
| `gt6` | 205 MB Mach-O arm64; with no arguments prints `usage: gt6 <path to EMAIN.SELF.elf>` and exits 2 |

- Dev dependencies installed with `brew install sdl2 spirv-cross` (D29): `sdl2` now
  installs **sdl2-compat 2.32.74**, the SDL2 API over **SDL3 3.4.18**; **spirv-cross
  1.4.363.0**. Already present: glslang 16.6.0. ps3recomp's configure reports "guest programs
  translated to MSL" (glslang plus spirv-cross found), so the Metal backend can run guest
  shaders, not only fixed function.
- `gt6` links Homebrew dylibs (SDL2, glslang, SPIRV-Tools) by absolute `/opt/homebrew`
  path, so it runs only on a Mac with them installed (BACKLOG, Mac GUI).
- The linker warns that Homebrew's static spirv-cross objects were built for macOS 27.0 while
  the link targets 26.5 (CMake's default deployment target). Harmless on this Mac; a player
  build must pin one deployment target for everything it bundles.
- 63 compiler warnings, all in ps3recomp's runtime (unused variables, format widths,
  deprecated `swapcontext`), none in the port's own files. No ps3recomp fix was needed to
  build on macOS beyond patch 0001.
- Optimisation levels as built (D30): lifted PPU chunks end their command line with `-O1`,
  SPU images with `-O2`, after the Release `-O3`; the runtime is at `-O3`.
- SPU images compiled: 1 of the 4 SPU programs (the only one the inventory marks
  `registered`) and all 57 job modules (`lift_jobmods` registers all of them, including the
  8 with unsupported words, whose bad words fall to the interpreter). The 3 unregistered
  programs are not compiled; they run in the SPU interpreter.
- `recomp/spu/sources.cmake`, written by `build_spu_workloads`, lists paths inside the
  translate step's `recomp.staging` folder, which no longer exists after the swap. The port
  does not use it (it reads `inventory.json` and `jobmods_manifest.json` instead).
- Patch 0001 (`gcm:flip` milestone) touches the 13 unit tests that `#include
  "../cellGcmSys.c"`: without an empty `ps3_ms` stub 8 of ps3recomp's `tools/test_gcm_*.py`
  stop linking. With the patch all 12 `test_gcm_*.py` and `test_milestone.py` pass. The key is
  recorded at each of the three places a guest flip request is counted for the present loop
  (FIFO flip marker, `cellGcmSetFlipCommand`, `cellGcmSetPrepareFlip`); the milestone log
  keeps the first occurrence in order and counts the rest.
- Adding patch 0001 changed the patches hash, so the tree was translated again (57.4 s,
  same 70,028 functions) before the build; configure refuses a tree translated under another
  patch set.

## Translating EMAIN (2026-10-27)

Measured with `ppu_lifter` on the v1.22 `USRDIR/EMAIN.SELF.elf` (M4 Max):

| Run | Time | Peak memory | Functions | Output |
|---|---|---|---|---|
| Without `--code-end` | 224 s | 12.9 GB | 87,498 | 4.1 GB of C++ |
| With `--code-end 0x101BEA0` (spike) | 21 s | 3.2 GB | 70,028 | 333 MB, 64 chunks + `ppu_recomp_table.cpp` |
| Same, via `scripts/translate_game.py` | 21.1 s (loader 0.6 s + lifter 20.4 s) | 3.2 GB | 70,028 | 333 MB in `ppu/` (66 files incl. header and table) |

- About 3.7 GB of the unbounded output comes from call targets promoted inside read-only
  data and the embedded SPU programs, from va 0x101BEA0 upward.
- The code end 0x101BEA0 is the end of the last executable section (section 4,
  0x1011CC0 + 0xA1E0), read from the ELF section headers.
- Compiling all 65 chunks with Apple clang 21, `-std=c++20 -O1 -w -fwrapv
  -fno-strict-aliasing -ffp-contract=off`, 12 in parallel: 72 s wall, 774 s CPU, largest
  chunk 16 s, peak 1.2 GB per compiler, 242 MB of objects. Include paths: the lift folder,
  `ps3recomp/runtime/ppu` (`ppu_vmx.h`), `ps3recomp/include`, `ps3recomp/runtime`.
- EMAIN SHA-256 `7b4f37bd...c373d1`, ps3recomp commit `4e8f3ca`.

**SPU programs and job modules** (`translate_game.py` SPU step, same run, same staging
folder as the PPU lift):

| What | Found | Lifted fully | Partial (runs interpreted, D9/O9) | Time |
|---|---|---|---|---|
| SPU ELF programs (`build_spu_workloads --input`) | 4 | 1 (0x1286F00, 17,400 B) | 3 | |
| SPURS job modules (`lift_jobmods --jobmods`) | 57 | 49 | 8 | |
| Whole SPU step | | | 11 | 36.8 s (whole translate 57.7 s) |

- Output: 41 MB in `spu/` (61 image folders, `spu_workloads.c`, `jobmods_register.c`,
  `inventory.json`, `jobmods_manifest.json`). No tool makes `taskset_policy_bytes.c` for
  GT6, so there is none. No tool failed outright.
- Partial SPU programs (by file offset): 0x13F9580 `ipc_spucore.elf` (14 bad words),
  0x13FE900 (11), 0x1415080 (3). `build_spu_workloads` refuses to register an image whose
  lift holds any `.word`, so these three are left out of `spu_workloads.c` and run
  entirely in the SPU interpreter. Their `spu_recomp.c` is still written.
- Partial job modules (unsupported words): `102b6697dde2` 1, `1bf6d3965594` 7, `3174b2012dbe` 4,
  `5e2f0559e74f` 1, `94f320930490` 4, `b683cd421be4` 24, `c25145879d61` 12, `fbe88df0b81a` 261
  (314 in all). `lift_jobmods` still registers these, and the bad words fall to the
  interpreter.
- Every unsupported word seen is data the lifter took for code (shuffle-mask constants such
  as `0x1F1E1D1C`, `0x01000000`), not an SPU instruction the lifter lacks. A per-image code
  end, like D25 for the PPU, should clear most of them (BACKLOG).
- `lift_jobmods --engine-elf` finds only 5 of the 57 modules: it requires the load base
  0x4000 at header +0x28, and 52 GT6 modules have 0 there. The step cuts the modules out with
  `map_game.find_embedded_jobmods` (all 57, 16-byte aligned) and uses `--jobmods` instead, so
  modules register by their first 16 bytes; all 57 are distinct. `lift_jobmods` falls back
  to the base 0x4000 for a 0 field.
- `build_spu_workloads --input` finds the 4 programs itself; `extract_spu_images` is not
  needed. Image ids: programs get content-derived ids (0x1xxxxxxx), job modules 200-256.

## Code map of v1.22 (2026-10-27)

**Risks found** (technical detail; the plain-language version is the owner summary above):

- **Helper-core code is the biggest job.** The 57 SPURS job modules (1.53 MB) are stored raw
  inside the executable, not as the separate programs ps3recomp's tools expect. Our map finds
  and extracts them; ps3recomp's own extractor finds none. Milestone 2 must lift them and build
  SPURS support for job chains and tasks, not just the simpler case.
- **ps3recomp's name list has gaps.** ps3recomp cannot name 227 of the 835 imported functions
  (EMAIN 217, EBOOT 10). RPCS3 names 222 of them, so the gap is in ps3recomp's list, not
  unknown territory. Five (in game storage) are unnamed by both.
- **The launcher does work before the game starts.** The 1.22 `EBOOT.BIN` runs a data-patch
  step, and can swap in a repaired executable, before it launches the game (below). The port
  must reproduce what that step leaves on disk, or run it.
- Nothing failed outright. One ps3recomp tool does not start under the isolated Python the
  project requires; a small runner works around it without changing ps3recomp (D22).

**What the 1.22 EBOOT launches.** From a static trace of the decrypted 1.22 `EBOOT.BIN` (in
the code segment, va = file offset + 0x10000). It always launches `<own folder>/EMAIN.SELF`,
that is `/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF`. The repair swap below is the one
exception.

- Boot function 0x123e0: takes `argv[0]`, cuts it to its folder, and checks that `EBOOT.BIN`
  and `EMAIN.SELF` both exist there. Both paths are built in a static buffer at va 0x52a10.
  If either is missing it shows the "game content damaged" dialog (`cellGameContentErrorDialog`).
- It then opens `TPPS-01.07/update.txt` in that folder and, if the file exists, overwrites it
  with `99.98 99.99` (string at va 0x3d100). As installed, `TPPS-01.07/update.txt` reads
  `01.06 01.07`, and every later `TPPS-01.xx/update.txt` already reads `99.98 99.99`.
- 0x1143c is a data-patch step (measured in "What the 1.22 EBOOT leaves on disk" above). It scans the `TPPS-%02d.%02d` folders,
  `PDIPFS` and `UPDATENODEINFO`, writes `UPDATENODEINFO.upd` and renames files. It receives the
  launch path only as a source to copy from, so it cannot change it.
- 0x108f0 is the repair swap. It reads the size of the current `EMAIN.SELF` (`cellFsFstat`)
  and looks it up in a table keyed by title ID (va 0x51b84, 0x20-byte rows of size + title).
  For BCES01977 the "broken" size is 9,058,928 bytes, which is the 1.14 `EMAIN.SELF`. Only on a
  match does it check `FIXEDELF114/EMAIN.SELF` against a second table (9,059,040 bytes, which
  is its size). It then renames that file over `USRDIR/EMAIN.SELF` (`cellFsRename` in 0x2224c).
  The 1.22 `EMAIN.SELF` is 9,001,952 bytes, so the swap does not happen on 1.22.
  **`FIXEDELF114` is a repaired 1.14 executable, kept for consoles stuck on the broken one.**
- Spawn: 0x12614 calls 0x2123c with the klicensee string from 0x13914 (the `KeyLicensee`
  default traced earlier) and the 0x52a10 buffer. 0x2123c parses the key and calls
  `sceNpDrmProcessExitSpawn2` at 0x21324. 0x125e4 is a non-DRM branch that calls
  `sys_game_process_exitspawn2` with the same buffer, taken when a state record returned by
  0x20858 has its first word 1 and the low bit of its second word clear. No code passes a `TPPS-*` or `FIXEDELF114` path to
  either spawn call.
- **The `TPPS-01.xx` folders** each hold an `EMAIN.SELF`, a `PDIPFS` folder and an `update.txt`
  ("from to" versions). They look like per-update staging for Polyphony's `PDIPFS` data-patch
  system. `TPPS-01.07/PDIPFS` is 971 MB and `TPPS-01.22/PDIPFS` is 17 MB. The 1.22 EBOOT never
  spawns their executables.
- **No two of the 21 decrypted executables are identical** (SHA-256, `map/identity.json`).
  `USRDIR/EMAIN.SELF` is not `TPPS-01.22/EMAIN.SELF`: the ELFs are 23,168,200 and 23,787,792
  bytes. Three pairs have equal ELF sizes but differ in millions of bytes:
  `FIXEDELF114`/`TPPS-01.14`, `TPPS-01.10`/`01.11` and `TPPS-01.12`/`01.13`. All carry the
  build tag `gt.gt6.ps3.product-strong.release.build`.

**Numbers** (`scripts/map_game.py`, ps3recomp 4e8f3ca8; full summary in
`~/Gran Turismo 6/build/BCES01977-v1.22/map/summary.json`):

| | 1.22 `EBOOT.BIN` | 1.22 `USRDIR/EMAIN.SELF` |
|---|---|---|
| ELF bytes | 278,344 | 23,168,200 |
| Code segment (also holds read-only data and the SPU programs) | 200,608 | 21,749,736 |
| Data segment, in file / in memory | 10,660 / 227,328 | 1,385,632 / 2,775,632 |
| Functions found (`find_functions`) | 1,117 | 72,144, covering 15,318,088 bytes |
| Address-taken functions (`ppu_loader`, from the descriptor table) | 282 | 33,428 (45,005 descriptors) |
| System functions imported / libraries | 95 / 11 | 740 / 46 |
| Imports ps3recomp cannot name | 10 | 217 (29 %) |
| SPU ELF programs | 0 | 4, 224,036 bytes |
| SPURS job modules | 0 | 57, 1,532,240 bytes |

- `find_functions` attributes almost no code to the SPU programs: 2 functions start in the
  3.4 MB stretch (va 0x112d880 to 0x1468190) that holds them. So the 15.3 MB is PPU code.
- **Imports of `EMAIN.SELF` by library** (the EBOOT's 11 libraries are all among these):
  sceNp 64, cellSysutil 55, cellSpurs 49, sceNp2 48, cellGcmSys 39, sysPrxForUser 38,
  sys_net 34, sceNpCommerce2 32, cellSail 31, cellHttp 28, cellSysutilAvc2 27, sys_fs 26,
  sys_io 23, cellSailRec 19, sceNpTus 19, cellPamf 18, cellNetCtl 15, cellUsbd 14,
  sceNpTrophy 13, cellAudio 12, cellDmux 12, cellRtc 10, cellUsbPspcm 9, cellAdec 8, cellGame 8,
  cellMusicUtility 8, libvdec 8, cellFiber 6, cellOskExtUtility 6, cellSysmodule 6, sceNpSns 6,
  cellGameStorage 5, cellHttpUtil 5, cellRec 5, cellKey2char 4, cellSaveData 4, cellSsl 4,
  cellVideoExportUtility 4, sceNpUtil 4, cellPhotoUtility 3, cellSync 3, cellSysutilNpEula 3,
  cellUserInfo 2, cellSysutilAvconfExt 1, sceNpBasicLimited 1, sys_crashdump 1.
- By purpose: online (sceNp except trophies, sys_net, HTTP/SSL, network control, voice chat,
  EULA) 290 in 14 libraries; video playback and recording (cellSail, cellSailRec, cellPamf,
  cellDmux, libvdec, cellAdec, cellRec, video export) 105; USB (cellUsbd, cellUsbPspcm) 23,
  probably including the racing wheels (milestone 7); SPURS and sync 52; the remaining core
  (graphics, files, pad, audio, system, save data, trophies, time, fibres) 270.
- **SPURS: yes, heavily.** The 49 cellSpurs imports cover initialisation with attributes,
  tasksets and tasks (`cellSpursCreateTaskset2`, `cellSpursCreateTask2`), job chains
  (`cellSpursCreateJobChainWithAttribute`, `cellSpursRunJobChain`, `cellSpursJobGuard*`),
  custom workloads (`cellSpursAddWorkloadWithAttribute`), SPURS queues, LV2 event queues and
  tracing. The one unnamed cellSpurs import is 0x2DDBCC0A (`_cellSpursWorkloadFlagReceiver2`
  in RPCS3).
- **SPU ELF programs** (file offsets in `EMAIN.SELF.elf`): 0x1286F00 17,400 B (built with SPU
  GCC 4.1.1, SDK 4.20), 0x13F9580 21,332 B (`ipc_spucore.elf`), 0x13FE900 91,956 B,
  0x1415080 93,348 B.
- **Job modules**: 57, all different, 3,216 to 155,184 bytes each, between file offsets
  0x111d880 and 0x1456600 of the code segment. Header: four `ila`, entry 0x30, image size, then
  `0xC0DEC0DE`. They are extracted to `map/<elf>/jobmods_embedded/` with ps3recomp's naming,
  ready for `lift_jobmods.py`. ps3recomp's `extract_jobmods.py` exits 0 and writes nothing
  (`MISSING .../USRDIR/patch.sdat`, `MISSING .../USRDIR/data.sdat`): GT6 has no SDATA archives.
  Programs the game loads from `GT.VOL` at run time would not show up in any of these counts.
- **Unresolved NIDs**: 217 in EMAIN, by library: cellSailRec 19, cellSail 18, sceNp 14,
  cellHttp 13, cellSysutil 13, cellSysutilAvc2 13, sceNp2 12, cellPamf 9, cellUsbPspcm 9,
  cellUsbd 9, sys_net 9, cellNetCtl 6, cellOskExtUtility 6, cellFiber 5, cellGameStorage 5,
  sceNpSns 5, sysPrxForUser 5, sys_io 5, then 18 libraries with 4 or fewer. 10 in EBOOT:
  cellFiber 5 (the `cellFiberPpuContext*` family), sys_fs 4 (`cellFsReadWithOffset`,
  `cellFsWriteWithOffset`, `cellFsAllocateFileAreaWithoutZeroFill`, `cellFsFGetBlockSize`),
  sys_crashdump 1. Every one appears by name in the RPCS3 0.0.43-20410 boot log
  (`ppu_loader: **** <lib> import: [<name>] (<nid>)`) except five cellGameStorage NIDs
  (0x23EC78CE, 0x50771F25, 0x8DBD9594, 0xA9201831, 0xD7724C0A), which RPCS3 also leaves
  unnamed. Core ones ps3recomp lacks include `sys_mempool_*`, `cellPadLdd*` (custom controller
  drivers) and `cellWebBrowser*`.
- **Tool failure.** `.venv/bin/python -I third_party/ps3recomp/tools/extract_spu_images.py
  EMAIN.SELF.elf -o spu_images` fails with `ModuleNotFoundError: No module named 'spu_elf'`
  (`extract_spu_images.py` line 31). `-I` leaves the script's folder off the import path, and
  unlike the other tools this one does not add it itself. Worked around (D22). The other four
  tools run as documented in ps3recomp's `docs/TOOLS.md`.
- **Run time** on the M4 Max: 13.6 s for the whole map, including SHA-256 of all 21 ELFs.
  `find_functions` on EMAIN takes 12.4 s; every other tool takes under 0.6 s.

## Building the v1.22 tree (2026-10-27)

- **Outcome: done.** `gt6unpack build` produces a verified v1.22 tree at
  `~/Gran Turismo 6/build/BCES01977-v1.22` (25 GB). Final installed APP_VER: 01.22. All 21
  SELFs decrypted; none failed, and no other SCE files were found.
- **The update executables need the game's own key.** The 18 update `EMAIN.SELF` files
  (`USRDIR/EMAIN.SELF`, `USRDIR/FIXEDELF114/EMAIN.SELF`, `USRDIR/TPPS-01.07` to
  `TPPS-01.22/EMAIN.SELF`) are free-licence NPDRM SELFs (program type 8, key revision 0x001C,
  licence 3). They do not open with the public free klicensee. The update `EBOOT.BIN` is the
  same kind of SELF and does open with it. This is the first real-data proof of that path.
- **Where the key comes from.** Captured once from RPCS3 0.0.43-20410-c365ea76 booting the
  disc with the updates installed. RPCS3 boots `/dev_hdd0/game/BCES01977/` (the 1.22
  `EBOOT.BIN`), which calls `sceNpDrmIsAvailable` for
  `/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF` with a klicensee on its stack. Traced in the
  decrypted 1.22 `EBOOT.BIN` (278,344 bytes):
  - Import stubs: `sceNpDrmIsAvailable` at 0x3c180, `sceNpDrmProcessExitSpawn2` at 0x3c1f0.
    `sceNpDrmIsAvailable` is called at 0x10984 and 0x10a38, both in the function at 0x108f0.
  - The klicensee buffer (sp+0x74) is filled by a hex-string parser (0x20f04) from the string
    returned by 0x13914.
  - 0x13914 looks up the config entry `"KeyLicensee"` (string at va 0x3f038) in a
    name/value table at va 0x7e00c. The fallback is the all-zero string at va 0x3f048.
  - A static initialiser registers `KeyLicensee` (0x128f4) with a type-6 (string) default
    that points to va 0x52000 in the data segment (file offset 0x42000). That default is
    `"0x"` + 32 hex digits: the klicensee in plain text.
  - Earlier byte-window scans missed it because they looked for 16 raw bytes, not hex text.
  - The decrypted ELF has exactly two such strings: that one and the all-zero fallback.
- **How gt6unpack gets it.** A free-licence NPDRM SELF that fails with the public klicensee is
  retried with every `0x`+32-hex string found in the decrypted update `EBOOT.BIN`. A candidate
  is accepted only if the metadata opens and every program-segment HMAC matches. The key is
  read from the player's own files at build time. It is not in the repository and not in
  `build.json`, which records only where it was found.
- One key opens all 18 update `EMAIN.SELF` files. `USRDIR/EMAIN.SELF` (the one the 1.22
  `EBOOT.BIN` spawns) is not the same file as `TPPS-01.22/EMAIN.SELF`.
- Decrypted executables (SHA-256 of the ELF):

  | File | ELF bytes | SHA-256 |
  |---|---|---|
  | dev_bdvd `PS3_GAME/USRDIR/EBOOT.BIN` | 143,064 | `241c3e8c805049474dcb337914928d6552a3a4087a70cccda018356d73285b28` |
  | dev_bdvd `PS3_GAME/USRDIR/EMAIN.SELF` | 22,371,400 | `3b543f22062d078a30ec2e5c15d16e7c8a2389cdc32375a58fec6c6842896729` |
  | dev_hdd0 `USRDIR/EBOOT.BIN` | 278,344 | `4c9f642e21df8963b1f0c6df14ecdb4b3e8d0c061c45427ecc955b6a9eec0272` |
  | dev_hdd0 `USRDIR/EMAIN.SELF` | 23,168,200 | `7b4f37bdf1cc6024a6abd38012eb40f02afe979996aa075ed9e1736aecc373d1` |
  | dev_hdd0 `USRDIR/FIXEDELF114/EMAIN.SELF` | 23,512,336 | `437bd0b66916da6d93481ea2c93881ab063ffa095eade33481cb01f5d9bb3312` |
  | dev_hdd0 `USRDIR/TPPS-01.07/EMAIN.SELF` | 23,309,640 | `70a6a472dc10b8113b34cb67d229d6cf7e9b15ccb20a1c634c415fb1e43618cd` |
  | dev_hdd0 `USRDIR/TPPS-01.08/EMAIN.SELF` | 23,310,904 | `ca197b14376eedcaba83b944819de6b290e33c9530207ad8875b30678ef72599` |
  | dev_hdd0 `USRDIR/TPPS-01.09/EMAIN.SELF` | 23,377,752 | `221c72567e8c2f20684111a2402cfa7ead4398e8be972b6c9f58707af2205f4a` |
  | dev_hdd0 `USRDIR/TPPS-01.10/EMAIN.SELF` | 23,180,216 | `c660236e51f84cf2d1ff0b06da2d2798ccaf9efa2d64725d512c59817487025d` |
  | dev_hdd0 `USRDIR/TPPS-01.11/EMAIN.SELF` | 23,180,216 | `1148b01e7fb6b060ee9472e16558582722df978d275896cf360e0213e6dcba65` |
  | dev_hdd0 `USRDIR/TPPS-01.12/EMAIN.SELF` | 23,384,040 | `68cd0695d7a8e8e5bc69c84339b30e9ff59fbaa2034579fbcbc46f79fc2d5dd8` |
  | dev_hdd0 `USRDIR/TPPS-01.13/EMAIN.SELF` | 23,384,040 | `d13d58e83fde6db67e5ba03d7e6ac978762e55d081081833d845c9e7689020a7` |
  | dev_hdd0 `USRDIR/TPPS-01.14/EMAIN.SELF` | 23,512,336 | `08f064cabff120cc5bfb0741872cf32d9f5df62225d6515f121fe905cff751bf` |
  | dev_hdd0 `USRDIR/TPPS-01.15/EMAIN.SELF` | 23,580,432 | `ae0cff918db28629c9746ca5ce31172c43e44033eeffd78a5ffef4552d47547d` |
  | dev_hdd0 `USRDIR/TPPS-01.16/EMAIN.SELF` | 23,784,592 | `6a2a469fafa9cee01622468841d07f726fb3f69ac23661a8b2ea2476d4df9cdc` |
  | dev_hdd0 `USRDIR/TPPS-01.17/EMAIN.SELF` | 23,785,360 | `6ecf1d291c26061b3f283b418583b34bd19bc2bb37f5112a07a1178cc785a562` |
  | dev_hdd0 `USRDIR/TPPS-01.18/EMAIN.SELF` | 23,785,488 | `f8c38f78152c9742d900ad24655b6fc8494943fcd7df4887a0a3d2fb72aa5a67` |
  | dev_hdd0 `USRDIR/TPPS-01.19/EMAIN.SELF` | 23,786,384 | `143303d1853fdc17cbf8433ed281583676af108fcb31fc86dd28c6184354889e` |
  | dev_hdd0 `USRDIR/TPPS-01.20/EMAIN.SELF` | 23,786,768 | `a3f7b4985d75bc13deec437fe3bf3bad898374b9876a3e0f415727f0c35ab897` |
  | dev_hdd0 `USRDIR/TPPS-01.21/EMAIN.SELF` | 23,787,664 | `5c65a069c74eb1dd7cb52bf03333edf4741b933fc8479f0db2ca26a0271dbf7d` |
  | dev_hdd0 `USRDIR/TPPS-01.22/EMAIN.SELF` | 23,787,792 | `0e665e78eca03246d13d4394ae22a4dfab32f5141bf0cd26a04622700c4cc2e0` |

- Update install cross-checked against RPCS3 0.0.43-20410-c365ea76 (`--headless --installpkg`,
  one package at a time in APP_VER order). Its `dev_hdd0/game/BCES01977` and the gt6unpack
  install match exactly: 16,536 files with identical SHA-256, and 5,118 identical folders.
  Each headless RPCS3 install finished in about 2 s and aborted during process teardown
  (exit 134) after writing the files.
- Timings on the M4 Max (from `build.json`), 155 s in total:

  | Step | Time |
  |---|---|
  | Verify the 21 packages (Sony SHA-1 over 11.2 GB) | 6.3 s |
  | Disc copy (the ISO is a separate volume, so `clonefile` gives EXDEV) | 15.6 s |
  | Disc SHA-1 | 7.5 s |
  | Install the updates | 104.8 s |
  | Decrypt the 21 SELFs (including the klicensee search) | 20.6 s |

- The mounted ISO is read-only all the way down (`r-xr-xr-x`). The built `dev_bdvd` is
  normalised to 0755 folders and 0644 files, so a rebuild or removal works.
- 1.07 carries no `USRDIR/EBOOT.BIN`, and the install handles that: a later package replaces
  only the files it carries. All 21 packages extract under the existing name checks with no
  rejections.

## Disc executables (2026-10-27)

- `EMAIN.SELF` and `EBOOT.BIN` are retail application SELFs (program type 4, not NPDRM),
  SCE header key revision 0x001C, header type 1, ELF64 big-endian PPC64 inside.
- Decrypted ELF SHA-256 (from `gt6unpack`, byte-identical to RPCS3 c365ea76 `--decrypt`):
  - `EMAIN.SELF` → 22,371,400 bytes, `3b543f22062d078a30ec2e5c15d16e7c8a2389cdc32375a58fec6c6842896729`
  - `EBOOT.BIN` → 143,064 bytes, `241c3e8c805049474dcb337914928d6552a3a4087a70cccda018356d73285b28`
- Both have 7 metadata sections: 5 program segments (type 2; the first two zlib-compressed,
  three empty), one SCE version section (type 3) and the section header table (type 1). All
  seven are flagged hashed. The last two are stored unencrypted.
- Section hash: the metadata key table holds, at `sha1_idx * 16`, a 96-byte slot: SHA-1[20],
  zero[12], HMAC key[64]. For every program segment, HMAC-SHA1(key, decrypted section data
  as stored, still zlib-compressed) equals the stored SHA-1. `gt6unpack` checks it.
- The type 3 and type 1 section hashes do not match. Tried, all with the slot's HMAC key and
  also plain SHA-1: the stored bytes; every start offset within ±0x100 and every length up
  to size+0x200; a size-long window at every offset of the SELF and of the decrypted ELF;
  zero padding of 0 to 64 bytes; truncation to 16-byte multiple; zlib-compressed forms
  (levels -1 to 9); 32-bit byte-swapped; AES-128-CTR of the bytes under every key/iv pair in
  the key table. None matched. Likely the signer hashed these before a later fix-up; the
  console never loads them, so it never checks them. RPCS3 checks no section hash at all.
  `gt6unpack` does not check these two. Neither holds segment contents, but the section header
  table is copied into the ELF unverified.
- The SCE version section (`crt0:p440001…` library version strings) is an ELF section outside
  every segment, so it is not in the decrypted ELF (same as RPCS3).

## Game and updates (2026-10-27)

- Disc: BCES01977 v1.00 (UK), `Gran Turismo 6 (UK).iso`, 25.3 GB, already disc-decrypted.
  `PARAM.SFO`: TITLE_ID BCES01977, APP_VER 01.00, VERSION 01.03, PS3_SYSTEM_VER 04.50.
  `USRDIR`: `EBOOT.BIN` (72 KB), `EMAIN.SELF` (8.8 MB), `GT.VOL` (15.4 GB).
  `PS3_UPDATE/PS3UPDAT.PUP`: firmware 4.50.
- Updates: Sony's list `BCES01977-ver.xml` has 21 packages, 1.02 to 1.22, 11.2 GB. All
  downloaded to `~/Gran Turismo 6/updates` and verified.
- Hash rule: Sony's SHA-1 in `BCES01977-ver.xml` covers the package minus its last 32 bytes.
  The package's last 32 bytes are that SHA-1 plus 12 zero bytes.
- Sony root certificates were obtained by running RPCS3 with `--installfw` on the disc's PUP,
  then bundled to PEM for `curl --cacert`. TLS checking was never turned off.
- Not yet verified: per-file hashes of the disc (redump checksums do not apply to a decrypted
  image; the community IRD lists per-file hashes).

## Risk: disc contents not checked against an independent source (2026-10-27)

- The committed manifest `manifests/BCES01977-v1.22.json` proves a player's build matches
  the one we made, but both start from the same disc image. If that image had a bad file
  (for example in GT.VOL), the manifest would record the bad hash as correct.
- The community IRD file lists per-file MD5s of the original disc and would catch this.
  Using it needs an ISO directory reader (BACKLOG, Unpacker). Until then, GT.VOL is
  unverified against an independent source.

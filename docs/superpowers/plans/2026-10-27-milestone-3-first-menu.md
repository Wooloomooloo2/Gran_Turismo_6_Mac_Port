# Milestone 3: First Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the translated GT6 runs from a fresh play folder, through its first-run data install, to the game's first menu. The menu is presented on screen, and a dumped frame shows the same screen RPCS3 shows at that point.

**Architecture:**
1. The boot harness learns to run long. It keeps a capped series of numbered frames and per-frame draw statistics, so a "drawn" frame can be told from a cleared one.
2. One RPCS3 run records the reference: what GT6 shows, when, and which library calls it makes on the way to the menu. That gives a target, a timeline and a list of the calls still missing.
3. The known gaps are closed: PPU fibers, and the other imports that are unresolved and fake success.
4. A bring-up loop fixes one blocker per round until the menu frame matches.

**Tech Stack:** as milestone 2: Python 3 (.venv, pytest), ps3recomp 4e8f3ca8 plus `patches/ps3recomp/*.patch` (D28), CMake/Ninja, Apple clang, Metal. RPCS3 (`~/Developer/others/rpcs3-bin/RPCS3.app`, GPL-2.0-only) is used only as a reference oracle, never as part of the product.

**Spec:** `docs/superpowers/specs/2026-10-27-gt6-mac-port-design.md`: milestone 3, sections 6.2, 6.3, 6.4 and 6.6. Decisions so far: `docs/DECISIONS.md` D1–D34. Milestone 2 state: `docs/FINDINGS.md` (owner summary, "Bring-up log (milestone 2)", "First presented frame") and `docs/BACKLOG.md`.

## Global Constraints

- **Repository contents.**
  - Never commit game files, keys, firmware, decrypted executables, translated code, run logs, frame dumps, RPCS3 logs or screenshots.
  - Every generated file lives under `$GT6_TREE`. RPCS3 reference captures go in `$GT6_TREE/reference/`.
  - Every new tool refuses an output path inside a git work tree, using the same `in_git_work_tree` helper as `scripts/translate_game.py`.
- **GT6's klicensee.** It must never be committed, quoted or copied anywhere.
  - RPCS3's log contains it. Quote only non-key lines.
  - **Owner instruction:** after the last RPCS3 run of a task, delete `~/Library/Caches/rpcs3/RPCS3.log` and any rotated copies (`RPCS3.log.gz`, `RPCS3*.log*` in that folder). Say so in the task report.
- **Firmware and SPURS.** No Sony firmware modules (liblv2, libsre, any PRX from `dev_flash`) are loaded or required. SPURS runs on ps3recomp's HLE. Configure refuses `taskset_policy_bytes.c`.
- **Licences.**
  - New files carry `SPDX-License-Identifier: GPL-2.0-or-later`.
  - Files adapted from ps3recomp keep its MIT notice.
  - Behaviour modelled on RPCS3 is credited, but RPCS3 code is not copied into MIT patches; say "behaviour follows RPCS3" as patches 0004/0005/0007 do.
  - `tests/scripts/test_licence_headers.py` stays green.
- **Documentation.**
  - Every design decision goes in `docs/DECISIONS.md` as the next free D-number (D35 onwards), dated, with the reason.
  - Measurements go in `docs/FINDINGS.md`, shortcuts in `docs/BACKLOG.md`.
- **ps3recomp.** The submodule stays at 4e8f3ca8. Changes are carried only as numbered patch files from `0010` onwards, applied by `scripts/apply_ps3recomp_patches.sh`. Each one is upstreamable and generic: no GT6 names in runtime code, and GT6-only switches live in `port/`.
- **Online.** Online calls answer "offline" and never hang the boot.
- **Fidelity.** Handling must match the PS3 (D10 / O10). Unimplemented calls that GT6 hits on the path to the menu are implemented following RPCS3's behaviour, or given an explicit "not available" answer if the console itself would refuse them. Faked success is never the final state for a call on the menu path.
- **Disk.** This Mac's disk has about 69 GB free. Frame series are capped, by default at 300 frames and 2 GB per run, and the harness stops dumping, with a logged note, when either cap is hit or free space falls below 20 GB. `runs/` older than the latest 10 may be pruned by the harness's `--prune` option only.
- **Other projects.** Never touch, stop or reconfigure other projects' processes (for example a running Bloodborne app) or their folders.
- **Windows.** Long runs are headless by default (`PS3RECOMP_METAL_HEADLESS=1`). Tonight the owner is away, so RPCS3's window may open for the reference run.
- **Tests.**
  - `.venv/bin/python -m pytest tests/scripts -q` and `ctest --test-dir build` stay green without game data.
  - Game-dependent tests skip visibly when `GT6_TREE` is unset.
  - The two load-sensitive upstream runners (BACKLOG) may be retried once before they count as a failure.
- **Git.** Work on branch `m3/first-menu`, merged into `main` locally at the end (owner rule). Pushing needs the owner's OK.

## Facts this plan relies on (milestone 2, measured 2026-10-27)

- **Pipeline:** `scripts/translate_game.py "$GT6_TREE"` (about 60 s), then `cmake -S . -B "$GT6_TREE/port-build" -G Ninja -DGT6_BUILD_PORT=ON -DGT6_TREE="$GT6_TREE"` and `cmake --build "$GT6_TREE/port-build" --target gt6` (about 76 s), then `scripts/prepare_play.py "$GT6_TREE" --force`, then `scripts/boot_game.py "$GT6_TREE"`. The README "Translate and boot" section is authoritative.
- **The harness today.**
  - `boot(gt6, tree, seconds=300, idle=60, headless=True, env=None)` stops 5 s after the first `gcm:flip` (`FLIP_GRACE`).
  - It writes `runs/<ts>/{report.json, summary.md, logs, frames/frame.ppm}`.
  - Its outcomes are `first_frame`, `flip_no_frame`, `exited`, `crashed`, `hung` and `timeout`.
  - `PS3RECOMP_METAL_FRAME_DUMP` writes one file, overwritten every 120th presented frame.
- **Last run** (20261027-211723): first_frame, with 100–999 flips. The frame is all zero while GT6 runs its first-run install, which took more than 5 minutes under RPCS3 before.
- **Imports.** GT6 calls 12 unresolved imports that fake CELL_OK (BACKLOG): `cellVideoOutGetScreenSize`, `_cellSpursWorkloadFlagReceiver2`, `cellSpursGetWorkloadFlag`, `cellSpursInitializeWithAttribute2`, `cellUsbdSetThreadPriority2`, `cellUsbdRegisterExtraLdd`, `sys_mempool_create`, `cellUsbdRegisterExtraLdd2`, `sys_prx_get_module_list`, `_cellFiberPpuContextAttributeInitialize`, `cellFiberPpuContextInitialize` and `cellFiberPpuContextRun`. 312 of EMAIN's 740 imports have no handler.
- **SPURS.** 17 SPURS images (16 jobs and the `Wws_Job` policy module) run interpreted on a fresh tree, are dumped to `<tree>/spu-missed/`, and are lifted by the next translate (D33). All of them lift only partly.
- **setjmp/longjmp.** Guest setjmp/longjmp works through patch 0009 (D34). Its invariant: no lifted C local may change between setjmp and longjmp.

## Review Focus

1. **A long run fills the disk.** Frame caps and the free-space floor stop dumping. They never crash the game or the harness, and the report says dumping stopped. Test in Task 1.
2. **A cleared or black frame counted as "drawn".** The per-frame statistics (draw calls since the last flip, and the share of non-zero pixels) decide `drawn`. A frame with 0 draw calls is never `drawn`, whatever its pixels. Test in Task 1.
3. **A long run never stops.** The game sits on the menu forever. `--seconds` ends it as `timeout`, with frames kept, and the process group is always killed. "Menu reached" is a human or agent judgement written into the run's `verdict.json`, never something the harness infers. Test in Task 1.
4. **A fiber is deleted, or its thread exits, while it is suspended.** No host thread leaks, no deadlock at process exit, and errors follow RPCS3's error codes. Test in Task 3.
5. **The import audit miscounts.** NID collisions or duplicate registrations make the audit report a handled import as missing, or the reverse. The audit is checked against ps3recomp's own registration table and against a known handled and a known unhandled NID. Test in Task 4.

---

### Task 1: Long runs: frame series and draw statistics

**Files:**
- Create: `patches/ps3recomp/0010-metal-frame-series-and-draw-stats.patch`
- Modify: `scripts/boot_game.py`, `tests/scripts/test_boot_game.py`, `README.md` (the "Translate and boot" section), `docs/DECISIONS.md` (D35)

**Interfaces:**
- Consumes: `boot()` and `classify()` from milestone 2, and the `PS3RECOMP_METAL_FRAME_DUMP` code path in `libs/video/rsx_metal_backend.m`.
- Produces:
  - **Runtime environment (patch 0010):**
    - `PS3RECOMP_METAL_FRAME_DIR=<dir>`: numbered dumps `frame_<presented#06d>.ppm`, one every `PS3RECOMP_METAL_FRAME_EVERY` presented frames (default 60). The first presented frame is always dumped.
    - `PS3RECOMP_METAL_FRAME_MAX` (default 300).
    - `PS3RECOMP_DRAW_STATS=<file>`: one line per presented frame, `<presented#> <draw_calls_since_last_flip> <clears_since_last_flip>`.
    - The existing single-file `PS3RECOMP_METAL_FRAME_DUMP` is unchanged.
  - **`boot_game.boot(gt6, tree, seconds=300, idle=60, headless=True, env=None, until="flip", frame_every=60, frame_max=300, frame_bytes=2*1024**3)`:**
    - `until="flip"` keeps milestone 2's behaviour.
    - `until="time"` runs to `seconds` and is not stopped by the first flip.
    - Disk caps: it stops dumping (by moving the frame dir aside, or by a stop-file the patch polls; implementer's choice, written up in D35) when the frames exceed `frame_bytes` or free space drops below 20 GB. The report records `dump_stopped: <reason>`.
  - **New `report.json` keys:**
    - `frames` (count);
    - `frames_list` (`[{"file", "presented", "draws", "clears", "nonzero_share"}]`);
    - `drawn_frames` (the count with `draws > 0` and `nonzero_share > 0.01`);
    - `first_drawn` (the presented number, or null);
    - `dump_stopped` (null or a reason).
  - **`scripts/boot_game.py` CLI:** `--until {flip,time}`, `--frame-every N`, `--frame-max N`, `--png` (converts the dumped frames to PNG with `sips` into `frames_png/` for viewing), and `--prune` (keeps the newest 10 runs).
  - **`classify`:** `first_frame` still needs `frames >= 1`. In `until="time"` mode, a run that reaches `seconds` without crashing is `timeout`, with the frames kept.

- [ ] **Step 1: Failing tests.** In `tests/scripts/test_boot_game.py`, with the existing fake-binary pattern:
  - `test_until_time_ignores_flip`: the fake prints `gcm:flip` and keeps running. The run lasts about `seconds` and ends as `timeout`.
  - `test_drawn_needs_draw_calls`: the fake writes a stats file with draws 0 and a non-zero frame. `drawn_frames == 0`.
  - `test_drawn_frame_counted`: draws 12 plus a non-zero frame gives `drawn_frames == 1` and `first_drawn` set.
  - `test_frame_bytes_cap_stops_dumping`: `frame_bytes` is tiny. `dump_stopped == "bytes"`, and the game is not killed for it.
  - `test_free_space_floor` monkeypatches `shutil.disk_usage`. It gives `dump_stopped == "disk"`.
  - `test_prune_keeps_ten`.
  - `test_group_killed_on_timeout_in_time_mode`.
- [ ] **Step 2: Patch 0010.** Do this in the submodule working tree, then export it with `git -C third_party/ps3recomp diff > patches/ps3recomp/0010-…` in the established way (see `scripts/apply_ps3recomp_patches.sh` and D28). It needs a C-level test runnable from `tools/test_*.py`, where the backend allows one headless; otherwise test the PPM writer and the stats line writer as separate functions.
- [ ] **Step 3: Implement the harness changes.** Then make the tests pass.
- [ ] **Step 4: One real check.** Run `scripts/boot_game.py "$GT6_TREE" --until time --seconds 240 --png` on a fresh play folder. Record the `drawn_frames` and `first_drawn` it reports in FINDINGS ("Long runs"). Look at 3 of the PNGs and describe them in words. This answers milestone 2's question: is the black frame cleared, or not drawn?
- [ ] **Step 5: Docs and commit.** D35 (the frame-series design and the caps), and a README line for each new flag. Commit `feat(boot): long runs with frame series and draw statistics`.

### Task 2: RPCS3 reference run to the first menu

**Files:**
- Modify: `docs/FINDINGS.md` (a new section, "RPCS3 reference: boot to the first menu"), `docs/BACKLOG.md`
- Outputs that are not committed: `$GT6_TREE/reference/rpcs3-<ts>/` (screenshots as PNG, `calls.txt`, `timeline.md`)

**Interfaces:**
- Consumes: the RPCS3 app, the owner's GT6 v1.22 install inside RPCS3 (as used for milestone 1 and 2's oracle runs; see FINDINGS), and macOS `screencapture`.
- Produces, for Task 5:
  - `$GT6_TREE/reference/rpcs3-<ts>/menu.png`, the first menu screen;
  - `first-run-install.png`, the screen during the install;
  - `timeline.md`, giving the seconds from boot to the first non-black screen, the install finishing, any intro or legal screens, and the first menu, plus every button press needed (for example "press X/Enter at the title");
  - `calls.txt`, the distinct HLE function names GT6 calls before the menu, taken from RPCS3's log with key lines removed. Keep the names only, with no arguments.
  - In FINDINGS: the same timeline in words, the call list compared against `scripts/audit_imports.py`'s output (Task 4), or against the BACKLOG list if Task 4 isn't done yet, and how the first-run install screen looks.

- [ ] **Step 1: Read FINDINGS.** Find how RPCS3 was run before: which app, which game path, and that `persistent_settings.dat` gains playtime. Start RPCS3 with the game from the command line (`RPCS3.app/Contents/MacOS/rpcs3 --no-gui <path to EBOOT.BIN>`, or the documented form). Run it on the player's GT6 install as RPCS3 has it.
  - Before touching RPCS3's GT6 save or install, copy RPCS3's `dev_hdd0/home/*/savedata/BCES01977*` aside into `$GT6_TREE/reference/rpcs3-save-backup-<ts>/`.
- [ ] **Step 2: Capture a screenshot every 10 s.** Use `screencapture -x -l <window id>`; find the window id with a small `osascript`, or with `CGWindowListCopyWindowInfo` through `python3 -c` and pyobjc if it is available. Otherwise capture the main display with `screencapture -x -D 1`. Keep going until the first menu is on screen or 30 minutes pass.
  - If the game waits for input (for example "press START"), send it with `osascript` key events to RPCS3 (RPCS3's default keyboard pad maps Enter to Start and X), and record each press in `timeline.md`.
- [ ] **Step 3: Write the outputs.**
  - Extract `calls.txt` from RPCS3's log with a filter that drops any line containing 32 or more hex digits. Check that no line in `calls.txt` contains `klic`, `0x` followed by 32 hex digits, or the word `KeyLicensee`.
  - Write `timeline.md` and the FINDINGS section. Look at the PNGs to describe the screens.
- [ ] **Step 4: Clean up.** Quit RPCS3. **Delete RPCS3's log files (owner instruction)** and confirm in the report that `~/Library/Caches/rpcs3/` holds no `*.log*`. Note the playtime added to RPCS3's stats.
- [ ] **Step 5: Commit** `docs: RPCS3 reference timeline to the first menu`.

### Task 3: PPU fibers (cellFiberPpu*)

**Files:**
- Create: `patches/ps3recomp/0011-cellfiber-ppu-contexts.patch` (implementation plus a `tools/test_cellfiber_ppu.py` runner and a C test)
- Modify: `docs/DECISIONS.md` (D36), `docs/BACKLOG.md` (remove the fiber entry when done)

**Interfaces:**
- Consumes: ps3recomp's HLE module registration (see how `libs/` modules register NIDs), the lifted-function call convention (`ppu_context*`, guest stack), and `runtime/ppu/ppu_sjlj.h` (D34).
- Produces: working `_cellFiberPpuContextAttributeInitialize`, `cellFiberPpuContextInitialize`, `cellFiberPpuContextRun`, `cellFiberPpuContextSwitch`, `cellFiberPpuContextSelf`, `cellFiberPpuContextReturnToThread`, `cellFiberPpuContextFinalize` and `cellFiberPpuContextCheckStackLimit`. Implement every `cellFiberPpuContext*` that GT6 imports; list GT6's imports from `<tree>/recomp/loader/EMAIN.SELF.imports.json`. If GT6 imports the cellFiberPpu scheduler APIs too (`cellFiberPpuInitialize`, `cellFiberPpuCreateFiber`, `cellFiberPpuRunFibers`, `cellFiberPpuYield`, `cellFiberPpuJoinFiber`, …), implement those as well.

- [ ] **Step 1: Find out how GT6 uses fibers.** Disassemble its call sites from the lifted code or the ELF: what entry functions, what stack sizes, and whether it switches between fibers or only runs and returns. Read RPCS3's `rpcs3/Emu/Cell/Modules/cellFiber.cpp` (most of it is stubs, so note that) and the SDK semantics from public docs. Record the findings.
- [ ] **Step 2: Choose the mechanism and record it as D36.** A lifted function runs on the host stack, and its guest state is in `ppu_context`. A fiber switch must therefore suspend the host call chain. The options:
  - (a) one host thread per fiber, with a baton handoff (a mutex/condvar or semaphore), so only one runs at a time;
  - (b) `ucontext`/`makecontext` on macOS arm64 (deprecated, but present);
  - (c) hand-written arm64 context switching.

  Recommend (a) unless the measurement in Step 1 shows thousands of switches per frame. Record the D34 interplay: a longjmp must not cross fibers.
- [ ] **Step 3: Failing tests.** C tests through the runner:
  - run returns to the thread when the entry returns;
  - switching A→B→A preserves each fiber's guest registers and stack;
  - Self returns the current fiber;
  - Finalize on a suspended fiber frees its host resources without a deadlock;
  - each error case follows RPCS3/SDK codes (`CELL_FIBER_ERROR_INVAL`, `CELL_FIBER_ERROR_STAT`, `CELL_FIBER_ERROR_PERM`, with values from RPCS3's `cellFiber.h`);
  - process exit with suspended fibers does not hang (the test runs under a timeout).
- [ ] **Step 4: Implement, export the patch, and run the patch-chain test** (`tests/scripts/test_ps3recomp_patches.py`).
- [ ] **Step 5: Rebuild and boot.** Translate, build, prepare and run `boot_game.py --until time --seconds 300`. The milestone log must show the fiber calls, and none of them may be in `unresolved`. Record the result in FINDINGS. Commit `feat(ps3recomp-patch): cellFiberPpu contexts (D36)`.

### Task 4: Import audit, and the other unresolved imports on the menu path

**Files:**
- Create: `scripts/audit_imports.py`, `tests/scripts/test_audit_imports.py`, `patches/ps3recomp/0012-…patch` (more files if the changes are split by module; one patch per library module)
- Modify: `docs/BACKLOG.md` (the import list becomes the audit's output, summarised), `docs/DECISIONS.md` (a D-number only if a call gets a deliberate non-PS3 answer)

**Interfaces:**
- Consumes: `<tree>/recomp/loader/EMAIN.SELF.imports.json`, ps3recomp's NID registrations (the names via `gen_hle_nids.py` and the runtime's registration tables), and `report.json` `unresolved` lists from runs.
- Produces:
  - `scripts/audit_imports.py "$GT6_TREE" [--runs]`, which prints a table of `module, name, nid, handled (yes/no), called_in_runs (count)` and writes `$GT6_TREE/recomp/import_audit.json`.
  - The non-fiber imports on the menu path implemented: the 9 non-fiber ones in BACKLOG, plus anything Task 2's `calls.txt` shows GT6 calling before the menu that has no handler.
    - USB calls (`cellUsbd*`) follow RPCS3: no devices, so GT6's wheel probe finds nothing.
    - `sys_prx_get_module_list` returns the list a console with no extra PRX loaded would give, per RPCS3.
    - `cellVideoOutGetScreenSize` gives the RPCS3 answer for a 720p/1080p HDMI setup, matching what `cellVideoOutGetState` already reports.

- [ ] **Step 1: Failing tests.**
  - `test_known_handled_nid` and `test_known_unhandled_nid` use NIDs taken from the runtime's tables; pick them in the test from the real table, under a pristine export.
  - `test_collision_reported`: two names with one NID are flagged, not silently merged.
  - `test_refuses_output_in_git_tree`.
- [ ] **Step 2: Implement the audit and run it** on the real tree. Paste its summary counts into FINDINGS.
- [ ] **Step 3: Implement each call.** Follow RPCS3's behaviour, with C tests through a runner per patch.
- [ ] **Step 4: Rebuild and boot.** With `--until time --seconds 300`, none of these may remain in `unresolved`. Commit per patch.

### Task 5: Bring-up loop to the first menu

**Files:** whatever each round needs: patches `0013+`, `port/`, `scripts/`. Every round appends to `docs/FINDINGS.md` "Bring-up log (milestone 3)", with one numbered row per round giving the symptom, the root cause, the fix and the run id. Shortcuts go in BACKLOG, and decisions get D-numbers.

**Interfaces:**
- Consumes: Tasks 1–4. Task 2's `timeline.md` gives the button presses and timings; Task 2's `menu.png` is the target.
- Produces: the outcome. A run, `boot_game.py --until time --seconds <timeline's menu time × 2, at least 600>`, whose dumped frames include one an agent judges, by viewing the PNG next to `reference/…/menu.png`, to be the same menu screen (same layout and text; colour and resolution may differ). The judgement is written to `runs/<ts>/verdict.json` as `{"menu": true, "frame": "...", "reference": "...", "notes": "..."}` and quoted in FINDINGS.
  - **Input:** if the menu needs a button press, add a harness option `--press <seconds>:<button>` that injects a pad press through ps3recomp's input layer. That needs a small generic patch: an env-driven scripted pad, for example `PS3RECOMP_PAD_SCRIPT="30:start,45:cross"`. Record it as a D-number.

- [ ] **Each round:**
  1. Boot on a fresh play folder (`prepare_play.py --force`).
  2. Read the report, the milestones and the last frames.
  3. Find the one blocker that stops progress. Use superpowers:systematic-debugging, and compare against RPCS3's behaviour and source for that call.
  4. Fix it with a test and commit.
  5. After any SPU dump into `spu-missed/`, re-translate so the next round runs those images natively.
- [ ] **Stop conditions** (bring these to the owner with evidence; do not work around them):
  - the fix needs Sony firmware;
  - it would break a recorded decision;
  - ps3recomp is shown to be unsuitable for something on the menu path.
- [ ] **A round budget per dispatch:** at most 6 blockers, or about 2.5 hours. Then report PROGRESS, so the controller reviews it before the next batch.

### Task 6: Docs and handover

**Files:**
- Modify: `README.md` (status: milestone 3 reached, or how far it got; the new harness flags), `CLAUDE.md` (state), `docs/FINDINGS.md` (owner summary for milestone 3 at the top: plain language, a 4-row table like milestone 2's), `docs/BACKLOG.md`, `THIRD-PARTY-NOTICES.md` (any new RPCS3-modelled behaviour; any new source)

- [ ] **Step 1: Write the docs.** `tests/scripts/test_docs.py` and `test_licence_headers.py` must pass.
- [ ] **Step 2: Full suite.**
  - Run `ctest --test-dir build`, then `.venv/bin/python -m pytest tests -q`, then the same with `GT6_TREE` set.
  - Then run `scripts/check_no_game_files.py $(git ls-files)`.
  - Record the counts in FINDINGS.
  - Confirm again that no RPCS3 log is left in `~/Library/Caches/rpcs3/`.
- [ ] **Step 3: Commit** `docs: milestone 3 handover`.

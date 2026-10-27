# Milestone 2: First Frame Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GT6's translated `EMAIN.SELF` runs as a native macOS program and presents at least one frame that the game itself drew.

**Architecture:** A dev-only script translates the player's decrypted v1.22 executables (PPU code, SPU images, SPURS job modules) with ps3recomp's tools into the player's own game folder. A CMake project in `port/` (adapted from ps3recomp's `templates/project`) compiles that output against ps3recomp's HLE runtime and Metal backend. A boot harness runs the result unattended, records how far it got and why it stopped, and the bring-up loop fixes blockers until the first guest flip is presented.

**Tech Stack:** Python 3 (.venv, pytest), ps3recomp v0.18.0 tools and runtime (submodule `third_party/ps3recomp`, pinned 4e8f3ca8), CMake 3.24+ / Ninja, Apple clang (C17/C++20/ObjC), Metal, SDL2, glslang and spirv-cross (Homebrew, dev only).

**Spec:** `docs/superpowers/specs/2026-10-27-gt6-mac-port-design.md` (milestone 2; sections 6.2, 6.3, 6.4, 6.6, risks 1, 2 and 6). Decisions so far: `docs/DECISIONS.md` D1-D24.

## Global Constraints

- Never commit game files, keys, firmware, decrypted executables or translated code. Every generated file (lifted C, objects, binaries, run logs, frame dumps) lives under the player's game folder (`$GT6_TREE`, e.g. `~/Gran Turismo 6/build/BCES01977-v1.22`), never inside the repository. Every new tool refuses an output path inside a git work tree (same rule as `gt6unpack` and `map_game.py`).
- No Sony firmware modules (liblv2, libsre, any PRX from `dev_flash`) are loaded or required. SPURS runs on ps3recomp's HLE (spec 6.3).
- Licences: new files carry `SPDX-License-Identifier: GPL-2.0-or-later`; files adapted from ps3recomp keep its MIT notice in the header and are credited in `THIRD-PARTY-NOTICES.md` and README Credits. `tests/scripts/test_licence_headers.py` must stay green.
- Every design decision goes in `docs/DECISIONS.md` as the next free D-number (D25 onwards), dated, with the reason. Measurements go in `docs/FINDINGS.md`, shortcuts in `docs/BACKLOG.md`.
- The ps3recomp submodule stays at 4e8f3ca8. Changes to it are carried only as patch files (Task 3) and each is upstreamable.
- Online calls answer "offline" (spec 2, non-goals); never let one hang the boot.
- The owner hands the Mac over in the evenings: long runs are unattended and must not open windows over the owner's work unless asked (`PS3RECOMP_METAL_HEADLESS=1` by default in the harness).
- Tests: `.venv/bin/python -m pytest tests/scripts -q` and `ctest --test-dir build` stay green without game data; integration tests that need the game skip visibly when `GT6_TREE` is unset (pattern: `tools/gt6unpack/tests/test_env.hpp`, and `pytest.skip` with a reason in Python).
- Pushing to GitHub needs the owner's OK. Work on branch `m2/first-frame`, merged into `main` locally at the end (owner rule).

## Facts this plan relies on (measured 2026-10-27 on the M4 Max, ps3recomp 4e8f3ca8)

- `ppu_lifter.py` on `USRDIR/EMAIN.SELF.elf` with `--functions <loader>/EMAIN.SELF.functions.json --hle-stubs <loader>/EMAIN.SELF.imports.json --chunks 64` and **no `--code-end`**: 224 s, 12.9 GB peak memory, 87,498 functions, **4.1 GB** of C++. About 3.7 GB of it is "functions" promoted from call targets inside read-only data and the embedded SPU programs (va 0x101BEA0 upward).
- Same with `--code-end 0x101BEA0` (end of the last executable section, section 4, `0x1011cc0 + 0xa1e0`): **21 s, 3.2 GB, 70,028 functions, 333 MB**, 64 chunks + `ppu_recomp_table.cpp`.
- Compiling all 65 chunks with Apple clang 21, `-std=c++20 -O1 -w -fwrapv -fno-strict-aliasing -ffp-contract=off`, 12 in parallel: **72 s wall**, 774 s CPU, largest chunk 16 s, peak 1.2 GB per compiler, 242 MB of objects.
- The generated sources need include paths `<lift dir>`, `ps3recomp/runtime/ppu` (for `ppu_vmx.h`), `ps3recomp/include`, `ps3recomp/runtime`.
- ps3recomp's runtime has no milestone event for a flip; draws log `rsx:draw_arrays` / `rsx:draw_indexed`. `PS3RECOMP_METAL_FRAME_DUMP` and `PS3RECOMP_METAL_HEADLESS` exist in `libs/video/rsx_metal_backend.m`. Unresolved imports log `[hle] UNRESOLVED NID 0x...` and fake CELL_OK.
- RPCS3's one boot of the 1.22 EBOOT (log `~/Library/Caches/rpcs3/RPCS3.log`) only shows its pre-compile scan; it does not show what the EBOOT's data-patch step writes. Task 4 settles that.
- Homebrew on this Mac has glslang 16.6.0, ninja, cmake; **sdl2 and spirv-cross are missing**.

## Review Focus

1. **A generated or run file lands in the repo.** `GT6_TREE` pointing into the repo, a relative path resolved from the repo root, or a symlink into it: every tool refuses with a clear message, and the port's CMake configure fails. Tests in Tasks 1, 3 and 5.
2. **A stale lift is compiled against a different ps3recomp or a different ELF.** `translate.json` records the ELF's SHA-256 and the ps3recomp commit; the port's configure refuses a mismatch. Tests in Tasks 1 and 3.
3. **The boot hangs instead of exiting.** A hang (no new milestone events for the idle window) is reported as `hung` with thread backtraces, and the child process is always killed, never left running overnight. Test in Task 5.
4. **A crash is reported as success.** A child killed by a signal, or one that exits 0 without a flip, is never `first_frame`. Test in Task 5.
5. **Running translate twice, or after a partial run.** The second run replaces the output atomically (staging folder plus rename, as `gt6unpack` does) and never mixes chunks from two runs. Test in Task 1.

---

### Task 1: Translate the PPU program

**Files:**
- Create: `scripts/translate_game.py`
- Create: `tests/scripts/test_translate_game.py`
- Create: `tests/scripts/fixtures/translate/` (tiny synthetic big-endian PPC64 ELF built by the test itself, not checked in as binary if it would trip the guard; build it in `tmp_path`)
- Modify: `docs/FINDINGS.md` (spike measurements above, as "Translating EMAIN (2026-10-27)"), `docs/DECISIONS.md` (D25, D26)

**Interfaces:**
- Consumes: `scripts/map_game.py`: `RUNNER`, `run_tool(python, tools, name, args, logs)`, `ps3recomp_commit(root)`, `sha256_file(path)`, `_inside(path, root)` (import the module as the tests do; do not copy code).
- Produces:
  - `code_end(elf_bytes: bytes) -> int`: highest `sh_addr + sh_size` over sections with `SHF_EXECINSTR` (0x4) in a big-endian ELF64; raises `ValueError` if there are none.
  - `translate(tree: Path, out: Path, python: str, tools: Path, chunks: int = 64, jobs: int | None = None) -> dict` returns the `translate.json` record.
  - Output layout: `<out>/ppu/ppu_recomp.h`, `<out>/ppu/ppu_recomp_NNN.cpp`, `<out>/ppu/ppu_recomp_table.cpp`, `<out>/loader/EMAIN.SELF.*.json`, `<out>/logs/`, `<out>/translate.json`. Default `<out>` is `<tree>/recomp`.
  - `translate.json` keys: `elf` (path relative to tree), `elf_sha256`, `ps3recomp_commit`, `code_end` (hex string), `chunks`, `functions` (int, parsed from the lifter's "N functions lifted" line), `seconds` (per step: `loader`, `lifter`), `spu` (filled by Task 2; `null` here).

- [ ] **Step 1: Write failing tests** in `tests/scripts/test_translate_game.py`:
  - `test_code_end_uses_last_exec_section`: build an ELF64 BE with sections `.text` (flags 0x6, addr 0x10200, size 0x100), `.stubs` (0x6, 0x10300, 0x20), `.rodata` (0x2, 0x10400, 0x1000); assert `code_end(...) == 0x10320`.
  - `test_code_end_no_exec_raises`: only flag-0x2 sections → `ValueError`.
  - `test_refuses_out_inside_git_tree`: `translate(tree, REPO / "x", ...)` raises `SystemExit` with a message containing `inside a git work tree`; nothing created.
  - `test_rerun_replaces_atomically`: with a fake `tools` folder whose `ppu_loader.py`/`ppu_lifter.py` are stub scripts that write marker files (the first run writes `ppu_recomp_000.cpp` and `ppu_recomp_001.cpp`, the second only `ppu_recomp_000.cpp`), assert that after the second run `ppu/` holds exactly the second run's files and no `*.staging` folder remains.
  - `test_record_fields`: same fakes; `translate.json` has every key listed above, `code_end` is `"0x10320"` for the fixture ELF, and `functions` equals the number the fake lifter printed.
  - `test_real_emain` (skips unless `GT6_TREE` is set): runs the real tools; asserts `functions > 60000`, `code_end == "0x101bea0"`, total size of `ppu/` under 600 MB.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/scripts/test_translate_game.py -q`. Expected: failures (module missing).
- [ ] **Step 3: Implement `scripts/translate_game.py`.** CLI: `translate_game.py <tree> [-o <out>] [--chunks 64] [--jobs N]`. Steps: `ppu_loader.py <elf> -o <staging>/loader`, then `ppu_lifter.py <elf> --functions ... --hle-stubs ... --code-end <hex> --chunks <n> [-j N] -o <staging>/ppu`, both through `map_game.run_tool` (isolated Python, D22). The ELF is `<tree>/decrypted/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF.elf`. Write into `<out>.staging`, then swap it in with a rename, keeping `<out>.old` until the swap succeeds (same recovery idea as `gt6unpack`'s build). Refuse an `<out>` inside a git work tree or inside the repo (resolve symlinks first). Module docstring in the style of `map_game.py`.
- [ ] **Step 4: Run the tests.** Expected: all pass; `test_real_emain` skipped without `GT6_TREE`, passing with `GT6_TREE=~/Gran\ Turismo\ 6/build/BCES01977-v1.22`.
- [ ] **Step 5: Docs.** FINDINGS: the spike numbers (both lifts and the compile). DECISIONS:
  - **D25**: the lift's code end is the end of the last executable ELF section, read from the section headers. Reason: without it 3.7 GB of data is lifted as code (FINDINGS).
  - **D26**: generated code, objects, binaries and run outputs live in the player's game folder (`<tree>/recomp`, `<tree>/port-build`, `<tree>/runs`). Reason: translated code is a derivative of the game (spec section 3).
- [ ] **Step 6: Commit** `feat(translate): lift EMAIN with code end from section headers`.

### Task 2: Translate the SPU programs and job modules

**Files:**
- Modify: `scripts/translate_game.py` (new `spu` step), `tests/scripts/test_translate_game.py`
- Modify: `docs/FINDINGS.md`, `docs/DECISIONS.md` (D27)

**Interfaces:**
- Consumes: Task 1's `translate()` and staging layout; `map_game.find_embedded_jobmods(buf)` and `jobmod_name(module)`; ps3recomp `tools/extract_spu_images.py`, `tools/lift_jobmods.py` (`--engine-elf`, `--register`, manifest), `tools/build_spu_workloads.py` (`--input`, `--constructor`, `--allow-partial`) as documented in `third_party/ps3recomp/docs/TOOLS.md`, `docs/SPU_LIFTER.md` and `templates/project/CMakeLists.txt` lines 127-171.
- Produces: `<out>/spu/` in the layout the template's `SPU_DIR` expects (`<image>/spu_recomp.c` per SPU image, plus `spu_workloads.c`, `jobmods_register.c`, `taskset_policy_bytes.c` where the tools make them); `translate.json["spu"] = {"images": int, "jobmods": int, "partial": [names that only lifted partially], "seconds": float}`.

- [ ] **Step 1: Write failing tests:** `test_spu_record_with_fake_tools` (fake tools write two image folders and a register file; assert `spu.images == 2`, `spu.jobmods` equals the fake manifest's count, `partial == []`), `test_spu_partial_is_recorded_not_fatal` (fake `build_spu_workloads.py` prints the partial marker and exits 0 under `--allow-partial`; assert the name appears in `partial` and the run still succeeds), `test_real_spu` (skips without `GT6_TREE`; `images == 4`, `jobmods == 57`).
- [ ] **Step 2: Run them.** Expected: fail.
- [ ] **Step 3: Implement.** Use `--allow-partial` so one hard SPU image does not block milestone 2. Every partial image is listed in `translate.json` and in FINDINGS, and each one counts as runtime fallback under D9 (O9).
- [ ] **Step 4: Run the tests.** Expected: pass (real test with `GT6_TREE`).
- [ ] **Step 5: Docs.** FINDINGS: counts, time, partial list. **D27**: SPURS and SPU work run on ps3recomp's HLE SPURS with lifted SPU code and its interpreter as the logged fallback. No firmware LLE. Reason: spec 6.3 (the shipped default must work without Sony modules), and O9.
- [ ] **Step 6: Commit** `feat(translate): lift GT6's SPU images and SPURS job modules`.

### Task 3: The port project builds a native `gt6` binary

**Files:**
- Create: `port/CMakeLists.txt` (adapted from `third_party/ps3recomp/templates/project/CMakeLists.txt`, MIT notice kept)
- Create: `port/main.cpp` (adapted from the template's `main.cpp`)
- Create: `port/gt6_overrides.cpp` (GT6-specific HLE overrides and the `ps3_load_prx_modules()` hook, empty to start)
- Create: `patches/ps3recomp/0001-milestone-event-on-flip.patch`
- Create: `scripts/apply_ps3recomp_patches.sh`
- Create: `tests/scripts/test_port_project.py`
- Modify: `CMakeLists.txt` (root: `option(GT6_BUILD_PORT "Build the game port (needs GT6_TREE)" OFF)`, `add_subdirectory(port)` when ON), `THIRD-PARTY-NOTICES.md`, README Credits, `docs/DECISIONS.md` (D28, D29, D30), `docs/BACKLOG.md`

**Interfaces:**
- Consumes: Task 1/2 output layout and `translate.json`.
- Produces:
  - Configure: `cmake -S . -B "$GT6_TREE/port-build" -G Ninja -DGT6_BUILD_PORT=ON -DGT6_TREE="$GT6_TREE" -DCMAKE_BUILD_TYPE=Release`. Executable `"$GT6_TREE/port-build/port/gt6"`, run as `gt6 <path to EMAIN.SELF.elf>`.
  - `RECOMP_DIR = ${GT6_TREE}/recomp/ppu`, `SPU_DIR = ${GT6_TREE}/recomp/spu`, `PS3_VFS_ROOT` default `${GT6_TREE}/dev_bdvd`. The `dev_hdd0` mapping points at `${GT6_TREE}/dev_hdd0` (through the runtime's cellFs mapping API, `docs/CELLFS_VFS_ROOT.md`).
  - Milestone key `gcm:flip`, emitted once per guest flip request that reaches present, through `ps3_ms("gcm:flip")` in `libs/video/cellGcmSys.c` (patch 0001).
  - `scripts/apply_ps3recomp_patches.sh [--check]` applies `patches/ps3recomp/*.patch` in order to `third_party/ps3recomp` with `git apply`. It is idempotent: a patch that is already applied (`git apply --reverse --check` succeeds) is skipped. `--check` exits non-zero if any patch neither applies nor is already applied.

- [ ] **Step 1: Install the dev dependencies:** `brew install sdl2 spirv-cross`. Record the versions in FINDINGS.
- [ ] **Step 2: Write failing tests** in `tests/scripts/test_port_project.py`:
  - `test_configure_refuses_tree_inside_repo`: `cmake -S <repo> -B <tmp> -DGT6_BUILD_PORT=ON -DGT6_TREE=<repo>/tmp-tree` fails, and stderr contains `GT6_TREE must be outside the repository`.
  - `test_configure_refuses_stale_lift`: a fake tree whose `recomp/translate.json` has `ps3recomp_commit` `"0000000"`. Configure fails with `translated with a different ps3recomp`.
  - `test_root_build_without_port_unchanged`: a default configure (no `GT6_BUILD_PORT`) still builds `gt6unpack` only.
  - `test_patches_apply_check`: `scripts/apply_ps3recomp_patches.sh --check` exits 0.
  - `test_real_port_builds` (skips without `GT6_TREE`, marked slow): configure and build. `gt6` exists, and running it without arguments exits non-zero with a usage line.
- [ ] **Step 3: Run them.** Expected: fail.
- [ ] **Step 4: Write patch 0001 and the apply script.** Generate the patch with `git diff` inside the submodule after editing, then `git checkout .` there, so the submodule checkout stays at the pin and the patch file is the only carrier. Each patch begins with a header naming its upstream status (`Upstream: not yet submitted`).
- [ ] **Step 5: Write `port/CMakeLists.txt`, `port/main.cpp`, `port/gt6_overrides.cpp`.** Start from the template and change only what GT6 needs:
  - the GT6_TREE checks: outside the repo; `translate.json` present; its `ps3recomp_commit` equals `git -C third_party/ps3recomp rev-parse HEAD`; its `elf_sha256` equals the SHA-256 of the ELF;
  - run the apply script at configure time;
  - VFS roots;
  - `-O1` for lifted PPU sources, `-O2` for SPU, as in the template (D30);
  - macOS only.

  Keep the template's frame clock, CFRunLoop main thread and Metal init.
- [ ] **Step 6: Run the tests.** Expected: pass. With `GT6_TREE` set, record the full build's wall time in FINDINGS (expected about 72 s for the lifted code, plus the runtime).
- [ ] **Step 7: Docs.**
  - **D28**: ps3recomp changes are carried as patch files in `patches/ps3recomp/`, applied at configure time, each written so it can go upstream. Reason: the pinned submodule stays a clean upstream commit, every change can be reviewed, and nothing needs a fork pushed before the owner agrees.
  - **D29**: during development the port builds with the tools on this Mac (Apple clang, Homebrew sdl2, glslang and spirv-cross). Bundling them for players follows O12 later. Log this in BACKLOG under Mac GUI, together with "players need Python for translation today".
  - **D30**: lifted PPU code is compiled at `-O1` (72 s on the M4 Max). The optimisation level is revisited in milestone 5 (locked 60) with measurements.
  - Credits: ps3recomp's project template (MIT).
- [ ] **Step 8: Commit** `feat(port): native gt6 binary from the lifted program`.

### Task 4: What the 1.22 EBOOT leaves on disk, and the launch contract

**Files:**
- Create: `scripts/eboot_effects.py` (dev-only)
- Create: `tests/scripts/test_eboot_effects.py`
- Modify: `docs/FINDINGS.md`, `docs/DECISIONS.md` (D31). Possibly `tools/gt6unpack` (only if the findings require it; see Step 4).

**Interfaces:**
- Produces:
  - `snapshot(root: Path) -> dict[str, str]`: relative path to SHA-256 for every file, plus `"<dir>/"` entries for folders.
  - `diff(before, after) -> {"added": [...], "removed": [...], "changed": [...]}`, sorted.
  - A FINDINGS entry listing exactly what the EBOOT changes.
  - The launch contract the port uses: the process path the game sees (`/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF`), its argv and its environment as RPCS3 passes them after `sceNpDrmProcessExitSpawn2`.

- [ ] **Step 1: Tests:** `test_snapshot_and_diff` covers an added file, a removed file, a changed file and a new folder in `tmp_path`, and `diff` lists each in the right bucket.
- [ ] **Step 2: Implement `snapshot`/`diff`, and a CLI:** `eboot_effects.py snapshot <dir> -o <json>`, `eboot_effects.py diff <a.json> <b.json>`.
- [ ] **Step 3: Experiment, unattended and outside the repo.**
  1. Make an APFS clone of `$GT6_TREE/dev_hdd0/game/BCES01977` with `cp -c -R`.
  2. Install it as RPCS3's `dev_hdd0/game/BCES01977`. Before doing so, move aside any existing folder there and record that you did.
  3. Snapshot it, then boot RPCS3 (`~/Developer/others/rpcs3-bin/RPCS3.app`, `--no-gui`) on `/dev_hdd0/game/BCES01977/USRDIR/EBOOT.BIN` until the log shows EMAIN loading, or for 180 s at most, and stop it. Snapshot again and diff.
  4. Also take the EMAIN argv from RPCS3's log (`sys_game_process_exitspawn2`/`sceNpDrmProcessExitSpawn2` arguments).
  5. Remove the clone afterwards and restore whatever was moved aside.
  6. Never copy RPCS3's log into the repo: it contains the klicensee. Quote only non-key lines.
- [ ] **Step 4: Rule.** If the diff only touches `update.txt`/`UPDATENODEINFO.upd` and renames inside `TPPS-*`, decide whether EMAIN reads them (search the log for EMAIN opening them). If EMAIN needs any of it, add the same changes as a post-install step to `gt6unpack build` with tests, and refresh the manifest. Otherwise record that nothing is needed.
  - **D31**: the port starts `EMAIN.SELF` directly with the launch contract above. The 1.22 `EBOOT.BIN` is not translated, and its on-disk effects are reproduced, or shown to be unneeded, per FINDINGS.
- [ ] **Step 5: Commit** `docs: what the 1.22 EBOOT changes, and how EMAIN is launched`, plus `feat(unpack): ...` if Step 4 needed code.

### Task 5: Boot harness

**Files:**
- Create: `scripts/boot_game.py`
- Create: `tests/scripts/test_boot_game.py`
- Create: `tests/scripts/fixtures/boot/` (fake `gt6` programs written as Python scripts, made executable by the test)

**Interfaces:**
- Consumes: Task 3's `gt6` binary and Task 4's launch contract; milestone log format (`runtime/milestone.c`: header `# ps3recomp milestone log v1`, lines `<ord>\t<key>`, `kv\t<key>\t<n>`, `# counts`, `count\t<key>\t<bucket>`, `# end`).
- Produces:
  - `parse_milestones(text: str) -> {"keys": [str in order], "kv": {str: int}, "ended": bool}`.
  - `classify(returncode: int | None, timed_out: bool, hung: bool, keys: list[str]) -> str`, one of `first_frame`, `exited`, `crashed`, `hung`, `timeout`.
    - `first_frame` if `"gcm:flip"` is in `keys` and the run did not crash. It wins over `exited` and `timeout`.
    - `crashed` if the return code is negative (killed by a signal) or above 128.
  - `boot(gt6: Path, tree: Path, seconds: int = 300, idle: int = 60, headless: bool = True, env: dict | None = None) -> dict`. It writes `<tree>/runs/<UTC yyyymmdd-HHMMSS>/` holding `stdout.log`, `stderr.log`, `milestones.log`, `frames/` (`PS3RECOMP_METAL_FRAME_DUMP`), `report.json` and `summary.md`.
    - `report.json` keys: `outcome`, `seconds`, `returncode`, `last_keys` (last 20), `unresolved_nids` (from `[hle] UNRESOLVED NID 0x...` lines), `unimplemented_syscalls` (`lv2_syscall N (stub)`), `frames` (count of dump files), `backtraces` (text for `hung`, from `/usr/bin/sample <pid> 3`).
    - `summary.md` opens with one plain sentence about the outcome, for the owner.
  - Environment set by default: `PS3_MILESTONE_OUT`, `PS3RECOMP_METAL_HEADLESS=1` when headless, `PS3RECOMP_METAL_FRAME_DUMP=<run>/frames`, `PS3_VFS_ROOT`.
  - CLI: `boot_game.py <tree> [--gt6 PATH] [--seconds N] [--idle N] [--window]`. It exits 0 on `first_frame`, otherwise 1.

- [ ] **Step 1: Write failing tests:**
  - `test_parse_milestones`: a sample log with keys, kv and counts.
  - The classify table:
    - flip, then exit 0 gives `first_frame`.
    - flip, then signal -11 gives `crashed`.
    - exit 0 with no flip gives `exited`.
    - timed out with a flip gives `first_frame`.
    - no new key for `idle` seconds gives `hung`.
  - `test_boot_fake_hang_is_killed`: a fake that sleeps forever. The outcome is `hung`, the child pid no longer exists afterwards, and `backtraces` is non-empty.
  - `test_boot_fake_crash`: a fake that writes a few keys and then calls `os.kill(os.getpid(), SIGSEGV)`. The outcome is `crashed`, and `last_keys` ends with the fake's last key.
  - `test_boot_collects_unresolved`: the fake prints two `UNRESOLVED NID` lines, and both appear in the report.
  - `test_refuses_tree_inside_repo`.
- [ ] **Step 2: Run them.** Expected: fail.
- [ ] **Step 3: Implement.**
  - Watch the milestone file's growth to detect hangs.
  - Always kill the whole process group on exit, timeout or hang (`start_new_session=True`, then `os.killpg`).
  - Never leave a child running.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** `feat(boot): unattended boot harness with outcome report`.

### Task 6: Bring-up to the first presented frame

This task is a loop, run by the controller with superpowers:systematic-debugging, not handed to one implementer. Each round:

1. Run `scripts/boot_game.py "$GT6_TREE"`.
2. Read `report.json`.
3. Find the root cause of the first blocker.
4. Fix it in the smallest right place.
5. Re-run.

**Where fixes go:**
- Behaviour specific to GT6 goes in `port/gt6_overrides.cpp`, or a new `port/gt6_*.cpp` file per subsystem.
- A generic runtime or lifter bug becomes a new `patches/ps3recomp/NNNN-*.patch` with its own test inside ps3recomp's test layout where one exists.
- An unresolved NID that GT6 calls during boot gets a real implementation if it matters for boot. Otherwise it gets an explicit "offline" or "not available" answer modelled on RPCS3's behaviour (credited), never a silent fake OK for online functions.

**Per round, append a row to FINDINGS "Bring-up log":** round, what stopped it (key/NID/signal), root cause, fix, outcome after. Every fix that is a design choice gets a D-number.

- [ ] **Step 1: First boot.** Record the outcome as round 1.
- [ ] **Step 2: Rounds until the outcome is `first_frame`.** Expected early blockers (from the ps3recomp survey):
  - the sysPrxForUser CRT (`sys_initialize_tls`, `sys_mempool_*`);
  - GCM memory layout (`ppu_hle_inject_base` versus GT6's `cellGcmMapMainMemory`);
  - SPURS initialisation with GT6's attributes;
  - the 217 unnamed NIDs: add names from RPCS3 to the port's NID table for logging, and offer the list upstream later.
- [ ] **Step 3: Acceptance.** `report.json` `outcome == "first_frame"`, `frames >= 1`. Look at the first dumped frame and describe it in FINDINGS (for example "solid colour", "loading screen"). Never commit the image: it is game output.
- [ ] **Step 4: Stop conditions other than success.** Each of these goes to the owner with evidence:
  - a blocker that would need Sony firmware modules;
  - a change that breaks a recorded decision;
  - ps3recomp turning out unsuitable (spec 6.2).

  Record the state in FINDINGS and `CLAUDE.md`, then stop.
- [ ] **Step 5: Commit per round**, for example `fix(port): <blocker>` or `fix(ps3recomp-patch): <blocker>`.

### Task 7: Docs, handover, owner summary

**Files:**
- Modify: `README.md` (status: milestone 2; a "Translate and boot (developer preview)" section with the commands from Tasks 1, 3 and 5; Credits), `CLAUDE.md` (state, paths, the new old-name URL fix), `docs/superpowers/specs/2026-10-27-gt6-mac-port-design.md` line 5 (repo URL is now `https://github.com/Wooloomooloo2/Gran_Turismo_6_Mac_Port`), `docs/FINDINGS.md` (owner summary for milestone 2 at the top, plain language, 4-row table like milestone 1's), `docs/BACKLOG.md` (anything parked during bring-up), `THIRD-PARTY-NOTICES.md`.

- [ ] **Step 1: Write the docs.** `tests/scripts/test_docs.py` and `test_licence_headers.py` must pass.
- [ ] **Step 2: Full suite.** Run `ctest --test-dir build`, `.venv/bin/python -m pytest tests -q`, and the same with `GT6_TREE` set. Then run `scripts/check_no_game_files.py $(git ls-files)`. Record the counts in FINDINGS.
- [ ] **Step 3: Commit** `docs: milestone 2 handover`.

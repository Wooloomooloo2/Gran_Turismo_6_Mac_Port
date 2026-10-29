# CLAUDE.md: Gran Turismo 6 for Mac (session handover)

Read this first, then `docs/superpowers/specs/2026-10-27-gt6-mac-port-design.md` (design),
`docs/DECISIONS.md` (decisions), `docs/FINDINGS.md` (measurements), `docs/BACKLOG.md`
(deferred work: log the proper fix there under 1) Stability, 2) Performance, 3) Mac GUI
whenever a shortcut is taken).

## How to write for the owner

The owner does not write code. Decades running large technology change programmes, so assume
full fluency in systems, delivery, risk and trade-offs, but none in language-specific detail.
The owner makes every product and architecture decision.

- Lead with the decision, outcome or risk. Mechanism only if asked.
- Questions must be answerable from their consequence for the player alone. No code or API
  names in questions.
- Keep summaries to a few sentences or a small table; long reasoning goes in docs.
- The owner hands the Mac over in the evenings for long unattended runs and wants a short
  morning summary (outcome first). Daytime work must not disturb the owner's use of the machine.

## What this repo is

A native Apple Silicon port of Gran Turismo 6 (PS3) by static recompilation, not emulation.
GitHub: https://github.com/Wooloomooloo2/Gran_Turismo_6_Mac_Port (public). Licence GPL-2.0-or-later,
except `tools/gt6unpack/` (GPL-2.0-only: it holds RPCS3-derived code, D24).

## Decisions already made (don't re-litigate)

See `docs/DECISIONS.md`: the owner decisions D1-D12 and D15. Headlines: native translation not emulation (D1); target
BCES-01977 v1.22 (D3); handling must match the PS3 exactly (D10); public PS3 keys live in
source (D15). Anything that would change one goes to the owner with evidence.

## Machine and paths

- Host: Apple M4 Max, macOS, arm64. Python venv at `.venv/` (`python3 -m venv .venv &&
  .venv/bin/pip install -r scripts/requirements-dev.txt`). Tests: `.venv/bin/python -m pytest tests/scripts -q`.
- Disc ISO: `~/Gran Turismo 6/Gran Turismo 6 (UK)/Gran Turismo 6 (UK).iso`. Leave untouched.
- Updates 1.02-1.22 (verified): `~/Gran Turismo 6/updates/`.
- RPCS3 source (reference): `~/Developer/others/rpcs3/`; binary: `~/Developer/others/rpcs3-bin/`.
- **Never commit game files, keys, firmware or translated code.** Run `scripts/install_hooks.sh`
  once; `scripts/check_no_game_files.py` blocks PS3 signatures. Never push without the owner's say-so.

## State as of 2026-10-27

Milestone 1 (unpack and map) is done on `m1/unpack`; milestone 2 is done on `m2/first-frame`
(neither pushed). `gt6unpack build` makes a verified v1.22 tree at
`~/Gran Turismo 6/build/BCES01977-v1.22` (`$GT6_TREE`). Milestone 2 adds, all dev-only:
`scripts/translate_game.py` (translation into `$GT6_TREE/recomp`), `scripts/prepare_play.py`
(play folder `$GT6_TREE/play`), the port (`port/`, `-DGT6_BUILD_PORT=ON -DGT6_TREE=...`, binary
`$GT6_TREE/port-build/port/gt6`) and `scripts/boot_game.py` (runs in `$GT6_TREE/runs/`). The
README section "Translate and boot" has the commands. ps3recomp changes are patches 0001-0009 in
`patches/ps3recomp/` (D28). Outcome: the game reaches `first_frame` on fresh play folders; the
dumped frame is solid black while GT6 runs its first-run install, and whether that is
"cleared" or "nothing drawn" is unknown until compared with an RPCS3 capture. Likely next
blocker: three unimplemented `cellFiberPpuContext*` imports that fake success.
Dev tools: Homebrew `sdl2 spirv-cross` (D29). Suite: 2 ctest, 158 pytest with `GT6_TREE`
set (153 + 5 skipped without), 71 C++ cases (4 integration cases need `GT6_DISC_DIR`/`GT6_UPDATES_DIR`).
Facts in `docs/FINDINGS.md`; decisions D1-D34.

Milestone 3 (first menu) is on `m3/first-menu` (Task 5 bring-up, FINDINGS "Bring-up log (milestone 3)"). As of batch 13: ps3recomp patches 0001-0050; decisions to D75. Runs ignore controllers paired with the Mac (D65, `--host-pad` to allow). A first boot reaches GT6's first menu on a new save, the first-run player page (player-name panel, OK button, "Welcome to Gran Turismo 6!" box, on a flat background), about 110 s in, with all its text (D71); the verdict is `runs/20261029-030728/verdict.json` (re-captured after D74; agent judgement, for the owner to confirm by eye; no RPCS3 reference menu). Every presented frame is now the 1280x720 display buffer the game flipped (D74: `cellGcmSetPrepareFlip` returned 0, so every flip showed buffer 0, and the whole surface was presented). With `--press 45:cross --press 75:cross --press 125:cross --press 145:cross --press 165:cross --press 185:cross --press 200:down --press 210:cross --press 225:down --press 235:cross --osk-text John --osk-text Smith` the names go in through the on-screen keyboard (D75, answered by the host), GT6 confirms "John Smith / J. Smith" and starts its first drive at Brands Hatch (tutorial boxes, HUD, AUTO DRIVE with Cross held); the 3D world is not drawn there yet and presents drop to a few a second. The main menu ("My Home") comes after that drive and is not reached yet. A second boot still stays on a black movie screen (BACKLOG: the main thread waits on a sync with GT6's task fiber, whose job is no longer queued). Each port build has a tree stamp (D72). Deliberate test crashes leave no macOS crash report (D63).

## Next steps

Milestone 3: reach the first menu. First: (1) capture what RPCS3 shows at the same point and
compare with our first frame; (2) implement the `cellFiberPpuContext*` calls (BACKLOG, 1) so
the first-run install can finish; (3) work through the 12 faked imports in `docs/BACKLOG.md`.
Plan it first (in `.superpowers/sdd/`, local only).

Also see `docs/BACKLOG.md`.

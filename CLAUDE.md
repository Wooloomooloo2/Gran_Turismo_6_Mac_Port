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
GitHub: https://github.com/Wooloomooloo2/Gran-Turismo-6-Mac (public). Licence GPL-2.0-or-later.

## Decisions already made (don't re-litigate)

See `docs/DECISIONS.md` D1-D15. Headlines: native translation not emulation (D1); target
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

Milestone 1 is done on branch `m1/unpack` (not pushed). `gt6unpack build` makes a verified
v1.22 tree at `~/Gran Turismo 6/build/BCES01977-v1.22`; `scripts/map_game.py` maps the code
(about 72k functions, 740 imports, 4 SPU programs plus 57 SPURS job modules in EMAIN).
Full suite with real data: 59 C++ cases and 25 Python tests, none skipped (set `GT6_DISC_DIR`
to the mounted ISO and `GT6_UPDATES_DIR`). Facts in `docs/FINDINGS.md`; decisions D1-D23.

## Next steps

Milestone 2: the translated program starts and draws something. Plan it first (in
`.superpowers/sdd/`, local only). Its first questions:

1. The EBOOT data-patch step (PDIPFS/TPPS): what it leaves on disk, and do we reproduce it?
2. SPURS/SPU strategy: the 57 job modules are raw in EMAIN; job chains and tasks are needed.
3. Compile time and size of translating 72k functions.

Also see `docs/BACKLOG.md` (milestone 2 open questions and polish list).

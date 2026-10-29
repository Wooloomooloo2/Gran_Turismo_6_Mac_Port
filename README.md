# Gran Turismo 6 for Mac

Play Gran Turismo 6 on Apple Silicon Macs as a native Mac app, from your own copy of the
game, without the stutter, freezes and crashes of running it under a PS3 emulator.

This is **not an emulator**. The game's own program code is translated ahead of time (static
recompilation) from PS3 machine code into Apple Silicon code and runs as a real macOS process.
The PS3's system software is replaced by a Mac runtime, and its graphics commands become Metal.

> **No game files or copyrighted assets are included, and none will ever be distributed.**
> You must provide your own legally owned copy of Gran Turismo 6 (European edition
> BCES-01977 for now). Translation of the game's code runs on your Mac, and the translated
> code never leaves it. This project is not affiliated with or endorsed by Sony Interactive
> Entertainment or Polyphony Digital.

## Status: pre-alpha, milestone 3 reached (first menu)

Milestone 3 ("reach the first menu") is reached, pending the owner's check by eye. On a new
save GT6's first menu is its first-run player page, and the Mac build shows it with all its
text (the name fields, the OK button and the "Welcome to Gran Turismo 6!" box) about two
minutes after starting. That needs a play folder whose first-run install is already done and
five scripted button presses ("To get to GT6's first menu" below). Two black rectangles above
the name panel are not explained yet. With scripted button presses and placeholder names the game goes
further: it accepts the names, shows its confirmation screen and starts its first drive at
Brands Hatch, with the tutorial boxes and the driving display. Nothing is playable yet.

Known gaps, carried into milestone 4:

- In that first drive the 3D world is not drawn (the track is black behind the driving
  display), and the frame rate drops to a few frames a second.
- A second start of the game, after the first, stays on a black screen.
- The on-screen keyboard is answered by the program itself; there is no text field for the
  player yet.
- On the player page, two black rectangles above the name panel look like something not yet
  drawn, and some runs show the page's text without its panel for a few seconds.

| Milestone | Outcome | State |
|---|---|---|
| 1 | Game unpacked, verified as v1.22, fully mapped | done |
| 2 | Translated program starts on the Mac and draws something | done |
| 3 | Reach the first menu | reached: the first-run player page with its text; got as far as the first drive (owner's eye check pending) |
| 4 | A race | next: the 3D world in the drive, then the frame rate |
| 5 | Locked 60 FPS | not started |
| 6 | MetalFX upscaling to 4K | not started |
| 7 | Racing wheel support | not started |

Online play is out of scope (Sony shut the servers down in 2018).

## Unpack your copy (developer preview)

This turns your own disc image and the official updates into a verified version 1.22 game
folder. It is a developer tool for now; nothing is playable yet. It needs an Apple Silicon Mac
with Xcode's command line tools and CMake, a decrypted disc image of BCES-01977 (`.iso`),
and the update files from Sony's update server: 21 packages, 1.02 to 1.22, 11.2 GB, as named
in the list Sony publishes for the title (`BCES01977-ver.xml`). Each package is checked against
Sony's SHA-1 before anything is written. A downloader that fetches them for you is planned
(see `docs/BACKLOG.md`).

```sh
# 1. Build the tool (from the repository folder).
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build

# 2. Mount the disc image read-only. The tool reads a folder, not the .iso itself.
mkdir -p /private/tmp/gt6iso
hdiutil attach -readonly -nobrowse -mountpoint /private/tmp/gt6iso "/path/to/Gran Turismo 6.iso"

# 3. Build the game folder. --out must be a new folder outside this repository
#    (the tool refuses a folder inside a git work tree). About 25 GB; a few minutes.
build/tools/gt6unpack/gt6unpack build --disc /private/tmp/gt6iso \
    --updates "/path/to/updates" --out "/path/to/build/BCES01977-v1.22"

# 4. Check it against the recorded v1.22 hashes. "0 mismatched, 0 missing" means it matches.
build/tools/gt6unpack/gt6unpack verify "/path/to/build/BCES01977-v1.22" \
    --manifest manifests/BCES01977-v1.22.json

# 5. Unmount the disc image.
hdiutil detach /private/tmp/gt6iso
```

`--force` rebuilds over a folder that an earlier `gt6unpack build` made; it never replaces
any other folder. Keep the game folder outside this repository so its files can never be
committed.

## Translate and boot (developer preview)

This translates the game's code, builds the Mac program and starts it for a few seconds. It is
a developer tool; it does not play the game. It needs the verified game folder from the step
above (called `$GT6_TREE` here), Python with the dev packages, CMake, Ninja, Apple's command
line tools, and three Homebrew packages: `brew install sdl2 glslang spirv-cross`. Everything
generated goes into `$GT6_TREE`, never into this repository.

```sh
export GT6_TREE="/path/to/build/BCES01977-v1.22"

# 1. Once: Python environment.
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements-dev.txt

# 2. Translate the game's code to C/C++ (58 s on an M4 Max, FINDINGS). It first applies
#    patches/ps3recomp to third_party/ps3recomp and refuses unless every patch is in.
.venv/bin/python scripts/translate_game.py "$GT6_TREE"

# 3. Make the play folder the game runs on (a clone of the tree's dev_hdd0 with the
#    launcher's on-disk changes applied). --force replaces one an earlier run used, and
#    with it any first-run install that run did (see "To get to GT6's first menu").
.venv/bin/python scripts/prepare_play.py "$GT6_TREE" --force

# 4. Build the Mac program (78 s on an M4 Max, FINDINGS; the lifted code is built at -O1,
#    D30). The build folder must be outside this repository and any git work tree; the
#    binary is $GT6_TREE/port-build/port/gt6.
cmake -S . -B "$GT6_TREE/port-build" -G Ninja -DGT6_BUILD_PORT=ON \
      -DGT6_TREE="$GT6_TREE" -DCMAKE_BUILD_TYPE=Release
cmake --build "$GT6_TREE/port-build" --target gt6

# 4b. The first-run install replaces USRDIR/EMAIN.SELF with a newer program (D44), so
#     translate and build that one too; the port starts whichever the play folder holds.
#     Repeat steps 2, 4 and 4b for every image after any change to patches/ps3recomp or the
#     submodule: boot_game.py refuses to run while a build is from another patch set (D47).
.venv/bin/python scripts/translate_game.py "$GT6_TREE" -o "$GT6_TREE/recomp-tpps122" \
      --elf decrypted/dev_hdd0/game/BCES01977/USRDIR/TPPS-01.22/EMAIN.SELF.elf
cmake -S . -B "$GT6_TREE/port-build-tpps122" -G Ninja -DGT6_BUILD_PORT=ON \
      -DGT6_TREE="$GT6_TREE" -DGT6_RECOMP="$GT6_TREE/recomp-tpps122" -DCMAKE_BUILD_TYPE=Release
cmake --build "$GT6_TREE/port-build-tpps122" --target gt6

# 4c. Once, after a passing `gt6unpack verify`: make the verified disc layer read-only, so
#     nothing can change it (D46; boot_game.py refuses while it is writable). Undo with
#     chmod -R u+w before anything that must write there.
chmod -R a-w "$GT6_TREE/dev_bdvd"

# 5. Start it unattended. It stops 5 s after the first flip, when the process exits,
#    when it hangs (--idle) or after --seconds. Options: --seconds N, --idle N, --window.
.venv/bin/python scripts/boot_game.py "$GT6_TREE"

# 5b. A long run: keep going after the first flip and keep a series of frames.
.venv/bin/python scripts/boot_game.py "$GT6_TREE" --until time --seconds 240 --png
```

Options for long runs (D35):

- `--until time` runs to `--seconds` instead of stopping 5 s after the first flip; a run that
  reaches the limit without crashing is `timeout`, with its frames kept, and one that ends by
  itself first is `exited` (`--until flip`, the default, is the old behaviour).
- `--frame-every N` dumps presented frame 1 and every N-th after it (default 60).
- `--frame-max N` dumps at most N frames per run (default 300). Dumps also stop by themselves
  when `frames/` passes 2 GB or the disk has less than 20 GB free (`dump_stopped` in
  `report.json`).
- `--png` copies the dumped frames to `frames_png/` as PNG (with macOS `sips`) for viewing.
- `--prune` deletes all but the newest 10 runs in `$GT6_TREE/runs` after this one.
- `--play play-SUFFIX` runs on `$GT6_TREE/play-SUFFIX`, made with `prepare_play.py --name
  play-SUFFIX`, instead of `$GT6_TREE/play` (D49). Saves and trophies stay inside the play
  folder (`dev_hdd0/home/00000001/savedata`, `trophies/`), and the port runs in the run folder
  (D50).
- `--press [IMAGE@]SECONDS:BUTTON` (repeatable) presses a pad button that many seconds after
  the game first polls the pad, e.g. `--press 480:cross` for GT6's "Installation complete."
  dialog; `2@30:cross` aims at the first exit-spawned program instead of the first (D40).
  Buttons: cross, circle, triangle, square, start, select, the d-pad, l1-l3, r1-r3.
- `--host-pad` lets a controller paired with this Mac reach the game; by default runs ignore
  it, so a pad left switched on cannot press buttons in an unattended run (D65).
- `--gt6 BINARY` runs another build than `$GT6_TREE/port-build/port/gt6` (it must still be
  current for the patch set, D47).
- `--osk-text TEXT` (repeatable) answers the game's on-screen keyboards in order, e.g.
  `--osk-text John --osk-text Smith` for GT6's player-name page; without it each keyboard is
  confirmed with the text it opened with (D75).

`scripts/prepare_play.py --name play-SUFFIX` makes a second play folder beside `play` (D49),
so a run can keep one folder (a finished first-run install, say) while another is used.

To get to GT6's first menu on a new save (milestone 3) the play folder must already hold a
finished first-run install, which takes about 8 minutes. Make one once and keep it, then run
each boot on an APFS clone of it (`cp -c -R` copies in a moment and takes no extra disk until
the game writes):

```sh
# Once: a play folder with the first-run install done. Cross at 480 s answers
# "Installation complete."; GT6 then restarts itself into its new program (a spawn in
# report.json) and the run ends by itself or at --seconds.
.venv/bin/python scripts/prepare_play.py "$GT6_TREE" --name play-installed
.venv/bin/python scripts/boot_game.py "$GT6_TREE" --play play-installed --until time \
      --seconds 540 --press 480:cross

# Each time: a fresh clone (any new name), then the presses below.
cp -c -R "$GT6_TREE/play-installed" "$GT6_TREE/play-run1"
.venv/bin/python scripts/boot_game.py "$GT6_TREE" --play play-run1 --until time --seconds 300 \
      --png --press 45:cross --press 75:cross --press 125:cross --press 145:cross --press 165:cross
```

A clone carries the install run's "used" mark, so `boot_game.py` warns that the folder was
already used and `report.json` names the install run in `play_reused`. That is expected for
a clone: do not run `prepare_play.py --force` on it or on `play-installed`, because that
wipes the install. Delete a clone (`rm -rf`) when its run is done. The scripted presses are `--press 45:cross --press 75:cross --press
125:cross --press 145:cross --press 165:cross` (past the screen-adjust page, the opening movie,
the welcome boxes); the player page is up at about 110 s. `--press 185:cross --press 200:down
--press 210:cross --press 225:down --press 235:cross --osk-text John --osk-text Smith` then
enters two placeholder names and confirms them, and further Cross presses go through the
first drive's tutorial boxes.

Each boot writes `$GT6_TREE/runs/<date-time>/` with `report.json` (outcome, frames, unresolved
imports), `summary.md`, the logs, the dumped frames (`frames/frame_<present>.ppm`) and
`draw_stats.txt` (one `<present> <draw calls> <clears>` line per presented frame).
`report.json` lists each dumped frame with its draw calls, clears and share of non-black pixels
(`frames_list`), and counts the frames that were really drawn: at least one draw call and more
than 1% non-black pixels (`drawn_frames`, `first_drawn`). The outcome is `first_frame` only
when the game flipped a frame and at least one frame was dumped (`flip_no_frame` otherwise). A
play folder that a run has used is not clean: for a clean boot from scratch, run step 3 with
`--force` before the next boot (`boot_game.py` warns when you have not). For runs that start
from a finished install, use a fresh clone instead, as above; there the warning is expected. Re-run step 2 after changing anything under
`patches/`. To take the patches back out of the submodule:
`git -C third_party/ps3recomp checkout . && git -C third_party/ps3recomp clean -fd`.

## Guard against game files

`scripts/check_no_game_files.py` refuses a file when any of these is true:

- it is larger than 50 MB;
- it starts with a PS3 file signature: SCE container (SELF, SPRX), PKG, firmware PUP,
  PARAM.SFO, EDAT/SDAT, trophy file (TRP), or a PS3 PPU or SPU ELF;
- its SHA-256 is listed in a manifest under `manifests/` (the hashes of every file of a
  built v1.22 game folder). This catches game files that carry no signature at all, which is
  most of them.

It cannot recognise game files from other versions or editions that have no signature, so
`gt6unpack build` also refuses to write its output inside a git work tree. Run
`scripts/install_hooks.sh` once after cloning to install the check as a pre-commit hook; CI
runs it on every push.

## Credits

- [RPCS3](https://github.com/RPCS3/rpcs3) (GPL-2.0-only): reference for PS3 behaviour. The
  unpacker's key table, SELF decryption and package reader are adapted from its
  `rpcs3/Crypto` code (`key_vault`, `unself`, `unpkg`).
- [ps3recomp](https://github.com/sp00nznet/ps3recomp) (MIT) by Ned Heller / sp00nznet: its
  tools map and translate the game's code (git submodule, dev-only), its runtime runs the
  translated program, and the port's build file and runner (`port/`) are adapted from its
  project template (MIT). Its runtime includes `at3_standalone` (LGPL-2.1), PPSSPP's
  extraction of FFmpeg's ATRAC3plus decoder.
  The changes this project makes to ps3recomp (`patches/ps3recomp/0001`-`0051`) are
  derivative of it and carry its MIT licence; they are meant to go upstream under MIT.
  Patches 0004, 0005, 0007, 0011-0024, 0026, 0028-0039, 0048, 0049 and 0051 follow RPCS3's
  behaviour (error answers, checks, lv2 and library semantics; each header names what);
  RPCS3 is a behaviour reference only, and no RPCS3 code is copied into them.
- [bloodborne_mac_port](https://github.com/Wooloomooloo2/bloodborne_mac_port): launcher,
  renderer machinery and project conventions.
- [doctest](https://github.com/doctest/doctest) (MIT): C++ test framework.

See `THIRD-PARTY-NOTICES.md` for licence details.

## Licence

The project is GPL-2.0-or-later, except the unpacker `gt6unpack` (`tools/gt6unpack/`), which
is GPL-2.0-only because it includes code adapted from RPCS3, which is GPL-2.0-only. Each
source file states its licence in an `SPDX-License-Identifier` line. See `LICENSE` (GPL-2.0
text) and `THIRD-PARTY-NOTICES.md`.

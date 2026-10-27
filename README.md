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

## Status: pre-alpha, milestone 1 done

Milestone 1 ("unpack and map") is done: your copy of the game turns into a verified version
1.22 game folder, and its code, imports and SPU programs are mapped. Nothing is playable yet.

**What's next:** milestone 2, where the translated program starts on the Mac and draws
something.

| Milestone | Outcome | State |
|---|---|---|
| 1 | Game unpacked, verified as v1.22, fully mapped | done |
| 2 | Translated program starts on the Mac and draws something | not started |
| 3 | Reach the first menu | not started |
| 4 | A race | not started |
| 5 | Locked 60 FPS | not started |
| 6 | MetalFX upscaling to 4K | not started |
| 7 | Racing wheel support | not started |

Online play is out of scope (Sony shut the servers down in 2018).

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
  analysis tools map the game's code (git submodule, dev-only), and it is the planned base for
  the translator and runtime.
- [bloodborne_mac_port](https://github.com/Wooloomooloo2/bloodborne_mac_port): launcher,
  renderer machinery and project conventions.
- [doctest](https://github.com/doctest/doctest) (MIT): C++ test framework.

See `THIRD-PARTY-NOTICES.md` for licence details.

## Licence

The project is GPL-2.0-or-later, except the unpacker `gt6unpack` (`tools/gt6unpack/`), which
is GPL-2.0-only because it includes code adapted from RPCS3, which is GPL-2.0-only. Each
source file states its licence in an `SPDX-License-Identifier` line. See `LICENSE` (GPL-2.0
text) and `THIRD-PARTY-NOTICES.md`.

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

## Status: pre-alpha, milestone 1

Milestone 1 is "unpack and map": turn your copy of the game into a verified version 1.22
game folder, and map all its code, imports and SPU programs. Nothing is playable yet.

| Milestone | Outcome | State |
|---|---|---|
| 1 | Game unpacked, verified as v1.22, fully mapped | in progress |
| 2 | Translated program starts on the Mac and draws something | not started |
| 3 | Reach the first menu | not started |
| 4 | A race | not started |
| 5 | Locked 60 FPS | not started |
| 6 | MetalFX upscaling to 4K | not started |
| 7 | Racing wheel support | not started |

Online play is out of scope (Sony shut the servers down in 2018).

## Guard against game files

`scripts/check_no_game_files.py` refuses any file that looks like PS3 game content. Run
`scripts/install_hooks.sh` once after cloning to install it as a pre-commit hook; CI runs it
on every push.

## Credits

- [RPCS3](https://github.com/RPCS3/rpcs3) (GPL-2.0): reference for PS3 behaviour, and the
  source of the decryption approach adapted for the unpacker.
- [ps3recomp](https://github.com/sp00nznet/ps3recomp) (MIT) by Ned Heller / sp00nznet: the
  planned base for the translator and runtime.
- [bloodborne_mac_port](https://github.com/Wooloomooloo2/bloodborne_mac_port): launcher,
  renderer machinery and project conventions.
- [doctest](https://github.com/doctest/doctest) (MIT): C++ test framework.

See `THIRD-PARTY-NOTICES.md` for licence details.

## Licence

GPL-2.0-or-later. See `LICENSE`.

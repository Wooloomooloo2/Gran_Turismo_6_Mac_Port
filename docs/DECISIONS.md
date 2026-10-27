# Decisions

Numbered, dated, with reasoning. Do not re-litigate the owner decisions (D1-D12 and D15) without the owner.

## Owner decisions (2026-10-27)

**D1.** Native translation, not emulation. Don't re-litigate.

**D2.** Priorities: locked 60 → MetalFX 4K → wheel. Controller first.

**D3.** Target game version **1.22** (final), European edition **BCES-01977**.

**D4.** Updates are fetched from Sony's update server with proper certificate verification, using Sony's root certificates taken from the firmware on the player's own disc.

**D5.** Online play out of scope.

**D6.** First milestone: the first menu.

**D7.** Public repo from the start, releases and outside contributors welcome, like Bloodborne.

**D8.** Reuse Bloodborne's launcher, MetalFX work and conventions where they fit.

**D9.** **A runtime fallback is allowed** for code not found ahead of time (SPU jobs loaded from data, overlays, missed indirect branches). It logs every use so the code can be translated ahead of time next run. Release builds aim for zero fallback use in normal play. This doesn't break O1: the product is still a translated native program.

**D10.** **Handling must match the PS3 exactly.** Physics and any gameplay-affecting SPU or PPU work is a faithful translation (exact SPU float and VMX behaviour), checked by determinism tests against reference traces recorded from RPCS3. Hand-written native replacements are allowed only where the player can't feel the difference (for example audio mixing, graphics setup), and each one is recorded in DECISIONS.

**D11.** **If a Mac can't hold 60:** first lower the internal resolution automatically and upscale with MetalFX. Beyond that, best effort on frame rate. Below-60 on a base M1 is not a project failure.

**D12.** **The app includes its own compiler** (a pinned LLVM/clang), so players don't install Apple's developer tools. During development, use the toolchain already on this Mac. **Large uploads from the owner's connection should happen late:** keep early releases small, and prefer ways that avoid uploading the toolchain from here (for example the app fetching a pinned, checksummed official LLVM build on first setup, or CI building release bundles). The builder picks the mechanism and records it in DECISIONS.

## Builder decisions

**D13 (2026-10-27).** C++ `gt6unpack` adapted from RPCS3 crypto; Python only for dev-time mapping. Reason: the unpacker ships to players and must not depend on RPCS3 or a Python install; RPCS3's crypto is GPL-2.0 and credited.

**D14 (2026-10-27).** Updates are installed as a separate `dev_hdd0` tree, as on a real PS3, not merged into the disc tree. Reason: matches how the game expects to find them, keeps the disc image untouched, and makes verification per layer.

**D15 (2026-10-27, owner).** Public PS3 decryption keys live in source, following the RPCS3 and ps3recomp precedent. Reason: players need no key hunting; the keys are publicly documented. This is a legal-exposure call and was made by the owner. No console-unique or disc-specific keys are ever committed (`keys.local*` is git-ignored).

**D16 (2026-10-27).** SELF decryption checks the section hash of every program segment and skips the hash of the section header table and SCE version sections. Reason: on the real disc executables the segment hashes match exactly, but the other two never match under any coverage tried (evidence in FINDINGS). Checking them would reject valid files. The decrypted ELFs are byte-identical to RPCS3's.

**D17 (2026-10-27).** The SELF decrypter supports retail ELF64 application and free-licence NPDRM SELFs only. Debug/fake SELFs, ELF32 SELFs and paid NPDRM licences raise clear errors. Reason: GT6's executables and its update packages need nothing more; less code to get wrong.

**D18 (2026-10-27).** The built disc layer (`dev_bdvd`) holds `PS3_DISC.SFB` and `PS3_GAME` only. The disc's `PS3_UPDATE` (system firmware) is left out, and the copied tree is made owner-writable. Reason: the game never reads the firmware, firmware must stay out of the project's outputs, and a read-only tree from a mounted image could not be rebuilt or removed.

**D19 (2026-10-27).** The klicensee that opens the update `EMAIN.SELF` files is found at build time in the player's own decrypted update `EBOOT.BIN`, never stored in the repository. A candidate key is accepted only if it decrypts the file with every program-segment hash matching. Reason: the game ships the key in its own executable as a config default (evidence in FINDINGS), so finding it there is reproducible from the player's files. Committing it would be a title-specific key, against D15. The key was captured once from RPCS3 to confirm the finding. That copy has been deleted, and the build neither needs nor reads a key file.

**D20 (2026-10-27).** The manifest covers `dev_bdvd`, `dev_hdd0` and `decrypted`, and nothing else. `build.json` is left out of the manifest and out of the EXTRA check. Reason: it holds timings and local paths that change on every run, so including it would make every build fail verification. Decided by the implementer.

**D21 (2026-10-27).** The code map covers the two executables a v1.22 console runs: the update `EBOOT.BIN` and the `USRDIR/EMAIN.SELF` it launches. The other 19 decrypted executables get a size and SHA-256 row only. Reason: the 1.22 `EBOOT.BIN` always launches `USRDIR/EMAIN.SELF` (evidence in FINDINGS); the disc, `FIXEDELF114` and `TPPS-01.xx` copies are older or standby builds that never run on 1.22. `scripts/map_game.py --elf` maps any of them if needed. Ruled by the controller; launch target confirmed by the implementer.

**D22 (2026-10-27).** `map_game.py` runs each ps3recomp tool as `python -I -c <runner> <tool> ...`, where the runner adds only that tool's own folder to the import path. Reason: under `python -I` the script's folder is not on the import path, and `extract_spu_images.py` fails with `ModuleNotFoundError: No module named 'spu_elf'` (the other tools add their folder themselves). The runner keeps isolated mode (no environment variables, no current-folder imports) without patching ps3recomp. Decided by the implementer.

**D23 (2026-10-27).** `map_game.py` also scans each ELF for job modules stored raw, using the header ps3recomp's `extract_jobmods.py` defines (and its file naming), and writes them next to its output. Reason: `extract_jobmods.py` only looks inside `patch.sdat`/`data.sdat` archives, which GT6 does not have, so it finds none, while `EMAIN.SELF` carries 57 job modules in its own code segment. Without the scan the map would report no job modules. Decided by the implementer.

**D24 (2026-10-27, ruling R5).** The files adapted from RPCS3 (`keys`, `self`, `pkg` in `tools/gt6unpack/src/`) are GPL-2.0-only, and `gt6unpack` as a whole is distributed under GPL-2.0-only. Everything else in the repository stays GPL-2.0-or-later. Every source file carries an `SPDX-License-Identifier` line saying which. Reason: RPCS3 states "Most files are licensed under the terms of GNU GPL-2.0-only", and its `rpcs3/Crypto` files carry no different notice, so code adapted from them cannot be offered under "or later" terms; the unpacker links that code, so the whole tool takes the stricter licence. Ruled by the controller after the final milestone 1 review.

**D25 (2026-10-27).** The lift's code end is the end of the last executable ELF section, read from the section headers. Reason: without it 3.7 GB of read-only data and embedded SPU programs are lifted as code (FINDINGS, "Translating EMAIN"). Decided by the implementer.

**D26 (2026-10-27).** Generated code, objects, binaries and run outputs live in the player's game folder (`<tree>/recomp`, `<tree>/port-build`, `<tree>/runs`), never in the repository. Reason: translated code is a derivative of the game (design spec, section 3). The translate tool refuses an output path inside a git work tree. Decided by the implementer.

**D27 (2026-10-27).** SPURS and SPU work run on ps3recomp's HLE SPURS with the lifted SPU code, and its SPU interpreter as the logged fallback. No firmware LLE: no Sony module (liblv2, libsre, any PRX from dev_flash) is loaded or required. The translate step lifts with `--allow-partial`, so an SPU program or job module that lifts only partly does not block the build; it is listed in `translate.json` and FINDINGS and runs in the interpreter (D9). Reason: design spec 6.3 (the shipped default must work without Sony modules), and O9. Decided by the implementer, per the milestone 2 plan.

**D28 (2026-10-27).** ps3recomp changes are carried as patch files in `patches/ps3recomp/`, applied in filename order to the submodule's working tree at configure time by `scripts/apply_ps3recomp_patches.sh` (which skips a patch already applied), each written so it can go upstream and headed with its upstream status. The submodule pointer stays at the pinned commit; only its working tree carries the patches. A tree translated under a different patch set is refused at configure time (`translate.json` records the patches' hash). Reason: the pinned submodule stays a clean upstream commit, every change can be reviewed, and nothing needs a fork pushed before the owner agrees. Decided by the implementer, per the milestone 2 plan.

**D29 (2026-10-27).** During development the port builds with the tools on this Mac: Apple clang, CMake and Ninja, and Homebrew's sdl2 (now `sdl2-compat` over SDL3), glslang and spirv-cross. Bundling them for players follows D12 (O12) later (BACKLOG, Mac GUI). Reason: D12 allows the local toolchain during development, and the runtime needs SDL2 for pad and audio and glslang plus spirv-cross to turn guest shaders into Metal ones. Decided by the implementer, per the milestone 2 plan.

**D30 (2026-10-27).** Lifted PPU code is compiled at `-O1` in every build type (72 s for the 65 chunks on the M4 Max, FINDINGS); lifted SPU code at `-O2`; the runtime takes the build type's level. The level is revisited in milestone 5 (locked 60) with measurements. Reason: the chunks are up to 5 MB of generated C++ each, and higher levels cost far more compile time and memory for a gain nobody has measured yet; `-O1` already inlines the small helpers the lifted code is made of. This follows ps3recomp's template. Decided by the implementer, per the milestone 2 plan.

**D31 (2026-10-27).** The port starts `EMAIN.SELF` directly with the launch contract in FINDINGS ("What the 1.22 EBOOT leaves on disk, and how EMAIN is launched"): the process `/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF`, argc 2 with `argv[0]` and `argv[1]` both that path, an empty environment and no data block, as the 1.22 `EBOOT.BIN` spawns it (`sceNpDrmProcessExitSpawn2`, measured under RPCS3). `port/main.cpp` passes it through ps3recomp's `PS3_BOOT_PATH` and `PS3_ARGV`, from which `ppu_run` builds the entry's argc, argv and envp. It runs on a play folder made by `scripts/prepare_play.py`, which carries the EBOOT's on-disk effects; the verified tree is never run (D32). The 1.22 `EBOOT.BIN` is not translated. Reason: the EBOOT only checks two files exist, rewrites 6 files that EMAIN's first-run install reads (without them EMAIN skips the 1.07 data patch), and spawns. The script reproduces those 6 files byte-identically, with the rule decoded from 0x1143c. So translating the EBOOT would add a second program and a cross-process klicensee hand-off for nothing. Ruled by the controller; measured and decoded by the implementer.

**D32 (2026-10-27).** The game runs on `<tree>/play/dev_hdd0`, an APFS clone of the verified `<tree>/dev_hdd0` made by `scripts/prepare_play.py` with the 1.22 EBOOT's on-disk effects applied. `<tree>/play/prepare.json` records what was applied, the source `build.json` (SHA-256, tool version, title, version) and the time. The port's `/dev_hdd0` defaults there (`PS3_HDD0_ROOT` still overrides), and it refuses to start unless that folder exists with `prepare.json` beside it (for an override, `$PS3_HDD0_ROOT/../prepare.json`). The script builds the folder in a staging folder and renames it into place only after writing `prepare.json`, and `--force` replaces only a folder holding this tool's `prepare.json`, never the tree or a folder containing it. An existing play folder is kept unless `--force` is given, because a first run has changed it. `gt6unpack` and the manifest are unchanged. Reason: EMAIN's first run moves thousands of files between `TPPS-*` and `PDIPFS`. Running on the verified tree would break `gt6unpack verify` and lose the known-good copy, while a clone costs 2.6 s and no disk space until files change. Ruled by the controller.

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

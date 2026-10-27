# Decisions

Numbered, dated, with reasoning. Do not re-litigate D1-D12 without the owner.

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

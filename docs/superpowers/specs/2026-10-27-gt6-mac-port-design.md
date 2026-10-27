# Gran Turismo 6 for Mac: design

Date: 2026-10-27. Status: draft for owner approval (builder-check questions answered, O9-O12).
Owner: Wooloomooloo2 (makes every product and architecture decision).
Repo: https://github.com/Wooloomooloo2/Gran-Turismo-6-Mac (public from day one).

## 1. Intent

Play Gran Turismo 6 on Apple Silicon Macs as a native Mac app, from the player's own copy of
the game, with none of the stutter, freezes or crashes of running it under a PS3 emulator.

"Native" is the point. The owner tried GT6 under RPCS3 on this Mac: it stutters, and it
freezes and crashes now and then. **The owner does not want a better emulator.** GT6's own
program code is translated ahead of time (static recompilation) from PS3 machine code into
Apple Silicon code and runs as a real macOS process. The PS3's system software is replaced by
a Mac runtime, and its graphics commands are turned into Metal.

Why Bloodborne's trick doesn't carry over: the sister project
(`~/Developer/GitHub/bloodborne_mac_port`) runs the PS4's x86-64 code directly under Rosetta 2.
The PS3 has a Cell processor: one PowerPC core (the PPU) plus six vector co-processors
(SPUs) with their own instruction set and 256 KB private memories. Rosetta can't run either.
Translation is the only native route.

## 2. Goals, non-goals, anti-goals

**Goals, in order (owner):**
1. A locked 60 FPS with even frame pacing, on any M-series Mac (base M1 is the hardware that
   proves it; the dev machine is an M4 Max). No shader-compile stutter, no freezes, no crashes.
   Note: on the PS3 itself GT6 ran at 1280×1080 and often fell below 60.
   Where a Mac can't hold 60, see O11 (resolution drops first, then best effort).
2. MetalFX upscaling to 4K; native 4K on Macs that can manage it.
3. Later: racing wheel support. Controller first.

**Milestones:**
1. The game program is unpacked, verified as v1.22, and fully mapped (code, imports, SPU
   programs).
2. The translated program starts on the Mac and draws something.
3. **First milestone the owner cares about: reaching GT6's first menu.**
4. A race.
5. A locked 60 FPS.
6. MetalFX to 4K.
7. Wheel support.

**Non-goals:**
- Online play (Sony shut GT6's servers down in 2018). Online features should fail
  gracefully as "offline", never hang.
- Building or improving a PS3 emulator. RPCS3 is reference material and a one-off tool, not
  the product.
- Other PS3 games. Generic tooling we build should go back upstream, but GT6 is the only target.
- Intel Macs.

**Anti-goals (failure even if it "works"):**
- Shipping anything owned by Sony or Polyphony Digital: game files, translated game code,
  firmware, system modules, keys. A release that contains any of them is a failure.
- A port that plays but stutters like the emulator did.
- Undocumented design decisions or uncredited borrowed code.

## 3. Constraints

- **Legal model (owner):** players bring their own legally owned copy. The owner owns a UK
  disc. The ISO on this Mac stands in for that disc until it can be dumped. Translated game
  code is a derivative of the game, so **translation runs on the player's Mac** and is
  never distributed. The project ships only its own tools, runtime and renderer, and states
  this in the README the way the Bloodborne port does.
- **Licence:** GPL-2.0 (owner prefers 2.0; 3.0 acceptable). Decided: **GPL-2.0-or-later**.
  RPCS3 is GPL-2.0 and the Bloodborne port is GPL-2.0-or-later, so both can be borrowed from.
  ps3recomp is MIT, which is compatible: its notices stay. **GPL-3.0-only code cannot be taken
  in** without relicensing the whole project to GPL-3.0. That is the owner's call, and the
  builder should raise it if it ever comes up.
- **Credit:** every borrowed file or idea is credited in README (Credits section),
  `THIRD-PARTY-NOTICES.md`, and file headers where code is copied.
- **Docs:** every design decision goes in `docs/DECISIONS.md` (numbered, dated, with the
  reasoning). README is updated with every release. The handover conventions follow
  Bloodborne: `CLAUDE.md` (session handover), `docs/FINDINGS.md` (measurements),
  `docs/BACKLOG.md` (shortcuts taken, with the proper fix logged).
- **Working pattern:** the owner hands the Mac over in the evenings for long unattended build
  and test runs and wants a short morning summary. Daytime work must not disturb the owner's
  use of the machine. Agents may be used, but their work is reviewed against this design and
  `docs/DECISIONS.md` before it's accepted.
- **Repo hygiene:** never commit game files, keys, firmware, decrypted executables or
  translated game code. `.gitignore` enforces it, and a CI check fails any commit containing
  PS3 file signatures (`SCE\0`, ELF with PPC64 machine type, PUP, PKG).
- **Writing for the owner:** the owner doesn't write code. Lead with decisions, outcomes and
  risks. Questions to the owner must be answerable from their effect on the player.

## 4. What the owner decided

| # | Decision |
|---|---|
| O1 | Native translation, not emulation. Don't re-litigate. |
| O2 | Priorities: locked 60 → MetalFX 4K → wheel. Controller first. |
| O3 | Target game version **1.22** (final), European edition **BCES-01977**. |
| O4 | Updates are fetched from Sony's update server with proper certificate verification, using Sony's root certificates taken from the firmware on the player's own disc. |
| O5 | Online play out of scope. |
| O6 | First milestone: the first menu. |
| O7 | Public repo from the start, releases and outside contributors welcome, like Bloodborne. |
| O8 | Reuse Bloodborne's launcher, MetalFX work and conventions where they fit. |
| O9 | **A runtime fallback is allowed** for code not found ahead of time (SPU jobs loaded from data, overlays, missed indirect branches). It logs every use so the code can be translated ahead of time next run. Release builds aim for zero fallback use in normal play. This doesn't break O1: the product is still a translated native program. |
| O10 | **Handling must match the PS3 exactly.** Physics and any gameplay-affecting SPU or PPU work is a faithful translation (exact SPU float and VMX behaviour), checked by determinism tests against reference traces recorded from RPCS3. Hand-written native replacements are allowed only where the player can't feel the difference (for example audio mixing, graphics setup), and each one is recorded in DECISIONS. |
| O11 | **If a Mac can't hold 60:** first lower the internal resolution automatically and upscale with MetalFX. Beyond that, best effort on frame rate. Below-60 on a base M1 is not a project failure. |
| O12 | **The app includes its own compiler** (a pinned LLVM/clang), so players don't install Apple's developer tools. During development, use the toolchain already on this Mac. **Large uploads from the owner's connection should happen late:** keep early releases small, and prefer ways that avoid uploading the toolchain from here (for example the app fetching a pinned, checksummed official LLVM build on first setup, or CI building release bundles). The builder picks the mechanism and records it in DECISIONS. |

## 5. Facts established so far

- Disc: `~/Gran Turismo 6/Gran Turismo 6 (UK)/Gran Turismo 6 (UK).iso` (25.3 GB, already
  disc-decrypted, mounts read-only with `hdiutil`). Leave it untouched.
  - `PARAM.SFO`: TITLE "Gran Turismo®6", TITLE_ID BCES01977, APP_VER 01.00, VERSION 01.03,
    PS3_SYSTEM_VER 04.50. Files dated 2013-11-11.
  - `PS3_GAME/USRDIR/`: `EBOOT.BIN` (72 KB, SCE-encrypted SELF, likely a small loader),
    `EMAIN.SELF` (8.8 MB, SCE-encrypted, the main program), `GT.VOL` (15.4 GB data
    archive).
  - `PS3_UPDATE/PS3UPDAT.PUP`: firmware 4.50.
  - Not yet verified. redump.org checksums cover *encrypted* full-disc images, so they don't
    apply to this decrypted ISO. Verification uses per-file hashes instead (the community IRD
    file for BCES-01977 lists them), as a milestone 1 task.
- Updates: Sony's list (`BCES01977-ver.xml`) has **21 packages, 1.02 → 1.22, 11.2 GB**,
  each with a SHA-1. They're downloaded and verified into `~/Gran Turismo 6/updates/` (outside
  the repo). That folder also holds the list and `sony-ca.pem`. Packages must be applied in
  order.
- Sony's root certificates: obtained by running the official RPCS3 macOS arm64 build
  (v0.0.43-20410, commit c365ea76, in `~/Developer/others/rpcs3-bin/`) once with
  `--installfw` on the disc's PUP. This filled `~/Library/Application Support/rpcs3/dev_flash/`.
  The certificates were bundled to PEM and used with `curl --cacert`. TLS checking was
  never turned off. The product's own unpacker must do this itself (see §6.1) and must not
  depend on RPCS3.
- RPCS3 source (reference, GPL-2.0): `~/Developer/others/rpcs3/` (shallow, commit c365ea76).

## 6. How it gets made

Five parts. The builder decides the internal structure of each.

### 6.1 Unpacker (milestone 1)
Takes the player's disc folder or ISO plus update packages and produces a verified v1.22 game
folder on the player's Mac.
- Reads the ISO directly, or a dumped folder. *(My call)* v1 accepts **already-decrypted** ISOs
  and folders, which is what the common PS3 and PC dumping tools produce. Encrypted
  redump-style images plus disc keys or IRD files come later, logged in BACKLOG, with a
  separate key-handling decision.
- *(My call)* **Editions:** v1 supports the European release BCES-01977 only. Other regions
  (US BCUS-98394, Japan, Asia) come later and add to it: per-edition hash manifests, update
  lists and address tables. The design keeps everything edition-keyed from day one so adding
  them stays cheap.
- *(My call)* **DLC:** content delivered in updates 1.02-1.22 is in scope. Paid DLC that
  needs PSN licence files or console-bound decryption is out of scope for v1 (logged in
  BACKLOG). Features that needed the servers (seasonal events, online-only unlocks) are
  out of scope with online play.
- Fetches the update list and packages from Sony's server, verifying TLS against Sony's
  roots extracted from the disc's own PUP, and checks each SHA-1. Lets the player point it
  at packages they already have.
- Decrypts the PKGs and SELF files, applies the updates in order, and verifies the result
  against a manifest of expected hashes. The manifest contains only hashes, no Sony
  content, and is committed.
- Decryption uses the publicly documented PS3 algorithms and keys, the same way RPCS3,
  ps3recomp and other open-source tools do. **Open question for the builder:** how the
  project handles keys. Shipping them in the source, as RPCS3 does, or asking the player
  to provide them, as ps3recomp does. Recommend one, record it in DECISIONS, and flag it to the
  owner, because it's a legal-exposure call.

### 6.2 Translator (milestones 1-3)
Turns GT6's PPU program (`EMAIN.SELF` after decryption, plus any PRX modules and SPU programs
it loads) into C/C++ that's compiled for arm64 on the player's Mac.
- **Decided (my call, open to the owner): build on ps3recomp**
  (https://github.com/sp00nznet/ps3recomp, MIT, very active, macOS/arm64 runtime and a Metal
  backend already in tree, with inFamous running in-game on macOS downstream). We use it as an
  upstream dependency (submodule or vendored at a pinned commit), and generic fixes go back
  upstream. GT6-specific code lives in this repo. If the builder finds ps3recomp unsuitable,
  that's a decision to bring back to the owner with evidence, not to make quietly.
- Secondary references: XenonRecomp and ReXGlue (Xbox 360 PowerPC recompilers, close
  cousins of the PPU), RPCS3's PPU/SPU interpreters as the ground truth for instruction
  behaviour.
- **SPUs are the main technical risk.** GT6 leans heavily on them (physics, graphics
  preparation, audio). The plan must find GT6's SPU programs early (milestone 1) and size
  the work.
- The translation step runs on the player's Mac, inside the launcher. Target: minutes, not
  hours, on a base M1. The builder measures this and records it.

### 6.3 Runtime
A Mac stand-in for the PS3's system software (LV2 kernel calls and system libraries: files,
GT.VOL access, saves, threads and sync, timers, audio, controller, system dialogs). Mostly
ps3recomp's HLE runtime, extended for GT6. RPCS3's HLE modules are the reference for
behaviour.
- **Never ship Sony firmware modules.** Some ps3recomp ports load Sony's own liblv2/libsre
  (low-level emulation). Whether GT6 may *optionally* use modules extracted from the player's
  own firmware is a builder recommendation, but the shipped default must work without them,
  or it goes back to the owner.
- Online calls answer "offline" cleanly.
- Saves live in `~/Library/Application Support/<app>/`, are backed up before risky changes
  (as in Bloodborne), and use a documented format, so a future import from a real PS3 save is
  possible.

### 6.4 Graphics (RSX → Metal)
Turns GT6's RSX command stream and shaders into Metal.
- Start from ps3recomp's Metal backend and pipeline cache. Take whatever helps from the
  Bloodborne renderer: frame pacing, the shader and pipeline cache approach that removed
  stutter, the MetalFX integration, the overlay, the benchmark harness. PS4 GCN shaders and
  PS3 RSX shaders are different, so the translator itself won't carry over. The
  surrounding machinery will.
- **No mid-race stutter is a requirement, not a polish item:** shaders and pipelines must be
  built ahead of time, during the translation step or on first launch with a progress bar,
  not when first drawn.
- Output resolution decoupled from GT6's internal 1280×1080. MetalFX upscaling (milestone 6).
  Native higher resolution where the renderer allows.

### 6.5 Launcher and app
Reuse the Bloodborne launcher (`bloodborne_mac_port/launcher/`) as the base. Flow: point at the
game → it unpacks and updates → it translates (once, with a progress bar) → Play. Settings for
resolution, upscaler, FPS cap and controls. Logs, crash reports and a diagnostics zip, as in
Bloodborne. Must not use GT6 or Sony branding in a way that suggests endorsement. The app name
is the owner's call, to be raised before the first release.

### 6.6 Evening test harness
An unattended loop for the owner's evening handovers. It builds, translates, boots, and records
how far the game got and why it stopped (the last calls, an unimplemented function, a crash,
a hang with thread states), plus performance once in game. It runs until morning or until
stuck, then writes a short summary for the owner (outcome first). Results go into
`docs/FINDINGS.md`.

## 7. Left to the builder

The internal design of every part. Language choices beyond what ps3recomp dictates (Swift
for the launcher, as in Bloodborne). Repo layout. Build system (CMake, following
ps3recomp). How to split work across agents. The order of work inside each milestone. Test
strategy. Any of these that turns into a trade-off visible to the player goes to the owner.

## 8. Main risks

1. **SPU translation** for a game this SPU-heavy may be slow or inexact. Mitigation: find
   and size it in milestone 1, lean on ps3recomp's existing SPU work, and use the runtime
   fallback (O9) for the gaps. Exactness is non-negotiable for physics (O10).
2. **ps3recomp maturity:** no title boots to gameplay from its main tree on macOS yet.
   We'll be among the first. Mitigation: pin a commit, upstream our fixes, keep GT6 code
   separate.
3. **Performance on a base M1:** a locked 60 means faster than the PS3 ever ran GT6.
   Unknown until milestone 4.
4. **Key handling and legal exposure** (§6.1).
5. **The 15.4 GB GT.VOL archive** may need custom reading, and possibly streaming
   performance work.
6. **Translation time on the player's Mac:** an 8.8 MB PPU program becomes millions of lines
   of C. Compile time against the "minutes on a base M1" target needs measuring early
   (milestone 2), along with ways to cut it (splitting into units, caching, lower
   optimisation for cold code).

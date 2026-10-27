# Findings

## Owner summary: milestone 1 (2026-10-27)

**Milestone 1 is done.** Your copy of the game now turns into a verified version 1.22 game
folder, and the game's code is fully mapped. Nothing failed outright.

| Question | Answer |
|---|---|
| Is it really v1.22? | Yes. Every game program was unlocked and the folder matches the recorded checksums. |
| How big is the game's code? | One 23 MB program made of about 72,000 separate routines. All of it has to be translated for the Mac. |
| Biggest risk | The game also runs many small programs on the PS3's helper chips. Recreating those on the Mac is the hardest part of what comes next. |
| What milestone 2 needs | Your go-ahead. It starts by settling three things: a data-patching step the launcher runs, how to handle the helper-chip programs, and how long the translation takes. |

One smaller risk: the disc has not yet been checked against an independent source (backlog).

Measurements and facts, newest first within each section.

### Test run

Full suite with the real disc and all updates (no skips):

- `ctest --test-dir build`: `test cases: 59 | 59 passed | 0 failed | 0 skipped`; `assertions: 332 | 332 passed | 0 failed`.
- `.venv/bin/python -m pytest tests -q`: `25 passed`.
- `scripts/check_no_game_files.py $(git ls-files)`: clean.

## Code map of v1.22 (2026-10-27)

**Risks found** (technical detail; the plain-language version is the owner summary above):

- **Helper-core code is the biggest job.** The 57 SPURS job modules (1.53 MB) are stored raw
  inside the executable, not as the separate programs ps3recomp's tools expect. Our map finds
  and extracts them; ps3recomp's own extractor finds none. Milestone 2 must lift them and build
  SPURS support for job chains and tasks, not just the simpler case.
- **ps3recomp's name list has gaps.** ps3recomp cannot name 227 of the 835 imported functions
  (EMAIN 217, EBOOT 10). RPCS3 names 222 of them, so the gap is in ps3recomp's list, not
  unknown territory. Five (in game storage) are unnamed by both.
- **The launcher does work before the game starts.** The 1.22 `EBOOT.BIN` runs a data-patch
  step, and can swap in a repaired executable, before it launches the game (below). The port
  must reproduce what that step leaves on disk, or run it.
- Nothing failed outright. One ps3recomp tool does not start under the isolated Python the
  project requires; a small runner works around it without changing ps3recomp (D22).

**What the 1.22 EBOOT launches.** From a static trace of the decrypted 1.22 `EBOOT.BIN` (in
the code segment, va = file offset + 0x10000). It always launches `<own folder>/EMAIN.SELF`,
that is `/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF`. The repair swap below is the one
exception.

- Boot function 0x123e0: takes `argv[0]`, cuts it to its folder, and checks that `EBOOT.BIN`
  and `EMAIN.SELF` both exist there. Both paths are built in a static buffer at va 0x52a10.
  If either is missing it shows the "game content damaged" dialog (`cellGameContentErrorDialog`).
- It then opens `TPPS-01.07/update.txt` in that folder and, if the file exists, overwrites it
  with `99.98 99.99` (string at va 0x3d100). As installed, `TPPS-01.07/update.txt` reads
  `01.06 01.07`, and every later `TPPS-01.xx/update.txt` already reads `99.98 99.99`.
- 0x1143c is a data-patch step (not yet analysed). It scans the `TPPS-%02d.%02d` folders,
  `PDIPFS` and `UPDATENODEINFO`, writes `UPDATENODEINFO.upd` and renames files. It receives the
  launch path only as a source to copy from, so it cannot change it.
- 0x108f0 is the repair swap. It reads the size of the current `EMAIN.SELF` (`cellFsFstat`)
  and looks it up in a table keyed by title ID (va 0x51b84, 0x20-byte rows of size + title).
  For BCES01977 the "broken" size is 9,058,928 bytes, which is the 1.14 `EMAIN.SELF`. Only on a
  match does it check `FIXEDELF114/EMAIN.SELF` against a second table (9,059,040 bytes, which
  is its size). It then renames that file over `USRDIR/EMAIN.SELF` (`cellFsRename` in 0x2224c).
  The 1.22 `EMAIN.SELF` is 9,001,952 bytes, so the swap does not happen on 1.22.
  **`FIXEDELF114` is a repaired 1.14 executable, kept for consoles stuck on the broken one.**
- Spawn: 0x12614 calls 0x2123c with the klicensee string from 0x13914 (the `KeyLicensee`
  default traced earlier) and the 0x52a10 buffer. 0x2123c parses the key and calls
  `sceNpDrmProcessExitSpawn2` at 0x21324. 0x125e4 is a non-DRM branch that calls
  `sys_game_process_exitspawn2` with the same buffer, taken when a state record returned by
  0x20858 has its first word 1 and the low bit of its second word clear. No code passes a `TPPS-*` or `FIXEDELF114` path to
  either spawn call.
- **The `TPPS-01.xx` folders** each hold an `EMAIN.SELF`, a `PDIPFS` folder and an `update.txt`
  ("from to" versions). They look like per-update staging for Polyphony's `PDIPFS` data-patch
  system. `TPPS-01.07/PDIPFS` is 971 MB and `TPPS-01.22/PDIPFS` is 17 MB. The 1.22 EBOOT never
  spawns their executables.
- **No two of the 21 decrypted executables are identical** (SHA-256, `map/identity.json`).
  `USRDIR/EMAIN.SELF` is not `TPPS-01.22/EMAIN.SELF`: the ELFs are 23,168,200 and 23,787,792
  bytes. Three pairs have equal ELF sizes but differ in millions of bytes:
  `FIXEDELF114`/`TPPS-01.14`, `TPPS-01.10`/`01.11` and `TPPS-01.12`/`01.13`. All carry the
  build tag `gt.gt6.ps3.product-strong.release.build`.

**Numbers** (`scripts/map_game.py`, ps3recomp 4e8f3ca8; full summary in
`~/Gran Turismo 6/build/BCES01977-v1.22/map/summary.json`):

| | 1.22 `EBOOT.BIN` | 1.22 `USRDIR/EMAIN.SELF` |
|---|---|---|
| ELF bytes | 278,344 | 23,168,200 |
| Code segment (also holds read-only data and the SPU programs) | 200,608 | 21,749,736 |
| Data segment, in file / in memory | 10,660 / 227,328 | 1,385,632 / 2,775,632 |
| Functions found (`find_functions`) | 1,117 | 72,144, covering 15,318,088 bytes |
| Address-taken functions (`ppu_loader`, from the descriptor table) | 282 | 33,428 (45,005 descriptors) |
| System functions imported / libraries | 95 / 11 | 740 / 46 |
| Imports ps3recomp cannot name | 10 | 217 (29 %) |
| SPU ELF programs | 0 | 4, 224,036 bytes |
| SPURS job modules | 0 | 57, 1,532,240 bytes |

- `find_functions` attributes almost no code to the SPU programs: 2 functions start in the
  3.4 MB stretch (va 0x112d880 to 0x1468190) that holds them. So the 15.3 MB is PPU code.
- **Imports of `EMAIN.SELF` by library** (the EBOOT's 11 libraries are all among these):
  sceNp 64, cellSysutil 55, cellSpurs 49, sceNp2 48, cellGcmSys 39, sysPrxForUser 38,
  sys_net 34, sceNpCommerce2 32, cellSail 31, cellHttp 28, cellSysutilAvc2 27, sys_fs 26,
  sys_io 23, cellSailRec 19, sceNpTus 19, cellPamf 18, cellNetCtl 15, cellUsbd 14,
  sceNpTrophy 13, cellAudio 12, cellDmux 12, cellRtc 10, cellUsbPspcm 9, cellAdec 8, cellGame 8,
  cellMusicUtility 8, libvdec 8, cellFiber 6, cellOskExtUtility 6, cellSysmodule 6, sceNpSns 6,
  cellGameStorage 5, cellHttpUtil 5, cellRec 5, cellKey2char 4, cellSaveData 4, cellSsl 4,
  cellVideoExportUtility 4, sceNpUtil 4, cellPhotoUtility 3, cellSync 3, cellSysutilNpEula 3,
  cellUserInfo 2, cellSysutilAvconfExt 1, sceNpBasicLimited 1, sys_crashdump 1.
- By purpose: online (sceNp except trophies, sys_net, HTTP/SSL, network control, voice chat,
  EULA) 290 in 14 libraries; video playback and recording (cellSail, cellSailRec, cellPamf,
  cellDmux, libvdec, cellAdec, cellRec, video export) 105; USB (cellUsbd, cellUsbPspcm) 23,
  probably including the racing wheels (milestone 7); SPURS and sync 52; the remaining core
  (graphics, files, pad, audio, system, save data, trophies, time, fibres) 270.
- **SPURS: yes, heavily.** The 49 cellSpurs imports cover initialisation with attributes,
  tasksets and tasks (`cellSpursCreateTaskset2`, `cellSpursCreateTask2`), job chains
  (`cellSpursCreateJobChainWithAttribute`, `cellSpursRunJobChain`, `cellSpursJobGuard*`),
  custom workloads (`cellSpursAddWorkloadWithAttribute`), SPURS queues, LV2 event queues and
  tracing. The one unnamed cellSpurs import is 0x2DDBCC0A (`_cellSpursWorkloadFlagReceiver2`
  in RPCS3).
- **SPU ELF programs** (file offsets in `EMAIN.SELF.elf`): 0x1286F00 17,400 B (built with SPU
  GCC 4.1.1, SDK 4.20), 0x13F9580 21,332 B (`ipc_spucore.elf`), 0x13FE900 91,956 B,
  0x1415080 93,348 B.
- **Job modules**: 57, all different, 3,216 to 155,184 bytes each, between file offsets
  0x111d880 and 0x1456600 of the code segment. Header: four `ila`, entry 0x30, image size, then
  `0xC0DEC0DE`. They are extracted to `map/<elf>/jobmods_embedded/` with ps3recomp's naming,
  ready for `lift_jobmods.py`. ps3recomp's `extract_jobmods.py` exits 0 and writes nothing
  (`MISSING .../USRDIR/patch.sdat`, `MISSING .../USRDIR/data.sdat`): GT6 has no SDATA archives.
  Programs the game loads from `GT.VOL` at run time would not show up in any of these counts.
- **Unresolved NIDs**: 217 in EMAIN, by library: cellSailRec 19, cellSail 18, sceNp 14,
  cellHttp 13, cellSysutil 13, cellSysutilAvc2 13, sceNp2 12, cellPamf 9, cellUsbPspcm 9,
  cellUsbd 9, sys_net 9, cellNetCtl 6, cellOskExtUtility 6, cellFiber 5, cellGameStorage 5,
  sceNpSns 5, sysPrxForUser 5, sys_io 5, then 18 libraries with 4 or fewer. 10 in EBOOT:
  cellFiber 5 (the `cellFiberPpuContext*` family), sys_fs 4 (`cellFsReadWithOffset`,
  `cellFsWriteWithOffset`, `cellFsAllocateFileAreaWithoutZeroFill`, `cellFsFGetBlockSize`),
  sys_crashdump 1. Every one appears by name in the RPCS3 0.0.43-20410 boot log
  (`ppu_loader: **** <lib> import: [<name>] (<nid>)`) except five cellGameStorage NIDs
  (0x23EC78CE, 0x50771F25, 0x8DBD9594, 0xA9201831, 0xD7724C0A), which RPCS3 also leaves
  unnamed. Core ones ps3recomp lacks include `sys_mempool_*`, `cellPadLdd*` (custom controller
  drivers) and `cellWebBrowser*`.
- **Tool failure.** `.venv/bin/python -I third_party/ps3recomp/tools/extract_spu_images.py
  EMAIN.SELF.elf -o spu_images` fails with `ModuleNotFoundError: No module named 'spu_elf'`
  (`extract_spu_images.py` line 31). `-I` leaves the script's folder off the import path, and
  unlike the other tools this one does not add it itself. Worked around (D22). The other four
  tools run as documented in ps3recomp's `docs/TOOLS.md`.
- **Run time** on the M4 Max: 13.6 s for the whole map, including SHA-256 of all 21 ELFs.
  `find_functions` on EMAIN takes 12.4 s; every other tool takes under 0.6 s.

## Building the v1.22 tree (2026-10-27)

- **Outcome: done.** `gt6unpack build` produces a verified v1.22 tree at
  `~/Gran Turismo 6/build/BCES01977-v1.22` (25 GB). Final installed APP_VER: 01.22. All 21
  SELFs decrypted; none failed, and no other SCE files were found.
- **The update executables need the game's own key.** The 18 update `EMAIN.SELF` files
  (`USRDIR/EMAIN.SELF`, `USRDIR/FIXEDELF114/EMAIN.SELF`, `USRDIR/TPPS-01.07` to
  `TPPS-01.22/EMAIN.SELF`) are free-licence NPDRM SELFs (program type 8, key revision 0x001C,
  licence 3). They do not open with the public free klicensee. The update `EBOOT.BIN` is the
  same kind of SELF and does open with it. This is the first real-data proof of that path.
- **Where the key comes from.** Captured once from RPCS3 0.0.43-20410-c365ea76 booting the
  disc with the updates installed. RPCS3 boots `/dev_hdd0/game/BCES01977/` (the 1.22
  `EBOOT.BIN`), which calls `sceNpDrmIsAvailable` for
  `/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF` with a klicensee on its stack. Traced in the
  decrypted 1.22 `EBOOT.BIN` (278,344 bytes):
  - Import stubs: `sceNpDrmIsAvailable` at 0x3c180, `sceNpDrmProcessExitSpawn2` at 0x3c1f0.
    `sceNpDrmIsAvailable` is called at 0x10984 and 0x10a38, both in the function at 0x108f0.
  - The klicensee buffer (sp+0x74) is filled by a hex-string parser (0x20f04) from the string
    returned by 0x13914.
  - 0x13914 looks up the config entry `"KeyLicensee"` (string at va 0x3f038) in a
    name/value table at va 0x7e00c. The fallback is the all-zero string at va 0x3f048.
  - A static initialiser registers `KeyLicensee` (0x128f4) with a type-6 (string) default
    that points to va 0x52000 in the data segment (file offset 0x42000). That default is
    `"0x"` + 32 hex digits: the klicensee in plain text.
  - Earlier byte-window scans missed it because they looked for 16 raw bytes, not hex text.
  - The decrypted ELF has exactly two such strings: that one and the all-zero fallback.
- **How gt6unpack gets it.** A free-licence NPDRM SELF that fails with the public klicensee is
  retried with every `0x`+32-hex string found in the decrypted update `EBOOT.BIN`. A candidate
  is accepted only if the metadata opens and every program-segment HMAC matches. The key is
  read from the player's own files at build time. It is not in the repository and not in
  `build.json`, which records only where it was found.
- One key opens all 18 update `EMAIN.SELF` files. `USRDIR/EMAIN.SELF` (the one the 1.22
  `EBOOT.BIN` spawns) is not the same file as `TPPS-01.22/EMAIN.SELF`.
- Decrypted executables (SHA-256 of the ELF):

  | File | ELF bytes | SHA-256 |
  |---|---|---|
  | dev_bdvd `PS3_GAME/USRDIR/EBOOT.BIN` | 143,064 | `241c3e8c805049474dcb337914928d6552a3a4087a70cccda018356d73285b28` |
  | dev_bdvd `PS3_GAME/USRDIR/EMAIN.SELF` | 22,371,400 | `3b543f22062d078a30ec2e5c15d16e7c8a2389cdc32375a58fec6c6842896729` |
  | dev_hdd0 `USRDIR/EBOOT.BIN` | 278,344 | `4c9f642e21df8963b1f0c6df14ecdb4b3e8d0c061c45427ecc955b6a9eec0272` |
  | dev_hdd0 `USRDIR/EMAIN.SELF` | 23,168,200 | `7b4f37bdf1cc6024a6abd38012eb40f02afe979996aa075ed9e1736aecc373d1` |
  | dev_hdd0 `USRDIR/FIXEDELF114/EMAIN.SELF` | 23,512,336 | `437bd0b66916da6d93481ea2c93881ab063ffa095eade33481cb01f5d9bb3312` |
  | dev_hdd0 `USRDIR/TPPS-01.07/EMAIN.SELF` | 23,309,640 | `70a6a472dc10b8113b34cb67d229d6cf7e9b15ccb20a1c634c415fb1e43618cd` |
  | dev_hdd0 `USRDIR/TPPS-01.08/EMAIN.SELF` | 23,310,904 | `ca197b14376eedcaba83b944819de6b290e33c9530207ad8875b30678ef72599` |
  | dev_hdd0 `USRDIR/TPPS-01.09/EMAIN.SELF` | 23,377,752 | `221c72567e8c2f20684111a2402cfa7ead4398e8be972b6c9f58707af2205f4a` |
  | dev_hdd0 `USRDIR/TPPS-01.10/EMAIN.SELF` | 23,180,216 | `c660236e51f84cf2d1ff0b06da2d2798ccaf9efa2d64725d512c59817487025d` |
  | dev_hdd0 `USRDIR/TPPS-01.11/EMAIN.SELF` | 23,180,216 | `1148b01e7fb6b060ee9472e16558582722df978d275896cf360e0213e6dcba65` |
  | dev_hdd0 `USRDIR/TPPS-01.12/EMAIN.SELF` | 23,384,040 | `68cd0695d7a8e8e5bc69c84339b30e9ff59fbaa2034579fbcbc46f79fc2d5dd8` |
  | dev_hdd0 `USRDIR/TPPS-01.13/EMAIN.SELF` | 23,384,040 | `d13d58e83fde6db67e5ba03d7e6ac978762e55d081081833d845c9e7689020a7` |
  | dev_hdd0 `USRDIR/TPPS-01.14/EMAIN.SELF` | 23,512,336 | `08f064cabff120cc5bfb0741872cf32d9f5df62225d6515f121fe905cff751bf` |
  | dev_hdd0 `USRDIR/TPPS-01.15/EMAIN.SELF` | 23,580,432 | `ae0cff918db28629c9746ca5ce31172c43e44033eeffd78a5ffef4552d47547d` |
  | dev_hdd0 `USRDIR/TPPS-01.16/EMAIN.SELF` | 23,784,592 | `6a2a469fafa9cee01622468841d07f726fb3f69ac23661a8b2ea2476d4df9cdc` |
  | dev_hdd0 `USRDIR/TPPS-01.17/EMAIN.SELF` | 23,785,360 | `6ecf1d291c26061b3f283b418583b34bd19bc2bb37f5112a07a1178cc785a562` |
  | dev_hdd0 `USRDIR/TPPS-01.18/EMAIN.SELF` | 23,785,488 | `f8c38f78152c9742d900ad24655b6fc8494943fcd7df4887a0a3d2fb72aa5a67` |
  | dev_hdd0 `USRDIR/TPPS-01.19/EMAIN.SELF` | 23,786,384 | `143303d1853fdc17cbf8433ed281583676af108fcb31fc86dd28c6184354889e` |
  | dev_hdd0 `USRDIR/TPPS-01.20/EMAIN.SELF` | 23,786,768 | `a3f7b4985d75bc13deec437fe3bf3bad898374b9876a3e0f415727f0c35ab897` |
  | dev_hdd0 `USRDIR/TPPS-01.21/EMAIN.SELF` | 23,787,664 | `5c65a069c74eb1dd7cb52bf03333edf4741b933fc8479f0db2ca26a0271dbf7d` |
  | dev_hdd0 `USRDIR/TPPS-01.22/EMAIN.SELF` | 23,787,792 | `0e665e78eca03246d13d4394ae22a4dfab32f5141bf0cd26a04622700c4cc2e0` |

- Update install cross-checked against RPCS3 0.0.43-20410-c365ea76 (`--headless --installpkg`,
  one package at a time in APP_VER order). Its `dev_hdd0/game/BCES01977` and the gt6unpack
  install match exactly: 16,536 files with identical SHA-256, and 5,118 identical folders.
  Each headless RPCS3 install finished in about 2 s and aborted during process teardown
  (exit 134) after writing the files.
- Timings on the M4 Max (from `build.json`), 155 s in total:

  | Step | Time |
  |---|---|
  | Verify the 21 packages (Sony SHA-1 over 11.2 GB) | 6.3 s |
  | Disc copy (the ISO is a separate volume, so `clonefile` gives EXDEV) | 15.6 s |
  | Disc SHA-1 | 7.5 s |
  | Install the updates | 104.8 s |
  | Decrypt the 21 SELFs (including the klicensee search) | 20.6 s |

- The mounted ISO is read-only all the way down (`r-xr-xr-x`). The built `dev_bdvd` is
  normalised to 0755 folders and 0644 files, so a rebuild or removal works.
- 1.07 carries no `USRDIR/EBOOT.BIN`, and the install handles that: a later package replaces
  only the files it carries. All 21 packages extract under the existing name checks with no
  rejections.

## Disc executables (2026-10-27)

- `EMAIN.SELF` and `EBOOT.BIN` are retail application SELFs (program type 4, not NPDRM),
  SCE header key revision 0x001C, header type 1, ELF64 big-endian PPC64 inside.
- Decrypted ELF SHA-256 (from `gt6unpack`, byte-identical to RPCS3 c365ea76 `--decrypt`):
  - `EMAIN.SELF` → 22,371,400 bytes, `3b543f22062d078a30ec2e5c15d16e7c8a2389cdc32375a58fec6c6842896729`
  - `EBOOT.BIN` → 143,064 bytes, `241c3e8c805049474dcb337914928d6552a3a4087a70cccda018356d73285b28`
- Both have 7 metadata sections: 5 program segments (type 2; the first two zlib-compressed,
  three empty), one SCE version section (type 3) and the section header table (type 1). All
  seven are flagged hashed. The last two are stored unencrypted.
- Section hash: the metadata key table holds, at `sha1_idx * 16`, a 96-byte slot: SHA-1[20],
  zero[12], HMAC key[64]. For every program segment, HMAC-SHA1(key, decrypted section data
  as stored, still zlib-compressed) equals the stored SHA-1. `gt6unpack` checks it.
- The type 3 and type 1 section hashes do not match. Tried, all with the slot's HMAC key and
  also plain SHA-1: the stored bytes; every start offset within ±0x100 and every length up
  to size+0x200; a size-long window at every offset of the SELF and of the decrypted ELF;
  zero padding of 0 to 64 bytes; truncation to 16-byte multiple; zlib-compressed forms
  (levels -1 to 9); 32-bit byte-swapped; AES-128-CTR of the bytes under every key/iv pair in
  the key table. None matched. Likely the signer hashed these before a later fix-up; the
  console never loads them, so it never checks them. RPCS3 checks no section hash at all.
  `gt6unpack` does not check these two. Neither holds segment contents, but the section header
  table is copied into the ELF unverified.
- The SCE version section (`crt0:p440001…` library version strings) is an ELF section outside
  every segment, so it is not in the decrypted ELF (same as RPCS3).

## Game and updates (2026-10-27)

- Disc: BCES01977 v1.00 (UK), `Gran Turismo 6 (UK).iso`, 25.3 GB, already disc-decrypted.
  `PARAM.SFO`: TITLE_ID BCES01977, APP_VER 01.00, VERSION 01.03, PS3_SYSTEM_VER 04.50.
  `USRDIR`: `EBOOT.BIN` (72 KB), `EMAIN.SELF` (8.8 MB), `GT.VOL` (15.4 GB).
  `PS3_UPDATE/PS3UPDAT.PUP`: firmware 4.50.
- Updates: Sony's list `BCES01977-ver.xml` has 21 packages, 1.02 to 1.22, 11.2 GB. All
  downloaded to `~/Gran Turismo 6/updates` and verified.
- Hash rule: Sony's SHA-1 in `BCES01977-ver.xml` covers the package minus its last 32 bytes.
  The package's last 32 bytes are that SHA-1 plus 12 zero bytes.
- Sony root certificates were obtained by running RPCS3 with `--installfw` on the disc's PUP,
  then bundled to PEM for `curl --cacert`. TLS checking was never turned off.
- Not yet verified: per-file hashes of the disc (redump checksums do not apply to a decrypted
  image; the community IRD lists per-file hashes).

## Risk: disc contents not checked against an independent source (2026-10-27)

- The committed manifest `manifests/BCES01977-v1.22.json` proves a player's build matches
  the one we made, but both start from the same disc image. If that image had a bad file
  (for example in GT.VOL), the manifest would record the bad hash as correct.
- The community IRD file lists per-file MD5s of the original disc and would catch this.
  Using it needs an ISO directory reader (BACKLOG, Unpacker). Until then, GT.VOL is
  unverified against an independent source.

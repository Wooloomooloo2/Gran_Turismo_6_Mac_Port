# Findings

Measurements and facts, newest first within each section.

## Building the v1.22 tree (2026-10-27)

- **Outcome: blocked.** `gt6unpack build` verifies and installs all 21 updates correctly, but
  the v1.22 game executable cannot be decrypted yet, so no v1.22 tree was produced. The update
  `EMAIN.SELF` files (18 of them: `USRDIR/EMAIN.SELF`, `USRDIR/FIXEDELF114/EMAIN.SELF`,
  `USRDIR/TPPS-01.07` to `TPPS-01.22/EMAIN.SELF`) are free-licence NPDRM SELFs (program type 8,
  key revision 0x001C, licence 3, content ID `EP9001-BCES01977_00-0000000000000000`) whose
  metadata does not open with the public free klicensee (`NP_KLIC_FREE`). On a PS3 (and in
  RPCS3) the game's own `EBOOT.BIN` hands the klicensee to the system when it spawns
  `EMAIN.SELF` (`sceNpDrmIsAvailable` / `sceNpDrmProcessExitSpawn`); RPCS3 has no built-in key
  for it either. Searched for it, without success: every byte offset of the decrypted 1.22
  `EBOOT.BIN`, every 16-byte value its PPU code builds from immediates and stores, and every
  byte offset of each file under 700 KB in the 1.22 package. The key is probably computed at
  run time.
- The update `EBOOT.BIN` is the same kind of SELF and opens with `NP_KLIC_FREE`. This is the
  first real-data proof of the free-licence NPDRM path. 1.22 `EBOOT.BIN` → 278,344 bytes,
  SHA-256 `4c9f642e21df8963b1f0c6df14ecdb4b3e8d0c061c45427ecc955b6a9eec0272`. The decryption
  pass found 21 SELFs in the two trees: 3 decrypted (disc `EBOOT.BIN` and `EMAIN.SELF`, as
  listed under Disc executables, and the update `EBOOT.BIN`) and the 18 `EMAIN.SELF` failures
  above. Because the run stopped, there is no `build.json` listing the skipped SCE files that
  are not SELFs.
- Update install cross-checked against RPCS3 0.0.43-20410-c365ea76 (`--headless --installpkg`,
  one package at a time in APP_VER order). Its `dev_hdd0/game/BCES01977` and the gt6unpack
  install match exactly: 16,536 files with identical SHA-256, and 5,118 identical folders.
  Each headless RPCS3 install finished in about 2 s and aborted during process teardown
  (exit 134) after writing the files. Final installed APP_VER: 01.22.
- Timings on the M4 Max (the build stops at the decryption step): verifying all 21 packages
  (Sony SHA-1 over 11.2 GB) took about 5 s. The full run took 141 s wall: the disc copy (the
  ISO is a separate volume, so `clonefile` gives EXDEV and the 15.4 GB disc tree is copied),
  disc hashing, about 80 s installing the updates (1.02: 12 s, 1.10: 22 s), and decryption.
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

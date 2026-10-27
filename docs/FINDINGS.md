# Findings

Measurements and facts, newest first within each section.

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

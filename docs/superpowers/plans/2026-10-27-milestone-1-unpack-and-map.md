# Milestone 1: Unpack, Verify v1.22, Map the Game — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From the owner's disc copy and the 21 Sony update packages, produce a verified GT6 v1.22 game tree with decrypted executables on this Mac, plus a map of GT6's code (functions, imports, SPU programs). That's the input milestone 2 translates.

**Architecture:** A standalone C++20 command-line tool, `gt6unpack`, built with CMake. It holds the PS3 format and crypto logic (SELF, PKG, PARAM.SFO), adapted from RPCS3's `rpcs3/Crypto/` (GPL-2.0) with RPCS3's utility dependencies stripped out. AES and SHA come from Apple CommonCrypto, inflate from the macOS SDK's zlib. Game mapping is a dev-only Python wrapper around ps3recomp's analysis tools (pinned submodule). Nothing produced from game data is ever written inside the repo.

**Tech Stack:** C++20 (Apple clang), CMake ≥ 3.24 + Ninja, CommonCrypto, zlib, doctest (vendored, MIT), Python 3.11+ with pytest (dev only), ps3recomp @ `4e8f3ca87a3e1d87bb83b8b7e9348fe2685cd514`.

**Spec:** `docs/superpowers/specs/2026-10-27-gt6-mac-port-design.md` (owner decisions O1-O12)

## Global Constraints

- Licence: **GPL-2.0-or-later**. No GPL-3.0-only code. Every borrowed file keeps its original notice and gets a header line `Adapted from RPCS3 (GPL-2.0), rpcs3/Crypto/<file>, commit c365ea76a552961ff078ea1a46da9d4b07729674`, plus an entry in `THIRD-PARTY-NOTICES.md` and README Credits.
- Never commit game files, keys files outside source, firmware, decrypted executables or translated code. Test fixtures that look like PS3 files are **generated at test time**, never committed.
- Edition: **BCES01977** only. Target version: **01.22**. Everything edition-specific is keyed by title ID.
- Real data locations (never modified by any task): disc `~/Gran Turismo 6/Gran Turismo 6 (UK)/Gran Turismo 6 (UK).iso`; updates `~/Gran Turismo 6/updates/` (21 `.pkg` files, `BCES01977-ver.xml`, `BCES01977-ver.xml.list`). Build output for real runs: `~/Gran Turismo 6/build/BCES01977-v1.22/`.
- Integration tests that need real data read `GT6_DISC_DIR` (mounted `PS3_GAME`'s parent) and `GT6_UPDATES_DIR`, and are **skipped** (not failed) when unset.
- Owner-facing docs follow the owner's conventions: decision, outcome or risk first; no code names in questions to the owner.
- Each design decision made while building goes in `docs/DECISIONS.md` as `D<n>` (date, decision, reasoning, who decided).
- Commits on branch `design/initial` → work continues on `m1/unpack` (created in Task 1). Don't push until the owner says so. Every commit ends with the attribution lines from the session.

## Review Focus

1. **A broken update chain** (one of 1.02-1.22 missing, or packages supplied out of filename order): expect a clear error naming the missing version, with nothing half-applied. Ordering comes from each package's `APP_VER`, never from the filename. → Task 6 tests.
2. **A truncated or corrupt download:** expect a SHA-1 mismatch against Sony's list, reported before any extraction. → Task 6 test.
3. **The 15.4 GB GT.VOL with not enough free disk, or the output on a different volume:** the APFS clone costs no space on the same volume. Otherwise expect a free-space check up front and a clear error. → Task 6 test (clone fallback path).
4. **Re-running into an existing output folder:** refuse without `--force`. With `--force`, rebuild in a staging folder and swap it in, never mixing old and new files. → Task 6 test.
5. **Paths with spaces and parentheses** (the owner's real paths): all tests use a temp root named `Gran Turismo 6 (UK) test`. → Tasks 5, 6, 8.

---

### Task 1: Repo foundation and the no-game-files guard

**Files:**
- Create: `LICENSE` (verbatim GPL-2.0 text, copy from `~/Developer/others/rpcs3/LICENSE`), `README.md` (replace), `THIRD-PARTY-NOTICES.md`, `CLAUDE.md`, `docs/DECISIONS.md`, `docs/FINDINGS.md`, `docs/BACKLOG.md`, `.gitignore`
- Create: `scripts/check_no_game_files.py`, `scripts/install_hooks.sh`, `.github/workflows/guard.yml`
- Test: `tests/scripts/test_check_no_game_files.py`

**Interfaces:**
- Produces: `check_no_game_files.py [paths...]`. Exits 1 and prints `BLOCKED <path>: <reason>` for any file whose first bytes are `SCE\0` (SELF/SPRX/PKG-SCE), `\x7fPKG` (PKG), `SCEUF` (PUP), `\x00PSF` (PARAM.SFO), or an ELF with `e_machine` 0x15 (PPC64) or 0x17 (SPU). Also blocks any file over 50 MB. With no args it checks `git diff --cached --name-only`.

- [ ] **Step 1: Branch.** `git checkout -b m1/unpack` (from `design/initial`).
- [ ] **Step 2: Write failing tests.** `test_blocks_self`, `test_blocks_pkg`, `test_blocks_pup`, `test_blocks_sfo`, `test_blocks_ppc64_elf`, `test_blocks_spu_elf`, `test_allows_arm64_elf` (e_machine 0xB7), `test_allows_text`, `test_blocks_large_file`. Each writes bytes to a tmp file inside a dir named `Gran Turismo 6 (UK) test` and asserts exit code and the `BLOCKED` line.
- [ ] **Step 3: Run.** `python3 -m pytest tests/scripts -q`. Expected: FAIL (script missing).
- [ ] **Step 4: Implement** the script (stdlib only), `install_hooks.sh` (writes `.git/hooks/pre-commit` calling it), and `guard.yml` (runs it over `git ls-files` on push/PR, macOS runner not required, ubuntu fine).
- [ ] **Step 5: Run.** Same command. Expected: PASS.
- [ ] **Step 6: Docs.**
  - `README.md`: what this is (native translation, not an emulator), status "pre-alpha, milestone 1", the legal statement (players bring their own legally owned copy; nothing from Sony or Polyphony is included or ever distributed; translation runs on the player's Mac), credits (RPCS3, ps3recomp, Bloodborne port, doctest), licence.
  - `docs/DECISIONS.md`: O1-O12 copied from spec §4 as D1-D12, plus D13 "C++ `gt6unpack` adapted from RPCS3 crypto; Python only for dev-time mapping" and D14 "Updates installed as a separate `dev_hdd0` tree, as on a real PS3, not merged into the disc tree".
  - `CLAUDE.md`: Bloodborne-style handover (how to write for the owner, decisions-don't-re-litigate pointer, machine and paths, next steps).
  - `.gitignore`: `build/ out/ *.pkg *.iso *.elf *.self *.sprx *.PUP game/ keys.local*`
- [ ] **Step 7: Commit.** `git add -A && scripts/check_no_game_files.py && git commit -m "Repo foundation: licence, docs, no-game-files guard"`, then run `scripts/install_hooks.sh`.

### Task 2: C++ build skeleton and crypto primitives

**Files:**
- Create: `CMakeLists.txt`, `tools/gt6unpack/CMakeLists.txt`, `tools/gt6unpack/src/crypto.hpp`, `tools/gt6unpack/src/crypto.cpp`, `third_party/doctest/doctest.h` (v2.4.11, MIT, with its LICENSE)
- Test: `tools/gt6unpack/tests/test_crypto.cpp`, `tools/gt6unpack/tests/main.cpp`

**Interfaces:**
- Produces (namespace `gt6::crypto`, all `std::span<const uint8_t>` in, `std::vector<uint8_t>` out unless noted):
  - `aes128_ctr(key16, iv16, data)`: encrypt == decrypt
  - `aes_cbc_decrypt(key /*16 or 32*/, iv16, data)`: no padding
  - `aes128_ecb_encrypt_block(key16, block16) -> std::array<uint8_t,16>`
  - `sha1(data) -> std::array<uint8_t,20>`, `sha256(data) -> std::array<uint8_t,32>`
  - `hmac_sha1(key, data) -> std::array<uint8_t,20>`
  - `class Sha1Stream { void update(span); std::array<uint8_t,20> final(); }` (multi-GB files)
  - `inflate_zlib(data, expected_size) -> std::vector<uint8_t>`: throws `std::runtime_error` on size mismatch
- CTest target `gt6unpack_tests`. CMake option `GT6_INTEGRATION` is read from env at test runtime, not configure time.

- [ ] **Step 1: Write failing tests:**
  - `aes128_ctr` NIST SP 800-38A F.5.1: key `2b7e151628aed2a6abf7158809cf4f3c`, IV `f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff`, PT block 1 `6bc1bee22e409f96e93d7e117393172a` → CT `874d6191b620e3261bef6864990db6ce`.
  - `aes_cbc_decrypt` AES-256 F.2.6 first block: key `603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4`, IV `000102030405060708090a0b0c0d0e0f`, CT `f58c4c04d6e5f1ba779eabfb5f7bfbd6` → PT `6bc1bee22e409f96e93d7e117393172a`.
  - `sha1("abc")` = `a9993e364706816aba3e25717850c26c9cd0d89d`.
  - `hmac_sha1` RFC 2202 case 1 (key 20×`0x0b`, "Hi There") = `b617318655057264e28bc0b6fb378c8ef146be00`.
  - `Sha1Stream` over "a","bc" equals `sha1("abc")`.
  - `inflate_zlib` round-trip of a `compress()`-ed buffer, and a throw on the wrong expected size.
- [ ] **Step 2: Run.** `cmake -S . -B build -G Ninja && cmake --build build && ctest --test-dir build`. Expected: FAIL (compile errors / missing symbols).
- [ ] **Step 3: Implement** with `CCCrypt` (kCCModeCTR via `CCCryptorCreateWithMode`, CBC with `ccNoPadding`), `CC_SHA1`/`CC_SHA256`/`CCHmac`, and zlib `uncompress`.
- [ ] **Step 4: Run.** Same. Expected: all pass.
- [ ] **Step 5: Commit.** "gt6unpack: build skeleton and crypto primitives"

### Task 3: Key vault

> **Blocked on the owner's key-handling decision (raised at plan handoff).** The default below follows RPCS3 and ps3recomp: the public keys live in source. If the owner chooses "player supplies keys", only `keys.cpp` changes. It then loads `~/Library/Application Support/GT6Mac/keys.toml` (same table shape), and the tests read the same file and are skipped when it's absent.

**Files:**
- Create: `tools/gt6unpack/src/keys.hpp`, `tools/gt6unpack/src/keys.cpp` (adapted from RPCS3 `key_vault.cpp`, only the tables GT6 needs: APP SELF keys for all revisions, NPDRM SELF keys, NP_KLIC_FREE, NP_KLIC_KEY, and the retail PKG (GPKG) key `2e7b71d7c9c9a14ea3221f188828b8f8`)
- Test: `tools/gt6unpack/tests/test_keys.cpp`

**Interfaces:**
- Produces:
  - `enum class SelfKeyType { App, Npdrm, Lv2, Isolated };`
  - `struct SelfKey { std::array<uint8_t,32> erk; std::array<uint8_t,16> riv; uint16_t revision; };`
  - `const SelfKey* find_self_key(SelfKeyType, uint16_t revision);` (nullptr if unknown)
  - `std::span<const uint8_t,16> pkg_retail_key();`, `std::span<const uint8_t,16> npdrm_klic_free();`, `std::span<const uint8_t,16> npdrm_klic_key();`

- [ ] **Step 1: Write failing tests.** `find_self_key(App, 0x001C)` is non-null (EMAIN.SELF's revision, seen in its header bytes 8-9). `find_self_key(App, 0x7FFF)` is null. `pkg_retail_key()` equals the GPKG bytes above.
- [ ] **Step 2: Run** ctest. Expected: FAIL.
- [ ] **Step 3: Implement** by transcribing the tables from RPCS3 `key_vault.cpp`, keeping the RPCS3 notice header.
- [ ] **Step 4: Run** ctest. Expected: PASS.
- [ ] **Step 5: Commit** and add the THIRD-PARTY-NOTICES entry. "gt6unpack: key vault (adapted from RPCS3)"

### Task 4: SELF/SPRX decryption to ELF

**Files:**
- Create: `tools/gt6unpack/src/self.hpp`, `tools/gt6unpack/src/self.cpp` (adapted from RPCS3 `unself.cpp`: SCE header, extended header, app info, metadata info AES-256-CBC with erk/riv, metadata headers/sections AES-128-CTR, zlib, ELF64 rebuild; plus the NPDRM path with the free-licence klicensee)
- Test: `tools/gt6unpack/tests/test_self.cpp`

**Interfaces:**
- Consumes: Task 2 crypto, Task 3 `find_self_key`.
- Produces:
  - `struct SelfInfo { uint16_t key_revision; uint16_t header_type; uint32_t program_type; bool npdrm; uint32_t npdrm_license; std::string content_id; };`
  - `SelfInfo inspect_self(std::span<const uint8_t>);`: throws `SelfError` on non-`SCE\0` input
  - `std::vector<uint8_t> decrypt_self(std::span<const uint8_t> self);`: returns an ELF64. Verifies the SHA-1-HMAC of every hashed section against the metadata and throws `SelfError("section N hash mismatch")`. Throws `SelfError("needs a licence file (paid content, out of scope)")` for NPDRM licence types other than free.
  - `class SelfError : public std::runtime_error`

- [ ] **Step 1: Write failing unit tests.** `inspect_self` throws on `"ELF\x7f..."` input. It throws a clear `SelfError` naming the revision on a header with key revision `0x7FFF`.
- [ ] **Step 2: Write failing integration tests** (skip unless `GT6_DISC_DIR` set):
  - `decrypt_self` on `PS3_GAME/USRDIR/EMAIN.SELF` → output starts `7f 45 4c 46 02 02` (ELF64, big-endian), `e_machine == 0x15`, at least one `PT_LOAD`.
  - Same for `EBOOT.BIN`.
  - The decryption is deterministic: the same SHA-256 on two runs.
- [ ] **Step 3: Run** ctest with `GT6_DISC_DIR` set to the mounted ISO (`hdiutil attach -readonly -nobrowse -mountpoint /private/tmp/gt6iso "<iso>"`). Expected: FAIL.
- [ ] **Step 4: Implement** by adapting RPCS3 `SELFDecrypter` (`LoadHeaders`, `LoadMetadata`, `DecryptData`, `MakeElf`), replacing `fs::file` with spans and `aes_*` with `gt6::crypto`.
- [ ] **Step 5: Run** ctest. Expected: PASS. Record the decrypted ELF SHA-256 values in `docs/FINDINGS.md` (hashes only).
- [ ] **Step 6: Commit.** "gt6unpack: SELF decryption (adapted from RPCS3)"

### Task 5: PKG extraction and PARAM.SFO

**Files:**
- Create: `tools/gt6unpack/src/sfo.hpp/.cpp`, `tools/gt6unpack/src/pkg.hpp/.cpp` (adapted from RPCS3 `unpkg.cpp`, retail finalized packages only), `tools/gt6unpack/tests/pkg_builder.hpp` (test-only synthetic PKG writer)
- Test: `tools/gt6unpack/tests/test_sfo.cpp`, `tools/gt6unpack/tests/test_pkg.cpp`

**Interfaces:**
- Produces:
  - `std::map<std::string, std::variant<std::string,uint32_t>> parse_sfo(std::span<const uint8_t>);`
  - `struct PkgEntry { std::string name; uint64_t offset, size; uint32_t type; bool is_dir; };`
  - `struct PkgInfo { std::string content_id; std::string title_id; std::vector<PkgEntry> entries; };`
  - `PkgInfo read_pkg(const std::filesystem::path&);` (decrypts only the file table)
  - `void extract_pkg(const std::filesystem::path& pkg, const std::filesystem::path& dest);` (streams in chunks of 1 MiB or more, never loads the whole package, rejects entries containing `..` or absolute paths)
  - `std::map<…> pkg_param_sfo(const std::filesystem::path&);` (extracts and parses only `PARAM.SFO`)
  - `class PkgError : public std::runtime_error`
- `pkg_builder.hpp`: `write_test_pkg(path, title_id, std::vector<std::pair<std::string, std::vector<uint8_t>>> files)` builds a finalized retail PKG encrypted with `pkg_retail_key()`, the same layout `read_pkg` expects.

- [ ] **Step 1: Write failing tests:**
  - `parse_sfo` on a built SFO with `TITLE_ID=BCES01977`, `APP_VER=01.22`, `ATTRIBUTE=0` (u32) returns those values.
  - A round-trip of a synthetic PKG containing `USRDIR/EBOOT.BIN` (random 3 MB) and `PARAM.SFO` into dir `Gran Turismo 6 (UK) test/out` gives byte-identical files.
  - A PKG entry named `../escape` → `PkgError`.
  - `pkg_param_sfo` returns `APP_VER`.
  - Integration (needs `GT6_UPDATES_DIR`): `pkg_param_sfo(EP9001-BCES01977_00-0000000000000000-A0102-V0101-PE.pkg)` has `TITLE_ID == "BCES01977"` and `APP_VER == "01.02"`.
- [ ] **Step 2: Run** ctest. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** ctest. Expected: PASS.
- [ ] **Step 5: Commit.** "gt6unpack: PKG extraction and PARAM.SFO (adapted from RPCS3)"

### Task 6: `gt6unpack build`: assemble a v1.22 game tree

**Files:**
- Create: `tools/gt6unpack/src/updates.hpp/.cpp`, `tools/gt6unpack/src/build_tree.hpp/.cpp`, `tools/gt6unpack/src/main.cpp`, `editions/BCES01977.json`
- Test: `tools/gt6unpack/tests/test_build_tree.cpp`

**Interfaces:**
- Consumes: Tasks 4 and 5.
- `editions/BCES01977.json` (committed, hashes only): `{ "title_id": "BCES01977", "target_app_ver": "01.22", "updates": [ {"app_ver":"01.02","sha1":"26044500a07d32e569de34c8738eaa872782df42"}, … all 21 from BCES01977-ver.xml.list … ] }`
- Produces:
  - `struct Edition { std::string title_id, target_app_ver; std::vector<std::pair<std::string,std::string>> updates; }; Edition load_edition(path);`
  - `std::vector<std::filesystem::path> order_updates(const Edition&, const std::vector<std::filesystem::path>& pkgs);`: orders by each package's own `APP_VER`. Throws `UpdateError("missing update 01.07")` on a gap and `UpdateError("…sha1 mismatch…")` on a checksum mismatch, both checked before any extraction.
  - `void build_tree(const BuildOptions&);` with `struct BuildOptions { path disc_dir, updates_dir, out_dir, edition_file; bool force; };`
- Output layout (D14):
  ```
  <out>/dev_bdvd/PS3_DISC.SFB, PS3_GAME/…   (APFS clonefile of the disc tree; copy fallback)
  <out>/dev_hdd0/game/BCES01977/…           (all updates installed in APP_VER order, later overwrite earlier)
  <out>/decrypted/<relative path>.elf       (every SCE file from both trees: EBOOT.BIN, EMAIN.SELF, *.sprx, *.self)
  <out>/build.json                          (tool version, inputs with SHA-1, final APP_VER, timings)
  ```
- CLI: `gt6unpack build --disc <dir> --updates <dir> --out <dir> [--edition editions/BCES01977.json] [--force]`
- Builds into `<out>.staging`, then renames over `<out>`. Before copying, it checks free space whenever `clonefile` returns `EXDEV`/`ENOTSUP`. Final check: `dev_hdd0/game/BCES01977/PARAM.SFO` `APP_VER == target_app_ver`, otherwise it throws.

- [ ] **Step 1: Write failing tests** (all synthetic, in `Gran Turismo 6 (UK) test`, with a 3-update test edition 01.02/01.03/01.04):
  - `test_order_by_app_ver_not_filename`: files named so the alphabetical order is wrong still come out 01.02, 01.03, 01.04.
  - `test_missing_update_named`: without 01.03 it throws, and the message contains `01.03`. `<out>` does not exist afterwards.
  - `test_sha1_mismatch_before_extract`: one flipped byte throws, and no staging dir is left behind.
  - `test_later_update_overwrites`: the same file in 01.02 and 01.04 gives 01.04's content.
  - `test_refuses_existing_out_without_force`, and `test_force_rebuilds_cleanly` (a stray file in the old `<out>` is gone afterwards).
  - `test_clone_fallback_copies`: inject a clone function returning `EXDEV`, and the files are still present.
  - `test_final_app_ver_checked`: an edition targeting 01.05 throws.
- [ ] **Step 2: Run** ctest. Expected: FAIL.
- [ ] **Step 3: Implement** (inject the clone function through `BuildOptions` for the test; the default is `clonefile(2)`).
- [ ] **Step 4: Run** ctest. Expected: PASS.
- [ ] **Step 5: Real run.** Mount the ISO, then `build/tools/gt6unpack/gt6unpack build --disc /private/tmp/gt6iso --updates "$HOME/Gran Turismo 6/updates" --out "$HOME/Gran Turismo 6/build/BCES01977-v1.22"`. Expected: exit 0, `build.json` final APP_VER `01.22`. Record the timings and the decrypted file list in FINDINGS.
- [ ] **Step 6: Oracle check against RPCS3** (one-off, record the result): `~/Developer/others/rpcs3-bin/RPCS3.app/Contents/MacOS/rpcs3 --installpkg <each pkg in order>`, then diff the file list and SHA-256s of `~/Library/Application Support/rpcs3/dev_hdd0/game/BCES01977` against `<out>/dev_hdd0/game/BCES01977`. Expected: identical. Note RPCS3's version in FINDINGS.
- [ ] **Step 7: Commit.** "gt6unpack build: assemble verified v1.22 tree"

### Task 7: `gt6unpack verify` and the committed v1.22 manifest

**Files:**
- Create: `tools/gt6unpack/src/manifest.hpp/.cpp`, `manifests/BCES01977-v1.22.json` (generated by Step 5, hashes only)
- Modify: `tools/gt6unpack/src/main.cpp` (add `manifest` and `verify` subcommands)
- Test: `tools/gt6unpack/tests/test_manifest.cpp`

**Interfaces:**
- Produces:
  - `gt6unpack manifest <out> -o <file>` writes `{ "title_id", "app_ver", "files": [{"path","size","sha256"}] }` covering `dev_bdvd`, `dev_hdd0` and `decrypted`, sorted by path.
  - `gt6unpack verify <out> --manifest <file>` exits 0 when it matches, or 1 and prints `MISMATCH <path>`, `MISSING <path>`, `EXTRA <path>` (extra files are a warning: exit 0 when there are no mismatches or missing files).
  - `struct VerifyReport { std::vector<std::string> mismatched, missing, extra; bool ok() const; }; VerifyReport verify_tree(path out, const Manifest&);`

- [ ] **Step 1: Write failing tests.** A synthetic tree with a manifest matches. A one-byte change gives `MISMATCH`. A deleted file gives `MISSING`. An added file gives `EXTRA` and `ok()==true`.
- [ ] **Step 2: Run** ctest. Expected: FAIL.
- [ ] **Step 3: Implement** with streaming SHA-256.
- [ ] **Step 4: Run** ctest. Expected: PASS.
- [ ] **Step 5: Generate** `manifests/BCES01977-v1.22.json` from the real tree, then run `verify` against it. Expected: exit 0. Run `scripts/check_no_game_files.py manifests/*.json`. Expected: clean.
- [ ] **Step 6:** Add to BACKLOG: "Disc check against the community IRD file (per-file MD5s keyed by ISO sector; needs an ISO directory reader). Until then, the disc's GT.VOL is unverified against an independent source." Record the risk in FINDINGS.
- [ ] **Step 7: Commit.** "gt6unpack verify + v1.22 manifest (hashes only)"

### Task 8: Map the game code with ps3recomp (dev-only)

**Files:**
- Create: `third_party/ps3recomp` (git submodule at `4e8f3ca87a3e1d87bb83b8b7e9348fe2685cd514`), `scripts/map_game.py`, `scripts/requirements-dev.txt` (ps3recomp's `requirements.txt` plus pytest)
- Test: `tests/scripts/test_map_game.py`, fixtures `tests/scripts/fixtures/map/*.json` (small, hand-written in ps3recomp's output shapes, no game data)

**Interfaces:**
- Consumes: `<out>/decrypted/**/*.elf` from Task 6.
- Produces: `scripts/map_game.py <out> [-o <out>/map]` runs, for each decrypted ELF, ps3recomp's `ppu_loader.py`, `find_functions.py`, `gen_imports.py`, `extract_spu_images.py`, `extract_jobmods.py` (call them with `python3 -I <tool> …`, check ps3recomp's `docs/TOOLS.md` for the exact flags), then writes `<out>/map/summary.json`:
  ```json
  { "elfs": [ { "path": "...", "functions": 0, "imports": {"<module>": 0}, "unresolved_nids": 0,
               "spu_images": [ {"name": "...", "size": 0} ], "jobmods": 0 } ],
    "totals": { "functions": 0, "imports": 0, "spu_images": 0, "spu_bytes": 0 } }
  ```
  `summarize(tool_outputs_dir) -> dict` is the pure function under test.

- [ ] **Step 1: Write failing tests.** `summarize(fixtures)` returns the totals the fixtures imply. A missing tool output for one ELF gives an `"error"` field for that ELF and does not crash.
- [ ] **Step 2: Run** `python3 -m pytest tests/scripts -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Add the submodule. Set up a dev venv in `.venv/` (gitignored).
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Real run** on `~/Gran Turismo 6/build/BCES01977-v1.22`. Record in `docs/FINDINGS.md`: the function count, imports per system module (the list of PS3 libraries GT6 needs, which is the runtime's to-do list), the SPU image count and total size, job modules (SPURS usage), unresolved NIDs, and the run time.
- [ ] **Step 6: Commit.** "Map GT6 code with ps3recomp (dev tooling)"

### Task 9: Milestone 1 write-up

**Files:**
- Modify: `docs/FINDINGS.md`, `docs/DECISIONS.md`, `docs/BACKLOG.md`, `README.md` (status), `CLAUDE.md` (state as of date, next steps = milestone 2 plan)

- [ ] **Step 1:** Run the full test suite: `ctest --test-dir build` and `python3 -m pytest tests -q`, with the integration env vars set. Expected: all pass, with none skipped. Paste the summary lines into FINDINGS.
- [ ] **Step 2:** Run `scripts/check_no_game_files.py $(git ls-files)`. Expected: clean.
- [ ] **Step 3:** Write the owner summary at the top of FINDINGS (outcome first, a few lines): v1.22 verified yes/no, the size of the code, how many SPU programs, the biggest risk found, and what milestone 2 needs.
- [ ] **Step 4:** Log in BACKLOG:
  - the player-side update download, with TLS verified against Sony roots extracted from the disc's PUP, without RPCS3 (spec §6.1)
  - ISO reading without `hdiutil`
  - the IRD check
  - other editions
- [ ] **Step 5: Commit.** "Milestone 1 write-up"

# Third-party notices

| Project | Licence | Use here |
|---|---|---|
| [RPCS3](https://github.com/RPCS3/rpcs3) | GPL-2.0-only ("Most files are licensed under the terms of GNU GPL-2.0-only", RPCS3 README) | Reference for PS3 behaviour; PS3 crypto code adapted for the `gt6unpack` unpacker (added in milestone 1). File headers credit copied code. The adapted files are GPL-2.0-only, so `gt6unpack` as a whole (everything under `tools/gt6unpack/`) is distributed under GPL-2.0-only (decision D24). `tools/gt6unpack/src/keys.cpp` and `keys.hpp` are adapted from `rpcs3/Crypto/key_vault.cpp` and `key_vault.h`; `tools/gt6unpack/src/self.cpp` and `self.hpp` are adapted from `rpcs3/Crypto/unself.cpp` and `unself.h`; `tools/gt6unpack/src/pkg.cpp` and `pkg.hpp` are adapted from `rpcs3/Crypto/unpkg.cpp` and `unpkg.h` (all commit c365ea76a552961ff078ea1a46da9d4b07729674). |
| [ps3recomp](https://github.com/sp00nznet/ps3recomp) by Ned Heller / sp00nznet | MIT | Git submodule at `third_party/ps3recomp`, pinned to commit 4e8f3ca87a3e1d87bb83b8b7e9348fe2685cd514; the pinned commit is unmodified, and the project's changes to it are carried as patch files in `patches/ps3recomp/`, applied to the checkout at configure time (D28). Its tools translate the game (`scripts/map_game.py`, `scripts/translate_game.py`, dev-only), and its runtime is linked into the port's `gt6` executable. `port/CMakeLists.txt`, `port/main.cpp` and `port/gt6_overrides.cpp` are adapted from its project template (`templates/project/CMakeLists.txt`, `main.cpp`, `stubs.cpp`); they keep its copyright line and are offered under GPL-2.0-or-later, as MIT allows. Its MIT notice stays with any code taken; full text below and in `third_party/ps3recomp/LICENSE`. |
| at3_standalone (FFmpeg's ATRAC3plus decoder as extracted by PPSSPP), inside ps3recomp | LGPL-2.1-or-later | Compiled into ps3recomp's runtime, so it is linked into `gt6`. Kept in `third_party/ps3recomp/third_party/at3_standalone/` with its own README and notices. |
| [bloodborne_mac_port](https://github.com/Wooloomooloo2/bloodborne_mac_port) | GPL-2.0-or-later | Launcher, renderer machinery and conventions (added as needed). |
| [doctest](https://github.com/doctest/doctest) | MIT | C++ unit tests: v2.4.11, single header at `third_party/doctest/doctest.h`, licence at `third_party/doctest/LICENSE.txt`. |

Every source file carries an `SPDX-License-Identifier` line: `GPL-2.0-only` under
`tools/gt6unpack/`, `GPL-2.0-or-later` for the rest of the project.

Every borrowed file or idea is also credited in the README and in file headers where code is
copied. The MIT licence texts are reproduced here when the code is added.

## ps3recomp licence (MIT)

```
MIT License

Copyright (c) 2026 Ned Heller / sp00nznet

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

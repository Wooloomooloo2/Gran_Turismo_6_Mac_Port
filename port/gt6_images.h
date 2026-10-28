/* SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Gran Turismo 6 for Mac: which port build runs which EMAIN.SELF (D44, D47).
 *
 * $GT6_IMAGES (set by scripts/boot_game.py) lists every build the harness found, as
 * "<self sha256>=<binary>|<elf>|<patch-set sha256>;...". gt6_find_image() looks up the build
 * for one SELF hash. A build made from another ps3recomp patch set than this binary's is
 * refused (GT6_IMAGE_STALE), never run: it would silently lack the current fixes.
 * Header-only so tests/scripts/test_gt6_images.py can compile it alone.
 */
#pragma once
#include <string>

enum gt6_image_match { GT6_IMAGE_NONE = 0, GT6_IMAGE_FOUND = 1, GT6_IMAGE_STALE = -1 };

/* Look up `sha` in `list`. FOUND fills bin and elf; STALE fills bin and stale_patches (the
 * build's patch-set hash, or "" when its entry names none). Entries that do not parse are
 * skipped. */
static inline gt6_image_match gt6_find_image(const char* list, const char* sha,
                                             const char* patches, std::string& bin,
                                             std::string& elf, std::string& stale_patches)
{
    const std::string all = list ? list : "";
    size_t pos = 0;
    while (pos < all.size()) {
        size_t end = all.find(';', pos);
        if (end == std::string::npos) end = all.size();
        const std::string item = all.substr(pos, end - pos);
        pos = end + 1;
        const size_t eq = item.find('=');
        const size_t bar = eq == std::string::npos ? std::string::npos : item.find('|', eq);
        if (eq == std::string::npos || bar == std::string::npos) continue;
        if (item.compare(0, eq, sha) != 0 || eq != std::string(sha).size()) continue;
        const size_t bar2 = item.find('|', bar + 1);
        bin = item.substr(eq + 1, bar - eq - 1);
        elf = item.substr(bar + 1, bar2 == std::string::npos ? std::string::npos : bar2 - bar - 1);
        const std::string ph = bar2 == std::string::npos ? "" : item.substr(bar2 + 1);
        if (ph != patches) { stale_patches = ph; return GT6_IMAGE_STALE; }
        return GT6_IMAGE_FOUND;
    }
    return GT6_IMAGE_NONE;
}

#include "doctest.h"
#include "keys.hpp"

#include <cstdint>
#include <vector>

using namespace gt6;

namespace {
std::vector<uint8_t> hex(const char* s) {
    std::vector<uint8_t> out;
    auto nib = [](char c) { return c <= '9' ? c - '0' : (c | 0x20) - 'a' + 10; };
    for (; s[0] && s[1]; s += 2) out.push_back(static_cast<uint8_t>(nib(s[0]) << 4 | nib(s[1])));
    return out;
}
template <class C>
std::vector<uint8_t> vec(const C& s) { return {s.begin(), s.end()}; }
}  // namespace

TEST_CASE("app key for EMAIN.SELF revision 0x001C exists") {
    const SelfKey* k = find_self_key(SelfKeyType::App, 0x001C);
    REQUIRE(k != nullptr);
    CHECK(k->revision == 0x001C);
    CHECK(vec(k->erk) == hex("CFF025375BA0079226BE01F4A31F346D79F62CFB643CA910E16CF60BD9092752"));
    CHECK(vec(k->riv) == hex("FD40664E2EBBA01BF359B0DCDF543DA4"));
}

TEST_CASE("unknown revisions are null") {
    CHECK(find_self_key(SelfKeyType::App, 0x7FFF) == nullptr);
    CHECK(find_self_key(SelfKeyType::Npdrm, 0x7FFF) == nullptr);
}

TEST_CASE("every populated entry is found by its own revision") {
    for (uint16_t r = 0; r <= 0x1D; ++r)
        if (const SelfKey* k = find_self_key(SelfKeyType::App, r)) CHECK(k->revision == r);
    const SelfKey* n = find_self_key(SelfKeyType::Npdrm, 0x001C);
    REQUIRE(n != nullptr);
    CHECK(n->revision == 0x001C);
    CHECK(find_self_key(SelfKeyType::App, 0x0012) == nullptr);
}

TEST_CASE("unpopulated types return null") {
    CHECK(find_self_key(SelfKeyType::Lv2, 0) == nullptr);
    CHECK(find_self_key(SelfKeyType::Isolated, 1) == nullptr);
}

TEST_CASE("PKG and NPDRM constants") {
    CHECK(vec(pkg_retail_key()) == hex("2e7b71d7c9c9a14ea3221f188828b8f8"));
    CHECK(vec(npdrm_klic_free()) == hex("72f990788f9cff745725f08e4c128387"));
    CHECK(vec(npdrm_klic_key()) == hex("f2fbca7a75b04edc1390638ccdfdd1ee"));
}

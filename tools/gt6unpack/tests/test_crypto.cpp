// SPDX-License-Identifier: GPL-2.0-only
#include "doctest.h"
#include "crypto.hpp"

#include <zlib.h>

#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

using namespace gt6::crypto;

namespace {
std::vector<uint8_t> hex(const std::string& s) {
    std::vector<uint8_t> out;
    for (size_t i = 0; i + 1 < s.size(); i += 2)
        out.push_back(static_cast<uint8_t>(std::stoi(s.substr(i, 2), nullptr, 16)));
    return out;
}
std::vector<uint8_t> bytes(const std::string& s) { return {s.begin(), s.end()}; }
template <class C> std::vector<uint8_t> vec(const C& c) { return {c.begin(), c.end()}; }
}  // namespace

TEST_CASE("aes128_ctr NIST SP 800-38A F.5.1") {
    auto key = hex("2b7e151628aed2a6abf7158809cf4f3c");
    auto iv = hex("f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff");
    auto pt = hex("6bc1bee22e409f96e93d7e117393172a");
    auto ct = aes128_ctr(key, iv, pt);
    CHECK(ct == hex("874d6191b620e3261bef6864990db6ce"));
    CHECK(aes128_ctr(key, iv, ct) == pt);
}

TEST_CASE("aes_cbc_decrypt AES-256 F.2.6 first block") {
    auto key = hex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4");
    auto iv = hex("000102030405060708090a0b0c0d0e0f");
    auto ct = hex("f58c4c04d6e5f1ba779eabfb5f7bfbd6");
    CHECK(aes_cbc_decrypt(key, iv, ct) == hex("6bc1bee22e409f96e93d7e117393172a"));
}

TEST_CASE("aes128_ecb_encrypt_block FIPS-197 C.1") {
    auto r = aes128_ecb_encrypt_block(hex("000102030405060708090a0b0c0d0e0f"),
                                      hex("00112233445566778899aabbccddeeff"));
    CHECK(vec(r) == hex("69c4e0d86a7b0430d8cdb78070b4c55a"));
}

TEST_CASE("sha1 and sha256 of abc") {
    CHECK(vec(sha1(bytes("abc"))) == hex("a9993e364706816aba3e25717850c26c9cd0d89d"));
    CHECK(vec(sha256(bytes("abc"))) ==
          hex("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
}

TEST_CASE("hmac_sha1 RFC 2202 case 1") {
    std::vector<uint8_t> key(20, 0x0b);
    CHECK(vec(hmac_sha1(key, bytes("Hi There"))) ==
          hex("b617318655057264e28bc0b6fb378c8ef146be00"));
}

TEST_CASE("Sha1Stream matches one-shot sha1") {
    Sha1Stream s;
    s.update(bytes("a"));
    s.update(bytes("bc"));
    CHECK(s.final() == sha1(bytes("abc")));
}

TEST_CASE("inflate_zlib round trip and size mismatch") {
    std::vector<uint8_t> src(1000);
    for (size_t i = 0; i < src.size(); ++i) src[i] = static_cast<uint8_t>(i % 7);
    uLongf clen = compressBound(static_cast<uLong>(src.size()));
    std::vector<uint8_t> comp(clen);
    REQUIRE(compress(comp.data(), &clen, src.data(), static_cast<uLong>(src.size())) == Z_OK);
    comp.resize(clen);
    CHECK(inflate_zlib(comp, src.size()) == src);
    CHECK_THROWS_AS(inflate_zlib(comp, src.size() - 1), std::runtime_error);
    CHECK_THROWS_AS(inflate_zlib(comp, src.size() + 1), std::runtime_error);
}

#include "crypto.hpp"

#include <CommonCrypto/CommonCryptor.h>
#include <CommonCrypto/CommonDigest.h>
#include <CommonCrypto/CommonHMAC.h>
#include <zlib.h>

#include <algorithm>
#include <stdexcept>
#include <string>

namespace gt6::crypto {

namespace {
void require(bool ok, const char* msg) {
    if (!ok) throw std::runtime_error(msg);
}
// CommonCrypto length arguments are CC_LONG (32-bit); feed large inputs in chunks.
constexpr size_t kChunk = 1u << 30;
}  // namespace

std::vector<uint8_t> aes128_ctr(Bytes key, Bytes iv, Bytes data) {
    require(key.size() == 16 && iv.size() == 16, "aes128_ctr: key and iv must be 16 bytes");
    CCCryptorRef ref = nullptr;
    CCCryptorStatus st = CCCryptorCreateWithMode(
        kCCEncrypt, kCCModeCTR, kCCAlgorithmAES, ccNoPadding, iv.data(), key.data(), key.size(),
        nullptr, 0, 0, kCCModeOptionCTR_BE, &ref);
    require(st == kCCSuccess, "aes128_ctr: cryptor create failed");
    std::vector<uint8_t> out(data.size());
    size_t done = 0;
    for (size_t off = 0; off < data.size() && st == kCCSuccess; off += kChunk) {
        size_t n = std::min(kChunk, data.size() - off);
        st = CCCryptorUpdate(ref, data.data() + off, n, out.data() + off, n, &done);
    }
    CCCryptorRelease(ref);
    require(st == kCCSuccess, "aes128_ctr: update failed");
    return out;
}

std::vector<uint8_t> aes_cbc_decrypt(Bytes key, Bytes iv, Bytes data) {
    require(key.size() == 16 || key.size() == 32, "aes_cbc_decrypt: key must be 16 or 32 bytes");
    require(iv.size() == 16, "aes_cbc_decrypt: iv must be 16 bytes");
    require(data.size() % 16 == 0, "aes_cbc_decrypt: data not a multiple of 16");
    std::vector<uint8_t> out(data.size());
    if (data.empty()) return out;
    size_t moved = 0;
    CCCryptorStatus st = CCCrypt(kCCDecrypt, kCCAlgorithmAES, 0, key.data(), key.size(), iv.data(),
                                 data.data(), data.size(), out.data(), out.size(), &moved);
    require(st == kCCSuccess && moved == data.size(), "aes_cbc_decrypt: CCCrypt failed");
    return out;
}

std::array<uint8_t, 16> aes128_ecb_encrypt_block(Bytes key, Bytes block) {
    require(key.size() == 16 && block.size() == 16, "aes128_ecb: key and block must be 16 bytes");
    std::array<uint8_t, 16> out{};
    size_t moved = 0;
    CCCryptorStatus st = CCCrypt(kCCEncrypt, kCCAlgorithmAES, kCCOptionECBMode, key.data(), 16,
                                 nullptr, block.data(), 16, out.data(), 16, &moved);
    require(st == kCCSuccess && moved == 16, "aes128_ecb: CCCrypt failed");
    return out;
}

struct Sha1Stream::Impl {
    CC_SHA1_CTX ctx;
};

Sha1Stream::Sha1Stream() : impl_(std::make_unique<Impl>()) { CC_SHA1_Init(&impl_->ctx); }
Sha1Stream::~Sha1Stream() = default;

void Sha1Stream::update(Bytes data) {
    for (size_t off = 0; off < data.size(); off += kChunk) {
        size_t n = std::min(kChunk, data.size() - off);
        CC_SHA1_Update(&impl_->ctx, data.data() + off, static_cast<CC_LONG>(n));
    }
}

std::array<uint8_t, 20> Sha1Stream::final() {
    std::array<uint8_t, 20> out{};
    CC_SHA1_Final(out.data(), &impl_->ctx);
    return out;
}

std::array<uint8_t, 20> sha1(Bytes data) {
    Sha1Stream s;
    s.update(data);
    return s.final();
}

struct Sha256Stream::Impl {
    CC_SHA256_CTX ctx;
};

Sha256Stream::Sha256Stream() : impl_(std::make_unique<Impl>()) { CC_SHA256_Init(&impl_->ctx); }
Sha256Stream::~Sha256Stream() = default;

void Sha256Stream::update(Bytes data) {
    for (size_t off = 0; off < data.size(); off += kChunk)
        CC_SHA256_Update(&impl_->ctx, data.data() + off,
                         static_cast<CC_LONG>(std::min(kChunk, data.size() - off)));
}

std::array<uint8_t, 32> Sha256Stream::final() {
    std::array<uint8_t, 32> out{};
    CC_SHA256_Final(out.data(), &impl_->ctx);
    return out;
}

std::array<uint8_t, 32> sha256(Bytes data) {
    Sha256Stream s;
    s.update(data);
    return s.final();
}

std::string to_hex(Bytes d) {
    static const char* k = "0123456789abcdef";
    std::string s;
    for (uint8_t b : d) {
        s += k[b >> 4];
        s += k[b & 15];
    }
    return s;
}

std::array<uint8_t, 20> hmac_sha1(Bytes key, Bytes data) {
    std::array<uint8_t, 20> out{};
    CCHmac(kCCHmacAlgSHA1, key.data(), key.size(), data.data(), data.size(), out.data());
    return out;
}

std::vector<uint8_t> inflate_zlib(Bytes data, size_t expected_size) {
    std::vector<uint8_t> out(expected_size);
    uLongf dest_len = static_cast<uLongf>(expected_size);
    int rc = uncompress(out.data(), &dest_len, data.data(), static_cast<uLong>(data.size()));
    if (rc != Z_OK)
        throw std::runtime_error("inflate_zlib: uncompress failed (zlib code " +
                                 std::to_string(rc) + ")");
    if (dest_len != expected_size)
        throw std::runtime_error("inflate_zlib: size mismatch");
    return out;
}

}  // namespace gt6::crypto

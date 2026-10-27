// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <vector>

// Thin wrappers over Apple CommonCrypto and zlib.
namespace gt6::crypto {

using Bytes = std::span<const uint8_t>;

// AES-128 CTR (big-endian counter); encrypt and decrypt are the same operation.
std::vector<uint8_t> aes128_ctr(Bytes key16, Bytes iv16, Bytes data);
// AES-CBC decrypt, no padding. Key is 16 or 32 bytes; data length must be a multiple of 16.
std::vector<uint8_t> aes_cbc_decrypt(Bytes key, Bytes iv16, Bytes data);
std::array<uint8_t, 16> aes128_ecb_encrypt_block(Bytes key16, Bytes block16);

std::array<uint8_t, 20> sha1(Bytes data);
std::array<uint8_t, 32> sha256(Bytes data);
std::array<uint8_t, 20> hmac_sha1(Bytes key, Bytes data);

// Incremental SHA-1 for very large inputs.
class Sha1Stream {
public:
    Sha1Stream();
    ~Sha1Stream();
    Sha1Stream(const Sha1Stream&) = delete;
    Sha1Stream& operator=(const Sha1Stream&) = delete;
    void update(Bytes data);
    std::array<uint8_t, 20> final();

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

// Incremental SHA-256 for very large inputs.
class Sha256Stream {
public:
    Sha256Stream();
    ~Sha256Stream();
    Sha256Stream(const Sha256Stream&) = delete;
    Sha256Stream& operator=(const Sha256Stream&) = delete;
    void update(Bytes data);
    std::array<uint8_t, 32> final();

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

// Lower-case hex of a byte string.
std::string to_hex(Bytes data);

// Inflates a zlib stream; throws std::runtime_error on error or if the result
// is not exactly expected_size bytes.
std::vector<uint8_t> inflate_zlib(Bytes data, size_t expected_size);

}  // namespace gt6::crypto

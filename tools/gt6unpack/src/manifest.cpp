// SPDX-License-Identifier: GPL-2.0-only
#include "manifest.hpp"

#include "crypto.hpp"
#include "json_util.hpp"

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <map>
#include <span>

namespace gt6 {

namespace fs = std::filesystem;

namespace {

const char* const kRoots[] = {"dev_bdvd", "dev_hdd0", "decrypted"};

struct Hashed {
    uint64_t size;
    std::string sha256;
};

Hashed hash_file(const fs::path& p) {
    std::ifstream f(p, std::ios::binary);
    if (!f) throw ManifestError("cannot read " + p.string());
    crypto::Sha256Stream h;
    // One zero-filled buffer for the whole run: allocating 8 MiB per file (16k+ files) is slow.
    static std::vector<uint8_t> buf(8u << 20);
    uint64_t total = 0;
    while (f) {
        f.read(reinterpret_cast<char*>(buf.data()), std::streamsize(buf.size()));
        const size_t n = size_t(f.gcount());
        h.update(std::span<const uint8_t>(buf.data(), n));
        total += n;
    }
    if (!f.eof()) throw ManifestError("read failed for " + p.string());
    return {total, crypto::to_hex(h.final())};
}

// Relative '/' paths of every regular file under the three roots, sorted.
std::vector<std::string> list_files(const fs::path& out) {
    std::vector<std::string> v;
    for (const char* root : kRoots) {
        const fs::path r = out / root;
        std::error_code ec;
        if (!fs::is_directory(r, ec)) continue;
        for (auto it = fs::recursive_directory_iterator(r); it != fs::recursive_directory_iterator(); ++it)
            if (it->is_regular_file() && !it->is_symlink()) v.push_back(it->path().lexically_relative(out).generic_string());
    }
    std::sort(v.begin(), v.end());
    return v;
}

// Minimal reader for the manifest's own JSON shape (objects, arrays, strings, unsigned numbers).
class Reader {
public:
    explicit Reader(std::string t) : t_(std::move(t)) {}

    Manifest manifest() {
        Manifest m;
        expect('{');
        for (bool first = true;; first = false) {
            ws();
            if (peek() == '}') break;
            if (!first) expect(',');
            const std::string k = str();
            expect(':');
            if (k == "title_id") m.title_id = str();
            else if (k == "app_ver") m.app_ver = str();
            else if (k == "files") files(m);
            else throw fail("unknown key " + k);
        }
        expect('}');
        return m;
    }

private:
    std::string t_;
    size_t i_ = 0;

    ManifestError fail(const std::string& what) const {
        return ManifestError("manifest: " + what + " at offset " + std::to_string(i_));
    }
    void ws() {
        while (i_ < t_.size() && (t_[i_] == ' ' || t_[i_] == '\n' || t_[i_] == '\r' || t_[i_] == '\t')) ++i_;
    }
    char peek() {
        ws();
        return i_ < t_.size() ? t_[i_] : '\0';
    }
    void expect(char c) {
        if (peek() != c) throw fail(std::string("expected '") + c + "'");
        ++i_;
    }
    std::string str() {
        expect('"');
        std::string s;
        while (i_ < t_.size() && t_[i_] != '"') {
            char c = t_[i_++];
            if (c == '\\') {
                if (i_ >= t_.size()) break;
                c = t_[i_++];
                if (c == 'u') {
                    if (i_ + 4 > t_.size()) throw fail("bad escape");
                    c = char(std::stoi(t_.substr(i_, 4), nullptr, 16));
                    i_ += 4;
                }
            }
            s += c;
        }
        expect('"');
        return s;
    }
    uint64_t num() {
        ws();
        const size_t b = i_;
        while (i_ < t_.size() && t_[i_] >= '0' && t_[i_] <= '9') ++i_;
        if (b == i_) throw fail("expected a number");
        return std::stoull(t_.substr(b, i_ - b));
    }
    void files(Manifest& m) {
        expect('[');
        for (bool first = true; peek() != ']'; first = false) {
            if (!first) expect(',');
            ManifestFile f;
            expect('{');
            for (bool kfirst = true; peek() != '}'; kfirst = false) {
                if (!kfirst) expect(',');
                const std::string k = str();
                expect(':');
                if (k == "path") f.path = str();
                else if (k == "size") f.size = num();
                else if (k == "sha256") f.sha256 = str();
                else throw fail("unknown file key " + k);
            }
            expect('}');
            m.files.push_back(std::move(f));
        }
        expect(']');
    }
};

}  // namespace

Manifest make_manifest(const fs::path& out, const std::string& title_id, const std::string& app_ver) {
    Manifest m;
    m.title_id = title_id;
    m.app_ver = app_ver;
    for (const std::string& rel : list_files(out)) {
        const Hashed h = hash_file(out / rel);
        m.files.push_back({rel, h.size, h.sha256});
    }
    return m;
}

void write_manifest(const fs::path& file, const Manifest& m) {
    std::ofstream j(file, std::ios::binary | std::ios::trunc);
    if (!j) throw ManifestError("cannot write " + file.string());
    j << "{\n  \"title_id\": " << json_str(m.title_id) << ",\n  \"app_ver\": " << json_str(m.app_ver)
      << ",\n  \"files\": [";
    for (size_t i = 0; i < m.files.size(); ++i)
        j << (i ? "," : "") << "\n    {\"path\": " << json_str(m.files[i].path) << ", \"size\": " << m.files[i].size
          << ", \"sha256\": " << json_str(m.files[i].sha256) << "}";
    j << "\n  ]\n}\n";
    j.flush();
    if (!j) throw ManifestError("write failed for " + file.string());
}

Manifest read_manifest(const fs::path& file) {
    std::ifstream f(file, std::ios::binary);
    if (!f) throw ManifestError("cannot read " + file.string());
    return Reader(std::string(std::istreambuf_iterator<char>(f), {})).manifest();
}

VerifyReport verify_tree(const fs::path& out, const Manifest& m) {
    VerifyReport r;
    std::map<std::string, const ManifestFile*> want;
    for (const ManifestFile& f : m.files) want[f.path] = &f;
    for (const auto& [path, f] : want) {
        std::error_code ec;
        const fs::path p = out / path;
        if (!fs::is_regular_file(p, ec)) {
            r.missing.push_back(path);
            continue;
        }
        // A size difference is a mismatch without reading the file.
        if (fs::file_size(p) != f->size || hash_file(p).sha256 != f->sha256) r.mismatched.push_back(path);
    }
    for (const std::string& rel : list_files(out))
        if (!want.count(rel)) r.extra.push_back(rel);
    return r;
}

}  // namespace gt6

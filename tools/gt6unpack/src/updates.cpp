// Edition files and update ordering/verification. No third-party code.
#include "updates.hpp"

#include "crypto.hpp"
#include "pkg.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <iterator>
#include <map>
#include <variant>

namespace gt6 {
namespace {

namespace fs = std::filesystem;

// ---- minimal JSON reader (objects, arrays, strings; other scalars are skipped) ----

struct Json;
using JsonObject = std::map<std::string, Json>;
using JsonArray = std::vector<Json>;
struct Json {
    std::variant<std::monostate, std::string, JsonArray, JsonObject> v;
};

class JsonParser {
public:
    explicit JsonParser(std::string s) : s_(std::move(s)) {}

    Json parse() {
        Json j = value();
        ws();
        if (p_ != s_.size()) fail("trailing characters");
        return j;
    }

private:
    [[noreturn]] void fail(const std::string& why) const {
        throw UpdateError("edition file: " + why + " at offset " + std::to_string(p_));
    }
    void ws() {
        while (p_ < s_.size() && std::isspace(static_cast<unsigned char>(s_[p_]))) ++p_;
    }
    char peek() {
        ws();
        if (p_ >= s_.size()) fail("unexpected end");
        return s_[p_];
    }
    void expect(char c) {
        if (peek() != c) fail(std::string("expected '") + c + "'");
        ++p_;
    }

    Json value() {
        const char c = peek();
        if (c == '{') return {object()};
        if (c == '[') return {array()};
        if (c == '"') return {string()};
        // Numbers, true, false, null: this format never needs them; accept and discard.
        const size_t start = p_;
        while (p_ < s_.size() && (std::isalnum(static_cast<unsigned char>(s_[p_])) || s_[p_] == '-' ||
                                  s_[p_] == '+' || s_[p_] == '.'))
            ++p_;
        if (p_ == start) fail("unexpected character");
        return {};
    }

    JsonObject object() {
        JsonObject o;
        expect('{');
        if (peek() == '}') {
            ++p_;
            return o;
        }
        for (;;) {
            std::string k = string();
            expect(':');
            o[k] = value();
            if (peek() == ',') {
                ++p_;
                continue;
            }
            expect('}');
            return o;
        }
    }

    JsonArray array() {
        JsonArray a;
        expect('[');
        if (peek() == ']') {
            ++p_;
            return a;
        }
        for (;;) {
            a.push_back(value());
            if (peek() == ',') {
                ++p_;
                continue;
            }
            expect(']');
            return a;
        }
    }

    std::string string() {
        expect('"');
        std::string out;
        while (p_ < s_.size() && s_[p_] != '"') {
            char c = s_[p_++];
            if (c == '\\') {
                if (p_ >= s_.size()) fail("bad escape");
                c = s_[p_++];
                switch (c) {
                    case '"': case '\\': case '/': break;
                    case 'n': c = '\n'; break;
                    case 't': c = '\t'; break;
                    default: fail("unsupported escape");
                }
            }
            out += c;
        }
        if (p_ >= s_.size()) fail("unterminated string");
        ++p_;
        return out;
    }

    std::string s_;
    size_t p_ = 0;
};

const std::string& get_string(const JsonObject& o, const std::string& key) {
    const auto it = o.find(key);
    if (it == o.end() || !std::holds_alternative<std::string>(it->second.v))
        throw UpdateError("edition file: missing string \"" + key + "\"");
    return std::get<std::string>(it->second.v);
}

bool is_digit(char c) { return c >= '0' && c <= '9'; }

bool is_app_ver(const std::string& s) {
    return s.size() == 5 && is_digit(s[0]) && is_digit(s[1]) && s[2] == '.' && is_digit(s[3]) && is_digit(s[4]);
}

bool is_sha1_hex(const std::string& s) {
    return s.size() == 40 &&
           std::all_of(s.begin(), s.end(), [](char c) { return is_digit(c) || (c >= 'a' && c <= 'f'); });
}

std::string sfo_string(const Sfo& sfo, const std::string& key, const fs::path& pkg) {
    const auto it = sfo.find(key);
    if (it == sfo.end() || !std::holds_alternative<std::string>(it->second))
        throw UpdateError(pkg.filename().string() + ": PARAM.SFO has no " + key);
    return std::get<std::string>(it->second);
}

}  // namespace

Edition load_edition(const fs::path& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) throw UpdateError("cannot open edition file " + path.string());
    const Json root = JsonParser({std::istreambuf_iterator<char>(f), {}}).parse();
    if (!std::holds_alternative<JsonObject>(root.v)) throw UpdateError("edition file: top level is not an object");
    const auto& o = std::get<JsonObject>(root.v);

    Edition ed;
    ed.title_id = get_string(o, "title_id");
    ed.target_app_ver = get_string(o, "target_app_ver");
    if (ed.title_id.size() != 9) throw UpdateError("edition file: bad title_id \"" + ed.title_id + "\"");
    if (!is_app_ver(ed.target_app_ver)) throw UpdateError("edition file: bad target_app_ver");

    const auto it = o.find("updates");
    if (it == o.end() || !std::holds_alternative<JsonArray>(it->second.v))
        throw UpdateError("edition file: missing \"updates\" array");
    for (const Json& u : std::get<JsonArray>(it->second.v)) {
        if (!std::holds_alternative<JsonObject>(u.v)) throw UpdateError("edition file: update is not an object");
        const auto& uo = std::get<JsonObject>(u.v);
        const std::string& ver = get_string(uo, "app_ver");
        const std::string& sha = get_string(uo, "sha1");
        if (!is_app_ver(ver)) throw UpdateError("edition file: bad app_ver \"" + ver + "\"");
        if (!is_sha1_hex(sha)) throw UpdateError("edition file: bad sha1 for " + ver);
        for (const auto& prev : ed.updates)
            if (prev.first == ver) throw UpdateError("edition file: duplicate app_ver " + ver);
        ed.updates.push_back({ver, sha});
    }
    // APP_VER is fixed-width "NN.NN", so string order is version order.
    std::sort(ed.updates.begin(), ed.updates.end());
    return ed;
}

std::string sony_pkg_sha1(const fs::path& pkg) {
    std::ifstream f(pkg, std::ios::binary);
    if (!f) throw UpdateError("cannot open " + pkg.string());
    const uint64_t size = fs::file_size(pkg);
    if (size < 32) throw UpdateError(pkg.filename().string() + ": too short for a package");
    crypto::Sha1Stream h;
    std::vector<uint8_t> buf(8u << 20);
    for (uint64_t left = size - 32; left > 0;) {
        const size_t n = size_t(std::min<uint64_t>(buf.size(), left));
        f.read(reinterpret_cast<char*>(buf.data()), std::streamsize(n));
        if (size_t(f.gcount()) != n) throw UpdateError("read failed for " + pkg.string());
        h.update(std::span<const uint8_t>(buf.data(), n));
        left -= n;
    }
    return crypto::to_hex(h.final());
}

std::vector<fs::path> order_updates(const Edition& edition, const std::vector<fs::path>& pkgs) {
    // Identify every package by its own PARAM.SFO first (cheap), then hash.
    std::map<std::string, fs::path> by_ver;
    for (const fs::path& p : pkgs) {
        Sfo sfo;
        try {
            sfo = pkg_param_sfo(p);
        } catch (const PkgError& e) {
            throw UpdateError(p.filename().string() + ": " + e.what());
        }
        const std::string title = sfo_string(sfo, "TITLE_ID", p);
        const std::string ver = sfo_string(sfo, "APP_VER", p);
        if (title != edition.title_id)
            throw UpdateError(p.filename().string() + ": update for " + title + ", not " + edition.title_id);
        const bool known = std::any_of(edition.updates.begin(), edition.updates.end(),
                                       [&](const auto& u) { return u.first == ver; });
        if (!known)
            throw UpdateError("unexpected update " + ver + " (" + p.filename().string() +
                              ") is not in the edition file");
        const auto [it, inserted] = by_ver.emplace(ver, p);
        if (!inserted)
            throw UpdateError("duplicate update " + ver + ": " + it->second.filename().string() + " and " +
                              p.filename().string());
    }
    for (const auto& u : edition.updates)
        if (!by_ver.count(u.first)) throw UpdateError("missing update " + u.first);

    std::vector<fs::path> ordered;
    for (const auto& [ver, sha] : edition.updates) {
        const fs::path& p = by_ver.at(ver);
        const std::string got = sony_pkg_sha1(p);
        if (got != sha)
            throw UpdateError("update " + ver + " (" + p.filename().string() + ") sha1 mismatch: expected " + sha +
                              ", got " + got);
        ordered.push_back(p);
    }
    return ordered;
}

}  // namespace gt6

// Assembles a game tree (design D14). No third-party code.
#include "build_tree.hpp"

#include "crypto.hpp"
#include "klic.hpp"
#include "pkg.hpp"
#include "self.hpp"
#include "sfo.hpp"
#include "updates.hpp"

#include <sys/clonefile.h>

#include <algorithm>
#include <cctype>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <fstream>
#include <iterator>
#include <sstream>

namespace gt6 {
namespace {

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;

// Disc entries that make up dev_bdvd. PS3_UPDATE (system firmware) is left out on purpose.
const char* const kDiscEntries[] = {"PS3_DISC.SFB", "PS3_GAME"};
constexpr uint64_t kSpaceMargin = 1ull << 30;  // keep 1 GiB spare beyond the estimate

double seconds_since(Clock::time_point t) {
    return std::chrono::duration<double>(Clock::now() - t).count();
}

std::string json_str(const std::string& s) {
    std::string o = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') {
            o += '\\';
            o += char(c);
        } else if (c < 0x20) {
            char b[8];
            std::snprintf(b, sizeof b, "\\u%04x", c);
            o += b;
        } else {
            o += char(c);
        }
    }
    return o + "\"";
}

std::vector<uint8_t> slurp(const fs::path& p) {
    std::ifstream f(p, std::ios::binary);
    if (!f) throw BuildError("cannot read " + p.string());
    return {std::istreambuf_iterator<char>(f), {}};
}

std::string sha1_file(const fs::path& p) {
    std::ifstream f(p, std::ios::binary);
    if (!f) throw BuildError("cannot read " + p.string());
    crypto::Sha1Stream h;
    std::vector<uint8_t> buf(8u << 20);
    while (f) {
        f.read(reinterpret_cast<char*>(buf.data()), std::streamsize(buf.size()));
        h.update(std::span<const uint8_t>(buf.data(), size_t(f.gcount())));
    }
    return crypto::to_hex(h.final());
}

std::string sfo_app_ver(const fs::path& sfo_path, std::string* title_id = nullptr) {
    Sfo sfo;
    try {
        sfo = parse_sfo(slurp(sfo_path));
    } catch (const SfoError& e) {
        throw BuildError(sfo_path.string() + ": " + e.what());
    }
    auto str = [&](const char* k) -> std::string {
        const auto it = sfo.find(k);
        if (it == sfo.end() || !std::holds_alternative<std::string>(it->second))
            throw BuildError(sfo_path.string() + " has no " + k);
        return std::get<std::string>(it->second);
    };
    if (title_id) *title_id = str("TITLE_ID");
    return str("APP_VER");
}

// Regular files under root, sorted, symlinks not followed.
std::vector<fs::path> files_under(const fs::path& root) {
    std::vector<fs::path> out;
    if (!fs::exists(root)) return out;
    if (fs::is_regular_file(fs::symlink_status(root))) return {root};
    for (const auto& e : fs::recursive_directory_iterator(root))
        if (e.is_regular_file() && !e.is_symlink()) out.push_back(e.path());
    std::sort(out.begin(), out.end());
    return out;
}

// Discs mount read-only (r-xr-xr-x everywhere). Built trees are normalised to 0755 folders and
// 0644 files so they can be rebuilt or removed later.
void normalise_perms(const fs::path& root) {
    constexpr auto dir_perms = fs::perms(0755), file_perms = fs::perms(0644);
    fs::permissions(root, fs::is_directory(fs::symlink_status(root)) ? dir_perms : file_perms);
    if (!fs::is_directory(fs::symlink_status(root))) return;
    for (const auto& e : fs::recursive_directory_iterator(root))
        if (!e.is_symlink()) fs::permissions(e.path(), e.is_directory() ? dir_perms : file_perms);
}

// Recursive copy that creates its own writable folders instead of copying read-only modes.
void copy_tree(const fs::path& src, const fs::path& dst) {
    if (!fs::is_directory(src)) {
        fs::copy_file(src, dst);
        return;
    }
    fs::create_directory(dst);
    fs::permissions(dst, fs::perms(0755));
    for (const auto& e : fs::recursive_directory_iterator(src)) {
        const fs::path target = dst / fs::relative(e.path(), src);
        if (e.is_symlink()) throw BuildError("unexpected symlink on disc: " + e.path().string());
        if (e.is_directory()) {
            fs::create_directory(target);
            fs::permissions(target, fs::perms(0755));
        } else {
            fs::copy_file(e.path(), target);
        }
    }
}

// remove_all that first restores owner access, so read-only leftovers go too.
void remove_tree(const fs::path& p, std::error_code& ec) {
    for (auto it = fs::recursive_directory_iterator(p, ec); !ec && it != fs::recursive_directory_iterator();
         it.increment(ec))
        if (it->is_directory()) fs::permissions(it->path(), fs::perms::owner_all, fs::perm_options::add, ec);
    ec.clear();
    fs::remove_all(p, ec);
}

void remove_tree(const fs::path& p) {
    std::error_code ec;
    remove_tree(p, ec);
    if (ec) throw BuildError("cannot remove " + p.string() + ": " + ec.message());
}

uint64_t bytes_under(const fs::path& root) {
    uint64_t n = 0;
    for (const auto& p : files_under(root)) n += fs::file_size(p);
    return n;
}

void ensure_space(const fs::path& dir, uint64_t need, const std::string& what) {
    const uint64_t avail = fs::space(dir).available;
    if (avail < need + kSpaceMargin)
        throw BuildError("not enough free space for " + what + ": need " + std::to_string((need + kSpaceMargin) >> 20) +
                         " MiB (including 1 GiB margin), " + std::to_string(avail >> 20) + " MiB available at " +
                         dir.string());
}

std::string lower(std::string s) {
    for (char& c : s) c = char(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

// Names that the PS3 loads as executables; these must decrypt.
bool executable_name(const fs::path& p) {
    const std::string n = p.filename().string();
    const std::string ext = lower(p.extension().string());
    return n == "EBOOT.BIN" || n == "EMAIN.SELF" || ext == ".sprx" || ext == ".self";
}

struct Decrypted {
    std::string source, output, sha256;
    uint64_t size;
    SelfInfo info;
    std::string klicensee_from;  // decrypted file the klicensee was found in; empty if none needed
};
struct Skipped {
    std::string path, reason;
};
struct Failed {
    std::string path, reason;
    bool npdrm_free = false;  // may open with the game's own klicensee
};

void write_file(const fs::path& out, std::span<const uint8_t> data) {
    fs::create_directories(out.parent_path());
    std::ofstream o(out, std::ios::binary | std::ios::trunc);
    o.write(reinterpret_cast<const char*>(data.data()), std::streamsize(data.size()));
    o.close();
    if (!o) throw BuildError("write failed for " + out.string());
}

// Decrypts every SELF in staging/dev_bdvd and staging/dev_hdd0 into staging/decrypted.
// Free-licence NPDRM SELFs that do not open with the public klicensee are retried with each
// klicensee string found in the decrypted update EBOOT.BIN files (see klic.hpp).
void decrypt_all(const fs::path& staging, std::vector<Decrypted>& done, std::vector<Skipped>& skipped,
                 const std::function<void(const std::string&)>& log) {
    std::vector<Failed> failed;
    auto store = [&](const std::string& rel, std::span<const uint8_t> elf, const SelfInfo& info,
                     const std::string& klic_from) {
        const fs::path out = staging / "decrypted" / (rel + ".elf");
        write_file(out, elf);
        done.push_back({rel, fs::relative(out, staging).generic_string(), crypto::to_hex(crypto::sha256(elf)), elf.size(), info,
                        klic_from});
        log("decrypted " + rel);
    };

    for (const char* tree : {"dev_bdvd", "dev_hdd0"}) {
        for (const fs::path& file : files_under(staging / tree)) {
            const std::string rel = fs::relative(file, staging).generic_string();
            uint8_t head[12] = {};
            {
                std::ifstream f(file, std::ios::binary);
                f.read(reinterpret_cast<char*>(head), sizeof head);
                const size_t got = size_t(f.gcount());
                const bool sce = got >= 4 && std::memcmp(head, "SCE\0", 4) == 0;
                if (!sce) {
                    if (executable_name(file)) skipped.push_back({rel, "executable name but no SCE magic"});
                    continue;
                }
                if (got < sizeof head) {
                    skipped.push_back({rel, "SCE magic but too short for an SCE header"});
                    continue;
                }
            }
            const unsigned header_type = unsigned(head[10]) << 8 | head[11];
            if (header_type != 1) {
                skipped.push_back({rel, "not a SELF (SCE header type " + std::to_string(header_type) + ")"});
                continue;
            }
            const std::vector<uint8_t> data = slurp(file);
            SelfInfo info;
            try {
                info = inspect_self(data);
            } catch (const SelfError& e) {
                if (executable_name(file)) {
                    failed.push_back({rel, e.what()});
                } else {
                    skipped.push_back({rel, std::string("SCE header type 1 but not accepted as a SELF: ") + e.what()});
                }
                continue;
            }
            try {
                store(rel, decrypt_self(data), info, "");
            } catch (const SelfError& e) {
                failed.push_back({rel, e.what(), info.npdrm && info.npdrm_license == 3});
            }
        }
    }

    if (std::any_of(failed.begin(), failed.end(), [](const Failed& f) { return f.npdrm_free; })) {
        // Klicensee candidates from the decrypted update EBOOT.BIN files, in tree order.
        std::vector<std::pair<KlicCandidate, std::string>> cands;
        for (const Decrypted& d : done)
            if (d.source.starts_with("dev_hdd0/") && fs::path(d.source).filename() == "EBOOT.BIN")
                for (const KlicCandidate& c : klicensee_strings(slurp(staging / d.output))) cands.push_back({c, d.output});
        std::vector<Failed> still;
        for (const Failed& f : failed) {
            bool opened = false;
            if (f.npdrm_free) {
                const std::vector<uint8_t> data = slurp(staging / f.path);
                for (const auto& [c, from] : cands) {
                    try {
                        // decrypt_self accepts the key only if the metadata opens and every
                        // program segment HMAC matches.
                        store(f.path, decrypt_self(data, &c.key), inspect_self(data), from);
                        opened = true;
                        break;
                    } catch (const SelfError&) {
                    }
                }
            }
            if (!opened)
                still.push_back({f.path, f.reason + (f.npdrm_free ? "; no klicensee in the decrypted update "
                                                                    "EBOOT.BIN opens it"
                                                                  : "")});
        }
        failed = std::move(still);
    }

    if (!failed.empty()) {
        std::string msg = std::to_string(failed.size()) + " SELF file(s) failed to decrypt:";
        for (const auto& f : failed) msg += "\n  " + f.path + ": " + f.reason;
        throw SelfError(msg);
    }
}

struct Report {
    std::string disc_copy;
    std::vector<std::pair<std::string, std::string>> disc_files;  // rel path, sha1
    struct Update {
        std::string app_ver, file, sha1;
        uint64_t size;
    };
    std::vector<Update> updates;
    std::vector<Decrypted> decrypted;
    std::vector<Skipped> skipped;
    std::vector<std::pair<std::string, double>> timings;
};

void write_build_json(const fs::path& path, const BuildOptions& o, const Edition& ed, const std::string& final_ver,
                      const Report& r) {
    std::ostringstream j;
    j << "{\n";
    j << "  \"tool\": \"gt6unpack\",\n";
    j << "  \"tool_version\": " << json_str(kToolVersion) << ",\n";
    j << "  \"title_id\": " << json_str(ed.title_id) << ",\n";
    j << "  \"target_app_ver\": " << json_str(ed.target_app_ver) << ",\n";
    j << "  \"final_app_ver\": " << json_str(final_ver) << ",\n";
    j << "  \"edition_file\": " << json_str(o.edition_file.string()) << ",\n";
    j << "  \"disc_dir\": " << json_str(o.disc_dir.string()) << ",\n";
    j << "  \"disc_copy\": " << json_str(r.disc_copy) << ",\n";
    j << "  \"disc_files\": [";
    for (size_t i = 0; i < r.disc_files.size(); ++i)
        j << (i ? "," : "") << "\n    {\"path\": " << json_str(r.disc_files[i].first)
          << ", \"sha1\": " << json_str(r.disc_files[i].second) << "}";
    j << "\n  ],\n";
    j << "  \"updates_dir\": " << json_str(o.updates_dir.string()) << ",\n";
    j << "  \"updates\": [";
    for (size_t i = 0; i < r.updates.size(); ++i) {
        const auto& u = r.updates[i];
        j << (i ? "," : "") << "\n    {\"app_ver\": " << json_str(u.app_ver) << ", \"file\": " << json_str(u.file)
          << ", \"size\": " << u.size << ", \"sha1\": " << json_str(u.sha1) << "}";
    }
    j << "\n  ],\n";
    j << "  \"decrypted\": [";
    for (size_t i = 0; i < r.decrypted.size(); ++i) {
        const auto& d = r.decrypted[i];
        j << (i ? "," : "") << "\n    {\"source\": " << json_str(d.source) << ", \"output\": " << json_str(d.output)
          << ", \"size\": " << d.size << ", \"sha256\": " << json_str(d.sha256)
          << ", \"program_type\": " << d.info.program_type << ", \"npdrm\": " << (d.info.npdrm ? "true" : "false")
          << ", \"key_revision\": " << d.info.key_revision;
        if (!d.klicensee_from.empty()) j << ", \"klicensee_from\": " << json_str(d.klicensee_from);
        j << "}";
    }
    j << "\n  ],\n";
    j << "  \"sce_skipped\": [";
    for (size_t i = 0; i < r.skipped.size(); ++i)
        j << (i ? "," : "") << "\n    {\"path\": " << json_str(r.skipped[i].path)
          << ", \"reason\": " << json_str(r.skipped[i].reason) << "}";
    j << "\n  ],\n";
    j << "  \"timings_s\": {";
    for (size_t i = 0; i < r.timings.size(); ++i) {
        char b[32];
        std::snprintf(b, sizeof b, "%.1f", r.timings[i].second);
        j << (i ? "," : "") << "\n    " << json_str(r.timings[i].first) << ": " << b;
    }
    j << "\n  }\n}\n";
    std::ofstream f(path, std::ios::binary | std::ios::trunc);
    f << j.str();
    f.close();
    if (!f) throw BuildError("write failed for " + path.string());
}

void build_into(const BuildOptions& o, const Edition& ed, const std::vector<fs::path>& ordered,
                const fs::path& staging, Report& r, std::string& final_ver) {
    const auto& log = o.log;
    uint64_t update_bytes = 0;
    for (const auto& p : ordered) update_bytes += fs::file_size(p);

    // dev_bdvd: clone the disc tree; copy (after a space check) when cloning is impossible.
    auto t = Clock::now();
    const fs::path bdvd = staging / "dev_bdvd";
    fs::create_directories(bdvd);
    bool copying = false;
    for (const char* name : kDiscEntries) {
        const fs::path src = o.disc_dir / name, dst = bdvd / name;
        if (!copying) {
            const int rc = o.clone(src, dst);
            if (rc == 0) continue;
            if (rc != EXDEV && rc != ENOTSUP && rc != EOPNOTSUPP)
                throw BuildError("clonefile " + src.string() + ": " + std::strerror(rc));
            uint64_t disc_bytes = 0;
            for (const char* n : kDiscEntries) disc_bytes += bytes_under(o.disc_dir / n);
            ensure_space(staging.parent_path(), disc_bytes + update_bytes, "the disc copy and updates");
            log(std::string("clonefile not possible (") + std::strerror(rc) + "); copying the disc tree");
            copying = true;
        }
        if (fs::exists(fs::symlink_status(dst))) remove_tree(dst);
        copy_tree(src, dst);
    }
    normalise_perms(bdvd);
    r.disc_copy = copying ? "copy" : "clonefile";
    r.timings.push_back({"disc_copy", seconds_since(t)});
    if (!copying) ensure_space(staging.parent_path(), update_bytes, "the updates");

    t = Clock::now();
    for (const fs::path& f : files_under(bdvd))
        r.disc_files.push_back({fs::relative(f, staging).generic_string(), sha1_file(f)});
    r.timings.push_back({"disc_hash", seconds_since(t)});

    // dev_hdd0: install in APP_VER order; a later package overwrites only the files it carries.
    t = Clock::now();
    const fs::path game = staging / "dev_hdd0" / "game" / ed.title_id;
    for (size_t i = 0; i < ordered.size(); ++i) {
        const auto u = Clock::now();
        extract_pkg(ordered[i], game);
        log("installed " + ed.updates[i].first + " (" + ordered[i].filename().string() + ") in " +
            std::to_string(int(seconds_since(u))) + " s");
    }
    r.timings.push_back({"install_updates", seconds_since(t)});

    t = Clock::now();
    decrypt_all(staging, r.decrypted, r.skipped, log);
    r.timings.push_back({"decrypt", seconds_since(t)});

    const fs::path sfo = game / "PARAM.SFO";
    if (!fs::exists(sfo)) throw BuildError("no PARAM.SFO in " + game.string());
    std::string title;
    final_ver = sfo_app_ver(sfo, &title);
    if (title != ed.title_id) throw BuildError("installed PARAM.SFO is for " + title + ", not " + ed.title_id);
    if (final_ver != ed.target_app_ver)
        throw BuildError("final APP_VER " + final_ver + " does not match the target " + ed.target_app_ver);
}

}  // namespace

int clone_with_clonefile(const fs::path& src, const fs::path& dst) {
    return ::clonefile(src.c_str(), dst.c_str(), CLONE_NOFOLLOW) == 0 ? 0 : errno;
}

void build_tree(const BuildOptions& o) {
    const auto t0 = Clock::now();
    const Edition ed = load_edition(o.edition_file);
    if (o.out_dir.empty()) throw BuildError("no output directory given");
    fs::path out = fs::absolute(o.out_dir).lexically_normal();
    if (!out.has_filename()) out = out.parent_path();  // trailing separator
    if (!out.has_filename() || out == out.root_path())
        throw BuildError("bad output directory \"" + o.out_dir.string() + "\"");
    const fs::path staging = out.string() + ".staging";
    const fs::path old = out.string() + ".old";

    // A run killed between moving <out> aside and moving the new tree in leaves <out>.old and no
    // <out>: put the old tree back before anything else.
    if (!fs::exists(fs::symlink_status(out)) && fs::exists(fs::symlink_status(old))) {
        fs::rename(old, out);
        o.log("restored " + out.string() + " from an interrupted earlier run");
    }
    if (fs::exists(out) && !o.force) throw BuildError(out.string() + " already exists (use --force to rebuild)");

    // Inputs: the disc must be this title; every update present and verified before writing.
    for (const char* name : kDiscEntries)
        if (!fs::exists(o.disc_dir / name)) throw BuildError(std::string("disc has no ") + name + ": " + o.disc_dir.string());
    std::string disc_title;
    const std::string disc_ver = sfo_app_ver(o.disc_dir / "PS3_GAME" / "PARAM.SFO", &disc_title);
    if (disc_title != ed.title_id) throw BuildError("disc is " + disc_title + ", edition is " + ed.title_id);
    o.log("disc " + disc_title + " APP_VER " + disc_ver);

    std::vector<fs::path> pkgs;
    if (!fs::is_directory(o.updates_dir)) throw BuildError("no updates directory " + o.updates_dir.string());
    for (const auto& e : fs::directory_iterator(o.updates_dir))
        if (e.is_regular_file() && lower(e.path().extension().string()) == ".pkg") pkgs.push_back(e.path());
    std::sort(pkgs.begin(), pkgs.end());

    Report r;
    auto t = Clock::now();
    const std::vector<fs::path> ordered = order_updates(ed, pkgs);
    r.timings.push_back({"verify_updates", seconds_since(t)});
    o.log("verified " + std::to_string(ordered.size()) + " updates");
    for (size_t i = 0; i < ordered.size(); ++i)
        r.updates.push_back({ed.updates[i].first, ordered[i].filename().string(), ed.updates[i].second,
                             uint64_t(fs::file_size(ordered[i]))});

    fs::create_directories(out.parent_path());
    // Leftovers of an interrupted earlier run. <out> (if any) is the good tree at this point:
    // a staging tree is never the only copy, and an .old tree beside <out> is superseded.
    if (fs::exists(fs::symlink_status(staging))) remove_tree(staging);
    if (fs::exists(fs::symlink_status(old))) remove_tree(old);
    fs::create_directories(staging);
    try {
        std::string final_ver;
        build_into(o, ed, ordered, staging, r, final_ver);
        r.timings.push_back({"total", seconds_since(t0)});
        write_build_json(staging / "build.json", o, ed, final_ver, r);
        // Swap by renames only, so <out> is always either the old or the new complete tree.
        const bool replacing = fs::exists(fs::symlink_status(out));
        if (replacing) fs::rename(out, old);
        try {
            fs::rename(staging, out);
        } catch (...) {
            if (replacing) fs::rename(old, out);
            throw;
        }
        if (replacing) {
            std::error_code ec;
            remove_tree(old, ec);  // best effort; the next run removes what is left
            if (ec) o.log("could not remove the previous build at " + old.string() + ": " + ec.message());
        }
    } catch (...) {
        std::error_code ec;
        remove_tree(staging, ec);
        throw;
    }
    o.log("done: " + out.string());
}

}  // namespace gt6

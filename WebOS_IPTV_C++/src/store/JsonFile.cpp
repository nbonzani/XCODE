#include "store/JsonFile.h"

#include <cstdio>
#include <fstream>
#include <system_error>

namespace iptv::store {

namespace fs = std::filesystem;

json readJson(const fs::path& path, json fallback) {
    std::ifstream in(path);
    if (!in) return fallback;
    try {
        json out;
        in >> out;
        return out;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "[store] failed to parse %s: %s\n",
                     path.string().c_str(), e.what());
        return fallback;
    }
}

bool writeJson(const fs::path& path, const json& value) {
    fs::path tmp = path;
    tmp += ".tmp";
    {
        std::ofstream out(tmp, std::ios::trunc);
        if (!out) {
            std::fprintf(stderr, "[store] cannot open %s for write\n", tmp.string().c_str());
            return false;
        }
        out << value.dump(2);
        out.flush();
        if (!out) {
            std::fprintf(stderr, "[store] write failed to %s\n", tmp.string().c_str());
            return false;
        }
    }
    std::error_code ec;
    fs::rename(tmp, path, ec);
    if (ec) {
        std::fprintf(stderr, "[store] rename %s -> %s failed: %s\n",
                     tmp.string().c_str(), path.string().c_str(), ec.message().c_str());
        fs::remove(tmp, ec);
        return false;
    }
    return true;
}

}  // namespace iptv::store

#include "store/Config.h"

#include "store/JsonFile.h"
#include "store/Paths.h"

namespace iptv::store {

namespace {
template <typename T>
T value_or(const json& j, const char* key, const T& fallback) {
    if (!j.contains(key)) return fallback;
    try { return j.at(key).get<T>(); } catch (...) { return fallback; }
}
std::vector<std::string> stringArray(const json& j, const char* key) {
    std::vector<std::string> out;
    if (!j.contains(key) || !j.at(key).is_array()) return out;
    for (const auto& v : j.at(key)) {
        if (v.is_string()) out.push_back(v.get<std::string>());
        else               out.push_back(v.dump());
    }
    return out;
}
}  // namespace

Config Config::load() {
    json j = readJson(Paths::configFile());
    Config c;
    c.serverUrl  = value_or<std::string>(j, "serverUrl", "");
    c.port       = value_or<std::string>(j, "port",      "");
    c.username   = value_or<std::string>(j, "username",  "");
    c.password   = value_or<std::string>(j, "password",  "");
    c.frenchOnly = value_or<bool>(j, "frenchOnly", true);
    c.selectedMovieCategories  = stringArray(j, "selectedMovieCategories");
    c.selectedSeriesCategories = stringArray(j, "selectedSeriesCategories");
    c.catalogSetupDone = value_or<bool>(j, "catalogSetupDone", false);
    return c;
}

bool Config::save() const {
    json j;
    j["serverUrl"]  = serverUrl;
    j["port"]       = port;
    j["username"]   = username;
    j["password"]   = password;
    j["frenchOnly"] = frenchOnly;
    j["selectedMovieCategories"]  = selectedMovieCategories;
    j["selectedSeriesCategories"] = selectedSeriesCategories;
    j["catalogSetupDone"] = catalogSetupDone;
    return writeJson(Paths::configFile(), j);
}

}  // namespace iptv::store

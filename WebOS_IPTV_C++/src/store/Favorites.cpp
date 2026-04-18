#include "store/Favorites.h"

#include "store/JsonFile.h"
#include "store/Paths.h"

namespace iptv::store {

namespace {

const char* keyForKind(FavoriteKind k) {
    return k == FavoriteKind::Movie ? "movies" : "series";
}
const char* idFieldForKind(FavoriteKind k) {
    return k == FavoriteKind::Movie ? "stream_id" : "series_id";
}
std::string idAsString(const json& v) {
    if (v.is_null()) return "";
    if (v.is_string()) return v.get<std::string>();
    if (v.is_number_integer()) return std::to_string(v.get<long long>());
    if (v.is_number_unsigned()) return std::to_string(v.get<unsigned long long>());
    return v.dump();
}
json readAll() {
    json j = readJson(Paths::favoritesFile());
    if (!j.is_object()) j = json::object();
    if (!j.contains("movies") || !j["movies"].is_array()) j["movies"] = json::array();
    if (!j.contains("series") || !j["series"].is_array()) j["series"] = json::array();
    return j;
}
}  // namespace

void Favorites::add(const json& item, FavoriteKind kind) {
    const char* key = keyForKind(kind);
    const char* idf = idFieldForKind(kind);
    std::string itemId = item.contains(idf) ? idAsString(item.at(idf)) : "";
    if (itemId.empty()) return;

    json j = readAll();
    auto& arr = j[key];
    for (const auto& it : arr) {
        if (it.contains(idf) && idAsString(it.at(idf)) == itemId) return;  // already in
    }
    arr.insert(arr.begin(), item);  // unshift
    writeJson(Paths::favoritesFile(), j);
}

void Favorites::remove(const std::string& itemId, FavoriteKind kind) {
    if (itemId.empty()) return;
    const char* key = keyForKind(kind);
    const char* idf = idFieldForKind(kind);

    json j = readAll();
    auto& arr = j[key];
    json kept = json::array();
    for (const auto& it : arr) {
        std::string id = it.contains(idf) ? idAsString(it.at(idf)) : "";
        if (id != itemId) kept.push_back(it);
    }
    arr = std::move(kept);
    writeJson(Paths::favoritesFile(), j);
}

bool Favorites::toggle(const json& item, FavoriteKind kind) {
    const char* idf = idFieldForKind(kind);
    std::string id = item.contains(idf) ? idAsString(item.at(idf)) : "";
    if (contains(id, kind)) {
        remove(id, kind);
        return false;
    }
    add(item, kind);
    return true;
}

bool Favorites::contains(const std::string& itemId, FavoriteKind kind) {
    if (itemId.empty()) return false;
    const char* key = keyForKind(kind);
    const char* idf = idFieldForKind(kind);
    json j = readAll();
    for (const auto& it : j[key]) {
        if (it.contains(idf) && idAsString(it.at(idf)) == itemId) return true;
    }
    return false;
}

json Favorites::all() {
    return readAll();
}

int Favorites::count() {
    json j = readAll();
    return static_cast<int>(j["movies"].size() + j["series"].size());
}

}  // namespace iptv::store

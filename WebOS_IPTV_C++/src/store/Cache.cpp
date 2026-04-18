#include "store/Cache.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <ctime>
#include <iomanip>
#include <regex>
#include <set>
#include <sstream>

#include <sqlite3.h>

#include "store/Paths.h"

namespace iptv::store {

namespace {

std::string isoNow() {
    using namespace std::chrono;
    auto now = system_clock::now();
    std::time_t t = system_clock::to_time_t(now);
    std::tm tm{};
    gmtime_r(&t, &tm);
    std::ostringstream oss;
    oss << std::put_time(&tm, "%Y-%m-%dT%H:%M:%SZ");
    return oss.str();
}

std::string asString(const json& v) {
    if (v.is_null()) return "";
    if (v.is_string()) return v.get<std::string>();
    if (v.is_number_integer()) return std::to_string(v.get<long long>());
    if (v.is_number_unsigned()) return std::to_string(v.get<unsigned long long>());
    if (v.is_number_float()) {
        std::ostringstream oss;
        oss << v.get<double>();
        return oss.str();
    }
    if (v.is_boolean()) return v.get<bool>() ? "1" : "0";
    return v.dump();
}

std::string getString(const json& obj, const char* key) {
    if (!obj.contains(key)) return "";
    return asString(obj.at(key));
}

double safeFloat(const json& obj, const char* key) {
    if (!obj.contains(key)) return 0.0;
    const auto& v = obj.at(key);
    if (v.is_number()) return v.get<double>();
    if (v.is_string()) {
        try { return std::stod(v.get<std::string>()); } catch (...) { return 0.0; }
    }
    return 0.0;
}

void bindString(sqlite3_stmt* st, int idx, const std::string& s) {
    sqlite3_bind_text(st, idx, s.c_str(), static_cast<int>(s.size()), SQLITE_TRANSIENT);
}

}  // namespace

Cache::Cache()  = default;
Cache::~Cache() { close(); }

bool Cache::open() {
    if (db_) return true;
    std::string path = Paths::cacheDb().string();
    sqlite3* raw = nullptr;
    int rc = sqlite3_open(path.c_str(), &raw);
    if (rc != SQLITE_OK) {
        std::fprintf(stderr, "[cache] sqlite3_open(%s) failed: %s\n",
                     path.c_str(), sqlite3_errmsg(raw));
        if (raw) sqlite3_close(raw);
        return false;
    }
    db_ = raw;
    exec("PRAGMA journal_mode = WAL;");
    exec("PRAGMA synchronous = NORMAL;");
    return createSchema();
}

void Cache::close() {
    if (db_) {
        sqlite3_close(static_cast<sqlite3*>(db_));
        db_ = nullptr;
    }
}

bool Cache::exec(const char* sql) {
    char* err = nullptr;
    int rc = sqlite3_exec(static_cast<sqlite3*>(db_), sql, nullptr, nullptr, &err);
    if (rc != SQLITE_OK) {
        std::fprintf(stderr, "[cache] sqlite exec failed: %s\nSQL: %s\n",
                     err ? err : "?", sql);
        if (err) sqlite3_free(err);
        return false;
    }
    return true;
}

bool Cache::createSchema() {
    return exec(
        "CREATE TABLE IF NOT EXISTS movies ("
            "stream_id TEXT PRIMARY KEY,"
            "name TEXT, category_id TEXT, category_name TEXT,"
            "stream_icon TEXT, container_extension TEXT,"
            "rating REAL, added TEXT, cached_at TEXT, is_french INTEGER"
        ");"
        "CREATE INDEX IF NOT EXISTS idx_movies_category ON movies(category_id);"
        "CREATE INDEX IF NOT EXISTS idx_movies_name ON movies(name);"
        "CREATE INDEX IF NOT EXISTS idx_movies_french ON movies(is_french);"

        "CREATE TABLE IF NOT EXISTS series ("
            "series_id TEXT PRIMARY KEY,"
            "name TEXT, category_id TEXT, category_name TEXT, cover TEXT,"
            "rating REAL, genre TEXT, release_date TEXT, plot TEXT,"
            "cached_at TEXT, is_french INTEGER"
        ");"
        "CREATE INDEX IF NOT EXISTS idx_series_category ON series(category_id);"
        "CREATE INDEX IF NOT EXISTS idx_series_name ON series(name);"
        "CREATE INDEX IF NOT EXISTS idx_series_french ON series(is_french);"

        "CREATE TABLE IF NOT EXISTS vod_categories ("
            "category_id TEXT PRIMARY KEY,"
            "category_name TEXT, parent_id TEXT, is_french INTEGER"
        ");"
        "CREATE INDEX IF NOT EXISTS idx_vodcat_french ON vod_categories(is_french);"

        "CREATE TABLE IF NOT EXISTS series_categories ("
            "category_id TEXT PRIMARY KEY,"
            "category_name TEXT, parent_id TEXT, is_french INTEGER"
        ");"
        "CREATE INDEX IF NOT EXISTS idx_seriescat_french ON series_categories(is_french);"

        "CREATE TABLE IF NOT EXISTS sync_meta ("
            "key TEXT PRIMARY KEY, value TEXT"
        ");"
    );
}

bool Cache::isFrench(const std::string& categoryName) {
    if (categoryName.empty()) return false;
    // Same rules as cacheService.js. Single regex per pattern, no lookbehind.
    static const std::regex re_short(R"((^|[^A-Za-z])FR([^A-Za-z]|$))");
    static const std::regex re_long(R"((^|[^A-Za-z])(?:FRENCH|FRANCE)([^A-Za-z]|$))",
                                    std::regex::icase);
    return std::regex_search(categoryName, re_short)
        || std::regex_search(categoryName, re_long);
}

bool Cache::saveVodCategories(const std::vector<json>& categories) {
    if (!db_) return false;
    auto* db = static_cast<sqlite3*>(db_);
    if (!exec("BEGIN;") || !exec("DELETE FROM vod_categories;")) return false;
    sqlite3_stmt* st = nullptr;
    sqlite3_prepare_v2(db,
        "INSERT INTO vod_categories(category_id, category_name, parent_id, is_french) "
        "VALUES(?, ?, ?, ?);", -1, &st, nullptr);
    for (const auto& c : categories) {
        std::string id = getString(c, "category_id");
        std::string nm = getString(c, "category_name");
        std::string p  = getString(c, "parent_id");
        bindString(st, 1, id);
        bindString(st, 2, nm);
        bindString(st, 3, p);
        sqlite3_bind_int(st, 4, isFrench(nm) ? 1 : 0);
        sqlite3_step(st);
        sqlite3_reset(st);
    }
    sqlite3_finalize(st);
    return exec("COMMIT;");
}

bool Cache::saveSeriesCategories(const std::vector<json>& categories) {
    if (!db_) return false;
    auto* db = static_cast<sqlite3*>(db_);
    if (!exec("BEGIN;") || !exec("DELETE FROM series_categories;")) return false;
    sqlite3_stmt* st = nullptr;
    sqlite3_prepare_v2(db,
        "INSERT INTO series_categories(category_id, category_name, parent_id, is_french) "
        "VALUES(?, ?, ?, ?);", -1, &st, nullptr);
    for (const auto& c : categories) {
        std::string id = getString(c, "category_id");
        std::string nm = getString(c, "category_name");
        std::string p  = getString(c, "parent_id");
        bindString(st, 1, id);
        bindString(st, 2, nm);
        bindString(st, 3, p);
        sqlite3_bind_int(st, 4, isFrench(nm) ? 1 : 0);
        sqlite3_step(st);
        sqlite3_reset(st);
    }
    sqlite3_finalize(st);
    return exec("COMMIT;");
}

bool Cache::saveMovies(const std::vector<json>& movies,
                       const std::map<std::string, std::string>& categoriesMap) {
    if (!db_) return false;
    auto* db = static_cast<sqlite3*>(db_);

    // French category IDs from already-saved vod_categories.
    std::set<std::string> frenchCatIds;
    sqlite3_stmt* qf = nullptr;
    sqlite3_prepare_v2(db,
        "SELECT category_id FROM vod_categories WHERE is_french = 1;", -1, &qf, nullptr);
    while (sqlite3_step(qf) == SQLITE_ROW) {
        frenchCatIds.insert(reinterpret_cast<const char*>(sqlite3_column_text(qf, 0)));
    }
    sqlite3_finalize(qf);

    if (!exec("BEGIN;") || !exec("DELETE FROM movies;")) return false;
    sqlite3_stmt* st = nullptr;
    sqlite3_prepare_v2(db,
        "INSERT INTO movies(stream_id, name, category_id, category_name, stream_icon, "
        "container_extension, rating, added, cached_at, is_french) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", -1, &st, nullptr);

    std::string cachedAt = isoNow();
    for (const auto& m : movies) {
        std::string id    = getString(m, "stream_id");
        std::string name  = getString(m, "name");
        std::string catId = getString(m, "category_id");
        std::string ext   = getString(m, "container_extension");
        if (ext.empty()) ext = "mkv";
        std::string catName;
        if (auto it = categoriesMap.find(catId); it != categoriesMap.end()) catName = it->second;

        bindString(st, 1, id);
        bindString(st, 2, name);
        bindString(st, 3, catId);
        bindString(st, 4, catName);
        bindString(st, 5, getString(m, "stream_icon"));
        bindString(st, 6, ext);
        sqlite3_bind_double(st, 7, safeFloat(m, "rating"));
        bindString(st, 8, getString(m, "added"));
        bindString(st, 9, cachedAt);
        sqlite3_bind_int(st, 10, frenchCatIds.count(catId) ? 1 : 0);
        sqlite3_step(st);
        sqlite3_reset(st);
    }
    sqlite3_finalize(st);
    return exec("COMMIT;");
}

bool Cache::saveSeriesList(const std::vector<json>& seriesList,
                           const std::map<std::string, std::string>& categoriesMap) {
    if (!db_) return false;
    auto* db = static_cast<sqlite3*>(db_);

    std::set<std::string> frenchCatIds;
    sqlite3_stmt* qf = nullptr;
    sqlite3_prepare_v2(db,
        "SELECT category_id FROM series_categories WHERE is_french = 1;", -1, &qf, nullptr);
    while (sqlite3_step(qf) == SQLITE_ROW) {
        frenchCatIds.insert(reinterpret_cast<const char*>(sqlite3_column_text(qf, 0)));
    }
    sqlite3_finalize(qf);

    if (!exec("BEGIN;") || !exec("DELETE FROM series;")) return false;
    sqlite3_stmt* st = nullptr;
    sqlite3_prepare_v2(db,
        "INSERT INTO series(series_id, name, category_id, category_name, cover, rating, "
        "genre, release_date, plot, cached_at, is_french) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", -1, &st, nullptr);

    std::string cachedAt = isoNow();
    for (const auto& s : seriesList) {
        std::string id    = getString(s, "series_id");
        std::string name  = getString(s, "name");
        std::string catId = getString(s, "category_id");
        std::string catName;
        if (auto it = categoriesMap.find(catId); it != categoriesMap.end()) catName = it->second;
        std::string release = getString(s, "releaseDate");
        if (release.empty()) release = getString(s, "release_date");

        bindString(st, 1, id);
        bindString(st, 2, name);
        bindString(st, 3, catId);
        bindString(st, 4, catName);
        bindString(st, 5, getString(s, "cover"));
        sqlite3_bind_double(st, 6, safeFloat(s, "rating"));
        bindString(st, 7, getString(s, "genre"));
        bindString(st, 8, release);
        bindString(st, 9, getString(s, "plot"));
        bindString(st, 10, cachedAt);
        sqlite3_bind_int(st, 11, frenchCatIds.count(catId) ? 1 : 0);
        sqlite3_step(st);
        sqlite3_reset(st);
    }
    sqlite3_finalize(st);
    return exec("COMMIT;");
}

namespace {
void readCatString(sqlite3_stmt* st, int col, std::string& out) {
    const unsigned char* v = sqlite3_column_text(st, col);
    if (v) out.assign(reinterpret_cast<const char*>(v));
}
}

CatalogSnapshot Cache::loadCatalog() {
    return loadCatalogFast(-1);
}

CatalogSnapshot Cache::loadCatalogFast(int limit) {
    CatalogSnapshot snap;
    if (!db_) return snap;
    auto* db = static_cast<sqlite3*>(db_);

    auto loadCats = [&](const char* table, std::vector<CachedCategory>& dst) {
        std::string sql = std::string("SELECT category_id, category_name, parent_id, is_french FROM ") + table;
        sqlite3_stmt* st = nullptr;
        sqlite3_prepare_v2(db, sql.c_str(), -1, &st, nullptr);
        while (sqlite3_step(st) == SQLITE_ROW) {
            CachedCategory c;
            readCatString(st, 0, c.category_id);
            readCatString(st, 1, c.category_name);
            readCatString(st, 2, c.parent_id);
            c.is_french = sqlite3_column_int(st, 3) != 0;
            dst.push_back(std::move(c));
        }
        sqlite3_finalize(st);
    };
    loadCats("vod_categories",    snap.movieCategories);
    loadCats("series_categories", snap.seriesCategories);

    {
        std::string sql =
            "SELECT stream_id, name, category_id, category_name, stream_icon, "
            "container_extension, rating, added, cached_at, is_french FROM movies";
        if (limit > 0) sql += " LIMIT " + std::to_string(limit);
        sqlite3_stmt* st = nullptr;
        sqlite3_prepare_v2(db, sql.c_str(), -1, &st, nullptr);
        while (sqlite3_step(st) == SQLITE_ROW) {
            CachedMovie m;
            readCatString(st, 0, m.stream_id);
            readCatString(st, 1, m.name);
            readCatString(st, 2, m.category_id);
            readCatString(st, 3, m.category_name);
            readCatString(st, 4, m.stream_icon);
            readCatString(st, 5, m.container_extension);
            m.rating = sqlite3_column_double(st, 6);
            readCatString(st, 7, m.added);
            readCatString(st, 8, m.cached_at);
            m.is_french = sqlite3_column_int(st, 9) != 0;
            snap.movies.push_back(std::move(m));
        }
        sqlite3_finalize(st);
    }
    {
        std::string sql =
            "SELECT series_id, name, category_id, category_name, cover, rating, genre, "
            "release_date, plot, cached_at, is_french FROM series";
        if (limit > 0) sql += " LIMIT " + std::to_string(limit);
        sqlite3_stmt* st = nullptr;
        sqlite3_prepare_v2(db, sql.c_str(), -1, &st, nullptr);
        while (sqlite3_step(st) == SQLITE_ROW) {
            CachedSeries s;
            readCatString(st, 0, s.series_id);
            readCatString(st, 1, s.name);
            readCatString(st, 2, s.category_id);
            readCatString(st, 3, s.category_name);
            readCatString(st, 4, s.cover);
            s.rating = sqlite3_column_double(st, 5);
            readCatString(st, 6, s.genre);
            readCatString(st, 7, s.release_date);
            readCatString(st, 8, s.plot);
            readCatString(st, 9, s.cached_at);
            s.is_french = sqlite3_column_int(st, 10) != 0;
            snap.series.push_back(std::move(s));
        }
        sqlite3_finalize(st);
    }
    return snap;
}

int64_t Cache::movieCount(bool frenchOnly) {
    if (!db_) return 0;
    auto* db = static_cast<sqlite3*>(db_);
    const char* sql = frenchOnly
        ? "SELECT COUNT(*) FROM movies WHERE is_french = 1;"
        : "SELECT COUNT(*) FROM movies;";
    sqlite3_stmt* st = nullptr;
    sqlite3_prepare_v2(db, sql, -1, &st, nullptr);
    int64_t n = (sqlite3_step(st) == SQLITE_ROW) ? sqlite3_column_int64(st, 0) : 0;
    sqlite3_finalize(st);
    return n;
}

int64_t Cache::seriesCount(bool frenchOnly) {
    if (!db_) return 0;
    auto* db = static_cast<sqlite3*>(db_);
    const char* sql = frenchOnly
        ? "SELECT COUNT(*) FROM series WHERE is_french = 1;"
        : "SELECT COUNT(*) FROM series;";
    sqlite3_stmt* st = nullptr;
    sqlite3_prepare_v2(db, sql, -1, &st, nullptr);
    int64_t n = (sqlite3_step(st) == SQLITE_ROW) ? sqlite3_column_int64(st, 0) : 0;
    sqlite3_finalize(st);
    return n;
}

void Cache::setLastSyncDate() {
    if (!db_) return;
    auto* db = static_cast<sqlite3*>(db_);
    sqlite3_stmt* st = nullptr;
    sqlite3_prepare_v2(db,
        "INSERT OR REPLACE INTO sync_meta(key, value) VALUES('last_sync', ?);",
        -1, &st, nullptr);
    std::string v = isoNow();
    bindString(st, 1, v);
    sqlite3_step(st);
    sqlite3_finalize(st);
}

std::optional<std::string> Cache::getLastSyncDate() {
    if (!db_) return std::nullopt;
    auto* db = static_cast<sqlite3*>(db_);
    sqlite3_stmt* st = nullptr;
    sqlite3_prepare_v2(db, "SELECT value FROM sync_meta WHERE key = 'last_sync';",
                      -1, &st, nullptr);
    std::optional<std::string> out;
    if (sqlite3_step(st) == SQLITE_ROW) {
        const unsigned char* v = sqlite3_column_text(st, 0);
        if (v) out = std::string(reinterpret_cast<const char*>(v));
    }
    sqlite3_finalize(st);
    return out;
}

bool Cache::needsSync(int maxAgeDays) {
    auto last = getLastSyncDate();
    if (!last) return true;
    // Parse "YYYY-MM-DDTHH:MM:SSZ" naively.
    std::tm tm{};
    if (strptime(last->c_str(), "%Y-%m-%dT%H:%M:%SZ", &tm) == nullptr) return true;
    std::time_t t = timegm(&tm);
    auto ageSec = std::time(nullptr) - t;
    return ageSec >= static_cast<std::time_t>(maxAgeDays) * 86400;
}

bool Cache::clear() {
    if (!db_) return false;
    return exec("DELETE FROM movies;")
        && exec("DELETE FROM series;")
        && exec("DELETE FROM vod_categories;")
        && exec("DELETE FROM series_categories;")
        && exec("DELETE FROM sync_meta;");
}

}  // namespace iptv::store

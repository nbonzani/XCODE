#pragma once
// SQLite-backed catalog cache, equivalent of src/services/cacheService.js (IndexedDB).
//
// Tables (mirror the IndexedDB stores):
//   movies              (stream_id PK, name, category_id, category_name, stream_icon,
//                        container_extension, rating REAL, added, cached_at, is_french INT)
//   series              (series_id PK, name, category_id, category_name, cover, rating REAL,
//                        genre, release_date, plot, cached_at, is_french INT)
//   vod_categories      (category_id PK, category_name, parent_id, is_french INT)
//   series_categories   (category_id PK, category_name, parent_id, is_french INT)
//   sync_meta           (key PK, value)
//
// Indexes mirror IndexedDB indexes (by_category, by_french, by_name).

#include <map>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace iptv::store {

using json = nlohmann::json;

struct CachedCategory {
    std::string category_id;
    std::string category_name;
    std::string parent_id;
    bool is_french = false;
};

struct CachedMovie {
    std::string stream_id;
    std::string name;
    std::string category_id;
    std::string category_name;
    std::string stream_icon;
    std::string container_extension;
    double rating = 0.0;
    std::string added;
    std::string cached_at;
    bool is_french = false;
};

struct CachedSeries {
    std::string series_id;
    std::string name;
    std::string category_id;
    std::string category_name;
    std::string cover;
    double rating = 0.0;
    std::string genre;
    std::string release_date;
    std::string plot;
    std::string cached_at;
    bool is_french = false;
};

struct CatalogSnapshot {
    std::vector<CachedMovie>    movies;
    std::vector<CachedSeries>   series;
    std::vector<CachedCategory> movieCategories;
    std::vector<CachedCategory> seriesCategories;
};

class Cache {
public:
    Cache();
    ~Cache();

    Cache(const Cache&) = delete;
    Cache& operator=(const Cache&) = delete;

    bool open();   // creates schema if missing
    void close();

    // The category->name map is derived from the categories already saved before save{Movies,SeriesList}.
    bool saveVodCategories(const std::vector<json>& categories);
    bool saveSeriesCategories(const std::vector<json>& categories);
    bool saveMovies(const std::vector<json>& movies, const std::map<std::string, std::string>& categoriesMap);
    bool saveSeriesList(const std::vector<json>& seriesList, const std::map<std::string, std::string>& categoriesMap);

    CatalogSnapshot loadCatalog();
    CatalogSnapshot loadCatalogFast(int limit = 60);

    int64_t movieCount(bool frenchOnly = true);
    int64_t seriesCount(bool frenchOnly = true);

    void setLastSyncDate();
    std::optional<std::string> getLastSyncDate();
    bool needsSync(int maxAgeDays = 30);

    bool clear();

    // Helper exposed for testing.
    static bool isFrench(const std::string& categoryName);

private:
    bool exec(const char* sql);
    bool createSchema();
    void* db_ = nullptr;   // sqlite3*, opaque to keep the header sqlite-free.
};

}  // namespace iptv::store

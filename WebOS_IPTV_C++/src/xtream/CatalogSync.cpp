#include "xtream/CatalogSync.h"

#include <algorithm>
#include <cstdio>
#include <map>
#include <unordered_set>

#include "store/Cache.h"
#include "store/Config.h"
#include "xtream/XtreamClient.h"

namespace iptv::xtream {

namespace {

// Convert parsed models back to raw JSON objects for Cache (which speaks json directly).
std::vector<nlohmann::json> rawFromCategories(const std::vector<Category>& cats) {
    std::vector<nlohmann::json> out;
    out.reserve(cats.size());
    for (const auto& c : cats) out.push_back(c.raw);
    return out;
}

std::vector<nlohmann::json> rawFromMovies(const std::vector<Movie>& items) {
    std::vector<nlohmann::json> out;
    out.reserve(items.size());
    for (const auto& m : items) out.push_back(m.raw);
    return out;
}

std::vector<nlohmann::json> rawFromSeries(const std::vector<Series>& items) {
    std::vector<nlohmann::json> out;
    out.reserve(items.size());
    for (const auto& s : items) out.push_back(s.raw);
    return out;
}

bool shouldKeep(const std::string& categoryId,
                const std::vector<std::string>& selected) {
    if (selected.empty()) return true;
    return std::find(selected.begin(), selected.end(), categoryId) != selected.end();
}

void fire(CatalogSync::ProgressCb& cb, const SyncProgress& p) {
    if (cb) cb(p);
}

}  // namespace

CatalogSync::CatalogSync(XtreamClient& client, store::Cache& cache)
    : client_(client), cache_(cache) {}

SyncResult CatalogSync::run(const store::Config& config,
                            ProgressCb progress,
                            ShouldAbortCb shouldAbort) {
    SyncResult result;
    auto aborted = [&] { return shouldAbort && shouldAbort(); };

    try {
        // 1) VOD categories
        fire(progress, {"vod_categories", 0, 1, {}});
        auto vodCats = client_.getVodCategories();
        fire(progress, {"vod_categories", 1, 1, {}});
        if (aborted()) { result.error = "aborted"; return result; }
        cache_.saveVodCategories(rawFromCategories(vodCats));

        std::map<std::string, std::string> vodCatMap;
        for (const auto& c : vodCats) vodCatMap[c.id] = c.name;

        // 2) Movies — honor selectedMovieCategories filter.
        // When the filter is empty we do one bulk fetch (no category_id param), which is faster.
        std::vector<Movie> allMovies;
        if (config.selectedMovieCategories.empty()) {
            fire(progress, {"vod_streams", 0, 1, "all"});
            allMovies = client_.getVodStreams();
            fire(progress, {"vod_streams", 1, 1, "all"});
        } else {
            int total = 0;
            for (const auto& c : vodCats) {
                if (shouldKeep(c.id, config.selectedMovieCategories)) ++total;
            }
            int done = 0;
            for (const auto& c : vodCats) {
                if (!shouldKeep(c.id, config.selectedMovieCategories)) continue;
                if (aborted()) { result.error = "aborted"; return result; }
                fire(progress, {"vod_streams", done, total, c.name});
                auto batch = client_.getVodStreams(c.id);
                allMovies.insert(allMovies.end(), batch.begin(), batch.end());
                ++done;
                fire(progress, {"vod_streams", done, total, c.name});
            }
        }
        cache_.saveMovies(rawFromMovies(allMovies), vodCatMap);
        result.moviesSaved = static_cast<int>(allMovies.size());

        // 3) Series categories
        fire(progress, {"series_categories", 0, 1, {}});
        auto serCats = client_.getSeriesCategories();
        fire(progress, {"series_categories", 1, 1, {}});
        if (aborted()) { result.error = "aborted"; return result; }
        cache_.saveSeriesCategories(rawFromCategories(serCats));

        std::map<std::string, std::string> serCatMap;
        for (const auto& c : serCats) serCatMap[c.id] = c.name;

        // 4) Series
        std::vector<Series> allSeries;
        if (config.selectedSeriesCategories.empty()) {
            fire(progress, {"series", 0, 1, "all"});
            allSeries = client_.getSeries();
            fire(progress, {"series", 1, 1, "all"});
        } else {
            int total = 0;
            for (const auto& c : serCats) {
                if (shouldKeep(c.id, config.selectedSeriesCategories)) ++total;
            }
            int done = 0;
            for (const auto& c : serCats) {
                if (!shouldKeep(c.id, config.selectedSeriesCategories)) continue;
                if (aborted()) { result.error = "aborted"; return result; }
                fire(progress, {"series", done, total, c.name});
                auto batch = client_.getSeries(c.id);
                allSeries.insert(allSeries.end(), batch.begin(), batch.end());
                ++done;
                fire(progress, {"series", done, total, c.name});
            }
        }
        cache_.saveSeriesList(rawFromSeries(allSeries), serCatMap);
        result.seriesSaved = static_cast<int>(allSeries.size());

        cache_.setLastSyncDate();
        fire(progress, {"done", 1, 1, {}});
        result.ok = true;
    } catch (const std::exception& e) {
        result.error = e.what();
        std::fprintf(stderr, "[sync] error: %s\n", e.what());
    }
    return result;
}

}  // namespace iptv::xtream

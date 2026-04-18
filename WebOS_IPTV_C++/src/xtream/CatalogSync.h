#pragma once
// Orchestrates a full catalog fetch from Xtream and saves it into the SQLite cache.
// Mirrors SyncScreen.jsx behavior: categories first, then movies/series (respecting
// selected categories from Config), with progress callbacks for UI reporting.

#include <functional>
#include <string>
#include <vector>

namespace iptv::store  { class Cache; struct Config; }
namespace iptv::xtream { class XtreamClient; }

namespace iptv::xtream {

struct SyncProgress {
    std::string phase;     // "vod_categories", "vod_streams", "series_categories", "series", "done"
    int done = 0;
    int total = 0;
    std::string currentCategoryName;
};

struct SyncResult {
    bool ok = false;
    std::string error;
    int moviesSaved = 0;
    int seriesSaved = 0;
};

class CatalogSync {
public:
    using ProgressCb = std::function<void(const SyncProgress&)>;
    using ShouldAbortCb = std::function<bool()>;

    CatalogSync(XtreamClient& client, store::Cache& cache);

    // Runs a full sync. selectedMovieCategories / selectedSeriesCategories from Config
    // restrict the fetch scope (empty vector = "all categories").
    SyncResult run(const store::Config& config,
                   ProgressCb progress = nullptr,
                   ShouldAbortCb shouldAbort = nullptr);

private:
    XtreamClient& client_;
    store::Cache& cache_;
};

}  // namespace iptv::xtream

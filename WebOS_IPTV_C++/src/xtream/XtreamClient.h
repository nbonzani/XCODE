#pragma once
// C++ port of src/services/xtreamApi.js. Same retry policy (3 tries, 1-2-4s backoff
// on 429/5xx and network/timeout errors) and same URL normalization rules.

#include <chrono>
#include <stdexcept>
#include <string>
#include <vector>

#include "xtream/Models.h"

namespace iptv::xtream {

class XtreamError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class XtreamClient {
public:
    XtreamClient(std::string serverUrl,
                 std::string port,
                 std::string username,
                 std::string password);

    // Authenticate. Throws XtreamError on bad creds, expired account, or transport failure.
    AuthInfo authenticate();

    std::vector<Category> getVodCategories();
    std::vector<Movie>    getVodStreams(const std::string& categoryId = {});
    json                  getVodInfo(const std::string& vodId);

    std::vector<Category> getSeriesCategories();
    std::vector<Series>   getSeries(const std::string& categoryId = {});
    SeriesInfo            getSeriesInfo(const std::string& seriesId);

    std::vector<Category> getLiveCategories();
    json                  getLiveStreamsRaw(const std::string& categoryId = {});

    // Fallback via panel_api.php : certains serveurs Xtream renvoient [] sur
    // action=get_vod_categories / get_series_categories alors que panel_api
    // retourne bien les listes. On parse les 3 sous-arbres et on les expose.
    struct PanelCategories {
        std::vector<Category> movies;
        std::vector<Category> series;
        std::vector<Category> live;
    };
    PanelCategories getPanelCategories();

    // URL builders — match xtreamApi.js byte-for-byte for compatibility with cached IDs.
    std::string getStreamUrl(const std::string& streamId,
                             const std::string& containerExtension) const;
    std::string getEpisodeUrl(const std::string& streamId,
                              const std::string& containerExtension) const;
    std::string getLiveUrl(const std::string& streamId,
                           const std::string& containerExtension = "ts") const;

    const std::string& baseUrl() const { return baseUrl_; }

private:
    using Params = std::vector<std::pair<std::string, std::string>>;

    // Issue GET on player_api.php with credentials + extra params, return parsed JSON.
    json getJson(const Params& extraParams,
                 std::chrono::milliseconds timeout = std::chrono::seconds(15));

    std::string buildUrl(const Params& params) const;

    std::string baseUrl_;     // e.g. http://server:port (no trailing slash)
    std::string apiUrl_;      // baseUrl_ + "/player_api.php"
    std::string username_;
    std::string password_;

    // Cache mémoire du résultat panel_api (80-100 MB). Partagé entre
    // getVodCategories/getSeriesCategories fallbacks pour éviter de
    // télécharger deux fois la même payload.
    bool panel_loaded_ = false;
    PanelCategories panel_cache_;
};

}  // namespace iptv::xtream

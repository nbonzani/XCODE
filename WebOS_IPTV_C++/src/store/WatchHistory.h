#pragma once
// Port of src/services/watchHistoryService.js. Two on-disk JSON files:
//   - watched_series.json :  { "<series_id>": { "<episode_id>": "<iso_date>", ... }, ... }
//   - last_watched.json   :  { "seriesId":..., "seriesName":..., "episodeTitle":...,
//                              "episodeId":..., "streamUrl":..., "date":<iso> }

#include <optional>
#include <set>
#include <string>

#include <nlohmann/json.hpp>

namespace iptv::store {

using json = nlohmann::json;

struct LastWatched {
    std::string seriesId;
    std::string seriesName;
    std::string episodeTitle;
    std::string episodeId;
    std::string streamUrl;
    std::string date;   // ISO 8601 string
};

class WatchHistory {
public:
    static void markEpisodeWatched(const std::string& episodeId, const std::string& seriesId);

    static void setLastWatchedSeries(const std::string& seriesId,
                                     const std::string& seriesName,
                                     const std::string& episodeTitle,
                                     const std::string& episodeId,
                                     const std::string& streamUrl);

    static std::optional<LastWatched> getLastWatchedSeries();

    static std::set<std::string> getWatchedEpisodesSet(const std::string& seriesId);
};

}  // namespace iptv::store

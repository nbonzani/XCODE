#include "store/WatchHistory.h"

#include <chrono>
#include <ctime>
#include <iomanip>
#include <sstream>

#include "store/JsonFile.h"
#include "store/Paths.h"

namespace iptv::store {

namespace {
std::string isoNow() {
    using namespace std::chrono;
    auto now = system_clock::now();
    auto ms  = duration_cast<milliseconds>(now.time_since_epoch()).count() % 1000;
    std::time_t t = system_clock::to_time_t(now);
    std::tm tm{};
    gmtime_r(&t, &tm);
    std::ostringstream oss;
    oss << std::put_time(&tm, "%Y-%m-%dT%H:%M:%S")
        << '.' << std::setw(3) << std::setfill('0') << ms << 'Z';
    return oss.str();
}
}  // namespace

void WatchHistory::markEpisodeWatched(const std::string& episodeId,
                                      const std::string& seriesId) {
    if (seriesId.empty() || episodeId.empty()) return;
    json all = readJson(Paths::watchedSeriesFile());
    if (!all.is_object()) all = json::object();
    json& bySeries = all[seriesId];
    if (!bySeries.is_object()) bySeries = json::object();
    bySeries[episodeId] = isoNow();
    writeJson(Paths::watchedSeriesFile(), all);
}

void WatchHistory::setLastWatchedSeries(const std::string& seriesId,
                                        const std::string& seriesName,
                                        const std::string& episodeTitle,
                                        const std::string& episodeId,
                                        const std::string& streamUrl) {
    json j;
    j["seriesId"]     = seriesId;
    j["seriesName"]   = seriesName;
    j["episodeTitle"] = episodeTitle;
    j["episodeId"]    = episodeId.empty() ? json(nullptr) : json(episodeId);
    j["streamUrl"]    = streamUrl.empty() ? json(nullptr) : json(streamUrl);
    j["date"]         = isoNow();
    writeJson(Paths::lastWatchedFile(), j);
}

std::optional<LastWatched> WatchHistory::getLastWatchedSeries() {
    json j = readJson(Paths::lastWatchedFile(), json(nullptr));
    if (!j.is_object()) return std::nullopt;
    LastWatched lw;
    auto getStr = [&](const char* key) -> std::string {
        if (!j.contains(key) || j.at(key).is_null()) return "";
        if (j.at(key).is_string()) return j.at(key).get<std::string>();
        return j.at(key).dump();
    };
    lw.seriesId     = getStr("seriesId");
    lw.seriesName   = getStr("seriesName");
    lw.episodeTitle = getStr("episodeTitle");
    lw.episodeId    = getStr("episodeId");
    lw.streamUrl    = getStr("streamUrl");
    lw.date         = getStr("date");
    return lw;
}

std::set<std::string> WatchHistory::getWatchedEpisodesSet(const std::string& seriesId) {
    std::set<std::string> out;
    if (seriesId.empty()) return out;
    json all = readJson(Paths::watchedSeriesFile());
    if (!all.is_object() || !all.contains(seriesId) || !all[seriesId].is_object()) return out;
    for (auto it = all[seriesId].begin(); it != all[seriesId].end(); ++it) {
        out.insert(it.key());
    }
    return out;
}

}  // namespace iptv::store

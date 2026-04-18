#pragma once
// Light DTOs covering the subset of Xtream player_api.php fields the React app uses.
// Only fields actually consumed by the original screens are mapped — additional
// fields stay accessible via the raw nlohmann::json kept on each item.

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace iptv::xtream {

using json = nlohmann::json;

struct Category {
    std::string id;
    std::string name;
    std::string parent_id;
    json raw;
};

struct Movie {
    std::string stream_id;
    std::string name;
    std::string category_id;
    std::string stream_icon;
    std::string container_extension;
    std::string rating;
    std::string added;       // unix epoch as string in Xtream
    json raw;
};

struct Series {
    std::string series_id;
    std::string name;
    std::string category_id;
    std::string cover;
    std::string genre;
    std::string release_date;
    std::string rating;
    std::string plot;
    json raw;
};

struct Episode {
    std::string id;
    std::string title;
    int season = 0;
    int episode_num = 0;
    std::string container_extension;
    std::string added;
    json raw;
};

struct Season {
    int season_number = 0;
    std::vector<Episode> episodes;
    json raw;
};

struct SeriesInfo {
    Series series;
    std::vector<Season> seasons;
    json raw;
};

// Result of authenticate() — surfaces auth + status, keeps the rest in raw.
struct AuthInfo {
    bool authenticated = false;
    std::string status;            // "Active", "Expired", ...
    std::string username;
    std::string expDate;           // unix epoch as string, possibly empty
    std::string serverUrl;
    json user_info;
    json server_info;
    json raw;
};

}  // namespace iptv::xtream

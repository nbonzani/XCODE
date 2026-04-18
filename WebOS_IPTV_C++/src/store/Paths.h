#pragma once
// Resolves where the app stores its data on disk. Same layout on host (Linux dev box)
// and on webOS TV — XDG_DATA_HOME with a HOME-based fallback.

#include <filesystem>
#include <string>

namespace iptv::store {

class Paths {
public:
    // Root data dir, e.g. $XDG_DATA_HOME/iptv-player or $HOME/.local/share/iptv-player.
    // Created lazily.
    static std::filesystem::path dataDir();

    static std::filesystem::path configFile();          // <data>/config.json
    static std::filesystem::path watchPositionFile();   // <data>/positions.json
    static std::filesystem::path favoritesFile();       // <data>/favorites.json
    static std::filesystem::path watchedSeriesFile();   // <data>/watched_series.json
    static std::filesystem::path lastWatchedFile();     // <data>/last_watched.json
    static std::filesystem::path cacheDb();             // <data>/cache.sqlite
};

}  // namespace iptv::store

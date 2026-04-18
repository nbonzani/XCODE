#include "store/Paths.h"

#include <cstdlib>
#include <system_error>

namespace iptv::store {

namespace fs = std::filesystem;

fs::path Paths::dataDir() {
    fs::path base;
    if (const char* xdg = std::getenv("XDG_DATA_HOME"); xdg && *xdg) {
        base = fs::path(xdg) / "iptv-player";
    } else if (const char* home = std::getenv("HOME"); home && *home) {
        base = fs::path(home) / ".local" / "share" / "iptv-player";
    } else {
        base = fs::path("/tmp") / "iptv-player";
    }
    std::error_code ec;
    fs::create_directories(base, ec);  // best-effort
    return base;
}

fs::path Paths::configFile()        { return dataDir() / "config.json"; }
fs::path Paths::watchPositionFile() { return dataDir() / "positions.json"; }
fs::path Paths::favoritesFile()     { return dataDir() / "favorites.json"; }
fs::path Paths::watchedSeriesFile() { return dataDir() / "watched_series.json"; }
fs::path Paths::lastWatchedFile()   { return dataDir() / "last_watched.json"; }
fs::path Paths::cacheDb()           { return dataDir() / "cache.sqlite"; }

}  // namespace iptv::store

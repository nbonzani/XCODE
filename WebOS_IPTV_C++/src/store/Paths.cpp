#include "store/Paths.h"

#include <cstdlib>
#include <fstream>
#include <system_error>
#include <vector>

namespace iptv::store {

namespace fs = std::filesystem;

fs::path Paths::dataDir() {
    // Candidate data dirs, tried in order until we find one we can actually write to.
    // On webOS the app sandbox usually allows /media/internal/<appId> or the app's
    // own directory; /tmp is always writable but volatile. HOME may or may not be set.
    std::vector<fs::path> candidates;
    if (const char* xdg = std::getenv("XDG_DATA_HOME"); xdg && *xdg) {
        candidates.emplace_back(fs::path(xdg) / "iptv-player");
    }
    if (const char* home = std::getenv("HOME"); home && *home) {
        candidates.emplace_back(fs::path(home) / ".local" / "share" / "iptv-player");
    }
    candidates.emplace_back("/media/internal/.iptv-player");
    candidates.emplace_back("/tmp/iptv-player");

    for (const auto& c : candidates) {
        std::error_code ec;
        fs::create_directories(c, ec);
        if (!ec && fs::exists(c)) {
            // Write probe.
            auto probe = c / ".write_probe";
            std::ofstream f(probe);
            if (f) { f.close(); fs::remove(probe, ec); return c; }
        }
    }
    return fs::path("/tmp/iptv-player");  // last-resort
}

fs::path Paths::configFile()        { return dataDir() / "config.json"; }
fs::path Paths::watchPositionFile() { return dataDir() / "positions.json"; }
fs::path Paths::favoritesFile()     { return dataDir() / "favorites.json"; }
fs::path Paths::watchedSeriesFile() { return dataDir() / "watched_series.json"; }
fs::path Paths::lastWatchedFile()   { return dataDir() / "last_watched.json"; }
fs::path Paths::cacheDb()           { return dataDir() / "cache.sqlite"; }

}  // namespace iptv::store

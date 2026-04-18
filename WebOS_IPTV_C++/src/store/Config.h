#pragma once
// Mirrors the React app's appStore config slice. Persisted to <data>/config.json.

#include <string>
#include <vector>

namespace iptv::store {

struct Config {
    // Xtream credentials
    std::string serverUrl;
    std::string port;
    std::string username;
    std::string password;

    // Catalog filters
    bool frenchOnly = true;
    std::vector<std::string> selectedMovieCategories;   // empty = "all"
    std::vector<std::string> selectedSeriesCategories;
    bool catalogSetupDone = false;

    static Config load();
    bool save() const;
};

}  // namespace iptv::store

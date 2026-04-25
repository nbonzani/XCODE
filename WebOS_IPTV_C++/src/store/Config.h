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
    bool frenchOnly = true;  // legacy — dérivé de selectedLanguages
    std::vector<std::string> selectedLanguages;         // codes ISO : "fr"|"en"|"it"|"de"|"es"
    std::vector<std::string> selectedMovieCategories;   // empty = "all"
    std::vector<std::string> selectedSeriesCategories;
    // VOST : un code langue ISO par case cochée (ex : "fr" = VOSTFR, "en" =
    // VOSTEN…). Sous-ensemble de selectedLanguages ; les autres codes sont
    // ignorés au chargement. Une entrée = inclure les VO sous-titrées dans
    // cette langue, en plus de la VF équivalente si la langue parente est
    // cochée.
    std::vector<std::string> vostLanguages;
    bool catalogSetupDone = false;

    static Config load();
    bool save() const;
};

}  // namespace iptv::store

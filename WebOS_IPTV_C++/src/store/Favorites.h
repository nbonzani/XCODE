#pragma once
// Port of src/services/favoritesService.js. Persisted as
//   { "movies": [<full movie object>...], "series": [<full series object>...] }

#include <string>

#include <nlohmann/json.hpp>

namespace iptv::store {

using json = nlohmann::json;

enum class FavoriteKind { Movie, Series };

class Favorites {
public:
    // Add to favorites if absent (matched on stream_id for movies, series_id for series).
    static void add(const json& item, FavoriteKind kind);
    static void remove(const std::string& itemId, FavoriteKind kind);
    // Returns true if added, false if removed.
    static bool toggle(const json& item, FavoriteKind kind);
    static bool contains(const std::string& itemId, FavoriteKind kind);
    static json all();   // { "movies": [...], "series": [...] }
    static int count();
};

}  // namespace iptv::store

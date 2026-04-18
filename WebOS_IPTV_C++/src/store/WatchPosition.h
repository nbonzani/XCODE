#pragma once
// Same persistence rules as src/services/watchPositionService.js:
//   * duration < 30 s        -> ignored
//   * position/duration > 90% -> cleared (treated as completed)
//   * position/duration < 2%  -> ignored
//   * otherwise              -> stored (position, duration, savedAt unix-ms)

#include <cstdint>
#include <string>

namespace iptv::store {

class WatchPosition {
public:
    // Save position. itemId can be a stream_id or episode id (anything string-keyable).
    static void save(const std::string& itemId, double position, double duration);

    // Returns 0.0 when no position is stored.
    static double get(const std::string& itemId);

    static void clear(const std::string& itemId);

    // "1h05m" / "12min 34s" / "" if seconds < 1
    static std::string format(double seconds);
};

}  // namespace iptv::store

#include "store/WatchPosition.h"

#include <chrono>
#include <cmath>
#include <sstream>

#include "store/JsonFile.h"
#include "store/Paths.h"

namespace iptv::store {

namespace {
int64_t nowMs() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count();
}
}  // namespace

void WatchPosition::save(const std::string& itemId, double position, double duration) {
    if (itemId.empty() || duration < 30.0 || std::isnan(duration)) return;
    double pct = position / duration;
    json j = readJson(Paths::watchPositionFile());
    if (!j.is_object()) j = json::object();

    if (pct > 0.90) {
        j.erase(itemId);
        writeJson(Paths::watchPositionFile(), j);
        return;
    }
    if (pct < 0.02) return;

    j[itemId] = {
        {"position", static_cast<int64_t>(position)},
        {"duration", static_cast<int64_t>(duration)},
        {"savedAt",  nowMs()},
    };
    writeJson(Paths::watchPositionFile(), j);
}

double WatchPosition::get(const std::string& itemId) {
    if (itemId.empty()) return 0.0;
    json j = readJson(Paths::watchPositionFile());
    if (!j.is_object() || !j.contains(itemId)) return 0.0;
    const auto& entry = j.at(itemId);
    if (!entry.contains("position")) return 0.0;
    try { return entry.at("position").get<double>(); }
    catch (...) { return 0.0; }
}

void WatchPosition::clear(const std::string& itemId) {
    if (itemId.empty()) return;
    json j = readJson(Paths::watchPositionFile());
    if (!j.is_object() || !j.contains(itemId)) return;
    j.erase(itemId);
    writeJson(Paths::watchPositionFile(), j);
}

std::string WatchPosition::format(double seconds) {
    if (seconds < 1.0) return "";
    int64_t s_total = static_cast<int64_t>(seconds);
    int64_t h = s_total / 3600;
    int64_t m = (s_total % 3600) / 60;
    int64_t s = s_total % 60;
    std::ostringstream oss;
    if (h > 0) {
        oss << h << "h";
        if (m < 10) oss << "0";
        oss << m << "m";
    } else {
        oss << m << "min ";
        if (s < 10) oss << "0";
        oss << s << "s";
    }
    return oss.str();
}

}  // namespace iptv::store

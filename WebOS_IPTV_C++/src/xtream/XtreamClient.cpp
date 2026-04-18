#include "xtream/XtreamClient.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <sstream>
#include <thread>
#include <unordered_set>

#include <curl/curl.h>

namespace iptv::xtream {

namespace {

constexpr int kRetryCount = 3;
constexpr int kRetryDelaysMs[3] = {1000, 2000, 4000};

const std::unordered_set<long>& retryStatuses() {
    static const std::unordered_set<long> s = {429, 500, 502, 503, 504};
    return s;
}

std::size_t writeCb(char* ptr, std::size_t size, std::size_t nmemb, void* userdata) {
    auto* out = static_cast<std::string*>(userdata);
    out->append(ptr, size * nmemb);
    return size * nmemb;
}

std::string urlEncode(CURL* curl, const std::string& s) {
    char* esc = curl_easy_escape(curl, s.c_str(), static_cast<int>(s.size()));
    std::string out = esc ? esc : "";
    if (esc) curl_free(esc);
    return out;
}

std::string normalizeBaseUrl(const std::string& serverUrl, const std::string& port) {
    std::string base = serverUrl;
    // trim
    auto isspace_c = [](unsigned char c){ return std::isspace(c); };
    while (!base.empty() && isspace_c(base.front())) base.erase(base.begin());
    while (!base.empty() && isspace_c(base.back()))  base.pop_back();
    while (!base.empty() && base.back() == '/') base.pop_back();

    if (!base.empty() &&
        base.compare(0, 7, "http://")  != 0 &&
        base.compare(0, 8, "https://") != 0) {
        base = "http://" + base;
    }

    std::string p = port;
    while (!p.empty() && isspace_c(p.front())) p.erase(p.begin());
    while (!p.empty() && isspace_c(p.back()))  p.pop_back();

    bool skipPort = p.empty() || p == "80" || p == "443";
    return skipPort ? base : base + ":" + p;
}

// Map nlohmann::json field to std::string, accepting either "string" or any scalar.
std::string asString(const json& v) {
    if (v.is_null()) return "";
    if (v.is_string()) return v.get<std::string>();
    if (v.is_number_integer()) return std::to_string(v.get<long long>());
    if (v.is_number_unsigned()) return std::to_string(v.get<unsigned long long>());
    if (v.is_number_float()) {
        std::ostringstream oss;
        oss << v.get<double>();
        return oss.str();
    }
    if (v.is_boolean()) return v.get<bool>() ? "1" : "0";
    return v.dump();
}

std::string getString(const json& obj, const char* key) {
    if (!obj.contains(key)) return "";
    return asString(obj.at(key));
}

int getInt(const json& obj, const char* key) {
    if (!obj.contains(key)) return 0;
    const auto& v = obj.at(key);
    if (v.is_number_integer()) return v.get<int>();
    if (v.is_number_unsigned()) return static_cast<int>(v.get<unsigned long long>());
    if (v.is_string()) {
        try { return std::stoi(v.get<std::string>()); } catch (...) { return 0; }
    }
    return 0;
}

}  // namespace

XtreamClient::XtreamClient(std::string serverUrl,
                           std::string port,
                           std::string username,
                           std::string password)
    : username_(std::move(username)),
      password_(std::move(password)) {
    baseUrl_ = normalizeBaseUrl(serverUrl, port);
    apiUrl_  = baseUrl_ + "/player_api.php";
}

std::string XtreamClient::buildUrl(const Params& params) const {
    CURL* curl = curl_easy_init();
    if (!curl) throw XtreamError("curl_easy_init() failed");

    std::string url = apiUrl_ + "?";
    auto append = [&](const std::string& k, const std::string& v) {
        if (url.back() != '?') url += '&';
        url += urlEncode(curl, k) + "=" + urlEncode(curl, v);
    };
    append("username", username_);
    append("password", password_);
    for (const auto& [k, v] : params) append(k, v);

    curl_easy_cleanup(curl);
    return url;
}

json XtreamClient::getJson(const Params& extraParams, std::chrono::milliseconds timeout) {
    std::string url = buildUrl(extraParams);
    std::string lastError;

    for (int attempt = 0; attempt < kRetryCount; ++attempt) {
        CURL* curl = curl_easy_init();
        if (!curl) throw XtreamError("curl_easy_init() failed");

        std::string body;
        long http_code = 0;
        struct curl_slist* headers = nullptr;
        headers = curl_slist_append(headers, "User-Agent: IPTVPlayer-Native/0.1");
        headers = curl_slist_append(headers, "Accept: application/json");

        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, static_cast<long>(timeout.count()));
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS, 10000L);
        curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCb);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &body);

        CURLcode rc = curl_easy_perform(curl);
        if (rc == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);

        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);

        if (rc == CURLE_OPERATION_TIMEDOUT || rc == CURLE_COULDNT_CONNECT ||
            rc == CURLE_COULDNT_RESOLVE_HOST || rc == CURLE_RECV_ERROR ||
            rc == CURLE_SEND_ERROR) {
            lastError = std::string("network: ") + curl_easy_strerror(rc);
            if (attempt < kRetryCount - 1) {
                std::this_thread::sleep_for(std::chrono::milliseconds(kRetryDelaysMs[attempt]));
                continue;
            }
            throw XtreamError("Connexion impossible vers " + baseUrl_ + " (" + lastError + ")");
        }
        if (rc != CURLE_OK) {
            throw XtreamError(std::string("curl error: ") + curl_easy_strerror(rc));
        }

        if (retryStatuses().count(http_code) && attempt < kRetryCount - 1) {
            lastError = "HTTP " + std::to_string(http_code);
            std::this_thread::sleep_for(std::chrono::milliseconds(kRetryDelaysMs[attempt]));
            continue;
        }

        if (http_code < 200 || http_code >= 300) {
            throw XtreamError("HTTP " + std::to_string(http_code) + " from server");
        }

        try {
            return json::parse(body);
        } catch (const json::parse_error&) {
            throw XtreamError("Réponse serveur invalide (non-JSON). Vérifiez l'URL. "
                              "Aperçu : " + body.substr(0, 120));
        }
    }
    throw XtreamError("Toutes les tentatives ont échoué : " + lastError);
}

// ── Public API ───────────────────────────────────────────────────────────────

AuthInfo XtreamClient::authenticate() {
    json data = getJson({});
    if (!data.is_object()) {
        throw XtreamError("Authentification échouée — réponse inattendue.");
    }
    AuthInfo info;
    info.raw = data;
    info.user_info   = data.value("user_info",   json::object());
    info.server_info = data.value("server_info", json::object());

    int auth = getInt(info.user_info, "auth");
    info.authenticated = (auth == 1);
    info.status   = getString(info.user_info, "status");
    info.username = getString(info.user_info, "username");
    info.expDate  = getString(info.user_info, "exp_date");
    info.serverUrl = getString(info.server_info, "url");

    if (!info.authenticated) {
        throw XtreamError("Identifiants incorrects. "
                          "Vérifiez votre nom d'utilisateur et mot de passe.");
    }
    if (info.status == "Expired") {
        throw XtreamError("Votre abonnement a expiré.");
    }
    return info;
}

static std::vector<Category> parseCategories(const json& arr) {
    std::vector<Category> out;
    if (!arr.is_array()) return out;
    out.reserve(arr.size());
    for (const auto& it : arr) {
        Category c;
        c.id        = getString(it, "category_id");
        c.name      = getString(it, "category_name");
        c.parent_id = getString(it, "parent_id");
        c.raw = it;
        out.push_back(std::move(c));
    }
    return out;
}

std::vector<Category> XtreamClient::getVodCategories() {
    return parseCategories(getJson({{"action", "get_vod_categories"}}));
}

std::vector<Movie> XtreamClient::getVodStreams(const std::string& categoryId) {
    Params p = {{"action", "get_vod_streams"}};
    auto t = std::chrono::milliseconds(120000);
    if (!categoryId.empty()) {
        p.push_back({"category_id", categoryId});
        t = std::chrono::milliseconds(30000);
    }
    json arr = getJson(p, t);
    std::vector<Movie> out;
    if (!arr.is_array()) return out;
    out.reserve(arr.size());
    for (const auto& it : arr) {
        Movie m;
        m.stream_id            = getString(it, "stream_id");
        m.name                 = getString(it, "name");
        m.category_id          = getString(it, "category_id");
        m.stream_icon          = getString(it, "stream_icon");
        m.container_extension  = getString(it, "container_extension");
        m.rating               = getString(it, "rating");
        m.added                = getString(it, "added");
        m.raw = it;
        out.push_back(std::move(m));
    }
    return out;
}

json XtreamClient::getVodInfo(const std::string& vodId) {
    json result = getJson({{"action", "get_vod_info"}, {"vod_id", vodId}},
                          std::chrono::milliseconds(20000));
    return result.is_object() ? result : json::object();
}

std::vector<Category> XtreamClient::getSeriesCategories() {
    return parseCategories(getJson({{"action", "get_series_categories"}}));
}

std::vector<Series> XtreamClient::getSeries(const std::string& categoryId) {
    Params p = {{"action", "get_series"}};
    auto t = std::chrono::milliseconds(120000);
    if (!categoryId.empty()) {
        p.push_back({"category_id", categoryId});
        t = std::chrono::milliseconds(30000);
    }
    json arr = getJson(p, t);
    std::vector<Series> out;
    if (!arr.is_array()) return out;
    out.reserve(arr.size());
    for (const auto& it : arr) {
        Series s;
        s.series_id    = getString(it, "series_id");
        s.name         = getString(it, "name");
        s.category_id  = getString(it, "category_id");
        s.cover        = getString(it, "cover");
        s.genre        = getString(it, "genre");
        s.release_date = getString(it, "releaseDate");
        if (s.release_date.empty()) s.release_date = getString(it, "release_date");
        s.rating       = getString(it, "rating");
        s.plot         = getString(it, "plot");
        s.raw = it;
        out.push_back(std::move(s));
    }
    return out;
}

SeriesInfo XtreamClient::getSeriesInfo(const std::string& seriesId) {
    json data = getJson({{"action", "get_series_info"}, {"series_id", seriesId}},
                        std::chrono::milliseconds(30000));
    SeriesInfo info;
    info.raw = data;
    if (!data.is_object()) return info;

    const json& si = data.value("info", json::object());
    info.series.series_id    = getString(si, "series_id");
    info.series.name         = getString(si, "name");
    info.series.category_id  = getString(si, "category_id");
    info.series.cover        = getString(si, "cover");
    info.series.genre        = getString(si, "genre");
    info.series.release_date = getString(si, "releaseDate");
    if (info.series.release_date.empty()) info.series.release_date = getString(si, "release_date");
    info.series.rating       = getString(si, "rating");
    info.series.plot         = getString(si, "plot");
    info.series.raw = si;

    // "episodes" is an object keyed by season number, each value is an array.
    if (data.contains("episodes") && data["episodes"].is_object()) {
        for (auto it = data["episodes"].begin(); it != data["episodes"].end(); ++it) {
            Season season;
            try { season.season_number = std::stoi(it.key()); }
            catch (...) { season.season_number = 0; }
            const json& list = it.value();
            if (!list.is_array()) continue;
            season.raw = list;
            for (const auto& e : list) {
                Episode ep;
                ep.id                  = getString(e, "id");
                ep.title               = getString(e, "title");
                ep.season              = getInt(e, "season");
                ep.episode_num         = getInt(e, "episode_num");
                ep.container_extension = getString(e, "container_extension");
                ep.added               = getString(e, "added");
                ep.raw = e;
                season.episodes.push_back(std::move(ep));
            }
            info.seasons.push_back(std::move(season));
        }
        std::sort(info.seasons.begin(), info.seasons.end(),
                  [](const Season& a, const Season& b) {
                      return a.season_number < b.season_number;
                  });
    }
    return info;
}

std::vector<Category> XtreamClient::getLiveCategories() {
    return parseCategories(getJson({{"action", "get_live_categories"}}));
}

json XtreamClient::getLiveStreamsRaw(const std::string& categoryId) {
    Params p = {{"action", "get_live_streams"}};
    auto t = std::chrono::milliseconds(120000);
    if (!categoryId.empty()) {
        p.push_back({"category_id", categoryId});
        t = std::chrono::milliseconds(30000);
    }
    return getJson(p, t);
}

std::string XtreamClient::getStreamUrl(const std::string& streamId,
                                       const std::string& containerExtension) const {
    return baseUrl_ + "/movie/" + username_ + "/" + password_ + "/" +
           streamId + "." + containerExtension;
}

std::string XtreamClient::getEpisodeUrl(const std::string& streamId,
                                        const std::string& containerExtension) const {
    return baseUrl_ + "/series/" + username_ + "/" + password_ + "/" +
           streamId + "." + containerExtension;
}

std::string XtreamClient::getLiveUrl(const std::string& streamId,
                                     const std::string& containerExtension) const {
    std::string ext = containerExtension.empty() ? "ts" : containerExtension;
    return baseUrl_ + "/live/" + username_ + "/" + password_ + "/" +
           streamId + "." + ext;
}

}  // namespace iptv::xtream

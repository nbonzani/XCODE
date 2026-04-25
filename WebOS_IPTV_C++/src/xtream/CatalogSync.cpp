#include "xtream/CatalogSync.h"

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cstdio>
#include <future>
#include <map>
#include <mutex>
#include <regex>
#include <thread>
#include <unordered_set>

#include "store/Cache.h"
#include "store/Config.h"
#include "xtream/XtreamClient.h"

namespace iptv::xtream {

namespace {

// Convert parsed models back to raw JSON objects for Cache (which speaks json directly).
std::vector<nlohmann::json> rawFromCategories(const std::vector<Category>& cats) {
    std::vector<nlohmann::json> out;
    out.reserve(cats.size());
    for (const auto& c : cats) out.push_back(c.raw);
    return out;
}

std::vector<nlohmann::json> rawFromMovies(const std::vector<Movie>& items) {
    std::vector<nlohmann::json> out;
    out.reserve(items.size());
    for (const auto& m : items) out.push_back(m.raw);
    return out;
}

std::vector<nlohmann::json> rawFromSeries(const std::vector<Series>& items) {
    std::vector<nlohmann::json> out;
    out.reserve(items.size());
    for (const auto& s : items) out.push_back(s.raw);
    return out;
}

bool shouldKeep(const std::string& categoryId,
                const std::vector<std::string>& selected) {
    if (selected.empty()) return true;
    return std::find(selected.begin(), selected.end(), categoryId) != selected.end();
}

// Détecte si le nom de catégorie contient un tag VOST<code> (ex : "VOSTFR").
// Renvoie le code langue ISO lowercase ("fr", "en", …), sinon "".
std::string categoryVostLang(const std::string& name) {
    static const std::regex re(
        R"((^|[^A-Za-z])VOST(FR|EN|IT|DE|ES)([^A-Za-z]|$))",
        std::regex::icase);
    std::smatch m;
    if (std::regex_search(name, m, re)) {
        std::string code = m[2].str();
        for (char& c : code) c = (char)std::tolower((unsigned char)c);
        return code;
    }
    return "";
}

// Match un nom de catégorie contre une liste de langues ISO
// (fr/en/it/de/es). Reconnaît les tags "FR -", "EN -", "IT - ", "ITALIANO",
// "ALLEMAND", etc. tivimate-style : on ne descend QUE les catégories qui
// passent, plutôt que tout télécharger puis filtrer côté UI.
bool matchesLanguages(const std::string& categoryName,
                      const std::vector<std::string>& langs) {
    if (langs.empty()) return true;  // pas de filtre langue = tout
    if (categoryName.empty()) return false;
    // Patterns (insensibles à la casse, bornes de mot simples).
    struct LangPat { const char* code; std::vector<std::regex> res; };
    auto build = [](std::initializer_list<const char*> rxs) {
        std::vector<std::regex> v;
        for (auto p : rxs) v.emplace_back(p, std::regex::icase);
        return v;
    };
    static const std::vector<LangPat> kTable = {
        {"fr", build({R"((^|[^A-Za-z])FR([^A-Za-z]|$))",
                       R"((^|[^A-Za-z])(?:FRENCH|FRANCE|FRANCAIS|FRANÇAIS)([^A-Za-z]|$))"})},
        {"en", build({R"((^|[^A-Za-z])EN([^A-Za-z]|$))",
                       R"((^|[^A-Za-z])(?:ENGLISH|ENG|UK|USA)([^A-Za-z]|$))"})},
        {"it", build({R"((^|[^A-Za-z])IT([^A-Za-z]|$))",
                       R"((^|[^A-Za-z])(?:ITALIAN|ITALIANO|ITALY|ITALIE)([^A-Za-z]|$))"})},
        {"de", build({R"((^|[^A-Za-z])DE([^A-Za-z]|$))",
                       R"((^|[^A-Za-z])(?:GERMAN|DEUTSCH|GERMANY|ALLEMAND)([^A-Za-z]|$))"})},
        {"es", build({R"((^|[^A-Za-z])ES([^A-Za-z]|$))",
                       R"((^|[^A-Za-z])(?:SPANISH|ESPANOL|ESPAÑOL|SPAIN|ESPAGNE)([^A-Za-z]|$))"})},
    };
    for (const auto& code : langs) {
        for (const auto& lp : kTable) {
            if (code != lp.code) continue;
            for (const auto& re : lp.res) {
                if (std::regex_search(categoryName, re)) return true;
            }
        }
    }
    return false;
}

// Filtre combiné langues + VOST : une catégorie marquée VOSTFR/VOSTEN/… n'est
// gardée que si la langue VOST correspondante est cochée dans
// cfg.vostLanguages. Les catégories non-VOST utilisent matchesLanguages
// classique.
bool matchesCategory(const std::string& name,
                     const std::vector<std::string>& langs,
                     const std::vector<std::string>& vostLangs) {
    std::string vost = categoryVostLang(name);
    if (!vost.empty()) {
        return std::find(vostLangs.begin(), vostLangs.end(), vost) !=
               vostLangs.end();
    }
    return matchesLanguages(name, langs);
}

// Filtre TITRE de film/série : certains serveurs mélangent VF et VOSTFR dans
// la même catégorie ("VOD | FR - LATEST MOVIES") et marquent VOST dans le
// titre individuel (ex : "La Femme de ménage - 2025 [VOSTFR]"). On écarte
// donc au niveau item si le titre contient VOSTxx et que la langue VOST
// correspondante n'est pas cochée.
bool itemTitleAllowedByVost(const std::string& title,
                            const std::vector<std::string>& vostLangs) {
    std::string vost = categoryVostLang(title);  // même regex, réutilisée
    if (vost.empty()) return true;
    return std::find(vostLangs.begin(), vostLangs.end(), vost) !=
           vostLangs.end();
}

void fire(CatalogSync::ProgressCb& cb, const SyncProgress& p) {
    if (cb) cb(p);
}

}  // namespace

CatalogSync::CatalogSync(XtreamClient& client, store::Cache& cache)
    : client_(client), cache_(cache) {}

SyncResult CatalogSync::run(const store::Config& config,
                            ProgressCb progress,
                            ShouldAbortCb shouldAbort) {
    SyncResult result;
    auto aborted = [&] { return shouldAbort && shouldAbort(); };
    auto t_start = std::chrono::steady_clock::now();
    auto elapsed_ms = [&]() -> int {
        return (int)std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - t_start).count();
    };

    try {
        // 1) VOD categories
        fire(progress, {"vod_categories", 0, 1, {}});
        auto t_cats_start = std::chrono::steady_clock::now();
        auto vodCats = client_.getVodCategories();
        fire(progress, {"vod_categories", 1, 1, {}});
        if (aborted()) { result.error = "aborted"; return result; }

        std::map<std::string, std::string> vodCatMap;
        for (const auto& c : vodCats) vodCatMap[c.id] = c.name;

        // 2) Movies — filtrage tivimate-style : on ne télécharge QUE les
        // catégories qui passent les filtres (langue + sélection utilisateur).
        // Ne stocke en cache QUE les catégories retenues (DB plus petite et
        // CatalogFilterScreen plus rapide — inutile de montrer des catégories
        // qu'on ne téléchargera jamais).
        std::vector<Category> keepVodCats;
        for (const auto& c : vodCats) {
            if (!shouldKeep(c.id, config.selectedMovieCategories)) continue;
            if (!matchesCategory(c.name, config.selectedLanguages,
                                 config.vostLanguages)) continue;
            keepVodCats.push_back(c);
        }
        cache_.saveVodCategories(rawFromCategories(keepVodCats));
        int vod_cats_ms = (int)std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - t_cats_start).count();

        // Fetch par catégorie en parallèle (4 threads) — gain ~4× sur le
        // temps total pour des pipes réseau I/O-bound. Le backend Xtream
        // supporte largement la concurrence (un fetch = une req HTTP GET).
        auto t_movies_start = std::chrono::steady_clock::now();
        std::vector<Movie> allMovies;
        {
            const int total = (int)keepVodCats.size();
            std::atomic<int> done{0};
            std::mutex merge_mu;
            auto worker = [&](int start, int step) {
                for (int i = start; i < total; i += step) {
                    if (aborted()) return;
                    const auto& c = keepVodCats[i];
                    auto batch = client_.getVodStreams(c.id);
                    {
                        std::lock_guard<std::mutex> lk(merge_mu);
                        allMovies.insert(allMovies.end(),
                                         std::make_move_iterator(batch.begin()),
                                         std::make_move_iterator(batch.end()));
                    }
                    int d = ++done;
                    fire(progress, {"vod_streams", d, total, c.name});
                }
            };
            const int kWorkers = 4;
            std::vector<std::thread> ts;
            for (int w = 0; w < kWorkers; ++w) ts.emplace_back(worker, w, kWorkers);
            for (auto& t : ts) t.join();
        }
        // Filtre fin au titre : écarte les films marqués VOSTxx dans leur nom
        // quand la langue VOST n'est pas cochée (cas serveurs où la catégorie
        // est neutre "VOD | FR - LATEST MOVIES" mais le titre porte [VOSTFR]).
        {
            auto before = allMovies.size();
            allMovies.erase(
                std::remove_if(allMovies.begin(), allMovies.end(),
                    [&](const Movie& m) {
                        return !itemTitleAllowedByVost(m.name, config.vostLanguages);
                    }),
                allMovies.end());
            auto filtered = before - allMovies.size();
            if (filtered > 0) {
                std::fprintf(stderr,
                    "[sync] %zu films VOSTxx écartés par filtre titre\n", filtered);
            }
        }
        cache_.saveMovies(rawFromMovies(allMovies), vodCatMap);
        result.moviesSaved = static_cast<int>(allMovies.size());
        int movies_ms = (int)std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - t_movies_start).count();
        std::fprintf(stderr,
            "[sync-timing] vod_cats=%d ms (%zu kept/%zu total)  movies=%d ms (%d films, %d cats, %d workers)\n",
            vod_cats_ms, keepVodCats.size(), vodCats.size(),
            movies_ms, result.moviesSaved, (int)keepVodCats.size(), 4);

        // 3) Series categories
        fire(progress, {"series_categories", 0, 1, {}});
        auto t_scats_start = std::chrono::steady_clock::now();
        auto serCats = client_.getSeriesCategories();
        fire(progress, {"series_categories", 1, 1, {}});
        if (aborted()) { result.error = "aborted"; return result; }

        std::map<std::string, std::string> serCatMap;
        for (const auto& c : serCats) serCatMap[c.id] = c.name;

        // 4) Séries — même filtrage tivimate-style que pour les films.
        std::vector<Category> keepSerCats;
        for (const auto& c : serCats) {
            if (!shouldKeep(c.id, config.selectedSeriesCategories)) continue;
            if (!matchesCategory(c.name, config.selectedLanguages,
                                 config.vostLanguages)) continue;
            keepSerCats.push_back(c);
        }
        cache_.saveSeriesCategories(rawFromCategories(keepSerCats));
        int ser_cats_ms = (int)std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - t_scats_start).count();

        auto t_series_start = std::chrono::steady_clock::now();
        std::vector<Series> allSeries;
        {
            const int total = (int)keepSerCats.size();
            std::atomic<int> done{0};
            std::mutex merge_mu;
            auto worker = [&](int start, int step) {
                for (int i = start; i < total; i += step) {
                    if (aborted()) return;
                    const auto& c = keepSerCats[i];
                    auto batch = client_.getSeries(c.id);
                    {
                        std::lock_guard<std::mutex> lk(merge_mu);
                        allSeries.insert(allSeries.end(),
                                         std::make_move_iterator(batch.begin()),
                                         std::make_move_iterator(batch.end()));
                    }
                    int d = ++done;
                    fire(progress, {"series", d, total, c.name});
                }
            };
            const int kWorkers = 4;
            std::vector<std::thread> ts;
            for (int w = 0; w < kWorkers; ++w) ts.emplace_back(worker, w, kWorkers);
            for (auto& t : ts) t.join();
        }
        // Même filtre fin au titre pour les séries (rare mais symétrique).
        {
            auto before = allSeries.size();
            allSeries.erase(
                std::remove_if(allSeries.begin(), allSeries.end(),
                    [&](const Series& s) {
                        return !itemTitleAllowedByVost(s.name, config.vostLanguages);
                    }),
                allSeries.end());
            auto filtered = before - allSeries.size();
            if (filtered > 0) {
                std::fprintf(stderr,
                    "[sync] %zu séries VOSTxx écartées par filtre titre\n", filtered);
            }
        }
        cache_.saveSeriesList(rawFromSeries(allSeries), serCatMap);
        result.seriesSaved = static_cast<int>(allSeries.size());
        int series_ms = (int)std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - t_series_start).count();
        std::fprintf(stderr,
            "[sync-timing] ser_cats=%d ms (%zu kept/%zu total)  series=%d ms (%d, %d cats)\n",
            ser_cats_ms, keepSerCats.size(), serCats.size(),
            series_ms, result.seriesSaved, (int)keepSerCats.size());

        cache_.setLastSyncDate();
        fire(progress, {"done", 1, 1, {}});
        result.ok = true;
        std::fprintf(stderr,
            "[sync-timing] total=%d ms movies=%d series=%d cats_vod=%zu cats_ser=%zu langs=%zu\n",
            elapsed_ms(), result.moviesSaved, result.seriesSaved,
            vodCats.size(), serCats.size(), config.selectedLanguages.size());
    } catch (const std::exception& e) {
        result.error = e.what();
        std::fprintf(stderr, "[sync] error: %s\n", e.what());
    }
    return result;
}

}  // namespace iptv::xtream

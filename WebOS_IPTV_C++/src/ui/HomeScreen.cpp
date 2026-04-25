#include "ui/HomeScreen.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <unordered_set>

#include <SDL2/SDL.h>
#include <SDL2/SDL_render.h>

#include "app/KeyCodes.h"
#include "store/Cache.h"
#include "store/Config.h"
#include "store/Favorites.h"
#include "store/WatchHistory.h"
#include "store/WatchPosition.h"
#include "ui/Badge.h"
#include "ui/Button.h"
#include "ui/ContentCard.h"
#include "ui/Draw.h"
#include "ui/FocusManager.h"
#include "ui/ImageLoader.h"
#include "ui/Sidebar.h"
#include "ui/Spinner.h"
#include "ui/TabBar.h"
#include "ui/TextRenderer.h"
#include "ui/Theme.h"
#include "ui/Toolbar.h"
#include "ui/VirtualKeyboard.h"

namespace iptv::ui {

namespace {
// Layout
constexpr int kCardW = theme::CardMovieWidth;
constexpr int kCardH = theme::CardMovieHeight;
constexpr int kCardGap = 26;
constexpr int kCarouselHeaderH = 54;
constexpr int kCarouselPadV = 20;
constexpr int kHeroPadX = 48;
constexpr int kHeroPadY = 28;
constexpr int kDebounceMs = 400;

// Extrait l'année depuis un nom "Film (2023)" ou "Film 2023".
int extractYear(const std::string& s) {
    int best = 0;
    const int n = (int)s.size();
    for (int i = 0; i + 4 <= n; ++i) {
        if (std::isdigit((unsigned char)s[i]) && std::isdigit((unsigned char)s[i+1]) &&
            std::isdigit((unsigned char)s[i+2]) && std::isdigit((unsigned char)s[i+3])) {
            int y = (s[i]-'0')*1000 + (s[i+1]-'0')*100 + (s[i+2]-'0')*10 + (s[i+3]-'0');
            if (y >= 1900 && y <= 2099) best = y;  // prend le dernier
        }
    }
    return best;
}

// Comparateur localCompare approximatif : case-insensitive ASCII + fallback bytewise.
int ciCompare(const std::string& a, const std::string& b) {
    size_t n = std::min(a.size(), b.size());
    for (size_t i = 0; i < n; ++i) {
        int ca = std::tolower((unsigned char)a[i]);
        int cb = std::tolower((unsigned char)b[i]);
        if (ca != cb) return ca - cb;
    }
    return (int)(a.size()) - (int)(b.size());
}
}  // namespace

int HomeScreen::extractYearFromName(const std::string& name) const {
    return extractYear(name);
}

HomeScreen::HomeScreen(TextRenderer& t, FocusManager& f, ImageLoader& il, store::Cache& c)
    : text_(t), focus_(f), images_(il), cache_(c) {
    toolbar_ = std::make_unique<Toolbar>(text_);
    tabbar_  = std::make_unique<TabBar>(text_);
    sidebar_ = std::make_unique<Sidebar>(text_);
    vkb_     = std::make_unique<VirtualKeyboard>(text_);

    // Toolbar callbacks
    toolbar_->setOnSettings([this]{ if (on_settings_) on_settings_(); });
    toolbar_->setOnSync([this]{ if (on_sync_) on_sync_(); });
    toolbar_->setOnOpenSearch([this]{
        vkb_->setMasked(false);
        vkb_->open(searchQuery_, "Rechercher\xE2\x80\xA6");
        vkb_open_ = true;
    });
    vkb_->setOnDone([this](const std::string& q){
        searchQuery_ = q;
        toolbar_->setQuery(q);
        vkb_open_ = false;
        rebuildRows();
        applySort();
    });
    vkb_->setOnCancel([this]{ vkb_open_ = false; });
    toolbar_->setOnFocusDown([this]{
        zone_ = Zone::TabBar;
        toolbar_->setFocused(false);
        tabbar_->setFocused(true);
        tabbar_->focusActive();
    });
    toolbar_->setOnFocusLeft([this]{ openSidebar(); });

    // TabBar callbacks
    tabbar_->setOnChange([this](TabId id){ switchTab(static_cast<Tab>(id)); });
    tabbar_->setOnFocusUp([this]{
        zone_ = Zone::Toolbar;
        tabbar_->setFocused(false);
        toolbar_->setFocused(true);
        toolbar_->focusFirst();
        // Quand le focus arrive sur la recherche depuis l'extérieur (pas un
        // retour de clavier virtuel), on vide le champ : ça annule le filtre
        // par nom et laisse l'utilisateur repartir sur une saisie fraîche.
        // Le cas "retour de VKB" ne passe pas ici (le zone reste Toolbar).
        if (!searchQuery_.empty()) {
            searchQuery_.clear();
            toolbar_->setQuery("");
            rebuildRows();
            applySort();
        }
    });
    tabbar_->setOnFocusDown([this]{
        zone_ = Zone::Carousel;
        tabbar_->setFocused(false);
        carousel_focus_ = 0;
    });
    tabbar_->setOnFocusLeft([this]{ openSidebar(); });

    // Sidebar callbacks
    sidebar_->setOnTabChange([this](int idx){
        switchTab(static_cast<Tab>(idx));
        closeSidebar();
    });
    sidebar_->setOnCategoryChange([this](const std::string& id){
        selectedCategoryId_ = id;
        rebuildRows();
        loadCategoriesForActiveTab();
        // Sélection de catégorie : focus immédiat sur la 1re vignette et
        // fermeture de la sidebar (comportement tivimate). On évite load()
        // qui tenterait de restaurer last_played_id_ hors catégorie.
        carousel_focus_ = 0;
        carousel_scroll_px_ = 0;
        last_focus_change_ticks_ = SDL_GetTicks();
        closeSidebar();
        zone_ = Zone::Carousel;
    });
    sidebar_->setOnSettings([this]{
        closeSidebar();
        if (on_settings_) on_settings_();
    });
    sidebar_->setOnCloseRight([this]{ closeSidebar(); });

    startVodWorker();
}

HomeScreen::~HomeScreen() { stopVodWorker(); releasePosterCache(); }

void HomeScreen::releasePosterCache() {
    for (auto& [url, tex] : poster_tex_) {
        if (tex) SDL_DestroyTexture(tex);
    }
    poster_tex_.clear();
    poster_requested_.clear();
}

void HomeScreen::setVodFetcher(VodDetailsFetcher f) {
    vod_fetcher_ = std::move(f);
}

void HomeScreen::openSidebar() {
    zone_ = Zone::Sidebar;
    tabbar_->setFocused(false);
    toolbar_->setFocused(false);
    sidebar_->setOpen(true);
    // Focus initial sur "Toutes les catégories" (idx 0 de la liste) : l'usage
    // le plus courant est de changer de catégorie, donc on économise un
    // aller-retour vers les tabs.
    sidebar_->focusToutesCategory();
}

void HomeScreen::closeSidebar() {
    sidebar_->setOpen(false);
    zone_ = Zone::Carousel;
}

void HomeScreen::switchTab(Tab t) {
    tab_ = t;
    tabbar_->setActive(static_cast<TabId>(t));
    sidebar_->setActiveTab(static_cast<int>(t));
    selectedCategoryId_.clear();
    sidebar_->setSelectedCategory("");
    loadCategoriesForActiveTab();
    rebuildRows();
    carousel_focus_ = 0;
    last_focus_change_ticks_ = SDL_GetTicks();
}

void HomeScreen::loadCategoriesForActiveTab() {
    auto snap = cache_.loadCatalog();
    const auto& rawCats = (tab_ == Tab::Series) ? snap.seriesCategories : snap.movieCategories;
    std::unordered_set<std::string> presentIds;
    if (tab_ == Tab::Series) {
        for (const auto& s : snap.series) presentIds.insert(s.category_id);
    } else if (tab_ == Tab::Movies) {
        for (const auto& m : snap.movies) presentIds.insert(m.category_id);
    }
    std::vector<SidebarCategory> cats;
    if (tab_ != Tab::Favorites) {
        for (const auto& c : rawCats) {
            if (presentIds.find(c.category_id) == presentIds.end()) continue;
            cats.push_back({c.category_id, c.category_name, 0});
        }
    }
    sidebar_->setCategories(cats);
}

std::vector<HomeScreen::Row> HomeScreen::fetchFavorites() const {
    std::vector<Row> v;
    auto favs = store::Favorites::all();
    for (const auto& m : favs["movies"]) {
        Row r;
        r.id = m.value("stream_id", std::string{});
        r.name = m.value("name", std::string{});
        r.poster_url = m.value("stream_icon", std::string{});
        r.container_extension = m.value("container_extension", std::string{"mkv"});
        r.is_series = false;
        r.is_favorite = true;
        if (!r.id.empty()) v.push_back(std::move(r));
    }
    for (const auto& s : favs["series"]) {
        Row r;
        r.id = s.value("series_id", std::string{});
        r.name = s.value("name", std::string{});
        r.poster_url = s.value("cover", std::string{});
        r.is_series = true;
        r.is_favorite = true;
        if (!r.id.empty()) v.push_back(std::move(r));
    }
    return v;
}

void HomeScreen::rebuildRows() {
    rows_.clear();
    auto cfg = store::Config::load();
    const bool frenchOnly = cfg.frenchOnly;
    auto passesCategory = [&](const std::string& id) {
        return selectedCategoryId_.empty() || id == selectedCategoryId_;
    };

    auto favSet = [&] {
        std::unordered_set<std::string> s;
        auto favs = store::Favorites::all();
        for (const auto& m : favs["movies"]) s.insert(m.value("stream_id", std::string{}));
        for (const auto& sr : favs["series"]) s.insert(sr.value("series_id", std::string{}));
        return s;
    }();

    if (tab_ == Tab::Favorites) {
        rows_ = fetchFavorites();
    } else {
        auto snap = cache_.loadCatalog();
        if (tab_ == Tab::Movies) {
            for (const auto& m : snap.movies) {
                if (frenchOnly && !m.is_french) continue;
                if (!passesCategory(m.category_id)) continue;
                Row r;
                r.id = m.stream_id;
                r.name = m.name;
                r.poster_url = m.stream_icon;
                r.category_id = m.category_id;
                r.container_extension = m.container_extension;
                r.rating = (float)m.rating;
                r.added = m.added;
                r.is_series = false;
                r.is_favorite = favSet.count(m.stream_id) > 0;
                rows_.push_back(std::move(r));
            }
        } else {  // Series
            for (const auto& s : snap.series) {
                if (frenchOnly && !s.is_french) continue;
                if (!passesCategory(s.category_id)) continue;
                Row r;
                r.id = s.series_id;
                r.name = s.name;
                r.poster_url = s.cover;
                r.series_cover = s.cover;
                r.category_id = s.category_id;
                r.rating = (float)s.rating;
                r.release_date = s.release_date;
                r.series_genre = s.genre;
                r.series_plot = s.plot;
                r.is_series = true;
                r.is_favorite = favSet.count(s.series_id) > 0;
                rows_.push_back(std::move(r));
            }
        }
    }

    // Filtre recherche (case-insensitive substring sur le nom).
    if (!searchQuery_.empty()) {
        std::string q = searchQuery_;
        for (char& c : q) c = (char)std::tolower((unsigned char)c);
        rows_.erase(std::remove_if(rows_.begin(), rows_.end(), [&](const Row& r){
            std::string n = r.name;
            for (char& c : n) c = (char)std::tolower((unsigned char)c);
            return n.find(q) == std::string::npos;
        }), rows_.end());
    }

    // Clamp focus si le filtre a réduit la liste.
    if (rows_.empty()) carousel_focus_ = 0;
    else if (carousel_focus_ >= (int)rows_.size()) carousel_focus_ = (int)rows_.size() - 1;

    applySort();

    // Maj compteurs TabBar/Sidebar. On recompte rapide : Favoris = fetchFavorites,
    // movies/series dans le catalogue.
    int nMovies = 0, nSeries = 0;
    auto snapCount = cache_.loadCatalog();
    for (const auto& m : snapCount.movies) if (!frenchOnly || m.is_french) ++nMovies;
    for (const auto& s : snapCount.series) if (!frenchOnly || s.is_french) ++nSeries;
    int nFavs = (int)fetchFavorites().size();
    tabbar_->setCounts(nMovies, nSeries, nFavs);
    sidebar_->setCounts(nMovies, nSeries, nFavs);
}

void HomeScreen::applySort() {
    if (sort_key_ == SortKey::None) return;
    const int f = (sort_dir_ == SortDir::Asc) ? 1 : -1;
    if (sort_key_ == SortKey::Alpha) {
        std::sort(rows_.begin(), rows_.end(), [f](const Row& a, const Row& b){
            return f * ciCompare(a.name, b.name) < 0;
        });
    } else if (sort_key_ == SortKey::Score) {
        // Items sans note (rating <= 0) toujours en fin, quel que soit le
        // sens du tri. Stable pour garder l'ordre relatif des ex-aequo.
        std::stable_sort(rows_.begin(), rows_.end(), [f](const Row& a, const Row& b){
            bool ha = a.rating > 0, hb = b.rating > 0;
            if (ha != hb) return ha;   // "a a l'info" passe devant
            if (!ha) return false;     // deux sans info : stable
            return f * ((a.rating < b.rating) ? -1 : (a.rating > b.rating) ? 1 : 0) < 0;
        });
    } else if (sort_key_ == SortKey::Date) {
        auto dateOf = [](const Row& r) {
            // release_date prioritaire ("YYYY..."), sinon année du nom, sinon added (ts)
            if (!r.release_date.empty()) {
                int y = 0, n = 0;
                for (char c : r.release_date) {
                    if (std::isdigit((unsigned char)c)) {
                        y = y*10 + (c-'0');
                        if (++n == 4) break;
                    } else if (n > 0) break;  // stop after first digit run
                }
                if (y > 0) return y;
            }
            int y = extractYear(r.name);
            if (y > 0) return y;
            return (int)std::strtol(r.added.c_str(), nullptr, 10);
        };
        // Items sans date (dateOf == 0) toujours en fin, quel que soit le sens.
        std::stable_sort(rows_.begin(), rows_.end(), [&](const Row& a, const Row& b){
            int da = dateOf(a), db = dateOf(b);
            bool ha = da > 0, hb = db > 0;
            if (ha != hb) return ha;
            if (!ha) return false;
            return f * (da - db) < 0;
        });
    }
}

void HomeScreen::load() {
    rebuildRows();
    // Restaure focus sur dernier item joué.
    if (!last_played_id_.empty()) {
        for (size_t i = 0; i < rows_.size(); ++i) {
            if (rows_[i].id == last_played_id_) { carousel_focus_ = (int)i; break; }
        }
    }
    auto lw = store::WatchHistory::getLastWatchedSeries();
    if (lw && !lw->seriesId.empty()) {
        resume_.valid = true;
        resume_.label = std::string("> Reprendre : ") + lw->seriesName +
                        " - " + lw->episodeTitle;
        resume_.seriesId  = lw->seriesId;
        resume_.episodeId = lw->episodeId;
    } else {
        resume_.valid = false;
    }
    loadCategoriesForActiveTab();
    zone_ = Zone::Carousel;
    last_focus_change_ticks_ = SDL_GetTicks();
    if (carousel_focus_ >= (int)rows_.size()) carousel_focus_ = 0;
}

VodDetails HomeScreen::getCachedDetails(const std::string& id) const {
    std::lock_guard<std::mutex> g(vod_cache_mu_);
    auto it = vod_cache_.find(id);
    if (it != vod_cache_.end()) return it->second;
    return VodDetails{};
}

VodDetails HomeScreen::detailsForFocused() const {
    if (rows_.empty() || carousel_focus_ < 0 || carousel_focus_ >= (int)rows_.size()) return {};
    const auto& r = rows_[carousel_focus_];
    if (r.is_series) {
        // Métadonnées directement depuis la row.
        VodDetails d;
        d.plot = r.series_plot;
        d.genre = r.series_genre;
        d.release_date = r.release_date;
        d.backdrop_url = r.series_cover;
        d.rating = r.rating;
        d.loaded = true;
        return d;
    }
    return getCachedDetails(r.id);
}

void HomeScreen::requestVodDetails(const std::string& id) {
    if (id.empty()) return;
    {
        std::lock_guard<std::mutex> g(vod_cache_mu_);
        if (vod_cache_.find(id) != vod_cache_.end()) return;  // déjà en cache
    }
    std::lock_guard<std::mutex> g(vod_queue_mu_);
    // Remplace toute requête pending par celle-ci — on ne veut que la dernière.
    vod_queue_.clear();
    vod_queue_.push_back(id);
    vod_queue_cv_.notify_one();
}

void HomeScreen::startVodWorker() {
    vod_worker_ = std::thread([this]{
        while (!vod_worker_stop_.load()) {
            std::string id;
            {
                std::unique_lock<std::mutex> lk(vod_queue_mu_);
                vod_queue_cv_.wait(lk, [this]{
                    return vod_worker_stop_.load() || !vod_queue_.empty();
                });
                if (vod_worker_stop_.load()) return;
                id = vod_queue_.front();
                vod_queue_.pop_front();
            }
            if (!vod_fetcher_) continue;
            VodDetails d;
            try {
                d = vod_fetcher_(id);
            } catch (...) {
                d = VodDetails{};
            }
            d.loaded = true;
            {
                std::lock_guard<std::mutex> g(vod_cache_mu_);
                vod_cache_[id] = d;
            }
        }
    });
}

void HomeScreen::stopVodWorker() {
    vod_worker_stop_.store(true);
    vod_queue_cv_.notify_all();
    if (vod_worker_.joinable()) vod_worker_.join();
}

void HomeScreen::toggleFavoriteFocused() {
    if (rows_.empty()) return;
    const Row& r = rows_[carousel_focus_];
    if (tab_ == Tab::Favorites) {
        // Ouvrir confirm modal
        fav_confirm_open_ = true;
        fav_confirm_btn_idx_ = 0;
        fav_confirm_item_ = r;
        return;
    }
    // Films / Séries : toggle direct. Reconstruit un item JSON minimal
    // suffisant pour le service (qui garde tout le blob tel quel).
    nlohmann::json item;
    if (r.is_series) {
        item["series_id"]   = r.id;
        item["name"]        = r.name;
        item["cover"]       = r.poster_url;
    } else {
        item["stream_id"]          = r.id;
        item["name"]               = r.name;
        item["stream_icon"]        = r.poster_url;
        item["container_extension"]= r.container_extension;
    }
    store::Favorites::toggle(item,
        r.is_series ? store::FavoriteKind::Series : store::FavoriteKind::Movie);
    rebuildRows();
    if (carousel_focus_ >= (int)rows_.size()) carousel_focus_ = (int)rows_.size() - 1;
    if (carousel_focus_ < 0) carousel_focus_ = 0;
}

void HomeScreen::confirmRemoveFavorite(bool confirm) {
    if (confirm) {
        store::Favorites::remove(fav_confirm_item_.id,
            fav_confirm_item_.is_series ? store::FavoriteKind::Series
                                        : store::FavoriteKind::Movie);
        rebuildRows();
        if (carousel_focus_ >= (int)rows_.size()) carousel_focus_ = (int)rows_.size() - 1;
        if (carousel_focus_ < 0) carousel_focus_ = 0;
    }
    fav_confirm_open_ = false;
}

void HomeScreen::handleKey(int code, bool& handled) {
    handled = true;

    // Virtual keyboard overlay : capte tout tant qu'il est ouvert.
    if (vkb_open_ && vkb_) {
        if (vkb_->handleKey(code)) return;
        if (!vkb_->isOpen()) vkb_open_ = false;  // fermé par onCancel/onDone
        return;
    }

    // Debug : 1/2/3 pour tests décodeurs.
    if (code == app::KEY::NUM_1 || code == app::KEY::NUM_2 || code == app::KEY::NUM_3) {
        const char* file =
            (code == app::KEY::NUM_1) ? "assets/test_asp.mkv" :
            (code == app::KEY::NUM_2) ? "assets/test_h264.mkv" :
                                         "assets/test_h264.mkv";
        char* base = SDL_GetBasePath();
        std::string path = base ? (std::string(base) + file) : "";
        if (base) SDL_free(base);
        const char* prefix = (code == app::KEY::NUM_3) ? "NDL:" : "LOCAL:";
        if (on_movie_ && !path.empty()) on_movie_(std::string(prefix) + path);
        return;
    }

    // Modal fav confirm : prend tout
    if (fav_confirm_open_) {
        if (code == app::KEY::LEFT || code == app::KEY::RIGHT) {
            fav_confirm_btn_idx_ = (fav_confirm_btn_idx_ == 0) ? 1 : 0;
            return;
        }
        if (app::isOkKey(code)) { confirmRemoveFavorite(fav_confirm_btn_idx_ == 1); return; }
        if (app::isBackKey(code)) { fav_confirm_open_ = false; return; }
        return;
    }

    if (zone_ == Zone::Sidebar) {
        int k = 0;
        if (code == app::KEY::UP)    k = SDLK_UP;
        else if (code == app::KEY::DOWN)  k = SDLK_DOWN;
        else if (code == app::KEY::LEFT)  k = SDLK_LEFT;
        else if (code == app::KEY::RIGHT) k = SDLK_RIGHT;
        else if (app::isOkKey(code))      k = SDLK_RETURN;
        else if (app::isBackKey(code))    { closeSidebar(); return; }
        if (k) sidebar_->handleKey(k);
        return;
    }

    if (zone_ == Zone::Toolbar) {
        int k = 0;
        if (code == app::KEY::DOWN)  k = SDLK_DOWN;
        else if (code == app::KEY::LEFT)  k = SDLK_LEFT;
        else if (code == app::KEY::RIGHT) k = SDLK_RIGHT;
        else if (app::isOkKey(code))      k = SDLK_RETURN;
        else if (app::isBackKey(code))    { zone_ = Zone::Carousel; toolbar_->setFocused(false); return; }
        if (k) toolbar_->handleKey(k);
        return;
    }

    if (zone_ == Zone::TabBar) {
        int k = 0;
        if (code == app::KEY::UP)    k = SDLK_UP;
        else if (code == app::KEY::DOWN)  k = SDLK_DOWN;
        else if (code == app::KEY::LEFT)  k = SDLK_LEFT;
        else if (code == app::KEY::RIGHT) k = SDLK_RIGHT;
        else if (app::isOkKey(code))      k = SDLK_RETURN;
        else if (app::isBackKey(code))    { zone_ = Zone::Carousel; tabbar_->setFocused(false); return; }
        if (k) tabbar_->handleKey(k);
        return;
    }

    if (zone_ == Zone::Sort) {
        if (code == app::KEY::LEFT)  {
            if (sort_focus_ == 0) { openSidebar(); return; }
            sort_focus_--;
            return;
        }
        if (code == app::KEY::RIGHT) { if (sort_focus_ < 2) sort_focus_++; return; }
        if (code == app::KEY::UP) {
            zone_ = Zone::TabBar;
            tabbar_->setFocused(true);
            tabbar_->focusActive();
            return;
        }
        if (code == app::KEY::DOWN) { zone_ = Zone::Carousel; return; }
        if (app::isOkKey(code)) {
            // Cycle : none → desc → asc → none
            SortKey newKey = (sort_focus_ == 0) ? SortKey::Alpha :
                             (sort_focus_ == 1) ? SortKey::Score : SortKey::Date;
            if (sort_key_ != newKey) {
                sort_key_ = newKey;
                sort_dir_ = SortDir::Desc;
            } else if (sort_dir_ == SortDir::Desc) {
                sort_dir_ = SortDir::Asc;
            } else {
                sort_key_ = SortKey::None;
            }
            rebuildRows();
            carousel_focus_ = 0;
            return;
        }
        if (app::isBackKey(code)) { zone_ = Zone::Carousel; return; }
        return;
    }

    // Zone::Carousel
    if (rows_.empty()) {
        if (code == app::KEY::UP) { zone_ = Zone::Sort; return; }
        if (code == app::KEY::LEFT) { openSidebar(); return; }
        if (app::isBackKey(code)) { handled = false; return; }
        return;
    }
    if (code == app::KEY::LEFT) {
        if (carousel_focus_ == 0) { openSidebar(); return; }
        carousel_focus_--;
        last_focus_change_ticks_ = SDL_GetTicks();
        return;
    }
    if (code == app::KEY::RIGHT) {
        if (carousel_focus_ + 1 < (int)rows_.size()) {
            carousel_focus_++;
            last_focus_change_ticks_ = SDL_GetTicks();
        }
        return;
    }
    if (code == app::KEY::UP)    { zone_ = Zone::Sort; return; }
    if (code == app::KEY::DOWN)  { toggleFavoriteFocused(); return; }
    if (app::isOkKey(code)) {
        const Row& r = rows_[carousel_focus_];
        last_played_id_ = r.id;
        if (r.is_series) {
            if (on_series_) on_series_(r.id);
        } else {
            if (on_movie_) on_movie_(r.id);
        }
        return;
    }
    if (app::isBackKey(code)) { handled = false; return; }
}

int HomeScreen::renderHero(SDL_Renderer* r, int x, int y, int w, int h) {
    SDL_Rect bg{x, y, w, h};
    const VodDetails d = detailsForFocused();
    const Row empty{};
    const Row& row = rows_.empty() ? empty : rows_[std::min(carousel_focus_, (int)rows_.size()-1)];

    // Fond : backdrop simulé par gradient coloré issu du hash du titre.
    uint32_t seed = 0;
    for (char c : row.name) seed = seed * 131 + (uint8_t)c;
    uint8_t hr = 20 + (seed & 0x3f);
    uint8_t hg = 10 + ((seed >> 6) & 0x3f);
    uint8_t hb = 30 + ((seed >> 12) & 0x5f);
    draw::fillGradientV(r, bg,
        {hr, hg, (uint8_t)(hb + 20), 255},
        {(uint8_t)(hr / 2), (uint8_t)(hg / 2), (uint8_t)(hb / 2), 255});

    // Gradient gauche→droite pour lisibilité texte : on utilise des bandes
    // larges (20 bandes) plutôt que pixel-par-pixel pour éviter des centaines
    // de draw calls par frame qui faisaient saccader pendant le scroll.
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    constexpr int kBands = 20;
    int bandW = (w + kBands - 1) / kBands;
    for (int b = 0; b < kBands; ++b) {
        float t = (float)b / (float)(kBands - 1);
        float alpha = 0.98f - t * 0.90f;
        if (alpha < 0.08f) alpha = 0.08f;
        SDL_SetRenderDrawColor(r, 0x0a, 0x0a, 0x10, (uint8_t)(alpha * 255));
        SDL_Rect strip{x + b * bandW, y, bandW, h};
        SDL_RenderFillRect(r, &strip);
    }
    // Fondu bas vers le carrousel : pareil, 10 bandes larges au lieu de 60.
    constexpr int kFadeBands = 10;
    int fadeBandH = 60 / kFadeBands;
    for (int i = 0; i < kFadeBands; ++i) {
        uint8_t a = (uint8_t)((i + 1) * 255 / kFadeBands);
        SDL_SetRenderDrawColor(r, 0x14, 0x14, 0x14, a);
        SDL_Rect strip{x, y + h - 60 + i * fadeBandH, w, fadeBandH};
        SDL_RenderFillRect(r, &strip);
    }

    // Texte infos — tivimate : title 1.9rem (~30px) Bold avec text-shadow,
    // meta avec séparateurs "·", réalisateur/acteurs en XS 55% white.
    // Layout strict : colonne gauche 40% (titre/meta/casting), colonne droite
    // 60% (synopsis). Le titre est ellipsé pour ne pas déborder.
    int leftX = x + kHeroPadX;
    int ty = y + kHeroPadY;
    const int leftColW = (int)(w * 0.40f) - kHeroPadX - 16;  // marge avant col droite
    const std::string title = row.name;
    // Titre : police LgBold (32 px) — réduit de XlBold (40 px). Wrap sur
    // 2 lignes max si débordement, ellipsis sur la 2e ligne si toujours
    // trop long.
    const auto titleStyle = theme::FontStyle::LgBold;
    {
        int tw = 0, th = 0;
        text_.measure(titleStyle, title, tw, th);
        auto drawLineShadow = [&](const std::string& s, int yPos) {
            text_.drawEllipsis(titleStyle, s, leftX + 2, yPos + 2,
                               leftColW, SDL_Color{0, 0, 0, 200});
            text_.drawEllipsis(titleStyle, s, leftX, yPos,
                               leftColW, theme::TextPrimary);
        };
        if (tw <= leftColW) {
            drawLineShadow(title, ty);
            ty += text_.lineHeight(titleStyle) + 6;
        } else {
            // Cherche le dernier espace dont la sous-chaîne à gauche tient.
            size_t splitAt = std::string::npos;
            for (size_t i = 0; i < title.size(); ++i) {
                if (title[i] == ' ') {
                    int w = 0, h = 0;
                    text_.measure(titleStyle, title.substr(0, i), w, h);
                    if (w <= leftColW) splitAt = i;
                    else break;
                }
            }
            std::string line1 = (splitAt == std::string::npos)
                ? title : title.substr(0, splitAt);
            std::string line2 = (splitAt == std::string::npos)
                ? std::string() : title.substr(splitAt + 1);
            drawLineShadow(line1, ty);
            ty += text_.lineHeight(titleStyle) + 2;
            if (!line2.empty()) drawLineShadow(line2, ty);
            ty += text_.lineHeight(titleStyle) + 6;
        }
    }

    // Meta : rating (gold) · year (white 65%) · genre (white 65%)
    int year = 0;
    if (!d.release_date.empty()) {
        int n = 0;
        for (char c : d.release_date) {
            if (std::isdigit((unsigned char)c)) {
                year = year * 10 + (c-'0');
                if (++n == 4) break;
            } else if (n > 0) break;
        }
    }
    if (year == 0) year = extractYearFromName(title);
    int mx = leftX;
    const int sepGap = 8;
    const SDL_Color sepColor = theme::withAlpha(theme::TextPrimary, 76);  // rgba 30%
    const SDL_Color metaColor = theme::withAlpha(theme::TextPrimary, 166); // rgba 65%
    auto drawMetaPart = [&](const std::string& s, SDL_Color c, bool first) {
        if (!first) {
            // sep
            int sw = 0, sh = 0; text_.measure(theme::FontStyle::SmBold, "·", sw, sh);
            text_.draw(theme::FontStyle::SmBold, "·",
                       mx + sepGap, ty, sepColor);
            mx += sepGap + sw + sepGap;
        }
        int tw = 0, th = 0;
        text_.measure(theme::FontStyle::SmBold, s, tw, th);
        text_.draw(theme::FontStyle::SmBold, s, mx, ty, c);
        mx += tw;
    };
    bool firstMeta = true;
    if (row.rating > 0) {
        char buf[32]; std::snprintf(buf, sizeof(buf), "\xE2\x98\x85 %.1f", row.rating);
        drawMetaPart(buf, theme::Gold, firstMeta); firstMeta = false;
    }
    if (year > 0) { drawMetaPart(std::to_string(year), metaColor, firstMeta); firstMeta = false; }
    if (!d.genre.empty()) { drawMetaPart(d.genre, metaColor, firstMeta); firstMeta = false; }
    ty += text_.lineHeight(theme::FontStyle::SmBold) + 14;

    const SDL_Color labelColor = theme::withAlpha(theme::TextPrimary, 90);
    const SDL_Color valueColor = theme::withAlpha(theme::TextPrimary, 140);
    if (!d.director.empty()) {
        int lw = 0, lh = 0;
        text_.measure(theme::FontStyle::XsRegular, "Réalisateur : ", lw, lh);
        text_.draw(theme::FontStyle::XsRegular, "Réalisateur : ", leftX, ty, labelColor);
        text_.drawEllipsis(theme::FontStyle::XsRegular, d.director,
                           leftX + lw, ty,
                           leftColW - lw, valueColor);
        ty += text_.lineHeight(theme::FontStyle::XsRegular) + 2;
    }
    if (!d.cast.empty()) {
        int lw = 0, lh = 0;
        text_.measure(theme::FontStyle::XsRegular, "Acteurs : ", lw, lh);
        text_.draw(theme::FontStyle::XsRegular, "Acteurs : ", leftX, ty, labelColor);
        text_.drawEllipsis(theme::FontStyle::XsRegular, d.cast,
                           leftX + lw, ty,
                           leftColW - lw, valueColor);
        ty += text_.lineHeight(theme::FontStyle::XsRegular) + 2;
    }

    // Synopsis à droite (60%) — wrap mot-à-mot avec mesure exacte.
    int rightX = x + (int)(w * 0.40f);
    int rightW = w - (int)(w * 0.40f) - kHeroPadX;
    int py = y + kHeroPadY + 8;
    const std::string& plot = d.plot;
    if (!plot.empty()) {
        std::string s = plot;
        // Clamp visuel : 9 lignes max (était 5). Dernière tronquée avec "…"
        // si le synopsis dépasse. Respecte aussi la hauteur de la zone Hero.
        const int kMaxLines = 9;
        int linesDrawn = 0;
        auto flushLine = [&](const std::string& line) {
            text_.draw(theme::FontStyle::SmRegular, line, rightX, py,
                       theme::withAlpha(theme::TextPrimary, 210));
            py += text_.lineHeight(theme::FontStyle::SmRegular) + 4;
            ++linesDrawn;
        };
        std::string line;
        std::string word;
        auto fits = [&](const std::string& s_) {
            int tw = 0, th = 0;
            text_.measure(theme::FontStyle::SmRegular, s_, tw, th);
            return tw <= rightW;
        };
        bool truncated = false;
        size_t i = 0;
        while (i <= s.size() && py < y + h - 60 && linesDrawn < kMaxLines) {
            char c = (i == s.size()) ? ' ' : s[i];
            if (c == ' ' || c == '\n') {
                if (!word.empty()) {
                    std::string candidate = line.empty() ? word : (line + " " + word);
                    if (fits(candidate)) {
                        line = candidate;
                    } else {
                        if (!line.empty()) flushLine(line);
                        line = word;
                        if (linesDrawn >= kMaxLines) { truncated = true; break; }
                    }
                    word.clear();
                }
                if (c == '\n' && !line.empty()) { flushLine(line); line.clear(); }
                if (i == s.size()) break;
            } else {
                word += c;
            }
            ++i;
        }
        if (!line.empty() && linesDrawn < kMaxLines && py < y + h - 60) {
            // Si on n'a pas consommé tout le texte, ajouter "…" à la dernière
            // ligne pour signaler la troncature visuelle.
            if (i < s.size() || !word.empty()) {
                std::string withEllipsis = line;
                // ellipse UTF-8 …
                while (!withEllipsis.empty() &&
                       !fits(withEllipsis + "\xE2\x80\xA6")) {
                    withEllipsis.pop_back();
                }
                withEllipsis += "\xE2\x80\xA6";
                text_.draw(theme::FontStyle::SmRegular, withEllipsis, rightX, py,
                           theme::withAlpha(theme::TextPrimary, 210));
            } else {
                flushLine(line);
            }
        } else if (truncated) {
            // Une ligne pleine déjà dessinée a été le flush ; on dessine un "…"
            // à la position courante pour indiquer la suite.
            text_.draw(theme::FontStyle::SmRegular, "\xE2\x80\xA6", rightX, py,
                       theme::withAlpha(theme::TextPrimary, 210));
        }
    } else if (!row.is_series && !d.loaded) {
        text_.draw(theme::FontStyle::SmRegular, "Chargement…", rightX, py,
                   theme::withAlpha(theme::TextPrimary, 150));
    }
    return h;
}

int HomeScreen::renderCarousel(SDL_Renderer* r, int x, int y, int w, int h) {
    SDL_Rect bg{x, y, w, h};
    draw::fillRect(r, bg, theme::BgPrimary);

    // Header : label | sort buttons | counter
    int headerY = y + 10;
    const char* catLabel =
        selectedCategoryId_.empty()
            ? ((tab_ == Tab::Series) ? "Toutes les séries"
              : (tab_ == Tab::Favorites) ? "Favoris"
                                         : "Tous les films")
            : "Catégorie sélectionnée";
    text_.draw(theme::FontStyle::SmBold, catLabel,
               x + 48,
               headerY + (kCarouselHeaderH - text_.lineHeight(theme::FontStyle::SmBold)) / 2,
               theme::TextPrimary);

    // Sort buttons au centre
    const char* sortLabels[3] = {"A - Z", "* Score", "# Date"};
    int widths[3] = {0};
    int bh = 0;
    for (int i = 0; i < 3; ++i) {
        int tw = 0, th = 0;
        text_.measure(theme::FontStyle::XsBold, sortLabels[i], tw, th);
        widths[i] = tw + 26;
        if (th + 10 > bh) bh = th + 10;
    }
    int gap = 8;
    int total = widths[0] + widths[1] + widths[2] + gap * 2;
    int sx = x + w / 2 - total / 2;
    int sy = headerY + (kCarouselHeaderH - bh) / 2;
    for (int i = 0; i < 3; ++i) {
        SDL_Rect rect{sx, sy, widths[i], bh};
        SortKey k = (i == 0) ? SortKey::Alpha : (i == 1) ? SortKey::Score : SortKey::Date;
        bool active = (sort_key_ == k);
        bool focus  = (zone_ == Zone::Sort && sort_focus_ == i);
        SDL_Color bgc = active ? SDL_Color{0x4a, 0x9e, 0xff, 56}
                               : SDL_Color{0x4a, 0x9e, 0xff, 13};
        SDL_Color border = active ? SDL_Color{0x4a, 0x9e, 0xff, 229}
                                  : SDL_Color{0x4a, 0x9e, 0xff, 77};
        SDL_Color fg = active ? theme::TextPrimary
                              : SDL_Color{0x4a, 0x9e, 0xff, 166};
        draw::fillRoundedRect(r, rect, rect.h / 2, bgc);
        draw::strokeRoundedRect(r, rect, rect.h / 2, 2, border);
        if (focus) draw::focusRing(r, rect, rect.h / 2, theme::Accent, 2, 2);
        std::string lbl = sortLabels[i];
        if (active) lbl += (sort_dir_ == SortDir::Asc) ? " ^" : " v";
        int tw = 0, th = 0;
        text_.measure(theme::FontStyle::XsBold, lbl, tw, th);
        text_.draw(theme::FontStyle::XsBold, lbl,
                   rect.x + (rect.w - tw) / 2,
                   rect.y + (rect.h - th) / 2, fg);
        sx += widths[i] + gap;
    }

    // Counter à droite
    char counter[40];
    std::snprintf(counter, sizeof(counter), "%d / %zu",
                  rows_.empty() ? 0 : carousel_focus_ + 1, rows_.size());
    int cw = 0, ch = 0;
    text_.measure(theme::FontStyle::XsRegular, counter, cw, ch);
    text_.draw(theme::FontStyle::XsRegular, counter,
               x + w - 48 - cw,
               headerY + (kCarouselHeaderH - ch) / 2,
               theme::TextSecondary);

    // Track : row horizontale de cartes + scroll
    int trackY = y + 10 + kCarouselHeaderH + kCarouselPadV;
    int viewLeft = x + 48;
    int viewRight = x + w - 48;
    int viewW = viewRight - viewLeft;

    int focusCenterX = carousel_focus_ * (kCardW + kCardGap) + kCardW / 2;
    int centerView = viewW / 2;
    int targetScroll = 0;
    if (focusCenterX > centerView) targetScroll = focusCenterX - centerView;
    // Ease-out doux vers la cible avec cap de vitesse : évite la saccade
    // quand on enchaîne plusieurs RIGHT d'affilée (gros delta → gros saut).
    // Gain 1/6 : plus lisse que 1/3 sans traîner (≈10 frames pour couvrir
    // un gap de 300 px). Clamp ±60 px/frame (≈3600 px/s à 60 fps) borne le
    // pic de vitesse sur de très grands sauts (tri refait, saut de tab…).
    int delta = targetScroll - carousel_scroll_px_;
    int step  = delta / 6;
    constexpr int kMaxStep = 60;
    if (step >  kMaxStep) step =  kMaxStep;
    if (step < -kMaxStep) step = -kMaxStep;
    if (step == 0 && delta != 0) step = (delta > 0) ? 1 : -1;  // évite stall
    carousel_scroll_px_ += step;
    if (std::abs(targetScroll - carousel_scroll_px_) <= 1) carousel_scroll_px_ = targetScroll;

    if (rows_.empty()) {
        text_.draw(theme::FontStyle::MdRegular,
                   "Aucun contenu disponible.  Lancez une synchronisation depuis la barre du haut.",
                   viewLeft, trackY + kCardH / 2,
                   theme::TextSecondary);
        return h;
    }

    int x0 = viewLeft - carousel_scroll_px_;
    for (size_t i = 0; i < rows_.size(); ++i) {
        SDL_Rect rect{x0 + (int)i * (kCardW + kCardGap), trackY, kCardW, kCardH};
        if (rect.x + kCardW < x || rect.x > x + w) continue;
        bool isF = (zone_ == Zone::Carousel) && ((int)i == carousel_focus_);
        ContentItem it;
        it.id = rows_[i].id;
        it.title = rows_[i].name;
        it.posterUrl = rows_[i].poster_url;
        it.rating = rows_[i].rating;
        it.isFavorite = rows_[i].is_favorite;
        it.type = rows_[i].is_series ? ContentType::Series : ContentType::Movie;

        // Poster : enqueue si pas encore demandé, lire le cache.
        SDL_Texture* poster = nullptr;
        const std::string& url = rows_[i].poster_url;
        if (!url.empty()) {
            auto hit = poster_tex_.find(url);
            if (hit != poster_tex_.end()) {
                poster = hit->second;
            } else if (poster_requested_.insert(url).second) {
                images_.request(url, [this, url](SDL_Texture* tex, int, int) {
                    poster_tex_[url] = tex;  // tex peut être nul en cas d'échec
                });
            }
        }
        drawContentCard(r, text_, poster, rect, it, isF);
    }
    return h;
}

void HomeScreen::render(SDL_Renderer* r, int winW, int winH) {
    // Débounce requête VodInfo : 400 ms après dernière transition de focus.
    uint32_t now = SDL_GetTicks();
    if (!rows_.empty() && carousel_focus_ < (int)rows_.size()) {
        const Row& rowF = rows_[carousel_focus_];
        if (!rowF.is_series && now - last_focus_change_ticks_ > kDebounceMs) {
            requestVodDetails(rowF.id);
        }
    }

    // Fond global (sera recouvert par Hero / Carousel)
    draw::fillRect(r, {0, 0, winW, winH}, theme::BgPrimary);

    // Toolbar
    toolbar_->setQuery(searchQuery_);
    toolbar_->setSyncing(syncing_);
    toolbar_->setFocused(zone_ == Zone::Toolbar);
    int toolbarH = toolbar_->render(r, 0, 0, winW);

    // TabBar
    int tabY = toolbarH;
    tabbar_->setFocused(zone_ == Zone::TabBar);
    int tabH = tabbar_->render(r, 0, tabY, winW);

    // Resume band si présent (au-dessus du Hero). Désactivé pour l'instant :
    // tivimate ne l'affiche plus dans le nouveau layout. On le remplace par
    // une pastille dans le Hero si focusé sur la série correspondante.
    // (kept simple: on le dessine si focus=Carousel && rows vide, peu utile)

    // Hero + Carousel — tivimate : carousel hauteur fixe (contenu card), hero prend le reste.
    int contentY = tabY + tabH;
    int contentH = winH - contentY;
    // Carousel : header (header H + padding) + track (padding V + card H + padding V).
    int carouselH = kCarouselHeaderH + 20 + kCardH + 20 + 10;
    int heroH = contentH - carouselH;
    if (heroH < 220) { heroH = 220; carouselH = contentH - heroH; }
    renderHero(r, 0, contentY, winW, heroH);
    renderCarousel(r, 0, contentY + heroH, winW, carouselH);

    // Sidebar overlay
    sidebar_->render(r, winW, winH, SDL_GetTicks());

    // Modal fav confirm
    if (fav_confirm_open_) {
        draw::fillRect(r, {0, 0, winW, winH}, theme::BgOverlay);
        const int pw = 720, ph = 240;
        SDL_Rect panel{(winW - pw) / 2, (winH - ph) / 2, pw, ph};
        draw::fillRoundedRect(r, panel, theme::RadiusLg, theme::SurfaceModal);
        draw::strokeRoundedRect(r, panel, theme::RadiusLg, 1, theme::Border);
        std::string msg = "Retirer " + fav_confirm_item_.name + " des favoris ?";
        text_.drawEllipsis(theme::FontStyle::MdBold, msg,
                           panel.x + 32, panel.y + 40, panel.w - 64, theme::TextPrimary);
        // Boutons Annuler / Supprimer
        ButtonStyle sA{ButtonVariant::Secondary, theme::FontStyle::MdBold};
        ButtonStyle sD{ButtonVariant::Danger,    theme::FontStyle::MdBold};
        int by = panel.y + panel.h - 80;
        int bx = panel.x + 32;
        SDL_Rect r1 = drawButton(r, text_, bx, by, "Annuler",   fav_confirm_btn_idx_ == 0, sA);
        drawButton(r, text_, bx + r1.w + 16, by, "Supprimer", fav_confirm_btn_idx_ == 1, sD);
    }

    // VKB overlay (recherche) par-dessus tout.
    if (vkb_ && vkb_->isOpen()) {
        vkb_->render(r, winW, winH);
    }
}

}  // namespace iptv::ui

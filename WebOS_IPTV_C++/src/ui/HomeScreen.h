#pragma once
// HomeScreen — layout style tivimate (dernière version) :
//   Toolbar (top) + TabBar + Hero (56%) + Carrousel horizontal unique (44%)
// + Sidebar slide-in overlay en option.
//
// Le Hero affiche les métadonnées enrichies de l'item focusé dans le
// carrousel (backdrop, plot, genre, rating, director, cast). Pour les
// films, getVodInfo() est appelé en asynchrone via un worker debounced
// (400 ms) et cache mémoire ; pour les séries, les métadonnées sont
// déjà dans le catalogue.

#include <atomic>
#include <condition_variable>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

struct SDL_Renderer;
struct SDL_Texture;

namespace iptv::store { class Cache; }

namespace iptv::ui {

class FocusManager;
class ImageLoader;
class TextRenderer;
class Toolbar;
class TabBar;
class Sidebar;
class VirtualKeyboard;

// Métadonnées enrichies (remplie via getVodInfo pour films, ou depuis cache pour séries).
struct VodDetails {
    std::string plot;
    std::string genre;
    std::string release_date;   // "YYYY-MM-DD" ou année seule
    std::string cast;
    std::string director;
    std::string backdrop_url;
    float rating = -1.0f;
    bool loaded = false;
};

using VodDetailsFetcher = std::function<VodDetails(const std::string& streamId)>;

class HomeScreen {
public:
    HomeScreen(TextRenderer& text, FocusManager& focus, ImageLoader& images,
               store::Cache& cache);
    ~HomeScreen();

    enum class Tab { Movies, Series, Favorites };

    void load();
    void handleKey(int code, bool& handled);
    void render(SDL_Renderer* r, int winW, int winH);

    void setOnOpenMovie(std::function<void(const std::string& streamId)> cb)  { on_movie_ = std::move(cb); }
    void setOnOpenSeries(std::function<void(const std::string& seriesId)> cb) { on_series_ = std::move(cb); }
    void setOnOpenSettings(std::function<void()> cb) { on_settings_ = std::move(cb); }
    void setOnSync(std::function<void()> cb) { on_sync_ = std::move(cb); }
    void setSyncing(bool s) { syncing_ = s; }

    // Fetcher asynchrone pour enrichir les films. Appelé dans un thread worker ;
    // peut bloquer sur une requête HTTP. Retourne VodDetails{.loaded=false} en cas
    // d'erreur. Si pas défini, on n'affiche que les métadonnées de base.
    void setVodFetcher(VodDetailsFetcher f);

    // Id de la carte focusée à la dernière lecture — utilisé pour restaurer le
    // focus après retour du lecteur. Mis à jour au select.
    const std::string& lastPlayedId() const { return last_played_id_; }

private:
    enum class Zone { Toolbar, TabBar, Sort, Carousel, Sidebar };
    enum class SortKey { None, Alpha, Score, Date };
    enum class SortDir { Desc, Asc };

    struct Row {
        std::string id;
        std::string name;
        std::string poster_url;
        std::string category_id;
        std::string container_extension;
        float rating = 0.0f;
        std::string release_date;
        std::string added;
        // Pour séries, métadonnées catalogue déjà présentes :
        std::string series_plot, series_genre, series_cover;
        bool is_series = false;
        bool is_favorite = false;
    };

    void switchTab(Tab t);
    void openSidebar();
    void closeSidebar();
    void loadCategoriesForActiveTab();
    void rebuildRows();
    void applySort();
    std::vector<Row> fetchFavorites() const;
    int extractYearFromName(const std::string& name) const;

    // Cache métadonnées + worker
    void startVodWorker();
    void stopVodWorker();
    void requestVodDetails(const std::string& id);   // appelé quand le focus change
    VodDetails getCachedDetails(const std::string& id) const;
    VodDetails detailsForFocused() const;

    // Rendu des sections
    int renderHero(SDL_Renderer* r, int x, int y, int w, int h);
    int renderCarousel(SDL_Renderer* r, int x, int y, int w, int h);

    // Toggle favori (DOWN sur une carte). Sur Favorites tab, ouvre le modal confirm.
    void toggleFavoriteFocused();
    void confirmRemoveFavorite(bool confirm);  // true=supprimer, false=annuler

    TextRenderer& text_;
    FocusManager& focus_;
    ImageLoader&  images_;
    store::Cache& cache_;

    Tab tab_ = Tab::Movies;
    Zone zone_ = Zone::Carousel;

    std::unique_ptr<Toolbar> toolbar_;
    std::unique_ptr<TabBar>  tabbar_;
    std::unique_ptr<Sidebar> sidebar_;
    std::unique_ptr<VirtualKeyboard> vkb_;
    bool vkb_open_ = false;   // mirror rapide de vkb_->isOpen() pour les tests

    // Rows = items du carrousel pour le tab courant (filtrés + triés).
    std::vector<Row> rows_;
    int carousel_focus_ = 0;
    int sort_focus_ = 0;              // 0..2 quand zone_==Sort
    SortKey sort_key_ = SortKey::None;
    SortDir sort_dir_ = SortDir::Desc;
    int carousel_scroll_px_ = 0;
    uint32_t last_focus_change_ticks_ = 0;  // pour debouncer requestVodDetails

    // Resume band
    struct ResumeBand {
        bool valid = false;
        std::string label;
        std::string seriesId;
        std::string episodeId;
    };
    ResumeBand resume_{};

    // Modal "Retirer des favoris ?"
    bool fav_confirm_open_ = false;
    int  fav_confirm_btn_idx_ = 0;  // 0=Annuler 1=Supprimer
    Row  fav_confirm_item_{};

    std::string selectedCategoryId_;
    std::string last_played_id_;
    bool syncing_ = false;
    std::string searchQuery_;

    std::function<void(const std::string&)> on_movie_;
    std::function<void(const std::string&)> on_series_;
    std::function<void()> on_settings_;
    std::function<void()> on_sync_;

    // Vod cache + worker
    mutable std::mutex vod_cache_mu_;
    std::unordered_map<std::string, VodDetails> vod_cache_;
    VodDetailsFetcher vod_fetcher_;
    std::thread vod_worker_;
    std::atomic<bool> vod_worker_stop_{false};
    std::mutex vod_queue_mu_;
    std::condition_variable vod_queue_cv_;
    std::deque<std::string> vod_queue_;
    std::string pending_fetch_id_;
    std::atomic<uint32_t> pending_since_ticks_{0};

    // Cache textures posters : url -> texture GPU. Chargé async via ImageLoader.
    // requested_posters_ évite les doubles enqueue pour une même URL.
    std::unordered_map<std::string, SDL_Texture*> poster_tex_;
    std::unordered_set<std::string> poster_requested_;
    void releasePosterCache();
};

}  // namespace iptv::ui

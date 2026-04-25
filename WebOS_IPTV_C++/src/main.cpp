// IPTV Player — entry point and screen router.
// Modes:
//   iptv-player                 -> launch the GUI (settings -> home -> series -> player)
//   iptv-player play <file>     -> play a local file (PoC J2 retained)
//   iptv-player xtream <args>   -> Xtream client smoke test (PoC)
//   iptv-player store           -> store/cache smoke test (PoC)
//   iptv-player sync            -> run a CatalogSync against the saved Config

#include <SDL2/SDL.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>

#include <glib.h>

#include "app/KeyCodes.h"
#include "platform/AppLifecycle.h"
#include "player/GstDecoder.h"
#include "player/NdlDecoder.h"
#include "player/SwDecoder.h"

#include <nlohmann/json.hpp>
#include "player/Playlist.h"
#include "store/Cache.h"
#include "store/Config.h"
#include "store/Favorites.h"
#include "store/Paths.h"
#include "store/WatchHistory.h"
#include "store/WatchPosition.h"
#include "ui/Draw.h"
#include "ui/FocusManager.h"
#include "ui/HomeScreen.h"
#include "ui/ImageLoader.h"
#include "ui/PlayerOSD.h"
#include "ui/PosterGrid.h"
#include "ui/SeriesDetailScreen.h"
#include "ui/SettingsScreen.h"
#include "ui/CatalogFilterScreen.h"
#include "ui/TextRenderer.h"
#include "ui/Theme.h"
#include "xtream/CatalogSync.h"
#include "xtream/XtreamClient.h"

#include <thread>
#include <curl/curl.h>

namespace {

// Forward decl — diag() is defined further down in another anonymous namespace
// block; App::loop() and others in *this* block need to call it.
void diag(const char* fmt, ...);

constexpr int kWidth  = 1920;
constexpr int kHeight = 1080;

namespace fs = std::filesystem;

// ── Font discovery ──────────────────────────────────────────────────────────
std::string resolveFontPath() {
    // 1. Bundled with the IPK / next to the binary (assets/font.ttf).
    char* base = SDL_GetBasePath();
    if (base) {
        std::string b = base;
        SDL_free(base);
        for (const char* rel : {"assets/font.ttf", "../assets/font.ttf"}) {
            fs::path p = fs::path(b) / rel;
            if (fs::exists(p)) return p.string();
        }
    }
    // 2. webOS system font
    const char* sysCandidates[] = {
        "/usr/share/fonts/LG_Smart_UI_TR.ttf",
        "/usr/share/fonts/LGSmartFontUI-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    };
    for (const char* p : sysCandidates) {
        if (fs::exists(p)) return p;
    }
    return {};
}

// ── Modes hérités (PoC) ─────────────────────────────────────────────────────

struct LatestFrame {
    std::mutex m;
    std::vector<uint8_t> y, u, v;
    int width = 0, height = 0, y_stride = 0, u_stride = 0, v_stride = 0;
    bool dirty = false;
};

void copyPlane(std::vector<uint8_t>& dst, const uint8_t* src, int stride, int height) {
    dst.resize(static_cast<size_t>(stride) * height);
    std::memcpy(dst.data(), src, dst.size());
}

int playFile(const std::string& path, bool realtime = true) {
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS | SDL_INIT_AUDIO) != 0) {
        std::fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
        return 1;
    }
    SDL_Window* window = SDL_CreateWindow(
        "IPTV Player", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED,
        kWidth, kHeight, SDL_WINDOW_FULLSCREEN);
    SDL_Renderer* renderer = SDL_CreateRenderer(
        window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);

    LatestFrame latest;
    std::atomic<int> decoded_count{0};

    iptv::GstDecoder decoder;
    decoder.setRealtime(realtime);
    decoder.setFrameCallback([&latest, &decoded_count](const iptv::VideoFrame& f) {
        std::lock_guard<std::mutex> g(latest.m);
        latest.width = f.width; latest.height = f.height;
        latest.y_stride = f.y_stride; latest.u_stride = f.u_stride; latest.v_stride = f.v_stride;
        copyPlane(latest.y, f.y, f.y_stride, f.height);
        copyPlane(latest.u, f.u, f.u_stride, f.height / 2);
        copyPlane(latest.v, f.v, f.v_stride, f.height / 2);
        latest.dirty = true;
        decoded_count.fetch_add(1, std::memory_order_relaxed);
    });

    if (!decoder.open(path)) { std::fprintf(stderr, "open: %s\n", decoder.lastError().c_str()); return 2; }
    if (!decoder.play())     { std::fprintf(stderr, "play failed\n"); return 3; }

    GMainContext* ctx = g_main_context_default();
    SDL_Texture* tex = nullptr;
    int tex_w = 0, tex_h = 0;
    bool running = true;
    Uint32 t_start = SDL_GetTicks();
    Uint32 last_log = t_start;
    int decoded_at_last = 0;

    while (running && !decoder.eos() && !decoder.hasError()) {
        while (g_main_context_iteration(ctx, FALSE)) {}
        SDL_Event ev;
        while (SDL_PollEvent(&ev)) {
            if (ev.type == SDL_QUIT) running = false;
            if (ev.type == SDL_KEYDOWN) {
                int k = ev.key.keysym.sym;
                if (k == SDLK_ESCAPE || iptv::app::isBackKey(k)) running = false;
                if (k == SDLK_SPACE)  decoder.pause();   // toggle would need state
                if (k == SDLK_RIGHT)  decoder.seekRelative(+10);
                if (k == SDLK_LEFT)   decoder.seekRelative(-10);
            }
        }

        {
            std::lock_guard<std::mutex> g(latest.m);
            if (latest.dirty) {
                if (!tex || tex_w != latest.width || tex_h != latest.height) {
                    if (tex) SDL_DestroyTexture(tex);
                    tex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_IYUV,
                                            SDL_TEXTUREACCESS_STREAMING,
                                            latest.width, latest.height);
                    tex_w = latest.width; tex_h = latest.height;
                }
                if (tex) SDL_UpdateYUVTexture(tex, nullptr,
                                              latest.y.data(), latest.y_stride,
                                              latest.u.data(), latest.u_stride,
                                              latest.v.data(), latest.v_stride);
                latest.dirty = false;
            }
        }
        SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
        SDL_RenderClear(renderer);
        if (tex) {
            float ratio = static_cast<float>(tex_w) / static_cast<float>(tex_h);
            int dw = kWidth, dh = static_cast<int>(kWidth / ratio);
            if (dh > kHeight) { dh = kHeight; dw = static_cast<int>(kHeight * ratio); }
            SDL_Rect dst{(kWidth - dw) / 2, (kHeight - dh) / 2, dw, dh};
            SDL_RenderCopy(renderer, tex, nullptr, &dst);
        }
        SDL_RenderPresent(renderer);

        Uint32 now = SDL_GetTicks();
        if (now - last_log >= 1000) {
            int total = decoded_count.load();
            float fps = (total - decoded_at_last) * 1000.0f / (now - last_log);
            SDL_Log("decode_fps=%.1f total=%d pos=%.1fs/%.1fs",
                    fps, total, decoder.positionSeconds(), decoder.durationSeconds());
            last_log = now;
            decoded_at_last = total;
        }
    }
    if (tex) SDL_DestroyTexture(tex);
    decoder.stop();
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
    SDL_Log("Total elapsed: %u ms, frames=%d", SDL_GetTicks() - t_start, decoded_count.load());
    return 0;
}

int xtreamTest(int argc, char* argv[]) {
    if (argc < 6) {
        std::fprintf(stderr, "Usage: iptv-player xtream <serverUrl> <port> <user> <pass>\n");
        return 1;
    }
    using namespace iptv::xtream;
    XtreamClient client(argv[2], argv[3], argv[4], argv[5]);
    std::printf("baseUrl: %s\n", client.baseUrl().c_str());
    try {
        AuthInfo a = client.authenticate();
        std::printf("[auth] user=%s status=%s exp=%s\n",
                    a.username.c_str(), a.status.c_str(), a.expDate.c_str());
        auto vc = client.getVodCategories();
        std::printf("[vod_categories] %zu\n", vc.size());
        auto sc = client.getSeriesCategories();
        std::printf("[series_categories] %zu\n", sc.size());
    } catch (const XtreamError& e) {
        std::fprintf(stderr, "[ERROR] %s\n", e.what());
        return 2;
    }
    return 0;
}

int storeTest() {
    using namespace iptv::store;
    std::printf("[store] dataDir: %s\n", Paths::dataDir().string().c_str());
    Config c = Config::load();
    std::printf("[config] server=%s user=%s\n", c.serverUrl.c_str(), c.username.c_str());
    Cache cache;
    if (!cache.open()) return 1;
    std::printf("[cache] movies=%lld series=%lld lastSync=%s\n",
                static_cast<long long>(cache.movieCount(false)),
                static_cast<long long>(cache.seriesCount(false)),
                cache.getLastSyncDate().value_or("never").c_str());
    return 0;
}

int syncTest() {
    using namespace iptv::store;
    Config c = Config::load();
    if (c.serverUrl.empty() || c.username.empty()) {
        std::fprintf(stderr, "[sync] no Xtream config saved (run iptv-player and Settings first)\n");
        return 1;
    }
    iptv::xtream::XtreamClient client(c.serverUrl, c.port, c.username, c.password);
    Cache cache;
    if (!cache.open()) return 2;
    iptv::xtream::CatalogSync sync(client, cache);
    auto res = sync.run(c, [](const iptv::xtream::SyncProgress& p) {
        std::printf("  [%s] %d/%d %s\n",
                    p.phase.c_str(), p.done, p.total, p.currentCategoryName.c_str());
        std::fflush(stdout);
    });
    std::printf("[sync] ok=%d movies=%d series=%d error=%s\n",
                res.ok, res.moviesSaved, res.seriesSaved, res.error.c_str());
    return res.ok ? 0 : 3;
}

// ── App GUI ─────────────────────────────────────────────────────────────────

class App {
public:
    // Optional auto-play at startup, triggered from SAM launch params JSON.
    // See main(): if argv[1] contains {"streamUrl": "..."}, we surface it here
    // and playUrl() is called right after the home/settings screen is ready.
    void setInitialStream(const std::string& url, const std::string& title) {
        initial_stream_url_   = url;
        initial_stream_title_ = title;
    }

    int run() {
        SDL_Log("App::run() entering");
        // Ask SAM (via SDL-webOS) to deliver BACK / EXIT / HOME keys to us
        // instead of consuming them itself (default behaviour: BACK exits app).
        // Must be set BEFORE SDL_Init so SDL-webOS picks it up at registration.
        SDL_SetHint("SDL_WEBOS_ACCESS_POLICY_KEYS_BACK", "true");
        SDL_SetHint("SDL_WEBOS_ACCESS_POLICY_KEYS_EXIT", "true");
        // Bilinear filtering when SDL scales textures (480p/SD DivX → 1080p),
        // otherwise upscaling uses nearest-neighbour and looks blocky.
        SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "linear");
        if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS | SDL_INIT_AUDIO) != 0) {
            SDL_Log("SDL_Init failed: %s", SDL_GetError());
            return 1;
        }
        SDL_Log("SDL_Init OK, video driver=%s", SDL_GetCurrentVideoDriver() ? SDL_GetCurrentVideoDriver() : "?");
        window_ = SDL_CreateWindow(
            "IPTV Native", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED,
            kWidth, kHeight, SDL_WINDOW_FULLSCREEN);
        if (!window_) { SDL_Log("SDL_CreateWindow failed: %s", SDL_GetError()); return 1; }
        SDL_Log("Window created");
        renderer_ = SDL_CreateRenderer(window_, -1,
            SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
        if (!renderer_) { SDL_Log("SDL_CreateRenderer failed: %s", SDL_GetError()); return 1; }
        SDL_Log("Renderer created");

        std::string fontPath = resolveFontPath();
        SDL_Log("Font path: %s", fontPath.empty() ? "(empty)" : fontPath.c_str());
        if (fontPath.empty()) {
            SDL_Log("Aucune font TTF trouvée — abandon");
            return 1;
        }
        if (!text_.init(renderer_, fontPath, 24)) { SDL_Log("text_.init failed"); return 1; }
        SDL_Log("TextRenderer init OK");

        images_.start(renderer_, 2);
        SDL_Log("ImageLoader started");
        cache_.open();
        SDL_Log("Cache opened");

        lifecycle_.start("com.iptv.player.native");
        // Relaunch hook — SAM notifies us when ares-launch is called again on the
        // already-running app. Testbench uses this to chain multiple streams
        // without killing/restarting the app between runs.
        lifecycle_.setRelaunchHandler([this](const std::string& payload) {
            SDL_Log("Relaunch payload: %s", payload.c_str());
            try {
                auto j = nlohmann::json::parse(payload);
                std::string url = j.value("streamUrl", std::string{});
                std::string title = j.value("title", std::string{});
                if (url.empty()) return;
                // Tear down current playback, then start the new one.
                exitPlayer();
                initial_stream_url_ = url;
                initial_stream_title_ = title;
                pending_initial_play_ms_ = SDL_GetTicks() + 500;  // small delay
                testbench_mode_ = true;  // stay on Player with black screen in between
            } catch (const std::exception& e) {
                SDL_Log("Relaunch payload parse failed: %s", e.what());
            }
        });
        SDL_Log("Lifecycle started");

        config_ = iptv::store::Config::load();
        SDL_Log("Config loaded: server=%s user=%s", config_.serverUrl.c_str(), config_.username.c_str());
        recreateXtreamClient();

        settings_ = std::make_unique<iptv::ui::SettingsScreen>(text_, focus_);
        settings_->setOnSave([this]{
            config_ = iptv::store::Config::load();
            recreateXtreamClient();
            // Sync lancée ici (pas sur test-connection, pas à l'ouverture du
            // catalog-filter, pas sur catalog-filter save) : seul "Enregistrer"
            // des paramètres + bouton Sync de Home déclenchent la synchro.
            kickoffSync();
            gotoHome();
        });
        settings_->setOnCancel([this]{ if (!config_.serverUrl.empty()) gotoHome(); });
        settings_->setOnOpenCatalogFilter([this]{ gotoCatalogFilter(); });
        // Test connexion : instancie un XtreamClient temporaire avec les
        // champs courants et appelle authenticate() dans un thread détaché.
        settings_->setOnTestConnection(
            [this](const std::string& url, const std::string& user,
                   const std::string& pass,
                   std::function<void(bool, std::string)> cb){
                std::thread([this, url, user, pass, cb = std::move(cb)]{
                    try {
                        iptv::xtream::XtreamClient c(url, "80", user, pass);
                        auto info = c.authenticate();
                        std::string msg = "OK";
                        if (!info.expDate.empty()) {
                            try {
                                time_t ts = (time_t)std::stoll(info.expDate);
                                std::tm tm{};
                                localtime_r(&ts, &tm);
                                char buf[32];
                                std::strftime(buf, sizeof(buf), "%d/%m/%Y", &tm);
                                msg = std::string("OK — abonnement valide jusqu'au ") + buf;
                            } catch (...) {}
                        }
                        cb(true, msg);
                        // Pas d'auto-sync sur test-connection : la synchro
                        // est déclenchée uniquement par "Enregistrer" des
                        // paramètres ou par le bouton Sync de Home.
                    } catch (const std::exception& e) {
                        cb(false, e.what());
                    }
                }).detach();
            });

        // CatalogFilterScreen a besoin d'un XtreamClient pour pouvoir fetch
        // les catégories au 1er accès (cache vide).
        if (!client_) recreateXtreamClient();
        catalogFilter_ = std::make_unique<iptv::ui::CatalogFilterScreen>(text_, cache_, *client_);
        catalogFilter_->setOnSave([this]{
            config_ = iptv::store::Config::load();
            // Pas de sync auto ici : l'utilisateur la déclenchera via
            // "Enregistrer" des paramètres ou le bouton Sync de Home.
            gotoSettings();
            settings_->focusSaveButton();
        });
        catalogFilter_->setOnCancel([this]{
            gotoSettings();
            settings_->focusSaveButton();
        });

        home_ = std::make_unique<iptv::ui::HomeScreen>(text_, focus_, images_, cache_);
        home_->setOnOpenMovie([this](const std::string& sid) { onOpenMovie(sid); });
        home_->setOnOpenSeries([this](const std::string& sid){ onOpenSeries(sid); });
        home_->setOnOpenSettings([this]{ gotoSettings(); });
        home_->setOnSync([this]{ kickoffSync(); });
        // Fetcher getVodInfo → métadonnées enrichies (backdrop, plot, genre, …)
        home_->setVodFetcher([this](const std::string& streamId) -> iptv::ui::VodDetails {
            iptv::ui::VodDetails d;
            if (!client_) return d;
            try {
                auto j = client_->getVodInfo(streamId);
                auto info = j.is_object() && j.contains("info") ? j["info"] : nlohmann::json::object();
                auto getStr = [&](const char* key) -> std::string {
                    if (!info.contains(key) || info[key].is_null()) return "";
                    if (info[key].is_string()) return info[key].get<std::string>();
                    return info[key].dump();
                };
                d.plot         = getStr("plot");
                if (d.plot.empty()) d.plot = getStr("description");
                d.genre        = getStr("genre");
                d.release_date = getStr("release_date");
                if (d.release_date.empty()) d.release_date = getStr("releasedate");
                d.cast         = getStr("cast");
                if (d.cast.empty()) d.cast = getStr("actors");
                d.director     = getStr("director");
                // backdrop_path peut être array ou string
                if (info.contains("backdrop_path")) {
                    if (info["backdrop_path"].is_array() && !info["backdrop_path"].empty() &&
                        info["backdrop_path"][0].is_string()) {
                        d.backdrop_url = info["backdrop_path"][0].get<std::string>();
                    } else if (info["backdrop_path"].is_string()) {
                        d.backdrop_url = info["backdrop_path"].get<std::string>();
                    }
                }
                if (d.backdrop_url.empty()) d.backdrop_url = getStr("cover_big");
                if (info.contains("rating") && info["rating"].is_number()) {
                    d.rating = info["rating"].get<float>();
                } else {
                    std::string rs = getStr("rating");
                    if (!rs.empty()) d.rating = (float)std::atof(rs.c_str());
                }
            } catch (const std::exception& e) {
                SDL_Log("getVodInfo(%s) failed: %s", streamId.c_str(), e.what());
            }
            return d;
        });

        if (config_.serverUrl.empty() || config_.username.empty()) {
            SDL_Log("No config -> gotoSettings");
            gotoSettings();
        } else {
            // Trigger background sync if the catalog cache is empty. The home screen
            // will show empty grids until the sync completes and refreshes them.
            int64_t nm = cache_.movieCount(false);
            int64_t ns = cache_.seriesCount(false);
            SDL_Log("Cache before sync: movies=%lld series=%lld",
                    static_cast<long long>(nm), static_cast<long long>(ns));
            if (nm == 0 && ns == 0 && client_) {
                SDL_Log("Starting background CatalogSync…");
                sync_thread_ = std::thread([this]{ runBackgroundSync(); });
            }
            SDL_Log("Have config -> gotoHome");
            gotoHome();
        }

        // If SAM launched us with a streamUrl (testbench auto-play), schedule
        // playback right after the app is in foreground (otherwise NDL /
        // souphttpsrc see a half-initialized TV session and silently fail).
        if (!initial_stream_url_.empty()) {
            SDL_Log("Initial stream queued from launch params: %s",
                    initial_stream_url_.c_str());
            pending_initial_play_ms_ = SDL_GetTicks() + 3000;  // fire 3s after run()
            testbench_mode_ = true;
        }

        SDL_Log("Entering main loop");
        last_input_ticks_ = SDL_GetTicks();
        return loop();
    }

    ~App() {
        // Ordre critique : stop refresh thread AVANT d'annuler le renderer
        // SDL (sinon le thread accède à un renderer détruit → crash).
        stopNdlRefresh();
        sync_abort_ = true;
        if (sync_thread_.joinable()) sync_thread_.join();
        if (decoder_) decoder_->stop();
        if (ndl_)     ndl_->stop();
        if (sw_)      sw_->stop();
        lifecycle_.stop();
        text_.clear();
        images_.stop();
        if (renderer_) SDL_DestroyRenderer(renderer_);
        if (window_) SDL_DestroyWindow(window_);
        SDL_Quit();
    }

private:
    enum class Screen { None, Settings, Filter, Home, Series, Player };

    void runBackgroundSync() {
        if (!client_) return;
        sync_active_ = true;
        sync_phase_ = "démarrage";
        iptv::xtream::CatalogSync sync(*client_, cache_);
        auto res = sync.run(config_,
            [this](const iptv::xtream::SyncProgress& p){
                std::lock_guard<std::mutex> lk(sync_mu_);
                sync_phase_ = p.phase;
                sync_done_ = p.done;
                sync_total_ = p.total;
                sync_category_ = p.currentCategoryName;
            },
            [this]{ return sync_abort_.load(); });
        SDL_Log("[sync] done ok=%d movies=%d series=%d err=%s",
                res.ok, res.moviesSaved, res.seriesSaved, res.error.c_str());
        sync_active_ = false;
        catalog_dirty_ = true;
    }

    void recreateXtreamClient() {
        if (config_.serverUrl.empty()) return;
        client_ = std::make_unique<iptv::xtream::XtreamClient>(
            config_.serverUrl, config_.port, config_.username, config_.password);
    }

    // Déclenche une sync manuelle si rien n'est déjà en cours.
    void kickoffSync() {
        if (!client_) return;
        if (sync_active_.load()) return;
        if (sync_thread_.joinable()) sync_thread_.join();
        sync_thread_ = std::thread([this]{ runBackgroundSync(); });
    }

    void gotoSettings() {
        screen_ = Screen::Settings;
        focus_.clear();
        settings_->load();
    }
    void gotoCatalogFilter() {
        // Sync avant d'afficher la fenêtre : garantit que la liste des
        // catégories est fraîche (cas où l'utilisateur modifie les langues
        // puis ouvre la sélection : nouveaux noms de catégorie visibles).
        // Tourne en arrière-plan, n'empêche pas l'affichage.
        kickoffSync();
        screen_ = Screen::Filter;
        focus_.clear();
        catalogFilter_->load();
    }
    void gotoHome() {
        screen_ = Screen::Home;
        home_->load();
    }
    void onOpenMovie(const std::string& streamId) {
        SDL_Log("onOpenMovie streamId=%s", streamId.c_str());
        // Debug path: "LOCAL:<absolute-path>" bypasses Xtream and plays a local file.
        if (streamId.compare(0, 6, "LOCAL:") == 0) {
            std::string path = streamId.substr(6);
            playUrl(path, "local_test", "", "Local test MPEG-4 ASP");
            return;
        }
        // "NDL:" prefix → hardware-decode PoC (task #19). Uses NdlDecoder.
        if (streamId.compare(0, 4, "NDL:") == 0) {
            std::string path = streamId.substr(4);
            runNdlPoc(path);
            return;
        }
        if (!client_) { SDL_Log("onOpenMovie: no client"); return; }
        // Call get_vod_info first: React does this and the CDN seems to gate
        // the /movie/ download on it (session registration / cookie).
        // On extrait aussi le codec audio pour forcer la chaîne statique
        // aparse+avdec côté décodeur (évite que decodebin prenne un HW LG
        // qui sort du 5.1 non-downmixable → "wrong size" / pas de son).
        std::string ext = "mkv";
        std::string title = "Film";
        std::string audio_codec;
        std::string video_codec;
        bool skip_audio_unsupported = false;
        try {
            auto info = client_->getVodInfo(streamId);
            if (info.is_object() && info.contains("movie_data") && info["movie_data"].is_object()) {
                const auto& md = info["movie_data"];
                if (md.contains("container_extension") && md["container_extension"].is_string())
                    ext = md["container_extension"].get<std::string>();
                if (md.contains("name") && md["name"].is_string())
                    title = md["name"].get<std::string>();
            }
            // info.info.{audio,video}.codec_name → normalisation.
            if (info.is_object() && info.contains("info") && info["info"].is_object()) {
                const auto& ii = info["info"];
                if (ii.contains("audio") && ii["audio"].is_object() &&
                    ii["audio"].contains("codec_name") &&
                    ii["audio"]["codec_name"].is_string()) {
                    std::string c = ii["audio"]["codec_name"].get<std::string>();
                    for (char& ch : c) ch = (char)std::tolower((unsigned char)ch);
                    if (c == "aac" || c == "ac3" || c == "eac3" ||
                        c == "mp3" || c == "mp2") {
                        audio_codec = (c == "mp2") ? std::string("mp3") : c;
                    } else if (c == "dts" || c == "dca") {
                        // Pas de décodeur DTS/DCA sur cette build (avdec_dca
                        // absent de libgstlibav bundled). On avorte la lecture
                        // avec un message plutôt que d'ouvrir un Player muet.
                        SDL_LogWarn(SDL_LOG_CATEGORY_APPLICATION,
                                    "onOpenMovie: audio dts → abort playback");
                        player_error_msg_ = "Audio DTS non support\xC3\xA9 par la TV";
                        player_error_until_ = SDL_GetTicks() + 4000;
                        return;
                    } else if (c == "truehd" || c == "mlp") {
                        // Pas de décodeur avdec_truehd. Une tentative pour
                        // laisser decodebin picker une piste AC3 alternative
                        // stalle le pipeline (decodebin probe tous les pads
                        // dans matroskademux → bloque le parsing vidéo).
                        // On mute proprement, la vidéo reste visible.
                        SDL_LogWarn(SDL_LOG_CATEGORY_APPLICATION,
                                    "onOpenMovie: audio %s non décodable → skip_audio",
                                    c.c_str());
                        skip_audio_unsupported = true;
                    }
                }
                if (ii.contains("video") && ii["video"].is_object() &&
                    ii["video"].contains("codec_name") &&
                    ii["video"]["codec_name"].is_string()) {
                    std::string c = ii["video"]["codec_name"].get<std::string>();
                    for (char& ch : c) ch = (char)std::tolower((unsigned char)ch);
                    if (c == "hevc" || c == "h265")        video_codec = "hevc";
                    else if (c == "h264" || c == "avc")    video_codec = "h264";
                    else if (c == "mpeg4")                 video_codec = "mpeg4";
                    else if (c == "msmpeg4v3")             video_codec = "msmpeg4";
                }
            }
        } catch (const std::exception& e) {
            SDL_Log("onOpenMovie: getVodInfo failed: %s (using defaults)", e.what());
        }
        std::string url = client_->getStreamUrl(streamId, ext);
        SDL_Log("onOpenMovie: url=%s ext=%s title=%s audio_codec=%s video_codec=%s",
                url.c_str(), ext.c_str(), title.c_str(), audio_codec.c_str(),
                video_codec.c_str());
        initial_stream_audio_codec_ = audio_codec;
        // RESET obligatoire du codec vidéo : un precedent watchdog peut avoir
        // pollué initial_stream_codec_ à "hevc" ou "gst" → film suivant forcé
        // dans ce path, échec garanti si le codec diffère.
        initial_stream_codec_ = video_codec.empty() ? std::string("auto") : video_codec;
        initial_stream_seek_sec_ = 0;
        initial_stream_skip_audio_ = skip_audio_unsupported;
        playUrl(url, streamId, "", title);
    }
    // Read /tmp/testbench_cmd.json, trigger playback with the included URL,
    // then clear the file so the same command isn't reprocessed on next poll.
    // We truncate instead of unlink: /tmp has the sticky bit and our app user
    // doesn't own the file (SCP creates it as "prisoner").
    void pollTestbenchCmd() {
        const char* kPath = "/tmp/testbench_cmd.json";
        std::ifstream f(kPath);
        if (!f) return;
        std::string body((std::istreambuf_iterator<char>(f)),
                          std::istreambuf_iterator<char>());
        f.close();
        // Erase content (size 0) to mark it consumed. Push side rewrites
        // the file for the next test.
        std::ofstream clr(kPath, std::ios::trunc);
        if (clr) clr.close();
        if (body.empty()) return;
        try {
            auto j = nlohmann::json::parse(body);
            std::string url = j.value("streamUrl", std::string{});
            std::string title = j.value("title", std::string{});
            std::string codec = j.value("codec", std::string{"auto"});
            std::string audio_codec = j.value("audio_codec", std::string{});
            bool skip_audio = j.value("skip_audio", false);
            int seek_sec = j.value("seek_sec", 0);
            if (url.empty()) return;
            SDL_Log("testbench cmd: streamUrl=%s codec=%s audio_codec=%s skip_audio=%d seek=%ds",
                    url.c_str(), codec.c_str(), audio_codec.c_str(),
                    (int)skip_audio, seek_sec);
            testbench_mode_ = true;
            exitPlayer();
            initial_stream_url_ = url;
            initial_stream_title_ = title;
            initial_stream_codec_ = codec;
            initial_stream_audio_codec_ = audio_codec;
            initial_stream_skip_audio_ = skip_audio;
            initial_stream_seek_sec_ = seek_sec;
            pending_initial_play_ms_ = SDL_GetTicks() + 300;  // small settle
        } catch (const std::exception& e) {
            SDL_Log("testbench cmd parse fail: %s", e.what());
        }
    }

    // Read /tmp/testbench_key.json, push an SDL_KEYDOWN into the SDL event
    // queue so the UI reacts as if the remote had been pressed. Format:
    //   {"key": "UP|DOWN|LEFT|RIGHT|ENTER|BACK|ESC|F1|F2|F3|F4"}
    // Allows driving the app from the host (scripts/push_key.sh) without a
    // physical remote — used for autonomous UI tests with the webcam.
    void pollTestbenchKey() {
        const char* kPath = "/tmp/testbench_key.json";
        std::ifstream f(kPath);
        if (!f) return;
        std::string body((std::istreambuf_iterator<char>(f)),
                          std::istreambuf_iterator<char>());
        f.close();
        std::ofstream clr(kPath, std::ios::trunc);
        if (clr) clr.close();
        if (body.empty()) return;
        try {
            auto j = nlohmann::json::parse(body);
            std::string key = j.value("key", std::string{});
            if (key.empty()) return;
            SDL_Keycode kc = 0;
            if      (key == "UP")    kc = SDLK_UP;
            else if (key == "DOWN")  kc = SDLK_DOWN;
            else if (key == "LEFT")  kc = SDLK_LEFT;
            else if (key == "RIGHT") kc = SDLK_RIGHT;
            else if (key == "ENTER" || key == "OK")  kc = SDLK_RETURN;
            else if (key == "BACK"  || key == "ESC") kc = SDLK_ESCAPE;
            else if (key == "F1") kc = SDLK_F1;
            else if (key == "F2") kc = SDLK_F2;
            else if (key == "F3") kc = SDLK_F3;
            else if (key == "F4") kc = SDLK_F4;
            else { SDL_Log("testbench key unknown: %s", key.c_str()); return; }
            // Les touches testbench bypass le screensaver (sinon la première
            // serait avalée pour fermer l'économiseur).
            screensaver_active_ = false;
            last_input_ticks_ = SDL_GetTicks();
            SDL_Event down{};
            down.type = SDL_KEYDOWN;
            down.key.state = SDL_PRESSED;
            down.key.repeat = 0;
            down.key.keysym.sym = kc;
            down.key.keysym.scancode = SDL_GetScancodeFromKey(kc);
            SDL_PushEvent(&down);
            SDL_Event up{};
            up.type = SDL_KEYUP;
            up.key.state = SDL_RELEASED;
            up.key.keysym.sym = kc;
            up.key.keysym.scancode = SDL_GetScancodeFromKey(kc);
            SDL_PushEvent(&up);
            SDL_Log("testbench key injected: %s", key.c_str());
        } catch (const std::exception& e) {
            SDL_Log("testbench key parse fail: %s", e.what());
        }
    }

    // NDL PoC: hardware-decode a local H.264 file via libNDL_directmedia.
    // Video renders to the TV's HW overlay plane below our SDL window.
    void runNdlPoc(const std::string& path) {
        SDL_Log("[ndl-poc] start path=%s", path.c_str());
        // Stop any active Gst playback to free the video resources.
        if (decoder_) { decoder_->stop(); decoder_.reset(); }
        if (!ndl_) ndl_ = std::make_unique<iptv::NdlDecoder>();
        if (!ndl_->init("com.iptv.player.native")) return;
        // Hard-code 1920x1080 for the bundled test file. Real integration will
        // peek at parsebin's caps and set dims dynamically.
        if (!ndl_->open(path, 1920, 1080)) {
            SDL_Log("[ndl-poc] open failed: %s", ndl_->lastError().c_str());
            return;
        }
        if (!ndl_->play()) {
            SDL_Log("[ndl-poc] play failed: %s", ndl_->lastError().c_str());
            return;
        }
        SDL_Log("[ndl-poc] playing");
    }

    void onOpenSeries(const std::string& seriesId) {
        if (!client_) { std::fprintf(stderr, "[router] no Xtream client configured\n"); return; }
        if (!seriesScreen_) {
            seriesScreen_ = std::make_unique<iptv::ui::SeriesDetailScreen>(text_, focus_, images_, *client_);
            seriesScreen_->setOnBack([this]{ gotoHome(); });
            seriesScreen_->setOnPlay([this](const std::string& url, const std::string& epId,
                                            const std::string& sid, const std::string& title,
                                            const std::string& audioCodec,
                                            const std::string& videoCodec) {
                // Construit la playlist de la saison courante pour permettre
                // prev/next dans le lecteur. Appelé AVANT playUrl pour que
                // l'OSD récupère la bonne info playlist via setPlaylist().
                buildEpisodePlaylist(epId);
                // DTS : aucun décodeur dispo → on avorte avec message.
                // TrueHD/MLP : décodeur absent → skip_audio, vidéo seule.
                if (audioCodec == "dts") {
                    SDL_LogWarn(SDL_LOG_CATEGORY_APPLICATION,
                                "episode audio dts → abort");
                    player_error_msg_ = "Audio DTS non support\xC3\xA9 par la TV";
                    player_error_until_ = SDL_GetTicks() + 4000;
                    return;
                }
                const bool ep_skip = (audioCodec == "truehd" || audioCodec == "mlp");
                initial_stream_skip_audio_ = ep_skip;
                initial_stream_audio_codec_ = ep_skip ? std::string() : audioCodec;
                // Si l'API Xtream a exposé le codec vidéo, on l'utilise en
                // priorité sur l'heuristique d'extension (.mkv ≠ toujours h264).
                if (!videoCodec.empty()) initial_stream_codec_ = videoCodec;
                else                      initial_stream_codec_ = "auto";
                playUrl(url, epId, sid, title);
            });
        }
        screen_ = Screen::Series;
        seriesScreen_->load(seriesId);
    }

    // Xtream /movie/<user>/<pass>/<id>.<ext> URLs 302 to a per-token CDN
    // (e.g. http://5827994.nodivorn.cc/...?token=...). The webOS GStreamer
    // playbin's HTTP source doesn't auto-follow the redirect here — it
    // type-finds on the 302 body (empty) and bails with "Stream doesn't contain
    // enough data". We resolve the final URL via libcurl and feed *that* to playbin.
    // Don't pre-resolve remote URLs: Xtream CDN tokens are often single-use, so
    // consuming the redirect via libcurl invalidates the token for playbin.
    // We let playbin + souphttpsrc follow the 302 themselves (see source-setup
    // hook in GstDecoder::open), and only rewrite local paths to file://.
    static std::string resolveRedirect(const std::string& url) {
        if (url.compare(0, 7, "http://")  == 0 ||
            url.compare(0, 8, "https://") == 0 ||
            url.compare(0, 7, "file://")  == 0) {
            return url;
        }
        return "file://" + url;
    }

    void playUrl(const std::string& orig_url, const std::string& itemId,
                 const std::string& seriesId, const std::string& title) {
        SDL_Log("playUrl: resolving redirect for %s", orig_url.c_str());
        std::string url = resolveRedirect(orig_url);
        SDL_Log("playUrl: effective url=%s", url.c_str());
        screen_ = Screen::Player;
        player_paused_ = false;
        player_muted_  = false;
        player_volume_ = 100;
        // OSD : visible immédiatement, caché 2 s APRÈS que la lecture ait
        // effectivement démarré (position > 0). Géré par
        // osd_first_progress_pending_ dans la boucle principale.
        if (osd_) {
            osd_->setTimeoutMs(10000);
            osd_->poke();
        }
        osd_first_progress_pending_ = true;
        playerTitle_ = title;
        playerUrl_   = url;
        playerItemId_ = itemId;
        playerSeriesId_ = seriesId;

        // Router : si initial_stream_codec_ dit explicitement "h264" ou
        // "hevc" → NDL HW decode. Sinon fallback GstDecoder (SW pour mpeg4,
        // msmpeg4v3, etc.). L'auto mode prend l'extension.
        auto ends_with = [](const std::string& s, const char* suf) {
            size_t n = std::strlen(suf);
            return s.size() >= n && s.compare(s.size() - n, n, suf) == 0;
        };
        std::string codec = initial_stream_codec_;
        if (codec.empty() || codec == "auto") {
            codec = (ends_with(url, ".mkv") || ends_with(url, ".mp4") ||
                     ends_with(url, ".m4v")) ? "h264" : "sw";
        }
        const bool use_ndl = (codec == "h264" || codec == "hevc" || codec == "h265");
        if (use_ndl) {
            if (decoder_) { decoder_->stop(); decoder_.reset(); }
            if (sw_) { sw_->stop(); sw_.reset(); }
            // Tear down any previous NDL instance: réutiliser ndl_ à chaud entre
            // deux films de codecs différents laisse le bridge NDL dans un état
            // pollué (media_loaded_ pas remis à zéro côté driver) → samples=0
            // après switch h264→hevc. On repart toujours d'une instance neuve.
            if (ndl_) { stopNdlRefresh(); ndl_->stop(); ndl_.reset(); }
            ndl_ = std::make_unique<iptv::NdlDecoder>();
            ndl_->setSkipAudio(initial_stream_skip_audio_);
            ndl_->setAudioCodec(initial_stream_audio_codec_);
            ndl_->setStartSeek(initial_stream_seek_sec_);
            if (!ndl_->init("com.iptv.player.native") ||
                !ndl_->open(url, 1920, 1080, codec) ||
                !ndl_->play()) {
                SDL_Log("playUrl: NDL path failed, falling back to Gst");
                ndl_.reset();
            } else {
                SDL_Log("playUrl: NDL HW decode active (%s, audio=%s, skip_audio=%d)",
                        codec.c_str(), initial_stream_audio_codec_.c_str(),
                        (int)initial_stream_skip_audio_);
                // Création de l'OSD pour le path NDL (oublié jusqu'ici :
                // la barre de contrôle ne s'affichait pas car osd_ null).
                if (!osd_) osd_ = std::make_unique<iptv::ui::PlayerOSD>(text_);
                osd_->setTitle(title);
                osd_->setPlaying(true);
                osd_->setMuted(false);
                osd_->setVolume(player_volume_);
                osd_->setSubTracks({}, -1);
                osd_->setStreamInfo(streamCodecLabel(codec),
                                    streamAudioLabel(initial_stream_audio_codec_),
                                    1920, 1080, "HW NDL");
                osd_->setFilename(urlBasename(url));
                osd_->setPlaylist(player_playlist_idx_,
                                  (int)player_playlist_.size());
                // Arme le watchdog : si aucun sample NDL dans les 4 s, on
                // bascule en GstDecoder (cas mkv HEVC annoncé h264, etc.).
                ndl_watchdog_at_ms_ = SDL_GetTicks() + 4000;
                // Lance le thread refresh SDL α=0 à 30 Hz — empêche le
                // compositor webOS de masquer le plan HW quand la boucle
                // principale est bloquée ponctuellement (cf hw_poc campagne
                // 2026-04-23, fix critique sans lequel la vidéo disparaît).
                startNdlRefresh();
                playerSeedAudioTracks();
                osd_->poke();
                lifecycle_.acquireWakeLock("playback");
                return;
            }
        }

        // SwDecoder = pipeline manuel (sans playbin). Utilisé pour :
        //   - msmpeg4v3 (DivX3)
        //   - mpeg4 ASP dans un conteneur matroska : playbin stalle à READY
        //     sur AC3, on bascule sur chaîne manuelle avdec_mpeg4+avdec_ac3
        //     (mémoire AVI+AC3 stall).
        //   - Pour mpeg4+avi on laisse GstDecoder/playbin : il marche bien
        //     sur les pistes MP3 (cf 2026-04-20) et la régression SwDecoder
        //     sur .avi est plus coûteuse à réparer.
        const bool mpeg4_mkv = (codec == "mpeg4") &&
                               (ends_with(url, ".mkv") || ends_with(url, ".mp4"));
        const bool use_sw = (codec == "msmpeg4" || codec == "msmpeg4v3" ||
                             mpeg4_mkv);
        if (use_sw) {
            if (decoder_) { decoder_->stop(); decoder_.reset(); }
            if (ndl_)     { stopNdlRefresh(); ndl_->stop(); ndl_.reset(); }
            sw_ = std::make_unique<iptv::SwDecoder>();
            sw_->setStartSeek(initial_stream_seek_sec_);
            sw_->setSkipAudio(initial_stream_skip_audio_);
            sw_->setAudioCodec(initial_stream_audio_codec_);
            sw_->setFrameCallback([this](const iptv::SwFrame& f) {
                std::lock_guard<std::mutex> g(latest_.m);
                latest_.width = f.width; latest_.height = f.height;
                latest_.y_stride = f.y_stride;
                latest_.u_stride = f.u_stride;
                latest_.v_stride = f.v_stride;
                copyPlane(latest_.y, f.y, f.y_stride, f.height);
                copyPlane(latest_.u, f.u, f.u_stride, f.height / 2);
                copyPlane(latest_.v, f.v, f.v_stride, f.height / 2);
                latest_.dirty = true;
            });
            if (!sw_->open(url, codec) || !sw_->play()) {
                SDL_Log("playUrl: SW path failed, falling back to Gst");
                sw_.reset();
            } else {
                SDL_Log("playUrl: SW decoder active (%s)", codec.c_str());
                if (!osd_) osd_ = std::make_unique<iptv::ui::PlayerOSD>(text_);
                osd_->setTitle(title);
                osd_->setPlaying(true);
                osd_->setMuted(false);
                osd_->setVolume(player_volume_);
                osd_->setSubTracks({}, -1);
                osd_->setStreamInfo(streamCodecLabel(codec),
                                    streamAudioLabel(initial_stream_audio_codec_),
                                    0, 0, "SW avdec");
                osd_->setFilename(urlBasename(url));
                osd_->setPlaylist(player_playlist_idx_,
                                  (int)player_playlist_.size());
                // Arme le watchdog SW : si aucune frame dans les 5 s, le
                // codec annoncé par Xtream est probablement faux (cas
                // fréquent : "mpeg4" qui cache un HEVC) → fallback playbin.
                sw_watchdog_at_ms_ = SDL_GetTicks() + 5000;
                playerSeedAudioTracks();
                osd_->poke();
                lifecycle_.acquireWakeLock("playback");
                return;
            }
        }
        decoder_ = std::make_unique<iptv::GstDecoder>();
        decoder_->setRealtime(true);
        decoder_->setFrameCallback([this](const iptv::VideoFrame& f) {
            std::lock_guard<std::mutex> g(latest_.m);
            latest_.width = f.width; latest_.height = f.height;
            latest_.y_stride = f.y_stride; latest_.u_stride = f.u_stride; latest_.v_stride = f.v_stride;
            copyPlane(latest_.y, f.y, f.y_stride, f.height);
            copyPlane(latest_.u, f.u, f.u_stride, f.height / 2);
            copyPlane(latest_.v, f.v, f.v_stride, f.height / 2);
            latest_.dirty = true;
        });
        SDL_Log("playUrl: calling decoder.open");
        if (!decoder_->open(url)) {
            SDL_Log("decoder.open(%s) failed: %s", url.c_str(), decoder_->lastError().c_str());
            screen_ = Screen::Home;
            decoder_.reset();
            return;
        }
        SDL_Log("playUrl: calling decoder.play");
        if (!decoder_->play()) {
            SDL_Log("decoder.play failed: %s", decoder_->lastError().c_str());
        } else {
            SDL_Log("playUrl: decoder.play returned true");
        }

        // Resume saved position if any.
        double saved = iptv::store::WatchPosition::get(itemId);
        if (saved > 5) {
            // Wait briefly for the pipeline to expose duration before seeking.
            // Decodebin usually has duration after first frame is decoded.
        }
        savedPosition_ = saved;

        if (!osd_) osd_ = std::make_unique<iptv::ui::PlayerOSD>(text_);
        osd_->setTitle(title);
        osd_->setPlaying(true);
        osd_->setMuted(false);
        osd_->setVolume(player_volume_);
        osd_->setSubTracks({}, -1);
        osd_->setStreamInfo(streamCodecLabel(codec),
                            streamAudioLabel(initial_stream_audio_codec_),
                            0, 0, "GStreamer");
        osd_->setFilename(urlBasename(url));
        osd_->setPlaylist(player_playlist_idx_,
                          (int)player_playlist_.size());
        playerSeedAudioTracks();
        osd_->poke();

        lifecycle_.acquireWakeLock("playback");
    }

    // Extrait le basename (dernière composante du chemin, sans querystring)
    // depuis une URL brute. Utilisé pour afficher le nom du fichier dans l'OSD.
    static std::string urlBasename(const std::string& url) {
        // Coupe la querystring.
        size_t qs = url.find('?');
        std::string path = (qs == std::string::npos) ? url : url.substr(0, qs);
        size_t slash = path.find_last_of('/');
        return (slash == std::string::npos) ? path : path.substr(slash + 1);
    }

    // Label humain pour le codec vidéo (UI OSD).
    static std::string streamCodecLabel(const std::string& c) {
        if (c == "h264" || c == "avc") return "H.264";
        if (c == "hevc" || c == "h265") return "H.265";
        if (c == "mpeg4") return "MPEG-4 ASP";
        if (c == "msmpeg4" || c == "msmpeg4v3") return "MSMPEG-4";
        if (c == "sw" || c.empty() || c == "auto") return "";
        std::string up = c;
        for (auto& ch : up) ch = (char)std::toupper((unsigned char)ch);
        return up;
    }
    static std::string streamAudioLabel(const std::string& c) {
        if (c.empty()) return "";
        if (c == "ac3")  return "AC3";
        if (c == "eac3") return "E-AC3";
        if (c == "aac")  return "AAC";
        if (c == "mp3")  return "MP3";
        if (c == "dts")  return "DTS";
        std::string up = c;
        for (auto& ch : up) ch = (char)std::toupper((unsigned char)ch);
        return up;
    }

    void exitPlayer() {
        if (decoder_) {
            double pos = decoder_->positionSeconds();
            double dur = decoder_->durationSeconds();
            if (pos > 0 && dur > 0 && !playerItemId_.empty()) {
                iptv::store::WatchPosition::save(playerItemId_, pos, dur);
            }
            decoder_->stop();
            decoder_.reset();
        }
        if (ndl_) {
            stopNdlRefresh();
            ndl_->stop();
            ndl_.reset();
        }
        if (sw_) {
            sw_->stop();
            sw_.reset();
        }
        if (texture_) { SDL_DestroyTexture(texture_); texture_ = nullptr; tex_w_ = tex_h_ = 0; }
        // In testbench mode: keep the wake lock so the TV doesn't drop to
        // standby between two tests, and stay on Player screen so render()
        // shows the idle animation. Release only when we leave testbench mode.
        if (!testbench_mode_) {
            lifecycle_.releaseWakeLock();
        }
        if (testbench_mode_) {
            screen_ = Screen::Player;
        } else {
            // BACK depuis le lecteur → écran principal (Home) quoi qu'il
            // arrive. L'utilisateur peut re-rentrer dans une série par
            // la vignette Home.
            screen_ = Screen::Home;
        }
    }

    int loop() {
        diag("loop() ENTERED\n");
        GMainContext* ctx = g_main_context_default();
        bool running = true;
        int tick = 0;
        // Observabilité : mesure la durée de chaque tour (dt). Si dt > 33 ms
        // pendant une lecture NDL, le compositor webOS peut masquer le plan
        // HW (symptôme "saccade"). Log seulement les tours > 50 ms pour ne
        // pas noyer les logs.
        uint32_t loop_last_ms = SDL_GetTicks();
        diag("loop() before while\n");
        while (running) {
            uint32_t loop_now_ms = SDL_GetTicks();
            uint32_t loop_dt_ms = loop_now_ms - loop_last_ms;
            loop_last_ms = loop_now_ms;
            if (loop_dt_ms > 50) {
                SDL_Log("[loop] stall dt=%ums tick=%d screen=%d ndl=%d",
                        loop_dt_ms, tick, (int)screen_,
                        ndl_ ? 1 : 0);
            }
            // Pump GLib only while a GstDecoder is active — SDL-webOS otherwise
            // floods the default context with Luna callbacks that livelock us.
            // Cap is generous (32) because GStreamer fires many events per frame
            // (probe queries + bus messages + new-sample) and a low cap leaves
            // decoded frames stuck in the appsink queue → looks like a frozen
            // first frame on screen.
            if (decoder_ || ndl_ || sw_) {
                // Cap réduit de 32 → 8 : chaque itération peut prendre ~4ms
                // avec les bus events GStreamer lourds (state changes sur
                // ~15 éléments du pipeline) → 32 itér = 128ms stall par
                // tour, observé dans hw_poc 2026-04-24. Les events non
                // traités ce tour-ci le seront au suivant.
                for (int i = 0; i < 8 && g_main_context_iteration(ctx, FALSE); ++i) {}
            }
            ++tick;

            // Deferred auto-play from launch params (wait for foreground).
            if (pending_initial_play_ms_ != 0 &&
                SDL_GetTicks() >= pending_initial_play_ms_) {
                pending_initial_play_ms_ = 0;
                SDL_Log("Deferred auto-play: %s", initial_stream_url_.c_str());
                playUrl(initial_stream_url_, "testbench", "",
                        initial_stream_title_.empty() ? std::string("Testbench")
                                                      : initial_stream_title_);
            }

            // Testbench command file polling : tous les 500 ms, on lit
            // /tmp/testbench_cmd.json, on le supprime, et on relance avec
            // le streamUrl qu'il contient. Permet au banc de test (sur le
            // PC hôte) de chaîner plusieurs tests via SCP sans redémarrer
            // l'app entre chaque run.
            if (tick % 30 == 0) {  // ~30 ticks * ~17ms = ~500ms
                pollTestbenchCmd();
                pollTestbenchKey();
            }

            // Wake-lock refresh permanent : toutes les ~60s on ping pour que
            // la TV ne s'endorme jamais (testbench ou UI test). L'avBlock
            // initial peut expirer côté power service.
            if (!decoder_ && !ndl_ && !sw_ && (tick % 3600) == 0) {
                lifecycle_.pingWakeLock("ui_test_idle");
            }

            SDL_Event ev;
            int polled = 0;
            while (SDL_PollEvent(&ev)) {
                ++polled;
                if (ev.type == SDL_KEYDOWN) {
                    SDL_Log("POLLED KEYDOWN sym=%d scan=%d screen=%d",
                            ev.key.keysym.sym, ev.key.keysym.scancode, (int)screen_);
                }
                if (ev.type == SDL_QUIT) running = false;
                if (ev.type == SDL_KEYDOWN) {
                    last_input_ticks_ = SDL_GetTicks();
                    // Si screensaver OLED actif, la première touche le ferme
                    // sans la transmettre à l'UI (sinon on déclencherait une
                    // action involontaire).
                    if (screensaver_active_) {
                        screensaver_active_ = false;
                        continue;
                    }
                    int k = ev.key.keysym.sym;
                    int sc = ev.key.keysym.scancode;
                    // Télécommande LG webOS : certaines touches arrivent
                    // avec sym=0 (keycode non résolu par SDL) + scancode
                    // vendor-specific. On mappe les scancodes observés vers
                    // nos constantes KEY::*. Observé 2026-04-24 : BACK = 482.
                    if (k == 0 && sc != 0) {
                        switch (sc) {
                            case 482: k = iptv::app::KEY::BACK; break;
                            default: break;
                        }
                    }
                    if (iptv::app::isExitKey(k)) { running = false; continue; }
                    handleKey(k);
                } else if (ev.type == SDL_TEXTINPUT && screen_ == Screen::Settings) {
                    settings_->handleText(ev.text.text);
                }
            }
            if ((tick % 240) == 0 && polled == 0) {
                SDL_Log("LOOP tick=%d polled=0 screen=%d", tick, (int)screen_);
            }

            images_.pump();
            // Re-read cache when the background sync flips the dirty flag.
            if (catalog_dirty_.exchange(false) && screen_ == Screen::Home) {
                SDL_Log("catalog dirty -> reloading HomeScreen");
                home_->load();
            }
            // Informe la HomeScreen de l'état de sync pour animer le spinner
            // dans la Toolbar (bouton "Sync…").
            home_->setSyncing(sync_active_);
            // Tick OSD en mode NDL aussi (pas seulement GstDecoder) + MAJ
            // position/durée pour que la timeline affiche une progression.
            // Watchdog SW : timeout 5 s. Si aucune frame décodée, le codec
            // "mpeg4" annoncé par Xtream est peut-être mal labellisé, ou
            // avdec_mpeg4 plante. Fallback DIRECT vers GstDecoder (playbin
            // auto-plug). L'étape intermédiaire NDL H.265 qu'on avait avant
            // ajoutait 4s de latence sans bénéfice pour les vrais MPEG-4.
            if (screen_ == Screen::Player && sw_ && sw_watchdog_at_ms_ != 0 &&
                SDL_GetTicks() >= sw_watchdog_at_ms_) {
                if (sw_->videoSampleCount() == 0) {
                    SDL_Log("[watchdog] SW sans sample après 5s, fallback GstDecoder");
                    std::string saveUrl    = playerUrl_;
                    std::string saveId     = playerItemId_;
                    std::string saveSeries = playerSeriesId_;
                    std::string saveTitle  = playerTitle_;
                    std::string saveAudio  = initial_stream_audio_codec_;
                    bool saveSkip          = initial_stream_skip_audio_;
                    sw_->stop(); sw_.reset();
                    sw_watchdog_at_ms_ = 0;
                    initial_stream_codec_       = "gst";  // playbin auto-plug
                    initial_stream_audio_codec_ = saveAudio;
                    initial_stream_skip_audio_  = saveSkip;
                    initial_stream_seek_sec_    = 0;
                    playUrl(saveUrl, saveId, saveSeries, saveTitle);
                    continue;
                }
                sw_watchdog_at_ms_ = 0;
            }

            // Watchdog NDL : si aucun sample vidéo poussé après 4 s, ou si
            // Load a déjà raté (hasError=true), on bascule immédiatement vers
            // GstDecoder. Causes typiques : matroskademux refuse de link sur
            // un codec mal annoncé, ou NDL Load rc=-1 (HEVC profil non
            // supporté par cette build).
            bool ndl_failed_fast = ndl_ && ndl_->hasError();
            if (screen_ == Screen::Player && ndl_ && ndl_watchdog_at_ms_ != 0 &&
                (ndl_failed_fast ||
                 SDL_GetTicks() >= ndl_watchdog_at_ms_)) {
                if (ndl_failed_fast || ndl_->videoSampleCount() == 0) {
                    SDL_Log("[watchdog] NDL KO (error=%d samples=%u) → fallback GstDecoder",
                            (int)ndl_failed_fast, ndl_->videoSampleCount());
                    std::string saveUrl    = playerUrl_;
                    std::string saveId     = playerItemId_;
                    std::string saveSeries = playerSeriesId_;
                    std::string saveTitle  = playerTitle_;
                    std::string saveAudio  = initial_stream_audio_codec_;
                    stopNdlRefresh();
                    ndl_->stop(); ndl_.reset();
                    ndl_watchdog_at_ms_ = 0;
                    // "gst" ne match ni use_ndl ni use_sw → force GstDecoder
                    // (playbin auto-plug, gère HEVC/VP9/etc).
                    initial_stream_codec_       = "gst";
                    initial_stream_audio_codec_ = saveAudio;
                    initial_stream_seek_sec_    = 0;
                    playUrl(saveUrl, saveId, saveSeries, saveTitle);
                    continue;
                }
                ndl_watchdog_at_ms_ = 0;  // OK, on a reçu des samples
            }
            if (screen_ == Screen::Player && ndl_ && osd_) {
                double pos = ndl_->positionSeconds();
                if (seek_dialog_open_) {
                    // Pendant la modale "Aller à", l'OSD affiche la cible
                    // pour que l'utilisateur voie exactement où il s'apprête
                    // à sauter. La lecture est en pause, donc pos réelle
                    // est figée.
                    osd_->setProgress((double)seek_dialog_target_sec_,
                                      seek_dialog_duration_sec_ > 0
                                        ? seek_dialog_duration_sec_
                                        : ndl_->durationSeconds());
                } else {
                    osd_->setProgress(pos, ndl_->durationSeconds());
                }
                if (osd_first_progress_pending_ && pos > 0.05) {
                    osd_first_progress_pending_ = false;
                    osd_->hideIn(2000);
                }
                osd_->tick(SDL_GetTicks());
            }
            if (screen_ == Screen::Player && sw_ && osd_) {
                double pos = sw_->positionSeconds();
                double dur = sw_->durationSeconds();
                if (seek_dialog_open_) {
                    osd_->setProgress((double)seek_dialog_target_sec_,
                                      seek_dialog_duration_sec_ > 0
                                        ? seek_dialog_duration_sec_ : dur);
                } else {
                    osd_->setProgress(pos, dur);
                }
                int lw = 0, lh = 0;
                {
                    std::lock_guard<std::mutex> g(latest_.m);
                    lw = latest_.width; lh = latest_.height;
                }
                if (lw > 0 && lh > 0) {
                    osd_->setVideoResolution(lw, lh);
                    if (osd_first_progress_pending_) {
                        osd_first_progress_pending_ = false;
                        osd_->hideIn(2000);
                    }
                }
                osd_->tick(SDL_GetTicks());
            }
            if (screen_ == Screen::Player && decoder_) {
                if (savedPosition_ > 5 && decoder_->durationSeconds() > savedPosition_ + 5) {
                    decoder_->seekSeconds(savedPosition_);
                    savedPosition_ = 0;
                }
                double pos = decoder_->positionSeconds();
                if (seek_dialog_open_) {
                    osd_->setProgress((double)seek_dialog_target_sec_,
                                      seek_dialog_duration_sec_ > 0
                                        ? seek_dialog_duration_sec_
                                        : decoder_->durationSeconds());
                } else {
                    osd_->setProgress(pos, decoder_->durationSeconds());
                }
                int lw = 0, lh = 0;
                {
                    std::lock_guard<std::mutex> g(latest_.m);
                    lw = latest_.width; lh = latest_.height;
                }
                if (lw > 0 && lh > 0) osd_->setVideoResolution(lw, lh);
                if (osd_first_progress_pending_ && pos > 0.05) {
                    osd_first_progress_pending_ = false;
                    osd_->hideIn(2000);
                }
                osd_->tick(SDL_GetTicks());
                if (decoder_->hasError()) {
                    player_error_msg_ = decoder_->lastError().substr(0, 100);
                    player_error_until_ = SDL_GetTicks() + 4000;
                    exitPlayer();
                } else if (decoder_->eos()) {
                    exitPlayer();
                }
            }

            render();
            SDL_RenderPresent(renderer_);
        }
        return 0;
    }

    void handleKey(int k) {
        namespace KEY = iptv::app::KEY;
        SDL_Log("KEY sym=%d (0x%x) screen=%d back?=%d ok?=%d",
                k, k, (int)screen_,
                iptv::app::isBackKey(k) ? 1 : 0,
                iptv::app::isOkKey(k) ? 1 : 0);

        // Confirmation de sortie d'application : modal prioritaire, capture
        // toutes les touches tant qu'elle est ouverte.
        if (exit_confirm_open_) {
            if (k == KEY::LEFT || k == KEY::RIGHT) {
                exit_confirm_focus_ = 1 - exit_confirm_focus_;
            } else if (iptv::app::isOkKey(k)) {
                if (exit_confirm_focus_ == 1) {   // "Oui"
                    SDL_Event ev; ev.type = SDL_QUIT; SDL_PushEvent(&ev);
                } else {
                    exit_confirm_open_ = false;
                }
            } else if (iptv::app::isBackKey(k)) {
                exit_confirm_open_ = false;
            }
            return;
        }

        bool handled = false;
        switch (screen_) {
            case Screen::Settings: settings_->handleKey(k, handled); break;
            case Screen::Filter:   if (catalogFilter_) catalogFilter_->handleKey(k, handled); break;
            case Screen::Home:     home_->handleKey(k, handled); break;
            case Screen::Series:   if (seriesScreen_) seriesScreen_->handleKey(k, handled); break;
            case Screen::Player:   handlePlayerKey(k, handled); break;
            default: break;
        }
        // BACK global : depuis n'importe quel écran secondaire on retourne au
        // main (Home). Depuis Home, on propose de quitter l'application.
        if (!handled && iptv::app::isBackKey(k)) {
            if (screen_ == Screen::Home) {
                exit_confirm_open_ = true;
                exit_confirm_focus_ = 0;   // Non par défaut
            } else {
                gotoHome();
            }
        }
    }

    void handlePlayerKey(int k, bool& handled) {
        namespace KEY = iptv::app::KEY;
        SDL_Log("[player] key sym=%d (0x%x) back?=%d ok?=%d exit?=%d",
                k, k, (int)iptv::app::isBackKey(k),
                (int)iptv::app::isOkKey(k), (int)iptv::app::isExitKey(k));

        // Quelle que soit la raison, BACK/EXIT/STOP doivent TOUJOURS quitter le
        // lecteur, même si decoder_/ndl_/sw_ sont transitoirement null (fin de
        // stream en cours). Ce filet de sécurité est en tête pour éviter les
        // blocages constatés.
        if (iptv::app::isBackKey(k) || iptv::app::isExitKey(k) ||
            k == KEY::STOP) {
            handled = true;
            exitPlayer();
            return;
        }

        // Modale "Aller à" : capture tout tant qu'ouverte.
        if (seek_dialog_open_) {
            if (k == KEY::LEFT)  { seekDialogAdjust(-30);  handled = true; return; }
            if (k == KEY::RIGHT) { seekDialogAdjust(+30);  handled = true; return; }
            if (k == KEY::DOWN)  { seekDialogAdjust(-300); handled = true; return; }
            if (k == KEY::UP)    { seekDialogAdjust(+300); handled = true; return; }
            if (iptv::app::isOkKey(k))   { confirmSeekDialog(); handled = true; return; }
            if (iptv::app::isBackKey(k)) { closeSeekDialog();   handled = true; return; }
            handled = true;
            return;
        }

        if (!decoder_ && !ndl_ && !sw_) return;
        handled = true;

        // Seek LEFT/RIGHT : sur NDL → ouvre la modale "Aller à" (NDL pas de
        // seek inplace). Sur GstDecoder → ±30 s silencieux (seek_simple OK).
        // Réservé au mode LECTURE (pas menu / btnMode).
        if (osd_ && !osd_->inBtnMode() && !osd_->anyMenuOpen()) {
            if (k == KEY::LEFT)  { playerSeek(-30); return; }
            if (k == KEY::RIGHT) { playerSeek(+30); return; }
        }

        if (osd_) osd_->poke();

        // ── Menu audio ouvert ─────────────────────────────────────────────
        if (osd_ && osd_->audioMenuOpen()) {
            if (iptv::app::isBackKey(k) || k == KEY::BLUE || k == KEY::STOP ||
                iptv::app::isExitKey(k)) {
                osd_->closeAudioMenu(); return;
            }
            if (k == KEY::UP)   { osd_->audioMenuMove(-1); return; }
            if (k == KEY::DOWN) { osd_->audioMenuMove(+1); return; }
            if (iptv::app::isOkKey(k)) {
                playerSelectAudio(osd_->audioMenuCurrentIdx());
                osd_->closeAudioMenu();
                return;
            }
            return;
        }

        // ── Menu sous-titres ouvert ───────────────────────────────────────
        if (osd_ && osd_->subMenuOpen()) {
            if (iptv::app::isBackKey(k) || k == KEY::RED || k == KEY::STOP ||
                iptv::app::isExitKey(k)) {
                osd_->closeSubMenu(); return;
            }
            if (k == KEY::UP)   { osd_->subMenuMove(-1); return; }
            if (k == KEY::DOWN) { osd_->subMenuMove(+1); return; }
            if (iptv::app::isOkKey(k)) {
                playerSelectSub(osd_->subMenuCurrentIdx());
                osd_->closeSubMenu();
                return;
            }
            return;
        }

        // ── Mode BOUTONS (après flèche bas) ───────────────────────────────
        if (osd_ && osd_->inBtnMode()) {
            if (k == KEY::LEFT)  { osd_->btnMove(-1); return; }
            if (k == KEY::RIGHT) { osd_->btnMove(+1); return; }
            if (k == KEY::UP || iptv::app::isBackKey(k)) {
                osd_->exitBtnMode(); return;
            }
            if (iptv::app::isOkKey(k)) {
                dispatchPlayerAction(osd_->btnActivate());
                return;
            }
            return;
        }

        // ── Mode LECTURE (défaut) ─────────────────────────────────────────
        // BACK/EXIT/STOP déjà traités en tête, LEFT/RIGHT ±30s silencieux.
        // OK / Play-Pause / UP cachent l'OSD immédiatement (feedback rapide
        // après l'action, pas besoin d'attendre le timeout 10s).
        if (iptv::app::isOkKey(k)) {
            playerTogglePause();
            if (osd_) osd_->hideNow();
            return;
        }
        if (k == KEY::PLAY_PAUSE || k == KEY::PAUSE) {
            playerTogglePause();
            if (osd_) osd_->hideNow();
            return;
        }
        if (k == KEY::PLAY) {
            if (player_paused_) playerTogglePause();
            if (osd_) osd_->hideNow();
            return;
        }
        if (k == KEY::UP)                     { if (osd_) osd_->hideNow();       return; }
        if (k == KEY::REW)                    { playerSeek(-300);                return; }
        if (k == KEY::FF)                     { playerSeek(+300);                return; }
        if (k == KEY::DOWN)                   { if (osd_) osd_->enterBtnMode();  return; }
        // Mapping télécommande 2026-04-24 :
        //   🔴 RED    = sortir du lecteur
        //   🟢 GREEN  = épisode précédent
        //   🟡 YELLOW = épisode suivant
        //   🔵 BLUE   = menu piste audio
        if (k == KEY::RED)                    { exitPlayer();                    return; }
        if (k == KEY::GREEN)                  { playerGoPrev();                  return; }
        if (k == KEY::YELLOW)                 { playerGoNext();                  return; }
        if (k == KEY::BLUE)                   { if (osd_) osd_->openAudioMenu(); return; }
    }

    // === OSD contrôles lecture ===================================================

    bool player_paused_ = false;
    bool player_muted_  = false;
    int  player_volume_ = 100;
    // Après le lancement d'une vidéo, l'OSD reste visible jusqu'à ce que la
    // position dépasse 0 (premier frame joué), puis on planifie le hide
    // 2 s plus tard. Réinitialisé à chaque playUrl().
    bool osd_first_progress_pending_ = false;
    // Watchdog NDL : timestamp (SDL_GetTicks) auquel on a lancé le path NDL.
    // Si après 4 s NdlDecoder n'a toujours vu aucun sample, on bascule en
    // GstDecoder (fallback auto-plug, gère HEVC/MPEG4/etc).
    uint32_t ndl_watchdog_at_ms_ = 0;
    // Le refresh thread SDL α=0 à 30 Hz tenté fin 2026-04-23 (inspiré hw_poc)
    // a été retiré : SDL_RenderPresent depuis un thread alterne crée un
    // conflit EGL sur webOS (erreur 3002 "Unable to make EGL context
    // current") qui stalle la boucle principale à 110-180 ms par tour →
    // les samples NDL ne passent plus. Le hw_poc était standalone sans
    // main thread concurrent, on ne peut pas répliquer tel quel.
    // La boucle principale fait SDL_RenderPresent chaque tour (~17 ms en
    // pratique) ce qui suffit à maintenir le plan NDL visible.
    void startNdlRefresh() {}
    void stopNdlRefresh() {}
    // Même logique côté SwDecoder : Xtream peut annoncer mpeg4 pour un mkv
    // dont le vrai codec est HEVC/AV1 → mpeg4vparse échoue à link, aucun
    // sample. On bascule alors sur GstDecoder (playbin auto-plug).
    uint32_t sw_watchdog_at_ms_ = 0;

    // Mapping code ISO → libellé humain pour le menu audio.
    static std::string humanLang(const std::string& code) {
        if (code == "fr") return "Français";
        if (code == "en") return "Anglais";
        if (code == "it") return "Italien";
        if (code == "de") return "Allemand";
        if (code == "es") return "Espagnol";
        return code;
    }

    // Seed la liste audio du lecteur depuis cfg.selectedLanguages. Tant que le
    // décodeur ne remonte pas de pistes réelles on utilise la préférence
    // utilisateur : feedback visuel immédiat + permet au menu de fonctionner.
    void playerSeedAudioTracks() {
        if (!osd_) return;
        auto cfg = iptv::store::Config::load();
        std::vector<std::string> langs = cfg.selectedLanguages;
        if (langs.empty()) langs = {"fr"};
        std::vector<std::string> labels;
        labels.reserve(langs.size());
        for (const auto& c : langs) labels.push_back(humanLang(c));
        osd_->setAudioTracks(labels, 0);
    }

    void playerSelectAudio(int idx) {
        if (!osd_) return;
        auto st = osd_->state();
        osd_->setAudioTracks(st.audioLabels, idx);
        // TODO: reload du stream sur la nouvelle piste côté décodeur.
    }

    void playerSelectSub(int idx) {
        if (!osd_) return;
        auto st = osd_->state();
        osd_->setSubTracks(st.subLabels, idx);
        // TODO: activer la piste sous-titres côté décodeur (pas implémenté).
    }

    void playerSeek(int seconds) {
        if (ndl_) {
            // NDL n'accepte pas de seek inplace (pas d'API flush+reset PTS
            // confirmée). ←/→ ouvre donc la modale "Aller à" qui arrête la
            // lecture, laisse l'utilisateur choisir un timer, puis relance
            // avec start_seek_sec_ pour que NDL démarre sur une IDR.
            openSeekDialogFromCurrent();
            return;
        }
        if (decoder_) decoder_->seekRelative(seconds);
        if (sw_)      sw_->seekRelative(seconds);
    }

    // === Modale "Aller à" (seek via restart) ===================================
    // NDL ne sachant pas seeker en vol, on arrête la lecture, on affiche un
    // sélecteur de temps, puis on relance depuis le début au timer choisi en
    // s'assurant que le premier sample livré à NDL est une IDR (KEY_UNIT).

    bool    seek_dialog_open_ = false;
    int     seek_dialog_target_sec_ = 0;
    double  seek_dialog_duration_sec_ = 0.0;
    // Contexte pour relancer la lecture après sélection.
    std::string seek_dialog_url_;
    std::string seek_dialog_item_id_;
    std::string seek_dialog_series_id_;
    std::string seek_dialog_title_;
    std::string seek_dialog_audio_codec_;
    std::string seek_dialog_codec_;  // "h264"/"hevc"/"mpeg4"/…

    void openSeekDialogFromCurrent() {
        if (!osd_) return;
        // Capture le contexte AVANT de fermer le pipeline : on en a besoin
        // pour relancer playUrl à l'identique (mais avec offset).
        seek_dialog_url_         = playerUrl_;
        seek_dialog_item_id_     = playerItemId_;
        seek_dialog_series_id_   = playerSeriesId_;
        seek_dialog_title_       = playerTitle_;
        seek_dialog_audio_codec_ = initial_stream_audio_codec_;
        seek_dialog_codec_       = initial_stream_codec_;
        // Position/durée actuelles comme point de départ de la sélection.
        double pos = 0, dur = 0;
        if (ndl_)           { pos = ndl_->positionSeconds();     dur = ndl_->durationSeconds(); }
        else if (decoder_)  { pos = decoder_->positionSeconds(); dur = decoder_->durationSeconds(); }
        seek_dialog_target_sec_    = (int)pos;
        seek_dialog_duration_sec_  = dur;
        // Pause la lecture pour que l'utilisateur ait le temps de choisir.
        if (!player_paused_) playerTogglePause();
        seek_dialog_open_ = true;
        osd_->poke();
    }

    void closeSeekDialog() {
        seek_dialog_open_ = false;
        // Reprend la lecture qu'on avait mise en pause à l'ouverture.
        if (player_paused_) playerTogglePause();
    }

    // Restart-seek direct : stop + relance à current+delta, même méthode que
    // confirmSeekDialog() mais sans passer par la modale. Utilisé par les
    // boutons ±30s / ±5min pour avoir un comportement uniforme entre NDL et
    // GstDecoder — pas d'inplace seek (fiable avec GstDecoder mais cause les
    // crashes NDL, cf tickets ndl_internals).
    void playerRestartSeek(int delta_sec) {
        if (!osd_) return;
        double pos = 0, dur = 0;
        if (ndl_)          { pos = ndl_->positionSeconds();     dur = ndl_->durationSeconds(); }
        else if (decoder_) { pos = decoder_->positionSeconds(); dur = decoder_->durationSeconds(); }
        int target = (int)pos + delta_sec;
        if (target < 0) target = 0;
        if (dur > 0 && target > (int)dur - 2) target = std::max(0, (int)dur - 2);

        seek_dialog_url_         = playerUrl_;
        seek_dialog_item_id_     = playerItemId_;
        seek_dialog_series_id_   = playerSeriesId_;
        seek_dialog_title_       = playerTitle_;
        seek_dialog_audio_codec_ = initial_stream_audio_codec_;
        seek_dialog_codec_       = initial_stream_codec_;
        seek_dialog_target_sec_  = target;
        seek_dialog_duration_sec_= dur;
        // confirmSeekDialog() fait le stop + relance — il clear aussi
        // seek_dialog_open_ (donc pas d'ouverture UI, juste l'effet).
        confirmSeekDialog();
    }

    void seekDialogAdjust(int delta_sec) {
        int t = seek_dialog_target_sec_ + delta_sec;
        if (t < 0) t = 0;
        if (seek_dialog_duration_sec_ > 0 && t > (int)seek_dialog_duration_sec_)
            t = (int)seek_dialog_duration_sec_;
        seek_dialog_target_sec_ = t;
        if (osd_) osd_->poke();   // garde la barre OSD visible pendant le réglage
    }

    void confirmSeekDialog() {
        int target = std::max(0, seek_dialog_target_sec_);
        if (seek_dialog_duration_sec_ > 0 && target > (int)seek_dialog_duration_sec_ - 2)
            target = std::max(0, (int)seek_dialog_duration_sec_ - 2);
        SDL_Log("[seek-modal] confirm target=%ds (dur=%.1fs)",
                target, seek_dialog_duration_sec_);
        seek_dialog_open_ = false;
        // Teardown : exitPlayer() resetterait screen_→Home, on veut rester
        // en Player mode. On stoppe manuellement les décodeurs.
        if (decoder_) { decoder_->stop(); decoder_.reset(); }
        if (ndl_)     { stopNdlRefresh(); ndl_->stop(); ndl_.reset(); }
        if (sw_)      { sw_->stop();      sw_.reset(); }
        if (texture_) { SDL_DestroyTexture(texture_); texture_ = nullptr; tex_w_ = tex_h_ = 0; }
        // Relance avec start_seek_sec_ — NdlDecoder::play() fera PAUSED →
        // seek(KEY_UNIT) → PLAYING, premier sample = IDR à ~target.
        initial_stream_audio_codec_ = seek_dialog_audio_codec_;
        initial_stream_codec_       = seek_dialog_codec_;
        initial_stream_seek_sec_    = target;
        playUrl(seek_dialog_url_, seek_dialog_item_id_,
                seek_dialog_series_id_, seek_dialog_title_);
    }

    void playerTogglePause() {
        player_paused_ = !player_paused_;
        if (decoder_) {
            if (player_paused_) decoder_->pause();
            else decoder_->play();
        }
        if (ndl_) {
            if (player_paused_) ndl_->pause();
            else ndl_->resume();
        }
    }

    void playerToggleMute() {
        player_muted_ = !player_muted_;
        // TODO: appliquer sur le sink audio (decoder_->setMuted si dispo).
        if (osd_) osd_->setMuted(player_muted_);
    }

    void playerVolumeChange(int delta) {
        player_volume_ = std::clamp(player_volume_ + delta, 0, 100);
        if (osd_) {
            osd_->setVolume(player_volume_);
            osd_->setMuted(player_volume_ == 0);
        }
        // TODO: propager au sink audio. Pour l'instant, feedback UI seulement.
    }

    // Playlist épisode : peuplée dans onOpenSeries→setOnPlay. Contient les
    // URL/id/titre/codec audio de tous les épisodes de la saison courante
    // pour permettre la navigation prev/next sans re-fetcher.
    struct PlaylistEp {
        std::string url;
        std::string id;
        std::string title;       // "S01E03 - Le bon titre"
        std::string audioCodec;
    };
    std::vector<PlaylistEp> player_playlist_;
    int                     player_playlist_idx_ = -1;

    // Construit player_playlist_ depuis la saison actuelle de seriesScreen_
    // et positionne player_playlist_idx_ sur l'épisode `currentEpId`.
    void buildEpisodePlaylist(const std::string& currentEpId) {
        player_playlist_.clear();
        player_playlist_idx_ = -1;
        if (!seriesScreen_ || !client_) return;
        const auto& eps = seriesScreen_->currentEpisodes();
        int seasonNo = seriesScreen_->currentSeasonNumber();
        player_playlist_.reserve(eps.size());
        for (const auto& ep : eps) {
            PlaylistEp p;
            p.url = client_->getEpisodeUrl(ep.id, ep.container_extension);
            p.id  = ep.id;
            char buf[160];
            std::snprintf(buf, sizeof(buf), "S%02dE%02d - %s",
                          seasonNo, ep.episode_num, ep.title.c_str());
            p.title = buf;
            // Même heuristique codec audio que SeriesDetailScreen.cpp.
            try {
                if (ep.raw.is_object() && ep.raw.contains("info") &&
                    ep.raw["info"].is_object()) {
                    const auto& ii = ep.raw["info"];
                    if (ii.contains("audio") && ii["audio"].is_object() &&
                        ii["audio"].contains("codec_name") &&
                        ii["audio"]["codec_name"].is_string()) {
                        std::string c = ii["audio"]["codec_name"].get<std::string>();
                        for (char& ch : c) ch = (char)std::tolower((unsigned char)ch);
                        if (c == "aac" || c == "ac3" || c == "eac3" ||
                            c == "mp3" || c == "mp2") {
                            p.audioCodec = (c == "mp2") ? std::string("mp3") : c;
                        }
                    }
                }
            } catch (...) {}
            if (ep.id == currentEpId) player_playlist_idx_ = (int)player_playlist_.size();
            player_playlist_.push_back(std::move(p));
        }
    }

    void playerJumpTo(int newIdx) {
        if (newIdx < 0 || newIdx >= (int)player_playlist_.size()) return;
        const auto& ep = player_playlist_[newIdx];
        player_playlist_idx_ = newIdx;
        initial_stream_audio_codec_ = ep.audioCodec;
        playUrl(ep.url, ep.id, playerSeriesId_, ep.title);
    }

    void playerGoNext() { playerJumpTo(player_playlist_idx_ + 1); }
    void playerGoPrev() { playerJumpTo(player_playlist_idx_ - 1); }

    // Déclenche l'action associée à un bouton de la barre OSD.
    void dispatchPlayerAction(iptv::ui::PlayerAction a) {
        using A = iptv::ui::PlayerAction;
        switch (a) {
            case A::PlayPause:   playerTogglePause(); break;
            case A::SeekBack5m:  playerRestartSeek(-300); break;
            case A::SeekBack30:  playerRestartSeek(-30);  break;
            case A::SeekFwd30:   playerRestartSeek(+30);  break;
            case A::SeekFwd5m:   playerRestartSeek(+300); break;
            case A::Prev:        playerGoPrev();      break;
            case A::Next:        playerGoNext();      break;
            case A::OpenAudio:   if (osd_) osd_->openAudioMenu(); break;
            case A::OpenSub:     if (osd_) osd_->openSubMenu();   break;
            case A::ToggleMute:  playerToggleMute();  break;
            case A::Close:       exitPlayer();        break;
            default: break;
        }
    }

    void render() {
        // NDL PoC: si une vidéo HW est en cours, on clear le framebuffer
        // SDL en alpha=0 pour laisser passer le plan overlay NDL par dessous.
        // Mais on NE retourne PLUS après : on laisse ensuite l'OSD et les
        // boutons de contrôle se dessiner par-dessus (sinon aucun bouton
        // n'apparaît quand la vidéo joue — bug #BACK-invisible).
        if (ndl_ && !ndl_->hasError()) {
            SDL_SetRenderDrawBlendMode(renderer_, SDL_BLENDMODE_NONE);
            SDL_SetRenderDrawColor(renderer_, 0, 0, 0, 0);
            SDL_RenderClear(renderer_);
            // Dessine l'OSD + les boutons Player par-dessus le plan NDL.
            // L'OSD/barre est affichée tant que `osd_->isVisible()` (poke
            // au démarrage + à chaque touche, auto-hide après ~5s). Le
            // menu audio, lui, reste tant qu'ouvert.
            if (screen_ == Screen::Player && osd_) {
                SDL_SetRenderDrawBlendMode(renderer_, SDL_BLENDMODE_BLEND);
                osd_->setPlaying(!player_paused_);
                osd_->render(renderer_, kWidth, kHeight);
            }
            if (player_error_until_ > SDL_GetTicks()) renderPlayerError();
            if (sync_active_) renderSyncOverlay();
            return;
        }
        // Testbench idle screen : entre deux tests on reste sur Player sans
        // décodeur. Fond très sombre + carré bleu qui rebondit sur tout
        // l'écran. Pas de texte fixe (burn-in OLED). La luminance moyenne
        // reste basse → evaluate_frames marquera "idle" pas "playing".
        if (testbench_mode_ && screen_ == Screen::Player && !decoder_ && !ndl_ && !sw_) {
            SDL_SetRenderDrawColor(renderer_, 4, 4, 8, 255);
            SDL_RenderClear(renderer_);
            const int kSize = 60;
            const int kSpanX = kWidth - kSize;
            const int kSpanY = kHeight - kSize;
            // Lissajous-like path : vitesses X et Y différentes, premières
            // repasses jamais au même endroit, couverture uniforme.
            uint32_t t = SDL_GetTicks();
            int rawX = (t / 5)  % (2 * kSpanX);
            int rawY = (t / 7)  % (2 * kSpanY);
            int x = (rawX < kSpanX) ? rawX : (2 * kSpanX - rawX);
            int y = (rawY < kSpanY) ? rawY : (2 * kSpanY - rawY);
            SDL_SetRenderDrawColor(renderer_, 60, 120, 200, 255);
            SDL_Rect r{x, y, kSize, kSize};
            SDL_RenderFillRect(renderer_, &r);
            return;
        }
        // Update screensaver state : activé si idle et pas de lecture vidéo.
        uint32_t now_ms = SDL_GetTicks();
        if (!screensaver_active_ && screen_ != Screen::Player &&
            last_input_ticks_ != 0 &&
            now_ms - last_input_ticks_ > kScreensaverIdleMs) {
            screensaver_active_ = true;
            SDL_Log("[screensaver] ON après %ums idle (screen=%d)",
                    now_ms - last_input_ticks_, (int)screen_);
        }
        if (screensaver_active_) {
            renderScreensaver(now_ms);
            return;
        }

        SDL_SetRenderDrawColor(renderer_, 0, 0, 0, 255);
        SDL_RenderClear(renderer_);
        switch (screen_) {
            case Screen::Settings: settings_->render(renderer_, kWidth, kHeight); break;
            case Screen::Filter:   if (catalogFilter_) catalogFilter_->render(renderer_, kWidth, kHeight); break;
            case Screen::Home:     home_->render(renderer_, kWidth, kHeight); break;
            case Screen::Series:   if (seriesScreen_) seriesScreen_->render(renderer_, kWidth, kHeight); break;
            case Screen::Player:   renderPlayer(); break;
            default: break;
        }
        if (sync_active_) renderSyncOverlay();
        if (player_error_until_ > SDL_GetTicks()) renderPlayerError();
        if (exit_confirm_open_) renderExitConfirm();
        if (seek_dialog_open_) renderSeekDialog();
    }

    // Formatage HH:MM:SS (ou MM:SS si < 1h) pour affichage timer.
    static std::string fmtHMS(int s) {
        if (s < 0) s = 0;
        int h = s / 3600, m = (s % 3600) / 60, sec = s % 60;
        char buf[16];
        if (h > 0) std::snprintf(buf, sizeof(buf), "%d:%02d:%02d", h, m, sec);
        else       std::snprintf(buf, sizeof(buf), "%d:%02d", m, sec);
        return buf;
    }

    // Modale "Aller à" — sélection de timer pour relance. Voile + panneau
    // central avec temps courant / durée + hints keymap.
    void renderSeekDialog() {
        SDL_SetRenderDrawBlendMode(renderer_, SDL_BLENDMODE_BLEND);
        // Voile : ne recouvre PAS la zone OSD bas d'écran (260 px) pour que
        // l'utilisateur voie la barre de défilement + le timer bouger quand
        // il règle la cible.
        const int kOsdZoneH = 260;
        SDL_SetRenderDrawColor(renderer_, 0, 0, 0, 200);
        SDL_Rect veil{0, 0, kWidth, kHeight - kOsdZoneH};
        SDL_RenderFillRect(renderer_, &veil);

        const int panelW = 860, panelH = 320;
        SDL_Rect panel{(kWidth - panelW) / 2, (kHeight - panelH) / 2,
                       panelW, panelH};
        iptv::ui::draw::fillRoundedRect(renderer_, panel, 16,
                                        SDL_Color{8, 12, 24, 240});
        iptv::ui::draw::strokeRoundedRect(renderer_, panel, 16, 3,
                                          iptv::ui::theme::Accent);

        // Titre
        const char* title = "Aller à";
        int tw = 0, th = 0;
        text_.measure(iptv::ui::theme::FontStyle::Xl2Bold, title, tw, th);
        text_.draw(iptv::ui::theme::FontStyle::Xl2Bold, title,
                   panel.x + (panel.w - tw) / 2, panel.y + 28,
                   iptv::ui::theme::TextPrimary);

        // Affichage timer : grosse typo au milieu.
        std::string curStr = fmtHMS(seek_dialog_target_sec_);
        std::string durStr = (seek_dialog_duration_sec_ > 0)
            ? ("  /  " + fmtHMS((int)seek_dialog_duration_sec_))
            : std::string("  /  --:--");
        std::string full = curStr + durStr;
        int fw = 0, fh = 0;
        text_.measure(iptv::ui::theme::FontStyle::Xl3Bold, full, fw, fh);
        text_.draw(iptv::ui::theme::FontStyle::Xl3Bold, full,
                   panel.x + (panel.w - fw) / 2, panel.y + 110,
                   iptv::ui::theme::Accent);

        // Hints
        const char* hint1 =
            "\xE2\x86\x90 / \xE2\x86\x92  \xC2\xB1 30s      "
            "\xE2\x86\x91 / \xE2\x86\x93  \xC2\xB1 5 min";
        const char* hint2 =
            "OK : reprendre la lecture au timer choisi    BACK : annuler";
        int hw = 0, hh = 0;
        text_.measure(iptv::ui::theme::FontStyle::MdRegular, hint1, hw, hh);
        text_.draw(iptv::ui::theme::FontStyle::MdRegular, hint1,
                   panel.x + (panel.w - hw) / 2, panel.y + panel.h - 96,
                   iptv::ui::theme::TextSecondary);
        text_.measure(iptv::ui::theme::FontStyle::MdRegular, hint2, hw, hh);
        text_.draw(iptv::ui::theme::FontStyle::MdRegular, hint2,
                   panel.x + (panel.w - hw) / 2, panel.y + panel.h - 52,
                   iptv::ui::theme::TextSecondary);
    }

    // Modal "Quitter l'application ?" déclenché par BACK sur Home. Deux
    // boutons [Non] [Oui], LEFT/RIGHT cycle, OK valide, BACK ferme.
    void renderExitConfirm() {
        namespace draw = iptv::ui::draw;
        SDL_SetRenderDrawBlendMode(renderer_, SDL_BLENDMODE_BLEND);

        // Voile noir semi-transparent pour détacher du fond.
        SDL_SetRenderDrawColor(renderer_, 0, 0, 0, 200);
        SDL_Rect veil{0, 0, kWidth, kHeight};
        SDL_RenderFillRect(renderer_, &veil);

        // Panneau centré.
        const int panelW = 640, panelH = 260;
        SDL_Rect panel{(kWidth - panelW) / 2, (kHeight - panelH) / 2,
                       panelW, panelH};
        draw::fillRoundedRect(renderer_, panel, 16, SDL_Color{8, 12, 24, 240});
        draw::strokeRoundedRect(renderer_, panel, 16, 3,
                                iptv::ui::theme::Accent);

        // Titre.
        const char* title = "Quitter l'application ?";
        int tw = 0, th = 0;
        text_.measure(iptv::ui::theme::FontStyle::XlBold, title, tw, th);
        text_.draw(iptv::ui::theme::FontStyle::XlBold, title,
                   panel.x + (panel.w - tw) / 2, panel.y + 40,
                   iptv::ui::theme::TextPrimary);

        // Deux boutons Non / Oui — style néon bleu (même esprit que l'OSD).
        const int btnW = 180, btnH = 72;
        const int btnGap = 40;
        int btnsY = panel.y + panelH - btnH - 36;
        int nonX = panel.x + (panel.w - (btnW * 2 + btnGap)) / 2;
        int ouiX = nonX + btnW + btnGap;

        auto drawBtn = [&](SDL_Rect rc, const char* label, bool focus,
                           bool danger) {
            const int radius = 12;
            SDL_Color halo = danger
                ? SDL_Color{0xff, 0x71, 0x71, 255}
                : SDL_Color{0x4a, 0x9e, 0xff, 255};
            iptv::ui::draw::glowHalo(renderer_, rc, radius, halo, focus ? 16 : 8);
            SDL_Color bg = danger
                ? (focus ? SDL_Color{0x3a, 0x08, 0x14, 235} : SDL_Color{0x1a, 0x05, 0x0a, 225})
                : (focus ? SDL_Color{0x10, 0x1e, 0x3a, 235} : SDL_Color{0x05, 0x0a, 0x1c, 220});
            iptv::ui::draw::fillRoundedRect(renderer_, rc, radius, bg);
            SDL_Color border = danger
                ? SDL_Color{0xff, 0x80, 0x80, 255}
                : (focus ? SDL_Color{0x80, 0xc8, 0xff, 255}
                          : iptv::ui::theme::Accent);
            iptv::ui::draw::strokeRoundedRect(renderer_, rc, radius, focus ? 4 : 3, border);
            int lw = 0, lh = 0;
            text_.measure(iptv::ui::theme::FontStyle::LgBold, label, lw, lh);
            SDL_Color txt = focus ? SDL_Color{255, 255, 255, 255}
                                  : SDL_Color{0xcc, 0xe4, 0xff, 255};
            text_.draw(iptv::ui::theme::FontStyle::LgBold, label,
                       rc.x + (rc.w - lw) / 2, rc.y + (rc.h - lh) / 2, txt);
        };

        drawBtn(SDL_Rect{nonX, btnsY, btnW, btnH}, "Non",
                exit_confirm_focus_ == 0, false);
        drawBtn(SDL_Rect{ouiX, btnsY, btnW, btnH}, "Oui",
                exit_confirm_focus_ == 1, true);
    }

    // Anti-burn-in OLED : fond noir + carré bleu qui se déplace doucement en
    // trajectoire Lissajous. La position parcourt tout l'écran donc aucun pixel
    // n'est sollicité de façon fixe.
    void renderScreensaver(uint32_t t_ms) {
        SDL_SetRenderDrawColor(renderer_, 0, 0, 0, 255);
        SDL_RenderClear(renderer_);
        const int sz = 80;
        float t = (float)t_ms / 1000.0f;
        // Lissajous 1:1.3 ratio — jamais répétitif, couvre tout l'écran.
        float fx = 0.5f + 0.45f * std::sin(t * 0.6f);
        float fy = 0.5f + 0.45f * std::sin(t * 0.78f + 1.1f);
        int x = (int)((kWidth - sz) * fx);
        int y = (int)((kHeight - sz) * fy);
        SDL_Rect box{x, y, sz, sz};
        // Fond accent (bleu) avec alpha plein — visible mais pas aveuglant.
        SDL_SetRenderDrawColor(renderer_, 0x4a, 0x9e, 0xff, 255);
        SDL_RenderFillRect(renderer_, &box);
    }

    void renderSyncOverlay() {
        // Bottom-right toast with the current sync phase and progress.
        std::string phase, cat; int done = 0, total = 0;
        {
            std::lock_guard<std::mutex> lk(sync_mu_);
            phase = sync_phase_;
            cat   = sync_category_;
            done  = sync_done_;
            total = sync_total_;
        }
        SDL_SetRenderDrawBlendMode(renderer_, SDL_BLENDMODE_BLEND);
        SDL_SetRenderDrawColor(renderer_, 0, 0, 0, 200);
        SDL_Rect box{kWidth - 540, kHeight - 120, 500, 80};
        SDL_RenderFillRect(renderer_, &box);
        text_.draw("Synchronisation du catalogue…", box.x + 16, box.y + 10, {230, 230, 230, 255});
        char line[256];
        std::snprintf(line, sizeof(line), "%s  %d/%d  %s",
                      phase.c_str(), done, total, cat.c_str());
        text_.draw(line, box.x + 16, box.y + 40, {180, 180, 190, 255});
    }

    void renderPlayerError() {
        SDL_SetRenderDrawBlendMode(renderer_, SDL_BLENDMODE_BLEND);
        SDL_SetRenderDrawColor(renderer_, 0, 0, 0, 220);
        SDL_Rect box{kWidth / 2 - 420, kHeight / 2 - 50, 840, 100};
        SDL_RenderFillRect(renderer_, &box);
        SDL_SetRenderDrawColor(renderer_, 220, 40, 40, 255);
        SDL_RenderDrawRect(renderer_, &box);
        text_.draw("Impossible de lire ce film", box.x + 24, box.y + 20, {240, 100, 100, 255});
        text_.draw(player_error_msg_, box.x + 24, box.y + 55, {200, 200, 200, 255});
    }

    void renderPlayer() {
        // Push the latest decoded frame into a streaming texture and render letterboxed.
        bool has_new = false;
        {
            std::lock_guard<std::mutex> g(latest_.m);
            if (latest_.dirty) {
                if (!texture_ || tex_w_ != latest_.width || tex_h_ != latest_.height) {
                    if (texture_) SDL_DestroyTexture(texture_);
                    texture_ = SDL_CreateTexture(renderer_, SDL_PIXELFORMAT_IYUV,
                                                 SDL_TEXTUREACCESS_STREAMING,
                                                 latest_.width, latest_.height);
                    tex_w_ = latest_.width; tex_h_ = latest_.height;
                }
                if (texture_) {
                    SDL_UpdateYUVTexture(texture_, nullptr,
                                         latest_.y.data(), latest_.y_stride,
                                         latest_.u.data(), latest_.u_stride,
                                         latest_.v.data(), latest_.v_stride);
                    has_new = true;
                }
                latest_.dirty = false;
            }
        }
        if (texture_) {
            float ratio = static_cast<float>(tex_w_) / static_cast<float>(tex_h_);
            int dw = kWidth, dh = static_cast<int>(kWidth / ratio);
            if (dh > kHeight) { dh = kHeight; dw = static_cast<int>(kHeight * ratio); }
            SDL_Rect dst{(kWidth - dw) / 2, (kHeight - dh) / 2, dw, dh};
            SDL_RenderCopy(renderer_, texture_, nullptr, &dst);
        }
        if (osd_) {
            osd_->setPlaying(!player_paused_);
            osd_->render(renderer_, kWidth, kHeight);
        }
        (void)has_new;
    }

    SDL_Window*   window_   = nullptr;
    SDL_Renderer* renderer_ = nullptr;
    iptv::ui::TextRenderer  text_;
    iptv::ui::ImageLoader   images_;
    iptv::ui::FocusManager  focus_;
    iptv::store::Cache      cache_;
    iptv::store::Config     config_;
    iptv::platform::AppLifecycle lifecycle_;
    std::unique_ptr<iptv::xtream::XtreamClient> client_;

    Screen screen_ = Screen::None;
    std::unique_ptr<iptv::ui::SettingsScreen>     settings_;
    std::unique_ptr<iptv::ui::CatalogFilterScreen> catalogFilter_;
    std::unique_ptr<iptv::ui::HomeScreen>         home_;
    std::unique_ptr<iptv::ui::SeriesDetailScreen> seriesScreen_;
    std::unique_ptr<iptv::ui::PlayerOSD>          osd_;

    // Player state
    std::unique_ptr<iptv::GstDecoder> decoder_;
    std::unique_ptr<iptv::NdlDecoder> ndl_;
    std::unique_ptr<iptv::SwDecoder>  sw_;

    // Optional auto-play at startup, set via setInitialStream() from main().
    std::string initial_stream_url_;
    std::string initial_stream_title_;
    std::string initial_stream_codec_;   // "auto" | "h264" | "hevc" | "mpeg4" | "msmpeg4"
    std::string initial_stream_audio_codec_;  // "" | "ac3" | "eac3" | "aac" | "mp3" | "dts"
    bool initial_stream_skip_audio_ = false;
    int initial_stream_seek_sec_ = 0;
    uint32_t pending_initial_play_ms_ = 0;  // 0 = no pending auto-play

    // Screensaver OLED anti-burn-in : après N secondes d'inactivité, on
    // remplace le rendu UI par un fond noir + un carré bleu qui se déplace.
    // Toute touche réveille (+ est consommée).
    uint32_t last_input_ticks_ = 0;
    bool screensaver_active_ = false;
    static constexpr uint32_t kScreensaverIdleMs = 30000;
    // Modal "Quitter l'application ?" : BACK sur Home l'ouvre, les autres
    // écrans retournent à Home sur BACK.
    bool exit_confirm_open_  = false;
    int  exit_confirm_focus_ = 0;  // 0 = Non (défaut), 1 = Oui
    // testbench_mode_ stays true once we've received at least one streamUrl via
    // launch params or relaunch. While true, exitPlayer() leaves the window on
    // a pure black screen instead of returning to the home grid, so the camera
    // sees a clean inter-test state.
    bool testbench_mode_ = false;
    LatestFrame latest_;
    SDL_Texture* texture_ = nullptr;
    int tex_w_ = 0, tex_h_ = 0;
    std::string playerTitle_, playerUrl_, playerItemId_, playerSeriesId_;
    double savedPosition_ = 0;
    // Transient error message shown in the player on decode failure.
    uint32_t player_error_until_ = 0;
    std::string player_error_msg_;

    // Background catalog sync — kicks in on first launch when the cache is empty.
    std::thread sync_thread_;
    std::atomic<bool> sync_abort_{false};
    std::atomic<bool> catalog_dirty_{false};
    std::atomic<bool> sync_active_{false};
    std::mutex sync_mu_;
    std::string sync_phase_;
    std::string sync_category_;
    int sync_done_ = 0;
    int sync_total_ = 0;
};

}  // namespace

// UDP debug socket (PC dev = 192.168.1.242:5555). We mirror every SDL_Log + stderr
// line over UDP so a crashing TV-side binary still leaves a trace.
namespace {
int g_diag_sock = -1;
sockaddr_in g_diag_addr{};

void diagInit() {
    g_diag_sock = socket(AF_INET, SOCK_DGRAM, 0);
    g_diag_addr.sin_family = AF_INET;
    g_diag_addr.sin_port   = htons(5555);
    inet_pton(AF_INET, "192.168.1.242", &g_diag_addr.sin_addr);
}
void diag(const char* fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    if (n < 0) return;
    if (n >= (int)sizeof(buf)) n = sizeof(buf) - 1;
    if (g_diag_sock >= 0) {
        sendto(g_diag_sock, buf, n, 0, (sockaddr*)&g_diag_addr, sizeof(g_diag_addr));
    }
    std::fwrite(buf, 1, n, stderr);
    std::fflush(stderr);
}
}  // namespace

// Mirror SDL_Log to the remote UDP log so we see all runtime messages.
static void sdlLogToUdp(void*, int /*category*/, SDL_LogPriority /*pri*/, const char* msg) {
    diag("[sdl] %s\n", msg);
}

// GLib 2.80 added g_once_init_leave_pointer (alongside the long-existing
// g_once_init_leave). On webOS 6.x's older GLib it doesn't exist. We provide
// the shim in libglib_compat.so (bundled in the IPK) and patchelf NEEDED-add
// it to libgstlibav.so — keeps the polyfill out of the main binary so the
// modern GLib header macro doesn't conflict at compile time.

// If the user config file is missing and the IPK ships a default_config.json
// next to the binary, import it once. Lets us pre-seed Xtream credentials for
// test deployments without typing on a TV keyboard.
static void seedDefaultConfigIfNeeded() {
    auto userCfg = iptv::store::Paths::configFile();
    diag("seedDefault: userCfg=%s\n", userCfg.string().c_str());
    bool needsSeed = true;
    if (std::filesystem::exists(userCfg)) {
        try {
            auto existing = iptv::store::Config::load();
            diag("seedDefault: existing serverUrl='%s' username='%s'\n",
                 existing.serverUrl.c_str(), existing.username.c_str());
            if (!existing.serverUrl.empty() && !existing.username.empty()) {
                needsSeed = false;
            }
        } catch (const std::exception& e) {
            diag("seedDefault: Config::load threw: %s\n", e.what());
        } catch (...) {
            diag("seedDefault: Config::load threw unknown\n");
        }
    }
    if (!needsSeed) { diag("seedDefault: skipping (valid config)\n"); return; }
    char* base = SDL_GetBasePath();
    if (!base) { diag("seedDefault: SDL_GetBasePath null\n"); return; }
    diag("seedDefault: basePath=%s\n", base);
    std::filesystem::path candidates[] = {
        std::filesystem::path(base) / "assets/default_config.json",
        std::filesystem::path(base) / "default_config.json",
    };
    SDL_free(base);
    std::error_code ec;
    for (const auto& src : candidates) {
        diag("seedDefault: candidate=%s exists=%d\n",
             src.string().c_str(), (int)std::filesystem::exists(src));
        if (!std::filesystem::exists(src)) continue;
        std::filesystem::create_directories(userCfg.parent_path(), ec);
        std::filesystem::copy_file(src, userCfg,
            std::filesystem::copy_options::overwrite_existing, ec);
        diag("seedDefault: copied from %s (err=%s)\n",
             src.string().c_str(), ec ? ec.message().c_str() : "ok");
        return;
    }
    diag("seedDefault: no candidate found\n");
}

int main(int argc, char* argv[]) {
    diagInit();
    diag("==== iptv-player boot, argc=%d, pid=%d ====\n", argc, getpid());
    for (int i = 0; i < argc; ++i) diag("  argv[%d]=%s\n", i, argv[i]);

    // SDL-webOS reads APPID to register with SAM. Without it, SDL_Init succeeds but
    // the compositor never raises our window over the splash, so the user keeps
    // seeing splash.png until the process exits.
    setenv("APPID", "com.iptv.player.native", 1);
    diag("APPID=%s\n", getenv("APPID"));

    // TEMP debug: restrict the home grid to a known set of MPEG-4 ASP films so
    // we can validate gst-libav decoding. Comment this line to restore the full
    // catalog (subject to the Config "frenchOnly" filter).
    setenv("IPTV_TEST_ASP_ONLY", "1", 1);

    // Tell GStreamer to also look in our bundled plugin dir (libgstlibav.so lives
    // there) so avdec_mpeg4/h265/mpeg2video become available. Append to any
    // existing path so system plugins still resolve.
    {
        char* base = SDL_GetBasePath();
        if (base) {
            std::string plugin_dir = std::string(base) + "lib/gstreamer-1.0";
            const char* existing = getenv("GST_PLUGIN_PATH");
            std::string merged = plugin_dir + (existing && *existing ? std::string(":") + existing : "");
            setenv("GST_PLUGIN_PATH", merged.c_str(), 1);
            // We also need the bundled ffmpeg/libstdc++ libs resolvable by dlopen'd
            // plugins. The binary's rpath=$ORIGIN/lib covers libs it links directly,
            // but libgstlibav.so's own NEEDED libs are resolved by the global loader.
            std::string ld_path = std::string(base) + "lib";
            const char* existing_ld = getenv("LD_LIBRARY_PATH");
            std::string merged_ld = ld_path + (existing_ld && *existing_ld ? std::string(":") + existing_ld : "");
            setenv("LD_LIBRARY_PATH", merged_ld.c_str(), 1);
            SDL_free(base);
            diag("GST_PLUGIN_PATH=%s\n", getenv("GST_PLUGIN_PATH"));
            diag("LD_LIBRARY_PATH=%s\n", getenv("LD_LIBRARY_PATH"));
        }
    }
    // Force GStreamer to rebuild its plugin registry from scratch each launch.
    // The system cache at ~/.cache/gstreamer-1.0 was built before our bundled
    // libgstlibav.so existed and never re-scans new paths on its own.
    unlink("/tmp/iptv-gst-registry.bin");
    setenv("GST_REGISTRY", "/tmp/iptv-gst-registry.bin", 1);
    setenv("GST_REGISTRY_FORK", "no", 1);
    setenv("GST_REGISTRY_UPDATE", "yes", 1);
    // Verbose plugin loader so we see WHY libgstlibav.so is rejected if it is.
    // Output goes through stderr → /tmp/iptv_native.log on the TV.
    setenv("GST_DEBUG", "GST_PLUGIN_LOADING:5,GST_REGISTRY:4", 1);
    setenv("GST_DEBUG_NO_COLOR", "1", 1);

    // Capture stdout/stderr to disk for post-mortem on the TV (SAM swallows them).
    std::freopen("/tmp/iptv_native.log", "w", stderr);
    std::setvbuf(stderr, nullptr, _IOLBF, 0);
    // Tap SDL_Log so every internal message lands on the UDP stream.
    SDL_LogSetOutputFunction(sdlLogToUdp, nullptr);
    SDL_LogSetAllPriority(SDL_LOG_PRIORITY_VERBOSE);
    diag("freopen stderr -> /tmp/iptv_native.log done\n");

    if (argc >= 2 && std::string(argv[1]) == "xtream") return xtreamTest(argc, argv);
    if (argc >= 2 && std::string(argv[1]) == "store")  return storeTest();
    if (argc >= 2 && std::string(argv[1]) == "sync")   return syncTest();
    if (argc >= 2 && std::string(argv[1]) == "play" && argc >= 3) return playFile(argv[2]);
    // Only treat argv[1] as a file path when it's not a SAM-style JSON launch payload
    // (SAM passes something like {"@system_native_app":true,...} as argv[1]).
    if (argc >= 2 && argv[1][0] != '-' && argv[1][0] != '{') return playFile(argv[1]);
    diag("dataDir=%s\n", iptv::store::Paths::dataDir().string().c_str());
    seedDefaultConfigIfNeeded();
    diag("launching GUI App\n");
    App app;

    // SAM launch payload: argv[1] is a JSON when launched via ares-launch -p
    // '{"streamUrl":"...","title":"..."}'. The testbench uses this to drive
    // the app to a specific stream without a human on the remote.
    if (argc >= 2 && argv[1][0] == '{') {
        try {
            auto payload = nlohmann::json::parse(argv[1]);
            std::string url = payload.value("streamUrl", std::string{});
            std::string title = payload.value("title", std::string{});
            if (!url.empty()) {
                diag("SAM launch param streamUrl=%s title=%s\n",
                     url.c_str(), title.c_str());
                app.setInitialStream(url, title);
            }
        } catch (const std::exception& e) {
            diag("SAM payload parse failed: %s\n", e.what());
        }
    }

    diag("App constructed, calling run()\n");
    int rc = app.run();
    diag("App.run() returned %d\n", rc);
    return rc;
}

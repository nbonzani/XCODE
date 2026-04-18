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
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <filesystem>
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
#include "player/Playlist.h"
#include "store/Cache.h"
#include "store/Config.h"
#include "store/Favorites.h"
#include "store/Paths.h"
#include "store/WatchHistory.h"
#include "store/WatchPosition.h"
#include "ui/FocusManager.h"
#include "ui/HomeScreen.h"
#include "ui/ImageLoader.h"
#include "ui/PlayerOSD.h"
#include "ui/PosterGrid.h"
#include "ui/SeriesDetailScreen.h"
#include "ui/SettingsScreen.h"
#include "ui/TextRenderer.h"
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
    int run() {
        SDL_Log("App::run() entering");
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
        SDL_Log("Lifecycle started");

        config_ = iptv::store::Config::load();
        SDL_Log("Config loaded: server=%s user=%s", config_.serverUrl.c_str(), config_.username.c_str());
        recreateXtreamClient();

        settings_ = std::make_unique<iptv::ui::SettingsScreen>(text_, focus_);
        settings_->setOnSave([this]{ config_ = iptv::store::Config::load();
                                     recreateXtreamClient(); gotoHome(); });
        settings_->setOnCancel([this]{ if (!config_.serverUrl.empty()) gotoHome(); });

        home_ = std::make_unique<iptv::ui::HomeScreen>(text_, focus_, images_, cache_);
        home_->setOnOpenMovie([this](const std::string& sid) { onOpenMovie(sid); });
        home_->setOnOpenSeries([this](const std::string& sid){ onOpenSeries(sid); });
        home_->setOnOpenSettings([this]{ gotoSettings(); });

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

        SDL_Log("Entering main loop");
        return loop();
    }

    ~App() {
        sync_abort_ = true;
        if (sync_thread_.joinable()) sync_thread_.join();
        if (decoder_) decoder_->stop();
        lifecycle_.stop();
        text_.clear();
        images_.stop();
        if (renderer_) SDL_DestroyRenderer(renderer_);
        if (window_) SDL_DestroyWindow(window_);
        SDL_Quit();
    }

private:
    enum class Screen { None, Settings, Home, Series, Player };

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

    void gotoSettings() {
        screen_ = Screen::Settings;
        focus_.clear();
        settings_->load();
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
        if (!client_) { SDL_Log("onOpenMovie: no client"); return; }
        std::string ext = "mkv";
        std::string title = "Film";
        try {
            SDL_Log("onOpenMovie: calling getVodInfo (blocking)");
            auto info = client_->getVodInfo(streamId);
            SDL_Log("onOpenMovie: getVodInfo ok, parsing");
            // Xtream returns either "info" or "movie_data" — try both.
            for (const char* k : {"info", "movie_data"}) {
                if (!info.contains(k) || !info[k].is_object()) continue;
                const auto& md = info[k];
                if (md.contains("container_extension") && md["container_extension"].is_string()) {
                    ext = md["container_extension"].get<std::string>();
                }
                if (md.contains("name") && md["name"].is_string()) {
                    title = md["name"].get<std::string>();
                }
                break;
            }
        } catch (const std::exception& e) {
            std::fprintf(stderr, "[router] getVodInfo failed (%s) — using defaults\n", e.what());
        }
        std::string url = client_->getStreamUrl(streamId, ext);
        SDL_Log("onOpenMovie: url=%s ext=%s title=%s", url.c_str(), ext.c_str(), title.c_str());
        playUrl(url, streamId, "", title);
    }
    void onOpenSeries(const std::string& seriesId) {
        if (!client_) { std::fprintf(stderr, "[router] no Xtream client configured\n"); return; }
        if (!seriesScreen_) {
            seriesScreen_ = std::make_unique<iptv::ui::SeriesDetailScreen>(text_, focus_, *client_);
            seriesScreen_->setOnBack([this]{ gotoHome(); });
            seriesScreen_->setOnPlay([this](const std::string& url, const std::string& epId,
                                            const std::string& sid, const std::string& title) {
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
        playerTitle_ = title;
        playerUrl_   = url;
        playerItemId_ = itemId;
        playerSeriesId_ = seriesId;
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
        osd_->poke();

        lifecycle_.acquireWakeLock("playback");
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
        if (texture_) { SDL_DestroyTexture(texture_); texture_ = nullptr; tex_w_ = tex_h_ = 0; }
        lifecycle_.releaseWakeLock();
        screen_ = playerSeriesId_.empty() ? Screen::Home : Screen::Series;
    }

    int loop() {
        diag("loop() ENTERED\n");
        GMainContext* ctx = g_main_context_default();
        bool running = true;
        int tick = 0;
        diag("loop() before while\n");
        while (running) {
            // Pump GLib only while a GstDecoder is active — SDL-webOS otherwise
            // floods the default context with Luna callbacks that livelock us.
            // Capped at 4 iterations per frame so SDL events keep flowing.
            if (decoder_) {
                for (int i = 0; i < 4 && g_main_context_iteration(ctx, FALSE); ++i) {}
            }
            ++tick;

            SDL_Event ev;
            while (SDL_PollEvent(&ev)) {
                if (ev.type == SDL_QUIT) running = false;
                if (ev.type == SDL_KEYDOWN) {
                    int k = ev.key.keysym.sym;
                    if (iptv::app::isExitKey(k)) { running = false; continue; }
                    handleKey(k);
                } else if (ev.type == SDL_TEXTINPUT && screen_ == Screen::Settings) {
                    settings_->handleText(ev.text.text);
                }
            }

            images_.pump();
            // Re-read cache when the background sync flips the dirty flag.
            if (catalog_dirty_.exchange(false) && screen_ == Screen::Home) {
                SDL_Log("catalog dirty -> reloading HomeScreen");
                home_->load();
            }
            if (screen_ == Screen::Player && decoder_) {
                if (savedPosition_ > 5 && decoder_->durationSeconds() > savedPosition_ + 5) {
                    decoder_->seekSeconds(savedPosition_);
                    savedPosition_ = 0;
                }
                osd_->setProgress(decoder_->positionSeconds(), decoder_->durationSeconds());
                osd_->tick(SDL_GetTicks());
                if (decoder_->eos() || decoder_->hasError()) exitPlayer();
            }

            render();
            SDL_RenderPresent(renderer_);
        }
        return 0;
    }

    void handleKey(int k) {
        bool handled = false;
        switch (screen_) {
            case Screen::Settings: settings_->handleKey(k, handled); break;
            case Screen::Home:     home_->handleKey(k, handled); break;
            case Screen::Series:   if (seriesScreen_) seriesScreen_->handleKey(k, handled); break;
            case Screen::Player:   handlePlayerKey(k, handled); break;
            default: break;
        }
        if (!handled && iptv::app::isBackKey(k)) {
            if (screen_ == Screen::Series)      gotoHome();
            else if (screen_ == Screen::Player) exitPlayer();
            else if (screen_ == Screen::Home)   gotoSettings();
        }
    }

    void handlePlayerKey(int k, bool& handled) {
        if (!decoder_) return;
        handled = true;
        osd_->poke();
        if (k == iptv::app::KEY::PLAY_PAUSE) {
            if (osd_->isVisible() && /*paused*/ false) decoder_->play();
            else decoder_->pause();
        } else if (k == iptv::app::KEY::FF) {
            decoder_->seekRelative(+300);
        } else if (k == iptv::app::KEY::REW) {
            decoder_->seekRelative(-300);
        } else if (k == iptv::app::KEY::RIGHT) {
            decoder_->seekRelative(+10);
        } else if (k == iptv::app::KEY::LEFT) {
            decoder_->seekRelative(-10);
        } else if (k == iptv::app::KEY::STOP) {
            exitPlayer();
        } else if (iptv::app::isBackKey(k) || iptv::app::isOkKey(k)) {
            handled = false;  // fall through to back handling
        }
    }

    void render() {
        SDL_SetRenderDrawColor(renderer_, 0, 0, 0, 255);
        SDL_RenderClear(renderer_);
        switch (screen_) {
            case Screen::Settings: settings_->render(renderer_, kWidth, kHeight); break;
            case Screen::Home:     home_->render(renderer_, kWidth, kHeight); break;
            case Screen::Series:   if (seriesScreen_) seriesScreen_->render(renderer_, kWidth, kHeight); break;
            case Screen::Player:   renderPlayer(); break;
            default: break;
        }
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
        if (osd_) osd_->render(renderer_, kWidth, kHeight);
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
    std::unique_ptr<iptv::ui::HomeScreen>         home_;
    std::unique_ptr<iptv::ui::SeriesDetailScreen> seriesScreen_;
    std::unique_ptr<iptv::ui::PlayerOSD>          osd_;

    // Player state
    std::unique_ptr<iptv::GstDecoder> decoder_;
    LatestFrame latest_;
    SDL_Texture* texture_ = nullptr;
    int tex_w_ = 0, tex_h_ = 0;
    std::string playerTitle_, playerUrl_, playerItemId_, playerSeriesId_;
    double savedPosition_ = 0;

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

// If the user config file is missing and the IPK ships a default_config.json
// next to the binary, import it once. Lets us pre-seed Xtream credentials for
// test deployments without typing on a TV keyboard.
static void seedDefaultConfigIfNeeded() {
    auto userCfg = iptv::store::Paths::configFile();
    if (std::filesystem::exists(userCfg)) return;
    char* base = SDL_GetBasePath();
    if (!base) return;
    std::filesystem::path candidates[] = {
        std::filesystem::path(base) / "assets/default_config.json",
        std::filesystem::path(base) / "default_config.json",
    };
    SDL_free(base);
    std::error_code ec;
    for (const auto& src : candidates) {
        if (!std::filesystem::exists(src)) continue;
        std::filesystem::create_directories(userCfg.parent_path(), ec);
        std::filesystem::copy_file(src, userCfg,
            std::filesystem::copy_options::overwrite_existing, ec);
        diag("seeded user config from %s (err=%s)\n",
             src.string().c_str(), ec ? ec.message().c_str() : "ok");
        return;
    }
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
    diag("App constructed, calling run()\n");
    int rc = app.run();
    diag("App.run() returned %d\n", rc);
    return rc;
}

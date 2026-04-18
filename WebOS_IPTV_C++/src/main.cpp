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
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

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

namespace {

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
        if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS | SDL_INIT_AUDIO) != 0) {
            std::fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
            return 1;
        }
        window_ = SDL_CreateWindow(
            "IPTV Native", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED,
            kWidth, kHeight, SDL_WINDOW_FULLSCREEN);
        if (!window_) { std::fprintf(stderr, "Window: %s\n", SDL_GetError()); return 1; }
        renderer_ = SDL_CreateRenderer(window_, -1,
            SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
        if (!renderer_) { std::fprintf(stderr, "Renderer: %s\n", SDL_GetError()); return 1; }

        std::string fontPath = resolveFontPath();
        if (fontPath.empty()) {
            std::fprintf(stderr, "Aucune font TTF trouvée — abandon\n");
            return 1;
        }
        if (!text_.init(renderer_, fontPath, 24)) return 1;

        images_.start(renderer_, 2);
        cache_.open();

        lifecycle_.start("com.iptv.player.native");

        config_ = iptv::store::Config::load();
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
            gotoSettings();
        } else {
            gotoHome();
        }

        return loop();
    }

    ~App() {
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
        if (!client_) return;
        std::string ext = "mkv";
        std::string title = "Film";
        try {
            auto info = client_->getVodInfo(streamId);
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

    void playUrl(const std::string& url, const std::string& itemId,
                 const std::string& seriesId, const std::string& title) {
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
        if (!decoder_->open(url)) {
            std::fprintf(stderr, "decoder.open(%s) failed: %s\n",
                         url.c_str(), decoder_->lastError().c_str());
            screen_ = Screen::Home;
            decoder_.reset();
            return;
        }
        decoder_->play();

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
        GMainContext* ctx = g_main_context_default();
        bool running = true;
        while (running) {
            // Pump GLib (GstDecoder, AppLifecycle).
            while (g_main_context_iteration(ctx, FALSE)) {}

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
        switch (k) {
            case iptv::app::KEY::PLAY_PAUSE:
            case iptv::app::KEY::PLAY:
            case iptv::app::KEY::PAUSE:
                if (osd_->isVisible() && /*paused*/ false) decoder_->play();
                else decoder_->pause();
                break;
            case iptv::app::KEY::FF:
                decoder_->seekRelative(+300); break;
            case iptv::app::KEY::REW:
                decoder_->seekRelative(-300); break;
            case iptv::app::KEY::RIGHT:
                decoder_->seekRelative(+10); break;
            case iptv::app::KEY::LEFT:
                decoder_->seekRelative(-10); break;
            case iptv::app::KEY::STOP:
                exitPlayer(); break;
            default:
                if (iptv::app::isBackKey(k) || iptv::app::isOkKey(k)) {
                    handled = false;  // fall through to back handling
                }
                break;
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
};

}  // namespace

int main(int argc, char* argv[]) {
    if (argc >= 2 && std::string(argv[1]) == "xtream") return xtreamTest(argc, argv);
    if (argc >= 2 && std::string(argv[1]) == "store")  return storeTest();
    if (argc >= 2 && std::string(argv[1]) == "sync")   return syncTest();
    if (argc >= 2 && std::string(argv[1]) == "play" && argc >= 3) return playFile(argv[2]);
    if (argc >= 2 && argv[1][0] != '-') return playFile(argv[1]);  // legacy positional
    App app;
    return app.run();
}

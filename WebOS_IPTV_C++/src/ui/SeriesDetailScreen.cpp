#include "ui/SeriesDetailScreen.h"

#include <algorithm>
#include <cstdio>

#include <SDL2/SDL.h>

#include "app/KeyCodes.h"
#include "store/WatchHistory.h"
#include "ui/FocusManager.h"
#include "ui/TextRenderer.h"
#include "xtream/XtreamClient.h"

namespace iptv::ui {

namespace {
constexpr int kHeaderH = 260;
constexpr int kRowH    = 58;
}

SeriesDetailScreen::SeriesDetailScreen(TextRenderer& t, FocusManager& f,
                                       xtream::XtreamClient& c)
    : text_(t), focus_(f), client_(c) {}

void SeriesDetailScreen::load(const std::string& seriesId) {
    seriesId_ = seriesId;
    flat_.clear();
    info_ = {};
    error_.clear();
    loading_ = true;
    try {
        info_ = client_.getSeriesInfo(seriesId);
        loading_ = false;
        for (const auto& season : info_.seasons) {
            for (std::size_t i = 0; i < season.episodes.size(); ++i) {
                EpisodeRef ref;
                ref.seasonNum  = season.season_number;
                ref.episodeIdx = i;
                ref.focusId    = "ep_" + std::to_string(season.season_number) + "_" +
                                 std::to_string(i);
                flat_.push_back(std::move(ref));
            }
        }
    } catch (const std::exception& e) {
        loading_ = false;
        error_ = e.what();
    }
    scroll_ = 0;
    registerFocus();
}

void SeriesDetailScreen::registerFocus() {
    focus_.clear();
    int y = kHeaderH;
    for (auto& r : flat_) {
        FocusNode n;
        n.id = r.focusId;
        n.x = 80;
        n.y = y - scroll_;
        n.w = 1700;
        n.h = kRowH - 6;
        const auto& season  = info_.seasons[r.seasonNum ? r.seasonNum : 0];
        // Find the exact season by number — we can't assume seasonNum == index.
        const xtream::Season* matched = nullptr;
        for (const auto& s : info_.seasons) if (s.season_number == r.seasonNum) { matched = &s; break; }
        if (!matched) matched = &season;
        const auto& ep = matched->episodes[r.episodeIdx];
        std::string url = client_.getEpisodeUrl(ep.id, ep.container_extension);
        std::string title = "S" + std::to_string(r.seasonNum) + "E" +
                            std::to_string(ep.episode_num) + " — " + ep.title;
        std::string epId = ep.id;
        std::string seriesId = seriesId_;
        n.onOk = [this, url, epId, seriesId, title] {
            store::WatchHistory::markEpisodeWatched(epId, seriesId);
            store::WatchHistory::setLastWatchedSeries(
                seriesId, info_.series.name, title, epId, url);
            if (on_play_) on_play_(url, epId, seriesId, title);
        };
        focus_.add(std::move(n));
        y += kRowH;
    }
}

void SeriesDetailScreen::handleKey(int code, bool& handled) {
    handled = true;
    if (app::isBackKey(code)) { if (on_back_) on_back_(); return; }
    if (code == app::KEY::UP)    { focus_.moveUp();
        // Scroll up if needed
        if (const FocusNode* n = focus_.find(focus_.focused()); n && n->y < kHeaderH) {
            scroll_ -= kRowH;
            if (scroll_ < 0) scroll_ = 0;
            registerFocus();
        }
        return;
    }
    if (code == app::KEY::DOWN)  { focus_.moveDown();
        if (const FocusNode* n = focus_.find(focus_.focused()); n && n->y + n->h > 1080) {
            scroll_ += kRowH;
            registerFocus();
        }
        return;
    }
    if (app::isOkKey(code))      { focus_.activate();  return; }
    handled = false;
}

void SeriesDetailScreen::render(SDL_Renderer* r, int winW, int winH) {
    (void)winW;
    SDL_SetRenderDrawColor(r, 12, 12, 16, 255);
    SDL_RenderClear(r);

    text_.draw(info_.series.name.empty() ? seriesId_ : info_.series.name,
               80, 40, {240, 240, 240, 255});
    if (!info_.series.genre.empty()) {
        text_.draw(info_.series.genre, 80, 100, {180, 180, 190, 255});
    }
    if (loading_) text_.draw("Chargement…", 80, 160, {180, 180, 190, 255});
    if (!error_.empty()) text_.draw("Erreur: " + error_, 80, 160, {220, 60, 60, 255});
    text_.draw("[RETOUR] Retour", 80, 200, {140, 140, 150, 255});

    // Render episode rows.
    SDL_Rect clip{0, kHeaderH - 4, winW, winH - kHeaderH};
    SDL_RenderSetClipRect(r, &clip);
    int y = kHeaderH - scroll_;
    for (const auto& er : flat_) {
        if (y + kRowH >= kHeaderH && y < winH) {
            SDL_SetRenderDrawColor(r, 22, 22, 28, 255);
            SDL_Rect row{80, y, 1700, kRowH - 6};
            SDL_RenderFillRect(r, &row);
            const xtream::Season* matched = nullptr;
            for (const auto& s : info_.seasons) if (s.season_number == er.seasonNum) { matched = &s; break; }
            if (matched) {
                const auto& ep = matched->episodes[er.episodeIdx];
                char buf[64];
                std::snprintf(buf, sizeof(buf), "S%02dE%02d",
                              er.seasonNum, ep.episode_num);
                text_.draw(buf, 100, y + 14, {200, 200, 210, 255});
                text_.draw(ep.title, 220, y + 14, {230, 230, 230, 255});
            }
            if (focus_.focused() == er.focusId) {
                SDL_SetRenderDrawColor(r, 220, 40, 40, 255);
                for (int k = 0; k < 3; ++k) {
                    SDL_Rect ro{80 - k, y - k, 1700 + 2*k, kRowH - 6 + 2*k};
                    SDL_RenderDrawRect(r, &ro);
                }
            }
        }
        y += kRowH;
    }
    SDL_RenderSetClipRect(r, nullptr);
}

}  // namespace iptv::ui

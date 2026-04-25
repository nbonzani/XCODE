#include "ui/SeriesDetailScreen.h"

#include <algorithm>
#include <cstdio>

#include <SDL2/SDL.h>
#include <SDL2/SDL_render.h>

#include "app/KeyCodes.h"
#include "store/WatchHistory.h"
#include "store/WatchPosition.h"
#include "ui/Draw.h"
#include "ui/FocusManager.h"
#include "ui/ImageLoader.h"
#include "ui/TextRenderer.h"
#include "ui/Theme.h"
#include "xtream/XtreamClient.h"

namespace iptv::ui {

namespace {
constexpr int kHeaderH = 80;
constexpr int kPosterW = 340;
constexpr int kPosterH = 510;
constexpr int kLeftPad = theme::GridPaddingH;
constexpr int kLeftColW = kPosterW;
constexpr int kEpisodeRowH = 70;
constexpr int kSeasonTabH = 56;
}

SeriesDetailScreen::SeriesDetailScreen(TextRenderer& t, FocusManager& f,
                                       ImageLoader& il, xtream::XtreamClient& c)
    : text_(t), focus_(f), images_(il), client_(c) {
    (void)focus_;
}

SeriesDetailScreen::~SeriesDetailScreen() {
    if (poster_tex_) SDL_DestroyTexture(poster_tex_);
}

const xtream::Season* SeriesDetailScreen::seasonAtIndex(int idx) const {
    if (idx < 0 || idx >= (int)info_.seasons.size()) return nullptr;
    return &info_.seasons[idx];
}

const std::vector<xtream::Episode>& SeriesDetailScreen::currentEpisodes() const {
    static const std::vector<xtream::Episode> kEmpty;
    const auto* s = seasonAtIndex(seasonIdx_);
    return s ? s->episodes : kEmpty;
}

int SeriesDetailScreen::currentSeasonNumber() const {
    const auto* s = seasonAtIndex(seasonIdx_);
    return s ? s->season_number : 0;
}

void SeriesDetailScreen::load(const std::string& seriesId) {
    seriesId_ = seriesId;
    info_ = {};
    error_.clear();
    loading_ = true;
    zone_ = Zone::Episodes;
    seasonIdx_ = 0;
    episodeIdx_ = 0;
    scrollRowY_ = 0;
    try {
        info_ = client_.getSeriesInfo(seriesId);
        loading_ = false;
    } catch (const std::exception& e) {
        loading_ = false;
        error_ = e.what();
    }
    watched_set_ = store::WatchHistory::getWatchedEpisodesSet(seriesId);
    // Focus initial sur l'épisode demandé (venu du resume band) si trouvé
    if (!initial_episode_id_.empty()) {
        for (size_t s = 0; s < info_.seasons.size(); ++s) {
            const auto& eps = info_.seasons[s].episodes;
            for (size_t i = 0; i < eps.size(); ++i) {
                if (eps[i].id == initial_episode_id_) {
                    seasonIdx_ = (int)s;
                    episodeIdx_ = (int)i;
                    break;
                }
            }
        }
        initial_episode_id_.clear();
    } else {
        // Sinon : focus sur le premier épisode non-vu de la saison courante
        // (reprise naturelle). Si tous vus, on laisse le focus sur le dernier.
        const auto& eps = currentEpisodes();
        if (!eps.empty() && !watched_set_.empty()) {
            int firstUnwatched = -1;
            for (size_t i = 0; i < eps.size(); ++i) {
                if (watched_set_.find(eps[i].id) == watched_set_.end()) {
                    firstUnwatched = (int)i;
                    break;
                }
            }
            if (firstUnwatched >= 0) episodeIdx_ = firstUnwatched;
            else                     episodeIdx_ = (int)eps.size() - 1;
        }
    }
}

void SeriesDetailScreen::handleKey(int code, bool& handled) {
    handled = true;
    if (app::isBackKey(code)) { if (on_back_) on_back_(); return; }
    if (zone_ == Zone::Header) {
        if (code == app::KEY::DOWN)     { zone_ = Zone::Seasons; return; }
        if (app::isOkKey(code))         { if (on_back_) on_back_(); return; }
        return;
    }
    if (zone_ == Zone::Seasons) {
        if (code == app::KEY::LEFT)  { if (seasonIdx_ > 0) seasonIdx_--; episodeIdx_ = 0; return; }
        if (code == app::KEY::RIGHT) { if (seasonIdx_ + 1 < totalSeasons()) seasonIdx_++; episodeIdx_ = 0; return; }
        if (code == app::KEY::UP)    { zone_ = Zone::Header; return; }
        if (code == app::KEY::DOWN)  { zone_ = Zone::Episodes; return; }
        if (app::isOkKey(code))      { /* saison déjà active */ return; }
        return;
    }
    // Zone::Episodes
    const auto& eps = currentEpisodes();
    if (eps.empty()) {
        if (code == app::KEY::UP) { zone_ = Zone::Seasons; return; }
        return;
    }
    if (code == app::KEY::UP) {
        if (episodeIdx_ == 0) { zone_ = Zone::Seasons; return; }
        episodeIdx_--;
        return;
    }
    if (code == app::KEY::DOWN) {
        if (episodeIdx_ + 1 < (int)eps.size()) episodeIdx_++;
        return;
    }
    if (app::isOkKey(code)) {
        const auto& ep = eps[episodeIdx_];
        std::string url = client_.getEpisodeUrl(ep.id, ep.container_extension);
        // Extrait les codecs audio/vidéo de l'épisode depuis l'info Xtream
        // pour router correctement :
        //   video : hevc/h265 → NDL H.265, h264/avc → NDL H.264,
        //           mpeg4 → SwDecoder, autre → GstDecoder playbin (auto).
        //   audio : aac/ac3/eac3/mp3/mp2 forcent une chaîne statique côté NDL.
        std::string audio_codec;
        std::string video_codec;
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
                        audio_codec = (c == "mp2") ? std::string("mp3") : c;
                    } else if (c == "dts" || c == "dca" || c == "truehd" ||
                               c == "mlp") {
                        // Token conventionnel "dts" = codec non décodable
                        // → main.cpp convertit en skip_audio=true.
                        audio_codec = "dts";
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
        } catch (...) {}
        char buf[128];
        std::snprintf(buf, sizeof(buf), "S%02dE%02d - %s",
                      info_.seasons[seasonIdx_].season_number, ep.episode_num,
                      ep.title.c_str());
        store::WatchHistory::markEpisodeWatched(ep.id, seriesId_);
        store::WatchHistory::setLastWatchedSeries(
            seriesId_, info_.series.name, buf, ep.id, url);
        if (on_play_) on_play_(url, ep.id, seriesId_, buf, audio_codec, video_codec);
        return;
    }
    handled = false;
}

void SeriesDetailScreen::render(SDL_Renderer* r, int winW, int winH) {
    draw::fillRect(r, {0, 0, winW, winH}, theme::BgPrimary);

    // Header haut : bouton retour focusable + titre
    SDL_Rect top{0, 0, winW, kHeaderH};
    draw::fillRect(r, top, theme::SurfaceToolbar);
    draw::hLine(r, 0, kHeaderH - 1, winW, theme::Divider);
    {
        const std::string label = "<  Retour";
        int tw = 0, th = 0;
        text_.measure(theme::FontStyle::LgBold, label, tw, th);
        SDL_Rect btn{kLeftPad - 12, 18, tw + 24, 44};
        const bool focus = (zone_ == Zone::Header);
        if (focus) {
            draw::fillRoundedRect(r, btn, theme::RadiusMd,
                                  theme::withAlpha(theme::Accent, 36));
            draw::strokeRoundedRect(r, btn, theme::RadiusMd, 2, theme::Accent);
        }
        text_.draw(theme::FontStyle::LgBold, label,
                   btn.x + 12, btn.y + (btn.h - th) / 2,
                   focus ? theme::TextPrimary : theme::TextPrimary);
    }
    if (loading_) {
        text_.draw(theme::FontStyle::MdRegular, "Chargement...",
                   winW / 2 - 80, 28, theme::TextSecondary);
        return;
    }
    if (!error_.empty()) {
        text_.draw(theme::FontStyle::MdRegular, "Erreur: " + error_,
                   winW / 2 - 200, 28, theme::Error);
        return;
    }

    int contentY = kHeaderH + 16;

    // Colonne gauche : poster + infos série
    SDL_Rect poster{kLeftPad, contentY, kPosterW, kPosterH};
    draw::fillRoundedRect(r, poster, theme::RadiusMd, theme::SurfaceCard);

    // Demander le poster au ImageLoader (cover / poster_url série) si pas déjà
    // fait, puis le rendre en respectant le ratio source.
    const std::string& wantUrl = info_.series.cover;
    if (!wantUrl.empty() && wantUrl != poster_url_) {
        // URL a changé (load d'une autre série), reset
        if (poster_tex_) { SDL_DestroyTexture(poster_tex_); poster_tex_ = nullptr; }
        poster_url_ = wantUrl;
        poster_requested_ = false;
    }
    if (!poster_url_.empty() && !poster_requested_ && !poster_tex_) {
        poster_requested_ = true;
        images_.request(poster_url_, [this](SDL_Texture* tex, int, int) {
            if (poster_tex_) SDL_DestroyTexture(poster_tex_);
            poster_tex_ = tex;
        });
    }
    if (poster_tex_) {
        int tw = 0, th = 0;
        SDL_QueryTexture(poster_tex_, nullptr, nullptr, &tw, &th);
        float sratio = (float)tw / (float)th;
        float dratio = (float)poster.w / (float)poster.h;
        SDL_Rect dst = poster;
        if (sratio > dratio) {
            int new_h = (int)(poster.w / sratio);
            dst.y = poster.y + (poster.h - new_h) / 2;
            dst.h = new_h;
        } else {
            int new_w = (int)(poster.h * sratio);
            dst.x = poster.x + (poster.w - new_w) / 2;
            dst.w = new_w;
        }
        SDL_RenderCopy(r, poster_tex_, nullptr, &dst);
    } else {
        // Placeholder : initiale centrée, opacity faible
        std::string init = info_.series.name.empty() ? "?" : info_.series.name.substr(0, 1);
        if (!info_.series.name.empty() &&
            (static_cast<unsigned char>(info_.series.name[0]) & 0x80)) {
            size_t n = 1;
            while (n < info_.series.name.size() &&
                   (static_cast<unsigned char>(info_.series.name[n]) & 0xC0) == 0x80) ++n;
            init = info_.series.name.substr(0, n);
        }
        int iw = 0, ih = 0;
        text_.measure(theme::FontStyle::Xl3Bold, init, iw, ih);
        text_.draw(theme::FontStyle::Xl3Bold, init,
                   poster.x + (poster.w - iw) / 2,
                   poster.y + (poster.h - ih) / 2,
                   theme::withAlpha(theme::TextSecondary, 120));
    }

    // Sous le poster : nom + meta
    int leftY = poster.y + poster.h + 16;
    text_.drawEllipsis(theme::FontStyle::XlBold, info_.series.name,
                       poster.x, leftY, poster.w, theme::TextPrimary);
    leftY += text_.lineHeight(theme::FontStyle::XlBold) + 6;
    {
        std::string meta;
        int totalSeasons = (int)info_.seasons.size();
        char buf[32]; std::snprintf(buf, sizeof(buf), "%d saison%s",
                                     totalSeasons, totalSeasons > 1 ? "s" : "");
        meta = buf;
        if (!info_.series.genre.empty()) meta += "  .  " + info_.series.genre;
        text_.drawEllipsis(theme::FontStyle::SmRegular, meta,
                           poster.x, leftY, poster.w, theme::TextSecondary);
    }

    // Colonne droite : onglets saisons + liste épisodes
    int rightX = poster.x + poster.w + 48;
    int rightW = winW - rightX - kLeftPad;

    text_.draw(theme::FontStyle::LgBold, "Saisons", rightX, contentY + 8, theme::Accent);
    int sy = contentY + 56;
    int sx = rightX;
    for (int i = 0; i < totalSeasons(); ++i) {
        const auto* s = seasonAtIndex(i);
        if (!s) continue;
        char tbl[32]; std::snprintf(tbl, sizeof(tbl), "Saison %d", s->season_number);
        int tw = 0, th = 0;
        text_.measure(theme::FontStyle::MdBold, tbl, tw, th);
        int w = tw + 48;
        SDL_Rect tab{sx, sy, w, kSeasonTabH};
        bool isActive = (i == seasonIdx_);
        bool isFocus  = (zone_ == Zone::Seasons && i == seasonIdx_);
        if (isActive) {
            draw::fillRoundedRect(r, tab, theme::RadiusSm, theme::AccentTint);
            SDL_Rect under{tab.x, tab.y + tab.h - 3, tab.w, 3};
            draw::fillRect(r, under, theme::Accent);
        }
        if (isFocus) draw::strokeRoundedRect(r, tab, theme::RadiusSm, 2, theme::Accent);
        text_.draw(theme::FontStyle::MdBold, tbl,
                   tab.x + (tab.w - tw) / 2,
                   tab.y + (tab.h - th) / 2,
                   isActive ? theme::TextPrimary : theme::TextSecondary);
        sx += w + 8;
    }

    // Liste épisodes (viewport scrollé)
    int listY = sy + kSeasonTabH + 24;
    int listBottom = winH - 20;
    int viewH = listBottom - listY;

    const auto& eps = currentEpisodes();
    // Scroll : si épisode focusé sort du viewport, ajuste scrollRowY_.
    if (zone_ == Zone::Episodes) {
        int itemTop = episodeIdx_ * kEpisodeRowH - scrollRowY_;
        if (itemTop < 0) scrollRowY_ = episodeIdx_ * kEpisodeRowH;
        int itemBot = itemTop + kEpisodeRowH;
        if (itemBot > viewH) scrollRowY_ = episodeIdx_ * kEpisodeRowH - (viewH - kEpisodeRowH);
        if (scrollRowY_ < 0) scrollRowY_ = 0;
    }

    SDL_Rect clip{rightX - 4, listY, rightW + 8, viewH};
    SDL_RenderSetClipRect(r, &clip);
    for (size_t i = 0; i < eps.size(); ++i) {
        int iy = listY + ((int)i * kEpisodeRowH - scrollRowY_);
        if (iy + kEpisodeRowH < listY || iy > listBottom) continue;
        SDL_Rect row{rightX, iy, rightW, kEpisodeRowH - 6};
        bool focus = (zone_ == Zone::Episodes && (int)i == episodeIdx_);
        if (focus) {
            draw::fillRoundedRect(r, row, theme::RadiusMd, theme::BgTertiary);
            draw::strokeRoundedRect(r, row, theme::RadiusMd, 2, theme::Accent);
        }
        const auto& ep = eps[i];
        char tit[256];
        std::snprintf(tit, sizeof(tit), "%d. %s", ep.episode_num, ep.title.c_str());
        int tw = 0, th = 0;
        text_.measure(theme::FontStyle::MdBold, tit, tw, th);
        int maxTitleW = row.w - theme::Space3 * 2 - 200;  // laisser la place au badge/position
        text_.drawEllipsis(theme::FontStyle::MdBold, tit,
                           row.x + theme::Space3,
                           row.y + (row.h - th) / 2,
                           maxTitleW,
                           theme::TextPrimary);

        // Badge "vu" ou position de reprise
        bool seen = watched_set_.count(ep.id) > 0;
        double pos = store::WatchPosition::get(ep.id);
        if (pos > 0) {
            // "hh:mm:ss / hh:mm:ss" format si durée connue, sinon format M:SS
            std::string label = store::WatchPosition::format(pos);
            int lw = 0, lh = 0;
            text_.measure(theme::FontStyle::SmRegular, label, lw, lh);
            text_.draw(theme::FontStyle::SmRegular, label,
                       row.x + row.w - theme::Space3 - lw,
                       row.y + (row.h - lh) / 2,
                       theme::TextSecondary);
        } else if (seen) {
            int vw = 0, vh = 0;
            text_.measure(theme::FontStyle::SmBold, "vu", vw, vh);
            text_.draw(theme::FontStyle::SmBold, "vu",
                       row.x + row.w - theme::Space3 - vw,
                       row.y + (row.h - vh) / 2,
                       theme::Success);
        }
    }
    SDL_RenderSetClipRect(r, nullptr);
}

}  // namespace iptv::ui

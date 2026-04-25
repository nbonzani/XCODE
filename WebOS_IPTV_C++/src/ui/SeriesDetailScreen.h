#pragma once
// SeriesDetailScreen — poster + synopsis à gauche, onglets Saisons + liste
// épisodes avec badge "vu" + position de reprise formatée.

#include <functional>
#include <set>
#include <string>
#include <vector>

#include "xtream/Models.h"

struct SDL_Renderer;
struct SDL_Texture;

namespace iptv::xtream { class XtreamClient; }

namespace iptv::ui {

class TextRenderer;
class FocusManager;
class ImageLoader;

class SeriesDetailScreen {
public:
    SeriesDetailScreen(TextRenderer& text, FocusManager& focus,
                       ImageLoader& images, xtream::XtreamClient& client);
    ~SeriesDetailScreen();

    void load(const std::string& seriesId);
    void handleKey(int code, bool& handled);
    void render(SDL_Renderer* r, int winW, int winH);

    void setOnPlay(std::function<void(const std::string& url,
                                      const std::string& episodeId,
                                      const std::string& seriesId,
                                      const std::string& episodeTitle,
                                      const std::string& audioCodec,
                                      const std::string& videoCodec)> cb) {
        on_play_ = std::move(cb);
    }
    void setOnBack(std::function<void()> cb) { on_back_ = std::move(cb); }

    // Si défini, l'épisode correspondant sera focusé à l'ouverture.
    void setInitialEpisodeId(const std::string& id) { initial_episode_id_ = id; }

    // Accesseurs publics pour construire une playlist côté app (prev/next
    // épisode dans le lecteur). La saison "courante" est celle vue à l'instant
    // où l'utilisateur déclenche la lecture.
    const std::vector<xtream::Episode>& currentEpisodes() const;
    int  currentEpisodeIdx() const { return episodeIdx_; }
    int  currentSeasonNumber() const;
    const std::string& seriesId() const { return seriesId_; }
    const std::string& seriesName() const { return info_.series.name; }

private:
    enum class Zone { Header, Seasons, Episodes };
    void computeSeasonIndices();
    const xtream::Season* seasonAtIndex(int idx) const;
    int totalSeasons() const { return (int)info_.seasons.size(); }

    TextRenderer& text_;
    FocusManager& focus_;
    ImageLoader&  images_;
    xtream::XtreamClient& client_;

    // Texture du poster série (chargé via ImageLoader).
    SDL_Texture* poster_tex_ = nullptr;
    std::string poster_url_;           // url en cours de fetch / loaded
    bool poster_requested_ = false;

    std::string seriesId_;
    std::string initial_episode_id_;
    xtream::SeriesInfo info_;
    bool loading_ = false;
    std::string error_;

    Zone zone_ = Zone::Episodes;
    int seasonIdx_ = 0;       // index dans info_.seasons
    int episodeIdx_ = 0;      // index dans la saison courante
    int scrollRowY_ = 0;      // scroll vertical de la liste d'épisodes (px)

    std::set<std::string> watched_set_;  // rafraîchi à chaque load()

    std::function<void(const std::string&, const std::string&,
                       const std::string&, const std::string&,
                       const std::string&, const std::string&)> on_play_;
    std::function<void()> on_back_;
};

}  // namespace iptv::ui

#pragma once
// Series detail: header (cover + metadata) + flat list of seasons/episodes.
// Ported structurally from SeriesDetailScreen.jsx.

#include <functional>
#include <string>

#include "xtream/Models.h"

struct SDL_Renderer;

namespace iptv::xtream { class XtreamClient; }

namespace iptv::ui {

class TextRenderer;
class FocusManager;

class SeriesDetailScreen {
public:
    SeriesDetailScreen(TextRenderer& text, FocusManager& focus, xtream::XtreamClient& client);

    void load(const std::string& seriesId);
    void handleKey(int code, bool& handled);
    void render(SDL_Renderer* r, int winW, int winH);

    void setOnPlay(std::function<void(const std::string& url,
                                      const std::string& episodeId,
                                      const std::string& seriesId,
                                      const std::string& episodeTitle)> cb) {
        on_play_ = std::move(cb);
    }
    void setOnBack(std::function<void()> cb) { on_back_ = std::move(cb); }

private:
    void registerFocus();

    TextRenderer& text_;
    FocusManager& focus_;
    xtream::XtreamClient& client_;

    std::string seriesId_;
    xtream::SeriesInfo info_;
    bool loading_ = false;
    std::string error_;

    // Flat enumeration of episodes for focus/scroll.
    struct EpisodeRef {
        int seasonNum;
        std::size_t episodeIdx;  // index within that season
        std::string focusId;
    };
    std::vector<EpisodeRef> flat_;
    int scroll_ = 0;

    std::function<void(const std::string&, const std::string&,
                       const std::string&, const std::string&)> on_play_;
    std::function<void()> on_back_;
};

}  // namespace iptv::ui

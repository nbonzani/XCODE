#pragma once
// Fullscreen player overlay: title, timeline, elapsed/total, play/pause, next/prev
// buttons. Auto-hides after 3s of inactivity (same as PlayerScreen.jsx).

#include <cstdint>
#include <functional>
#include <string>

struct SDL_Renderer;

namespace iptv::ui {

class TextRenderer;

struct PlayerOSDState {
    std::string title;
    std::string playlistHint;  // e.g. "3/12" or empty
    double position = 0.0;
    double duration = 0.0;
    bool paused = false;
    bool visible = true;
};

class PlayerOSD {
public:
    explicit PlayerOSD(TextRenderer& text) : text_(text) {}

    void poke();                     // mark user activity — resets the auto-hide timer
    void tick(uint32_t nowMs);       // called each frame with SDL_GetTicks

    bool isVisible() const { return state_.visible; }

    void setTitle(const std::string& t)         { state_.title = t; }
    void setPlaylistHint(const std::string& h)  { state_.playlistHint = h; }
    void setPlaying(bool playing)               { state_.paused = !playing; }
    void setProgress(double pos, double dur)    { state_.position = pos; state_.duration = dur; }

    void render(SDL_Renderer* renderer, int winW, int winH);

    // Timeout in ms before the OSD fades out after poke().
    void setTimeoutMs(uint32_t t) { timeoutMs_ = t; }

private:
    TextRenderer& text_;
    PlayerOSDState state_;
    uint32_t lastPokeMs_ = 0;
    uint32_t timeoutMs_ = 3000;
};

}  // namespace iptv::ui

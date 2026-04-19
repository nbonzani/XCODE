#include "ui/PlayerOSD.h"

#include <algorithm>
#include <cstdio>
#include <sstream>

#include <SDL2/SDL.h>

#include "ui/TextRenderer.h"

namespace iptv::ui {

namespace {
std::string formatTime(double seconds) {
    if (seconds < 0) seconds = 0;
    int s = static_cast<int>(seconds);
    int h = s / 3600;
    int m = (s % 3600) / 60;
    int sec = s % 60;
    char buf[16];
    if (h > 0) std::snprintf(buf, sizeof(buf), "%d:%02d:%02d", h, m, sec);
    else       std::snprintf(buf, sizeof(buf), "%d:%02d", m, sec);
    return buf;
}
}  // namespace

void PlayerOSD::poke() {
    state_.visible = true;
    lastPokeMs_ = SDL_GetTicks();
}

void PlayerOSD::tick(uint32_t nowMs) {
    if (!state_.visible) return;
    if (nowMs - lastPokeMs_ > timeoutMs_ && !state_.paused) {
        state_.visible = false;
    }
}

void PlayerOSD::render(SDL_Renderer* r, int winW, int winH) {
    if (!state_.visible) return;

    // Bottom translucent strip.
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(r, 0, 0, 0, 180);
    SDL_Rect strip{0, winH - 180, winW, 180};
    SDL_RenderFillRect(r, &strip);

    // Title top-left.
    text_.draw(state_.title, 40, 30, {240, 240, 240, 255});
    if (!state_.playlistHint.empty()) {
        text_.draw(state_.playlistHint, 40, 30 + text_.lineHeight() + 4,
                   {180, 180, 180, 255});
    }

    // Timeline.
    int tlX = 60;
    int tlY = winH - 110;
    int tlW = winW - 120;
    SDL_SetRenderDrawColor(r, 70, 70, 70, 255);
    SDL_Rect bar{tlX, tlY, tlW, 6};
    SDL_RenderFillRect(r, &bar);
    if (state_.duration > 0) {
        float ratio = static_cast<float>(state_.position / state_.duration);
        ratio = std::clamp(ratio, 0.0f, 1.0f);
        SDL_SetRenderDrawColor(r, 220, 40, 40, 255);
        SDL_Rect fill{tlX, tlY, static_cast<int>(tlW * ratio), 6};
        SDL_RenderFillRect(r, &fill);
        // Playhead dot.
        SDL_Rect dot{tlX + static_cast<int>(tlW * ratio) - 6, tlY - 4, 14, 14};
        SDL_RenderFillRect(r, &dot);
    }

    // Times.
    std::string left = formatTime(state_.position);
    std::string right = state_.duration > 0 ? formatTime(state_.duration) : std::string("--:--");
    text_.draw(left,  tlX, tlY + 16, {220, 220, 220, 255});
    int rw = 0, rh = 0; text_.measure(right, rw, rh);
    text_.draw(right, tlX + tlW - rw, tlY + 16, {220, 220, 220, 255});

    // Play/pause indicator bottom-left + exit hint.
    const char* state = state_.paused ? "PAUSE" : "PLAY";
    text_.draw(state, 40, winH - 52, {220, 220, 220, 255});
    text_.draw("[OK] Retour", winW - 240, winH - 52, {180, 180, 180, 255});
}

}  // namespace iptv::ui

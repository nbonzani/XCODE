#pragma once
// LG webOS TV remote key mapping — values here are `SDL_Keycode`s (what lands in
// ev.key.keysym.sym), not DOM `KeyboardEvent.keyCode`s.
//
// SDL on webOS TV maps the directional cluster and OK to standard SDLK_* constants.
// BACK/EXIT/COLOR/MEDIA keys come through as vendor-specific AC_* or extra codes; we
// discover them at runtime via the debug dump and pin the right SDLK_* below.

#include <cstdint>
#include <SDL2/SDL_keycode.h>

namespace iptv::app {

namespace KEY {
// Directional cluster + OK — standard SDL keys
constexpr int LEFT  = SDLK_LEFT;
constexpr int UP    = SDLK_UP;
constexpr int RIGHT = SDLK_RIGHT;
constexpr int DOWN  = SDLK_DOWN;
constexpr int OK    = SDLK_RETURN;
constexpr int ENTER = SDLK_RETURN;

// BACK : SDL maps LG's back to AC_BACK. Escape is a common keyboard fallback.
constexpr int BACK     = SDLK_AC_BACK;
constexpr int BACK_ALT = SDLK_ESCAPE;
// EXIT (home button on LG) is not universal; SDL_HOME isn't defined for all builds
// so we match it numerically against the value LG sends.
constexpr int EXIT     = SDLK_AC_HOME;

// Media transport — SDL_AUDIO* / SDL_MEDIA*. SDL has no distinct keysym for PAUSE
// nor PLAY_PAUSE so we overload SDLK_AUDIOPLAY for both and track state in the UI.
constexpr int PLAY       = SDLK_AUDIOPLAY;
constexpr int PAUSE      = SDLK_AUDIOPLAY;       // same keysym; toggle handled by UI state
constexpr int PLAY_PAUSE = SDLK_AUDIOPLAY;
constexpr int STOP       = SDLK_AUDIOSTOP;
constexpr int FF         = SDLK_AUDIOFASTFORWARD;
constexpr int REW        = SDLK_AUDIOREWIND;

// Color buttons — SDL has no standard keycode for them. On webOS they land on
// SDLK_F1..F4 in some builds; we keep these as a best-effort default and adjust
// after observing the actual key events (logged on startup).
constexpr int RED    = SDLK_F1;
constexpr int GREEN  = SDLK_F2;
constexpr int YELLOW = SDLK_F3;
constexpr int BLUE   = SDLK_F4;

// Numeric 0-9
constexpr int NUM_0 = SDLK_0;
constexpr int NUM_1 = SDLK_1;
constexpr int NUM_2 = SDLK_2;
constexpr int NUM_3 = SDLK_3;
constexpr int NUM_4 = SDLK_4;
constexpr int NUM_5 = SDLK_5;
constexpr int NUM_6 = SDLK_6;
constexpr int NUM_7 = SDLK_7;
constexpr int NUM_8 = SDLK_8;
constexpr int NUM_9 = SDLK_9;
}  // namespace KEY

inline bool isBackKey(int code) { return code == KEY::BACK || code == KEY::BACK_ALT; }
inline bool isOkKey(int code)   { return code == KEY::OK; }
inline bool isExitKey(int code) { return code == KEY::EXIT; }
inline bool isDirectionalKey(int code) {
    return code == KEY::LEFT || code == KEY::RIGHT || code == KEY::UP || code == KEY::DOWN;
}
inline bool isMediaKey(int code) {
    return code == KEY::PLAY || code == KEY::PAUSE || code == KEY::PLAY_PAUSE ||
           code == KEY::STOP || code == KEY::FF    || code == KEY::REW;
}

}  // namespace iptv::app

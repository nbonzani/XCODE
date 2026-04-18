#pragma once
// LG webOS TV remote key codes — port of src/constants/keyCodes.js.
//
// SDL2 reports these as ev.key.keysym.sym (or .scancode for some).
// Tested values for webOS 4.x/5.x/6.x (LG OLED C1 included). VK_BACK can be 461 or 8
// depending on model — the helpers below cover both.

#include <cstdint>

namespace iptv::app {

namespace KEY {
// Directional
constexpr int LEFT  = 37;
constexpr int UP    = 38;
constexpr int RIGHT = 39;
constexpr int DOWN  = 40;

// Validation / system
constexpr int OK       = 13;
constexpr int ENTER    = 13;
constexpr int BACK     = 461;
constexpr int BACK_ALT = 8;
constexpr int EXIT     = 1001;

// Media transport
constexpr int PLAY       = 415;
constexpr int PAUSE      = 19;
constexpr int PLAY_PAUSE = 179;
constexpr int STOP       = 413;
constexpr int FF         = 417;
constexpr int REW        = 412;

// Color buttons (standard remote — not on Magic Remote)
constexpr int RED    = 403;
constexpr int GREEN  = 404;
constexpr int YELLOW = 405;
constexpr int BLUE   = 406;

// Numeric
constexpr int NUM_0 = 48;
constexpr int NUM_1 = 49;
constexpr int NUM_2 = 50;
constexpr int NUM_3 = 51;
constexpr int NUM_4 = 52;
constexpr int NUM_5 = 53;
constexpr int NUM_6 = 54;
constexpr int NUM_7 = 55;
constexpr int NUM_8 = 56;
constexpr int NUM_9 = 57;
}  // namespace KEY

inline bool isBackKey(int code) { return code == KEY::BACK || code == KEY::BACK_ALT; }
inline bool isOkKey(int code)   { return code == KEY::OK; }
inline bool isExitKey(int code) { return code == KEY::EXIT; }
inline bool isDirectionalKey(int code) { return code >= KEY::LEFT && code <= KEY::DOWN; }
inline bool isMediaKey(int code) {
    return code == KEY::PLAY || code == KEY::PAUSE || code == KEY::PLAY_PAUSE ||
           code == KEY::STOP || code == KEY::FF    || code == KEY::REW;
}

}  // namespace iptv::app

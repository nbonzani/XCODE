#pragma once
// Thin wrapper around SDL2_ttf. Charge un font regular + bold aux tailles
// standard (Theme::FontStyle) et met en cache les textures rendues pour
// éviter de repasser par le rasterizer à chaque frame.

#include <cstdint>
#include <string>
#include <unordered_map>

#include <SDL2/SDL_ttf.h>

#include "ui/Theme.h"

struct SDL_Renderer;
struct SDL_Texture;

namespace iptv::ui {

struct Color {
    uint8_t r = 255, g = 255, b = 255, a = 255;
};

// Conversion implicite SDL_Color → Color (pour compat Theme.h).
inline Color toColor(SDL_Color c) { return Color{c.r, c.g, c.b, c.a}; }

class TextRenderer {
public:
    TextRenderer();
    ~TextRenderer();

    TextRenderer(const TextRenderer&) = delete;
    TextRenderer& operator=(const TextRenderer&) = delete;

    // Legacy : charge une seule police (regular). Conservé pour compat.
    bool init(SDL_Renderer* renderer, const std::string& fontPath, int pointSize);

    // Nouveau : charge regular + bold TTF, prépare toutes les tailles Theme.
    // boldFontPath peut être vide → bold repliera sur regular.
    bool initWithWeights(SDL_Renderer* renderer,
                         const std::string& regularPath,
                         const std::string& boldPath);

    // API legacy (utilise la police chargée via init()).
    void draw(const std::string& text, int x, int y, Color color = {});
    void measure(const std::string& text, int& w, int& h);
    int  lineHeight() const;
    int  pointSize() const { return pt_; }

    // API nouvelle (multi-taille). style sélectionne (taille, weight).
    void draw(theme::FontStyle style, const std::string& text, int x, int y,
              SDL_Color color);
    void measure(theme::FontStyle style, const std::string& text, int& w, int& h);
    int  lineHeight(theme::FontStyle style);

    // Dessine une chaîne, mais tronque avec "…" si elle dépasse maxWidth.
    void drawEllipsis(theme::FontStyle style, const std::string& text, int x, int y,
                      int maxWidth, SDL_Color color);

    // Purge le cache.
    void clear();

private:
    struct FontSlot { TTF_Font* f = nullptr; int pt = 0; };
    FontSlot& slotFor(theme::FontStyle style);
    SDL_Texture* rasterize(TTF_Font* font, const std::string& text, SDL_Color c);

    SDL_Renderer* renderer_ = nullptr;
    TTF_Font* font_ = nullptr;
    int pt_ = 0;
    std::string regular_path_;
    std::string bold_path_;

    // 13 slots pour FontStyle (XsRegular..Xl3Bold). Index via style enum.
    FontSlot slots_[13]{};

    struct Key {
        std::string text;
        uint32_t color = 0;
        int slot = -1;  // index de slot ou -1 pour le font_ legacy
        bool operator==(const Key& o) const {
            return text == o.text && color == o.color && slot == o.slot;
        }
    };
    struct KeyHash {
        std::size_t operator()(const Key& k) const {
            return std::hash<std::string>()(k.text) ^
                   (k.color * 2654435761u) ^ ((uint32_t)k.slot * 16777619u);
        }
    };
    std::unordered_map<Key, SDL_Texture*, KeyHash> cache_;
};

}  // namespace iptv::ui

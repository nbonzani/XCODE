#pragma once
// Thin wrapper around SDL2_ttf. Loads a font once, keeps a small LRU of rendered
// glyph textures so repeatedly-drawn strings don't go through the rasterizer.

#include <cstdint>
#include <string>
#include <unordered_map>

#include <SDL2/SDL_ttf.h>

struct SDL_Renderer;
struct SDL_Texture;

namespace iptv::ui {

struct Color {
    uint8_t r = 255, g = 255, b = 255, a = 255;
};

class TextRenderer {
public:
    TextRenderer();
    ~TextRenderer();

    TextRenderer(const TextRenderer&) = delete;
    TextRenderer& operator=(const TextRenderer&) = delete;

    // Initialise with a TTF font (absolute path). Returns false on error.
    bool init(SDL_Renderer* renderer, const std::string& fontPath, int pointSize);

    // Draw text at pixel coordinates. Texture is cached on (text, size, color).
    void draw(const std::string& text, int x, int y, Color color = {});

    // Returns (w,h) in pixels for a given string, without drawing.
    void measure(const std::string& text, int& w, int& h);

    int pointSize() const { return pt_; }
    int lineHeight() const;  // font line skip

    // Purge cache (call on SDL_Renderer destruction).
    void clear();

private:
    SDL_Renderer* renderer_ = nullptr;
    TTF_Font* font_ = nullptr;
    int pt_ = 0;

    struct Key {
        std::string text;
        uint32_t color = 0;
        bool operator==(const Key& o) const { return text == o.text && color == o.color; }
    };
    struct KeyHash {
        std::size_t operator()(const Key& k) const {
            return std::hash<std::string>()(k.text) ^ (k.color * 2654435761u);
        }
    };
    std::unordered_map<Key, SDL_Texture*, KeyHash> cache_;
};

}  // namespace iptv::ui

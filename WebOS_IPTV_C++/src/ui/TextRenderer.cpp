#include "ui/TextRenderer.h"

#include <cstdio>

#include <SDL2/SDL.h>
#include <SDL2/SDL_ttf.h>

namespace iptv::ui {

namespace {
bool g_ttf_inited = false;
void ensureTtfInit() {
    if (!g_ttf_inited) {
        if (TTF_Init() != 0) {
            std::fprintf(stderr, "TTF_Init failed: %s\n", TTF_GetError());
        }
        g_ttf_inited = true;
    }
}
}  // namespace

TextRenderer::TextRenderer()  = default;
TextRenderer::~TextRenderer() { clear(); if (font_) TTF_CloseFont(font_); }

bool TextRenderer::init(SDL_Renderer* renderer, const std::string& fontPath, int pt) {
    ensureTtfInit();
    renderer_ = renderer;
    pt_ = pt;
    font_ = TTF_OpenFont(fontPath.c_str(), pt);
    if (!font_) {
        std::fprintf(stderr, "TTF_OpenFont(%s, %d) failed: %s\n",
                     fontPath.c_str(), pt, TTF_GetError());
        return false;
    }
    return true;
}

int TextRenderer::lineHeight() const {
    return font_ ? TTF_FontLineSkip(font_) : pt_;
}

void TextRenderer::measure(const std::string& text, int& w, int& h) {
    w = h = 0;
    if (!font_ || text.empty()) return;
    TTF_SizeUTF8(font_, text.c_str(), &w, &h);
}

void TextRenderer::draw(const std::string& text, int x, int y, Color color) {
    if (!font_ || !renderer_ || text.empty()) return;
    uint32_t packed = (uint32_t(color.r) << 24) | (uint32_t(color.g) << 16) |
                      (uint32_t(color.b) << 8)  |  uint32_t(color.a);
    Key k{text, packed};
    SDL_Texture* tex = nullptr;
    auto it = cache_.find(k);
    if (it != cache_.end()) {
        tex = it->second;
    } else {
        SDL_Color sdlc{color.r, color.g, color.b, color.a};
        SDL_Surface* surf = TTF_RenderUTF8_Blended(font_, text.c_str(), sdlc);
        if (!surf) return;
        tex = SDL_CreateTextureFromSurface(renderer_, surf);
        SDL_FreeSurface(surf);
        if (!tex) return;
        if (cache_.size() > 512) {
            // Drop the first half of entries when the cache gets big — simple eviction.
            auto mid = cache_.begin();
            std::advance(mid, cache_.size() / 2);
            for (auto it2 = cache_.begin(); it2 != mid; ) {
                SDL_DestroyTexture(it2->second);
                it2 = cache_.erase(it2);
            }
        }
        cache_.emplace(k, tex);
    }
    int w = 0, h = 0;
    SDL_QueryTexture(tex, nullptr, nullptr, &w, &h);
    SDL_Rect dst{x, y, w, h};
    SDL_RenderCopy(renderer_, tex, nullptr, &dst);
}

void TextRenderer::clear() {
    for (auto& [k, tex] : cache_) {
        if (tex) SDL_DestroyTexture(tex);
    }
    cache_.clear();
}

}  // namespace iptv::ui

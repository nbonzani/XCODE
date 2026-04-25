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

// Mapping FontStyle → (size, isBold).
struct StyleInfo { int size; bool bold; };
StyleInfo styleInfo(theme::FontStyle s) {
    using FS = theme::FontStyle;
    switch (s) {
        case FS::XsRegular:  return {theme::FontXs,  false};
        case FS::XsBold:     return {theme::FontXs,  true};
        case FS::SmRegular:  return {theme::FontSm,  false};
        case FS::SmBold:     return {theme::FontSm,  true};
        case FS::MdRegular:  return {theme::FontMd,  false};
        case FS::MdBold:     return {theme::FontMd,  true};
        case FS::LgRegular:  return {theme::FontLg,  false};
        case FS::LgBold:     return {theme::FontLg,  true};
        case FS::XlRegular:  return {theme::FontXl,  false};
        case FS::XlBold:     return {theme::FontXl,  true};
        case FS::Xl2Regular: return {theme::Font2xl, false};
        case FS::Xl2Bold:    return {theme::Font2xl, true};
        case FS::Xl3Bold:    return {theme::Font3xl, true};
    }
    return {theme::FontMd, false};
}
}  // namespace

TextRenderer::TextRenderer()  = default;
TextRenderer::~TextRenderer() {
    clear();
    for (auto& s : slots_) if (s.f) TTF_CloseFont(s.f);
    if (font_) TTF_CloseFont(font_);
}

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
    // Si regularPath pas encore défini, le réutilise pour les styles multi-taille.
    if (regular_path_.empty()) regular_path_ = fontPath;
    return true;
}

bool TextRenderer::initWithWeights(SDL_Renderer* renderer,
                                   const std::string& regularPath,
                                   const std::string& boldPath) {
    ensureTtfInit();
    renderer_ = renderer;
    regular_path_ = regularPath;
    bold_path_ = boldPath.empty() ? regularPath : boldPath;
    // Charge en lazy dans slotFor ; on se contente de pré-ouvrir la police
    // regular taille Md pour l'API legacy.
    if (!font_) {
        font_ = TTF_OpenFont(regular_path_.c_str(), theme::FontMd);
        pt_ = theme::FontMd;
        if (!font_) {
            std::fprintf(stderr, "TTF_OpenFont(%s, %d) failed: %s\n",
                         regular_path_.c_str(), theme::FontMd, TTF_GetError());
            return false;
        }
    }
    return true;
}

TextRenderer::FontSlot& TextRenderer::slotFor(theme::FontStyle style) {
    int idx = static_cast<int>(style);
    FontSlot& s = slots_[idx];
    if (!s.f) {
        auto info = styleInfo(style);
        const std::string& path = info.bold ? bold_path_ : regular_path_;
        const std::string& fallback = regular_path_;
        const char* load = (!path.empty() ? path : fallback).c_str();
        s.f = TTF_OpenFont(load, info.size);
        s.pt = info.size;
        if (!s.f) {
            std::fprintf(stderr, "TTF_OpenFont(%s, %d) failed: %s\n",
                         load, info.size, TTF_GetError());
        }
    }
    return s;
}

int TextRenderer::lineHeight() const {
    return font_ ? TTF_FontLineSkip(font_) : pt_;
}

int TextRenderer::lineHeight(theme::FontStyle style) {
    FontSlot& s = slotFor(style);
    return s.f ? TTF_FontLineSkip(s.f) : s.pt;
}

void TextRenderer::measure(const std::string& text, int& w, int& h) {
    w = h = 0;
    if (!font_ || text.empty()) return;
    TTF_SizeUTF8(font_, text.c_str(), &w, &h);
}

void TextRenderer::measure(theme::FontStyle style, const std::string& text,
                           int& w, int& h) {
    w = h = 0;
    FontSlot& s = slotFor(style);
    if (!s.f || text.empty()) return;
    TTF_SizeUTF8(s.f, text.c_str(), &w, &h);
}

SDL_Texture* TextRenderer::rasterize(TTF_Font* font, const std::string& text,
                                     SDL_Color c) {
    SDL_Surface* surf = TTF_RenderUTF8_Blended(font, text.c_str(), c);
    if (!surf) return nullptr;
    SDL_Texture* tex = SDL_CreateTextureFromSurface(renderer_, surf);
    SDL_FreeSurface(surf);
    return tex;
}

void TextRenderer::draw(const std::string& text, int x, int y, Color color) {
    if (!font_ || !renderer_ || text.empty()) return;
    uint32_t packed = (uint32_t(color.r) << 24) | (uint32_t(color.g) << 16) |
                      (uint32_t(color.b) << 8)  |  uint32_t(color.a);
    Key k{text, packed, -1};
    SDL_Texture* tex = nullptr;
    auto it = cache_.find(k);
    if (it != cache_.end()) {
        tex = it->second;
    } else {
        SDL_Color sdlc{color.r, color.g, color.b, color.a};
        tex = rasterize(font_, text, sdlc);
        if (!tex) return;
        if (cache_.size() > 512) {
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

void TextRenderer::draw(theme::FontStyle style, const std::string& text,
                        int x, int y, SDL_Color color) {
    if (!renderer_ || text.empty()) return;
    FontSlot& s = slotFor(style);
    if (!s.f) return;
    uint32_t packed = (uint32_t(color.r) << 24) | (uint32_t(color.g) << 16) |
                      (uint32_t(color.b) << 8)  |  uint32_t(color.a);
    Key k{text, packed, static_cast<int>(style)};
    SDL_Texture* tex = nullptr;
    auto it = cache_.find(k);
    if (it != cache_.end()) {
        tex = it->second;
    } else {
        tex = rasterize(s.f, text, color);
        if (!tex) return;
        if (cache_.size() > 512) {
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

void TextRenderer::drawEllipsis(theme::FontStyle style, const std::string& text,
                                int x, int y, int maxWidth, SDL_Color color) {
    if (text.empty() || maxWidth <= 0) return;
    int w = 0, h = 0;
    measure(style, text, w, h);
    if (w <= maxWidth) { draw(style, text, x, y, color); return; }
    // Dichotomie sur la longueur (byte-based — approximation UTF-8 mais on
    // reste conservatif en coupant sur des octets non-continuation quand on
    // peut). On s'arrête avant un octet de continuation (0x80..0xBF) pour
    // ne pas briser un caractère multi-byte.
    auto canCut = [&](size_t n) {
        if (n >= text.size()) return true;
        return (static_cast<unsigned char>(text[n]) & 0xC0) != 0x80;
    };
    const std::string ell = "…";
    size_t lo = 0, hi = text.size();
    while (lo < hi) {
        size_t mid = (lo + hi + 1) / 2;
        while (mid > lo && !canCut(mid)) --mid;
        std::string t = text.substr(0, mid) + ell;
        int tw = 0, th = 0;
        measure(style, t, tw, th);
        if (tw <= maxWidth) lo = mid;
        else                hi = mid - 1;
        if (mid == lo) break;
    }
    std::string out = text.substr(0, lo) + ell;
    draw(style, out, x, y, color);
}

void TextRenderer::clear() {
    for (auto& [k, tex] : cache_) {
        if (tex) SDL_DestroyTexture(tex);
    }
    cache_.clear();
}

}  // namespace iptv::ui

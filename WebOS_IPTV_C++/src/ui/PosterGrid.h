#pragma once
// Grid of posters with lazy image loading. Handles its own FocusNode registration
// and scrolling — the hosting screen just forwards arrow/OK keys.

#include <functional>
#include <string>
#include <vector>

struct SDL_Renderer;
struct SDL_Texture;

namespace iptv::ui {

class FocusManager;
class ImageLoader;
class TextRenderer;

struct GridItem {
    std::string id;          // focus id / item id
    std::string title;
    std::string imageUrl;    // optional — placeholder shown while loading
};

class PosterGrid {
public:
    PosterGrid(FocusManager& focus, ImageLoader& loader, TextRenderer& text);
    ~PosterGrid();

    PosterGrid(const PosterGrid&) = delete;
    PosterGrid& operator=(const PosterGrid&) = delete;

    // Grid placement (inside the window). Call before setItems().
    void setBounds(int x, int y, int w, int h);
    void setCellSize(int cw, int ch) { cw_ = cw; ch_ = ch; }
    void setGap(int g) { gap_ = g; }
    void setColumns(int cols) { cols_ = cols; }

    void setItems(std::vector<GridItem> items);
    void setOnSelect(std::function<void(const GridItem&)> cb) { on_select_ = std::move(cb); }

    // Walk through the currently visible window and make sure posters are queued
    // for download. Call after setItems() and when scrolling.
    void prefetchVisible();

    // Scroll so the focused item is in view.
    void ensureFocusedVisible();

    // Render. Called each frame by the hosting screen.
    void render(SDL_Renderer* renderer, const std::string& focusedId);

    // Focus ids registered for this grid (prefixed "grid_<id>" if not already).
    const std::string& focusIdFor(std::size_t index) const { return focusIds_[index]; }

private:
    struct Cell {
        GridItem item;
        SDL_Texture* texture = nullptr;
        bool requested = false;
    };

    void registerFocus();
    void unregisterFocus();

    FocusManager& focus_;
    ImageLoader&  loader_;
    TextRenderer& text_;

    int x_ = 0, y_ = 0, w_ = 0, h_ = 0;
    int cw_ = 180, ch_ = 270;
    int gap_ = 20;
    int cols_ = 6;
    int scroll_ = 0;  // pixels scrolled down

    std::vector<Cell> cells_;
    std::vector<std::string> focusIds_;
    std::function<void(const GridItem&)> on_select_;
};

}  // namespace iptv::ui

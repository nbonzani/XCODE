#include "ui/PosterGrid.h"

#include <algorithm>
#include <cmath>

#include <SDL2/SDL.h>

#include "ui/FocusManager.h"
#include "ui/ImageLoader.h"
#include "ui/TextRenderer.h"

namespace iptv::ui {

PosterGrid::PosterGrid(FocusManager& f, ImageLoader& l, TextRenderer& t)
    : focus_(f), loader_(l), text_(t) {}

PosterGrid::~PosterGrid() {
    for (auto& c : cells_) if (c.texture) SDL_DestroyTexture(c.texture);
    cells_.clear();
}

void PosterGrid::setBounds(int x, int y, int w, int h) {
    x_ = x; y_ = y; w_ = w; h_ = h;
}

void PosterGrid::setItems(std::vector<GridItem> items) {
    for (auto& c : cells_) if (c.texture) SDL_DestroyTexture(c.texture);
    cells_.clear();
    focusIds_.clear();
    cells_.reserve(items.size());
    focusIds_.reserve(items.size());
    for (auto& it : items) {
        Cell c;
        c.item = std::move(it);
        if (c.item.id.empty()) c.item.id = "cell_" + std::to_string(cells_.size());
        focusIds_.push_back("grid_" + c.item.id);
        cells_.push_back(std::move(c));
    }
    scroll_ = 0;
    // Focus nodes are registered lazily via activate() when this grid becomes the
    // visible tab — avoids paying O(N) to scan thousands of off-screen nodes on
    // every arrow-key press.
}

void PosterGrid::activate() {
    focus_.clear();
    registerFocus();
    if (!focusIds_.empty()) focus_.setFocus(focusIds_.front());
}

void PosterGrid::registerFocus() {
    // Cap how many cells we register focus for — browsing tens of thousands of
    // movies needs pagination/search, not an O(N) walk on every arrow press.
    constexpr std::size_t kMaxFocusable = 500;
    const std::size_t limit = std::min(cells_.size(), kMaxFocusable);
    for (std::size_t i = 0; i < limit; ++i) {
        int col = static_cast<int>(i % cols_);
        int row = static_cast<int>(i / cols_);
        int cx = x_ + col * (cw_ + gap_);
        int cy = y_ + row * (ch_ + gap_) - scroll_;

        FocusNode node;
        node.id    = focusIds_[i];
        node.x     = cx;
        node.y     = cy;
        node.w     = cw_;
        node.h     = ch_;
        node.group = "grid";
        std::size_t idx = i;
        node.onOk = [this, idx] {
            if (on_select_ && idx < cells_.size()) on_select_(cells_[idx].item);
        };
        focus_.add(std::move(node));
    }
}

void PosterGrid::prefetchVisible() {
    if (cells_.empty()) return;
    int firstRow = std::max(0, scroll_ / (ch_ + gap_) - 1);
    int visibleRows = h_ / (ch_ + gap_) + 2;
    int lastRow = firstRow + visibleRows;
    int first = firstRow * cols_;
    int last  = std::min<int>(cells_.size(), lastRow * cols_);
    for (int i = first; i < last; ++i) {
        auto& c = cells_[i];
        if (c.requested || c.item.imageUrl.empty()) continue;
        c.requested = true;
        loader_.request(c.item.imageUrl,
            [this, i](SDL_Texture* tex, int, int) {
                if (static_cast<std::size_t>(i) >= cells_.size()) {
                    if (tex) SDL_DestroyTexture(tex);
                    return;
                }
                auto& cc = cells_[i];
                if (cc.texture) SDL_DestroyTexture(cc.texture);
                cc.texture = tex;
            });
    }
}

void PosterGrid::ensureFocusedVisible() {
    const auto& focusedId = focus_.focused();
    auto it = std::find(focusIds_.begin(), focusIds_.end(), focusedId);
    if (it == focusIds_.end()) return;
    std::size_t idx = static_cast<std::size_t>(std::distance(focusIds_.begin(), it));
    int row = static_cast<int>(idx / cols_);
    int topPx = row * (ch_ + gap_);
    int bottomPx = topPx + ch_;
    if (topPx < scroll_) {
        scroll_ = topPx;
    } else if (bottomPx > scroll_ + h_) {
        scroll_ = bottomPx - h_;
    }
    // Re-register focus rects with the new scroll offset.
    registerFocus();
}

void PosterGrid::render(SDL_Renderer* renderer, const std::string& focusedId) {
    // Clip to our bounds so scrolled rows outside the grid are hidden.
    SDL_Rect clip{x_, y_, w_, h_};
    SDL_RenderSetClipRect(renderer, &clip);

    for (std::size_t i = 0; i < cells_.size(); ++i) {
        int col = static_cast<int>(i % cols_);
        int row = static_cast<int>(i / cols_);
        int cx = x_ + col * (cw_ + gap_);
        int cy = y_ + row * (ch_ + gap_) - scroll_;
        if (cy + ch_ < y_ || cy > y_ + h_) continue;  // off-screen

        SDL_Rect dst{cx, cy, cw_, ch_};
        auto& cell = cells_[i];
        if (cell.texture) {
            SDL_RenderCopy(renderer, cell.texture, nullptr, &dst);
        } else {
            // Placeholder: dark grey card with initials.
            SDL_SetRenderDrawColor(renderer, 35, 35, 40, 255);
            SDL_RenderFillRect(renderer, &dst);
            std::string initials = cell.item.title.substr(0, 1);
            text_.draw(initials, cx + cw_/2 - 10, cy + ch_/2 - 12, {180, 180, 180, 255});
        }

        // Title below, truncated.
        std::string title = cell.item.title;
        if (title.size() > 30) title = title.substr(0, 28) + "…";
        text_.draw(title, cx, cy + ch_ + 4, {230, 230, 230, 255});

        // Focus outline.
        if (focusIds_[i] == focusedId) {
            SDL_SetRenderDrawColor(renderer, 220, 40, 40, 255);
            for (int k = 0; k < 3; ++k) {
                SDL_Rect r{cx - k, cy - k, cw_ + 2*k, ch_ + 2*k};
                SDL_RenderDrawRect(renderer, &r);
            }
        }
    }
    SDL_RenderSetClipRect(renderer, nullptr);
}

}  // namespace iptv::ui

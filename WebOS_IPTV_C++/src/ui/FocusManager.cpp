#include "ui/FocusManager.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace iptv::ui {

void FocusManager::clear() {
    nodes_.clear();
    focusedId_.clear();
}

void FocusManager::add(FocusNode node) {
    if (focusedId_.empty()) focusedId_ = node.id;  // first node registered = default focus
    nodes_.push_back(std::move(node));
}

void FocusManager::setFocus(const std::string& id) {
    for (const auto& n : nodes_) {
        if (n.id == id) { focusedId_ = id; return; }
    }
}

const FocusNode* FocusManager::find(const std::string& id) const {
    for (const auto& n : nodes_) if (n.id == id) return &n;
    return nullptr;
}

bool FocusManager::move(Dir d) {
    const FocusNode* cur = find(focusedId_);
    if (!cur) {
        if (nodes_.empty()) return false;
        focusedId_ = nodes_.front().id;
        return true;
    }
    float cx = cur->x + cur->w / 2.0f;
    float cy = cur->y + cur->h / 2.0f;

    float best = std::numeric_limits<float>::infinity();
    const FocusNode* winner = nullptr;
    for (const auto& n : nodes_) {
        if (n.id == focusedId_) continue;
        float nx = n.x + n.w / 2.0f;
        float ny = n.y + n.h / 2.0f;
        float dx = nx - cx;
        float dy = ny - cy;

        bool onAxis = false;
        switch (d) {
            case Dir::Left:  onAxis = dx < -1.0f; break;
            case Dir::Right: onAxis = dx >  1.0f; break;
            case Dir::Up:    onAxis = dy < -1.0f; break;
            case Dir::Down:  onAxis = dy >  1.0f; break;
        }
        if (!onAxis) continue;

        // Score: primary distance along the axis + 2× penalty for off-axis drift.
        float primary = (d == Dir::Left || d == Dir::Right) ? std::abs(dx) : std::abs(dy);
        float cross   = (d == Dir::Left || d == Dir::Right) ? std::abs(dy) : std::abs(dx);
        float score = primary + 2.0f * cross;
        if (score < best) {
            best = score;
            winner = &n;
        }
    }
    if (!winner) return false;
    focusedId_ = winner->id;
    return true;
}

bool FocusManager::moveLeft()  { return move(Dir::Left); }
bool FocusManager::moveRight() { return move(Dir::Right); }
bool FocusManager::moveUp()    { return move(Dir::Up); }
bool FocusManager::moveDown()  { return move(Dir::Down); }

void FocusManager::activate() {
    const FocusNode* n = find(focusedId_);
    if (n && n->onOk) n->onOk();
}

}  // namespace iptv::ui

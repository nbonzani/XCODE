#pragma once
// Port of the playlist/navigation slice of playerStore.js.
// Used by PlayerScreen next/prev buttons and by series-auto-play.

#include <string>
#include <vector>

namespace iptv::player {

struct PlaylistItem {
    std::string id;          // stream_id (movie) or episode id (series)
    std::string title;       // display title ("Movie name" or "S01E02 - Title")
    std::string streamUrl;   // full playable URL
    std::string seriesId;    // empty for movies — used to persist watch history
};

class Playlist {
public:
    Playlist() = default;
    explicit Playlist(std::vector<PlaylistItem> items, int startIndex = 0)
        : items_(std::move(items)), index_(startIndex) {}

    bool empty() const           { return items_.empty(); }
    std::size_t size() const     { return items_.size(); }
    int index() const            { return index_; }
    bool hasNext() const         { return index_ + 1 < static_cast<int>(items_.size()); }
    bool hasPrev() const         { return index_ > 0; }

    const PlaylistItem* current() const {
        if (items_.empty() || index_ < 0 || index_ >= static_cast<int>(items_.size())) return nullptr;
        return &items_[index_];
    }
    const PlaylistItem* next() {
        if (!hasNext()) return nullptr;
        ++index_;
        return current();
    }
    const PlaylistItem* prev() {
        if (!hasPrev()) return nullptr;
        --index_;
        return current();
    }

private:
    std::vector<PlaylistItem> items_;
    int index_ = 0;
};

}  // namespace iptv::player

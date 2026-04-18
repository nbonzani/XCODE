#pragma once
// Spatial focus navigation — equivalent of the manual ref/focus tree in the React app.
//
// Widgets register a rectangle and an id. The manager walks sibling rectangles on
// a direction key press and picks the best candidate (closest centre along the axis).

#include <functional>
#include <string>
#include <vector>

namespace iptv::ui {

struct FocusNode {
    std::string id;
    int x = 0, y = 0, w = 0, h = 0;
    // Optional group (e.g. "grid-row-3", "sidebar") for overriding nearest neighbour.
    std::string group;
    // Callback fired when OK is pressed while this node has focus.
    std::function<void()> onOk;
};

class FocusManager {
public:
    void clear();
    void add(FocusNode node);
    void setFocus(const std::string& id);
    std::string focused() const { return focusedId_; }

    // Handle an arrow key. Returns true if focus changed.
    bool moveLeft();
    bool moveRight();
    bool moveUp();
    bool moveDown();

    // Fire the OK handler on the currently focused node.
    void activate();

    // Iterate nodes for drawing focus outlines.
    const std::vector<FocusNode>& nodes() const { return nodes_; }
    const FocusNode* find(const std::string& id) const;

private:
    enum class Dir { Left, Right, Up, Down };
    bool move(Dir d);

    std::vector<FocusNode> nodes_;
    std::string focusedId_;
};

}  // namespace iptv::ui

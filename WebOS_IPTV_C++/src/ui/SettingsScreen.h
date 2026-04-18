#pragma once
// Minimal Xtream credentials form: serverUrl / port / username / password + Save button.
// Navigation is pure-keyboard (arrow keys + OK), mirrored from SettingsScreen.jsx.
//
// The screen is stateful but self-contained; the hosting router just dispatches
// SDL events via handleKey() and paints via render().

#include <functional>
#include <string>

struct SDL_Renderer;

namespace iptv::store { struct Config; }

namespace iptv::ui {

class TextRenderer;
class FocusManager;

class SettingsScreen {
public:
    SettingsScreen(TextRenderer& text, FocusManager& focus);

    void load();                                       // reads current Config into fields
    void handleKey(int keyCode, bool& handled);        // returns handled=true if consumed
    void handleText(const std::string& text);          // for SDL_TEXTINPUT if enabled
    void render(SDL_Renderer* r, int winW, int winH);

    // Called when the user confirms Save with valid credentials.
    void setOnSave(std::function<void()> cb) { on_save_ = std::move(cb); }
    void setOnCancel(std::function<void()> cb) { on_cancel_ = std::move(cb); }

private:
    enum Field { F_Server = 0, F_Port, F_User, F_Pass, F_Save, F_Count };

    void registerFocus();
    void saveCurrent();

    TextRenderer& text_;
    FocusManager& focus_;

    std::string fields_[F_Count];  // server, port, user, pass (Save unused)
    bool loaded_ = false;

    std::function<void()> on_save_;
    std::function<void()> on_cancel_;
};

}  // namespace iptv::ui

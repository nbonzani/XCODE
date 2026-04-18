#include "ui/SettingsScreen.h"

#include <cstdio>

#include <SDL2/SDL.h>

#include "app/KeyCodes.h"
#include "store/Config.h"
#include "ui/FocusManager.h"
#include "ui/TextRenderer.h"

namespace iptv::ui {

namespace {
constexpr int kLabelX   = 200;
constexpr int kValueX   = 500;
constexpr int kFieldW   = 900;
constexpr int kFieldH   = 60;
constexpr int kRowH     = 100;
constexpr int kFirstY   = 260;
}

SettingsScreen::SettingsScreen(TextRenderer& text, FocusManager& focus)
    : text_(text), focus_(focus) {}

void SettingsScreen::load() {
    if (loaded_) return;
    auto c = store::Config::load();
    fields_[F_Server] = c.serverUrl;
    fields_[F_Port]   = c.port;
    fields_[F_User]   = c.username;
    fields_[F_Pass]   = c.password;
    loaded_ = true;
    registerFocus();
}

void SettingsScreen::registerFocus() {
    focus_.clear();
    const char* ids[F_Count] = {"fld_server", "fld_port", "fld_user", "fld_pass", "btn_save"};
    for (int i = 0; i < F_Count; ++i) {
        FocusNode n;
        n.id = ids[i];
        n.x = kValueX;
        n.y = kFirstY + i * kRowH;
        n.w = (i == F_Save) ? 260 : kFieldW;
        n.h = kFieldH;
        if (i == F_Save) {
            n.onOk = [this]{ saveCurrent(); };
        } else {
            // Text fields don't do anything on OK in this MVP — focus sticks and the
            // user edits via "kb paste" mode. A real on-TV keyboard integration comes later.
            n.onOk = nullptr;
        }
        focus_.add(std::move(n));
    }
    focus_.setFocus("fld_server");
}

void SettingsScreen::saveCurrent() {
    store::Config c = store::Config::load();
    c.serverUrl = fields_[F_Server];
    c.port      = fields_[F_Port];
    c.username  = fields_[F_User];
    c.password  = fields_[F_Pass];
    if (c.save() && on_save_) on_save_();
}

void SettingsScreen::handleKey(int code, bool& handled) {
    handled = true;
    if (code == app::KEY::UP)    { focus_.moveUp();    return; }
    if (code == app::KEY::DOWN)  { focus_.moveDown();  return; }
    if (code == app::KEY::LEFT)  { focus_.moveLeft();  return; }
    if (code == app::KEY::RIGHT) { focus_.moveRight(); return; }
    if (app::isOkKey(code))      { focus_.activate();  return; }
    if (app::isBackKey(code))    { if (on_cancel_) on_cancel_(); return; }

    // Backspace on a focused text field.
    const std::string& f = focus_.focused();
    int field = -1;
    if      (f == "fld_server") field = F_Server;
    else if (f == "fld_port")   field = F_Port;
    else if (f == "fld_user")   field = F_User;
    else if (f == "fld_pass")   field = F_Pass;

    if (field >= 0 && code == SDLK_BACKSPACE) {
        if (!fields_[field].empty()) fields_[field].pop_back();
        return;
    }
    handled = false;
}

void SettingsScreen::handleText(const std::string& text) {
    const std::string& f = focus_.focused();
    if      (f == "fld_server") fields_[F_Server] += text;
    else if (f == "fld_port")   fields_[F_Port]   += text;
    else if (f == "fld_user")   fields_[F_User]   += text;
    else if (f == "fld_pass")   fields_[F_Pass]   += text;
}

void SettingsScreen::render(SDL_Renderer* r, int winW, int winH) {
    (void)winH;
    SDL_SetRenderDrawColor(r, 15, 15, 20, 255);
    SDL_RenderClear(r);

    text_.draw("Configuration Xtream", 200, 140, {240, 240, 240, 255});

    const char* labels[F_Count] = {"URL serveur", "Port", "Utilisateur", "Mot de passe", ""};
    for (int i = 0; i < F_Count; ++i) {
        int y = kFirstY + i * kRowH;
        if (i != F_Save) {
            text_.draw(labels[i], kLabelX, y + 14, {180, 180, 190, 255});
            // Field box
            SDL_SetRenderDrawColor(r, 30, 30, 38, 255);
            SDL_Rect box{kValueX, y, kFieldW, kFieldH};
            SDL_RenderFillRect(r, &box);
            std::string shown = fields_[i];
            if (i == F_Pass) shown = std::string(shown.size(), '*');
            text_.draw(shown, kValueX + 12, y + 14, {230, 230, 230, 255});
        } else {
            // Save button
            SDL_SetRenderDrawColor(r, 60, 30, 30, 255);
            SDL_Rect btn{kValueX, y, 260, kFieldH};
            SDL_RenderFillRect(r, &btn);
            text_.draw("  Enregistrer", kValueX, y + 14, {240, 240, 240, 255});
        }
    }

    // Focus outline
    const FocusNode* focused = focus_.find(focus_.focused());
    if (focused) {
        SDL_SetRenderDrawColor(r, 220, 40, 40, 255);
        for (int k = 0; k < 3; ++k) {
            SDL_Rect ro{focused->x - k, focused->y - k, focused->w + 2*k, focused->h + 2*k};
            SDL_RenderDrawRect(r, &ro);
        }
    }

    text_.draw("Astuce : use SDL_TEXTINPUT ou brancher un clavier USB pour saisir.",
               200, winH - 120, {140, 140, 150, 255});
}

}  // namespace iptv::ui

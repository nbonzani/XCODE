#include "ui/SettingsScreen.h"

#include <algorithm>
#include <cstdio>

#include <SDL2/SDL.h>
#include <SDL2/SDL_render.h>

#include "app/KeyCodes.h"
#include "store/Config.h"
#include "ui/Button.h"
#include "ui/Draw.h"
#include "ui/FocusManager.h"
#include "ui/TextRenderer.h"
#include "ui/Theme.h"
#include "ui/VirtualKeyboard.h"

namespace iptv::ui {

namespace {
constexpr int kPad = theme::GridPaddingH;
constexpr int kSectionGap = 28;
constexpr int kFieldH = 52;
constexpr int kLabelW = 220;
constexpr int kInputW = 640;
constexpr const char* kLangCodes[5]  = {"fr", "en", "it", "de", "es"};
constexpr const char* kLangLabels[5] = {"Français", "Anglais", "Italien", "Allemand", "Espagnol"};
constexpr const char* kVostLabels[5] = {"VOSTFR", "VOSTEN", "VOSTIT", "VOSTDE", "VOSTES"};
}

SettingsScreen::SettingsScreen(TextRenderer& text, FocusManager& focus)
    : text_(text), focus_(focus) {
    (void)focus_;
    vkb_ = std::make_unique<VirtualKeyboard>(text_);
}

SettingsScreen::~SettingsScreen() = default;

void SettingsScreen::load() {
    auto c = store::Config::load();
    fields_[0] = c.serverUrl;
    fields_[1] = c.username;
    fields_[2] = c.password;
    for (int i = 0; i < 5; ++i) {
        lang_selected_[i] = std::find(c.selectedLanguages.begin(),
                                      c.selectedLanguages.end(),
                                      kLangCodes[i]) != c.selectedLanguages.end();
    }
    // Si rien n'est coché à la migration, "fr" par défaut.
    if (std::none_of(std::begin(lang_selected_), std::end(lang_selected_), [](bool b){ return b; })) {
        lang_selected_[0] = true;
    }
    for (int i = 0; i < 5; ++i) {
        vost_selected_[i] = std::find(c.vostLanguages.begin(), c.vostLanguages.end(),
                                      kLangCodes[i]) != c.vostLanguages.end();
    }
    loaded_ = true;
    focus_idx_ = F_Server;
}

void SettingsScreen::focusSaveButton() { focus_idx_ = F_Save; }

void SettingsScreen::saveCurrent() {
    store::Config c = store::Config::load();
    c.serverUrl = fields_[0];
    c.port      = "";  // Port embarqué dans l'URL — parse au besoin côté client.
    // Extrait le port si présent dans l'URL : "http://host:port/..."
    auto url = c.serverUrl;
    auto scheme = url.find("://");
    if (scheme != std::string::npos) {
        auto host = scheme + 3;
        auto colon = url.find(':', host);
        auto slash = url.find('/', host);
        if (colon != std::string::npos && (slash == std::string::npos || colon < slash)) {
            auto end = (slash == std::string::npos) ? url.size() : slash;
            c.port = url.substr(colon + 1, end - colon - 1);
            c.serverUrl = url.substr(0, colon) + url.substr(end);
        }
    }
    if (c.port.empty()) c.port = "80";
    c.username  = fields_[1];
    c.password  = fields_[2];
    c.selectedLanguages.clear();
    for (int i = 0; i < 5; ++i) if (lang_selected_[i]) c.selectedLanguages.push_back(kLangCodes[i]);
    c.frenchOnly = (c.selectedLanguages.size() == 1 && c.selectedLanguages[0] == "fr");
    // VOST : ne persiste que les codes dont la langue parente est cochée.
    c.vostLanguages.clear();
    for (int i = 0; i < 5; ++i) {
        if (lang_selected_[i] && vost_selected_[i])
            c.vostLanguages.push_back(kLangCodes[i]);
    }
    if (c.save() && on_save_) on_save_();
}

void SettingsScreen::handleKey(int code, bool& handled) {
    handled = true;
    if (vkb_ && vkb_->isOpen()) {
        int k = 0;
        if (code == app::KEY::UP)    k = SDLK_UP;
        else if (code == app::KEY::DOWN)  k = SDLK_DOWN;
        else if (code == app::KEY::LEFT)  k = SDLK_LEFT;
        else if (code == app::KEY::RIGHT) k = SDLK_RIGHT;
        else if (app::isOkKey(code))      k = SDLK_RETURN;
        else if (app::isBackKey(code))    k = SDLK_AC_BACK;
        if (k) vkb_->handleKey(k);
        return;
    }

    if (app::isBackKey(code)) { if (on_cancel_) on_cancel_(); return; }

    const bool onButtonRow = (focus_idx_ == F_Cancel || focus_idx_ == F_Save);

    // Les slots F_Vost0..F_Vost4 ne sont focusables que si la langue parente
    // correspondante est cochée. Skip dans la navigation UP/DOWN.
    auto isVostSlotVisible = [&](int idx) {
        if (idx < F_Vost0 || idx > F_Vost4) return true;
        return lang_selected_[idx - F_Vost0];
    };

    if (code == app::KEY::UP) {
        if (onButtonRow) { focus_idx_ = F_Categories; return; }
        int i = focus_idx_;
        do { if (i > 0) i--; else break; } while (!isVostSlotVisible(i));
        focus_idx_ = i;
        return;
    }
    if (code == app::KEY::DOWN) {
        if (onButtonRow) return;
        if (focus_idx_ == F_Categories) { focus_idx_ = F_Save; return; }
        int i = focus_idx_;
        do { if (i < F_Categories) i++; else break; } while (!isVostSlotVisible(i));
        focus_idx_ = i;
        return;
    }
    if (code == app::KEY::LEFT) {
        if (focus_idx_ == F_Save)   { focus_idx_ = F_Cancel; return; }
        return;
    }
    if (code == app::KEY::RIGHT) {
        if (focus_idx_ == F_Cancel) { focus_idx_ = F_Save; return; }
        return;
    }
    if (app::isOkKey(code)) {
        if (focus_idx_ <= F_Pass) {
            // Ouvrir le VKB pour saisir ce champ
            vkb_target_field_ = focus_idx_;
            vkb_->setMasked(focus_idx_ == F_Pass);
            vkb_->setOnDone([this](const std::string& s){
                if (vkb_target_field_ >= 0 && vkb_target_field_ < 3)
                    fields_[vkb_target_field_] = s;
                vkb_target_field_ = -1;
            });
            vkb_->setOnCancel([this]{ vkb_target_field_ = -1; });
            const char* ph =
                focus_idx_ == F_Server ? "http://for-smart.cc" :
                focus_idx_ == F_User   ? "utilisateur" : "mot de passe";
            vkb_->open(fields_[focus_idx_], ph);
            return;
        }
        if (focus_idx_ >= F_Lang0 && focus_idx_ <= F_Lang4) {
            int i = focus_idx_ - F_Lang0;
            lang_selected_[i] = !lang_selected_[i];
            return;
        }
        if (focus_idx_ >= F_Vost0 && focus_idx_ <= F_Vost4) {
            int i = focus_idx_ - F_Vost0;
            if (lang_selected_[i]) vost_selected_[i] = !vost_selected_[i];
            return;
        }
        switch (focus_idx_) {
            case F_Categories: if (on_catalog_filter_) on_catalog_filter_(); return;
            case F_Cancel:     if (on_cancel_) on_cancel_();                 return;
            case F_Save:       saveCurrent();                                return;
            case F_TestConn:
                if (on_test_conn_ && !test_in_progress_) {
                    test_in_progress_ = true;
                    test_status_msg_ = "Test en cours…";
                    on_test_conn_(fields_[F_Server], fields_[F_User], fields_[F_Pass],
                                  [this](bool ok, std::string msg){
                                      test_in_progress_ = false;
                                      test_last_ok_ = ok;
                                      test_status_msg_ = ok
                                          ? (msg.empty() ? std::string("OK") : msg)
                                          : (std::string("Échec : ") + msg);
                                  });
                }
                return;
            default: return;
        }
    }
    handled = false;
}

void SettingsScreen::handleText(const std::string& text) {
    (void)text;
    // Plus utilisé — le VKB gère la saisie.
}

void SettingsScreen::render(SDL_Renderer* r, int winW, int winH) {
    draw::fillRect(r, {0, 0, winW, winH}, theme::BgPrimary);

    text_.draw(theme::FontStyle::Xl2Bold, "Paramètres", kPad, 40, theme::TextPrimary);
    draw::hLine(r, 0, 120, winW, theme::Divider);

    SDL_Rect panel{kPad, 140, winW - 2 * kPad, winH - 180};
    draw::fillRoundedRect(r, panel, theme::RadiusLg, theme::SurfaceCard);
    draw::strokeRoundedRect(r, panel, theme::RadiusLg, 1, theme::Border);

    int y = panel.y + 32;
    int xL = panel.x + 48;

    // ── Section Serveur Xtream ──────────────────────────────────────────
    text_.draw(theme::FontStyle::LgBold, "Serveur Xtream", xL, y, theme::Accent);
    y += 56;
    const char* labels[3] = {"URL serveur", "Utilisateur", "Mot de passe"};
    for (int i = 0; i < 3; ++i) {
        text_.draw(theme::FontStyle::MdRegular, labels[i], xL, y + 6, theme::TextSecondary);
        SDL_Rect input{xL + kLabelW, y, kInputW, kFieldH};
        bool focus = (focus_idx_ == i);
        draw::fillRoundedRect(r, input, theme::RadiusMd, theme::SurfaceInput);
        if (focus) {
            draw::focusRing(r, input, theme::RadiusMd, theme::Accent, 2, 0);
        } else {
            draw::strokeRoundedRect(r, input, theme::RadiusMd, 1, theme::Border);
        }
        std::string shown = fields_[i];
        if (i == 2) shown = std::string(shown.size(), '*');
        if (shown.empty()) {
            const char* ph = (i == 0) ? "ex : http://for-smart.cc"
                          : (i == 1) ? "utilisateur" : "mot de passe";
            text_.drawEllipsis(theme::FontStyle::MdRegular, ph,
                               input.x + 16,
                               input.y + (input.h - text_.lineHeight(theme::FontStyle::MdRegular)) / 2,
                               input.w - 32, theme::TextPlaceholder);
        } else {
            text_.drawEllipsis(theme::FontStyle::MdRegular, shown,
                               input.x + 16,
                               input.y + (input.h - text_.lineHeight(theme::FontStyle::MdRegular)) / 2,
                               input.w - 32, theme::TextPrimary);
        }
        y += kFieldH + 12;
    }

    // ── Bouton "Tester la connexion" ────────────────────────────────────
    {
        ButtonStyle stTest{ButtonVariant::Secondary, theme::FontStyle::MdBold};
        int tw = 0, th = 0;
        text_.measure(stTest.font, "Tester la connexion", tw, th);
        SDL_Rect tbtn{xL, y, tw + stTest.paddingH * 2, kFieldH};
        drawButtonInRect(r, text_, tbtn, "Tester la connexion",
                         focus_idx_ == F_TestConn, stTest);
        // Feedback à droite : vert si OK, rouge si échec, gris sinon.
        if (!test_status_msg_.empty()) {
            SDL_Color col = test_in_progress_
                ? theme::TextSecondary
                : (test_last_ok_ ? SDL_Color{0x2e, 0xcc, 0x71, 255}
                                 : SDL_Color{0xe7, 0x4c, 0x3c, 255});
            text_.draw(theme::FontStyle::MdRegular, test_status_msg_,
                       tbtn.x + tbtn.w + 24,
                       y + (kFieldH - text_.lineHeight(theme::FontStyle::MdRegular)) / 2,
                       col);
        }
        y += kFieldH + 12;
    }
    y += kSectionGap;

    // ── Section Langues ─────────────────────────────────────────────────
    text_.draw(theme::FontStyle::LgBold, "Langues du catalogue", xL, y, theme::Accent);
    y += 56;
    text_.draw(theme::FontStyle::MdRegular, "Cochez les langues à afficher :",
               xL, y + 6, theme::TextSecondary);
    y += 40;
    int cbX = xL;
    for (int i = 0; i < 5; ++i) {
        bool focus = (focus_idx_ == F_Lang0 + i);
        int lw = 0, lh = 0;
        text_.measure(theme::FontStyle::MdRegular, kLangLabels[i], lw, lh);
        SDL_Rect row{cbX - 8, y, 40 + lw + 24, 40};
        if (focus) {
            draw::fillRoundedRect(r, row, theme::RadiusSm, theme::BgTertiary);
            draw::strokeRoundedRect(r, row, theme::RadiusSm, 2, theme::Accent);
        }
        SDL_Rect cb{row.x + 8, row.y + (row.h - 24) / 2, 24, 24};
        draw::strokeRoundedRect(r, cb, theme::RadiusSm, 2,
                                lang_selected_[i] ? theme::Accent : theme::Border);
        if (lang_selected_[i]) {
            SDL_Rect inner{cb.x + 5, cb.y + 5, 14, 14};
            draw::fillRoundedRect(r, inner, theme::RadiusSm, theme::Accent);
        }
        text_.draw(theme::FontStyle::MdRegular, kLangLabels[i],
                   cb.x + 32, cb.y + (cb.h - lh) / 2, theme::TextPrimary);
        cbX = row.x + row.w + 24;
        // Wrap après 3 boutons
        if (i == 2) { cbX = xL; y += 48; }
    }
    y += kFieldH + kSectionGap;

    // ── Section Sous-titres (VOST par langue) ───────────────────────────
    text_.draw(theme::FontStyle::LgBold, "Sous-titres", xL, y, theme::Accent);
    y += 56;
    // Compte les langues actives pour savoir si on a au moins une case.
    int nbActiveLangs = 0;
    for (int i = 0; i < 5; ++i) if (lang_selected_[i]) nbActiveLangs++;
    if (nbActiveLangs == 0) {
        text_.draw(theme::FontStyle::MdRegular,
                   "(aucune langue sélectionnée)",
                   xL, y + 6, theme::TextSecondary);
        y += 40;
    } else {
        text_.draw(theme::FontStyle::MdRegular,
                   "Inclure les VO sous-titrées :",
                   xL, y + 6, theme::TextSecondary);
        y += 40;
        int cbX = xL;
        int nbOnRow = 0;
        for (int i = 0; i < 5; ++i) {
            if (!lang_selected_[i]) continue;  // hide for unselected langs
            bool focus = (focus_idx_ == F_Vost0 + i);
            int lw = 0, lh = 0;
            text_.measure(theme::FontStyle::MdRegular, kVostLabels[i], lw, lh);
            SDL_Rect row{cbX - 8, y, 40 + lw + 24, 40};
            if (focus) {
                draw::fillRoundedRect(r, row, theme::RadiusSm, theme::BgTertiary);
                draw::strokeRoundedRect(r, row, theme::RadiusSm, 2, theme::Accent);
            }
            SDL_Rect cb{row.x + 8, row.y + (row.h - 24) / 2, 24, 24};
            draw::strokeRoundedRect(r, cb, theme::RadiusSm, 2,
                                    vost_selected_[i] ? theme::Accent : theme::Border);
            if (vost_selected_[i]) {
                SDL_Rect inner{cb.x + 5, cb.y + 5, 14, 14};
                draw::fillRoundedRect(r, inner, theme::RadiusSm, theme::Accent);
            }
            text_.draw(theme::FontStyle::MdRegular, kVostLabels[i],
                       cb.x + 32, cb.y + (cb.h - lh) / 2, theme::TextPrimary);
            cbX = row.x + row.w + 24;
            nbOnRow++;
            if (nbOnRow == 3) { cbX = xL; y += 48; nbOnRow = 0; }
        }
    }
    y += kFieldH + kSectionGap;

    // ── Section Catégories ──────────────────────────────────────────────
    text_.draw(theme::FontStyle::LgBold, "Catégories", xL, y, theme::Accent);
    y += 56;
    ButtonStyle stBtn{ButtonVariant::Secondary, theme::FontStyle::MdBold};
    int tw = 0, th = 0;
    text_.measure(stBtn.font, "Sélection des catégories...", tw, th);
    SDL_Rect btn{xL, y, tw + stBtn.paddingH * 2, kFieldH};
    drawButtonInRect(r, text_, btn, "Sélection des catégories...",
                     focus_idx_ == F_Categories, stBtn);

    // ── Boutons bas : Annuler / Enregistrer ─────────────────────────────
    int by = panel.y + panel.h - 88;
    ButtonStyle sP{ButtonVariant::Primary,   theme::FontStyle::MdBold};
    ButtonStyle sS{ButtonVariant::Secondary, theme::FontStyle::MdBold};
    int twS = 0, thS = 0;
    text_.measure(sP.font, "Enregistrer", twS, thS);
    int wSave = twS + sP.paddingH * 2;
    int wCancel = 0, hC = 0;
    text_.measure(sS.font, "Annuler", wCancel, hC);
    wCancel += sS.paddingH * 2;
    int rightEdge = panel.x + panel.w - 48;
    SDL_Rect saveR{rightEdge - wSave, by, wSave, thS + sP.paddingV * 2};
    drawButtonInRect(r, text_, saveR, "Enregistrer", focus_idx_ == F_Save, sP);
    SDL_Rect cancelR{saveR.x - 16 - wCancel, by, wCancel, hC + sS.paddingV * 2};
    drawButtonInRect(r, text_, cancelR, "Annuler", focus_idx_ == F_Cancel, sS);

    // VKB par-dessus
    if (vkb_ && vkb_->isOpen()) vkb_->render(r, winW, winH);
}

}  // namespace iptv::ui

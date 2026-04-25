#pragma once
// SettingsScreen — URL serveur + user/pass + langues (checkboxes) +
// bouton "Sélection des catégories". Clavier virtuel overlay pour la saisie.

#include <functional>
#include <memory>
#include <string>
#include <vector>

struct SDL_Renderer;

namespace iptv::store { struct Config; }

namespace iptv::ui {

class TextRenderer;
class FocusManager;
class VirtualKeyboard;

class SettingsScreen {
public:
    SettingsScreen(TextRenderer& text, FocusManager& focus);
    ~SettingsScreen();

    void load();
    void handleKey(int keyCode, bool& handled);
    void handleText(const std::string& text);
    void render(SDL_Renderer* r, int winW, int winH);

    // Place le focus sur le bouton "Enregistrer". Appelé par l'app au retour
    // de la fenêtre "Sélection des catégories" pour éviter de devoir re-
    // scroller tout le formulaire.
    void focusSaveButton();

    void setOnSave(std::function<void()> cb) { on_save_ = std::move(cb); }
    void setOnCancel(std::function<void()> cb) { on_cancel_ = std::move(cb); }
    void setOnOpenCatalogFilter(std::function<void()> cb) { on_catalog_filter_ = std::move(cb); }
    // cb.first = true si la connexion avec les valeurs courantes réussit,
    // avec un message à afficher ; appelé en async (thread) pour ne pas
    // bloquer l'UI. Défini par main.cpp via XtreamClient.authenticate().
    void setOnTestConnection(std::function<void(const std::string& url,
                                                 const std::string& user,
                                                 const std::string& pass,
                                                 std::function<void(bool, std::string)> cb)> f) {
        on_test_conn_ = std::move(f);
    }

private:
    // Ordre vertical des lignes focusables.
    enum Field {
        F_Server = 0,
        F_User,
        F_Pass,
        F_TestConn,
        F_Lang0,         // Français
        F_Lang1,         // Anglais
        F_Lang2,         // Italien
        F_Lang3,         // Allemand
        F_Lang4,         // Espagnol
        F_Vost0,         // VOSTFR (si langue FR cochée)
        F_Vost1,         // VOSTEN
        F_Vost2,         // VOSTIT
        F_Vost3,         // VOSTDE
        F_Vost4,         // VOSTES
        F_Categories,
        F_Cancel,
        F_Save,
        F_Count,
    };

    void saveCurrent();

    TextRenderer& text_;
    FocusManager& focus_;

    std::string fields_[3];  // server, user, pass
    // 5 langues : fr/en/it/de/es
    bool lang_selected_[5] = {true, false, false, false, false};
    // VOST par langue : case cochée = inclure les VO sous-titrées dans cette
    // langue, en plus de la VF équivalente. Uniquement visible/focusable si
    // la langue parente est cochée dans lang_selected_.
    bool vost_selected_[5] = {false, false, false, false, false};
    int focus_idx_ = 0;
    bool loaded_ = false;

    std::unique_ptr<VirtualKeyboard> vkb_;
    int vkb_target_field_ = -1;

    std::function<void()> on_save_;
    std::function<void()> on_cancel_;
    std::function<void()> on_catalog_filter_;
    std::function<void(const std::string&, const std::string&, const std::string&,
                        std::function<void(bool, std::string)>)> on_test_conn_;

    // Feedback du bouton "Tester la connexion". État temporaire, affiché
    // à droite du bouton ("Test en cours…", "OK", "Échec: …").
    std::string test_status_msg_;
    bool test_in_progress_ = false;
    bool test_last_ok_ = false;
};

}  // namespace iptv::ui

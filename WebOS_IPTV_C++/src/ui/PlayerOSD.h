#pragma once
// Player OSD façon tivimate (WebOS IPTV React) :
//   Overlay bas d'écran avec 3 lignes :
//     - Info row  : titre (+ "i/N" playlist) à gauche, temps + hints couleur à droite
//     - Timeline  : barre de progression avec fill + thumb
//     - Button row: [⏮ ▶/⏸ ⏭]  centre-gauche  …  [🎵 🔤 🔊/🔇 ✕] centre-droit
//   Deux modes :
//     Mode LECTURE (défaut)      — OK=Play/Pause, ←/→=−10/+10s, FF/REW=±5min,
//                                   ↓=enter BTNMODE, ↑=Volume+5, GREEN=Next,
//                                   YELLOW=Prev, BLUE=Audio menu, RED=Sub menu,
//                                   BACK=Close.
//     Mode BOUTONS (après ↓)      — ←/→ déplacent le focus, OK active le bouton,
//                                   ↑ ou BACK → retour LECTURE.
//   Menus modaux :
//     Audio menu (haut-gauche)   — ↑↓ navigate, OK select, BLUE/BACK close.
//     Subs menu  (haut-droite)   — ↑↓ navigate, OK select, RED/BACK close. Le
//                                   premier item "Désactivés" a id=-1.
//   Auto-hide : 3000 ms après dernier poke(), sauf si BTNMODE ou menu ouvert.

#include <cstdint>
#include <string>
#include <vector>

struct SDL_Renderer;

namespace iptv::ui {

class TextRenderer;

// Actions exposées : résultat de btnActivate() + utile côté main.cpp pour le
// dispatch des touches couleur quand la barre n'est pas en mode boutons.
enum class PlayerAction {
    None,
    PlayPause,
    SeekBack5m,
    SeekBack30,
    SeekFwd30,
    SeekFwd5m,
    Prev,
    Next,
    OpenAudio,
    OpenSub,
    ToggleMute,
    Close,
};

struct PlayerOSDState {
    std::string title;

    // Playlist (-1,0 = pas de playlist)
    int  playlistIdx = -1;
    int  playlistTotal = 0;

    // Info stream (affichés dans l'info row)
    std::string filename;          // basename extrait de l'URL lue
    std::string videoCodec;        // "H264" / "HEVC" / "MPEG-4" / …
    std::string audioCodec;        // "AC3" / "AAC" / …
    int         videoWidth  = 0;   // 0 = inconnu
    int         videoHeight = 0;
    std::string decoderMode;       // "HW NDL" / "SW avdec" / "GStreamer" / …

    // Progression + état
    double position = 0.0;
    double duration = 0.0;
    bool   paused   = false;
    bool   muted    = false;
    int    volume   = 100;   // 0..100

    // Pistes audio/subs
    std::vector<std::string> audioLabels;
    int activeAudioIdx = 0;
    std::vector<std::string> subLabels;      // "Désactivés" implicite à id=-1
    int activeSubIdx = -1;

    // Mode / focus
    bool btnMode = false;
    int  btnFocusIdx = 0;

    // Menus
    bool audioMenuOpen = false;
    int  audioMenuIdx  = 0;
    bool subMenuOpen   = false;
    int  subMenuIdx    = -1;

    // Visibilité
    bool visible = true;
};

class PlayerOSD {
public:
    explicit PlayerOSD(TextRenderer& text) : text_(text) {}

    // ── Visibilité / timer auto-hide ─────────────────────────────────────
    void poke();                     // toute activité utilisateur : affiche + reset timer
    void tick(uint32_t nowMs);       // appelé chaque frame
    bool isVisible() const { return state_.visible; }
    void setTimeoutMs(uint32_t t) { timeoutMs_ = t; }
    // One-shot : affiche l'OSD et programme son hide dans `ms` millisecondes.
    // Utilisé au démarrage de la lecture pour cacher la barre 2 s après la
    // première frame jouée (transitoire — indépendant du timeoutMs_).
    void hideIn(uint32_t ms);
    // Cache immédiatement l'OSD (Play/Pause ou flèche haut côté utilisateur).
    void hideNow() { state_.visible = false; }

    // ── Setters d'état ───────────────────────────────────────────────────
    void setTitle(const std::string& t)        { state_.title = t; }
    void setPlaylist(int idx, int total)       { state_.playlistIdx = idx; state_.playlistTotal = total; }
    void setProgress(double pos, double dur)   { state_.position = pos; state_.duration = dur; }
    void setPlaying(bool playing)              { state_.paused = !playing; }
    void setMuted(bool m)                      { state_.muted = m; }
    void setVolume(int v)                      { state_.volume = v < 0 ? 0 : (v > 100 ? 100 : v); }
    void setAudioTracks(const std::vector<std::string>& labels, int activeIdx) {
        state_.audioLabels = labels; state_.activeAudioIdx = activeIdx;
    }
    void setSubTracks(const std::vector<std::string>& labels, int activeIdx) {
        state_.subLabels = labels; state_.activeSubIdx = activeIdx;
    }
    // Info codec / résolution / pipeline de décodage (affiché dans l'info row).
    void setStreamInfo(const std::string& videoCodec,
                       const std::string& audioCodec,
                       int width, int height,
                       const std::string& decoderMode) {
        state_.videoCodec  = videoCodec;
        state_.audioCodec  = audioCodec;
        state_.videoWidth  = width;
        state_.videoHeight = height;
        state_.decoderMode = decoderMode;
    }
    void setVideoResolution(int w, int h) {
        state_.videoWidth = w; state_.videoHeight = h;
    }
    void setFilename(const std::string& f) { state_.filename = f; }

    // Accesseurs utiles (capacités selon l'état)
    bool hasAudio()    const { return !state_.audioLabels.empty(); }
    bool hasSubs()     const { return !state_.subLabels.empty(); }
    bool hasPlaylist() const { return state_.playlistTotal > 1; }
    bool hasPrev()     const { return hasPlaylist() && state_.playlistIdx > 0; }
    bool hasNext()     const { return hasPlaylist() && state_.playlistIdx < state_.playlistTotal - 1; }

    // ── Mode boutons ─────────────────────────────────────────────────────
    void enterBtnMode();
    void exitBtnMode();
    bool inBtnMode() const { return state_.btnMode; }
    void btnMove(int dir);                     // LEFT/RIGHT dans la barre
    PlayerAction btnActivate() const;          // action correspondant au bouton focusé

    // ── Menus ────────────────────────────────────────────────────────────
    void openAudioMenu();
    void closeAudioMenu();
    bool audioMenuOpen() const { return state_.audioMenuOpen; }
    void audioMenuMove(int dir);               // UP/DOWN
    int  audioMenuCurrentIdx() const { return state_.audioMenuIdx; }

    void openSubMenu();
    void closeSubMenu();
    bool subMenuOpen() const { return state_.subMenuOpen; }
    void subMenuMove(int dir);                 // UP/DOWN
    int  subMenuCurrentIdx() const { return state_.subMenuIdx; }

    bool anyMenuOpen() const { return state_.audioMenuOpen || state_.subMenuOpen; }

    // ── Rendering ────────────────────────────────────────────────────────
    void render(SDL_Renderer* renderer, int winW, int winH);

    // Accès direct (read-only) — pratique pour le debug / tests.
    const PlayerOSDState& state() const { return state_; }

private:
    // Construit la liste ordonnée des boutons visibles (pareil que tivimate).
    std::vector<PlayerAction> visibleButtons() const;

    void renderBar(SDL_Renderer* r, int winW, int winH);
    void renderAudioMenu(SDL_Renderer* r, int winW, int winH);
    void renderSubMenu(SDL_Renderer* r, int winW, int winH);

    TextRenderer&  text_;
    PlayerOSDState state_;
    uint32_t       lastPokeMs_ = 0;
    uint32_t       timeoutMs_  = 10000;
};

}  // namespace iptv::ui

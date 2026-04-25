#include "ui/PlayerOSD.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>

#include <SDL2/SDL.h>

#include "ui/Draw.h"
#include "ui/TextRenderer.h"
#include "ui/Theme.h"

namespace iptv::ui {

namespace {

// Helper format m:ss ou h:mm:ss.
std::string formatTime(double seconds) {
    if (seconds < 0 || seconds != seconds) seconds = 0;
    int s = static_cast<int>(seconds);
    int h = s / 3600;
    int m = (s % 3600) / 60;
    int sec = s % 60;
    char buf[16];
    if (h > 0) std::snprintf(buf, sizeof(buf), "%d:%02d:%02d", h, m, sec);
    else       std::snprintf(buf, sizeof(buf), "%d:%02d", m, sec);
    return buf;
}

// Tous les draws de l'OSD sont en BLEND : la vidéo sous-jacente (plan NDL ou
// texture SDL) transparaît selon l'alpha. Aucune couleur n'est opaque à 255
// sauf les fills pleins des widgets (progress fill, thumb).
inline void blendFill(SDL_Renderer* r, SDL_Rect rc, SDL_Color c) {
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(r, c.r, c.g, c.b, c.a);
    SDL_RenderFillRect(r, &rc);
}

// Bordure 2 px autour d'un rect en blend.
inline void blendStroke2(SDL_Renderer* r, SDL_Rect rc, SDL_Color c) {
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(r, c.r, c.g, c.b, c.a);
    SDL_Rect t1{rc.x, rc.y, rc.w, 2};
    SDL_Rect t2{rc.x, rc.y + rc.h - 2, rc.w, 2};
    SDL_Rect t3{rc.x, rc.y, 2, rc.h};
    SDL_Rect t4{rc.x + rc.w - 2, rc.y, 2, rc.h};
    SDL_RenderFillRect(r, &t1);
    SDL_RenderFillRect(r, &t2);
    SDL_RenderFillRect(r, &t3);
    SDL_RenderFillRect(r, &t4);
}

// Gradient vertical de alpha0 (haut) à alpha1 (bas) sur couleur noire.
// Utilisé pour fondu doux en haut de la bande info.
inline void blendGradientVAlpha(SDL_Renderer* r, SDL_Rect rc,
                                uint8_t a0, uint8_t a1) {
    if (rc.h <= 0 || rc.w <= 0) return;
    SDL_SetRenderDrawBlendMode(r, SDL_BLENDMODE_BLEND);
    constexpr int kBandH = 8;
    int nBands = (rc.h + kBandH - 1) / kBandH;
    for (int b = 0; b < nBands; ++b) {
        float t = (nBands == 1) ? 0.0f : (float)b / (float)(nBands - 1);
        uint8_t a = (uint8_t)(a0 + (a1 - a0) * t);
        SDL_SetRenderDrawColor(r, 0, 0, 0, a);
        int yy = rc.y + b * kBandH;
        int hh = std::min(kBandH, rc.y + rc.h - yy);
        SDL_Rect strip{rc.x, yy, rc.w, hh};
        SDL_RenderFillRect(r, &strip);
    }
}

}  // namespace

// ── Visibilité / timer ──────────────────────────────────────────────────────

void PlayerOSD::poke() {
    state_.visible = true;
    lastPokeMs_ = SDL_GetTicks();
}

void PlayerOSD::hideIn(uint32_t ms) {
    state_.visible = true;
    // Astuce : on "antidate" lastPokeMs_ pour que le timeout restant soit `ms`.
    uint32_t now = SDL_GetTicks();
    if (ms >= timeoutMs_) lastPokeMs_ = now;
    else                  lastPokeMs_ = now - (timeoutMs_ - ms);
}

void PlayerOSD::tick(uint32_t nowMs) {
    if (!state_.visible) return;
    // Toujours visible si BTNMODE ou menu ouvert ou pause.
    if (state_.btnMode || state_.audioMenuOpen || state_.subMenuOpen ||
        state_.paused) return;
    if (nowMs - lastPokeMs_ > timeoutMs_) state_.visible = false;
}

// ── Liste ordonnée des boutons visibles ────────────────────────────────────

std::vector<PlayerAction> PlayerOSD::visibleButtons() const {
    std::vector<PlayerAction> out;
    if (hasPlaylist()) out.push_back(PlayerAction::Prev);
    out.push_back(PlayerAction::SeekBack5m);
    out.push_back(PlayerAction::SeekBack30);
    out.push_back(PlayerAction::PlayPause);
    out.push_back(PlayerAction::SeekFwd30);
    out.push_back(PlayerAction::SeekFwd5m);
    if (hasPlaylist()) out.push_back(PlayerAction::Next);
    // OpenAudio bouton n'a de sens qu'avec ≥2 pistes : pas la peine d'afficher
    // un menu où on ne peut rien choisir. Si 0 ou 1 piste → on cache.
    if (state_.audioLabels.size() > 1) out.push_back(PlayerAction::OpenAudio);
    if (hasSubs())     out.push_back(PlayerAction::OpenSub);
    out.push_back(PlayerAction::ToggleMute);
    out.push_back(PlayerAction::Close);
    return out;
}

// ── Mode boutons ───────────────────────────────────────────────────────────

void PlayerOSD::enterBtnMode() {
    state_.btnMode = true;
    state_.visible = true;
    auto btns = visibleButtons();
    int idx = 0;
    for (size_t i = 0; i < btns.size(); ++i) {
        if (btns[i] == PlayerAction::PlayPause) { idx = (int)i; break; }
    }
    state_.btnFocusIdx = idx;
}

void PlayerOSD::exitBtnMode() {
    state_.btnMode = false;
    lastPokeMs_ = SDL_GetTicks();
}

void PlayerOSD::btnMove(int dir) {
    auto btns = visibleButtons();
    if (btns.empty()) return;
    int n = (int)btns.size();
    state_.btnFocusIdx = std::clamp(state_.btnFocusIdx + dir, 0, n - 1);
}

PlayerAction PlayerOSD::btnActivate() const {
    auto btns = visibleButtons();
    if (btns.empty()) return PlayerAction::None;
    int i = std::clamp(state_.btnFocusIdx, 0, (int)btns.size() - 1);
    return btns[i];
}

// ── Menus ──────────────────────────────────────────────────────────────────

void PlayerOSD::openAudioMenu() {
    if (!hasAudio()) return;
    state_.audioMenuOpen = true;
    state_.subMenuOpen   = false;
    state_.audioMenuIdx  = state_.activeAudioIdx;
    state_.visible = true;
}
void PlayerOSD::closeAudioMenu() { state_.audioMenuOpen = false; lastPokeMs_ = SDL_GetTicks(); }

void PlayerOSD::audioMenuMove(int dir) {
    int n = (int)state_.audioLabels.size();
    if (n <= 0) return;
    state_.audioMenuIdx = std::clamp(state_.audioMenuIdx + dir, 0, n - 1);
}

void PlayerOSD::openSubMenu() {
    if (!hasSubs()) return;
    state_.subMenuOpen = true;
    state_.audioMenuOpen = false;
    state_.subMenuIdx  = state_.activeSubIdx;
    state_.visible = true;
}
void PlayerOSD::closeSubMenu() { state_.subMenuOpen = false; lastPokeMs_ = SDL_GetTicks(); }

void PlayerOSD::subMenuMove(int dir) {
    int n = (int)state_.subLabels.size();
    state_.subMenuIdx = std::clamp(state_.subMenuIdx + dir, -1, n - 1);
}

// ── Rendering ──────────────────────────────────────────────────────────────

void PlayerOSD::render(SDL_Renderer* r, int winW, int winH) {
    if (!state_.visible) return;
    renderBar(r, winW, winH);
    if (state_.audioMenuOpen) renderAudioMenu(r, winW, winH);
    if (state_.subMenuOpen)   renderSubMenu(r, winW, winH);
}

void PlayerOSD::renderBar(SDL_Renderer* r, int winW, int winH) {
    // Zone OSD en bas : 260 px.
    const int zoneH = 260;
    SDL_Rect zone{0, winH - zoneH, winW, zoneH};

    // Fond : gradient vertical noir semi-transparent (alpha 0 haut → 180 bas).
    // Les infos + boutons transparaissent bien sur la vidéo, contraste suffisant
    // pour la lisibilité du texte clair.
    blendGradientVAlpha(r, zone, 0, 190);
    // Liseret accent en haut du fondu (1 px).
    blendFill(r, SDL_Rect{0, zone.y, winW, 1}, SDL_Color{0x4a, 0x9e, 0xff, 120});

    // ── Ligne 1 : info ───────────────────────────────────────────────────
    const int infoY = zone.y + 20;
    int leftX  = 40;
    int titleMaxW = (int)(winW * 0.55f) - leftX;
    text_.drawEllipsis(theme::FontStyle::LgBold, state_.title, leftX, infoY,
                       titleMaxW, theme::TextPrimary);

    // Sous-ligne d'infos techniques : fichier · codec · résolution · décodeur · audio.
    std::string techLine;
    if (!state_.filename.empty()) techLine = state_.filename;
    if (!state_.videoCodec.empty()) {
        techLine += (techLine.empty() ? "" : "  \xC2\xB7  ");
        techLine += state_.videoCodec;
    }
    if (state_.videoWidth > 0 && state_.videoHeight > 0) {
        char buf[48];
        std::snprintf(buf, sizeof(buf), "%s%dx%d",
                      techLine.empty() ? "" : "  \xC2\xB7  ",
                      state_.videoWidth, state_.videoHeight);
        techLine += buf;
    }
    if (!state_.decoderMode.empty()) {
        techLine += (techLine.empty() ? "" : "  \xC2\xB7  ");
        techLine += state_.decoderMode;
    }
    if (!state_.audioCodec.empty()) {
        techLine += (techLine.empty() ? "" : "  \xC2\xB7  audio ");
        techLine += state_.audioCodec;
    }
    if (hasPlaylist()) {
        char buf[32];
        std::snprintf(buf, sizeof(buf), "  \xC2\xB7  %d / %d",
                      state_.playlistIdx + 1, state_.playlistTotal);
        techLine += buf;
    }
    if (!techLine.empty()) {
        text_.drawEllipsis(theme::FontStyle::XsRegular, techLine, leftX,
                           infoY + text_.lineHeight(theme::FontStyle::LgBold) + 4,
                           titleMaxW, theme::TextSecondary);
    }

    // Droite : temps + hints couleur.
    std::string timeStr = formatTime(state_.position) + " / " +
                          (state_.duration > 0 ? formatTime(state_.duration)
                                               : std::string("--:--"));
    int tw = 0, th = 0;
    text_.measure(theme::FontStyle::MdBold, timeStr, tw, th);
    int rightX = winW - 40 - tw;
    text_.draw(theme::FontStyle::MdBold, timeStr, rightX, infoY + 2,
               theme::TextPrimary);

    // Hints couleur sous le temps, de droite à gauche selon disponibilité.
    // Mapping télécommande 2026-04-24 :
    //   🔴 rouge = quitter le lecteur
    //   🟢 vert  = épisode précédent
    //   🟡 jaune = épisode suivant
    //   🔵 bleu  = menu piste audio
    struct Hint { SDL_Color dot; const char* label; bool show; };
    Hint hints[] = {
        {SDL_Color{0xf8, 0x71, 0x71, 255}, "Quitter", true},
        {SDL_Color{0x4a, 0x9e, 0xff, 255}, "Audio",   hasAudio()},
        {SDL_Color{0xfb, 0xbf, 0x24, 255}, "Suiv.",   hasNext()},
        {SDL_Color{0x4a, 0xde, 0x80, 255}, "Préc.",   hasPrev()},
    };
    int hintY = infoY + th + 10;
    int hintX = winW - 40;
    for (const auto& h : hints) {
        if (!h.show) continue;
        int lw = 0, lh = 0;
        text_.measure(theme::FontStyle::XsRegular, h.label, lw, lh);
        int rowW = 12 + 6 + lw;
        hintX -= rowW;
        blendFill(r, SDL_Rect{hintX, hintY + 4, 12, 12}, h.dot);
        text_.draw(theme::FontStyle::XsRegular, h.label, hintX + 18, hintY,
                   theme::TextSecondary);
        hintX -= 18;
    }

    // ── Ligne 2 : timeline ───────────────────────────────────────────────
    const int tlX = 40;
    const int tlY = zone.y + 110;
    const int tlW = winW - 80;
    const int tlH = 6;
    blendFill(r, SDL_Rect{tlX, tlY, tlW, tlH}, SDL_Color{255, 255, 255, 60});
    float ratio = 0.0f;
    if (state_.duration > 0) {
        ratio = (float)(state_.position / state_.duration);
        ratio = std::clamp(ratio, 0.0f, 1.0f);
    }
    int fillW = (int)(tlW * ratio);
    blendFill(r, SDL_Rect{tlX, tlY, fillW, tlH}, theme::Accent);
    // Thumb (cercle) à la position courante.
    const int thumbR = 8;
    int thumbX = tlX + fillW;
    draw::fillCircle(r, thumbX, tlY + tlH / 2, thumbR, theme::Accent);

    // ── Ligne 3 : boutons ────────────────────────────────────────────────
    auto btns = visibleButtons();
    const int btnH   = 64;
    const int btnRow = zone.y + 160;

    auto sideOf = [](PlayerAction a) {
        switch (a) {
            case PlayerAction::Prev:
            case PlayerAction::SeekBack5m:
            case PlayerAction::SeekBack30:
            case PlayerAction::PlayPause:
            case PlayerAction::SeekFwd30:
            case PlayerAction::SeekFwd5m:
            case PlayerAction::Next:       return 0;
            default:                       return 1;
        }
    };
    auto widthOf = [&](PlayerAction a) -> int {
        switch (a) {
            case PlayerAction::OpenAudio:   return 120;
            case PlayerAction::OpenSub:     return 130;
            case PlayerAction::SeekBack5m:
            case PlayerAction::SeekBack30:
            case PlayerAction::SeekFwd30:
            case PlayerAction::SeekFwd5m:   return 82;
            default:                         return 72;
        }
    };

    int wLeft = 0, wRight = 0;
    const int gap = 12;
    std::vector<int> sides(btns.size(), 0);
    for (size_t i = 0; i < btns.size(); ++i) {
        sides[i] = sideOf(btns[i]);
        int w = widthOf(btns[i]);
        if (sides[i] == 0) wLeft  += w + (wLeft  ? gap : 0);
        else               wRight += w + (wRight ? gap : 0);
    }
    int leftStartX  = (int)(winW * 0.35f) - wLeft  / 2;
    int rightStartX = (int)(winW * 0.65f) - wRight / 2;

    auto drawBtn = [&](int x, PlayerAction a, bool focus, int w) {
        SDL_Rect rc{x, btnRow, w, btnH};
        // Look "néon bleu" inspiré des remotes TV : halo bleu derrière +
        // rectangle arrondi fond sombre + bordure accent claire.
        const int radius = 12;
        SDL_Color accent = theme::Accent;        // #4a9eff
        SDL_Color accentHi = {0x80, 0xc8, 0xff, 255};

        // 1. Halo diffus derrière le bouton (toujours présent, intensifié
        //    quand focusé — comme une LED plus brillante).
        SDL_Color haloColor = (a == PlayerAction::Close)
            ? SDL_Color{0xff, 0x71, 0x71, 255}
            : SDL_Color{0x4a, 0x9e, 0xff, 255};
        draw::glowHalo(r, rc, radius, haloColor, focus ? 16 : 8);

        // 2. Fond sombre arrondi, très opaque pour contraster avec le halo.
        SDL_Color bg = (a == PlayerAction::Close)
            ? SDL_Color{0x1a, 0x05, 0x0a, 225}
            : SDL_Color{0x05, 0x0a, 0x1c, 220};
        if (focus) bg = (a == PlayerAction::Close)
            ? SDL_Color{0x3a, 0x08, 0x14, 235}
            : SDL_Color{0x10, 0x1e, 0x3a, 235};
        draw::fillRoundedRect(r, rc, radius, bg);

        // 3. Bordure accent 3 px (plus épaisse quand focusé pour effet "pressé").
        SDL_Color border = (a == PlayerAction::Close)
            ? SDL_Color{0xff, 0x80, 0x80, 255}
            : (focus ? accentHi : accent);
        draw::strokeRoundedRect(r, rc, radius, focus ? 4 : 3, border);

        const char* label = "";
        std::string composed;
        switch (a) {
            // Glyphes limités à Latin-1 + Geometric Shapes (U+25xx) supportés
            // par le TTF embarqué ; les emoji (⏸ 🔊 ⏮ ⏭ ⏪ ⏩) tombaient en tofu.
            case PlayerAction::Prev:       label = "|\xC2\xAB"; break;       // |«
            case PlayerAction::Next:       label = "\xC2\xBB|"; break;       // »|
            case PlayerAction::SeekBack5m: label = "\xC2\xAB 5m"; break;     // « 5m
            case PlayerAction::SeekBack30: label = "\xC2\xAB 30s"; break;    // « 30s
            case PlayerAction::SeekFwd30:  label = "30s \xC2\xBB"; break;    // 30s »
            case PlayerAction::SeekFwd5m:  label = "5m \xC2\xBB"; break;     // 5m »
            case PlayerAction::PlayPause:
                label = state_.paused ? "\xE2\x96\xB6" : "| |"; break;       // ▶ / | |
            case PlayerAction::OpenAudio: {
                std::string code = (state_.activeAudioIdx >= 0 &&
                                    state_.activeAudioIdx < (int)state_.audioLabels.size())
                    ? state_.audioLabels[state_.activeAudioIdx] : std::string("");
                std::string shortLbl;
                for (size_t i = 0; i < code.size() && shortLbl.size() < 3; ++i) {
                    char c = code[i];
                    if (c == ' ' || c == '(' || c == '-') break;
                    shortLbl += (char)std::toupper((unsigned char)c);
                }
                if (shortLbl.empty()) shortLbl = "AUD";
                // "♫" (U+266B) absent du TTF embarqué → préfixe ASCII.
                composed = "Aud " + shortLbl;
                label = composed.c_str();
                break;
            }
            case PlayerAction::OpenSub: {
                if (state_.activeSubIdx < 0) {
                    composed = "CC OFF";
                } else if (state_.activeSubIdx < (int)state_.subLabels.size()) {
                    std::string code = state_.subLabels[state_.activeSubIdx];
                    std::string shortLbl;
                    for (size_t i = 0; i < code.size() && shortLbl.size() < 3; ++i) {
                        char c = code[i];
                        if (c == ' ' || c == '(' || c == '-') break;
                        shortLbl += (char)std::toupper((unsigned char)c);
                    }
                    if (shortLbl.empty()) shortLbl = "SUB";
                    composed = "CC " + shortLbl;
                }
                label = composed.c_str();
                break;
            }
            case PlayerAction::ToggleMute:
                // Icône dessinée (cf. plus bas) — pas de texte. Le placeholder
                // " " évite de centrer le texte (lw=0) ; le rendu réel est
                // intercepté plus bas avec une early-return après l'icône.
                label = " "; break;
            case PlayerAction::Close:
                label = "X"; break;   // X ASCII, ✕ (U+2715) absent du TTF
            default: label = "?"; break;
        }

        theme::FontStyle fs;
        switch (a) {
            case PlayerAction::OpenAudio:
            case PlayerAction::OpenSub:
            case PlayerAction::SeekBack5m:
            case PlayerAction::SeekBack30:
            case PlayerAction::SeekFwd30:
            case PlayerAction::SeekFwd5m: fs = theme::FontStyle::SmBold; break;
            default:                       fs = theme::FontStyle::LgBold; break;
        }
        // Cas spécial ToggleMute : pas de texte, on dessine une icône
        // haut-parleur (avec ou sans barre selon mute) en SDL primitives
        // — le TTF embarqué n'inclut pas les emoji 🔊 / 🔇.
        if (a == PlayerAction::ToggleMute) {
            SDL_Color iconCol = focus
                ? SDL_Color{255, 255, 255, 255}
                : SDL_Color{0xcc, 0xe4, 0xff, 255};
            const int cx = rc.x + rc.w / 2;
            const int cy = rc.y + rc.h / 2;
            // Base trapézoïdale du haut-parleur (fond + cône stylisé).
            // Coordonnées : centre logique en (0,0), span ±18 px horizontal.
            // Caisse rectangulaire à gauche.
            SDL_SetRenderDrawColor(r, iconCol.r, iconCol.g, iconCol.b, iconCol.a);
            SDL_Rect box{cx - 14, cy - 4, 6, 9};
            SDL_RenderFillRect(r, &box);
            // Cône (pavillon) : 4 lignes formant un trapèze plein.
            // Approche simple : SDL_RenderFillRect à plusieurs hauteurs.
            for (int dy = -10; dy <= 10; ++dy) {
                int span = 8 - std::abs(dy) * 6 / 10;
                if (span < 0) span = 0;
                SDL_RenderDrawLine(r, cx - 8, cy + dy,
                                      cx - 8 + span, cy + dy);
            }
            // Arcs de son (3 traits courbes courts) — uniquement si non muet.
            if (!state_.muted) {
                for (int k = 0; k < 3; ++k) {
                    int rad = 5 + k * 5;
                    // Petite portion d'arc à droite : on dessine 5 segments.
                    for (int t = -30; t <= 30; t += 6) {
                        float a0 = (float)t        * 3.14159f / 180.0f;
                        float a1 = (float)(t + 6)  * 3.14159f / 180.0f;
                        int x0 = cx + 4 + (int)(rad * std::cos(a0));
                        int y0 = cy     + (int)(rad * std::sin(a0));
                        int x1 = cx + 4 + (int)(rad * std::cos(a1));
                        int y1 = cy     + (int)(rad * std::sin(a1));
                        SDL_RenderDrawLine(r, x0, y0, x1, y1);
                    }
                }
            } else {
                // Barre oblique rouge ↘ pour indiquer mute.
                SDL_SetRenderDrawColor(r, 0xff, 0x60, 0x60, 255);
                for (int o = 0; o < 3; ++o) {
                    SDL_RenderDrawLine(r, cx - 16, cy - 12 + o,
                                          cx + 16, cy + 12 + o);
                }
            }
            return;  // skip text render
        }

        int lw = 0, lh = 0;
        text_.measure(fs, label, lw, lh);
        // Texte blanc pur si focus, bleu clair sinon — accentue la LED.
        SDL_Color txt = focus
            ? SDL_Color{255, 255, 255, 255}
            : SDL_Color{0xcc, 0xe4, 0xff, 255};
        text_.draw(fs, label,
                   rc.x + (rc.w - lw) / 2, rc.y + (rc.h - lh) / 2, txt);
    };

    int xL = leftStartX, xR = rightStartX;
    for (size_t i = 0; i < btns.size(); ++i) {
        int w = widthOf(btns[i]);
        bool focus = state_.btnMode && (int)i == state_.btnFocusIdx;
        if (sides[i] == 0) { drawBtn(xL, btns[i], focus, w); xL += w + gap; }
        else               { drawBtn(xR, btns[i], focus, w); xR += w + gap; }
    }

    // Bandeau d'aide retiré (demande utilisateur 2026-04-24) : le rappel
    // keymap en petite police bas d'écran ajoutait du bruit visuel. Les
    // boutons sont déjà étiquetés et le mode BTNMODE se voit au focus.
}

void PlayerOSD::renderAudioMenu(SDL_Renderer* r, int winW, int winH) {
    (void)winW;
    const int panelW = 480;
    int itemCount = std::max<int>(1, (int)state_.audioLabels.size());
    int panelH = 72 + itemCount * 52 + 48;
    SDL_Rect panel{60, 80, panelW, panelH};
    blendFill(r, panel, SDL_Color{10, 10, 18, 225});
    blendStroke2(r, panel, theme::Accent);

    text_.draw(theme::FontStyle::LgBold, "Piste audio",
               panel.x + 24, panel.y + 18, theme::TextPrimary);

    for (int i = 0; i < itemCount; ++i) {
        SDL_Rect row{panel.x + 16, panel.y + 72 + i * 52, panel.w - 32, 44};
        bool focus  = (i == state_.audioMenuIdx);
        bool active = (i == state_.activeAudioIdx);
        if (focus) {
            blendFill(r, row, SDL_Color{0x4a, 0x9e, 0xff, 170});
            blendStroke2(r, row, theme::Accent);
        }
        const std::string& lbl = (i < (int)state_.audioLabels.size())
            ? state_.audioLabels[i] : std::string("(vide)");
        std::string full = (active ? "\xE2\x96\xB6 " : "   ") + lbl;
        text_.draw(theme::FontStyle::MdBold, full,
                   row.x + 14,
                   row.y + (row.h - text_.lineHeight(theme::FontStyle::MdBold)) / 2,
                   theme::TextPrimary);
    }

    text_.draw(theme::FontStyle::XsRegular,
               "\xE2\x86\x91\xE2\x86\x93  \xC2\xB7  OK  \xC2\xB7  BLEU/BACK ferme",
               panel.x + 24, panel.y + panel.h - 28, theme::TextSecondary);
    (void)winH;
}

void PlayerOSD::renderSubMenu(SDL_Renderer* r, int winW, int winH) {
    const int panelW = 480;
    int itemCount = 1 + (int)state_.subLabels.size();
    int panelH = 72 + itemCount * 52 + 48;
    SDL_Rect panel{winW - panelW - 60, 80, panelW, panelH};
    blendFill(r, panel, SDL_Color{10, 10, 18, 225});
    blendStroke2(r, panel, SDL_Color{0xf8, 0x71, 0x71, 255});

    text_.draw(theme::FontStyle::LgBold, "Sous-titres",
               panel.x + 24, panel.y + 18, theme::TextPrimary);

    auto drawRow = [&](int visualIdx, int realIdx, const std::string& lbl) {
        SDL_Rect row{panel.x + 16, panel.y + 72 + visualIdx * 52,
                     panel.w - 32, 44};
        bool focus  = (state_.subMenuIdx == realIdx);
        bool active = (state_.activeSubIdx == realIdx);
        if (focus) {
            blendFill(r, row, SDL_Color{0x4a, 0x9e, 0xff, 170});
            blendStroke2(r, row, theme::Accent);
        }
        std::string full = (active ? "\xE2\x96\xB6 " : "   ") + lbl;
        text_.draw(theme::FontStyle::MdBold, full,
                   row.x + 14,
                   row.y + (row.h - text_.lineHeight(theme::FontStyle::MdBold)) / 2,
                   theme::TextPrimary);
    };
    drawRow(0, -1, "Désactivés");
    for (int i = 0; i < (int)state_.subLabels.size(); ++i) {
        drawRow(i + 1, i, state_.subLabels[i]);
    }

    text_.draw(theme::FontStyle::XsRegular,
               "\xE2\x86\x91\xE2\x86\x93  \xC2\xB7  OK  \xC2\xB7  ROUGE/BACK ferme",
               panel.x + 24, panel.y + panel.h - 28, theme::TextSecondary);
    (void)winH;
}

}  // namespace iptv::ui

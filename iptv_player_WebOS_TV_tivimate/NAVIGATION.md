# Navigation télécommande — Carte complète

> Touches : `↑ ↓ ← →` `OK` `BACK` `←/→ = LEFT/RIGHT`  
> Pour modifier un comportement : chercher le fichier indiqué, la zone de focus, et la touche correspondante.

---

## 1. SettingsScreen `src/screens/SettingsScreen.jsx`

### Layout

```
┌──────────────────────────────────────────────────────┐
│  [0] URL du serveur                                  │
│  [1] Nom d'utilisateur                               │
│  [2] Mot de passe                                    │
├──────────────────────────────────────────────────────┤
│  [3] Tester la connexion   [4] Enregistrer           │
├──────────────────────────────────────────────────────┤
│  Zone langues (visible si connexion OK)              │
│    [FR] [IT] [DE] [EN] [ES]   ← inLangArea          │
│    [Tout]  [Continuer →]      ← inLangActions        │
├──────────────────────────────────────────────────────┤
│  [5] Rechercher USB   [6] Chemin M3U   [7] Charger  │
└──────────────────────────────────────────────────────┘
```

### Navigation verticale principale (fieldOrder)

| Depuis idx | ↑ | ↓ | ← | → |
|---|---|---|---|---|
| 0 URL | — (reste) | 1 Username | — | — |
| 1 Username | 0 URL | 2 Password | — | — |
| 2 Password | 1 Username | 3 Tester | — | — |
| 3 Tester | **Continuer** (si picker visible) sinon 2 Password | 4 Enregistrer **ou** zone langues (si picker) | — | 4 Enregistrer |
| 4 Enregistrer | 3 Tester | 5 Scan USB | 3 Tester | — |
| 5 Scan USB | 4 Enregistrer | 6 Chemin | — | 7 Charger |
| 6 Chemin | 5 Scan | 7 Charger | — | — |
| 7 Charger | 6 Chemin | — (reste) | 5 Scan | — |

### Zone langues — `inLangArea` (ligne FR/IT/DE/EN/ES)

| Touche | Action |
|---|---|
| ← | Focus lang précédente (min 0) |
| → | Focus lang suivante (max 4) |
| OK | Toggle la langue (add/remove) |
| ↑ | → idx 3 Tester la connexion |
| ↓ | → inLangActions (toutRef) |
| BACK | Retour accueil (si configuré) |

### Zone langues — `inLangActions` (ligne Tout / Continuer)

| Touche | Action |
|---|---|
| ← | Focus Tout (idx 0) |
| → | Focus Continuer (idx 1) — seulement si langue sélectionnée |
| OK | Exécute Tout ou Continuer |
| ↑ | → inLangArea (dernière lang focalisée) |
| ↓ | → idx 4 Enregistrer |
| BACK | Retour accueil (si configuré) |

---

## 2. CatalogFilterScreen `src/screens/CatalogFilterScreen.jsx`

### Layout

```
┌───────────────────────────────────────────────────────────┐
│  [Films (x/y)]  [Séries (x/y)]        Page N / M        │  ← zone 'tabs'
├───────────────────────────────────────────────────────────┤
│  ☑ Catégorie 1   ☑ Catégorie 2   ☐ Catégorie 3          │
│  ☑ Catégorie 4   ☐ Catégorie 5   ☑ Catégorie 6          │
│  ...  (3 colonnes × 10 lignes = 30 par page)             │  ← zone 'cats'
│                                                           │
├───────────────────────────────────────────────────────────┤
│              [Tout sélectionner] [Tout désélect.] [OK]   │  ← zone 'ctrl'
└───────────────────────────────────────────────────────────┘
```

### Zone `tabs`

| Touche | Action |
|---|---|
| ← | Films (si pas déjà actif) |
| → | Séries (si pas déjà actif) |
| ↓ | → zone cats, focus catégorie [0] |
| OK | Click l'onglet |

### Zone `cats` — grille 3 colonnes, PAGE_SIZE = 30

| Touche | Action |
|---|---|
| ↑ | Ligne précédente (même colonne) — si première ligne & page > 0 : page précédente, même colonne, dernière ligne — si première ligne & page 0 : → zone tabs |
| ↓ | Ligne suivante (même colonne) — si dernière ligne & page suivante existe : page suivante, même colonne — si dernière ligne & dernière page : → zone ctrl |
| ← | Colonne précédente (si col > 0) |
| → | Colonne suivante (si col < 2 et item existe) |
| OK | Cocher / Décocher la catégorie |

### Zone `ctrl` — 3 boutons : [0] Tout sel. [1] Tout désel. [2] OK

| Touche | Action |
|---|---|
| ↑ | Si btn > 0 : btn précédent — si btn 0 : → zone cats, dernière catégorie |
| ↓ | Bouton suivant (max 2) |
| ← | Bouton précédent |
| → | Bouton suivant |
| OK | Exécute le bouton (Tout sel. / Tout désel. / Valider) |

---

## 3. HomeScreen `src/screens/HomeScreen.jsx`

### Layout

```
┌──────────┬────────────────────────────────────────────┐
│          │  [🔍 Recherche]  [🔄 Sync]  [⚙ Paramètres] │  Toolbar
│ SIDEBAR  ├────────────────────────────────────────────┤
│ (overlay)│  [🎬 Films]  [📺 Séries]  [⭐ Favoris]     │  TabBar
│          ├────────────────────────────────────────────┤
│ ← ferme  │  [▶ Reprendre S02E05]  (si série en cours) │  Resume
│ avec ←   ├────────────────────────────────────────────┤
│ ou BACK  │  [Tri A-Z] [⭐] [📅]                       │  Header tri
│          ├────────────────────────────────────────────┤
│          │  [Card] [Card] [Card]                       │
│          │  [Card] [Card] [Card]  ...                  │  ContentGrid
└──────────┴────────────────────────────────────────────┘
```

### Transitions entre zones

| De | Touche | Vers |
|---|---|---|
| Sidebar | → ou BACK | Ferme sidebar + focus première carte |
| Toolbar idx 0 | ← | Ouvre Sidebar |
| Toolbar | ↓ | TabBar |
| TabBar | ↑ | Toolbar |
| TabBar | ↓ | Resume (si présent) sinon ContentGrid header |
| TabBar | ← (onglet 0) | Ouvre Sidebar |
| Resume | ↑ | TabBar |
| Resume | ↓ | ContentGrid première carte |
| ContentGrid header | ↑ | TabBar |
| ContentGrid header | ↓ | ContentGrid carrousel |
| ContentGrid carrousel | ↑ | ContentGrid header |
| ContentGrid carrousel | ← (col 0) | Ouvre Sidebar |
| ContentGrid carrousel | OK | Fiche série ou Lecteur |

---

## 4. Toolbar `src/components/home/Toolbar.jsx`

### Layout

```
[🔍 Recherche…]  ──────────────  [🔄 Synchroniser]  [⚙ Paramètres]
   idx 0                               idx 1              idx 2
```

### Mode bouton (searchOpen = false)

| Touche | Action |
|---|---|
| ← @ idx 0 | → Sidebar (`onFocusLeft`) |
| ← @ idx > 0 | Bouton précédent |
| → | Bouton suivant (max idx 2) |
| ↓ | → TabBar (`onFocusDown`) |
| OK | Click le bouton |

### Mode recherche (searchOpen = true)

| Touche | Action |
|---|---|
| OK | Ferme l'input, applique la recherche |
| BACK | Ferme l'input, applique la recherche |
| ⌫ Backspace | Efface le dernier caractère |
| ← / → | Déplace le curseur dans le texte |
| ↑ | Ferme l'input |
| ↓ | Ferme l'input + → TabBar |

---

## 5. Sidebar `src/components/home/Sidebar.jsx`

### Layout

```
┌────────────────────┐
│  [🎬 Films    ]    │  ← zone tabs
│  [📺 Séries   ]    │
│  [⭐ Favoris  ]    │
├────────────────────┤
│  Toutes            │  ← zone cats
│  Action            │
│  Comédie           │
│  ...               │
├────────────────────┤
│  [⚙ Paramètres]   │  ← zone settings
└────────────────────┘
```

### Zone `tabs` (3 onglets verticaux)

| Touche | Action |
|---|---|
| ↑ | Onglet précédent (min 0) |
| ↓ | Onglet suivant — si dernier : → zone cats idx 0 |
| → | Ferme Sidebar + focus grille (`onFocusRight`) |
| OK | Sélectionne l'onglet |

### Zone `cats`

| Touche | Action |
|---|---|
| ↑ | Catégorie précédente — si idx 0 : → zone tabs |
| ↓ | Catégorie suivante — si dernière : → zone settings |
| → | Ferme Sidebar + focus grille |
| OK | Filtre par cette catégorie |

### Zone `settings`

| Touche | Action |
|---|---|
| ↑ | → zone cats, dernière catégorie |
| → | Ferme Sidebar + focus grille |
| OK | Ouvre SettingsScreen |

---

## 6. SeriesDetailScreen `src/screens/SeriesDetailScreen.jsx`

### Layout

```
┌─────────────────────────┬─────────────────────┐
│  Affiche + Titre        │  [S1] [S2] [S3]     │  ← panel seasons
│  Année · Durée · Note   │  ─────────────────  │
│                         │  Ep 1 — Titre        │
│  [← Retour]             │  Ep 2 — Titre        │  ← panel episodes
│  [☆ Favoris]            │  Ep 3 — Titre        │
│  [▶ Lire]               │  ...                 │
│  ← panel left           │                      │
└─────────────────────────┴─────────────────────┘
```

### Panel `left` — 3 boutons : [0] Retour [1] Favoris [2] Lire

| Touche | Action |
|---|---|
| ← | Bouton précédent (min 0) |
| → | Bouton suivant — si btn 2 (Lire) : → panel seasons |
| ↓ | → panel seasons |
| OK | Click le bouton |
| BACK | Navigate('/') |

### Panel `seasons`

| Touche | Action |
|---|---|
| ↑ | Saison précédente — si idx 0 : → panel left, btn 0 |
| ↓ | Saison suivante (max seasons.length - 1) |
| ← | → panel left, btn 0 |
| → | → panel episodes |
| OK | Sélectionne la saison (charge les épisodes) |
| BACK | Navigate('/') |

### Panel `episodes`

| Touche | Action |
|---|---|
| ↑ | Épisode précédent — si idx 0 : → panel left, btn 2 (Lire) |
| ↓ | Épisode suivant (max episodes.length - 1) |
| ← | → panel seasons |
| OK | Lance la lecture de l'épisode |
| BACK | Navigate('/') |

> **Note :** Si une seule saison → démarrage direct sur panel `episodes`.  
> Au démarrage : focus automatique sur le premier épisode non regardé.

---

## 7. ContentGrid — Tri `src/components/home/ContentGrid.jsx`

### Header (boutons de tri)

```
[A-Z]  [⭐ Score]  [📅 Date]
 idx 0    idx 1      idx 2
```

| Touche | Action |
|---|---|
| ← @ idx 0 | → Sidebar |
| ← @ idx > 0 | Bouton précédent |
| → | Bouton suivant (max 2) |
| ↑ | → TabBar |
| ↓ | → Carrousel carte [0] |
| OK | Toggle tri : desc → asc → désactivé |

### Carrousel (cartes)

| Touche | Action |
|---|---|
| ← @ col 0 | → Sidebar |
| ← | Carte précédente |
| → | Carte suivante (charge automatiquement si proche de la fin) |
| ↑ | → Header tri |
| ↓ | Toggle favori (si disponible) |
| OK | Ouvre fiche série ou lance le lecteur |

---

## Flux inter-écrans

```
/settings ──→ [Connexion OK + langues] ──→ /catalog-filter ──→ /
    ↑                                                            │
    └─────────────── Bouton ⚙ Paramètres ───────────────────────┘
    
/ (HomeScreen) ──→ [OK sur carte film]  ──→ /player
              ──→ [OK sur carte série]  ──→ /series/:id ──→ [▶ Lire] ──→ /player
              
/player ──→ [BACK] ──→ retour précédent
```

---

## Légende touches télécommande

| Code | Touche physique |
|---|---|
| KEY.OK (13) | Touche OK / Entrée |
| KEY.LEFT (37) | Flèche gauche |
| KEY.UP (38) | Flèche haut |
| KEY.RIGHT (39) | Flèche droite |
| KEY.DOWN (40) | Flèche bas |
| BACK (461) | Touche Retour LG |
| KEY.PLAY_PAUSE | Touche lecture/pause |
| KEY.RED/GREEN/YELLOW/BLUE | Touches couleur |

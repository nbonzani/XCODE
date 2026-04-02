# ARCHITECTURE — IPTV Player webOS v2.0

> Document de référence technique — Généré le 2026-03-29
> Base : ANALYSE_FONCTIONNELLE.md + SELECTION_FONCTIONNALITES.md + décisions architecturales arrêtées

---

## Section 1 — Résumé du projet

| Champ | Valeur |
|-------|--------|
| **Nom de l'application** | IPTV Player |
| **ID webOS** | `com.iptv.player` |
| **Version** | 2.0.0 |
| **Technologie** | React 18 + Vite 5 |
| **TV cible** | LG OLED C1 (webOS 6.x) |
| **Chromium embarqué** | 87 |
| **Protocole exécution** | `file://` (pas de serveur HTTP) |
| **Routage** | HashRouter (`file://…/index.html#/route`) |
| **Persistance catalogue** | IndexedDB via bibliothèque `idb` |
| **Persistance config** | localStorage |
| **Lecture vidéo** | `<video>` HTML5 natif (MP4/H.264) + HLS.js si URL `.m3u8` |
| **Navigation** | @noriginmedia/spatial-navigation |
| **Clavier virtuel** | Composant React custom (AZERTY, 6 occurrences) |
| **Transpilation** | Babel plugins `@babel/plugin-transform-*` pour Chromium 87 |
| **Source Python portée** | `iptv_player_PC` (~7 000 lignes, PyQt6) |

---

## Section 2 — Arbre de composants complet

```
App
├── HashRouter
│   └── NavigationProvider  (contexte zone active + dispatch keydown global)
│       ├── Layout           (structure globale : Toolbar + <main> + StatusBar)
│       │   ├── Toolbar      (bouton Réglages + titre app — ZONE: TOOLBAR)
│       │   └── StatusBar    (messages sync, erreurs, état connexion)
│       │
│       ├── Routes
│       │   ├── Route path="/"
│       │   │   └── HomePage        (onglets Films / Séries)
│       │   │       ├── TabBar      (Films | Séries — ZONE: TAB_BAR)
│       │   │       ├── MoviesTab   (onglet Films — conditionnel)
│       │   │       │   ├── FilterBar          (ZONE: FILTER_BAR_MOVIES)
│       │   │       │   │   ├── SearchButton   (bouton → VirtualKeyboardModal)
│       │   │       │   │   ├── FilterSelect   (catégorie)
│       │   │       │   └── ContentGrid        (ZONE: GRID_MOVIES)
│       │   │       │       └── ContentCard × N  (vignette poster + titre + rating)
│       │   │       └── SeriesTab  (onglet Séries — conditionnel)
│       │   │           ├── FilterBar          (ZONE: FILTER_BAR_SERIES)
│       │   │           │   ├── SearchButton   (bouton → VirtualKeyboardModal)
│       │   │           │   ├── FilterSelect   (catégorie)
│       │   │           └── ContentGrid        (ZONE: GRID_SERIES)
│       │   │               └── ContentCard × N
│       │   │
│       │   └── Route path="/player"
│       │       └── PlayerPage          (plein écran, gestion playlist)
│       │           └── VideoPlayer     (ZONE: PLAYER)
│       │               ├── <video>     (élément HTML5 natif + HLS.js si .m3u8)
│       │               └── PlayerControls  (ZONE: PLAYER_CONTROLS — auto-masqué)
│       │                   ├── ProgressBar   (scrubber + temps courant / durée)
│       │                   ├── PlayPauseBtn
│       │                   ├── StopBtn
│       │                   ├── SeekBack30    (-30s)
│       │                   ├── SeekForward30 (+30s)
│       │                   ├── MuteBtn
│       │                   ├── VolumeSlider
│       │                   └── TitleLabel
│       │
│       └── Modals (portals — superposés à la route active)
│           ├── SettingsModal    (ZONE: SETTINGS_MODAL — isFocusBoundary)
│           │   ├── TextInput × 4  (URL, Port, Username, Password → VirtualKeyboardModal)
│           │   ├── TestConnectionBtn
│           │   ├── ToggleFrench   (filtre langue par défaut)
│           │   ├── SaveBtn
│           │   └── CancelBtn
│           ├── SeriesModal      (ZONE: SERIES_MODAL — isFocusBoundary)
│           │   ├── CoverImage
│           │   ├── SeriesMetadata (titre, genre, note, plot)
│           │   ├── SeasonSelector (onglets saisons)
│           │   ├── EpisodeList    (liste épisodes avec ✅ vus)
│           │   ├── PlayEpisodeBtn
│           │   ├── PlaySeasonBtn  (playlist complète)
│           │   └── LoadingSpinner (pendant fetch async)
│           └── VirtualKeyboardModal  (ZONE: VIRTUAL_KEYBOARD — isFocusBoundary)
│               ├── DisplayField   (texte en cours de saisie)
│               ├── KeyboardGrid   (AZERTY 3 rangées — navigable télécommande)
│               │   └── KeyButton × N  (lettres + ⌫ + Espace + OK)
│               └── CancelBtn
│
└── Hooks globaux (non-UI)
    ├── useRemoteNavigation   (listener keydown, routing zones, BACK global)
    ├── useSync               (orchestration fetch API Xtream → IndexedDB)
    ├── useMovies             (chargement + filtrage films depuis IndexedDB)
    ├── useSeries             (chargement + filtrage séries depuis IndexedDB)
    ├── usePlayer             (état lecteur, init HLS.js, gestion playlist)
    └── useVirtualKeyboard    (état saisie, curseur grille, callbacks submit)
```

---

## Section 3 — Zones de navigation télécommande

| Zone | Description | UP | DOWN | LEFT | RIGHT | OK | BACK |
|------|-------------|----|----|------|-------|----|------|
| `TOOLBAR` | Barre supérieure (bouton Réglages) | — bloqué | `TAB_BAR` | — bloqué | — bloqué | Ouvre SettingsModal | Quitter l'app *(confirm dialog)* |
| `TAB_BAR` | Onglets Films / Séries | `TOOLBAR` | `FILTER_BAR_*` (onglet actif) | Onglet précédent | Onglet suivant | Activer l'onglet | `TOOLBAR` |
| `FILTER_BAR_MOVIES` | Filtres onglet Films | `TAB_BAR` | `GRID_MOVIES` | Filtre précédent | Filtre suivant | Ouvrir VirtualKeyboard ou toggle | `TAB_BAR` |
| `FILTER_BAR_SERIES` | Filtres onglet Séries | `TAB_BAR` | `GRID_SERIES` | Filtre précédent | Filtre suivant | Ouvrir VirtualKeyboard ou toggle | `TAB_BAR` |
| `GRID_MOVIES` | Grille vignettes Films | `FILTER_BAR_MOVIES` (1ère ligne) — interne sinon | Interne (ligne suivante) | Interne (carte précédente) | Interne (carte suivante) | Ouvre SeriesModal ou lecture film | `FILTER_BAR_MOVIES` |
| `GRID_SERIES` | Grille vignettes Séries | `FILTER_BAR_SERIES` (1ère ligne) — interne sinon | Interne (ligne suivante) | Interne | Interne | Ouvre SeriesModal | `FILTER_BAR_SERIES` |
| `SETTINGS_MODAL` | Modal configuration serveur | Interne | Interne | Interne | Interne | Valider champ / action bouton | Fermer modal → focus retourne `TOOLBAR` |
| `SERIES_MODAL` | Modal saisons/épisodes | Interne | Interne | Interne (saison précédente) | Interne (saison suivante) | Lancer lecture | Fermer modal → focus retourne ContentCard |
| `VIRTUAL_KEYBOARD` | Clavier AZERTY custom | Rangée précédente | Rangée suivante | Touche précédente | Touche suivante | Appuyer la touche | Annuler saisie → focus retourne élément origine |
| `PLAYER` | Lecteur vidéo plein écran | Affiche `PLAYER_CONTROLS` | — | — | — | Affiche `PLAYER_CONTROLS` | Arrête + quitte → `navigate(-1)` |
| `PLAYER_CONTROLS` | Barre de contrôles (auto-masqué 3s) | Masquer les contrôles | — | Bouton précédent | Bouton suivant | Actionner le bouton | Arrête + quitte → `navigate(-1)` |

> **Règle `isFocusBoundary`** : appliqué **uniquement** à `SETTINGS_MODAL`, `SERIES_MODAL`, `VIRTUAL_KEYBOARD`. Jamais sur les zones de contenu.

> **Scroll automatique** : `scrollIntoView({ behavior:'smooth', block:'nearest' })` sur chaque ContentCard recevant le focus (grilles pouvant dépasser l'écran).

---

## Section 4 — Routes HashRouter

| Route | Composant | Description | Paramètres |
|-------|-----------|-------------|------------|
| `#/` | `HomePage` | Écran principal avec onglets Films et Séries. Zone d'entrée par défaut. | — |
| `#/player` | `PlayerPage` | Lecteur vidéo plein écran. Reçoit les données via `location.state`. | `state: { url, title, type: 'movie'\|'episode'\|'season', playlist?: [{url,title}] }` |

> Deux routes suffisent. Les modaux (Settings, Series, VirtualKeyboard) ne sont pas des routes — ce sont des overlays gérés par état React (`useState` booléen) sur la HomePage.

---

## Section 5 — Schéma des données IndexedDB

**Nom de la base :** `iptv-player-db`  **Version :** `1`

### Store : `movies`

| Champ | Type | Description |
|-------|------|-------------|
| `stream_id` *(keyPath)* | number | Clé primaire — ID Xtream |
| `name` | string | Titre du film |
| `category_id` | string | ID catégorie parente |
| `category_name` | string | Nom de la catégorie |
| `stream_icon` | string | URL poster distant |
| `container_extension` | string | `mkv` ou `mp4` |
| `rating` | number | Note (0.0 – 10.0) |
| `added` | number | Unix timestamp d'ajout |
| `genre` | string | Genre(s) séparés par virgule |
| `release_date` | string | Année de sortie |
| `plot` | string | Synopsis |
| `is_french` | number | `1` si contenu français, `0` sinon |
| `cached_at` | number | Timestamp de la dernière mise en cache |

**Index :**
| Nom index | Champ(s) | Unique |
|-----------|----------|--------|
| `by_category` | `category_id` | non |
| `by_french` | `is_french` | non |
| `by_name` | `name` | non |

**Exemple d'enregistrement :**
```json
{
  "stream_id": 14782,
  "name": "Dune : Deuxième Partie",
  "category_id": "42",
  "category_name": "FR | FILMS RÉCENTS",
  "stream_icon": "http://server:8080/images/14782.jpg",
  "container_extension": "mkv",
  "rating": 8.5,
  "added": 1709251200,
  "genre": "Science-Fiction, Aventure",
  "release_date": "2024",
  "plot": "Paul Atréides s'unit aux Fremen...",
  "is_french": 1,
  "cached_at": 1711699200
}
```

---

### Store : `series`

| Champ | Type | Description |
|-------|------|-------------|
| `series_id` *(keyPath)* | number | Clé primaire — ID Xtream |
| `name` | string | Titre de la série |
| `category_id` | string | ID catégorie parente |
| `category_name` | string | Nom de la catégorie |
| `cover` | string | URL affiche distante |
| `rating` | number | Note (0.0 – 10.0) |
| `genre` | string | Genre(s) |
| `release_date` | string | Année de début |
| `plot` | string | Synopsis |
| `is_french` | number | `1` si contenu français |
| `cached_at` | number | Timestamp mise en cache |

**Index :**
| Nom index | Champ(s) | Unique |
|-----------|----------|--------|
| `by_category` | `category_id` | non |
| `by_french` | `is_french` | non |
| `by_name` | `name` | non |

---

### Store : `vod_categories`

| Champ | Type | Description |
|-------|------|-------------|
| `category_id` *(keyPath)* | string | Clé primaire |
| `category_name` | string | Libellé affiché |
| `parent_id` | string | ID parent (`"0"` si racine) |
| `is_french` | number | `1` si catégorie française |

**Index :** `by_french` sur `is_french`

---

### Store : `series_categories`

Structure identique à `vod_categories`.

---

### Store : `watched_episodes`

| Champ | Type | Description |
|-------|------|-------------|
| `episode_id` *(keyPath)* | number | Clé primaire — ID épisode Xtream |
| `series_id` | number | ID de la série parente |
| `watched_at` | number | Timestamp de visionnage |

**Index :**
| Nom index | Champ(s) | Unique |
|-----------|----------|--------|
| `by_series` | `series_id` | non |

**Exemple :**
```json
{ "episode_id": 885421, "series_id": 1247, "watched_at": 1711699200000 }
```

---

### Store : `sync_meta`

| Champ | Type | Description |
|-------|------|-------------|
| `key` *(keyPath)* | string | Clé de métadonnée |
| `value` | number | Valeur (timestamp ms) |

**Enregistrements utilisés :**

| key | value | Description |
|-----|-------|-------------|
| `"last_sync"` | Timestamp ms | Date de la dernière synchronisation complète |

**Logique de décision sync :**
`Date.now() - last_sync > 30 * 24 * 60 * 60 * 1000` → déclencher sync

---

## Section 6 — localStorage

| Clé | Type | Valeur par défaut | Description |
|-----|------|-------------------|-------------|
| `iptv_server_url` | string | `""` | URL de base du serveur Xtream (ex: `http://srv.example.com`) |
| `iptv_port` | string | `"8080"` | Port du serveur |
| `iptv_username` | string | `""` | Identifiant Xtream |
| `iptv_password` | string | `""` | Mot de passe Xtream |
| `iptv_language_filter` | string | `"french"` | Filtre langue : `"french"` ou `"all"` |
| `iptv_last_config_test` | string | `""` | Timestamp ISO du dernier test de connexion réussi |

> **Détection premier lancement :** `localStorage.getItem('iptv_server_url') === null || === ''`
> **Sécurité :** les credentials sont stockés en clair dans localStorage (périmètre accepté — app locale non distribuée publiquement).

---

## Section 7 — Flux de données principaux

### Flux 1 — Premier lancement (config → auth → sync → affichage)

```
App.useEffect (mount)
│
├─ storage.getConfig() ──► server_url vide ?
│                           │
│                      YES ─┤
│                           └─► setSettingsOpen(true)
│                               SettingsModal affiché
│                               ZONE: SETTINGS_MODAL (isFocusBoundary)
│                               │
│                               ├─ 4 × TextInput → VirtualKeyboardModal
│                               │   (URL, Port, Username, Password)
│                               │
│                               ├─ "Tester connexion"
│                               │   └─► fetch(`{url}:{port}/player_api.php
│                               │         ?username=X&password=X`)
│                               │        ├─ KO → StatusBar: "Erreur connexion"
│                               │        └─ OK → storage.saveConfig(...)
│                               │
│                               └─ "Enregistrer"
│                                   └─► setSettingsOpen(false)
│                                       triggerSync()
│
└─ server_url présent ─┐
                       └─► db.getSyncMeta('last_sync')
                            │
                            ├─ absent ou age > 30j ──► triggerSync()
                            └─ récent ──────────────► loadFromDB()

triggerSync():
┌──────────────────────────────────────────────────────────────────┐
│ setSyncState({ running:true, step:1/4, msg:'Catégories films…'}) │
│ fetch getVodCategories → db.vod_categories.putAll()              │
│ setSyncState({ step:2/4, msg:'Films…' })                         │
│ fetch getVodStreams (toutes catégories) → db.movies.putAll()      │
│ setSyncState({ step:3/4, msg:'Catégories séries…' })             │
│ fetch getSeriesCategories → db.series_categories.putAll()        │
│ setSyncState({ step:4/4, msg:'Séries…' })                        │
│ fetch getSeries → db.series.putAll()                             │
│ db.sync_meta.put({ key:'last_sync', value: Date.now() })         │
│ setSyncState({ running:false })                                   │
│ loadFromDB()                                                      │
└──────────────────────────────────────────────────────────────────┘

loadFromDB():
└─► db.searchMovies(filters) → setMovies([...]) → ContentGrid render
    db.searchSeries(filters) → setSeries([...]) → ContentGrid render
```

---

### Flux 2 — Lecture d'un film (sélection → player → fin)

```
ContentCard reçoit OK (keyCode 13)
│
└─► buildStreamUrl(movie):
    url = `{server_url}:{port}/movie/{username}/{password}/{stream_id}.{ext}`
    navigate('/player', { state: { url, title, type:'movie' } })

PlayerPage mount:
│
├─ videoRef.current ← <video> élément HTML5
├─ url.endsWith('.m3u8') ?
│   ├─ OUI → Hls.isSupported() ?
│   │          ├─ OUI → new Hls({ maxBufferLength:30 })
│   │          │         hls.loadSource(url)
│   │          │         hls.attachMedia(videoRef.current)
│   │          └─ NON → videoRef.current.src = url (HLS natif webOS 6)
│   └─ NON → videoRef.current.src = url (MP4 direct)
│
├─ videoRef.current.play()
└─ startHideTimer(3000ms) → setControlsVisible(false)

Pendant la lecture:
┌─ timeupdate event ──────────► setCurrentTime / setDuration
├─ PLAY (415) / PAUSE (19) ───► video.paused ? play() : pause()
├─ PLAY_PAUSE (10252) ────────► idem
├─ FF (417) ──────────────────► video.currentTime += 30
├─ RW (412) ──────────────────► video.currentTime -= 30
├─ STOP (413) ────────────────► video.pause() → navigate(-1)
├─ OK (13) / directionnel ────► setControlsVisible(true)
│                                resetHideTimer(3000ms)
│                                → auto-masquage si inactivité
└─ BACK (461) ────────────────► e.preventDefault()
                                 video.pause()
                                 hls?.destroy()
                                 navigate(-1)

video.ended:
└─► navigate(-1) → retour HomePage (focus restauré sur dernière ContentCard)
```

---

### Flux 3 — Lecture d'une série (sélection → dialogue saisons → épisode → playlist)

```
ContentCard série reçoit OK (keyCode 13)
│
└─► setSeriesModalOpen(true)
    SeriesModal mount — ZONE: SERIES_MODAL (isFocusBoundary)
    focusSelf() → focus piégé dans la modale
    │
    ├─ fetch getSeriesInfo(series_id)
    │   └─► setSeasonsData({ seasons, episodes })
    │       setLoadingInfo(false)
    │
    ├─ db.watched_episodes.getAllBySeries(series_id)
    │   └─► watchedSet = new Set([episode_id, ...])
    │
    └─ populateEpisodeList():
        Pour chaque épisode → { title, episode_num, watched: watchedSet.has(id) }
        auto-focus → premier épisode où watched === false

─────────────────────────────────────────────────────
CAS A — Lecture épisode unique
─────────────────────────────────────────────────────
Episode sélectionné (OK):
│
├─ db.watched_episodes.put({ episode_id, series_id, watched_at: Date.now() })
├─ url = `{base}/series/{u}/{p}/{stream_id}.{ext}`
├─ setSeriesModalOpen(false)
│   └─► focus retourne sur ContentCard série
└─► navigate('/player', { state: { url, title, type:'episode' } })
    PlayerPage → lecture simple (cf. Flux 2)

─────────────────────────────────────────────────────
CAS B — Lecture saison complète (playlist)
─────────────────────────────────────────────────────
Bouton "Lire la saison" (OK):
│
├─ playlist = season.episodes.map(ep → ({
│    url: buildEpisodeUrl(ep),
│    title: `${seriesName} S${season}E${ep.episode_num} - ${ep.title}`
│  }))
├─ setSeriesModalOpen(false)
└─► navigate('/player', { state: { playlist, type:'season' } })

PlayerPage (mode playlist):
│
├─ playlistIndex = 0
├─ video.src = playlist[0].url → play()
│
└─ video.ended:
    ├─ playlistIndex < playlist.length - 1 ?
    │   └─ OUI → playlistIndex++
    │             db.watched_episodes.put(currentEpisode)
    │             video.src = playlist[playlistIndex].url
    │             video.play()
    └─ NON (dernier épisode) → navigate(-1)

─────────────────────────────────────────────────────
BACK dans SeriesModal (à tout moment)
─────────────────────────────────────────────────────
BACK (461):
└─► e.preventDefault()
    setSeriesModalOpen(false)
    focus retourne sur ContentCard série d'origine
    (setFocus(previousFocusKey) via spatial-navigation)
```

---

## Section 8 — Keycodes télécommande LG utilisés

| Nom touche | keyCode | Action dans l'app |
|-----------|---------|-------------------|
| `VK_UP` | 38 | Navigation ↑ entre zones et éléments |
| `VK_DOWN` | 40 | Navigation ↓ entre zones et éléments |
| `VK_LEFT` | 37 | Navigation ← ; rewind -30s (dans PlayerControls) |
| `VK_RIGHT` | 39 | Navigation → ; forward +30s (dans PlayerControls) |
| `VK_OK` / Enter | 13 | Sélectionner / valider / afficher contrôles lecteur |
| `VK_BACK` | **461** | ⚠️ Retour arrière — `preventDefault()` **OBLIGATOIRE** partout |
| `VK_PLAY` | 415 | Play (lecture vidéo) |
| `VK_PAUSE` | 19 | Pause (lecture vidéo) |
| `VK_PLAY_PAUSE` | 10252 | Toggle play/pause (touche unique certains modèles C1) |
| `VK_STOP` | 413 | Arrêt → quitter le lecteur |
| `VK_FAST_FWD` | 417 | Avance rapide +30 secondes |
| `VK_REWIND` | 412 | Recul -30 secondes |
| `VK_RED` | 403 | *(réservé — non utilisé v2.0)* |
| `VK_GREEN` | 404 | *(réservé — non utilisé v2.0)* |
| `VK_YELLOW` | 405 | *(réservé — non utilisé v2.0)* |
| `VK_BLUE` | 406 | *(réservé — non utilisé v2.0)* |

> **Constante centrale :** tous les keycodes sont définis dans `src/constants/keycodes.js` et importés depuis ce fichier unique. Jamais de valeur numérique brute dans les composants.

> **Touches directionnelles + preventDefault()** : `e.preventDefault()` appliqué sur UP/DOWN/LEFT/RIGHT dans le listener global pour bloquer le scroll natif Chromium.

---

## Section 9 — appinfo.json

```json
{
  "id": "com.iptv.player",
  "version": "2.0.0",
  "vendor": "IPTV Player",
  "type": "web",
  "main": "index.html",
  "title": "IPTV Player",
  "icon": "icon.png",
  "largeIcon": "icon_large.png",
  "bgColor": "#000000",
  "splashBackground": "#000000",
  "allowCrossDomainAccess": true,
  "transparent": false,
  "disableBackHistoryAPI": true,
  "resolution": "1920x1080",
  "useNativeScroll": false,
  "cpuAffinity": "low"
}
```

| Champ | Justification |
|-------|--------------|
| `allowCrossDomainAccess: true` | Indispensable pour les requêtes HTTP vers le serveur Xtream et le chargement des posters (CORS depuis `file://`) |
| `disableBackHistoryAPI: true` | On gère la navigation BACK manuellement (VK_BACK 461 + preventDefault) — désactiver l'API histoire évite les conflits |
| `useNativeScroll: false` | Le scroll natif webOS est imprévisible, toute la navigation est gérée par spatial-navigation |
| `cpuAffinity: "low"` | Limite l'impact CPU de l'app sur le système de la TV |
| `resolution: "1920x1080"` | Viewport explicite — pas de mise à l'échelle imprévue |
| `bgColor / splashBackground: "#000000"` | Cohérent avec le thème sombre, pas de flash blanc au démarrage |

> **Emplacement à la build :** `appinfo.json` est dans `public/` (racine du projet) → copié automatiquement par Vite dans `dist/` lors du build.

---

## Section 10 — Structure de fichiers du projet

```
WebOS_IPTV_Player_V2.0/
│
├── public/                          — Assets statiques copiés tels quels dans dist/
│   ├── appinfo.json                 — Métadonnées webOS (obligatoire)
│   ├── icon.png                     — Icône 80×80 px (requis LG Content Store)
│   └── icon_large.png               — Icône 130×130 px
│
├── src/
│   ├── main.jsx                     — Point d'entrée React, wrapper DOMContentLoaded
│   ├── App.jsx                      — HashRouter + NavigationProvider + Routes
│   │
│   ├── constants/
│   │   ├── keycodes.js              — KEYS = { UP:38, DOWN:40, BACK:461, … }
│   │   └── frenchKeywords.js        — Liste mots-clés détection contenu FR/VF/VOSTFR
│   │
│   ├── contexts/
│   │   └── NavigationContext.jsx    — Contexte zone active, setActiveZone, previousZone
│   │
│   ├── hooks/
│   │   ├── useRemoteNavigation.js   — Listener keydown global, routing zones, BACK handler
│   │   ├── useSync.js               — Orchestration sync API Xtream → IndexedDB, état progression
│   │   ├── useMovies.js             — Chargement, filtrage, pagination films depuis IndexedDB
│   │   ├── useSeries.js             — Chargement, filtrage, pagination séries depuis IndexedDB
│   │   ├── usePlayer.js             — État lecteur, init HLS.js, gestion playlist séquentielle
│   │   └── useVirtualKeyboard.js    — État saisie clavier virtuel, position curseur, submit/cancel
│   │
│   ├── services/
│   │   ├── xtreamApi.js             — Client API Xtream : fetch, buildStreamUrl, buildEpisodeUrl
│   │   ├── db.js                    — Init IndexedDB (idb), toutes les opérations CRUD
│   │   └── storage.js               — Wrappers localStorage : getConfig, saveConfig, isConfigured
│   │
│   ├── pages/
│   │   ├── HomePage/
│   │   │   ├── index.jsx            — Onglets Films/Séries, gestion état tab actif, focus TabBar
│   │   │   ├── MoviesTab.jsx        — Composition FilterBar + ContentGrid films
│   │   │   └── SeriesTab.jsx        — Composition FilterBar + ContentGrid séries
│   │   └── PlayerPage/
│   │       └── index.jsx            — Plein écran : VideoPlayer + gestion playlist + retour
│   │
│   ├── components/
│   │   │
│   │   ├── Layout/
│   │   │   ├── index.jsx            — Structure globale : Toolbar en haut, <main>, StatusBar en bas
│   │   │   ├── Toolbar.jsx          — Titre app + bouton Réglages (ZONE: TOOLBAR)
│   │   │   └── StatusBar.jsx        — Messages dynamiques (sync en cours, erreur, info)
│   │   │
│   │   ├── ContentGrid/
│   │   │   ├── index.jsx            — CSS Grid, IntersectionObserver pagination (F19), lazy load
│   │   │   └── ContentCard.jsx      — Vignette : poster lazy (F08) + titre + rating, focusable
│   │   │
│   │   ├── FilterBar/
│   │   │   ├── index.jsx            — Conteneur barre filtres (ZONE: FILTER_BAR_*)
│   │   │   ├── SearchButton.jsx     — Bouton affichant la valeur, ouvre VirtualKeyboardModal (F10/F11)
│   │   │   ├── FilterSelect.jsx     — Composant select custom focusable (catégorie F17/F18)
│   │   │
│   │   ├── VideoPlayer/
│   │   │   ├── index.jsx            — Élément <video> HTML5, init HLS.js si .m3u8 (F22')
│   │   │   ├── PlayerControls.jsx   — Barre contrôles auto-masquée (F23/F25), ZONE: PLAYER_CONTROLS
│   │   │   └── ProgressBar.jsx      — Scrubber + affichage temps courant / durée (F24)
│   │   │
│   │   ├── modals/
│   │   │   ├── SettingsModal.jsx    — Config serveur, 4 champs + test + save (F01/F02)
│   │   │   └── SeriesModal.jsx      — Saisons/épisodes + marquage vus + lecture (F30/F33/F34/F36)
│   │   │
│   │   └── VirtualKeyboard/
│   │       └── index.jsx            — Clavier AZERTY navigable télécommande (6 usages)
│   │
│   └── styles/
│       ├── global.css               — Reset CSS, variables, body background #000
│       ├── theme.css                — Tokens couleurs dark theme (--color-primary, --color-focus, …)
│       └── focus.css                — Styles focus universels (.focused: outline, scale, glow)
│
├── index.html                       — Template HTML (root div, pas de type="module" après build)
├── vite.config.js                   — Config Vite webOS (base, assetsDir, Babel, removeModuleType)
├── package.json                     — Dépendances npm et scripts
├── .gitignore
├── ARCHITECTURE.md                  — Ce document
├── ANALYSE_FONCTIONNELLE.md         — Analyse code source Python
└── SELECTION_FONCTIONNALITES.md     — Décisions de portage
```

---

## Section 11 — Dépendances npm

### Dépendances de production

| Package | Version | Rôle |
|---------|---------|------|
| `react` | `^18.2.0` | Framework UI |
| `react-dom` | `^18.2.0` | Rendu DOM React |
| `react-router-dom` | `^6.20.0` | HashRouter + Routes + navigate |
| `@noriginmedia/spatial-navigation` | `^0.14.0` | Navigation spatiale télécommande (`useFocusable`, `FocusContext`, `init`) |
| `hls.js` | `^1.4.14` | Lecture HLS (.m3u8) en fallback si HLS natif indisponible |
| `idb` | `^8.0.0` | Wrapper Promise pour IndexedDB (API simple et typée) |

### Dépendances de développement

| Package | Version | Rôle |
|---------|---------|------|
| `vite` | `^5.0.0` | Bundler et serveur de développement |
| `@vitejs/plugin-react` | `^4.2.0` | Intégration React + Babel dans Vite |
| `@babel/plugin-transform-optional-chaining` | `^7.23.0` | Transpile `obj?.prop` pour Chromium 87 |
| `@babel/plugin-transform-nullish-coalescing-operator` | `^7.23.0` | Transpile `a ?? b` pour Chromium 87 |
| `@babel/plugin-transform-logical-assignment-operators` | `^7.23.0` | Transpile `a \|\|= b` pour Chromium 87 |

> **Note Babel :** selon le skill `webos-dev-constraints`, `?.` et `??` sont techniquement supportés nativement par Chrome 87 (ajoutés en Chrome 80). Les plugins Babel sont conservés par sécurité (comportement observé différent sur certaines TV LG C1 en pratique).

> **`idb` v8** : API basée sur les Promises, compatible IndexedDB disponible sur webOS 6+ (Chromium 87). À vérifier avec `ares-inspect` si une version antérieure (`^7.1.1`) est nécessaire.

---

## Section 12 — Checklist de déploiement

### Phase 1 — Build

```
□ npm run build → génère dist/
□ Vérifier dist/index.html :
  □ Aucune balise <script type="module"> (plugin removeModuleType actif)
  □ src scripts relatifs : ./assets/index.js (pas /assets/index.js)
  □ href CSS relatif : ./assets/index.css
□ Vérifier dist/ contient bien :
  □ appinfo.json (copié depuis public/)
  □ icon.png (80×80 px)
  □ icon_large.png (130×130 px)
  □ index.html
  □ assets/index.js  (bundle JS unique)
  □ assets/index.css (styles compilés)
□ Ouvrir dist/index.html dans Chrome PC → app fonctionnelle en file://
```

### Phase 2 — Packaging

```
□ ares-package ./dist
  → génère com.iptv.player_2.0.0_all.ipk
□ Vérifier que le .ipk est bien généré (taille > 0)
```

### Phase 3 — Installation TV

```
□ TV LG C1 et PC sur le même réseau Wi-Fi
□ Mode développeur activé sur la TV (app LG Developer Mode)
□ ares-setup-device → device "tv" configuré avec IP TV
□ ares-install --device tv ./com.iptv.player_2.0.0_all.ipk
□ ares-launch --device tv com.iptv.player
□ App visible à l'écran → pas d'écran noir
```

### Phase 4 — Validation fonctionnelle (télécommande physique)

```
□ Navigation télécommande
  □ UP/DOWN/LEFT/RIGHT naviguent entre zones (Toolbar → TabBar → FilterBar → Grid)
  □ OK sélectionne les éléments
  □ BACK ferme les modales sans quitter l'app (preventDefault actif)
  □ Aucun scroll natif parasite sur les touches directionnelles
  □ Focus visible sur tous les éléments actifs (outline/glow CSS)
  □ Focus restauré après fermeture de chaque modale

□ Clavier virtuel
  □ SearchButton → ouvre VirtualKeyboardModal (focus piégé)
  □ Saisie lettre par lettre fonctionnelle
  □ ⌫ efface le dernier caractère
  □ OK soumet la valeur
  □ BACK annule sans modifier la valeur

□ Configuration serveur
  □ Premier lancement → SettingsModal s'ouvre automatiquement
  □ Test connexion → feedback OK / KO visible
  □ Credentials sauvegardés en localStorage

□ Synchronisation catalogue
  □ Sync automatique au premier lancement (après config)
  □ Barre de progression visible (StatusBar)
  □ Grille films/séries remplie après sync

□ Lecture vidéo
  □ Film MP4 → lecture directe sans erreur
  □ URL .m3u8 → HLS.js ou HLS natif (vérifier console ares-inspect)
  □ Contrôles s'affichent à l'appui d'une touche, auto-masqués 3s
  □ VK_PLAY / VK_PAUSE / VK_STOP / VK_FF / VK_RW fonctionnels
  □ BACK quitte le lecteur → retour HomePage

□ Séries
  □ SeriesModal s'ouvre avec liste épisodes
  □ Épisodes vus marqués ✅
  □ Premier épisode non vu auto-sélectionné
  □ Lecture épisode unique → PlayerPage
  □ Lecture saison complète → playlist séquentielle

□ Performance
  □ Défilement grille fluide (>20 fps)
  □ Pas de freeze au chargement des vignettes (lazy loading actif)
  □ Mémoire stable après 10 min d'utilisation (ares-inspect → Memory tab)
```

### Phase 5 — Débogage (si anomalie)

```
□ ares-inspect --device tv --app com.iptv.player
  → ouvre Chromium DevTools dans le navigateur PC
  □ Console : aucune SyntaxError, aucune ReferenceError
  □ Network : toutes les requêtes API retournent 200
  □ Application → IndexedDB → vérifier stores remplis
  □ Application → localStorage → vérifier credentials présents
  □ Memory : pas de fuite mémoire (heap stable)
```

---

*Fin du document d'architecture — Référence pour tout le développement React webOS v2.0*

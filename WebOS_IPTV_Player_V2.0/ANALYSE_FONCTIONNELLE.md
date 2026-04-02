# Analyse Fonctionnelle — IPTV Player PC

> Analyse générée le 2026-03-29 — Base : code source Python/PyQt6 (~7 000 lignes, 13 fichiers)

---

## Section 1 — Résumé de l'application

Application desktop Windows de lecture et gestion de contenu IPTV via le protocole Xtream Codes. Elle synchronise un catalogue films/séries depuis un serveur Xtream, présente le contenu sous forme de grille de vignettes, et permet la lecture VLC, le téléchargement local et l'export M3U.

**Écrans / vues identifiés : 7**

| # | Vue | Fichier |
|---|-----|---------|
| 1 | Fenêtre principale (onglets) | main_window.py |
| 2 | Dialogue Paramètres serveur | settings_dialog.py |
| 3 | Dialogue Séries (saisons/épisodes) | series_dialog.py |
| 4 | Lecteur vidéo plein écran | player_window.py |
| 5 | Dialogue options de lecture (film) | play_options_dialog.py |
| 6 | Dialogue téléchargement (progression) | download_manager.py |
| 7 | Dialogue téléchargement saison (batch) | download_manager.py |

**Flux utilisateur principal :**
1. Au premier lancement : saisir URL serveur, port, identifiants → tester la connexion → sauvegarder
2. Synchronisation automatique du catalogue (API → SQLite, ~30 jours de cache)
3. Naviguer dans l'onglet Films ou Séries via grille de vignettes
4. Filtrer par langue française, genre, année ou recherche texte
5. Cliquer sur un film → choisir lire sur PC ou télécharger
6. Cliquer sur une série → choisir saison/épisode → lire ou télécharger
7. Consulter les téléchargements locaux dans l'onglet Téléchargements

---

## Section 2 — Inventaire exhaustif des fonctionnalités

| ID | Fonctionnalité | Écran/Module | Complexité | Dépendances techniques |
|----|---------------|-------------|------------|------------------------|
| F01 | Configuration serveur Xtream (URL, port, login) | settings_dialog | S | QLineEdit, config.json |
| F02 | Test de connexion au serveur | settings_dialog | S | XtreamClient.authenticate() |
| F03 | Synchronisation catalogue depuis API | main_window / SyncThread | M | QThread, Xtream API, SQLite |
| F04 | Synchronisation auto au démarrage (si cache > 30j) | main_window | S | cache_db.needs_sync() |
| F05 | Indicateur de progression de sync | main_window | S | QProgressBar, pyqtSignal |
| F06 | Grille de vignettes Films (ContentGrid) | main_window | M | ContentCard, QFrame, QThreadPool |
| F07 | Grille de vignettes Séries (ContentGrid) | main_window | M | ContentCard, QFrame, QThreadPool |
| F08 | Chargement asynchrone des posters (lazy) | main_window / PosterLoader | M | QRunnable, requests, QPixmap |
| F09 | Téléchargement par batch des vignettes | main_window / ThrottledThumbnailThread | M | QThread, throttle 50ms |
| F10 | Recherche texte Films | main_window | S | SQLite LIKE, QLineEdit |
| F11 | Recherche texte Séries | main_window | S | SQLite LIKE, QLineEdit |
| F12 | Filtre langue française (Films) | main_window | S | is_french flag SQLite |
| F13 | Filtre langue française (Séries) | main_window | S | is_french flag SQLite |
| F14 | Filtre genre (Films) | main_window | S | QComboBox, SQLite WHERE |
| F15 | Filtre genre (Séries) | main_window | S | QComboBox, SQLite WHERE |
| F16 | Filtre année (Films) | main_window | S | QSpinBox, SQLite WHERE |
| F17 | Filtre par catégorie (Films) | main_window | S | QComboBox, SQLite |
| F18 | Filtre par catégorie (Séries) | main_window | S | QComboBox, SQLite |
| F19 | Pagination / chargement infini (scroll) | main_window / ContentGrid | M | scroll event, lazy load |
| F20 | Redimensionnement grille responsive | main_window / ContentGrid | S | resizeEvent, colonnes dynamiques |
| F21 | Dialogue options film (lire / télécharger) | play_options_dialog | S | QDialog, pyqtSignal |
| F22 | Lecture film en plein écran (VLC) | player_window | L | python-vlc, hwnd, QFrame |
| F23 | Contrôles lecteur (play/pause/stop/seek/volume) | player_window | M | VLC API, QSlider |
| F24 | Affichage temps courant / durée | player_window | S | QTimer 500ms, VLC get_time() |
| F25 | Auto-masquage contrôles (3s inactivité) | player_window | S | QTimer single-shot |
| F26 | Raccourcis clavier lecteur | player_window | S | keyPressEvent |
| F27 | Lecture sur moniteur secondaire | player_window | M | QScreen detection, screen_index |
| F28 | Sourdine (mute/unmute) | player_window | S | VLC audio_set_mute() |
| F29 | Playlist séquentielle d'épisodes | player_window | M | _playlist list, QTimer fin détection |
| F30 | Dialogue séries : liste saisons/épisodes | series_dialog | M | QTreeWidget, SeriesInfoLoader |
| F31 | Chargement asynchrone infos série | series_dialog | M | QThread, XtreamClient.get_series_info() |
| F32 | Chargement asynchrone couverture série | series_dialog | S | QThread, requests, QPixmap |
| F33 | Marquage épisodes vus (✅ vert) | series_dialog | S | SQLite watched_episodes |
| F34 | Auto-sélection premier épisode non vu | series_dialog | S | set comparison SQLite |
| F35 | Lecture épisode unique | series_dialog | S | play_episode signal |
| F36 | Lecture saison complète (playlist) | series_dialog | M | play_season signal, playlist |
| F37 | Téléchargement épisode unique | series_dialog | S | download_episode signal |
| F38 | Téléchargement saison complète (batch) | series_dialog / SeasonDownloadDialog | M | QThread séquentiel |
| F39 | Téléchargement film avec progression | download_manager | M | QThread, requests stream, chunks 512Ko |
| F40 | Indicateur vitesse et ETA téléchargement | download_manager | S | calcul Ko/s, datetime |
| F41 | Annulation téléchargement (propre) | download_manager | S | _cancel flag, suppression fichier partiel |
| F42 | Téléchargement batch saison (séquentiel) | download_manager / SeasonDownloadDialog | M | queue d'épisodes, double cancel |
| F43 | Historique téléchargements (onglet) | main_window | S | SQLite downloads, QListWidget |
| F44 | Lecture d'un fichier téléchargé localement | main_window | S | PlayerWindow avec path local |
| F45 | Suppression d'un fichier téléchargé | main_window | M | os.remove(), SQLite DELETE |
| F46 | Export M3U tous canaux | main_window | S | file.write(), Xtream URL format |
| F47 | Export M3U canaux français uniquement | main_window | S | is_french filter + file.write() |
| F48 | Export catalogue CSV (films + séries) | main_window | S | csv.writer, SQLite SELECT |
| F49 | Vidage du cache (DB + thumbnails) | main_window | S | cache_db.clear_cache(), shutil.rmtree |
| F50 | Détection français par mots-clés catégorie | cache_db | S | FRENCH_KEYWORDS list, regex |
| F51 | Thème sombre (dark theme) | main_window | S | setStyleSheet() |
| F52 | Barre de statut messages | main_window | S | QStatusBar |
| F53 | Barre de menu | main_window | S | QMenuBar, QAction |
| F54 | Scan dossier Vidéos (lecture locale) | main_window | M | os.walk(), sous-répertoires |
| F55 | Timer inactivité (4s) pour arrêt vignettes | main_window | S | QTimer idle detection |

---

## Section 3 — Sources de données

### APIs appelées

**Protocole : Xtream Codes (HTTP GET)**

Base URL : `http://{server_url}:{port}/player_api.php`

| Méthode | Paramètres | Réponse | Utilisation |
|---------|-----------|---------|-------------|
| `GET /player_api.php?username=X&password=X` | auth | user_info, server_info | Authentification / test connexion |
| `GET /player_api.php?action=get_vod_category` | auth | `[{category_id, category_name, parent_id}]` | Catégories films |
| `GET /player_api.php?action=get_vod_streams&category_id=X` | auth + cat | `[{stream_id, name, stream_icon, container_extension, rating, added, …}]` | Liste films |
| `GET /player_api.php?action=get_vod_info&vod_id=X` | auth + id | `{info: {genre, release_date, plot, …}, movie_data: {…}}` | Métadonnées film |
| `GET /player_api.php?action=get_series_categories` | auth | `[{category_id, category_name, parent_id}]` | Catégories séries |
| `GET /player_api.php?action=get_series&category_id=X` | auth + cat | `[{series_id, name, cover, rating, genre, …}]` | Liste séries |
| `GET /player_api.php?action=get_series_info&series_id=X` | auth + id | `{seasons: {…}, episodes: {saison: [{episode_id, id, title, container_extension, …}]}}` | Épisodes série |
| `GET /player_api.php?action=get_live_categories` | auth | catégories live | Export M3U live |
| `GET /player_api.php?action=get_live_streams&category_id=X` | auth + cat | canaux live | Export M3U live |

**URLs de streaming :**
- Film : `{base_url}/movie/{username}/{password}/{stream_id}.{ext}`
- Épisode : `{base_url}/series/{username}/{password}/{stream_id}.{ext}`
- Live : `{base_url}/live/{username}/{password}/{stream_id}.{ext}`

**Téléchargement posters/vignettes :** HTTP GET direct sur les URLs `stream_icon` / `cover` (HTTPS, serveurs tiers)

### Fichiers locaux lus/écrits

| Fichier | Format | Chemin | Contenu |
|---------|--------|--------|---------|
| config.json | JSON | `%APPDATA%\IPTVPlayer\config.json` | Credentials + préférences |
| cache.db | SQLite | `%APPDATA%\IPTVPlayer\cache.db` | Catalogue + historique |
| thumbnails/* | JPEG/PNG | `%APPDATA%\IPTVPlayer\thumbnails\` | Vignettes cachées (~10-50 Ko chacune) |
| *.mkv / *.mp4 | Vidéo | `%USERPROFILE%\Videos\IPTVPlayer\` | Fichiers téléchargés |
| *.m3u | Texte | Dossier choisi par l'utilisateur | Playlists exportées |
| *.csv | CSV | Dossier choisi par l'utilisateur | Export catalogue |

### Données persistées

| Données | Stockage | Durée |
|---------|---------|-------|
| Credentials serveur | config.json | Permanent |
| Filtre langue | config.json | Permanent |
| Catalogue films (métadonnées) | SQLite movies | 30 jours |
| Catalogue séries | SQLite series | 30 jours |
| Catégories VOD/Séries | SQLite *_categories | 30 jours |
| Épisodes vus | SQLite watched_episodes | Permanent |
| Historique téléchargements | SQLite downloads | Permanent |
| Date dernière sync | SQLite sync_meta | Mis à jour à chaque sync |
| Vignettes images | Fichiers disque | Permanent (clear_cache pour effacer) |

---

## Section 4 — Interactions utilisateur

### Champs de saisie texte (clavier virtuel sur TV)

| Champ | Vue | Type PyQt6 | Contenu attendu |
|-------|-----|-----------|----------------|
| URL serveur | SettingsDialog | QLineEdit | URL HTTP (ex: `http://...`) |
| Port | SettingsDialog | QLineEdit | Entier (ex: `8080`) |
| Nom d'utilisateur | SettingsDialog | QLineEdit | Alphanumérique |
| Mot de passe | SettingsDialog | QLineEdit (echo=Password) | Alphanumérique |
| Recherche films | MainWindow | QLineEdit | Texte libre |
| Recherche séries | MainWindow | QLineEdit | Texte libre |

**Total : 6 champs de saisie → 6 claviers virtuels à prévoir sur TV**

### Raccourcis clavier

| Raccourci | Contexte | Action |
|-----------|---------|--------|
| `Espace` | PlayerWindow | Play / Pause |
| `Échap` | PlayerWindow | Fermer le lecteur |
| `→` | PlayerWindow | Avance +10 secondes |
| `←` | PlayerWindow | Recul -10 secondes |
| `Page Down` | PlayerWindow | Avance +5 minutes |
| `Page Up` | PlayerWindow | Recul -5 minutes |
| `↑` | PlayerWindow | Volume +5 |
| `↓` | PlayerWindow | Volume -5 |
| `M` | PlayerWindow | Mute / Unmute |
| `Ctrl+Q` | MainWindow | Quitter l'application |

### Interactions souris spéciales

| Interaction | Contexte | Effet |
|-------------|---------|-------|
| Clic gauche sur vidéo | PlayerWindow / _ClickOverlay | Toggle barre de contrôles |
| Clic droit sur vidéo | PlayerWindow | Play / Pause |
| Mouvement souris | PlayerWindow | Affiche contrôles (3s), puis masque |
| Scroll bas (fin de liste) | ContentGrid | Charge la page suivante (pagination) |
| Redimensionnement fenêtre | ContentGrid | Recalcule le nombre de colonnes |

---

## Section 5 — Incompatibilités webOS identifiées

### ❌ IMPOSSIBLE sur webOS

| ID | Fonctionnalité | Raison |
|----|---------------|--------|
| F22 | Lecture VLC plein écran | python-vlc / VLC n'existe pas sur webOS — remplacer par `<video>` HTML5 ou HLS.js |
| F27 | Lecture sur moniteur secondaire | webOS est mono-écran TV, pas de multi-monitor API |
| F44 | Lecture de fichier local téléchargé | Accès filesystem restreint sur webOS (pas de chemin arbitraire) |
| F45 | Suppression fichier téléchargé local | Accès fichiers système interdit |
| F39 | Téléchargement de fichier vidéo | `<a download>` non supporté pour streaming vidéo ; API webOS Downloads absente |
| F42 | Téléchargement batch saison | Même contrainte que F39 |
| F37 | Téléchargement épisode unique | Même contrainte que F39 |
| F38 | Téléchargement saison complète | Même contrainte que F39 |
| F43 | Historique téléchargements | Sans téléchargements, sans objet |
| F46 | Export M3U | Écriture filesystem impossible ; pas de QFileDialog |
| F47 | Export M3U français | Même contrainte que F46 |
| F48 | Export catalogue CSV | Même contrainte que F46 |
| F54 | Scan dossier Vidéos local | Pas d'accès `os.walk()` équivalent en webOS |

### ⚠️ ADAPTATION REQUISE

| ID | Fonctionnalité | Adaptation nécessaire |
|----|---------------|----------------------|
| F01 | Configuration serveur | QDialog → modal React ; QLineEdit → `<input>` avec clavier virtuel TV |
| F02 | Test de connexion | fetch() côté client → CORS possible selon serveur Xtream |
| F03 | Synchronisation catalogue | QThread → fetch + async/await ; stocker en IndexedDB ou localStorage |
| F04 | Sync auto au démarrage | `useEffect` au montage du composant App |
| F05 | Indicateur progression sync | State React + composant ProgressBar |
| F08 | Chargement asynchrone posters | `loading="lazy"` sur `<img>` + IntersectionObserver |
| F09 | Téléchargement batch vignettes | Fetch séquentiel avec délai ; ou simplement `loading="lazy"` |
| F10 | Recherche texte Films | `<input>` → clavier virtuel TV ; logique côté client sur données IndexedDB |
| F11 | Recherche texte Séries | Idem F10 |
| F17/F18 | Filtre catégorie | `<select>` navigables à la télécommande |
| F19 | Pagination / chargement infini | IntersectionObserver ou scroll event, focus TV compatible |
| F22' | Lecture vidéo (remplacement VLC) | `<video>` HTML5 + HLS.js pour les flux HLS ; DRM selon le serveur |
| F23 | Contrôles lecteur | Composant React navigable télécommande (touches VK_*) |
| F25 | Auto-masquage contrôles | `setTimeout` + event listener télécommande |
| F26 | Raccourcis clavier lecteur | Remapper sur keyCodes webOS (VK_PLAY, VK_PAUSE, VK_LEFT, etc.) |
| F29 | Playlist séquentielle | Gérer `ended` event sur `<video>` + queue d'URLs |
| F30 | Dialogue séries | QDialog → composant modal React focusable télécommande |
| F31 | Chargement async infos série | fetch() + Suspense ou state loading |
| F33 | Marquage épisodes vus | Stocker dans IndexedDB au lieu de SQLite |
| F34 | Auto-sélection épisode non vu | Logique JS identique, données IndexedDB |
| F36 | Lecture saison complète | Idem F29 |
| F50 | Détection français | Logique JS pure, FRENCH_KEYWORDS portables |
| F51 | Thème sombre | CSS / Tailwind, trivial |
| F52 | Barre de statut | Composant React |
| F53 | Barre de menu | Navigation React, attention focus télécommande |
| F55 | Timer inactivité | `setTimeout` JS |

### ✅ PORTABLE sans modification majeure

| ID | Fonctionnalité | Commentaire |
|----|---------------|-------------|
| F06 | Grille de vignettes Films | CSS Grid responsive |
| F07 | Grille de vignettes Séries | CSS Grid responsive |
| F13-F18 | Filtres (logique métier) | Pure JS, portables |
| F20 | Grille responsive | CSS Grid auto-fill |
| F21 | Dialogue options film | Modal React simple (sans download) |
| F24 | Affichage temps / durée | `timeupdate` event HTML5 video |
| F28 | Sourdine | `video.muted` HTML5 |
| F32 | Chargement couverture série | `<img>` async |
| F35 | Lecture épisode unique | `<video src=...>` |
| F40 | Affichage vitesse/ETA | Logique JS via fetch stream ReadableStream |
| F50 | Détection français mots-clés | Logique pure JS |

---

## Section 6 — Dépendances Python à analyser

| Bibliothèque | Version | Rôle | Équivalent Web/React | Action |
|-------------|---------|------|---------------------|--------|
| **PyQt6** | >=6.4.0 | Framework GUI complet | React + composants UI | Réécrire entièrement |
| **python-vlc** | >=3.0.18128 | Lecture vidéo | `<video>` HTML5 + **HLS.js** + **Shaka Player** | Remplacer |
| **requests** | >=2.28.0 | HTTP client | `fetch()` natif ou **axios** | Remplacer |
| **sqlite3** | built-in | Base de données locale | **IndexedDB** (via idb) ou **localStorage** pour config | Remplacer |
| **json** | built-in | Config persistence | JSON.parse/stringify natif | Trivial |
| **threading** | built-in | Threads background | `async/await`, `Promise`, Web Workers | Réécrire |
| **pathlib / os.path** | built-in | Chemins fichiers | N/A — pas de filesystem sur webOS | Supprimer |
| **hashlib** | built-in | MD5 pour noms thumbnails | `crypto.subtle.digest()` ou librairie js | Adapter |
| **re** | built-in | Regex | RegExp natif JS | Trivial |
| **datetime** | built-in | Dates/heures | `Date`, **date-fns** ou **dayjs** | Trivial |
| **shutil** | built-in | Suppression dossiers | N/A — pas d'accès filesystem | Supprimer |
| **subprocess / os** | built-in | Lancement process | N/A | Supprimer |
| **csv** | built-in | Export CSV | N/A (fonctionnalité exclue) | Supprimer |

### Bibliothèques web candidates à utiliser

| Besoin | Bibliothèque recommandée | Raison |
|--------|------------------------|--------|
| Lecture HLS/DASH | **HLS.js** | Compatible Chromium 87, supporte .m3u8 |
| Lecture vidéo direct | `<video>` HTML5 natif | Suffisant pour mp4/mkv si codec supporté |
| Persistance locale | **idb** (wrapper IndexedDB) | Async, structuré, remplacement SQLite |
| Config simple | **localStorage** | Suffisant pour 6 clés de config |
| Requêtes HTTP | **fetch()** natif | Intégré Chromium 87 |
| Dates | **date-fns** | Légère, tree-shakable |

---

*Fin de l'analyse fonctionnelle — aucune recommandation de portage incluse dans ce document*

# M3U Manager — Architecture technique

> Document de référence du projet — avril 2026
> Version 1.1 — mise à jour après session de développement du 2 avril 2026

---

## Structure des fichiers

```
PC_Gestion_M3U/
├── main.py                      ← Point d'entrée : affiche LoginDialog puis fenêtre principale
├── core/
│   ├── __init__.py              ← Rend core/ importable comme module Python
│   ├── xtream_client.py         ← Connexion Xtream, téléchargement M3U (CRÉÉ ✓)
│   ├── config_manager.py        ← Lecture/écriture config.json local (CRÉÉ ✓)
│   ├── m3u_parser.py            ← Parsing M3U → liste de dictionnaires Python (étape 2)
│   ├── filters.py               ← Détection type/qualité + logique de filtrage (étape 3)
│   └── exporter.py              ← Export M3U, CSV, téléchargement fichiers (étape 7)
├── ui/
│   ├── __init__.py              ← Rend ui/ importable comme module Python
│   ├── login_dialog.py          ← Boîte de dialogue de connexion PyQt6 (CRÉÉ ✓)
│   ├── main_window.py           ← Fenêtre principale PyQt6 (étape 4)
│   ├── filter_panel.py          ← Widget panneau de filtres (étape 6)
│   └── channel_table.py         ← Widget tableau avec surlignage et tri (étape 5)
├── data/
│   └── config.json              ← Identifiants sauvegardés localement (généré au runtime)
├── SPEC_fonctionnalites.md      ← Ce document fonctionnel
├── SPEC_architecture.md         ← Ce document technique
├── requirements.txt             ← PyQt6>=6.6.0, requests>=2.31.0
└── README.md
```

---

## Rôle détaillé de chaque module

### `main.py`
- Crée QApplication
- Affiche LoginDialog
- Si connexion acceptée : récupère XtreamClient authentifié, lance MainWindow
- Si quitter : sys.exit(0)
- Ne contient aucune logique métier

### `core/xtream_client.py` ✓
Classe `XtreamClient(base_url, username, password)`

| Méthode | Description |
|---|---|
| `__init__()` | Nettoie l'URL, crée Session requests avec retry 3x et User-Agent |
| `authenticate()` | Vérifie les identifiants via player_api.php, retourne user_info+server_info |
| `download_m3u()` | Télécharge la playlist via get.php (timeout 60s), retourne texte brut |
| `get_live_categories()` | Retourne la liste des catégories live |
| `get_vod_categories()` | Retourne la liste des catégories VOD |
| `get_series_categories()` | Retourne la liste des catégories séries |

Gestion d'erreurs : ValueError (identifiants), ConnectionError (réseau), RuntimeError (M3U)

### `core/config_manager.py` ✓
- `load_config()` → lit data/config.json, retourne dict (ou {} si absent)
- `save_config(dict)` → écrit data/config.json (crée data/ si nécessaire)
- Structure config : base_url, username, password, last_connected

### `core/m3u_parser.py` (étape 2)
Fonction `parse_m3u(text)` → retourne une liste de dictionnaires.

Structure d'une entrée parsée :
```python
{
  "name":         str,   # Nom affiché (après la virgule dans EXTINF)
  "url":          str,   # URL du flux
  "group":        str,   # group-title
  "tvg_id":       str,   # tvg-id
  "tvg_name":     str,   # tvg-name
  "tvg_logo":     str,   # URL du logo
  "tvg_country":  str,   # code ISO pays (ex: "FR")
  "tvg_language": str,   # langue (ex: "French")
  "tvg_chno":     str,   # numéro de chaîne
  "content_type": str,   # "live" | "vod" | "series" (détecté)
  "quality":      str,   # "SD" | "HD" | "FHD" | "4K" | "UHD" | "unknown"
  "raw_extinf":   str    # ligne EXTINF brute (pour réexport fidèle)
}
```

### `core/filters.py` (étape 3)
- `detect_content_type(entry)` → analyse URL et group pour classer live/vod/series
- `detect_quality(entry)` → analyse nom et group pour classer SD/HD/FHD/4K/unknown
- `apply_filters(entries, filter_config)` → retourne liste filtrée
- `filter_config` : dict de critères (types actifs, qualités actives, pays, langue, mots-clés)

### `core/exporter.py` (étape 7)
- `export_m3u(entries, filepath)` → reconstruit et écrit fichier M3U+ valide
- `export_csv(entries, filepath)` → CSV point-virgule (Nom ; URL)
- `download_entry(entry, dest_folder, progress_callback)` → télécharge avec suivi progression

### `ui/login_dialog.py` ✓
Classe `LoginDialog(QDialog)`
- Champs : URL, username, password
- Bouton "Tester la connexion" → AuthWorker(QThread) → résultat en signal
- Sauvegarde config si test réussi
- Active "Se connecter" uniquement après test positif
- `get_client()` → retourne XtreamClient authentifié
- `get_credentials()` → retourne (base_url, username, password)

### `ui/main_window.py` (étape 4)
Classe `MainWindow(QMainWindow)`
- Barre de menu (Fichier)
- Layout : FilterPanel (gauche, largeur fixe) + ChannelTable (droite, extensible)
- Barre de statut : nombre d'entrées affichées / total

### `ui/channel_table.py` (étape 5)
Classe `ChannelTable(QTableWidget)`
- Colonnes : Nom, Groupe, Type, Pays, Langue, Qualité, URL
- Surlignage : live=bleu clair (#DDEEFF), vod=vert clair (#DDFFD8), series=orange clair (#FFF0CC)
- Tri multi-colonnes
- Signal `entry_double_clicked(entry_dict)` sur double-clic

### `ui/filter_panel.py` (étape 6)
Classe `FilterPanel(QWidget)`
- Cases à cocher type, qualité, langue rapide
- Listes déroulantes pays/langue
- Champs texte libre
- Signal `filters_changed(filter_config)` émis à chaque modification

---

## Bibliothèques requises

| Bibliothèque | Version | Usage |
|---|---|---|
| PyQt6 | >= 6.6.0 | Interface graphique |
| requests | >= 2.31.0 | HTTP + téléchargement |
| re, csv, json, subprocess, os, pathlib, datetime | stdlib | Inclus Python 3.12 |

---

## Ordre de développement

| Étape | Fichier | Statut | Critère de validation |
|---|---|---|---|
| 1 | xtream_client + config_manager + login_dialog + main | ✓ EN COURS | Fenêtre connexion + test réussi + lignes M3U en console |
| 2 | m3u_parser | ⏳ | Dictionnaire Python par entrée affiché en console |
| 3 | filters | ⏳ | Filtres testés en console |
| 4 | main_window | ⏳ | Fenêtre principale qui s'ouvre |
| 5 | channel_table | ⏳ | Tableau avec données et surlignage |
| 6 | filter_panel | ⏳ | Filtres connectés au tableau |
| 7 | exporter | ⏳ | Fichiers M3U et CSV générés |
| 8 | Téléchargement | ⏳ | Vidéo téléchargée avec barre de progression |
| 9 | Lecture vidéo | ⏳ | Double-clic → VLC/mpv |

---

## Évolutions futures

| Cible | Stratégie |
|---|---|
| Android | Réutilisation de core/ via Kivy ou exposition en API REST (FastAPI) |
| webOS | core/ exposé via FastAPI, interface React |

La séparation stricte core/ (logique) / ui/ (affichage) garantit cette portabilité.

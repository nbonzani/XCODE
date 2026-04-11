"""
cache_db.py - Gestion du cache local : base SQLite + vignettes sur disque.

Ce module stocke :
  - La liste des films et séries (base SQLite) → recherche rapide sans réseau
  - Les vignettes (posters) téléchargées sur le disque → affichage instantané

Emplacements :
    %APPDATA%\\IPTVPlayer\\cache.db         → base de données SQLite
    %APPDATA%\\IPTVPlayer\\thumbnails\\      → dossier des vignettes

Les vignettes sont téléchargées en arrière-plan après chaque synchronisation.
Au démarrage suivant, elles sont lues depuis le disque (très rapide).
"""

import sqlite3
import hashlib
import threading
import os
import requests

from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# ============================================================
# Chemins des données
# ============================================================

DATA_DIR       = Path(os.path.expanduser("~")) / "AppData" / "Roaming" / "IPTVPlayer"
DB_FILE        = DATA_DIR / "cache.db"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"

# Mots-clés qui indiquent du contenu en français dans un nom de catégorie
FRENCH_KEYWORDS = [
    "FR", "FRENCH", "FRANÇAIS", "FRANCAIS",
    "VF", "VOSTFR", "VOST", " FR ", "FR-", "-FR",
    "FRANCO", "QUÉBEC", "QUEBEC"
]


# ============================================================
# Connexion et initialisation
# ============================================================

def _ensure_dirs():
    """Crée les dossiers de données si nécessaire."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """
    Crée et retourne une connexion à la base de données SQLite.
    row_factory permet d'accéder aux colonnes par leur nom.
    """
    _ensure_dirs()
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db() -> None:
    """
    Crée toutes les tables et index si ils n'existent pas encore.
    Ajoute également les colonnes manquantes sur une base existante
    (migration silencieuse pour les mises à jour).
    Appelé au démarrage de l'application.
    """
    _ensure_dirs()
    conn = get_connection()
    c = conn.cursor()

    # -- Table des catégories de films --
    c.execute("""
        CREATE TABLE IF NOT EXISTS vod_categories (
            category_id   TEXT PRIMARY KEY,
            category_name TEXT NOT NULL,
            parent_id     TEXT,
            is_french     INTEGER DEFAULT 0
        )
    """)

    # -- Table des films --
    c.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            stream_id           INTEGER PRIMARY KEY,
            name                TEXT NOT NULL,
            category_id         TEXT,
            category_name       TEXT,
            stream_icon         TEXT,
            container_extension TEXT DEFAULT 'mkv',
            rating              REAL DEFAULT 0,
            added               TEXT,
            genre               TEXT DEFAULT '',
            release_date        TEXT DEFAULT '',
            plot                TEXT DEFAULT '',
            cover_local         TEXT DEFAULT '',
            cached_at           TEXT,
            is_french           INTEGER DEFAULT 0
        )
    """)

    # -- Table des catégories de séries --
    c.execute("""
        CREATE TABLE IF NOT EXISTS series_categories (
            category_id   TEXT PRIMARY KEY,
            category_name TEXT NOT NULL,
            parent_id     TEXT,
            is_french     INTEGER DEFAULT 0
        )
    """)

    # -- Table des séries --
    c.execute("""
        CREATE TABLE IF NOT EXISTS series (
            series_id    INTEGER PRIMARY KEY,
            name         TEXT NOT NULL,
            category_id  TEXT,
            category_name TEXT,
            cover        TEXT,
            rating       REAL DEFAULT 0,
            genre        TEXT DEFAULT '',
            release_date TEXT DEFAULT '',
            plot         TEXT DEFAULT '',
            cover_local  TEXT DEFAULT '',
            cached_at    TEXT,
            is_french    INTEGER DEFAULT 0
        )
    """)

    # Index pour accélérer les recherches
    c.execute("CREATE INDEX IF NOT EXISTS idx_movies_name     ON movies(name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_movies_category ON movies(category_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_series_name     ON series(name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_series_category ON series(category_id)")

    # -- Table de métadonnées de synchronisation --
    # Stocke par exemple la date de la dernière synchronisation réussie.
    c.execute("""
        CREATE TABLE IF NOT EXISTS sync_meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # -- Table des épisodes visionnés --
    # Permet de surligner en vert les épisodes déjà regardés dans SeriesDialog
    # et de proposer automatiquement la lecture du suivant.
    c.execute("""
        CREATE TABLE IF NOT EXISTS watched_episodes (
            episode_id  INTEGER PRIMARY KEY,   -- id Xtream de l'épisode
            series_id   INTEGER NOT NULL,
            watched_at  TEXT NOT NULL
        )
    """)
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_watched_series "
        "ON watched_episodes(series_id)"
    )

    # -- Table des films téléchargés --
    c.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            stream_id     INTEGER,
            file_path     TEXT NOT NULL,
            file_size     INTEGER DEFAULT 0,
            extension     TEXT DEFAULT 'mkv',
            cover_local   TEXT DEFAULT '',
            downloaded_at TEXT NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_downloads_name ON downloads(name)")

    # Migration silencieuse : ajouter cover_local si elle n'existe pas
    # (pour les utilisateurs ayant une ancienne version de la base)
    for table, col in [("movies", "cover_local"), ("series", "cover_local")]:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # La colonne existe déjà → aucun problème

    conn.commit()
    conn.close()


# ============================================================
# Fonctions utilitaires internes
# ============================================================

def _is_french(category_name: str) -> bool:
    """Détecte si une catégorie correspond à du contenu en français."""
    if not category_name:
        return False
    name_upper = category_name.upper()
    return any(kw in name_upper for kw in FRENCH_KEYWORDS)


def _safe_float(value) -> float:
    """Convertit une valeur en float sans lever d'exception."""
    try:
        return float(value or 0)
    except (ValueError, TypeError):
        return 0.0


# ============================================================
# Sauvegarde dans le cache
# ============================================================

def save_vod_categories(categories: List[Dict]) -> None:
    """Sauvegarde toutes les catégories de films (remplace les existantes)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM vod_categories")
    for cat in categories:
        c.execute(
            "INSERT OR REPLACE INTO vod_categories VALUES (?, ?, ?, ?)",
            (
                str(cat.get("category_id", "")),
                cat.get("category_name", ""),
                str(cat.get("parent_id", "")),
                1 if _is_french(cat.get("category_name", "")) else 0
            )
        )
    conn.commit()
    conn.close()


def save_movies(movies: List[Dict], categories_map: Dict[str, str]) -> None:
    """
    Sauvegarde la liste complète des films dans le cache.

    Args:
        movies         : Liste des films retournés par l'API Xtream.
        categories_map : Dictionnaire {category_id: category_name}.
    """
    conn = get_connection()
    c = conn.cursor()

    # Récupérer les IDs des catégories françaises
    c.execute("SELECT category_id FROM vod_categories WHERE is_french = 1")
    french_cat_ids = {row[0] for row in c.fetchall()}

    cached_at = datetime.now().isoformat()
    c.execute("DELETE FROM movies")

    for movie in movies:
        cat_id = str(movie.get("category_id", ""))
        c.execute("""
            INSERT OR REPLACE INTO movies (
                stream_id, name, category_id, category_name,
                stream_icon, container_extension, rating, added,
                cached_at, is_french
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            movie.get("stream_id"),
            movie.get("name", ""),
            cat_id,
            categories_map.get(cat_id, ""),
            movie.get("stream_icon", ""),
            movie.get("container_extension", "mkv"),
            _safe_float(movie.get("rating")),
            movie.get("added", ""),
            cached_at,
            1 if cat_id in french_cat_ids else 0
        ))

    conn.commit()
    conn.close()


def save_series_categories(categories: List[Dict]) -> None:
    """Sauvegarde toutes les catégories de séries (remplace les existantes)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM series_categories")
    for cat in categories:
        c.execute(
            "INSERT OR REPLACE INTO series_categories VALUES (?, ?, ?, ?)",
            (
                str(cat.get("category_id", "")),
                cat.get("category_name", ""),
                str(cat.get("parent_id", "")),
                1 if _is_french(cat.get("category_name", "")) else 0
            )
        )
    conn.commit()
    conn.close()


def save_series_list(series_list: List[Dict], categories_map: Dict[str, str]) -> None:
    """
    Sauvegarde la liste complète des séries dans le cache.

    Args:
        series_list    : Liste des séries retournées par l'API Xtream.
        categories_map : Dictionnaire {category_id: category_name}.
    """
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT category_id FROM series_categories WHERE is_french = 1")
    french_cat_ids = {row[0] for row in c.fetchall()}

    cached_at = datetime.now().isoformat()
    c.execute("DELETE FROM series")

    for serie in series_list:
        cat_id = str(serie.get("category_id", ""))
        c.execute("""
            INSERT OR REPLACE INTO series (
                series_id, name, category_id, category_name,
                cover, rating, genre, release_date, plot,
                cached_at, is_french
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            serie.get("series_id"),
            serie.get("name", ""),
            cat_id,
            categories_map.get(cat_id, ""),
            serie.get("cover", ""),
            _safe_float(serie.get("rating")),
            serie.get("genre", ""),
            serie.get("releaseDate", ""),
            serie.get("plot", ""),
            cached_at,
            1 if cat_id in french_cat_ids else 0
        ))

    conn.commit()
    conn.close()


# ============================================================
# Recherche dans le cache
# ============================================================

def search_movies(
    query: str = "",
    genre: str = "",
    year: str = "",
    french_only: bool = True,
    category_id: str = "",
    limit: int = 300
) -> List[Dict]:
    """
    Recherche des films dans le cache selon plusieurs critères.

    Args:
        query       : Terme de recherche dans le nom du film.
        genre       : Genre à filtrer.
        year        : Année de sortie (ex: "2023").
        french_only : Si True, ne retourne que les films des catégories françaises.
        category_id : Filtre par identifiant de catégorie.
        limit       : Nombre maximum de résultats.

    Returns:
        Liste de dicts, chaque dict décrivant un film.
    """
    conn = get_connection()
    c = conn.cursor()

    sql = "SELECT * FROM movies WHERE 1=1"
    params = []

    if query:
        sql += " AND name LIKE ?"
        params.append(f"%{query}%")
    if genre:
        sql += " AND genre LIKE ?"
        params.append(f"%{genre}%")
    if year:
        # 'added' est un timestamp Unix (ex: "1617235200").
        # On utilise strftime de SQLite pour en extraire l'année.
        # On teste aussi release_date au cas où il serait renseigné (format "YYYY-...").
        sql += (
            " AND ("
            "strftime('%Y', datetime(CAST(added AS INTEGER), 'unixepoch')) = ?"
            " OR release_date LIKE ?"
            ")"
        )
        params.append(year)
        params.append(f"{year}%")
    if french_only:
        sql += " AND is_french = 1"
    if category_id:
        sql += " AND category_id = ?"
        params.append(category_id)

    sql += " ORDER BY name COLLATE NOCASE LIMIT ?"
    params.append(limit)

    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def search_series(
    query: str = "",
    genre: str = "",
    year: str = "",
    french_only: bool = True,
    category_id: str = "",
    limit: int = 300
) -> List[Dict]:
    """
    Recherche des séries dans le cache selon plusieurs critères.

    Args:
        query       : Terme de recherche dans le nom de la série.
        genre       : Genre à filtrer.
        year        : Année de sortie.
        french_only : Si True, ne retourne que les séries françaises.
        category_id : Filtre par identifiant de catégorie.
        limit       : Nombre maximum de résultats.

    Returns:
        Liste de dicts, chaque dict décrivant une série.
    """
    conn = get_connection()
    c = conn.cursor()

    sql = "SELECT * FROM series WHERE 1=1"
    params = []

    if query:
        sql += " AND name LIKE ?"
        params.append(f"%{query}%")
    if genre:
        sql += " AND genre LIKE ?"
        params.append(f"%{genre}%")
    if year:
        # Même logique que pour les films : 'added' est un timestamp Unix.
        sql += (
            " AND ("
            "strftime('%Y', datetime(CAST(added AS INTEGER), 'unixepoch')) = ?"
            " OR release_date LIKE ?"
            ")"
        )
        params.append(year)
        params.append(f"{year}%")
    if french_only:
        sql += " AND is_french = 1"
    if category_id:
        sql += " AND category_id = ?"
        params.append(category_id)

    sql += " ORDER BY name COLLATE NOCASE LIMIT ?"
    params.append(limit)

    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ============================================================
# Récupération des catégories
# ============================================================

def get_vod_categories_list(french_only: bool = True) -> List[Dict]:
    """Retourne la liste des catégories de films dans le cache."""
    conn = get_connection()
    c = conn.cursor()
    if french_only:
        c.execute("SELECT * FROM vod_categories WHERE is_french = 1 ORDER BY category_name")
    else:
        c.execute("SELECT * FROM vod_categories ORDER BY category_name")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_series_categories_list(french_only: bool = True) -> List[Dict]:
    """Retourne la liste des catégories de séries dans le cache."""
    conn = get_connection()
    c = conn.cursor()
    if french_only:
        c.execute("SELECT * FROM series_categories WHERE is_french = 1 ORDER BY category_name")
    else:
        c.execute("SELECT * FROM series_categories ORDER BY category_name")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ============================================================
# Compteurs
# ============================================================

def get_movie_count(french_only: bool = True) -> int:
    """Retourne le nombre de films en cache."""
    conn = get_connection()
    c = conn.cursor()
    if french_only:
        c.execute("SELECT COUNT(*) FROM movies WHERE is_french = 1")
    else:
        c.execute("SELECT COUNT(*) FROM movies")
    count = c.fetchone()[0]
    conn.close()
    return count


def get_series_count(french_only: bool = True) -> int:
    """Retourne le nombre de séries en cache."""
    conn = get_connection()
    c = conn.cursor()
    if french_only:
        c.execute("SELECT COUNT(*) FROM series WHERE is_french = 1")
    else:
        c.execute("SELECT COUNT(*) FROM series")
    count = c.fetchone()[0]
    conn.close()
    return count


# ============================================================
# Gestion des vignettes locales
# ============================================================

def _thumbnail_local_path(url: str, item_id: int, item_type: str) -> Optional[Path]:
    """
    Calcule le chemin local d'une vignette à partir de son URL.

    On utilise un hash MD5 partiel de l'URL pour créer un nom de fichier
    unique et court, sans risque de collision.

    Args:
        url       : URL distante de la vignette.
        item_id   : Identifiant du film ou de la série.
        item_type : "movie" ou "series".

    Returns:
        Chemin (Path) du fichier local, ou None si l'URL est vide.
    """
    if not url:
        return None
    # Extraire l'extension depuis l'URL
    ext = url.split(".")[-1].split("?")[0].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    return THUMBNAILS_DIR / f"{item_type}_{item_id}_{url_hash}.{ext}"


def get_thumbnail_path(url: str, item_id: int, item_type: str = "movie") -> Optional[str]:
    """
    Retourne le chemin local de la vignette si elle est déjà téléchargée,
    sinon None (le téléchargement se fait via download_thumbnails_background).

    Lecture pure depuis le disque → zéro réseau, très rapide.

    Args:
        url       : URL distante de la vignette.
        item_id   : Identifiant du film ou de la série.
        item_type : "movie" ou "series".

    Returns:
        Chemin absolu (str) si le fichier existe, sinon None.
    """
    local = _thumbnail_local_path(url, item_id, item_type)
    if local and local.exists():
        return str(local)
    return None


def _download_single_thumbnail(url: str, item_id: int, item_type: str) -> Optional[str]:
    """
    Télécharge une vignette depuis son URL et la sauvegarde sur le disque.
    Met à jour la colonne cover_local dans la base de données.

    Utilisé en interne par download_thumbnails_background.

    Returns:
        Chemin local du fichier, ou None en cas d'échec.
    """
    local = _thumbnail_local_path(url, item_id, item_type)
    if local is None:
        return None

    # Déjà présente → ne pas retélécharger
    if local.exists():
        return str(local)

    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            local.write_bytes(resp.content)
            # Enregistrer le chemin local dans la base de données
            _set_cover_local(item_id, item_type, str(local))
            return str(local)
    except Exception:
        pass  # Silencieux : image indisponible, pas de plantage

    return None


def _set_cover_local(item_id: int, item_type: str, local_path: str) -> None:
    """Met à jour la colonne cover_local dans la base pour un film ou une série."""
    conn = get_connection()
    c = conn.cursor()
    if item_type == "movie":
        c.execute(
            "UPDATE movies SET cover_local = ? WHERE stream_id = ?",
            (local_path, item_id)
        )
    else:
        c.execute(
            "UPDATE series SET cover_local = ? WHERE series_id = ?",
            (local_path, item_id)
        )
    conn.commit()
    conn.close()


def download_thumbnails_background(
    items: List[Dict],
    item_type: str,
    progress_callback=None
) -> threading.Thread:
    """
    Télécharge toutes les vignettes d'une liste en arrière-plan (thread daemon).

    L'application reste réactive pendant ce téléchargement.
    Au prochain démarrage, les vignettes seront lues depuis le disque.

    Args:
        items             : Liste de dicts (films ou séries).
        item_type         : "movie" ou "series".
        progress_callback : Fonction optionnelle appelée avec (current, total)
                            à chaque vignette téléchargée.

    Returns:
        Le thread lancé (peut être ignoré).
    """
    def _worker():
        total = len(items)
        for i, item in enumerate(items):
            url     = item.get("stream_icon") or item.get("cover", "")
            item_id = item.get("stream_id") or item.get("series_id")
            if url and item_id:
                _download_single_thumbnail(url, item_id, item_type)
            if progress_callback:
                progress_callback(i + 1, total)

    t = threading.Thread(target=_worker, daemon=True)
    # daemon=True : s'arrête automatiquement quand l'application se ferme
    t.start()
    return t


# ============================================================
# Métadonnées de synchronisation
# ============================================================

def get_last_sync_date() -> Optional[datetime]:
    """
    Retourne la date de la dernière synchronisation réussie,
    ou None si aucune synchronisation n'a encore eu lieu.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM sync_meta WHERE key = 'last_sync'")
    row = c.fetchone()
    conn.close()
    if row:
        try:
            return datetime.fromisoformat(row[0])
        except ValueError:
            return None
    return None


def set_last_sync_date() -> None:
    """
    Enregistre la date et l'heure actuelles comme date de la
    dernière synchronisation réussie.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO sync_meta (key, value) VALUES ('last_sync', ?)",
        (datetime.now().isoformat(),)
    )
    conn.commit()
    conn.close()


def needs_sync(max_age_days: int = 30) -> bool:
    """
    Indique si une synchronisation est nécessaire.

    Retourne True si :
      - Aucune synchronisation n'a jamais été effectuée (premier démarrage), ou
      - La dernière synchronisation date de plus de max_age_days jours.

    Args:
        max_age_days : Âge maximal du cache en jours (défaut : 30 jours).
    """
    last = get_last_sync_date()
    if last is None:
        return True   # Jamais synchronisé
    age = (datetime.now() - last).days
    return age >= max_age_days


# ============================================================
# Items sans vignette locale (pour le téléchargement en arrière-plan)
# ============================================================

def get_items_without_thumbnail(item_type: str, limit: int = 1000) -> List[Dict]:
    """
    Retourne les films ou séries qui n'ont pas encore de vignette locale.

    Ce sont eux qui seront traités par ThrottledThumbnailThread.

    Args:
        item_type : "movie" ou "series".
        limit     : Nombre maximum d'items retournés.

    Returns:
        Liste de dicts. Pour les films, contient 'stream_id' et 'stream_icon'.
        Pour les séries, contient 'series_id' et 'cover'.
    """
    conn = get_connection()
    c = conn.cursor()

    if item_type == "movie":
        c.execute("""
            SELECT stream_id, name, stream_icon
            FROM   movies
            WHERE  (cover_local = '' OR cover_local IS NULL)
              AND  (stream_icon IS NOT NULL AND stream_icon != '')
            LIMIT  ?
        """, (limit,))
    else:
        c.execute("""
            SELECT series_id, name, cover
            FROM   series
            WHERE  (cover_local = '' OR cover_local IS NULL)
              AND  (cover IS NOT NULL AND cover != '')
            LIMIT  ?
        """, (limit,))

    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ============================================================
# Épisodes visionnés
# ============================================================

def mark_episode_watched(episode_id: int, series_id: int) -> None:
    """
    Enregistre qu'un épisode a été lancé en lecture.

    Si l'épisode a déjà été marqué, sa date de visionnage est mise à jour.

    Args:
        episode_id : Identifiant Xtream de l'épisode (champ 'id').
        series_id  : Identifiant Xtream de la série parente.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """INSERT OR REPLACE INTO watched_episodes (episode_id, series_id, watched_at)
           VALUES (?, ?, ?)""",
        (episode_id, series_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_watched_episodes_set(series_id: int) -> set:
    """
    Retourne l'ensemble des identifiants d'épisodes déjà visionnés
    pour une série donnée.

    Utilisé par SeriesDialog pour colorier les épisodes vus en vert
    et pré-sélectionner le prochain épisode non visionné.

    Args:
        series_id : Identifiant Xtream de la série.

    Returns:
        Ensemble (set) d'entiers : les episode_id visionnés.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT episode_id FROM watched_episodes WHERE series_id = ?",
        (series_id,)
    )
    rows = c.fetchall()
    conn.close()
    return {row[0] for row in rows}


# ============================================================
# Sauvegarde d'une vignette depuis des octets déjà téléchargés
# ============================================================

def save_thumbnail_from_bytes(
    url: str, item_id: int, item_type: str, content: bytes
) -> Optional[str]:
    """
    Persiste sur le disque une vignette déjà téléchargée (bytes en mémoire).

    Appelé par PosterLoader juste après son téléchargement réseau,
    pour éviter de retélécharger la même image au prochain démarrage.

    Args:
        url       : URL d'origine (sert à calculer le nom de fichier local).
        item_id   : Identifiant du film ou de la série.
        item_type : "movie" ou "series".
        content   : Contenu brut (bytes) de l'image.

    Returns:
        Chemin local (str) si la sauvegarde a réussi, sinon None.
    """
    local = _thumbnail_local_path(url, item_id, item_type)
    if local is None:
        return None
    if local.exists():
        return str(local)   # Déjà présente, rien à faire
    try:
        _ensure_dirs()
        local.write_bytes(content)
        _set_cover_local(item_id, item_type, str(local))
        return str(local)
    except Exception:
        return None


# ============================================================
# Nettoyage du cache
# ============================================================

# ============================================================
# Films téléchargés
# ============================================================

def add_download(
    name: str,
    stream_id: int,
    file_path: str,
    file_size: int,
    extension: str,
    cover_local: str = ""
) -> int:
    """
    Enregistre un film téléchargé dans la base de données.

    Args:
        name        : Titre du film.
        stream_id   : Identifiant Xtream (pour référence).
        file_path   : Chemin absolu du fichier téléchargé.
        file_size   : Taille en octets.
        extension   : Extension vidéo (mkv, mp4…).
        cover_local : Chemin local de la vignette (optionnel).

    Returns:
        ID de l'enregistrement créé.
    """
    from datetime import datetime
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO downloads (name, stream_id, file_path, file_size,
                               extension, cover_local, downloaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        name, stream_id, file_path, file_size,
        extension, cover_local, datetime.now().isoformat()
    ))
    row_id = c.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_downloads() -> List[Dict]:
    """
    Retourne la liste de tous les films téléchargés, du plus récent au plus ancien.

    Returns:
        Liste de dicts avec les clés : id, name, file_path, file_size,
        extension, cover_local, downloaded_at.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM downloads ORDER BY downloaded_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_download(download_id: int) -> None:
    """
    Supprime un enregistrement de téléchargement de la base de données.
    Note : le fichier vidéo sur le disque N'est PAS supprimé ici —
    c'est à l'appelant de le faire s'il le souhaite.

    Args:
        download_id : ID de l'enregistrement (colonne `id`).
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM downloads WHERE id = ?", (download_id,))
    conn.commit()
    conn.close()


def clear_cache() -> None:
    """
    Vide entièrement le cache :
    - Supprime toutes les données de la base SQLite
    - Supprime toutes les vignettes du disque
    Note : les films téléchargés (table downloads + fichiers) sont conservés.
    """
    # Supprimer les vignettes sur le disque
    if THUMBNAILS_DIR.exists():
        for f in THUMBNAILS_DIR.iterdir():
            try:
                f.unlink()
            except Exception:
                pass

    # Vider les tables de la base de données
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM movies")
    c.execute("DELETE FROM series")
    c.execute("DELETE FROM vod_categories")
    c.execute("DELETE FROM series_categories")
    conn.commit()
    conn.close()

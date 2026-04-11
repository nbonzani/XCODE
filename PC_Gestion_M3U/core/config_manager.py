import json
import hashlib
from pathlib import Path
import datetime

CONFIG_PATH  = Path(__file__).parent.parent / "data" / "config.json"
CACHE_PATH   = Path(__file__).parent.parent / "data" / "m3u_cache.m3u"
CACHE_META   = Path(__file__).parent.parent / "data" / "m3u_cache.json"
RATINGS_PATH = Path(__file__).parent.parent / "data" / "ratings_cache.json"


def load_config() -> dict:
    """Charge la configuration depuis data/config.json.

    Returns:
        dict avec la configuration, ou {} si le fichier n'existe pas ou est invalide.
    """
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def add_recent_file(filepath: str, max_recent: int = 5) -> None:
    """Ajoute un fichier en tête de la liste des fichiers récents (max 5)."""
    config = load_config()
    recent = config.get("recent_files", [])
    # Retirer si déjà présent, puis remettre en tête
    recent = [f for f in recent if f != filepath]
    recent.insert(0, filepath)
    config["recent_files"] = recent[:max_recent]
    save_config(config)


def get_recent_files() -> list:
    """Retourne la liste des fichiers récents (chemins existants uniquement)."""
    config = load_config()
    recent = config.get("recent_files", [])
    import os
    return [f for f in recent if os.path.exists(f)]


def save_config(config_dict: dict) -> bool:
    """Sauvegarde la configuration dans data/config.json.

    Args:
        config_dict: dictionnaire de configuration à sauvegarder.

    Returns:
        True si succès, False si erreur.
    """
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


# ── Cache de la playlist M3U ─────────────────────────────────────

def _connection_fingerprint(base_url: str, username: str, password: str) -> str:
    """Hash unique identifiant les paramètres de connexion."""
    raw = f"{base_url}|{username}|{password}"
    return hashlib.sha256(raw.encode()).hexdigest()


def save_m3u_cache(raw_text: str, base_url: str, username: str, password: str) -> bool:
    """Sauvegarde le texte M3U brut et les métadonnées de connexion."""
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(raw_text, encoding="utf-8")
        meta = {
            "fingerprint": _connection_fingerprint(base_url, username, password),
            "saved_at": datetime.datetime.now().isoformat(),
            "size": len(raw_text),
        }
        CACHE_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def load_m3u_cache(base_url: str, username: str, password: str) -> str | None:
    """Charge le cache M3U si les paramètres de connexion correspondent.

    Returns:
        Le texte M3U brut, ou None si pas de cache ou connexion différente.
    """
    try:
        if not CACHE_PATH.exists() or not CACHE_META.exists():
            return None
        meta = json.loads(CACHE_META.read_text(encoding="utf-8"))
        expected = _connection_fingerprint(base_url, username, password)
        if meta.get("fingerprint") != expected:
            return None
        return CACHE_PATH.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        return None


def clear_m3u_cache() -> None:
    """Supprime le cache M3U et les scores."""
    try:
        for p in (CACHE_PATH, CACHE_META, RATINGS_PATH):
            if p.exists():
                p.unlink()
    except OSError:
        pass


# ── Cache des scores (ratings) ───────────────────────────────────

def save_ratings_cache(ratings: dict) -> bool:
    """Sauvegarde le dictionnaire des scores (stream_id/name → rating)."""
    try:
        RATINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RATINGS_PATH.write_text(
            json.dumps(ratings, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except OSError:
        return False


def load_ratings_cache() -> dict:
    """Charge les scores sauvegardés. Retourne {} si absent."""
    try:
        if RATINGS_PATH.exists():
            return json.loads(RATINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}

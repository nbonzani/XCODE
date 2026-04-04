import json
from pathlib import Path
import datetime

CONFIG_PATH = Path(__file__).parent.parent / "data" / "config.json"


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

"""
config.py - Gestion de la configuration de l'application IPTV Player.

Les paramètres sont sauvegardés dans un fichier JSON dans le dossier
utilisateur Windows : C:\\Users\\<nom>\\AppData\\Roaming\\IPTVPlayer\\
"""

import json
import os

# Dossier et fichier de configuration (dans AppData pour Windows)
CONFIG_DIR = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "IPTVPlayer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# Valeurs par défaut de la configuration
DEFAULT_CONFIG = {
    "server_url": "",       # URL du serveur, ex: http://monserveur.com
    "port": "8080",         # Port du serveur
    "username": "",         # Nom d'utilisateur Xtream
    "password": "",         # Mot de passe Xtream
    "language_filter": "french",  # "french" = contenu FR uniquement, "all" = tout
    "last_sync": None       # Date de la dernière synchronisation
}


def load_config() -> dict:
    """
    Charge la configuration depuis le fichier JSON.

    Si le fichier n'existe pas encore (premier lancement),
    retourne la configuration par défaut.

    Returns:
        dict: La configuration de l'application.
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Fusionner avec les valeurs par défaut pour les nouvelles clés
            # (utile si une nouvelle version ajoute de nouveaux paramètres)
            config = DEFAULT_CONFIG.copy()
            config.update(data)
            return config
        except (json.JSONDecodeError, IOError):
            # Fichier corrompu → retourner les valeurs par défaut
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """
    Sauvegarde la configuration dans le fichier JSON.

    Crée le dossier si celui-ci n'existe pas encore.

    Args:
        config: Dictionnaire contenant les paramètres à sauvegarder.
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def is_configured(config: dict) -> bool:
    """
    Vérifie si la configuration minimale est présente
    (URL serveur, nom d'utilisateur, mot de passe).

    Args:
        config: La configuration à vérifier.

    Returns:
        True si l'application est configurée, False sinon.
    """
    return bool(
        config.get("server_url") and
        config.get("username") and
        config.get("password")
    )

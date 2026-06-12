"""Persistance des profils sous %APPDATA% (config NON sensible). — JALON 1.

Stocke la liste des :class:`~threedx_cleaner.models.profile.Profile` en TOML
sous ``%APPDATA%/3dx-cleaner/profiles.toml``. **Aucun mot de passe** n'y figure
(cf. :mod:`secret_store`, qui range les secrets dans le Credential Manager).

Le dossier de config est resoluble via la variable d'environnement
``THREEDX_CONFIG_DIR`` (prioritaire, utile aux tests et au portable), sinon
``%APPDATA%`` (Windows), avec repli sur ``~/.config`` ailleurs.

Format du fichier (array of tables) ::

    [[profiles]]
    name = "Polytech on-prem"
    deployment = "on_prem"
    username = "prenom.nom@univ-lorraine.fr"
    base_url = "https://3dexperience2025.univ-lorraine.fr"
    ...
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import tomli_w

from threedx_cleaner.credentials import secret_store
from threedx_cleaner.models.profile import Profile

#: Sous-dossier applicatif et nom de fichier des profils.
APP_DIR_NAME = "3dx-cleaner"
PROFILES_FILENAME = "profiles.toml"

#: Variable d'environnement permettant de surcharger le dossier de config.
CONFIG_DIR_ENV = "THREEDX_CONFIG_DIR"


def config_dir() -> Path:
    """Retourne le dossier de configuration de l'application.

    Priorite : ``THREEDX_CONFIG_DIR`` > ``%APPDATA%`` (Windows) > ``~/.config``.
    Le dossier est cree si absent.
    """
    override = os.environ.get(CONFIG_DIR_ENV, "").strip()
    if override:
        base = Path(override)
    elif appdata := os.environ.get("APPDATA", "").strip():
        base = Path(appdata) / APP_DIR_NAME
    else:
        base = Path.home() / ".config" / APP_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def profiles_path() -> Path:
    """Chemin complet du fichier ``profiles.toml``."""
    return config_dir() / PROFILES_FILENAME


def load() -> list[Profile]:
    """Charge tous les profils enregistres.

    Returns:
        La liste des profils (vide si le fichier n'existe pas encore).

    Raises:
        ValueError: si une entree du fichier est invalide (mode incoherent...).
    """
    path = profiles_path()
    if not path.exists():
        return []
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    raw_profiles = data.get("profiles", [])
    return [Profile(**entry) for entry in raw_profiles]


def save(profiles: list[Profile]) -> None:
    """Ecrit l'ensemble des profils (remplace le fichier).

    Args:
        profiles: liste complete des profils a persister.
    """
    payload = {"profiles": [p.model_dump() for p in profiles]}
    path = profiles_path()
    # Ecriture atomique : fichier temporaire puis remplacement.
    tmp = path.with_suffix(".toml.tmp")
    with tmp.open("wb") as fh:
        tomli_w.dump(payload, fh)
    tmp.replace(path)


def get(name: str) -> Profile | None:
    """Retourne le profil de ce nom, ou ``None`` s'il n'existe pas."""
    for profile in load():
        if profile.name == name:
            return profile
    return None


def upsert(profile: Profile) -> None:
    """Ajoute le profil ou remplace celui de meme nom.

    Args:
        profile: profil a enregistrer (cle = ``profile.name``).
    """
    profiles = load()
    for idx, existing in enumerate(profiles):
        if existing.name == profile.name:
            profiles[idx] = profile
            break
    else:
        profiles.append(profile)
    save(profiles)


def delete(name: str, *, drop_secret: bool = True) -> bool:
    """Supprime un profil et, par defaut, son secret keyring associe.

    Args:
        name: nom du profil a supprimer.
        drop_secret: si vrai, efface aussi le mot de passe du Credential Manager.

    Returns:
        ``True`` si un profil a ete retire, ``False`` s'il n'existait pas.
    """
    profiles = load()
    remaining = [p for p in profiles if p.name != name]
    if len(remaining) == len(profiles):
        return False
    save(remaining)
    if drop_secret:
        secret_store.delete_password(name)
    return True

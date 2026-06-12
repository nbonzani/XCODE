"""Secrets dans le Windows Credential Manager via ``keyring``. — JALON 1.

Le mot de passe d'un profil est stocke/lu/efface via ``keyring`` (service =
``SERVICE_NAME``, username = ``Profile.name``). JAMAIS de mot de passe en clair
sur disque ni dans un log.

Sous Windows, le backend par defaut est ``WinVaultKeyring`` (Credential
Manager). Les fonctions ci-dessous sont volontairement minces : elles isolent
le reste de l'application de l'API ``keyring`` et garantissent qu'aucun secret
ne transite par un fichier de configuration.
"""

from __future__ import annotations

import keyring

#: Nom de service unique sous lequel tous les secrets de l'app sont ranges.
SERVICE_NAME = "3dx-cleaner"


def set_password(profile_name: str, password: str) -> None:
    """Enregistre (ou remplace) le mot de passe associe a un profil.

    Args:
        profile_name: nom du profil (cle unique, = ``Profile.name``).
        password: mot de passe 3DPassport a stocker dans le coffre OS.

    Raises:
        ValueError: si ``profile_name`` ou ``password`` est vide.
        keyring.errors.KeyringError: en cas d'echec du backend.
    """
    if not profile_name:
        raise ValueError("Le nom de profil est requis.")
    if not password:
        raise ValueError("Le mot de passe est requis.")
    keyring.set_password(SERVICE_NAME, profile_name, password)


def get_password(profile_name: str) -> str | None:
    """Lit le mot de passe d'un profil depuis le coffre OS.

    Args:
        profile_name: nom du profil.

    Returns:
        Le mot de passe, ou ``None`` si aucun secret n'est enregistre.
    """
    if not profile_name:
        return None
    return keyring.get_password(SERVICE_NAME, profile_name)


def delete_password(profile_name: str) -> None:
    """Efface le mot de passe d'un profil (idempotent).

    Ne leve pas si aucun secret n'existe : l'operation est silencieuse afin
    de pouvoir nettoyer un profil sans connaitre l'etat prealable du coffre.

    Args:
        profile_name: nom du profil.
    """
    if not profile_name:
        return
    try:
        keyring.delete_password(SERVICE_NAME, profile_name)
    except keyring.errors.PasswordDeleteError:
        # Aucun secret enregistre : rien a faire.
        pass


def has_password(profile_name: str) -> bool:
    """Indique si un mot de passe est enregistre pour ce profil."""
    return get_password(profile_name) is not None

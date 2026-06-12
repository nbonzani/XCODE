"""Gestion des identifiants : profils (non sensibles) + secrets (keyring).

- :mod:`settings_builder` : batit un ``Settings`` threedx_mcp **en memoire**
  depuis un profil + mot de passe (aucun secret sur disque).
- :mod:`profile_store` : persistance des profils sous %APPDATA% (jalon 1).
- :mod:`secret_store` : mots de passe dans le Windows Credential Manager (jalon 1).
"""

from __future__ import annotations

from threedx_cleaner.credentials import profile_store, secret_store
from threedx_cleaner.credentials.settings_builder import (
    build_settings,
    build_settings_from_env,
)

__all__ = [
    "build_settings",
    "build_settings_from_env",
    "profile_store",
    "secret_store",
]

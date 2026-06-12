"""Persistance des profils sous %APPDATA% (config NON sensible). — JALON 1.

Stockera la liste des :class:`~threedx_cleaner.models.profile.Profile` en
TOML/JSON sous ``%APPDATA%/3dx-cleaner/profiles.toml``. Aucun mot de passe
n'y figure (cf. :mod:`secret_store`).
"""

from __future__ import annotations

# Implementation au jalon 1 (F7).

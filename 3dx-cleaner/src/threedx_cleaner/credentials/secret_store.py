"""Secrets dans le Windows Credential Manager via ``keyring``. — JALON 1.

Le mot de passe d'un profil sera stocke/lu/efface via ``keyring`` (service =
``3dx-cleaner``, username = ``Profile.name``). JAMAIS de mot de passe en clair
sur disque ni dans un log.
"""

from __future__ import annotations

# Implementation au jalon 1 (F7).

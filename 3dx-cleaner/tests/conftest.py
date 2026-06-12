"""Fixtures partagees des tests.

Installe un backend ``keyring`` **en memoire** pour la duree de chaque test :
aucun secret ne touche le Credential Manager reel de la machine, et les tests
restent hermetiques et reproductibles.
"""

from __future__ import annotations

from collections.abc import Iterator

import keyring
import keyring.backend
import keyring.errors
import pytest


class InMemoryKeyring(keyring.backend.KeyringBackend):
    """Backend keyring volatil (dict en memoire), pour les tests."""

    priority = 1.0  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self._store[(service, username)]
        except KeyError as exc:
            raise keyring.errors.PasswordDeleteError("Aucun secret") from exc


@pytest.fixture(autouse=True)
def in_memory_keyring() -> Iterator[InMemoryKeyring]:
    """Remplace le backend keyring par un backend volatil le temps du test."""
    previous = keyring.get_keyring()
    backend = InMemoryKeyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(previous)


@pytest.fixture
def config_dir(tmp_path, monkeypatch) -> Iterator[str]:
    """Isole le dossier de config (profiles.toml) dans un repertoire temporaire."""
    monkeypatch.setenv("THREEDX_CONFIG_DIR", str(tmp_path))
    yield str(tmp_path)

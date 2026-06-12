"""Tests du stockage des secrets via keyring (backend en memoire, cf. conftest)."""

from __future__ import annotations

import pytest

from threedx_cleaner.credentials import secret_store


def test_set_get_roundtrip() -> None:
    secret_store.set_password("monprofil", "s3cret")
    assert secret_store.get_password("monprofil") == "s3cret"
    assert secret_store.has_password("monprofil") is True


def test_get_absent_returns_none() -> None:
    assert secret_store.get_password("inconnu") is None
    assert secret_store.has_password("inconnu") is False


def test_overwrite() -> None:
    secret_store.set_password("p", "old")
    secret_store.set_password("p", "new")
    assert secret_store.get_password("p") == "new"


def test_delete_is_idempotent() -> None:
    secret_store.set_password("p", "x")
    secret_store.delete_password("p")
    assert secret_store.get_password("p") is None
    # Deuxieme suppression : ne doit pas lever.
    secret_store.delete_password("p")


def test_empty_inputs_rejected() -> None:
    with pytest.raises(ValueError):
        secret_store.set_password("", "x")
    with pytest.raises(ValueError):
        secret_store.set_password("p", "")
    # Lecture/suppression d'un nom vide : silencieux.
    assert secret_store.get_password("") is None
    secret_store.delete_password("")

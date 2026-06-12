"""Tests de la persistance des profils (TOML isole via THREEDX_CONFIG_DIR)."""

from __future__ import annotations

from pathlib import Path

import pytest

from threedx_cleaner.credentials import profile_store, secret_store
from threedx_cleaner.models.profile import Profile

pytestmark = pytest.mark.usefixtures("config_dir")


def _onprem(name: str = "onprem") -> Profile:
    return Profile(
        name=name,
        deployment="on_prem",
        username="a.b@univ-lorraine.fr",
        base_url="https://3dx.univ-lorraine.fr",
    )


def _cloud(name: str = "cloud") -> Profile:
    return Profile(
        name=name,
        deployment="cloud",
        username="a.b@example.com",
        tenant_id="r1132101034393-eu1-academia",
        platform_id="R1132101034393",
    )


def test_load_empty_when_no_file() -> None:
    assert profile_store.load() == []


def test_upsert_and_get_roundtrip() -> None:
    profile_store.upsert(_onprem())
    loaded = profile_store.get("onprem")
    assert loaded is not None
    assert loaded.deployment == "on_prem"
    assert loaded.base_url == "https://3dx.univ-lorraine.fr"


def test_upsert_replaces_same_name() -> None:
    profile_store.upsert(_onprem())
    updated = _onprem()
    updated = updated.model_copy(update={"username": "c.d@univ-lorraine.fr"})
    profile_store.upsert(updated)
    profiles = profile_store.load()
    assert len(profiles) == 1
    assert profiles[0].username == "c.d@univ-lorraine.fr"


def test_multiple_modes_persist() -> None:
    profile_store.upsert(_onprem())
    profile_store.upsert(_cloud())
    names = sorted(p.name for p in profile_store.load())
    assert names == ["cloud", "onprem"]


def test_delete_returns_false_when_absent() -> None:
    assert profile_store.delete("nope") is False


def test_delete_removes_profile_and_secret() -> None:
    profile_store.upsert(_onprem())
    secret_store.set_password("onprem", "s3cret")
    assert profile_store.delete("onprem") is True
    assert profile_store.get("onprem") is None
    assert secret_store.get_password("onprem") is None


def test_file_contains_no_password(config_dir: str) -> None:
    """Garde-fou F7 : le fichier TOML ne doit jamais contenir de secret."""
    profile_store.upsert(_onprem())
    secret_store.set_password("onprem", "TOPSECRET")
    content = (Path(config_dir) / profile_store.PROFILES_FILENAME).read_text(
        encoding="utf-8"
    )
    assert "TOPSECRET" not in content
    assert "password" not in content.lower()


def test_invalid_entry_raises_on_load(config_dir: str) -> None:
    """Une entree au mode incoherent doit lever a la lecture (validation Profile)."""
    bad = 'profiles = [{ name = "x", deployment = "on_prem", username = "u" }]\n'
    (Path(config_dir) / profile_store.PROFILES_FILENAME).write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError):
        profile_store.load()

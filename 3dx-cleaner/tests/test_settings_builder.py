"""Tests du pivot technique : Settings construit en memoire (sans .env).

Verifie notamment qu'une variable d'environnement ``THREEDX_*`` ambiante de
l'AUTRE mode ne contamine pas la construction (robustesse F7).
"""

from __future__ import annotations

import pytest

from threedx_cleaner.credentials.settings_builder import build_settings
from threedx_cleaner.models.profile import Profile


def test_build_on_prem_settings() -> None:
    p = Profile(
        name="onprem",
        deployment="on_prem",
        username="a.b@univ-lorraine.fr",
        base_url="https://3dx.univ-lorraine.fr",
    )
    s = build_settings(p, "secret")
    assert s.deployment_mode == "on_prem"
    assert s.base_url == "https://3dx.univ-lorraine.fr"
    assert s.username == "a.b@univ-lorraine.fr"


def test_build_cloud_settings() -> None:
    p = Profile(
        name="cloud",
        deployment="cloud",
        username="a.b@example.com",
        tenant_id="r1132101034393-eu1-academia",
        platform_id="R1132101034393",
    )
    s = build_settings(p, "secret")
    assert s.deployment_mode == "cloud"
    assert s.tenant_id == "r1132101034393-eu1-academia"


def test_empty_password_rejected() -> None:
    p = Profile(
        name="x",
        deployment="on_prem",
        username="u",
        base_url="https://h",
    )
    with pytest.raises(ValueError):
        build_settings(p, "")


def test_ambient_env_other_mode_does_not_contaminate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un THREEDX_TENANT_ID ambiant ne doit pas rendre un profil on-prem ambigu."""
    monkeypatch.setenv("THREEDX_TENANT_ID", "rXXXX-eu1-academia")
    monkeypatch.setenv("THREEDX_PLATFORM_ID", "RXXXX")
    p = Profile(
        name="onprem",
        deployment="on_prem",
        username="u",
        base_url="https://3dx.univ-lorraine.fr",
    )
    s = build_settings(p, "secret")  # ne doit pas lever (mode neutralise)
    assert s.deployment_mode == "on_prem"
    assert s.tenant_id == ""

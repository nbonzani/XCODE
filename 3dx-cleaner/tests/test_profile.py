"""Tests du modele Profile (validation de coherence de mode)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from threedx_cleaner.models.profile import Profile


def test_on_prem_ok() -> None:
    p = Profile(
        name="polytech",
        deployment="on_prem",
        username="a.b@univ-lorraine.fr",
        base_url="https://3dx.univ-lorraine.fr",
    )
    assert p.target_label == "https://3dx.univ-lorraine.fr"


def test_cloud_ok() -> None:
    p = Profile(
        name="academia",
        deployment="cloud",
        username="a.b@example.com",
        tenant_id="r1132101034393-eu1-academia",
        platform_id="R1132101034393",
    )
    assert p.target_label == "r1132101034393-eu1-academia"


def test_on_prem_requires_base_url() -> None:
    with pytest.raises(ValidationError):
        Profile(name="x", deployment="on_prem", username="u")


def test_on_prem_rejects_cloud_fields() -> None:
    with pytest.raises(ValidationError):
        Profile(
            name="x",
            deployment="on_prem",
            username="u",
            base_url="https://h",
            tenant_id="t",
        )


def test_cloud_requires_tenant_and_platform() -> None:
    with pytest.raises(ValidationError):
        Profile(
            name="x", deployment="cloud", username="u", tenant_id="t"
        )  # platform_id manquant


def test_cloud_rejects_base_url() -> None:
    with pytest.raises(ValidationError):
        Profile(
            name="x",
            deployment="cloud",
            username="u",
            tenant_id="t",
            platform_id="P",
            base_url="https://h",
        )

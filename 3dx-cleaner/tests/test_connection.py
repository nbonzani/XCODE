"""Tests de la couche connexion (probe + contextes), moteur mocke.

On ne touche pas le reseau : ``ThreeDxClient`` et les endpoints ``admin`` sont
remplaces par des doubles dans l'espace de noms du module ``connection``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from threedx_cleaner.core import connection
from threedx_cleaner.models.profile import Profile


def _settings():
    from threedx_cleaner.credentials.settings_builder import build_settings

    return build_settings(
        Profile(
            name="t",
            deployment="on_prem",
            username="u@x",
            base_url="https://h",
        ),
        "pwd",
    )


@pytest.fixture
def fake_engine(monkeypatch):
    """Remplace ThreeDxClient + admin par des doubles configurables."""
    state = {
        "user": SimpleNamespace(
            login="nbonzani",
            id=42,
            full_name="Nicolas Bonzani",
            email="nb@x",
            super_user=False,
            enabled=True,
        ),
        "contexts": SimpleNamespace(
            contexts=[
                SimpleNamespace(name="Role.Org.Space", title="Space - Role"),
                SimpleNamespace(name="Role.Org.Space", title="doublon"),
                SimpleNamespace(name="Admin.Org.Space", title=""),
            ]
        ),
        "contexts_exc": None,
    }

    monkeypatch.setattr(connection, "ThreeDxClient", lambda settings: object())

    def _get_user(_client):
        return state["user"]

    def _list_ctx(_client):
        if state["contexts_exc"] is not None:
            raise state["contexts_exc"]
        return state["contexts"]

    monkeypatch.setattr(
        connection.admin, "get_current_user", _get_user, raising=True
    )
    monkeypatch.setattr(
        connection.admin, "list_security_contexts", _list_ctx, raising=True
    )
    return state


def test_who_am_i(fake_engine) -> None:
    who = connection.who_am_i(_settings())
    assert who.login == "nbonzani"
    assert who.internal_id == "42"
    assert who.deployment_mode == "on_prem"


def test_list_contexts_dedup_and_fallback_title(fake_engine) -> None:
    options = connection.list_security_contexts(_settings())
    # Doublon retire (2 entrees Role.Org.Space -> 1)
    assert [o.name for o in options] == ["Role.Org.Space", "Admin.Org.Space"]
    # title vide -> label retombe sur name
    assert options[1].label() == "Admin.Org.Space"


def test_probe_returns_identity_and_contexts(fake_engine) -> None:
    result = connection.probe(_settings())
    assert result.who.login == "nbonzani"
    assert result.contexts_error is None
    assert len(result.contexts) == 2


def test_probe_contexts_error_is_non_blocking(fake_engine) -> None:
    fake_engine["contexts_exc"] = RuntimeError("getallctx 500")
    result = connection.probe(_settings())
    # Connexion OK malgre l'echec des contextes
    assert result.who.login == "nbonzani"
    assert result.contexts == []
    assert "getallctx 500" in (result.contexts_error or "")

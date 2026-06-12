"""Tests du listing des collabspaces (moteur mocké, sans réseau)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from threedx_cleaner.core import collabspace_query


def _space(name):
    return SimpleNamespace(name=name)


def _list(items, *, nb_pages):
    return SimpleNamespace(items=items, nb_pages=nb_pages)


def test_single_page_sorted_dedup(monkeypatch) -> None:
    monkeypatch.setattr(
        collabspace_query.collabspaces,
        "list_collabspaces",
        lambda _c, **kw: _list([_space("B"), _space("A"), _space("A")], nb_pages=1),
        raising=True,
    )
    assert collabspace_query.list_space_names(object()) == ["A", "B"]


def test_follows_pages(monkeypatch) -> None:
    pages = [
        _list([_space("S1")], nb_pages=2),
        _list([_space("S2")], nb_pages=2),
    ]

    def fake(_c, **kw):
        return pages[kw["page"]]

    monkeypatch.setattr(
        collabspace_query.collabspaces, "list_collabspaces", fake, raising=True
    )
    assert collabspace_query.list_space_names(object()) == ["S1", "S2"]


def test_stops_on_empty_items(monkeypatch) -> None:
    monkeypatch.setattr(
        collabspace_query.collabspaces,
        "list_collabspaces",
        lambda _c, **kw: _list([], nb_pages=99),
        raising=True,
    )
    assert collabspace_query.list_space_names(object()) == []

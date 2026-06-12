"""Tests de la recherche filtrée F3 (moteur mocké, sans réseau)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from threedx_cleaner.core import document_query
from threedx_cleaner.core.document_query import SearchFilters


def _hit(**kw):
    base = dict(
        physical_id="PID",
        identifier="prd-1",
        type="VPMReference",
        title="Pièce",
        revision="A.1",
        status="In Work",
        owner="nbonzani",
        modified="2026-06-01",
        organization="Org",
        project="Proj",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _result(hits, *, nmatches, next_start=None, truncated=False, query="*"):
    return SimpleNamespace(
        hits=hits,
        nresults=len(hits),
        nmatches=nmatches,
        next_start=next_start,
        truncated=truncated,
        query=query,
    )


@pytest.fixture
def captured_calls(monkeypatch):
    calls: list[dict] = []

    def fake_search_advanced(_client, **kwargs):
        calls.append(kwargs)
        # Renvoie 1 hit par défaut (les tests de pagination overrident).
        return _result([_hit()], nmatches=1)

    monkeypatch.setattr(
        document_query.search, "search_advanced", fake_search_advanced, raising=True
    )
    return calls


def test_search_page_maps_hit_to_row(captured_calls) -> None:
    page = document_query.search_page(object(), SearchFilters())
    assert len(page.rows) == 1
    row = page.rows[0]
    assert row.physical_id == "PID"
    assert row.type == "VPMReference"
    assert row.key == "PID"
    assert row.size_bytes is None  # taille non résolue à ce stade


def test_filters_passed_through(captured_calls) -> None:
    filters = SearchFilters(
        query="suspension",
        types=["Document"],
        owner="nb",
        maturity="Released",
        modified_after="2026-01-01",
        modified_before="2026-12-31",
        page_size=10,
    )
    document_query.search_page(object(), filters, start=0)
    kw = captured_calls[-1]
    assert kw["query"] == "suspension"
    assert kw["types"] == ["Document"]
    assert kw["owner"] == "nb"
    assert kw["maturity"] == "Released"
    assert kw["limit"] == 10
    assert kw["extra_clauses"] is None


def test_collabspace_builds_extra_clause(captured_calls) -> None:
    document_query.search_page(object(), SearchFilters(collabspace="PersoNB"))
    kw = captured_calls[-1]
    assert kw["extra_clauses"] == ['[ds6w:collabspace]:"PersoNB"']


def test_collabspace_escapes_quotes(captured_calls) -> None:
    document_query.search_page(object(), SearchFilters(collabspace='a"b'))
    kw = captured_calls[-1]
    assert kw["extra_clauses"] == ['[ds6w:collabspace]:"a\\"b"']


def test_search_all_follows_cursor(monkeypatch) -> None:
    pages = [
        _result([_hit(physical_id="P1")], nmatches=2, next_start="cur1"),
        _result([_hit(physical_id="P2")], nmatches=2, next_start=None),
    ]
    seq = iter(pages)
    monkeypatch.setattr(
        document_query.search,
        "search_advanced",
        lambda _c, **kw: next(seq),
        raising=True,
    )
    agg = document_query.search_all(object(), SearchFilters())
    assert [r.physical_id for r in agg.rows] == ["P1", "P2"]
    assert agg.truncated is False
    assert agg.next_start is None


def test_search_all_stops_on_repeated_cursor(monkeypatch) -> None:
    # Curseur qui ne progresse pas → arrêt anti-boucle, truncated si reste.
    monkeypatch.setattr(
        document_query.search,
        "search_advanced",
        lambda _c, **kw: _result([_hit()], nmatches=99, next_start="same"),
        raising=True,
    )
    agg = document_query.search_all(object(), SearchFilters())
    # Curseur répété détecté à la 2e requête → arrêt anti-boucle (2 pages max).
    assert len(agg.rows) == 2
    assert agg.truncated is True


def test_search_all_respects_max_objects(monkeypatch) -> None:
    monkeypatch.setattr(
        document_query.search,
        "search_advanced",
        lambda _c, **kw: _result(
            [_hit(physical_id=f"P{kw['start']}")], nmatches=100, next_start=f"c{kw['start']}"
        ),
        raising=True,
    )
    agg = document_query.search_all(object(), SearchFilters(), max_objects=3)
    assert len(agg.rows) == 3
    assert agg.truncated is True

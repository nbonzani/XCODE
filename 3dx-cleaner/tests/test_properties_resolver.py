"""Tests du résolveur maturité + verrouillage (jalon 3, moteur mocké)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from threedx_cleaner.core.document_query import ObjectRow
from threedx_cleaner.core.properties_resolver import (
    NullPropertiesResolver,
    PropInfo,
    ReadAttributesPropertiesResolver,
    format_lock,
)


def _row(key: str) -> ObjectRow:
    return ObjectRow(
        physical_id=key, identifier=None, type="Document", title=None,
        revision=None, status=None, owner=None, modified=None,
        organization=None, project=None,
    )


class _FakeAttrObj:
    def __init__(self, pid, basic=None):
        self.physical_id = pid
        self._basic = basic or {}

    def basic_by_name(self, name):
        v = self._basic.get(name)
        return SimpleNamespace(value=v) if v is not None else None

    def attribute_by_name(self, name):
        return None


def _patch(monkeypatch, objs):
    from threedx_mcp.client.endpoints import attributes

    monkeypatch.setattr(
        attributes, "read_attributes",
        lambda _c, ids, **kw: SimpleNamespace(results=objs), raising=True,
    )


def test_null_resolver() -> None:
    assert NullPropertiesResolver().resolve([_row("A")]) == {"A": PropInfo()}


def test_maturity_and_lock(monkeypatch) -> None:
    _patch(monkeypatch, [
        _FakeAttrObj("A", basic={"current": ["En traitement"], "reservedby": ["nb"]}),
    ])
    out = ReadAttributesPropertiesResolver(object()).resolve([_row("A")])
    assert out["A"] == PropInfo(maturity="En traitement", lock="nb")


def test_maturity_without_lock_field(monkeypatch) -> None:
    _patch(monkeypatch, [_FakeAttrObj("A", basic={"current": ["Validé"]})])
    out = ReadAttributesPropertiesResolver(object()).resolve([_row("A")])
    assert out["A"].maturity == "Validé"
    assert out["A"].lock is None  # champ verrou absent → inconnu


def test_reserved_flag_false_is_free(monkeypatch) -> None:
    _patch(monkeypatch, [_FakeAttrObj("A", basic={"reserved": ["false"]})])
    out = ReadAttributesPropertiesResolver(object()).resolve([_row("A")])
    assert out["A"].lock == ""


def test_error_tolerated(monkeypatch) -> None:
    from threedx_mcp.client.endpoints import attributes

    def boom(_c, ids, **kw):
        raise RuntimeError("read down")

    monkeypatch.setattr(attributes, "read_attributes", boom, raising=True)
    assert ReadAttributesPropertiesResolver(object()).resolve([_row("A")]) == {
        "A": PropInfo()
    }


def test_cache_avoids_second_call(monkeypatch) -> None:
    from threedx_mcp.client.endpoints import attributes

    calls = {"n": 0}

    def counting(_c, ids, **kw):
        calls["n"] += 1
        return SimpleNamespace(results=[_FakeAttrObj("A", basic={"current": ["x"]})])

    monkeypatch.setattr(attributes, "read_attributes", counting, raising=True)
    resolver = ReadAttributesPropertiesResolver(object())
    resolver.resolve([_row("A")])
    resolver.resolve([_row("A")])
    assert calls["n"] == 1


@pytest.mark.parametrize(
    "state,expected",
    [(None, "—"), ("", "Libre"), ("?", "Verrouillé"), ("nb", "Verrouillé — nb")],
)
def test_format_lock(state, expected) -> None:
    assert format_lock(state) == expected

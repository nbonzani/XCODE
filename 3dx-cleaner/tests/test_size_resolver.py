"""Tests de l'architecture de résolution de taille (jalon 3)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from threedx_cleaner.core.document_query import ObjectRow
from threedx_cleaner.core.size_resolver import (
    ModelerFilesSizeResolver,
    NullSizeResolver,
    format_size,
)


def _row(key: str, *, type: str | None = "Document") -> ObjectRow:
    return ObjectRow(
        physical_id=key,
        identifier=None,
        type=type,
        title=None,
        revision=None,
        status=None,
        owner=None,
        modified=None,
        organization=None,
        project=None,
    )


def _file(size: int | None) -> SimpleNamespace:
    """Faux DocumentFile : le résolveur ne lit que ``size_bytes``."""
    return SimpleNamespace(size_bytes=size)


def test_null_resolver_returns_none_for_all() -> None:
    rows = [_row("A"), _row("B")]
    assert NullSizeResolver().resolve(rows) == {"A": None, "B": None}


def test_modeler_resolver_sums_files(monkeypatch: pytest.MonkeyPatch) -> None:
    from threedx_mcp.client.endpoints import documents

    monkeypatch.setattr(
        documents, "list_document_files", lambda _c, _pid: [_file(100), _file(23)]
    )
    resolver = ModelerFilesSizeResolver(client=object())
    assert resolver.resolve([_row("A")]) == {"A": 123}


def test_modeler_resolver_none_when_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from threedx_mcp.client.endpoints import documents

    monkeypatch.setattr(documents, "list_document_files", lambda _c, _pid: [])
    resolver = ModelerFilesSizeResolver(client=object())
    assert resolver.resolve([_row("A")]) == {"A": None}


def test_modeler_resolver_skips_non_document_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from threedx_mcp.client.endpoints import documents

    calls: list[str] = []

    def _spy(_c: object, pid: str) -> list[SimpleNamespace]:
        calls.append(pid)
        return [_file(50)]

    monkeypatch.setattr(documents, "list_document_files", _spy)
    resolver = ModelerFilesSizeResolver(client=object())
    # Type non documentaire → ni appel réseau, ni taille.
    assert resolver.resolve([_row("P", type="VPMReference")]) == {"P": None}
    assert calls == []


def test_modeler_resolver_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    from threedx_mcp.client.endpoints import documents

    calls: list[str] = []

    def _spy(_c: object, pid: str) -> list[SimpleNamespace]:
        calls.append(pid)
        return [_file(42)]

    monkeypatch.setattr(documents, "list_document_files", _spy)
    resolver = ModelerFilesSizeResolver(client=object())
    resolver.resolve([_row("A")])
    resolver.resolve([_row("A")])
    assert calls == ["A"]  # 2e appel servi par le cache


def test_modeler_resolver_tolerates_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from threedx_mcp.client.endpoints import documents

    def _boom(_c: object, _pid: str) -> list[SimpleNamespace]:
        raise RuntimeError("network down")

    monkeypatch.setattr(documents, "list_document_files", _boom)
    resolver = ModelerFilesSizeResolver(client=object())
    assert resolver.resolve([_row("A")]) == {"A": None}


@pytest.mark.parametrize(
    "size,expected",
    [
        (None, "—"),
        (-5, "—"),
        (0, "0 o"),
        (512, "512 o"),
        (1024, "1.0 Ko"),
        (1536, "1.5 Ko"),
        (1048576, "1.0 Mo"),
        (1073741824, "1.0 Go"),
    ],
)
def test_format_size(size, expected) -> None:
    assert format_size(size) == expected

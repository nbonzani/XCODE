"""Tests de l'architecture de résolution de taille (jalon 2)."""

from __future__ import annotations

import pytest

from threedx_cleaner.core.document_query import ObjectRow
from threedx_cleaner.core.size_resolver import (
    ModelerFilesSizeResolver,
    NullSizeResolver,
    SizeContractNotCaptured,
    format_size,
)


def _row(key: str) -> ObjectRow:
    return ObjectRow(
        physical_id=key,
        identifier=None,
        type=None,
        title=None,
        revision=None,
        status=None,
        owner=None,
        modified=None,
        organization=None,
        project=None,
    )


def test_null_resolver_returns_none_for_all() -> None:
    rows = [_row("A"), _row("B")]
    assert NullSizeResolver().resolve(rows) == {"A": None, "B": None}


def test_modeler_resolver_is_stub_until_har_captured() -> None:
    resolver = ModelerFilesSizeResolver(client=object())
    with pytest.raises(SizeContractNotCaptured):
        resolver.resolve([_row("A")])


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

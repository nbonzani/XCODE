"""Tests du pré-vol de suppression F5 (lecture seule, moteur mocké)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from threedx_cleaner.core import preflight
from threedx_cleaner.core.document_query import ObjectRow


def _row(pid="PID", type_="VPMReference"):
    return ObjectRow(
        physical_id=pid,
        identifier="prd-1",
        type=type_,
        title="Pièce",
        revision="A",
        status="In Work",
        owner="nb",
        modified="2026-06-01",
        organization="Org",
        project="Proj",
    )


def _client(mode="on_prem"):
    return SimpleNamespace(settings=SimpleNamespace(deployment_mode=mode))


@pytest.fixture
def onprem_engine(monkeypatch):
    monkeypatch.setattr(
        preflight.lifecycle_delete,
        "check_delete_access",
        lambda _c, ids: {i: True for i in ids},
        raising=True,
    )
    monkeypatch.setattr(
        preflight.lifecycle_delete,
        "get_delete_options",
        lambda _c, ids: [
            {
                "physicalid": i,
                "type": "VPMReference",
                "logical_delete": False,  # suppression physique
                "available_options": [{"key": "wholeStructure", "value": False}],
            }
            for i in ids
        ],
        raising=True,
    )
    monkeypatch.setattr(
        preflight.navigation,
        "get_relation_count",
        lambda _c, items: SimpleNamespace(where_used_count=lambda: 2),
        raising=True,
    )


def test_onprem_verdict(onprem_engine) -> None:
    verdicts = preflight.run_preflight(_client(), [_row()])
    v = verdicts[0]
    assert v.deletable is True
    assert v.physical_delete is True  # logical_delete False
    assert v.cascade_available is True
    assert v.where_used_count == 2
    assert v.has_dependents is True
    assert v.notes == []


def test_where_used_can_be_disabled(onprem_engine) -> None:
    verdicts = preflight.run_preflight(_client(), [_row()], with_where_used=False)
    assert verdicts[0].where_used_count is None


def test_cloud_dispatch(monkeypatch) -> None:
    called = {"cloud_access": False, "cloud_options": False}

    def cloud_access(ids):
        called["cloud_access"] = True
        return {i: True for i in ids}

    def cloud_options(_c, ids):
        called["cloud_options"] = True
        return [{"physicalid": i, "type": "Document", "logical_delete": False,
                 "available_options": []} for i in ids]

    monkeypatch.setattr(
        preflight.lifecycle_delete, "check_delete_access_cloud", cloud_access, raising=True
    )
    monkeypatch.setattr(
        preflight.lifecycle_delete, "get_delete_options_cloud", cloud_options, raising=True
    )
    monkeypatch.setattr(
        preflight.navigation,
        "get_relation_count",
        lambda _c, items: SimpleNamespace(where_used_count=lambda: 0),
        raising=True,
    )
    verdicts = preflight.run_preflight(_client("cloud"), [_row(type_="Document")])
    assert called["cloud_access"] and called["cloud_options"]
    assert verdicts[0].cascade_available is False
    assert verdicts[0].has_dependents is False


def test_partial_errors_become_notes(monkeypatch) -> None:
    def boom(_c, ids):
        raise RuntimeError("403")

    monkeypatch.setattr(preflight.lifecycle_delete, "check_delete_access", boom, raising=True)
    monkeypatch.setattr(
        preflight.lifecycle_delete, "get_delete_options",
        lambda _c, ids: [], raising=True,
    )
    monkeypatch.setattr(
        preflight.navigation,
        "get_relation_count",
        lambda _c, items: (_ for _ in ()).throw(RuntimeError("nav down")),
        raising=True,
    )
    verdicts = preflight.run_preflight(_client(), [_row()])
    v = verdicts[0]
    assert v.has_delete_access is None
    assert any("checkDeleteAccess" in n for n in v.notes)
    assert any("where-used" in n for n in v.notes)


def test_missing_physical_id_noted(onprem_engine) -> None:
    verdicts = preflight.run_preflight(_client(), [_row(pid=None)])
    v = verdicts[0]
    assert any("physical_id" in n for n in v.notes)

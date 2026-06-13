"""Tests du widget CheckableComboBox (pytest-qt)."""

from __future__ import annotations

from threedx_cleaner.ui.checkable_combo import CheckableComboBox


def test_set_items_and_check(qtbot) -> None:
    combo = CheckableComboBox("Tous")
    qtbot.addWidget(combo)
    combo.set_items(["A", "B", "C"])
    assert combo.checked_values() == []
    combo.set_checked(["A", "C"])
    assert combo.checked_values() == ["A", "C"]


def test_set_items_keeps_checked(qtbot) -> None:
    combo = CheckableComboBox()
    qtbot.addWidget(combo)
    combo.set_items(["A", "B"])
    combo.set_checked(["B"])
    combo.set_items(["A", "B", "C", "D"])  # keep_checked par défaut
    assert combo.checked_values() == ["B"]


def test_add_values_dedup(qtbot) -> None:
    combo = CheckableComboBox()
    qtbot.addWidget(combo)
    combo.set_items(["A"])
    combo.add_values(["A", "B", "B", "C"])
    texts = [combo._model.item(i).text() for i in range(combo._model.rowCount())]
    assert texts == ["A", "B", "C"]


def test_display_text(qtbot) -> None:
    combo = CheckableComboBox("Tous")
    qtbot.addWidget(combo)
    combo.set_items(["A", "B", "C"])
    assert combo.lineEdit().text() == ""  # placeholder « Tous » visible
    combo.set_checked(["A"])
    assert combo.lineEdit().text() == "A"
    combo.set_checked(["A", "B"])
    assert combo.lineEdit().text() == "2 sélectionnés"


def test_clear_checks(qtbot) -> None:
    combo = CheckableComboBox()
    qtbot.addWidget(combo)
    combo.set_items(["A", "B"])
    combo.set_checked(["A", "B"])
    combo.clear_checks()
    assert combo.checked_values() == []

"""Liste déroulante à cases à cocher (multi-sélection) réutilisable.

PyQt6 n'offre pas de combo multi-select natif. Ce widget enveloppe un
``QComboBox`` avec un modèle d'items cochables : la zone de texte (lecture
seule) résume la sélection (« Tous » si vide, la valeur si une seule, « N
sélectionnés » sinon), et le popup reste ouvert pendant qu'on coche/décoche.
"""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QComboBox, QWidget


class CheckableComboBox(QComboBox):
    """Combo à cases à cocher (multi-sélection)."""

    selectionChanged = pyqtSignal()

    def __init__(self, placeholder: str = "Tous", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._placeholder = placeholder
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText(placeholder)
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        # Intercepte les clics : ouvrir le popup depuis la zone texte, et
        # cocher/décocher sans refermer le popup (clic sur le viewport).
        self.lineEdit().installEventFilter(self)
        self.view().viewport().installEventFilter(self)

    # --- Interaction ---

    def eventFilter(self, obj: object, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseButtonRelease:
            if obj is self.lineEdit():
                self.showPopup()
                return True
            if obj is self.view().viewport():
                index = self.view().indexAt(event.position().toPoint())
                item = self._model.itemFromIndex(index)
                if item is not None:
                    checked = item.checkState() == Qt.CheckState.Checked
                    item.setCheckState(
                        Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked
                    )
                    self._update_text()
                    self.selectionChanged.emit()
                return True  # consomme → le popup reste ouvert
        return super().eventFilter(obj, event)

    # --- API ---

    def set_items(self, values: Iterable[str], *, keep_checked: bool = True) -> None:
        """Remplace la liste des valeurs (conserve les cochées par défaut)."""
        checked = set(self.checked_values()) if keep_checked else set()
        self._model.clear()
        for value in values:
            self._add_item(value, value in checked)
        self._update_text()

    def add_values(self, values: Iterable[str]) -> None:
        """Ajoute des valeurs absentes (sans toucher aux cases existantes)."""
        existing = {
            self._model.item(i).text() for i in range(self._model.rowCount())
        }
        added = False
        for value in values:
            if value and value not in existing:
                self._add_item(value, checked=False)
                existing.add(value)
                added = True
        if added:
            self._update_text()

    def checked_values(self) -> list[str]:
        """Retourne les valeurs cochées (ordre du modèle)."""
        out: list[str] = []
        for i in range(self._model.rowCount()):
            item = self._model.item(i)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                out.append(item.text())
        return out

    def set_checked(self, values: Iterable[str]) -> None:
        """Force l'état coché sur les valeurs données."""
        want = set(values)
        for i in range(self._model.rowCount()):
            item = self._model.item(i)
            if item is not None:
                item.setCheckState(
                    Qt.CheckState.Checked if item.text() in want else Qt.CheckState.Unchecked
                )
        self._update_text()

    def clear_checks(self) -> None:
        """Décoche tout."""
        self.set_checked([])

    # --- Interne ---

    def _add_item(self, text: str, checked: bool) -> None:
        item = QStandardItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked,
            Qt.ItemDataRole.CheckStateRole,
        )
        self._model.appendRow(item)

    def _update_text(self) -> None:
        checked = self.checked_values()
        if not checked:
            text = ""  # vide → le placeholder « Tous » s'affiche
        elif len(checked) == 1:
            text = checked[0]
        else:
            text = f"{len(checked)} sélectionnés"
        self.lineEdit().setText(text)

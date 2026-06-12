"""F3 — panneau de recherche filtrée + tableau à cases (lecture seule, jalon 2).

Affiche un formulaire de filtres (texte, types, propriétaire, maturité, dates,
collabspace), lance la recherche via ``core.document_query`` dans un ``QThread``
worker, et présente les résultats dans un tableau à cases avec pagination et
récapitulatif de sélection. **Aucune action d'écriture** : ce panneau ne fait
que lire et sélectionner — la sélection sera consommée par les jalons suivants
(normalisation, pré-vol, purge).

La colonne « Taille » est présente mais affiche « — » tant que le contrat REST
de taille n'est pas capturé (cf. :mod:`threedx_cleaner.core.size_resolver`).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from threedx_mcp.client.session import ThreeDxClient
from threedx_mcp.config import Settings

from threedx_cleaner.core import collabspace_query, document_query
from threedx_cleaner.core.document_query import ObjectRow, SearchFilters, SearchPage
from threedx_cleaner.core.size_resolver import format_size

#: En-têtes des colonnes de données (hors colonne 0 = case à cocher).
_COLUMNS = (
    "Type",
    "Identifiant",
    "Titre",
    "Rév.",
    "Statut",
    "Propriétaire",
    "Modifié",
    "Taille",
)


class _SearchWorker(QThread):
    """Exécute une recherche (un batch ou exhaustive) hors thread UI."""

    page_ready = pyqtSignal(object)  # SearchPage
    failed = pyqtSignal(str)

    def __init__(
        self,
        client: ThreeDxClient,
        filters: SearchFilters,
        *,
        start: int | str,
        exhaustive: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._filters = filters
        self._start = start
        self._exhaustive = exhaustive

    def run(self) -> None:  # noqa: D102
        try:
            if self._exhaustive:
                page = document_query.search_all(self._client, self._filters)
            else:
                page = document_query.search_page(
                    self._client, self._filters, start=self._start
                )
        except Exception as exc:  # noqa: BLE001 — tout motif rapporté à l'UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.page_ready.emit(page)


class _CollabspacesWorker(QThread):
    """Récupère la liste des collabspaces (pour le filtre) hors thread UI."""

    ready = pyqtSignal(list)  # list[str]
    failed = pyqtSignal(str)

    def __init__(self, client: ThreeDxClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client = client

    def run(self) -> None:  # noqa: D102
        try:
            names = collabspace_query.list_space_names(self._client)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.ready.emit(names)


class SearchPanel(QWidget):
    """Panneau F3 : filtres + tableau à cases (lecture seule)."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client = ThreeDxClient(settings)
        self._rows: list[ObjectRow] = []
        self._next_start: str | None = None
        self._search_worker: _SearchWorker | None = None
        self._cs_worker: _CollabspacesWorker | None = None

        root = QVBoxLayout(self)
        root.addWidget(self._build_filters())
        root.addWidget(self._build_table(), stretch=1)
        root.addLayout(self._build_footer())

        self._set_status("Prêt. Renseignez des filtres puis lancez la recherche.")
        self._load_collabspaces()

    # --- Construction UI ---

    def _build_filters(self) -> QGroupBox:
        box = QGroupBox("Filtres de recherche (lecture seule)")
        form = QFormLayout(box)

        self._query = QLineEdit("*")
        self._query.setPlaceholderText("Texte libre ou UQL (* = tout)")
        self._types = QLineEdit()
        self._types.setPlaceholderText("Types séparés par des virgules (ex. VPMReference, Document)")
        self._owner = QLineEdit()
        self._owner.setPlaceholderText("Login propriétaire (optionnel)")
        self._maturity = QLineEdit()
        self._maturity.setPlaceholderText("Statut/maturité (ex. In Work, Released)")
        self._modified_after = QLineEdit()
        self._modified_after.setPlaceholderText("Modifié après — ISO (2026-01-01)")
        self._modified_before = QLineEdit()
        self._modified_before.setPlaceholderText("Modifié avant — ISO (2026-12-31)")
        self._collabspace = QComboBox()
        self._collabspace.setEditable(True)
        self._collabspace.addItem("")  # vide = pas de filtre collabspace
        self._collabspace.lineEdit().setPlaceholderText("Collaborative space (optionnel)")
        self._page_size = QSpinBox()
        self._page_size.setRange(1, 500)
        self._page_size.setValue(50)

        form.addRow("Texte", self._query)
        form.addRow("Types", self._types)
        form.addRow("Propriétaire", self._owner)
        form.addRow("Maturité", self._maturity)
        form.addRow("Modifié après", self._modified_after)
        form.addRow("Modifié avant", self._modified_before)
        form.addRow("Collabspace", self._collabspace)
        form.addRow("Taille de page", self._page_size)

        actions = QHBoxLayout()
        self._search_btn = QPushButton("Rechercher")
        self._search_btn.clicked.connect(self._on_search)
        self._enumerate_btn = QPushButton("Tout énumérer")
        self._enumerate_btn.setToolTip(
            "Rapatrie toutes les pages (borné à "
            f"{document_query.MAX_ENUMERATION} objets)."
        )
        self._enumerate_btn.clicked.connect(self._on_enumerate)
        actions.addWidget(self._search_btn)
        actions.addWidget(self._enumerate_btn)
        actions.addStretch(1)
        form.addRow("", self._wrap(actions))
        return box

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget(0, len(_COLUMNS) + 1)
        self._table.setHorizontalHeaderLabels(["", *_COLUMNS])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.itemChanged.connect(self._on_item_changed)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Titre
        return self._table

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        self._select_all_btn = QPushButton("Tout cocher")
        self._select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        self._select_none_btn = QPushButton("Tout décocher")
        self._select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        self._more_btn = QPushButton("Charger la suite")
        self._more_btn.setEnabled(False)
        self._more_btn.clicked.connect(self._on_load_more)
        footer.addWidget(self._select_all_btn)
        footer.addWidget(self._select_none_btn)
        footer.addWidget(self._more_btn)
        footer.addStretch(1)
        self._status = QLabel("")
        footer.addWidget(self._status)
        return footer

    @staticmethod
    def _wrap(layout: QHBoxLayout) -> QWidget:
        w = QWidget()
        w.setLayout(layout)
        return w

    # --- Filtres ---

    def _current_filters(self) -> SearchFilters:
        types_raw = [t.strip() for t in self._types.text().split(",") if t.strip()]
        return SearchFilters(
            query=self._query.text().strip() or "*",
            types=types_raw or None,
            owner=self._owner.text().strip() or None,
            maturity=self._maturity.text().strip() or None,
            modified_after=self._modified_after.text().strip() or None,
            modified_before=self._modified_before.text().strip() or None,
            collabspace=self._collabspace.currentText().strip() or None,
            page_size=self._page_size.value(),
        )

    # --- Recherche ---

    def _on_search(self) -> None:
        self._start_search(start=0, exhaustive=False, reset=True)

    def _on_enumerate(self) -> None:
        self._start_search(start=0, exhaustive=True, reset=True)

    def _on_load_more(self) -> None:
        if self._next_start is None:
            return
        self._start_search(start=self._next_start, exhaustive=False, reset=False)

    def _start_search(self, *, start: int | str, exhaustive: bool, reset: bool) -> None:
        if self._search_worker is not None and self._search_worker.isRunning():
            return
        if reset:
            self._clear_table()
        self._set_busy(True)
        self._set_status("Recherche en cours…")
        self._search_worker = _SearchWorker(
            self._client,
            self._current_filters(),
            start=start,
            exhaustive=exhaustive,
            parent=self,
        )
        self._search_worker.page_ready.connect(lambda page: self._on_page(page, reset))
        self._search_worker.failed.connect(self._on_search_failed)
        self._search_worker.finished.connect(lambda: self._set_busy(False))
        self._search_worker.start()

    def _on_page(self, page: SearchPage, reset: bool) -> None:
        if reset:
            self._clear_table()
        self._append_rows(page.rows)
        self._next_start = page.next_start
        self._more_btn.setEnabled(bool(page.next_start))
        self._update_status(page)

    def _on_search_failed(self, message: str) -> None:
        self._set_status(f"ÉCHEC — {message}", error=True)

    # --- Tableau ---

    def _clear_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        self._rows = []
        self._table.blockSignals(False)

    def _append_rows(self, rows: list[ObjectRow]) -> None:
        self._table.blockSignals(True)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            check.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(r, 0, check)
            values = (
                row.type or "",
                row.identifier or "",
                row.title or "",
                row.revision or "",
                row.status or "",
                row.owner or "",
                row.modified or "",
                format_size(row.size_bytes),
            )
            for c, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self._table.setItem(r, c, item)
            self._rows.append(row)
        self._table.blockSignals(False)

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item is not None:
                item.setCheckState(state)
        self._table.blockSignals(False)
        self._refresh_selection_count()

    def _on_item_changed(self, _item: QTableWidgetItem) -> None:
        self._refresh_selection_count()

    def selected_rows(self) -> list[ObjectRow]:
        """Retourne les lignes cochées (consommées par les jalons suivants)."""
        out: list[ObjectRow] = []
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                if r < len(self._rows):
                    out.append(self._rows[r])
        return out

    # --- Collabspaces ---

    def _load_collabspaces(self) -> None:
        if self._cs_worker is not None and self._cs_worker.isRunning():
            return
        self._cs_worker = _CollabspacesWorker(self._client, self)
        self._cs_worker.ready.connect(self._on_collabspaces)
        self._cs_worker.failed.connect(lambda _m: None)  # silencieux : filtre optionnel
        self._cs_worker.start()

    def _on_collabspaces(self, names: list[str]) -> None:
        current = self._collabspace.currentText()
        self._collabspace.blockSignals(True)
        self._collabspace.clear()
        self._collabspace.addItem("")
        self._collabspace.addItems(names)
        self._collabspace.setCurrentText(current)
        self._collabspace.blockSignals(False)

    # --- Statut ---

    def _selected_count(self) -> int:
        return sum(
            1
            for r in range(self._table.rowCount())
            if (it := self._table.item(r, 0)) is not None
            and it.checkState() == Qt.CheckState.Checked
        )

    def _refresh_selection_count(self) -> None:
        self._status.setText(
            f"{self._table.rowCount()} objet(s) affiché(s) · "
            f"{self._selected_count()} coché(s)."
        )

    def _update_status(self, page: SearchPage) -> None:
        shown = self._table.rowCount()
        more = " · pages restantes" if page.next_start else ""
        self._set_status(
            f"{shown} objet(s) affiché(s) / {page.nmatches} match(es) serveur"
            f"{more} · {self._selected_count()} coché(s)."
        )

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self._status.setText(text)
        self._status.setStyleSheet("color: #b00020;" if error else "")

    def _set_busy(self, busy: bool) -> None:
        self._search_btn.setEnabled(not busy)
        self._enumerate_btn.setEnabled(not busy)
        if busy:
            self._more_btn.setEnabled(False)

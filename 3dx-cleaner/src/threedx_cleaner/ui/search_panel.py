"""F3 — panneau de recherche filtrée + tableau à cases (lecture seule, jalon 2).

Affiche un formulaire de filtres (texte, types, propriétaire, maturité, dates,
collabspace), lance la recherche via ``core.document_query`` dans un ``QThread``
worker, et présente les résultats dans un tableau à cases avec pagination et
récapitulatif de sélection. **Aucune action d'écriture** : ce panneau ne fait
que lire et sélectionner — la sélection sera consommée par les jalons suivants
(normalisation, pré-vol, purge).

La colonne « Taille » est renseignée à la demande, après chaque page, par un
:class:`~threedx_cleaner.core.size_resolver.ModelerFilesSizeResolver` exécuté
dans un worker Qt (appels réseau ``/files`` hors thread UI). Elle affiche « — »
pour un objet sans fichier ou de type non documentaire.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
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
from threedx_cleaner.core.properties_resolver import (
    PropertiesResolver,
    PropInfo,
    ReadAttributesPropertiesResolver,
    format_lock,
)
from threedx_cleaner.core.size_resolver import (
    ModelerFilesSizeResolver,
    SizeResolver,
    format_size,
)
from threedx_cleaner.ui.checkable_combo import CheckableComboBox

#: Maturités usuelles proposées d'emblée (NLS FR + EN), complétées par les
#: valeurs réellement rencontrées dans les résultats.
_DEFAULT_MATURITIES = (
    "In Work", "Frozen", "Released", "Obsolete",
    "En traitement", "Gelé", "Validé", "Obsolète",
)

#: En-têtes des colonnes de données (hors colonne 0 = case à cocher).
_COLUMNS = (
    "Type",
    "Identifiant",
    "Titre",
    "Rév.",
    "Maturité",
    "Verrouillage",
    "Propriétaire",
    "Modifié",
    "Taille",
)

#: Largeurs initiales (px) par colonne de données (clé = index dans _COLUMNS).
_COLUMN_WIDTHS = (110, 150, 240, 55, 110, 130, 130, 140, 90)


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


class _SizeWorker(QThread):
    """Résout la taille d'un lot de lignes hors thread UI (appels ``/files``)."""

    resolved = pyqtSignal(dict)  # {row.key: size_bytes | None}

    def __init__(
        self,
        resolver: SizeResolver,
        rows: list[ObjectRow],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._resolver = resolver
        self._rows = rows

    def run(self) -> None:  # noqa: D102
        try:
            result = self._resolver.resolve(self._rows)
        except Exception:  # noqa: BLE001 — résolution best-effort, non bloquante
            return
        self.resolved.emit(result)


class _PropsWorker(QThread):
    """Résout maturité + verrouillage d'un lot de lignes hors thread UI."""

    resolved = pyqtSignal(dict)  # {row.key: PropInfo}

    def __init__(
        self,
        resolver: PropertiesResolver,
        rows: list[ObjectRow],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._resolver = resolver
        self._rows = rows

    def run(self) -> None:  # noqa: D102
        try:
            result = self._resolver.resolve(self._rows)
        except Exception:  # noqa: BLE001 — résolution best-effort, non bloquante
            return
        self.resolved.emit(result)


class SearchPanel(QWidget):
    """Panneau F3 : filtres + tableau à cases (lecture seule)."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client = ThreeDxClient(settings)
        self._rows: list[ObjectRow] = []
        self._next_start: str | None = None
        self._search_worker: _SearchWorker | None = None
        self._cs_worker: _CollabspacesWorker | None = None
        # Résolveur de taille réel (endpoint /files) — cache partagé entre pages.
        self._size_resolver: SizeResolver = ModelerFilesSizeResolver(self._client)
        self._size_workers: list[_SizeWorker] = []
        # Résolveur maturité + verrouillage (read_attributes par lot) — cache partagé.
        self._props_resolver: PropertiesResolver = ReadAttributesPropertiesResolver(
            self._client
        )
        self._props_workers: list[_PropsWorker] = []

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
        # Combos à cocher (multi-sélection). Type/Propriétaire s'enrichissent au
        # fil des résultats ; Maturité est pré-remplie ; Collabspace est chargé
        # depuis le serveur. « Tous » (vide) = pas de filtre.
        self._types = CheckableComboBox("Tous les types")
        self._owners = CheckableComboBox("Tous les propriétaires")
        self._maturities = CheckableComboBox("Toutes les maturités")
        self._maturities.set_items(_DEFAULT_MATURITIES)
        self._collabspaces = CheckableComboBox("Tous les espaces")
        self._modified_after = QLineEdit()
        self._modified_after.setPlaceholderText("Modifié après — ISO (2026-01-01)")
        self._modified_before = QLineEdit()
        self._modified_before.setPlaceholderText("Modifié avant — ISO (2026-12-31)")
        self._page_size = QSpinBox()
        self._page_size.setRange(1, 500)
        self._page_size.setValue(50)

        form.addRow("Texte", self._query)
        form.addRow("Types", self._types)
        form.addRow("Propriétaires", self._owners)
        form.addRow("Maturités", self._maturities)
        form.addRow("Modifié après", self._modified_after)
        form.addRow("Modifié avant", self._modified_before)
        form.addRow("Collabspaces", self._collabspaces)
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
        # Toutes les colonnes redimensionnables librement (drag) avec largeur
        # initiale fixe. On évite le mode Stretch (qui rend le drag des
        # colonnes voisines erratique) ; un scroll horizontal apparaît au besoin.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 30)
        for idx, width in enumerate(_COLUMN_WIDTHS, start=1):
            self._table.setColumnWidth(idx, width)
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
        return SearchFilters(
            query=self._query.text().strip() or "*",
            types=self._types.checked_values() or None,
            owners=self._owners.checked_values() or None,
            maturities=self._maturities.checked_values() or None,
            collabspaces=self._collabspaces.checked_values() or None,
            modified_after=self._modified_after.text().strip() or None,
            modified_before=self._modified_before.text().strip() or None,
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
        self._accumulate_facets(page.rows)
        self._resolve_sizes(page.rows)
        self._resolve_props(page.rows)

    def _accumulate_facets(self, rows: list[ObjectRow]) -> None:
        """Enrichit les combos Type/Propriétaire/Maturité avec les valeurs vues."""
        self._types.add_values(sorted({r.type for r in rows if r.type}))
        self._owners.add_values(sorted({r.owner for r in rows if r.owner}))
        self._maturities.add_values(sorted({r.status for r in rows if r.status}))

    def _on_search_failed(self, message: str) -> None:
        self._set_status(f"ÉCHEC — {message}", error=True)

    # --- Résolution de taille (colonne « Taille ») ---

    def _resolve_sizes(self, rows: list[ObjectRow]) -> None:
        """Lance la résolution de taille des lignes ``rows`` hors thread UI."""
        targets = [r for r in rows if r.physical_id]
        if not targets:
            return
        worker = _SizeWorker(self._size_resolver, targets, self)
        worker.resolved.connect(self._on_sizes_resolved)
        worker.finished.connect(lambda: self._size_workers.remove(worker)
                                if worker in self._size_workers else None)
        self._size_workers.append(worker)
        worker.start()

    def _on_sizes_resolved(self, sizes: dict[str, int | None]) -> None:
        """Met à jour la colonne « Taille » pour les clés résolues."""
        size_col = len(_COLUMNS)  # dernière colonne (Taille), après la case (col 0)
        self._table.blockSignals(True)
        for r, row in enumerate(self._rows):
            if r >= self._table.rowCount():
                break
            if row.key in sizes:
                item = self._table.item(r, size_col)
                if item is not None:
                    item.setText(format_size(sizes[row.key]))
        self._table.blockSignals(False)

    # --- Résolution maturité + verrouillage (read_attributes par lot) ---

    def _resolve_props(self, rows: list[ObjectRow]) -> None:
        """Lance la résolution maturité + verrouillage hors thread UI."""
        targets = [r for r in rows if r.physical_id]
        if not targets:
            return
        worker = _PropsWorker(self._props_resolver, targets, self)
        worker.resolved.connect(self._on_props_resolved)
        worker.finished.connect(lambda: self._props_workers.remove(worker)
                                if worker in self._props_workers else None)
        self._props_workers.append(worker)
        worker.start()

    def _on_props_resolved(self, props: dict[str, PropInfo]) -> None:
        """Remplit les colonnes « Maturité » et « Verrouillage »."""
        mat_col = _COLUMNS.index("Maturité") + 1   # +1 : case à cocher en col 0
        lock_col = _COLUMNS.index("Verrouillage") + 1
        new_maturities: set[str] = set()
        self._table.blockSignals(True)
        for r, row in enumerate(self._rows):
            if r >= self._table.rowCount():
                break
            info = props.get(row.key)
            if info is None:
                continue
            if info.maturity:
                item = self._table.item(r, mat_col)
                # ne remplace que si la recherche n'avait rien fourni (vide ou « … »)
                if item is not None and item.text().strip() in ("", "…"):
                    item.setText(info.maturity)
                new_maturities.add(info.maturity)
            lock_item = self._table.item(r, lock_col)
            if lock_item is not None:
                lock_item.setText(format_lock(info.lock))
        self._table.blockSignals(False)
        if new_maturities:
            self._maturities.add_values(sorted(new_maturities))

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
                row.status or "…",      # Maturité (ds6w:status ; sinon résolue)
                "…",                    # Verrouillage — résolu en tâche de fond
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
        self._collabspaces.set_items(names)

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

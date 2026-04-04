from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont

# Couleurs de surlignage par type
COLOR_LIVE    = QColor("#DDEEFF")   # Bleu clair
COLOR_VOD     = QColor("#DDFFD8")   # Vert clair
COLOR_SERIES  = QColor("#FFF0CC")   # Orange clair
COLOR_UNKNOWN = QColor("#F5F5F5")   # Gris très clair

# Définition des colonnes (titre, clé dans le dict, largeur initiale)
COLUMNS = [
    ("Nom",       "name",         350),
    ("Groupe",    "group",        250),
    ("Type",      "content_type", 80),
    ("Qualité",   "quality",      80),
    ("Score",     "rating",       70),
    ("URL",       "url",          400),
]

class ChannelTable(QTableWidget):
    """
    Tableau d'affichage des entrées M3U.
    Émet entry_double_clicked(dict) au double-clic sur une ligne.
    """
    entry_double_clicked = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []

        # Police plus grande
        font = QFont()
        font.setPointSize(11)
        self.setFont(font)

        # En-têtes en gras
        header_font = QFont()
        header_font.setPointSize(11)
        header_font.setBold(True)
        self.horizontalHeader().setFont(header_font)

        # Hauteur des lignes
        self.verticalHeader().setDefaultSectionSize(28)

        # Configuration générale du tableau
        self.setColumnCount(len(COLUMNS))
        self.setHorizontalHeaderLabels([c[0] for c in COLUMNS])
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.setWordWrap(False)

        # Toutes les colonnes sont redimensionnables par l'utilisateur
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        for i, (_, _, width) in enumerate(COLUMNS):
            self.setColumnWidth(i, width)
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)

        # Ascenseur horizontal
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Double-clic sur une ligne
        self.cellDoubleClicked.connect(self._on_double_click)

    def _on_double_click(self, row, col):
        if 0 <= row < len(self._entries):
            self.entry_double_clicked.emit(self._entries[row])

    def _color_for_type(self, content_type: str) -> QColor:
        return {
            "live":   COLOR_LIVE,
            "vod":    COLOR_VOD,
            "series": COLOR_SERIES,
        }.get(content_type, COLOR_UNKNOWN)

    def _format_rating(self, rating: str) -> str:
        try:
            val = float(rating)
            stars = round(val / 2)
            return "★" * stars + "☆" * (5 - stars)
        except (ValueError, TypeError):
            return ""

    def populate(self, entries: list):
        """Remplit le tableau avec la liste d'entrées fournie."""
        self._entries = entries

        self.setUpdatesEnabled(False)
        self.setSortingEnabled(False)
        self.clearContents()
        self.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            color = self._color_for_type(entry.get("content_type", ""))
            brush = QBrush(color)

            values = [
                entry.get("name", ""),
                entry.get("group", ""),
                entry.get("content_type", ""),
                entry.get("quality", ""),
                self._format_rating(entry.get("rating", "")),
                entry.get("url", ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setBackground(brush)
                self.setItem(row, col, item)

        self.setSortingEnabled(True)
        self.setUpdatesEnabled(True)

    def get_selected_entries(self) -> list:
        """Retourne la liste des entrées sélectionnées par l'utilisateur."""
        rows = set(idx.row() for idx in self.selectedIndexes())
        return [self._entries[r] for r in sorted(rows) if r < len(self._entries)]

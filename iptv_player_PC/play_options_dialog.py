"""
play_options_dialog.py - Dialogue de sélection du mode de lecture.

Affiché uniquement lorsque l'utilisateur clique sur un FILM.
Propose deux actions :
  1. Voir sur ce PC (plein écran)
  2. Télécharger le film en local

Note : l'option "écran secondaire" a été retirée car sous Windows,
activer un second écran désactive l'affichage principal (mode "Second
écran uniquement"), ce qui rend l'option inutilisable dans ce contexte.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QWidget, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QFont


class _OptionButton(QWidget):
    """
    Bouton d'option personnalisé avec icône, titre et description.
    Émet clicked() lorsqu'il est pressé.
    """
    clicked = pyqtSignal()

    def __init__(self, icon: str, title: str, description: str,
                 enabled: bool = True, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled
                       else Qt.CursorShape.ForbiddenCursor)
        self._enabled = enabled

        base_bg   = "#1e1e38" if enabled else "#181828"
        base_text = "white"   if enabled else "#555"
        desc_text = "#aaa"    if enabled else "#444"

        self.setStyleSheet(f"""
            _OptionButton {{
                background-color: {base_bg};
                border: 1px solid {"#3a3a5a" if enabled else "#252535"};
                border-radius: 8px;
            }}
            _OptionButton:hover {{
                border-color: {"#2196F3" if enabled else "#252535"};
                background-color: {"#252550" if enabled else "#181828"};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)

        # Icône
        lbl_icon = QLabel(icon)
        lbl_icon.setStyleSheet(f"font-size: 28px; color: {'white' if enabled else '#444'};")
        lbl_icon.setFixedWidth(40)
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_icon)

        # Texte
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {base_text}; font-size: 14px; font-weight: bold;")
        text_col.addWidget(lbl_title)

        lbl_desc = QLabel(description)
        lbl_desc.setStyleSheet(f"color: {desc_text}; font-size: 11px;")
        text_col.addWidget(lbl_desc)

        layout.addLayout(text_col)
        layout.addStretch()

        if not enabled:
            lbl_unavail = QLabel("Non disponible")
            lbl_unavail.setStyleSheet("color: #444; font-size: 10px; font-style: italic;")
            layout.addWidget(lbl_unavail)

    def mousePressEvent(self, event):
        if self._enabled and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class PlayOptionsDialog(QDialog):
    """
    Dialogue de sélection du mode de lecture / téléchargement.

    Signals émis (un seul est émis selon le choix) :
        play_on_screen(int)  : 0 = écran principal, 1 = écran secondaire
        download()           : lancer le téléchargement
    """

    play_on_screen = pyqtSignal(int)
    download       = pyqtSignal()

    def __init__(self, item_data: dict, content_type: str = "movie", parent=None):
        """
        Args:
            item_data    : dict du film ou de la série (depuis le cache).
            content_type : "movie" ou "series".
        """
        super().__init__(parent)
        self.item_data    = item_data
        self.content_type = content_type

        self.setWindowTitle("Que souhaitez-vous faire ?")
        self.setModal(True)
        self.setFixedWidth(500)

        self.setStyleSheet("""
            QDialog { background-color: #0f0f1a; color: white; }
            QLabel  { color: white; }
        """)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ---- En-tête : titre + métadonnées ----
        header = QWidget()
        header.setStyleSheet(
            "background-color: #1a1a2e; border-radius: 8px; padding: 4px;"
        )
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(14, 10, 14, 10)
        hlay.setSpacing(14)

        # Poster local si disponible
        cover_local = self.item_data.get("cover_local", "")
        if cover_local:
            pixmap = QPixmap(cover_local)
            if not pixmap.isNull():
                lbl_cover = QLabel()
                lbl_cover.setFixedSize(52, 72)
                lbl_cover.setPixmap(
                    pixmap.scaled(52, 72,
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                )
                lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hlay.addWidget(lbl_cover)

        # Infos textuelles
        info_col = QVBoxLayout()
        info_col.setSpacing(4)

        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        lbl_name = QLabel(self.item_data.get("name", ""))
        lbl_name.setFont(title_font)
        lbl_name.setWordWrap(True)
        info_col.addWidget(lbl_name)

        meta = []
        if self.item_data.get("category_name"):
            meta.append(self.item_data["category_name"])
        if self.item_data.get("rating"):
            try:
                meta.append(f"⭐ {float(self.item_data['rating']):.1f}")
            except (ValueError, TypeError):
                pass
        if meta:
            lbl_meta = QLabel("  ·  ".join(meta))
            lbl_meta.setStyleSheet("color: #888; font-size: 12px;")
            info_col.addWidget(lbl_meta)

        hlay.addLayout(info_col)
        layout.addWidget(header)

        # ---- Titre section ----
        lbl_section = QLabel("Choisissez une action :")
        lbl_section.setStyleSheet("color: #7eb8f7; font-size: 13px; font-weight: bold;")
        layout.addWidget(lbl_section)

        # ---- Option 1 : Lire sur ce PC ----
        btn_primary = _OptionButton(
            icon        = "🖥️",
            title       = "Voir sur ce PC",
            description = "Plein écran, lecture immédiate",
            enabled     = True
        )
        btn_primary.clicked.connect(self._on_primary)
        layout.addWidget(btn_primary)

        # ---- Option 2 : Télécharger ----
        btn_download = _OptionButton(
            icon        = "⬇️",
            title       = "Télécharger le film",
            description = "Sauvegarder dans Vidéos\\IPTVPlayer pour lecture hors-ligne",
            enabled     = True
        )
        btn_download.clicked.connect(self._on_download)
        layout.addWidget(btn_download)

        # ---- Bouton Annuler ----
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2a2a44;")
        layout.addWidget(sep)

        btn_cancel = QPushButton("Annuler")
        btn_cancel.setStyleSheet("""
            QPushButton { background-color: #1e1e38; color: #aaa;
                          border: 1px solid #3a3a5a; border-radius: 4px;
                          padding: 8px; font-size: 13px; }
            QPushButton:hover { background-color: #2a2a50; color: white; }
        """)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

    # ------------------------------------------------------------------ #
    #  Slots                                                                #
    # ------------------------------------------------------------------ #

    def _on_primary(self):
        self.play_on_screen.emit(0)
        self.accept()

    def _on_download(self):
        self.download.emit()
        self.accept()

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QFont


class LoadingOverlay(QWidget):
    """Overlay semi-transparent centré sur la fenêtre parente,
    affichant la progression du chargement M3U en plusieurs phases."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # ── Panneau central (carte blanche) ──────────────────────
        self._card = QWidget(self)
        self._card.setFixedSize(420, 200)
        self._card.setStyleSheet(
            "QWidget {"
            "  background-color: white;"
            "  border-radius: 12px;"
            "  border: 1px solid #BDBDBD;"
            "}"
        )

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(12)

        # Titre de la phase
        self._lbl_phase = QLabel("Chargement en cours…")
        self._lbl_phase.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font_phase = QFont()
        font_phase.setPointSize(13)
        font_phase.setBold(True)
        self._lbl_phase.setFont(font_phase)
        self._lbl_phase.setStyleSheet("color: #1565C0; border: none;")
        card_layout.addWidget(self._lbl_phase)

        # Barre de progression
        self._progress = QProgressBar()
        self._progress.setFixedHeight(18)
        self._progress.setRange(0, 0)  # mode indéterminé par défaut
        self._progress.setTextVisible(True)
        self._progress.setStyleSheet(
            "QProgressBar {"
            "  border: 1px solid #E0E0E0;"
            "  border-radius: 9px;"
            "  background-color: #F5F5F5;"
            "  text-align: center;"
            "  font-size: 11px;"
            "  color: #616161;"
            "}"
            "QProgressBar::chunk {"
            "  background-color: #1565C0;"
            "  border-radius: 8px;"
            "}"
        )
        card_layout.addWidget(self._progress)

        # Détail texte
        self._lbl_detail = QLabel("")
        self._lbl_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_detail.setStyleSheet(
            "color: #757575; font-size: 11px; border: none;"
        )
        self._lbl_detail.setWordWrap(True)
        card_layout.addWidget(self._lbl_detail)

        card_layout.addStretch()

        self.hide()

    # ── API publique ─────────────────────────────────────────────
    def show_phase(self, phase_text: str, detail: str = "",
                   value: int = -1, maximum: int = 0):
        """Met à jour la phase affichée.

        value=-1 → mode indéterminé (barre animée).
        value>=0 → progression déterminée sur maximum.
        """
        self._lbl_phase.setText(phase_text)
        self._lbl_detail.setText(detail)

        if value < 0:
            self._progress.setRange(0, 0)
        else:
            self._progress.setRange(0, maximum)
            self._progress.setValue(value)

        if not self.isVisible():
            self._reposition()
            self.show()
            self.raise_()

    def update_progress(self, value: int, maximum: int, detail: str = ""):
        """Met à jour la progression sans changer la phase."""
        self._progress.setRange(0, maximum)
        self._progress.setValue(value)
        if detail:
            self._lbl_detail.setText(detail)

    def finish(self):
        """Cache l'overlay."""
        self.hide()

    # ── Positionnement ───────────────────────────────────────────
    def _reposition(self):
        """Centre la carte sur le parent."""
        if self.parent():
            parent_rect = self.parent().rect()
            self.setGeometry(parent_rect)
            cx = (parent_rect.width() - self._card.width()) // 2
            cy = (parent_rect.height() - self._card.height()) // 2
            self._card.move(cx, cy)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    # ── Fond semi-transparent ────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        painter.end()

"""
ui/recording_bar.py
-------------------
Barre d'enregistrement audio : bouton Enregistrer/Arrêter + chronomètre en temps réel.

Ce widget est placé en haut de la fenêtre principale.
Il émet des signaux PyQt6 pour communiquer avec la fenêtre principale
sans couplage fort.

Signaux émis :
  - enregistrement_demarre()           : l'utilisateur a cliqué sur "Enregistrer"
  - enregistrement_arrete(chemin, duree): l'enregistrement est terminé
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette

from core.audio_recorder import AudioRecorder


class RecordingBar(QWidget):
    """Barre horizontale avec bouton d'enregistrement et chronomètre."""

    # Signaux vers la fenêtre principale
    enregistrement_demarre = pyqtSignal()
    enregistrement_arrete = pyqtSignal(str, float)  # (chemin_audio, duree_secondes)
    erreur_enregistrement = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recorder = AudioRecorder()
        self._timer_chrono = QTimer(self)
        self._timer_chrono.setInterval(500)  # Mise à jour toutes les 0.5 s
        self._timer_chrono.timeout.connect(self._mettre_a_jour_chrono)
        self._configurer_ui()

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------

    def _configurer_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(16)

        # --- Bouton principal ---
        self.btn_enregistrer = QPushButton("⏺  Enregistrer")
        self.btn_enregistrer.setFixedHeight(40)
        self.btn_enregistrer.setMinimumWidth(160)
        self.btn_enregistrer.setFont(QFont("Segoe UI", 11))
        self.btn_enregistrer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_enregistrer.clicked.connect(self._toggle_enregistrement)
        self._appliquer_style_repos()

        # --- Étiquette chronomètre ---
        self.lbl_chrono = QLabel("00:00")
        self.lbl_chrono.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self.lbl_chrono.setFixedWidth(60)
        self.lbl_chrono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_chrono.hide()

        # --- Étiquette statut ---
        self.lbl_statut = QLabel("Prêt à enregistrer")
        self.lbl_statut.setFont(QFont("Segoe UI", 10))
        self.lbl_statut.setStyleSheet("color: #666666;")

        layout.addWidget(self.btn_enregistrer)
        layout.addWidget(self.lbl_chrono)
        layout.addWidget(self.lbl_statut)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _toggle_enregistrement(self):
        """Démarre ou arrête l'enregistrement selon l'état actuel."""
        if self._recorder.est_en_cours():
            self._arreter()
        else:
            self._demarrer()

    def _demarrer(self):
        try:
            self._recorder.start_enregistrement()
        except Exception as e:
            self.erreur_enregistrement.emit(f"Impossible de démarrer l'enregistrement :\n{e}")
            return

        # Mise à jour visuelle
        self.btn_enregistrer.setText("⏹  Arrêter")
        self._appliquer_style_enregistrement()
        self.lbl_chrono.show()
        self.lbl_chrono.setText("00:00")
        self.lbl_statut.setText("Enregistrement en cours…")
        self.lbl_statut.setStyleSheet("color: #cc0000; font-weight: bold;")

        self._timer_chrono.start()
        self.enregistrement_demarre.emit()

    def _arreter(self):
        self._timer_chrono.stop()

        chemin, duree = self._recorder.stop_enregistrement()

        # Mise à jour visuelle
        self.btn_enregistrer.setText("⏺  Enregistrer")
        self._appliquer_style_repos()
        self.lbl_chrono.hide()

        if chemin:
            secondes = int(duree)
            self.lbl_statut.setText(
                f"Enregistrement terminé ({secondes // 60:02d}:{secondes % 60:02d})"
            )
            self.lbl_statut.setStyleSheet("color: #007700;")
            self.enregistrement_arrete.emit(chemin, duree)
        else:
            self.lbl_statut.setText("Aucune donnée capturée.")
            self.lbl_statut.setStyleSheet("color: #aa6600;")

    def _mettre_a_jour_chrono(self):
        """Met à jour l'affichage du chronomètre toutes les 0.5 s."""
        duree = self._recorder.duree_actuelle()
        minutes = int(duree) // 60
        secondes = int(duree) % 60
        self.lbl_chrono.setText(f"{minutes:02d}:{secondes:02d}")

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    def _appliquer_style_repos(self):
        self.btn_enregistrer.setStyleSheet("""
            QPushButton {
                background-color: #e53935;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 4px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #c62828; }
            QPushButton:pressed { background-color: #b71c1c; }
        """)

    def _appliquer_style_enregistrement(self):
        self.btn_enregistrer.setStyleSheet("""
            QPushButton {
                background-color: #424242;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 4px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #212121; }
            QPushButton:pressed { background-color: #000000; }
        """)

    def definir_statut(self, message: str, couleur: str = "#666666"):
        """Permet à la fenêtre principale de mettre à jour le message de statut."""
        self.lbl_statut.setText(message)
        self.lbl_statut.setStyleSheet(f"color: {couleur};")

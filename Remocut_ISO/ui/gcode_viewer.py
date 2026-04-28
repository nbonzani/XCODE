"""
ui/gcode_viewer.py — Visualiseur du programme GCode généré.

Affiche le GCode dans une liste avec numéros de ligne (fond sombre).
Émet la position (X, Y) de l'outil correspondant à la ligne sélectionnée,
calculée par parsing modal (X/Y précédents conservés si absents).
"""

import logging
import re
from typing import Dict, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Regex pour extraire X<nombre> ou Y<nombre> (signe + décimal)
_RE_X = re.compile(r"(?<![A-Z])X(-?\d+(?:\.\d+)?)")
_RE_Y = re.compile(r"(?<![A-Z])Y(-?\d+(?:\.\d+)?)")


class GCodeViewer(QWidget):
    """
    Widget d'affichage du GCode avec sélection de ligne.

    Signaux :
        position_changee(object) — (x, y) en mm ou None si indéterminé.
        retour_demande()         — émis au clic sur "← Aperçu DXF".
    """

    position_changee = pyqtSignal(object)
    retour_demande = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._positions: Dict[int, Tuple[float, float]] = {}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Header : bouton retour + infos
        header = QHBoxLayout()
        header.setContentsMargins(4, 2, 4, 2)

        self._btn_retour = QPushButton("← Aperçu DXF")
        self._btn_retour.setMaximumHeight(24)
        self._btn_retour.setStyleSheet(
            "QPushButton { padding: 2px 8px; border: 1px solid #aaa; "
            "border-radius: 3px; background: #eee; }"
            "QPushButton:hover { background: #ddd; }"
        )
        self._btn_retour.clicked.connect(self.retour_demande.emit)
        header.addWidget(self._btn_retour)

        # Bouton lecture / pause
        self._btn_lecture = QPushButton("▶")
        self._btn_lecture.setMaximumHeight(24)
        self._btn_lecture.setMaximumWidth(32)
        self._btn_lecture.setToolTip("Lecture / Pause")
        self._btn_lecture.setStyleSheet(
            "QPushButton { padding: 2px 6px; border: 1px solid #aaa; "
            "border-radius: 3px; background: #eee; font-weight: bold; }"
            "QPushButton:hover { background: #ddd; }"
            "QPushButton:checked { background: #c8e6c9; border-color: #4caf50; }"
        )
        self._btn_lecture.setCheckable(True)
        self._btn_lecture.clicked.connect(self._on_toggle_lecture)
        header.addWidget(self._btn_lecture)

        # Bouton stop (reset au début)
        self._btn_stop = QPushButton("■")
        self._btn_stop.setMaximumHeight(24)
        self._btn_stop.setMaximumWidth(28)
        self._btn_stop.setToolTip("Stop (retour à la ligne 1)")
        self._btn_stop.setStyleSheet(
            "QPushButton { padding: 2px 6px; border: 1px solid #aaa; "
            "border-radius: 3px; background: #eee; }"
            "QPushButton:hover { background: #ddd; }"
        )
        self._btn_stop.clicked.connect(self._on_stop)
        header.addWidget(self._btn_stop)

        # Slider de vitesse (lignes / seconde)
        lbl_vit = QLabel("Vitesse :")
        lbl_vit.setStyleSheet("color: #333; font-size: 10px;")
        header.addWidget(lbl_vit)

        self._slider_vitesse = QSlider(Qt.Orientation.Horizontal)
        self._slider_vitesse.setMinimum(1)      # 1 ligne/s
        self._slider_vitesse.setMaximum(100)    # 100 lignes/s
        self._slider_vitesse.setValue(10)       # 10 lignes/s par défaut
        self._slider_vitesse.setMaximumWidth(120)
        self._slider_vitesse.setToolTip("Vitesse de défilement (lignes/seconde)")
        self._slider_vitesse.valueChanged.connect(self._on_vitesse_changee)
        header.addWidget(self._slider_vitesse)

        self._lbl_vitesse = QLabel("10 l/s")
        self._lbl_vitesse.setStyleSheet("color: #333; font-size: 10px;")
        self._lbl_vitesse.setMinimumWidth(48)
        header.addWidget(self._lbl_vitesse)

        header.addStretch()

        self._lbl_info = QLabel("")
        self._lbl_info.setStyleSheet("color: #333; font-size: 10px;")
        header.addWidget(self._lbl_info)

        layout.addLayout(header)

        # Timer pour le défilement automatique
        self._timer_lecture = QTimer(self)
        self._timer_lecture.timeout.connect(self._avancer_ligne)
        self._appliquer_vitesse_timer()

        # Liste GCode (fond sombre, monospace)
        self._liste = QListWidget()
        self._liste.setFont(QFont("Consolas", 10))
        self._liste.setStyleSheet(
            "QListWidget { background: #1e1e24; color: #e0e0e0; "
            "border: 1px solid #444; border-radius: 2px; "
            "selection-background-color: #2d5a87; selection-color: #ffffff; }"
            "QListWidget::item { padding: 1px 4px; border-bottom: 1px solid #2a2a30; }"
            "QListWidget::item:selected { background: #2d5a87; color: #ffffff; }"
        )
        self._liste.setAlternatingRowColors(False)
        self._liste.setUniformItemSizes(True)   # optim pour gros programmes
        self._liste.currentRowChanged.connect(self._on_ligne_changee)
        layout.addWidget(self._liste, 1)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def set_gcode(self, texte: str) -> None:
        """Charge le texte GCode, parse les positions et affiche."""
        self._arreter_lecture()
        self._liste.clear()
        self._positions = {}

        if not texte:
            self._lbl_info.setText("(vide)")
            return

        lignes = texte.splitlines()
        cur_x, cur_y = 0.0, 0.0
        n_largeur = len(str(len(lignes)))

        for idx, ligne in enumerate(lignes):
            # Extraire X/Y (ignore commentaires ; ... et ( ... ))
            code_part = ligne.split(';', 1)[0]
            # Retirer aussi (...) commentaires
            code_part = re.sub(r"\([^)]*\)", "", code_part)
            code_up = code_part.upper()

            m_x = _RE_X.search(code_up)
            m_y = _RE_Y.search(code_up)
            if m_x:
                try:
                    cur_x = float(m_x.group(1))
                except ValueError:
                    pass
            if m_y:
                try:
                    cur_y = float(m_y.group(1))
                except ValueError:
                    pass

            self._positions[idx] = (cur_x, cur_y)

            # Format : "  12  | G01 X100 Y200"
            item_text = f"{idx + 1:>{n_largeur}} │ {ligne}"
            self._liste.addItem(QListWidgetItem(item_text))

        self._lbl_info.setText(f"{len(lignes)} ligne(s)")

        if lignes:
            self._liste.setCurrentRow(0)

    def vider(self) -> None:
        """Efface l'affichage."""
        self._arreter_lecture()
        self._liste.clear()
        self._positions = {}
        self._lbl_info.setText("")

    # ------------------------------------------------------------------
    # Lecture automatique
    # ------------------------------------------------------------------

    def _on_toggle_lecture(self, checked: bool) -> None:
        """Démarre ou met en pause le défilement automatique."""
        if checked:
            if self._liste.count() == 0:
                self._btn_lecture.setChecked(False)
                return
            # Si on est sur la dernière ligne, rebobiner
            if self._liste.currentRow() >= self._liste.count() - 1:
                self._liste.setCurrentRow(0)
            self._btn_lecture.setText("❚❚")
            self._timer_lecture.start()
        else:
            self._btn_lecture.setText("▶")
            self._timer_lecture.stop()

    def _on_stop(self) -> None:
        """Arrête la lecture et remet à la ligne 1."""
        self._arreter_lecture()
        if self._liste.count() > 0:
            self._liste.setCurrentRow(0)

    def _arreter_lecture(self) -> None:
        """Arrête le timer et remet le bouton lecture en position initiale."""
        self._timer_lecture.stop()
        self._btn_lecture.setChecked(False)
        self._btn_lecture.setText("▶")

    def _avancer_ligne(self) -> None:
        """Passe à la ligne suivante (appelé par le timer)."""
        ligne = self._liste.currentRow()
        if ligne < 0:
            self._liste.setCurrentRow(0)
            return
        if ligne >= self._liste.count() - 1:
            # Fin du programme
            self._arreter_lecture()
            return
        self._liste.setCurrentRow(ligne + 1)

    def _on_vitesse_changee(self, valeur: int) -> None:
        """Met à jour la vitesse du timer et le libellé."""
        self._lbl_vitesse.setText(f"{valeur} l/s")
        self._appliquer_vitesse_timer()

    def _appliquer_vitesse_timer(self) -> None:
        """Applique l'intervalle du timer selon le slider (lignes/seconde)."""
        lignes_par_sec = max(1, self._slider_vitesse.value())
        intervalle_ms = max(10, int(1000 / lignes_par_sec))
        self._timer_lecture.setInterval(intervalle_ms)

    # ------------------------------------------------------------------
    # Slots internes
    # ------------------------------------------------------------------

    def _on_ligne_changee(self, idx: int) -> None:
        """Émet la position (X, Y) correspondant à la ligne sélectionnée."""
        if idx in self._positions:
            self.position_changee.emit(self._positions[idx])
        else:
            self.position_changee.emit(None)

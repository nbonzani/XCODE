"""
ui/note_list_widget.py
----------------------
Panneau gauche de l'interface : liste des notes avec filtres.

Fonctionnalités :
  - Affichage de la liste avec date, durée, thème(s) et extrait du texte
  - Filtre par thème (menu déroulant)
  - Recherche plein texte dans les transcriptions
  - Bouton "Supprimer" pour effacer la note sélectionnée

Signal émis :
  - note_selectionnee(note_id: int) : l'utilisateur a cliqué sur une note
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLineEdit, QComboBox, QLabel, QPushButton, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

import core.database as db
from utils.config import EXTRAIT_LONGUEUR


class NoteListWidget(QWidget):
    """Panneau liste + filtres des notes."""

    note_selectionnee = pyqtSignal(int)  # note_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._configurer_ui()
        self.rafraichir()

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------

    def _configurer_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # --- Titre du panneau ---
        lbl_titre = QLabel("Notes enregistrées")
        lbl_titre.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_titre.setStyleSheet("padding: 8px 8px 4px 8px; color: #333;")
        layout.addWidget(lbl_titre)

        # --- Barre de recherche ---
        self.champ_recherche = QLineEdit()
        self.champ_recherche.setPlaceholderText("🔍  Rechercher dans les transcriptions…")
        self.champ_recherche.setFont(QFont("Segoe UI", 10))
        self.champ_recherche.textChanged.connect(self._on_filtre_change)
        self.champ_recherche.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px 8px;
                margin: 0 8px;
            }
        """)
        layout.addWidget(self.champ_recherche)

        # --- Filtre par thème ---
        ligne_filtre = QHBoxLayout()
        ligne_filtre.setContentsMargins(8, 0, 8, 0)
        lbl_filtre = QLabel("Thème :")
        lbl_filtre.setFont(QFont("Segoe UI", 10))
        self.combo_theme = QComboBox()
        self.combo_theme.setFont(QFont("Segoe UI", 10))
        self.combo_theme.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_theme.currentTextChanged.connect(self._on_filtre_change)
        ligne_filtre.addWidget(lbl_filtre)
        ligne_filtre.addWidget(self.combo_theme, stretch=1)
        layout.addLayout(ligne_filtre)

        # --- Liste des notes ---
        self.liste = QListWidget()
        self.liste.setFont(QFont("Segoe UI", 10))
        self.liste.setAlternatingRowColors(True)
        self.liste.itemClicked.connect(self._on_item_clique)
        self.liste.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #1565c0;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #e3f2fd;
            }
        """)
        layout.addWidget(self.liste, stretch=1)

        # --- Bouton supprimer ---
        self.btn_supprimer = QPushButton("🗑  Supprimer la note sélectionnée")
        self.btn_supprimer.setFont(QFont("Segoe UI", 10))
        self.btn_supprimer.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f5;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px 12px;
                margin: 0 8px 8px 8px;
                color: #c62828;
            }
            QPushButton:hover { background-color: #ffebee; }
            QPushButton:disabled { color: #aaa; }
        """)
        self.btn_supprimer.setEnabled(False)
        self.btn_supprimer.clicked.connect(self._supprimer_note)
        layout.addWidget(self.btn_supprimer)

        # Label compteur
        self.lbl_compteur = QLabel("")
        self.lbl_compteur.setFont(QFont("Segoe UI", 9))
        self.lbl_compteur.setStyleSheet("color: #999; padding: 0 8px 6px 8px;")
        layout.addWidget(self.lbl_compteur)

    # ------------------------------------------------------------------
    # Rafraîchissement de la liste
    # ------------------------------------------------------------------

    def rafraichir(self):
        """Recharge la liste des notes et les thèmes du filtre depuis la base."""
        self._recharger_themes_combo()
        self._recharger_liste()

    def _recharger_themes_combo(self):
        """Met à jour le menu déroulant des thèmes sans déclencher de signal."""
        self.combo_theme.blockSignals(True)
        theme_courant = self.combo_theme.currentText()
        self.combo_theme.clear()
        self.combo_theme.addItem("Tous les thèmes")
        for nom in db.get_noms_themes():
            self.combo_theme.addItem(nom)
        # Rétablir la sélection précédente si possible
        index = self.combo_theme.findText(theme_courant)
        if index >= 0:
            self.combo_theme.setCurrentIndex(index)
        self.combo_theme.blockSignals(False)

    def _recharger_liste(self):
        """Recharge les items de la liste selon les filtres actifs."""
        theme = self.combo_theme.currentText()
        recherche = self.champ_recherche.text().strip()

        theme_filtre = theme if theme != "Tous les thèmes" else None
        recherche_filtre = recherche if recherche else None

        notes = db.get_toutes_notes(theme_filtre=theme_filtre, recherche=recherche_filtre)

        self.liste.clear()
        for note in notes:
            item = self._creer_item(note)
            self.liste.addItem(item)

        count = len(notes)
        self.lbl_compteur.setText(f"{count} note{'s' if count > 1 else ''}")
        self.btn_supprimer.setEnabled(False)

    def _creer_item(self, note: dict) -> QListWidgetItem:
        """Crée un QListWidgetItem à partir d'un dict de note."""
        # Formatage de la date
        try:
            dt = datetime.fromisoformat(note["date_creation"])
            date_str = dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            date_str = note.get("date_creation", "")[:16]

        # Formatage de la durée
        duree = note.get("duree_secondes") or 0
        duree_str = f"{int(duree) // 60:02d}:{int(duree) % 60:02d}"

        # Titre ou extrait
        titre = note.get("titre") or ""
        transcription = note.get("transcription") or ""
        if not titre:
            titre = (transcription[:40] + "…") if len(transcription) > 40 else transcription
        if not titre:
            titre = "(sans titre)"

        # Thèmes
        themes_str = note.get("themes") or "—"

        # Extrait du texte
        extrait = transcription[:EXTRAIT_LONGUEUR]
        if len(transcription) > EXTRAIT_LONGUEUR:
            extrait += "…"

        texte_affichage = (
            f"{titre}\n"
            f"📅 {date_str}  ⏱ {duree_str}  🏷 {themes_str}\n"
            f"{extrait}"
        )

        item = QListWidgetItem(texte_affichage)
        item.setData(Qt.ItemDataRole.UserRole, note["id"])  # Stockage de l'ID
        return item

    # ------------------------------------------------------------------
    # Gestionnaires d'événements
    # ------------------------------------------------------------------

    def _on_filtre_change(self):
        self._recharger_liste()

    def _on_item_clique(self, item: QListWidgetItem):
        note_id = item.data(Qt.ItemDataRole.UserRole)
        if note_id is not None:
            self.btn_supprimer.setEnabled(True)
            self.note_selectionnee.emit(note_id)

    def _supprimer_note(self):
        item = self.liste.currentItem()
        if not item:
            return
        note_id = item.data(Qt.ItemDataRole.UserRole)
        reponse = QMessageBox.question(
            self,
            "Confirmer la suppression",
            "Supprimer définitivement cette note ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reponse == QMessageBox.StandardButton.Yes:
            db.supprimer_note(note_id)
            self._recharger_liste()

    def selectionner_note(self, note_id: int):
        """Sélectionne programmatiquement une note dans la liste."""
        for i in range(self.liste.count()):
            item = self.liste.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == note_id:
                self.liste.setCurrentItem(item)
                self.btn_supprimer.setEnabled(True)
                break

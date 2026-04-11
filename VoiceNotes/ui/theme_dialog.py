"""
ui/theme_dialog.py
------------------
Dialogue de gestion des thèmes configurables.

Permet à l'utilisateur de :
  - Voir la liste complète des thèmes
  - Ajouter un nouveau thème manuellement
  - Renommer un thème existant
  - Supprimer un thème (avec avertissement si des notes y sont associées)
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QLineEdit, QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

import core.database as db


class ThemeDialog(QDialog):
    """Fenêtre modale de gestion des thèmes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestion des thèmes")
        self.setMinimumSize(400, 450)
        self.setModal(True)
        self._configurer_ui()
        self._charger_themes()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _configurer_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # Titre
        lbl = QLabel("Gérer les thèmes")
        lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        layout.addWidget(lbl)

        explication = QLabel(
            "Ces thèmes sont utilisés pour classer vos notes.\n"
            "Vous pouvez en ajouter, renommer ou supprimer."
        )
        explication.setFont(QFont("Segoe UI", 10))
        explication.setStyleSheet("color: #666;")
        layout.addWidget(explication)

        # Liste des thèmes
        self.liste = QListWidget()
        self.liste.setFont(QFont("Segoe UI", 11))
        self.liste.setAlternatingRowColors(True)
        self.liste.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QListWidget::item { padding: 6px; }
            QListWidget::item:selected { background: #1565c0; color: white; }
        """)
        layout.addWidget(self.liste, stretch=1)

        # Champ + bouton d'ajout
        ligne_ajout = QHBoxLayout()
        self.champ_nouveau = QLineEdit()
        self.champ_nouveau.setFont(QFont("Segoe UI", 10))
        self.champ_nouveau.setPlaceholderText("Nouveau thème…")
        self.champ_nouveau.returnPressed.connect(self._ajouter_theme)
        self.champ_nouveau.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px 8px;
            }
        """)
        btn_ajouter = QPushButton("Ajouter")
        btn_ajouter.setFont(QFont("Segoe UI", 10))
        btn_ajouter.clicked.connect(self._ajouter_theme)
        btn_ajouter.setStyleSheet("""
            QPushButton {
                background: #1565c0; color: white;
                border: none; border-radius: 4px;
                padding: 6px 14px;
            }
            QPushButton:hover { background: #0d47a1; }
        """)
        ligne_ajout.addWidget(self.champ_nouveau)
        ligne_ajout.addWidget(btn_ajouter)
        layout.addLayout(ligne_ajout)

        # Boutons modifier / supprimer
        ligne_actions = QHBoxLayout()
        btn_renommer = QPushButton("Renommer")
        btn_renommer.setFont(QFont("Segoe UI", 10))
        btn_renommer.clicked.connect(self._renommer_theme)
        btn_renommer.setStyleSheet(self._style_secondaire())

        btn_supprimer = QPushButton("🗑  Supprimer")
        btn_supprimer.setFont(QFont("Segoe UI", 10))
        btn_supprimer.clicked.connect(self._supprimer_theme)
        btn_supprimer.setStyleSheet(self._style_secondaire("#c62828"))

        ligne_actions.addWidget(btn_renommer)
        ligne_actions.addWidget(btn_supprimer)
        ligne_actions.addStretch()
        layout.addLayout(ligne_actions)

        # Bouton fermer
        btn_fermer = QPushButton("Fermer")
        btn_fermer.setFont(QFont("Segoe UI", 10))
        btn_fermer.clicked.connect(self.accept)
        btn_fermer.setStyleSheet(self._style_secondaire())
        layout.addWidget(btn_fermer, alignment=Qt.AlignmentFlag.AlignRight)

    # ------------------------------------------------------------------
    # Chargement
    # ------------------------------------------------------------------

    def _charger_themes(self):
        self.liste.clear()
        for theme in db.get_tous_themes():
            item = QListWidgetItem(theme["nom"])
            item.setData(Qt.ItemDataRole.UserRole, theme["id"])
            self.liste.addItem(item)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _ajouter_theme(self):
        nom = self.champ_nouveau.text().strip()
        if not nom:
            return
        db.get_ou_creer_theme(nom)
        self.champ_nouveau.clear()
        self._charger_themes()

    def _renommer_theme(self):
        item = self.liste.currentItem()
        if not item:
            QMessageBox.information(self, "Sélection requise",
                                    "Sélectionnez un thème à renommer.")
            return
        theme_id = item.data(Qt.ItemDataRole.UserRole)
        nom_actuel = item.text()

        nouveau_nom, ok = QInputDialog.getText(
            self, "Renommer le thème",
            "Nouveau nom :", text=nom_actuel
        )
        if ok and nouveau_nom.strip() and nouveau_nom.strip() != nom_actuel:
            db.renommer_theme(theme_id, nouveau_nom.strip())
            self._charger_themes()

    def _supprimer_theme(self):
        item = self.liste.currentItem()
        if not item:
            QMessageBox.information(self, "Sélection requise",
                                    "Sélectionnez un thème à supprimer.")
            return
        theme_id = item.data(Qt.ItemDataRole.UserRole)
        nom = item.text()

        reponse = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Supprimer le thème « {nom} » ?\n\n"
            "Les notes associées ne seront pas supprimées, "
            "mais elles perdront ce thème.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reponse == QMessageBox.StandardButton.Yes:
            db.supprimer_theme(theme_id)
            self._charger_themes()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    def _style_secondaire(self, couleur_texte: str = "#333") -> str:
        return f"""
            QPushButton {{
                background: #f5f5f5;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px 14px;
                color: {couleur_texte};
            }}
            QPushButton:hover {{ background: #e0e0e0; }}
        """

"""
ui/dxf_list_panel.py — Panneau liste des fichiers DXF chargés.

Permet d'ajouter, supprimer et régler la quantité de chaque fichier DXF.
Émet list_changed à chaque modification.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import List, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


@dataclass
class EntreeDxf:
    """Représente un fichier DXF chargé avec sa quantité."""
    chemin: str
    nom: str
    contours: List[List[Tuple[float, float]]]
    quantite: int = 1


class _ItemDxf(QWidget):
    """Widget d'un item de la liste DXF (nom + spinbox quantité + bouton supprimer)."""

    supprimer = pyqtSignal(object)   # émet self
    quantite_changee = pyqtSignal()

    def __init__(self, entree: EntreeDxf, parent=None):
        super().__init__(parent)
        self._entree = entree

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Nom du fichier
        self._lbl = QLabel(entree.nom)
        self._lbl.setToolTip(entree.chemin)
        self._lbl.setMinimumWidth(80)
        layout.addWidget(self._lbl, 1)

        # Contours info
        n_cont = len(entree.contours)
        lbl_cont = QLabel(f"{n_cont} ctrs")
        lbl_cont.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(lbl_cont)

        # Quantité
        lbl_qty = QLabel("×")
        lbl_qty.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_qty)

        self._spin = QSpinBox()
        self._spin.setMinimum(1)
        self._spin.setMaximum(999)
        self._spin.setValue(entree.quantite)
        self._spin.setMaximumWidth(60)
        self._spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._spin.valueChanged.connect(self._on_qty_changed)
        layout.addWidget(self._spin)

        # Bouton supprimer
        btn_del = QPushButton("✕")
        btn_del.setMaximumWidth(24)
        btn_del.setMaximumHeight(24)
        btn_del.setStyleSheet(
            "QPushButton { color: #c00; border: none; font-weight: bold; }"
            "QPushButton:hover { color: #f00; }"
        )
        btn_del.setToolTip("Supprimer ce fichier")
        btn_del.clicked.connect(lambda: self.supprimer.emit(self))
        layout.addWidget(btn_del)

    @property
    def entree(self) -> EntreeDxf:
        return self._entree

    def _on_qty_changed(self, valeur: int) -> None:
        self._entree.quantite = valeur
        self.quantite_changee.emit()


class DxfListPanel(QWidget):
    """
    Panneau latéral listant les fichiers DXF chargés.

    Signaux :
        list_changed : émis à chaque modification (ajout, suppression, quantité).
    """

    list_changed = pyqtSignal()
    selection_changee = pyqtSignal(object)   # EntreeDxf ou None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[_ItemDxf] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Titre
        lbl_titre = QLabel("Fichiers DXF")
        lbl_titre.setStyleSheet(
            "font-weight: bold; color: #333; padding: 2px 4px; "
            "background: #e8e8e8; border-radius: 3px;"
        )
        layout.addWidget(lbl_titre)

        # Bouton ajouter
        self._btn_ajouter = QPushButton("+ Ajouter DXF…")
        self._btn_ajouter.setStyleSheet(
            "QPushButton { background: #2980b9; color: white; border-radius: 4px; padding: 4px 8px; }"
            "QPushButton:hover { background: #3498db; }"
        )
        self._btn_ajouter.clicked.connect(self._ajouter_dxf_dialogue)
        layout.addWidget(self._btn_ajouter)

        # Liste scrollable
        self._liste_widget = QListWidget()
        self._liste_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._liste_widget.setStyleSheet(
            "QListWidget { border: 1px solid #ccc; border-radius: 3px; background: #fafafa; }"
            "QListWidget::item { border-bottom: 1px solid #eee; padding: 0px; }"
            "QListWidget::item:selected { background: #d0e8f8; }"
        )
        self._liste_widget.currentRowChanged.connect(self._on_selection_changee)
        layout.addWidget(self._liste_widget, 1)

        # Résumé
        self._lbl_resume = QLabel("Aucun fichier chargé.")
        self._lbl_resume.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        self._lbl_resume.setWordWrap(True)
        layout.addWidget(self._lbl_resume)

        # Bouton vider
        self._btn_vider = QPushButton("Vider la liste")
        self._btn_vider.setStyleSheet(
            "QPushButton { color: #c00; border: 1px solid #c00; border-radius: 3px; padding: 2px 6px; }"
            "QPushButton:hover { background: #fdd; }"
        )
        self._btn_vider.setEnabled(False)
        self._btn_vider.clicked.connect(self._vider_liste)
        layout.addWidget(self._btn_vider)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def get_entrees(self) -> List[EntreeDxf]:
        """Retourne la liste des entrées DXF actuellement chargées."""
        return [item.entree for item in self._items]

    def get_entree_selectionnee(self):
        """Retourne l'EntreeDxf sélectionnée (ou None)."""
        idx = self._liste_widget.currentRow()
        if 0 <= idx < len(self._items):
            return self._items[idx].entree
        return None

    def ajouter_entree(self, entree: EntreeDxf) -> None:
        """Ajoute une entrée DXF programmatiquement (ex: depuis argv)."""
        self._ajouter_item(entree)

    def _on_selection_changee(self, ligne: int) -> None:
        """Émet l'entrée sélectionnée (ou None)."""
        if 0 <= ligne < len(self._items):
            self.selection_changee.emit(self._items[ligne].entree)
        else:
            self.selection_changee.emit(None)

    # ------------------------------------------------------------------
    # Slots internes
    # ------------------------------------------------------------------

    def _ajouter_dxf_dialogue(self) -> None:
        """Ouvre un dialogue de sélection de fichiers DXF."""
        chemins, _ = QFileDialog.getOpenFileNames(
            self,
            "Ouvrir des fichiers DXF",
            "",
            "Fichiers DXF (*.dxf);;Tous les fichiers (*)",
        )
        if not chemins:
            return

        for chemin in chemins:
            # Éviter les doublons
            if any(item.entree.chemin == chemin for item in self._items):
                logger.warning(f"Fichier déjà dans la liste : '{chemin}'")
                continue

            try:
                from utils.file_io import charger_dxf
                contours = charger_dxf(chemin, tolerance_fermeture=0.01)
                entree = EntreeDxf(
                    chemin=chemin,
                    nom=os.path.basename(chemin),
                    contours=contours,
                    quantite=1,
                )
                self._ajouter_item(entree)
                logger.info(
                    f"DXF ajouté : '{entree.nom}' ({len(contours)} contour(s))"
                )
            except Exception as e:
                logger.error(f"Erreur chargement DXF '{chemin}' : {e}")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self,
                    "Erreur DXF",
                    f"Impossible de charger :\n{os.path.basename(chemin)}\n\n{e}",
                )

    def _ajouter_item(self, entree: EntreeDxf) -> None:
        """Ajoute un widget item dans la liste."""
        item_widget = _ItemDxf(entree)
        item_widget.supprimer.connect(self._supprimer_item)
        item_widget.quantite_changee.connect(self._on_modifie)
        self._items.append(item_widget)

        list_item = QListWidgetItem(self._liste_widget)
        list_item.setSizeHint(item_widget.sizeHint())
        self._liste_widget.addItem(list_item)
        self._liste_widget.setItemWidget(list_item, item_widget)

        # Sélectionner automatiquement le dernier ajouté
        self._liste_widget.setCurrentRow(len(self._items) - 1)

        self._on_modifie()

    def _supprimer_item(self, item_widget: _ItemDxf) -> None:
        """Supprime un item de la liste."""
        idx = self._items.index(item_widget)
        self._items.pop(idx)
        self._liste_widget.takeItem(idx)
        self._on_modifie()

    def _vider_liste(self) -> None:
        """Supprime tous les items."""
        self._items.clear()
        self._liste_widget.clear()
        self._on_modifie()

    def _on_modifie(self) -> None:
        """Met à jour le résumé et émet list_changed."""
        n = len(self._items)
        if n == 0:
            self._lbl_resume.setText("Aucun fichier chargé.")
        else:
            total_qty = sum(item.entree.quantite for item in self._items)
            total_cont = sum(len(item.entree.contours) for item in self._items)
            self._lbl_resume.setText(
                f"{n} fichier(s) · {total_qty} pièce(s) · {total_cont} contour(s)"
            )
        self._btn_vider.setEnabled(n > 0)
        self.list_changed.emit()

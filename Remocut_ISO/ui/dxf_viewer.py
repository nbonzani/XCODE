"""
ui/dxf_viewer.py — Visualiseur 2D des contours DXF importés.

QWidget avec QPainter :
  - Affiche les contours extérieurs en bleu, les trous en rouge.
  - Zoom à la molette, déplacement par clic-glisser.
  - Affichage des dimensions de la bounding box globale.
  - Méthode set_contours() pour charger les données à afficher.
"""

import logging
import math
from typing import List, Optional, Tuple

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QTransform,
    QWheelEvent,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

logger = logging.getLogger(__name__)

# Couleurs d'affichage (contraste renforcé)
COULEUR_EXTERIEUR = QColor(10, 50, 180)       # Bleu foncé saturé
COULEUR_INTERIEUR = QColor(190, 20, 20)       # Rouge foncé saturé
COULEUR_FOND = QColor(250, 250, 252)          # Fond presque blanc
COULEUR_AXES = QColor(180, 180, 180)
COULEUR_TEXTE = QColor(30, 30, 30)

# Épaisseurs
EPAISSEUR_CONTOUR = 2.8
EPAISSEUR_POINT_DEPART = 1.8

# Marge visuelle autour des contours (pixels)
MARGE_AFFICHAGE = 30


class DxfViewer(QWidget):
    """
    Widget d'affichage 2D des contours DXF.

    Conventions :
      - Les contours sont stockés en coordonnées DXF (Y vers le haut).
      - L'affichage inverse Y pour respecter la convention écran (Y vers le bas).
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._contours: List[List[Tuple[float, float]]] = []
        self._contours_interieurs: List[bool] = []  # True = trou pour chaque contour

        # Paramètres de vue
        self._echelle: float = 1.0
        self._offset: QPointF = QPointF(0.0, 0.0)
        self._drag_start: Optional[QPoint] = None
        self._offset_drag: Optional[QPointF] = None

        # Bounding box globale (en coordonnées DXF)
        self._bb: Optional[Tuple[float, float, float, float]] = None

        self.setMinimumSize(300, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setStyleSheet(f"background-color: {COULEUR_FOND.name()};")

    # -----------------------------------------------------------------------
    # Données
    # -----------------------------------------------------------------------

    def set_contours(
        self,
        contours: List[List[Tuple[float, float]]],
        interieurs: Optional[List[bool]] = None,
    ) -> None:
        """
        Charge les contours à afficher.

        Args:
            contours   : Liste de contours (listes de tuples (x, y) en mm).
            interieurs : Liste de booléens (True = trou). Si None, tous extérieurs.
        """
        self._contours = contours
        if interieurs is not None and len(interieurs) == len(contours):
            self._contours_interieurs = list(interieurs)
        else:
            self._contours_interieurs = [False] * len(contours)

        # Calculer la bounding box globale
        self._bb = self._calculer_bb()
        self._ajuster_vue()
        self.update()

    def set_entrees_multiples(self, entrees) -> None:
        """
        Affiche les contours de plusieurs entrées DXF (List[EntreeDxf]).

        Regroupe tous les contours en une seule vue.
        """
        tous_contours = []
        for e in entrees:
            tous_contours.extend(e.contours)
        self.set_contours(tous_contours)

    def set_entree_unique(self, entree) -> None:
        """
        Affiche les contours d'une seule entrée DXF (vue détaillée).

        Args:
            entree : EntreeDxf — le fichier à afficher seul.
        """
        if entree is None:
            self.vider()
            return
        self.set_contours(entree.contours)

    def vider(self) -> None:
        """Efface tous les contours affichés."""
        self._contours = []
        self._contours_interieurs = []
        self._bb = None
        self.update()

    # -----------------------------------------------------------------------
    # Peinture
    # -----------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        """Dessin principal."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fond
        painter.fillRect(self.rect(), COULEUR_FOND)

        if not self._contours or self._bb is None:
            self._dessiner_message(painter, "Aucun fichier DXF chargé")
            return

        # Appliquer la transformation (zoom + pan)
        painter.save()
        painter.translate(self._offset)
        painter.scale(self._echelle, self._echelle)

        # Dessiner les contours
        for i, contour in enumerate(self._contours):
            if len(contour) < 2:
                continue
            est_int = self._contours_interieurs[i] if i < len(self._contours_interieurs) else False
            couleur = COULEUR_INTERIEUR if est_int else COULEUR_EXTERIEUR
            self._dessiner_contour(painter, contour, couleur)

        painter.restore()

        # Informations (bounding box)
        self._dessiner_infos(painter)

    def _dessiner_contour(
        self,
        painter: QPainter,
        contour: List[Tuple[float, float]],
        couleur: QColor,
    ) -> None:
        """Dessine un contour avec la couleur donnée."""
        pen = QPen(couleur, EPAISSEUR_CONTOUR)
        pen.setCosmetic(True)  # épaisseur fixe indépendante du zoom
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        pts = [self._dxf_vers_ecran_local(x, y) for x, y in contour]
        if not pts:
            return

        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])
        # Fermeture
        painter.drawLine(pts[-1], pts[0])

        # Marquer le point de départ (petit cercle plein)
        pen_start = QPen(couleur, EPAISSEUR_POINT_DEPART)
        pen_start.setCosmetic(True)
        painter.setPen(pen_start)
        painter.setBrush(couleur)
        r = 4.0 / self._echelle
        painter.drawEllipse(pts[0], r, r)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _dxf_vers_ecran_local(
        self, x: float, y: float
    ) -> QPointF:
        """Convertit des coordonnées DXF en coordonnées locales (Y inversé)."""
        if self._bb is None:
            return QPointF(x, -y)
        # Décaler pour que la BB commence en (0,0) et inverser Y
        _, y_min, _, y_max = self._bb
        return QPointF(x, -(y))

    def _dessiner_infos(self, painter: QPainter) -> None:
        """Affiche les dimensions de la bounding box en bas à gauche."""
        if self._bb is None:
            return
        x_min, y_min, x_max, y_max = self._bb
        w = x_max - x_min
        h = y_max - y_min
        n = len(self._contours)

        texte = f"{n} contour(s) | {w:.1f} × {h:.1f} mm"
        painter.setPen(QPen(COULEUR_TEXTE))
        painter.setFont(QFont("Monospace", 9))
        painter.drawText(8, self.height() - 8, texte)

    def _dessiner_message(self, painter: QPainter, msg: str) -> None:
        """Affiche un message centré."""
        painter.setPen(QPen(QColor(150, 150, 150)))
        painter.setFont(QFont("Sans", 11))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, msg)

    # -----------------------------------------------------------------------
    # Coordonnées
    # -----------------------------------------------------------------------

    def _ajuster_vue(self) -> None:
        """Adapte le zoom et le pan pour afficher tous les contours."""
        if self._bb is None:
            return
        x_min, y_min, x_max, y_max = self._bb
        w_dxf = x_max - x_min
        h_dxf = y_max - y_min

        if w_dxf < 1e-6 or h_dxf < 1e-6:
            return

        w_widget = self.width() - 2 * MARGE_AFFICHAGE
        h_widget = self.height() - 2 * MARGE_AFFICHAGE

        if w_widget <= 0 or h_widget <= 0:
            return

        # Échelle pour faire tenir la BB dans le widget
        echelle_x = w_widget / w_dxf
        echelle_y = h_widget / h_dxf
        self._echelle = min(echelle_x, echelle_y)

        # Centrer
        cx_dxf = (x_min + x_max) / 2
        cy_dxf = (y_min + y_max) / 2
        cx_widget = self.width() / 2
        cy_widget = self.height() / 2

        self._offset = QPointF(
            cx_widget - self._echelle * cx_dxf,
            cy_widget + self._echelle * cy_dxf,  # Y inversé
        )

    def _calculer_bb(
        self,
    ) -> Optional[Tuple[float, float, float, float]]:
        """Calcule la bounding box globale de tous les contours."""
        if not self._contours:
            return None
        pts = [p for c in self._contours for p in c]
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    # -----------------------------------------------------------------------
    # Interactions
    # -----------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom à la molette, centré sur la position de la souris."""
        facteur = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        pos = QPointF(event.position())

        # Zoom centré sur la position souris
        self._offset = QPointF(
            pos.x() + facteur * (self._offset.x() - pos.x()),
            pos.y() + facteur * (self._offset.y() - pos.y()),
        )
        self._echelle *= facteur
        self.update()

    def mousePressEvent(self, event) -> None:
        """Démarre le déplacement par clic-glisser."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
            self._offset_drag = QPointF(self._offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        """Déplace la vue lors d'un glisser."""
        if self._drag_start is not None and self._offset_drag is not None:
            delta = event.pos() - self._drag_start
            self._offset = QPointF(
                self._offset_drag.x() + delta.x(),
                self._offset_drag.y() + delta.y(),
            )
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        """Termine le déplacement."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self._offset_drag = None
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-clic : réinitialiser la vue."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._ajuster_vue()
            self.update()

    def resizeEvent(self, event) -> None:
        """Réadapter la vue lors du redimensionnement."""
        super().resizeEvent(event)
        if self._bb is not None:
            self._ajuster_vue()

"""
ui/nesting_view.py — Visualiseur du nesting sur la tôle.

QWidget avec QPainter :
  - Rectangle de la tôle en gris clair.
  - Pièces placées : contours extérieurs en bleu, trous en rouge.
  - Lead-in en vert clair, lead-out en orange.
  - Déplacements rapides G00 en pointillés verts.
  - Zoom molette, pan clic-glisser.
"""

import logging
import math
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

from core.geometry import (
    calculer_lead_in,
    calculer_lead_out,
    lead_in_polyline,
    lead_out_polyline,
)
from core.nesting import ContourPlace

logger = logging.getLogger(__name__)

# Couleurs
COULEUR_FOND = QColor(240, 240, 240)
COULEUR_TOLE = QColor(255, 255, 255)
COULEUR_BORD_TOLE = QColor(100, 100, 100)
COULEUR_EXTERIEUR = QColor(30, 100, 210)
COULEUR_INTERIEUR = QColor(200, 50, 50)
COULEUR_LEAD_IN = QColor(0, 160, 80)
COULEUR_LEAD_OUT = QColor(230, 120, 0)
COULEUR_DEPLACEMENT_RAPIDE = QColor(50, 180, 50)
COULEUR_TEXTE = QColor(60, 60, 60)
COULEUR_REMPLISSAGE_PROBLEME = QColor(255, 140, 140, 180)  # rouge pâle (piquage impossible)
COULEUR_CONTOUR_PROBLEME = QColor(220, 30, 30)

MARGE_AFFICHAGE = 30


def _couleur_pale_pour_piece(id_piece: int) -> QColor:
    """
    Retourne une couleur pâle déterministe pour une pièce donnée.
    HSL avec luminosité élevée → lisible sans masquer les contours.
    """
    # Teinte répartie par hash stable sur 360°, saturation et luminosité fixes
    hue = (id_piece * 67) % 360     # 67 ≠ diviseur de 360 → bonne répartition
    col = QColor()
    col.setHsl(hue, 140, 225)        # teinte, saturation modérée, luminosité haute
    col.setAlpha(170)                # semi-transparent pour laisser voir les traits
    return col


class NestingView(QWidget):
    """
    Vue de nesting : tôle + contours placés + trajectoires.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._contours_places: List[ContourPlace] = []
        self._largeur_tole: float = 3000.0
        self._hauteur_tole: float = 1500.0
        self._longueur_lead_in: float = 5.0
        self._longueur_lead_out: float = 5.0
        self._type_lead: str = 'lineaire'   # 'lineaire' ou 'arc'

        # Paramètres de vue
        self._echelle: float = 1.0
        self._offset: QPointF = QPointF(0.0, 0.0)
        self._drag_start: Optional[QPoint] = None
        self._offset_drag: Optional[QPointF] = None

        # Position outil (marqueur rouge) — None = non affiché
        self._position_outil: Optional[Tuple[float, float]] = None

        # Afficher les trajectoires (lead-in/out, G00) ?
        # False tant que l'étape "Calculer Trajectoires" n'a pas été lancée.
        self._afficher_trajectoires: bool = False

        self.setMinimumSize(300, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    # -----------------------------------------------------------------------
    # Données
    # -----------------------------------------------------------------------

    def set_afficher_trajectoires(self, actif: bool) -> None:
        """Active/désactive le rendu des lead-in/out et des déplacements G00."""
        self._afficher_trajectoires = bool(actif)
        self.update()

    def set_nesting(
        self,
        contours_places: List[ContourPlace],
        largeur_tole: float,
        hauteur_tole: float,
        longueur_lead_in: float = 5.0,
        longueur_lead_out: float = 5.0,
        type_lead: str = 'lineaire',
    ) -> None:
        """
        Charge les données de nesting à afficher.

        Args:
            contours_places  : Contours placés issus de nesting.placer().
            largeur_tole     : Largeur de la tôle en mm.
            hauteur_tole     : Hauteur de la tôle en mm.
            longueur_lead_in : Pour afficher les points de piquage.
            longueur_lead_out: Pour afficher les points de sortie.
        """
        self._contours_places = contours_places
        self._largeur_tole = largeur_tole
        self._hauteur_tole = hauteur_tole
        self._longueur_lead_in = longueur_lead_in
        self._longueur_lead_out = longueur_lead_out
        self._type_lead = type_lead
        self._ajuster_vue()
        self.update()

    def vider(self) -> None:
        """Efface l'affichage."""
        self._contours_places = []
        self._position_outil = None
        self.update()

    def set_position_outil(self, pos) -> None:
        """
        Définit la position de l'outil à afficher (marqueur rouge).

        Args:
            pos : Tuple (x, y) en mm, ou None pour masquer le marqueur.
        """
        self._position_outil = pos
        self.update()

    # -----------------------------------------------------------------------
    # Peinture
    # -----------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        """Dessin principal."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fond général
        painter.fillRect(self.rect(), COULEUR_FOND)

        painter.save()
        painter.translate(self._offset)
        painter.scale(self._echelle, self._echelle)

        # Tôle
        self._dessiner_tole(painter)

        # Contours et trajectoires
        if self._contours_places:
            # Remplissage pâle par pièce (sous les contours) — règle
            # even-odd pour que les trous soient automatiquement exclus.
            self._dessiner_remplissages(painter)
            if self._afficher_trajectoires:
                self._dessiner_deplacements_rapides(painter)
            for cp in self._contours_places:
                self._dessiner_contour_place(painter, cp)

        # Marqueur position outil (au-dessus de tout le reste)
        if self._position_outil is not None:
            self._dessiner_position_outil(painter)

        painter.restore()

        # Informations textuelles
        self._dessiner_infos(painter)

    def _dessiner_position_outil(self, painter: QPainter) -> None:
        """
        Dessine un marqueur rouge (croix + cercle) à la position outil.

        ATTENTION : les coordonnées reçues proviennent du GCode, où Y est
        déjà inversé par le générateur (`Y{-y_interne}`). On les utilise
        directement en coords "paint" (qui sont Y-bas) — pas de ré-inversion,
        sinon le marqueur apparaît en miroir par rapport aux contours.
        """
        x, y = self._position_outil
        pt = QPointF(x, y)

        # Cercle rouge plein
        couleur_fond = QColor(255, 40, 40, 220)
        painter.setBrush(couleur_fond)
        pen_c = QPen(QColor(140, 0, 0), 1.5)
        pen_c.setCosmetic(True)
        painter.setPen(pen_c)
        r = 6.0 / self._echelle
        painter.drawEllipse(pt, r, r)

        # Croix noire au centre
        from PyQt6.QtCore import Qt as Qt2
        painter.setBrush(Qt2.BrushStyle.NoBrush)
        pen_x = QPen(QColor(20, 20, 20), 1.8)
        pen_x.setCosmetic(True)
        painter.setPen(pen_x)
        rx = 10.0 / self._echelle
        painter.drawLine(QPointF(pt.x() - rx, pt.y()), QPointF(pt.x() + rx, pt.y()))
        painter.drawLine(QPointF(pt.x(), pt.y() - rx), QPointF(pt.x(), pt.y() + rx))

    def _dessiner_tole(self, painter: QPainter) -> None:
        """Dessine le rectangle de la tôle."""
        from PyQt6.QtCore import QRectF
        # La tôle part de (0,0) en interne, affichée avec Y inversé
        # (0,0) = coin bas-gauche interne → coin haut-gauche écran
        rect = QRectF(0, -self._hauteur_tole, self._largeur_tole, self._hauteur_tole)
        painter.fillRect(rect, COULEUR_TOLE)
        pen = QPen(COULEUR_BORD_TOLE, 2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(rect)

    def _id_pieces_problematiques(self) -> set:
        """Retourne l'ensemble des id_piece dont au moins un contour a probleme_piquage."""
        return {
            cp.id_piece for cp in self._contours_places
            if getattr(cp, 'probleme_piquage', False)
        }

    def _dessiner_remplissages(self, painter: QPainter) -> None:
        """
        Remplit l'intérieur de chaque pièce avec une couleur pâle dédiée
        (une couleur par id_piece). Les trous sont automatiquement exclus
        grâce à la règle de remplissage even-odd.
        Les pièces dont le piquage n'a pas pu être placé sont rouge pâle.
        """
        # Regrouper tous les contours (ext + trous) par id_piece
        par_piece: dict = {}
        for cp in self._contours_places:
            par_piece.setdefault(cp.id_piece, []).append(cp)

        problematiques = self._id_pieces_problematiques()
        painter.setPen(Qt.PenStyle.NoPen)

        for id_p, contours in par_piece.items():
            path = QPainterPath()
            path.setFillRule(Qt.FillRule.OddEvenFill)
            for cp in contours:
                if len(cp.points) < 3:
                    continue
                pts = [QPointF(x, -y) for x, y in cp.points]
                sub = QPainterPath()
                sub.moveTo(pts[0])
                for p in pts[1:]:
                    sub.lineTo(p)
                sub.closeSubpath()
                path.addPath(sub)

            if id_p in problematiques:
                couleur = COULEUR_REMPLISSAGE_PROBLEME
            else:
                couleur = _couleur_pale_pour_piece(id_p)
            painter.setBrush(QBrush(couleur))
            painter.drawPath(path)

    def _dessiner_contour_place(
        self, painter: QPainter, cp: ContourPlace
    ) -> None:
        """Dessine un contour placé avec lead-in/lead-out."""
        if len(cp.points) < 2:
            return

        probleme = getattr(cp, 'probleme_piquage', False)

        # --- Contour principal ---
        if probleme:
            couleur = COULEUR_CONTOUR_PROBLEME
        else:
            couleur = COULEUR_INTERIEUR if cp.est_interieur else COULEUR_EXTERIEUR
        pen = QPen(couleur, 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        pts = [QPointF(x, -y) for x, y in cp.points]
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])
        painter.drawLine(pts[-1], pts[0])  # fermeture

        if not self._afficher_trajectoires:
            return

        # --- Lead-in (polyline : linéaire = 2 pts, arc = N pts) ---
        try:
            poly_in = lead_in_polyline(
                cp.points, self._longueur_lead_in, self._type_lead, cp.est_interieur
            )
            if len(poly_in) >= 2:
                pen_li = QPen(COULEUR_LEAD_IN, 1.5)
                pen_li.setCosmetic(True)
                painter.setPen(pen_li)
                pts_in = [QPointF(x, -y) for x, y in poly_in]
                for i in range(len(pts_in) - 1):
                    painter.drawLine(pts_in[i], pts_in[i + 1])
                # Croix au point de piquage (début de la polyline)
                self._dessiner_croix(painter, pts_in[0], COULEUR_LEAD_IN)
        except Exception:
            pass

        # --- Lead-out (polyline) ---
        try:
            poly_out = lead_out_polyline(
                cp.points, self._longueur_lead_out, self._type_lead, cp.est_interieur
            )
            if len(poly_out) >= 2:
                pen_lo = QPen(COULEUR_LEAD_OUT, 1.5)
                pen_lo.setCosmetic(True)
                painter.setPen(pen_lo)
                pts_out = [QPointF(x, -y) for x, y in poly_out]
                for i in range(len(pts_out) - 1):
                    painter.drawLine(pts_out[i], pts_out[i + 1])
                # Croix au point de dégagement (fin de la polyline)
                self._dessiner_croix(painter, pts_out[-1], COULEUR_LEAD_OUT)
        except Exception:
            pass

    def _dessiner_deplacements_rapides(self, painter: QPainter) -> None:
        """
        Dessine les déplacements rapides G00 entre les contours (pointillés verts).
        """
        pen = QPen(COULEUR_DEPLACEMENT_RAPIDE, 1.0)
        from PyQt6.QtCore import Qt as Qt2
        pen.setStyle(Qt2.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)

        pos_courante = QPointF(0.0, 0.0)  # origine machine

        for cp in self._contours_places:
            if not cp.points:
                continue
            try:
                piquage, _ = calculer_lead_in(cp.points, self._longueur_lead_in)
                dest = QPointF(piquage[0], -piquage[1])
            except Exception:
                dest = QPointF(cp.points[0][0], -cp.points[0][1])

            painter.drawLine(pos_courante, dest)
            pos_courante = QPointF(cp.points[0][0], -cp.points[0][1])

    def _dessiner_croix(
        self, painter: QPainter, pt: QPointF, couleur: QColor
    ) -> None:
        """Dessine une petite croix au point donné."""
        pen = QPen(couleur, 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        r = 4.0 / self._echelle
        painter.drawLine(QPointF(pt.x() - r, pt.y()), QPointF(pt.x() + r, pt.y()))
        painter.drawLine(QPointF(pt.x(), pt.y() - r), QPointF(pt.x(), pt.y() + r))

    def _dessiner_infos(self, painter: QPainter) -> None:
        """Affiche les informations de nesting en bas à gauche."""
        n_pieces = len(set(cp.id_piece for cp in self._contours_places))
        n_contours = len(self._contours_places)
        texte = (
            f"Tôle : {self._largeur_tole:.0f} × {self._hauteur_tole:.0f} mm  |  "
            f"{n_pieces} pièce(s)  |  {n_contours} contour(s)"
        )
        painter.setPen(QPen(COULEUR_TEXTE))
        painter.setFont(QFont("Monospace", 9))
        painter.drawText(8, self.height() - 8, texte)

    # -----------------------------------------------------------------------
    # Vue
    # -----------------------------------------------------------------------

    def _ajuster_vue(self) -> None:
        """Adapte le zoom pour afficher toute la tôle, centrée dans le widget."""
        if self._largeur_tole <= 0 or self._hauteur_tole <= 0:
            return

        w_widget = self.width() - 2 * MARGE_AFFICHAGE
        h_widget = self.height() - 2 * MARGE_AFFICHAGE

        if w_widget <= 0 or h_widget <= 0:
            return

        echelle_x = w_widget / self._largeur_tole
        echelle_y = h_widget / self._hauteur_tole
        self._echelle = min(echelle_x, echelle_y)

        # La tôle occupe en coords internes : X ∈ [0, largeur], Y ∈ [-hauteur, 0]
        # (Y est inversé pour que le dessin matche l'écran).
        # Son centre interne est donc à (largeur/2, -hauteur/2).
        cx_dxf = self._largeur_tole / 2.0
        cy_dxf = -self._hauteur_tole / 2.0
        cx_widget = self.width() / 2.0
        cy_widget = self.height() / 2.0

        # Transform appliqué : screen = offset + échelle * interne
        # → pour que centre interne = centre widget :
        self._offset = QPointF(
            cx_widget - self._echelle * cx_dxf,
            cy_widget - self._echelle * cy_dxf,
        )

    # -----------------------------------------------------------------------
    # Interactions
    # -----------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom centré sur la position souris."""
        facteur = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        pos = QPointF(event.position())
        self._offset = QPointF(
            pos.x() + facteur * (self._offset.x() - pos.x()),
            pos.y() + facteur * (self._offset.y() - pos.y()),
        )
        self._echelle *= facteur
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
            self._offset_drag = QPointF(self._offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is not None and self._offset_drag is not None:
            delta = event.pos() - self._drag_start
            self._offset = QPointF(
                self._offset_drag.x() + delta.x(),
                self._offset_drag.y() + delta.y(),
            )
            self.update()

    def mouseReleaseEvent(self, event) -> None:
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
        super().resizeEvent(event)
        self._ajuster_vue()
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._ajuster_vue()
        self.update()

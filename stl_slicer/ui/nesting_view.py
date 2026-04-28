# =============================================================================
# ui/nesting_view.py — Widget de visualisation et d'édition du nesting 2D
#
# Fonctionnalités :
#   - Dessin vectoriel QPainter des contours placés sur la plaque
#   - Zoom centré sur la souris (molette)
#   - Panoramique (déplacement de la vue) : clic droit + glisser
#   - Déplacement interactif des sections : clic gauche sur une pièce + glisser
#   - Rotation des sections : Ctrl + clic gauche + glisser (gauche/droite)
#   - Double-clic : réinitialiser la vue (zoom=1, pan=0)
#   - Mise à jour en temps réel de self._placements (partagé avec MainWindow)
# =============================================================================

import math

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPointF, QRectF, QPoint
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QCursor
)
from shapely.geometry import Point, Polygon
from shapely.affinity import translate, rotate
from typing import List, Tuple, Optional


# Palette de couleurs pour distinguer les sections (cyclique)
COULEURS = [
    '#4FC3F7', '#81C784', '#FFB74D', '#F48FB1',
    '#CE93D8', '#80CBC4', '#FFCC02', '#FF8A65',
    '#90CAF9', '#A5D6A7', '#FFAB91', '#B39DDB',
]


# =============================================================================
# Helpers géométriques pour le rendu Qt des arcs
# =============================================================================

def _arc_qt_angles(p_start: Tuple[float, float],
                   p_end:   Tuple[float, float],
                   p_mid:   Tuple[float, float],
                   cx: float, cy: float) -> Tuple[float, float]:
    """
    Convertit un arc (p_start → p_mid → p_end) autour de (cx, cy) en angles
    (start_deg, span_deg) compatibles avec QPainterPath.arcTo / QPainter.drawArc.

    Convention Qt :
      - 0° = 3 h (positif X)
      - Positif = sens anti-horaire VISUEL à l'écran
    Convention shapely :
      - Y croît vers le haut (sens anti-horaire mathématique)
    Comme la vue effectue une symétrie Y à l'affichage, un arc parcouru en sens
    anti-horaire dans shapely est aussi anti-horaire VISUELLEMENT à l'écran.
    Les angles atan2 calculés directement sur (y - cy, x - cx) shapely sont
    donc utilisables tels quels par Qt.
    """
    a_s = math.atan2(p_start[1] - cy, p_start[0] - cx)
    a_m = math.atan2(p_mid[1]   - cy, p_mid[0]   - cx)
    a_e = math.atan2(p_end[1]   - cy, p_end[0]   - cx)

    two_pi = 2.0 * math.pi
    d_mid_ccw = (a_m - a_s) % two_pi
    d_end_ccw = (a_e - a_s) % two_pi

    if d_mid_ccw < d_end_ccw:
        # Arc parcouru en CCW (shapely sens trigo) → CCW visuel → Qt positif
        span = d_end_ccw
    else:
        # Arc parcouru en CW → Qt négatif
        span = -(two_pi - d_end_ccw)

    return math.degrees(a_s), math.degrees(span)


class NestingView(QWidget):
    """
    Widget QPainter pour afficher et éditer interactivement le plan de nesting.

    Système de coordonnées :
      - Shapely (mm) : Y croît vers le haut
      - Écran (px)   : Y croît vers le bas
      → Conversion : py = base_oy + pan_y + (hauteur_plaque - y_mm) * echelle * zoom
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 200)
        self.setStyleSheet("background-color: #1a1a2e;")
        self.setMouseTracking(True)

        # --- Données de la plaque et des placements ---
        self._largeur_plaque = 0.0
        self._hauteur_plaque = 0.0
        self._placements: List[Tuple] = []   # (poly, ox, oy, idx_orig)
        self._nb_non_places = 0

        # --- Transform de base (recalculé à chaque resize / définition plaque) ---
        self._base_echelle = 1.0     # px/mm sans zoom
        self._base_ox = 30.0         # offset X de la plaque (px) sans pan
        self._base_oy = 30.0         # offset Y de la plaque (px) sans pan

        # --- Zoom et panoramique ---
        self._zoom = 1.0             # facteur de zoom courant (1 = ajusté à la fenêtre)
        self._pan_dx = 0.0           # décalage horizontal en pixels (panoramique)
        self._pan_dy = 0.0           # décalage vertical en pixels (panoramique)

        # --- État drag panoramique (clic droit) ---
        self._pan_actif = False
        self._pan_pos_prec = QPoint(0, 0)

        # --- État drag section — translation (clic gauche) ---
        self._drag_idx: Optional[int] = None
        self._drag_mm_prec: Tuple[float, float] = (0.0, 0.0)

        # --- État rotation section (Ctrl + clic gauche + glisser) ---
        # Un pixel de déplacement horizontal = DEG_PAR_PIXEL degrés de rotation
        self._rotate_idx: Optional[int] = None
        self._rotate_x_prec: float = 0.0       # position X écran au dernier event
        self._rotate_angle_cumul: float = 0.0  # angle total accumulé depuis le début du drag
        self._rotate_poly_initial = None        # polygone avant début de la rotation
        self._rotate_mouse_x: float = 0.0      # position souris X courante (pour affichage)
        self._rotate_mouse_y: float = 0.0      # position souris Y courante (pour affichage)
        self.DEG_PAR_PIXEL = 0.4               # sensibilité : 0.4°/pixel

        # --- Contrainte d'espacement ---
        self._espacement: float = 0.0          # distance minimum entre pièces (mm)
        self._espacement_bord: float = 0.0     # distance minimum pièces/bord (mm)
        self._drag_bloque: bool = False         # True si le dernier mouvement a été bloqué

        # --- Prévisualisation du lissage (None = désactivée) ---
        # Parallèle à _placements. Pour chaque placement i, _entites_lisses[i] est
        # la structure retournée par core.lissage.lisser_polygone :
        #   [entites_anneau_ext, entites_trou_1, ...]
        # où chaque liste d'entités contient des tuples ('line', p0, p1),
        # ('arc', (cx,cy), r, p_start, p_end, p_mid) ou ('circle', (cx,cy), r).
        self._entites_lisses: Optional[List[List[list]]] = None

    # =========================================================================
    # Méthodes publiques
    # =========================================================================

    def definir_plaque(self, largeur: float, hauteur: float):
        """Définit les dimensions de la plaque et réinitialise la vue."""
        self._largeur_plaque = largeur
        self._hauteur_plaque = hauteur
        self._reinitialiser_vue()
        self.update()

    def definir_espacement(self, espacement: float):
        """Définit l'espacement minimum entre pièces (déplacements manuels)."""
        self._espacement = max(0.0, espacement)

    def definir_espacement_bord(self, espacement_bord: float):
        """Définit l'espacement minimum pièces/bord (déplacements manuels)."""
        self._espacement_bord = max(0.0, espacement_bord)

    def definir_placements(self, placements: list, nb_non_places: int = 0):
        """
        Définit les placements à afficher.
        Attention : stocke une RÉFÉRENCE à la liste — les modifications
        effectuées par glisser-déposer se reflèteront directement dans
        la liste de MainWindow utilisée pour l'export.
        """
        self._placements = placements
        self._nb_non_places = nb_non_places
        # Une nouvelle liste de placements invalide toute prévisualisation de lissage
        self._entites_lisses = None
        self.update()

    def definir_entites_lisses(self, entites_par_placement: Optional[list]):
        """
        Active/met à jour la prévisualisation du lissage.

        Paramètre :
            entites_par_placement :
              - None              → désactive la prévisualisation (affichage normal)
              - liste parallèle à _placements : pour chaque placement, la
                structure [entites_anneau_ext, entites_trou_1, ...]
        """
        self._entites_lisses = entites_par_placement
        self.update()

    def effacer_lissage(self):
        """Désactive la prévisualisation du lissage."""
        self._entites_lisses = None
        self.update()

    def effacer(self):
        """Remet le widget à l'état vide et réinitialise la vue."""
        self._placements = []
        self._largeur_plaque = 0.0
        self._hauteur_plaque = 0.0
        self._nb_non_places = 0
        self._entites_lisses = None
        self._reinitialiser_vue()
        self.update()

    # =========================================================================
    # Gestion des événements souris
    # =========================================================================

    def wheelEvent(self, event):
        """Zoom centré sur la position de la souris."""
        if self._largeur_plaque <= 0:
            event.accept()
            return

        facteur = 1.20 if event.angleDelta().y() > 0 else 1.0 / 1.20
        # Plage de zoom large : 0.02 × (dézoom extrême) → 2000 × (vue microscopique
        # sur un arc pour valider le lissage à la précision près).
        nouveau_zoom = max(0.02, min(2000.0, self._zoom * facteur))

        # Garder le point sous la souris fixe visuellement
        mx = event.position().x()
        my = event.position().y()
        self._calculer_base_transform()
        ratio = nouveau_zoom / self._zoom
        # Formule zoom-vers-curseur :
        # pan_new = (cursor - base_offset) * (1 - ratio) + pan_old * ratio
        self._pan_dx = (mx - self._base_ox) * (1.0 - ratio) + self._pan_dx * ratio
        self._pan_dy = (my - self._base_oy) * (1.0 - ratio) + self._pan_dy * ratio
        self._zoom = nouveau_zoom

        self.update()
        event.accept()

    def mousePressEvent(self, event):
        """
        Clic droit ou milieu    → panoramique (déplacer la vue)
        Clic gauche             → déplacer la section sous le curseur
        Ctrl + clic gauche      → faire tourner la section sous le curseur
        """
        self._calculer_base_transform()
        ctrl_presse = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._pan_actif = True
            self._pan_pos_prec = event.position().toPoint()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

        elif event.button() == Qt.MouseButton.LeftButton:
            x_mm, y_mm = self._ecran_vers_mm(
                event.position().x(), event.position().y()
            )
            idx = self._hit_test(x_mm, y_mm)

            if ctrl_presse:
                # Mode rotation : Ctrl maintenu
                self._rotate_idx = idx
                self._rotate_x_prec = event.position().x()
                self._rotate_angle_cumul = 0.0
                self._rotate_mouse_x = event.position().x()
                self._rotate_mouse_y = event.position().y()
                # Mémoriser le polygone initial pour appliquer une rotation absolue
                if idx is not None:
                    self._rotate_poly_initial = self._placements[idx][0]
                else:
                    self._rotate_poly_initial = None
                self._drag_idx = None
                if idx is not None:
                    self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            else:
                # Mode translation normal
                self._drag_idx = idx
                self._drag_mm_prec = (x_mm, y_mm)
                self._rotate_idx = None
                if idx is not None:
                    self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))

        event.accept()

    def mouseMoveEvent(self, event):
        """Panoramique, déplacement ou rotation selon le mode actif."""
        if self._pan_actif:
            # --- Panoramique ---
            pos = event.position().toPoint()
            self._pan_dx += pos.x() - self._pan_pos_prec.x()
            self._pan_dy += pos.y() - self._pan_pos_prec.y()
            self._pan_pos_prec = pos
            self.update()

        elif self._rotate_idx is not None:
            # --- Rotation 1°/pixel (Ctrl + glisser gauche/droite) ---
            # dx positif (vers la droite) → rotation horaire en vue écran
            # En shapely (Y vers le haut), la rotation horaire est négative.
            dx = event.position().x() - self._rotate_x_prec
            delta_deg = -dx * self.DEG_PAR_PIXEL
            self._rotate_x_prec = event.position().x()
            self._rotate_mouse_x = event.position().x()
            self._rotate_mouse_y = event.position().y()

            if delta_deg != 0.0 and self._rotate_poly_initial is not None:
                self._rotate_angle_cumul += delta_deg
                # Arrondir à 1° pour un pas net
                angle_entier = round(self._rotate_angle_cumul)
                shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self._appliquer_rotation_snappee(self._rotate_idx, angle_entier,
                                                 force=shift)
                self.update()

        elif self._drag_idx is not None:
            # --- Translation ---
            self._calculer_base_transform()
            x_mm, y_mm = self._ecran_vers_mm(
                event.position().x(), event.position().y()
            )
            dx = x_mm - self._drag_mm_prec[0]
            dy = y_mm - self._drag_mm_prec[1]
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._deplacer_section(self._drag_idx, dx, dy, force=shift)
            # Toujours avancer le point de référence pour que le drag
            # reste fluide et réactif dès que le blocage est levé.
            self._drag_mm_prec = (x_mm, y_mm)
            self.update()

        event.accept()

    def mouseReleaseEvent(self, event):
        """Termine le panoramique, la translation ou la rotation."""
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._pan_actif = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        elif event.button() == Qt.MouseButton.LeftButton:
            self._drag_idx = None
            self._rotate_idx = None
            self._rotate_poly_initial = None
            self._drag_bloque = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        event.accept()

    def mouseDoubleClickEvent(self, event):
        """Double-clic → réinitialiser la vue (zoom + pan)."""
        self._reinitialiser_vue()
        self.update()
        event.accept()

    def resizeEvent(self, event):
        """Recalcule la transform de base quand la fenêtre est redimensionnée."""
        self._calculer_base_transform()
        super().resizeEvent(event)

    # =========================================================================
    # Dessin QPainter
    # =========================================================================

    def paintEvent(self, event):
        """Dessine le fond, la plaque, les contours et la légende."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fond
        painter.fillRect(self.rect(), QColor('#1a1a2e'))

        if self._largeur_plaque <= 0 or self._hauteur_plaque <= 0:
            # Message d'invite si aucune plaque définie
            painter.setPen(QPen(QColor('#555577')))
            painter.setFont(QFont('Segoe UI', 12))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "Calculez le nesting pour voir la répartition\n\n"
                "Molette : zoom  |  Clic droit ou milieu : panoramique\n"
                "Clic gauche : déplacer une section\n"
                "Ctrl + clic gauche : faire tourner une section (pas 1°)\n"
                "Double-clic : réinitialiser la vue"
            )
            painter.end()
            return

        # Recalcul du transform de base
        self._calculer_base_transform()

        # Coordonnées de la plaque à l'écran (avec zoom + pan)
        e = self._base_echelle * self._zoom
        ox = self._base_ox + self._pan_dx
        oy = self._base_oy + self._pan_dy
        plaque_px_w = self._largeur_plaque * e
        plaque_px_h = self._hauteur_plaque * e

        # --- Plaque ---
        painter.setPen(QPen(QColor('#6666aa'), 1.5))
        painter.setBrush(QBrush(QColor('#22223a')))
        painter.drawRect(QRectF(ox, oy, plaque_px_w, plaque_px_h))

        # --- Grille légère (tous les 100 mm) ---
        self._dessiner_grille(painter, ox, oy, e)

        # --- Passe 1 : contours et fonds des sections ---
        use_lissage = (self._entites_lisses is not None
                       and len(self._entites_lisses) == len(self._placements))
        for i, (poly, _ox_mm, _oy_mm, idx_original) in enumerate(self._placements):
            est_selectionne = (i == self._drag_idx)
            en_rotation     = (i == self._rotate_idx)
            est_bloque      = self._drag_bloque and (est_selectionne or en_rotation)
            couleur         = COULEURS[i % len(COULEURS)]
            if use_lissage:
                self._dessiner_polygone_lisse(
                    painter, self._entites_lisses[i], e, ox, oy,
                    couleur, est_selectionne, en_rotation, est_bloque
                )
            else:
                self._dessiner_polygone(
                    painter, poly, e, ox, oy,
                    couleur,
                    est_selectionne,
                    en_rotation,
                    est_bloque
                )

        # --- Passe 2 : numéros de section (toujours au premier plan) ---
        for i, (poly, _ox_mm, _oy_mm, idx_original) in enumerate(self._placements):
            self._dessiner_numero(painter, poly, e, ox, oy, i + 1)

        # --- Boîte englobante des sections ---
        if self._placements:
            self._dessiner_bbox_sections(painter, e, ox, oy)

        # --- Angle de rotation affiché près du curseur ---
        if self._rotate_idx is not None:
            self._dessiner_angle_rotation(painter)

        # --- Légende ---
        self._dessiner_legende(painter, ox, oy + plaque_px_h)

        # --- Tooltip de navigation ---
        self._dessiner_aide(painter)

        painter.end()

    # =========================================================================
    # Méthodes de dessin internes
    # =========================================================================

    def _dessiner_grille(self, painter: QPainter, ox: float, oy: float, e: float):
        """Dessine une grille discrète (tous les 100 mm ou 50 mm) sur la plaque."""
        pas = 100.0  # mm
        if self._largeur_plaque < 200 or self._hauteur_plaque < 200:
            pas = 50.0

        painter.setPen(QPen(QColor('#333355'), 0.5, Qt.PenStyle.DotLine))

        x = pas
        while x < self._largeur_plaque:
            px = ox + x * e
            painter.drawLine(
                QPointF(px, oy),
                QPointF(px, oy + self._hauteur_plaque * e)
            )
            x += pas

        y = pas
        while y < self._hauteur_plaque:
            py = oy + (self._hauteur_plaque - y) * e
            painter.drawLine(
                QPointF(ox, py),
                QPointF(ox + self._largeur_plaque * e, py)
            )
            y += pas

    def _dessiner_polygone(
        self,
        painter: QPainter,
        poly: Polygon,
        e: float,
        ox: float,
        oy: float,
        couleur_hex: str,
        selectionne: bool = False,
        en_rotation: bool = False,
        bloque: bool = False
    ):
        """
        Dessine uniquement le contour et le fond d'un polygone shapely.
        Le numéro est dessiné séparément (passe 2) pour rester au premier plan.
        - selectionne  : translation en cours → fond semi-opaque + bordure épaisse
        - en_rotation  : rotation en cours   → bordure pointillée orange + fond chaud
        - bloque       : mouvement refusé (espacement) → bordure et fond rouges
        """
        couleur = QColor(couleur_hex)
        if bloque:
            # Rouge : mouvement bloqué par contrainte d'espacement
            pen = QPen(QColor('#EF5350'), 2.5, Qt.PenStyle.SolidLine)
            couleur_fond = QColor(239, 83, 80, 120)
        elif en_rotation:
            pen = QPen(QColor('#FFA726'), 2.2, Qt.PenStyle.DashLine)
            couleur_fond = QColor(255, 167, 38, 110)
        elif selectionne:
            pen = QPen(couleur, 2.5)
            couleur_fond = QColor(couleur.red(), couleur.green(), couleur.blue(), 130)
        else:
            pen = QPen(couleur, 1.2)
            couleur_fond = QColor(couleur.red(), couleur.green(), couleur.blue(), 55)

        painter.setPen(pen)
        painter.setBrush(QBrush(couleur_fond))

        # --- Contour extérieur ---
        coords_ext = list(poly.exterior.coords)
        if len(coords_ext) < 2:
            return

        path = QPainterPath()
        premier = True
        for x_mm, y_mm in coords_ext:
            px = ox + x_mm * e
            py = oy + (self._hauteur_plaque - y_mm) * e
            if premier:
                path.moveTo(px, py)
                premier = False
            else:
                path.lineTo(px, py)
        path.closeSubpath()

        # --- Trous intérieurs (cas pièces creuses) ---
        for interior in poly.interiors:
            coords_int = list(interior.coords)
            if len(coords_int) < 2:
                continue
            sous = QPainterPath()
            p2 = True
            for x_mm, y_mm in coords_int:
                px = ox + x_mm * e
                py = oy + (self._hauteur_plaque - y_mm) * e
                if p2:
                    sous.moveTo(px, py)
                    p2 = False
                else:
                    sous.lineTo(px, py)
            sous.closeSubpath()
            path = path.subtracted(sous)

        painter.drawPath(path)

    def _dessiner_polygone_lisse(
        self,
        painter: QPainter,
        anneaux_entites: list,
        e: float,
        ox: float,
        oy: float,
        couleur_hex: str,
        selectionne: bool = False,
        en_rotation: bool = False,
        bloque: bool = False
    ):
        """
        Dessine un polygone depuis sa liste d'entités lissées
        (retournée par core.lissage.lisser_polygone).

        Entités supportées :
          ('line',   p0, p1)                                → lineTo
          ('arc',    (cx,cy), r, p_start, p_end, p_mid)     → arcTo
          ('circle', (cx,cy), r)                            → addEllipse

        Rendu en deux passes :
          1. Chemin complet (fond + contour) avec un pen « normal ».
          2. Sur-tracé des arcs et cercles avec un pen plus épais, pour
             faire ressortir visuellement les zones lissées.

        Un anneau composé d'un unique 'circle' est rendu comme cercle plein.
        Les arcs en milieu de polyligne sont rendus via QPainterPath.arcTo.
        Les trous (anneaux intérieurs) sont soustraits du chemin extérieur.
        """
        couleur = QColor(couleur_hex)
        if bloque:
            pen_base   = QPen(QColor('#EF5350'), 2.5, Qt.PenStyle.SolidLine)
            pen_courbe = QPen(QColor('#EF5350'), 4.0, Qt.PenStyle.SolidLine)
            couleur_fond = QColor(239, 83, 80, 120)
        elif en_rotation:
            pen_base   = QPen(QColor('#FFA726'), 2.2, Qt.PenStyle.DashLine)
            pen_courbe = QPen(QColor('#FFA726'), 3.5, Qt.PenStyle.SolidLine)
            couleur_fond = QColor(255, 167, 38, 110)
        elif selectionne:
            pen_base   = QPen(couleur, 2.5)
            pen_courbe = QPen(couleur, 4.0)
            couleur_fond = QColor(couleur.red(), couleur.green(),
                                  couleur.blue(), 130)
        else:
            # Lignes fines (identiques au rendu normal), arcs/cercles
            # épaissis pour que la partie lissée saute aux yeux.
            pen_base   = QPen(couleur, 1.2)
            pen_courbe = QPen(couleur, 3.0)
            couleur_fond = QColor(couleur.red(), couleur.green(),
                                  couleur.blue(), 55)
        pen_courbe.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen_courbe.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        # --- Passe 1 : fond + trait fin sur tout le contour ---
        painter.setPen(pen_base)
        painter.setBrush(QBrush(couleur_fond))

        path_total = QPainterPath()
        for ring_idx, entites in enumerate(anneaux_entites):
            if not entites:
                continue
            sub = self._construire_path_anneau(entites, e, ox, oy)
            if sub.isEmpty():
                continue
            if ring_idx == 0:
                path_total.addPath(sub)
            else:
                # Anneau intérieur → trou : soustraction
                path_total = path_total.subtracted(sub)

        painter.drawPath(path_total)

        # --- Passe 2 : sur-tracé épaissi des arcs et cercles seulement ---
        painter.setPen(pen_courbe)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for entites in anneaux_entites:
            for ent in entites:
                if ent[0] == 'arc':
                    _, (cx, cy), r, p_start, p_end, p_mid = ent
                    cx_px = ox + cx * e
                    cy_px = oy + (self._hauteur_plaque - cy) * e
                    r_px  = r * e
                    rect  = QRectF(cx_px - r_px, cy_px - r_px,
                                   2.0 * r_px, 2.0 * r_px)
                    start_deg, span_deg = _arc_qt_angles(
                        p_start, p_end, p_mid, cx, cy
                    )
                    # QPainter.drawArc : angles en 1/16 de degré
                    painter.drawArc(rect,
                                    int(round(start_deg * 16)),
                                    int(round(span_deg * 16)))
                elif ent[0] == 'circle':
                    _, (cx, cy), r = ent
                    cx_px = ox + cx * e
                    cy_px = oy + (self._hauteur_plaque - cy) * e
                    r_px  = r * e
                    painter.drawEllipse(QPointF(cx_px, cy_px), r_px, r_px)

    def _construire_path_anneau(self, entites: list,
                                 e: float, ox: float, oy: float) -> QPainterPath:
        """
        Construit un QPainterPath fermé représentant un anneau d'entités
        (lignes/arcs/cercles). Les coordonnées shapely (Y croissant vers
        le haut) sont transformées en coordonnées écran (Y croissant vers
        le bas).
        """
        sub = QPainterPath()

        # Cas spécial : un seul cercle pour tout l'anneau
        if len(entites) == 1 and entites[0][0] == 'circle':
            _, (cx, cy), r = entites[0]
            cx_px = ox + cx * e
            cy_px = oy + (self._hauteur_plaque - cy) * e
            r_px  = r * e
            sub.addEllipse(QPointF(cx_px, cy_px), r_px, r_px)
            return sub

        # Point de départ de l'anneau = premier point de la première entité
        ent0 = entites[0]
        if ent0[0] == 'line':
            x0, y0 = ent0[1]
        elif ent0[0] == 'arc':
            x0, y0 = ent0[3]        # p_start
        else:  # 'circle' au milieu d'un mélange — rare
            _, (cx, cy), r = ent0
            # Démarrer à (cx + r, cy) comme point arbitraire
            x0, y0 = cx + r, cy

        px0 = ox + x0 * e
        py0 = oy + (self._hauteur_plaque - y0) * e
        sub.moveTo(px0, py0)

        for ent in entites:
            typ = ent[0]

            if typ == 'line':
                _, _p0, p1 = ent
                x1, y1 = p1
                px1 = ox + x1 * e
                py1 = oy + (self._hauteur_plaque - y1) * e
                sub.lineTo(px1, py1)

            elif typ == 'arc':
                _, (cx, cy), r, p_start, p_end, p_mid = ent
                cx_px = ox + cx * e
                cy_px = oy + (self._hauteur_plaque - cy) * e
                r_px  = r * e
                rect  = QRectF(cx_px - r_px, cy_px - r_px,
                               2.0 * r_px, 2.0 * r_px)
                start_deg, span_deg = _arc_qt_angles(
                    p_start, p_end, p_mid, cx, cy
                )
                # arcTo ajoute automatiquement une ligne de la position
                # courante vers le début de l'arc s'il y a un écart.
                sub.arcTo(rect, start_deg, span_deg)

            elif typ == 'circle':
                # Cercle imbriqué dans une polyligne : cas rare → ajouter
                # comme sous-ellipse indépendante (n'affecte pas le tracé
                # courant, mais sera quand même affiché).
                _, (cx, cy), r = ent
                cx_px = ox + cx * e
                cy_px = oy + (self._hauteur_plaque - cy) * e
                r_px  = r * e
                sub.addEllipse(QPointF(cx_px, cy_px), r_px, r_px)

        sub.closeSubpath()
        return sub

    def _dessiner_numero(
        self,
        painter: QPainter,
        poly: Polygon,
        e: float,
        ox: float,
        oy: float,
        numero: int
    ):
        """
        Dessine le numéro de section au centre du polygone.
        Appelé en passe 2 (après tous les polygones) pour rester au premier plan.
        Le brush est explicitement désactivé pour éviter tout rectangle de fond.
        """
        cx_mm = (poly.bounds[0] + poly.bounds[2]) / 2
        cy_mm = (poly.bounds[1] + poly.bounds[3]) / 2
        cx = ox + cx_mm * e
        cy = oy + (self._hauteur_plaque - cy_mm) * e

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setBackgroundMode(Qt.BGMode.TransparentMode)
        painter.setPen(QPen(Qt.GlobalColor.white))
        # Taille bornée à 36 pt pour éviter un texte géant aux forts zooms
        taille_fonte = max(7, min(36, int(9 * self._zoom)))
        painter.setFont(QFont('Segoe UI', taille_fonte, QFont.Weight.Bold))
        painter.drawText(
            QRectF(cx - 20, cy - 11, 40, 22),
            Qt.AlignmentFlag.AlignCenter,
            str(numero)
        )

    def _dessiner_angle_rotation(self, painter: QPainter):
        """
        Affiche l'angle de rotation courant (en degrés entiers) près du curseur
        pendant une opération Ctrl+drag. Fond semi-transparent pour lisibilité.
        Rouge si le mouvement est bloqué par l'espacement.
        """
        angle = round(self._rotate_angle_cumul)
        texte = f"{angle:+d}°"
        if self._drag_bloque:
            texte += "  ⛔"

        mx = self._rotate_mouse_x + 14
        my = self._rotate_mouse_y - 20

        painter.setBrush(QBrush(QColor(0, 0, 0, 160)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(mx - 4, my - 14, 80, 20), 4, 4)

        couleur_texte = QColor('#EF5350') if self._drag_bloque else QColor('#FFA726')
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setBackgroundMode(Qt.BGMode.TransparentMode)
        painter.setPen(QPen(couleur_texte))
        painter.setFont(QFont('Segoe UI', 10, QFont.Weight.Bold))
        painter.drawText(QRectF(mx, my - 14, 76, 20),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         texte)

    def _dessiner_bbox_sections(self, painter: QPainter,
                                e: float, ox: float, oy: float):
        """
        Dessine la boîte englobante minimale de toutes les sections placées,
        et affiche ses dimensions (L × H) et son aire.

        La boîte est tracée en pointillés jaunes, avec :
          - une cote horizontale centrée en haut  (largeur en mm)
          - une cote verticale centrée à droite   (hauteur en mm)
          - un badge en coin supérieur droit       (surface en cm²)
        """
        # --- Calcul de la boîte englobante pièces + marge bord (mm) ---
        # La bbox est étendue de espacement_bord sur les 4 côtés :
        # elle représente la taille de tôle minimale et touche le bord de la tôle.
        epb = self._espacement_bord
        raw_min_x = min(p.bounds[0] for p, *_ in self._placements)
        raw_min_y = min(p.bounds[1] for p, *_ in self._placements)
        raw_max_x = max(p.bounds[2] for p, *_ in self._placements)
        raw_max_y = max(p.bounds[3] for p, *_ in self._placements)

        min_x = raw_min_x - epb
        min_y = raw_min_y - epb
        max_x = raw_max_x + epb
        max_y = raw_max_y + epb

        bw = max_x - min_x   # largeur tôle min (mm)
        bh = max_y - min_y   # hauteur tôle min (mm)
        aire_cm2 = bw * bh / 100.0  # mm² → cm²

        # --- Coordonnées écran de la boîte ---
        bx0 = ox + min_x * e
        by0 = oy + (self._hauteur_plaque - max_y) * e
        bx1 = ox + max_x * e
        by1 = oy + (self._hauteur_plaque - min_y) * e
        bpw = bx1 - bx0
        bph = by1 - by0

        # --- Tracé de la boîte en pointillés jaunes ---
        pen_bbox = QPen(QColor('#FFD600'), 1.4, Qt.PenStyle.DashLine)
        pen_bbox.setDashPattern([6, 4])
        painter.setPen(pen_bbox)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(bx0, by0, bpw, bph))

        # Police commune pour les annotations
        painter.setBackgroundMode(Qt.BGMode.TransparentMode)
        font_cote = QFont('Segoe UI', max(7, min(24, int(8 * self._zoom))))
        painter.setFont(font_cote)

        MARGE = 4   # px entre le trait et le texte

        # --- Cote horizontale (largeur) — centrée au-dessus du bord supérieur ---
        texte_larg = f"{bw:.1f} mm"
        tw_larg = painter.fontMetrics().horizontalAdvance(texte_larg)
        tx_larg = bx0 + (bpw - tw_larg) / 2
        ty_larg = by0 - MARGE - painter.fontMetrics().height()

        # Fond semi-transparent pour lisibilité
        painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            QRectF(tx_larg - 3, ty_larg, tw_larg + 6,
                   painter.fontMetrics().height() + 2), 3, 3
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#FFD600')))
        painter.drawText(QRectF(tx_larg, ty_larg,
                                tw_larg + 1,
                                painter.fontMetrics().height() + 2),
                         Qt.AlignmentFlag.AlignLeft, texte_larg)

        # --- Cote verticale (hauteur) — centrée à droite du bord droit ---
        texte_haut = f"{bh:.1f} mm"
        th_haut = painter.fontMetrics().height()
        tw_haut = painter.fontMetrics().horizontalAdvance(texte_haut)
        tx_haut = bx1 + MARGE
        ty_haut = by0 + (bph - th_haut) / 2

        painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            QRectF(tx_haut - 2, ty_haut, tw_haut + 6, th_haut + 2), 3, 3
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#FFD600')))
        painter.drawText(QRectF(tx_haut + 2, ty_haut,
                                tw_haut + 1, th_haut + 2),
                         Qt.AlignmentFlag.AlignLeft, texte_haut)

        # --- Badge surface — coin supérieur droit de la boîte ---
        if aire_cm2 >= 100:
            texte_aire = f"{aire_cm2:.0f} cm²"
        elif aire_cm2 >= 10:
            texte_aire = f"{aire_cm2:.1f} cm²"
        else:
            texte_aire = f"{aire_cm2:.2f} cm²"

        font_badge = QFont('Segoe UI', max(7, min(24, int(8 * self._zoom))),
                           QFont.Weight.Bold)
        painter.setFont(font_badge)
        tw_aire = painter.fontMetrics().horizontalAdvance(texte_aire)
        th_aire = painter.fontMetrics().height()
        bx_aire = bx1 - tw_aire - 8
        by_aire = by0 + MARGE

        painter.setBrush(QBrush(QColor(0x1a, 0x1a, 0x00, 200)))
        painter.setPen(QPen(QColor('#FFD600'), 0.8))
        painter.drawRoundedRect(
            QRectF(bx_aire - 4, by_aire - 2, tw_aire + 10, th_aire + 4), 4, 4
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#FFD600')))
        painter.drawText(QRectF(bx_aire, by_aire, tw_aire + 2, th_aire + 2),
                         Qt.AlignmentFlag.AlignLeft, texte_aire)

    def _dessiner_legende(self, painter: QPainter, ox: float, oy: float):
        """Affiche le résumé sous la plaque."""
        if not self._placements:
            return
        nb = len(self._placements)
        texte = f"{nb} pièce(s)"
        if self._nb_non_places > 0:
            texte += f"  ·  {self._nb_non_places} non placée(s)"
        texte += f"  ·  zoom : {self._zoom:.1f}×"
        painter.setPen(QPen(QColor('#7777aa')))
        painter.setFont(QFont('Segoe UI', 9))
        painter.drawText(QRectF(ox, oy + 5, self.width(), 20),
                         Qt.AlignmentFlag.AlignLeft, texte)

    def _dessiner_aide(self, painter: QPainter):
        """Affiche l'aide de navigation dans le coin supérieur droit."""
        aide = ("Molette:zoom  |  clic droit/milieu:panoramique  |  ✥:déplacer  "
                "|  Ctrl+✥:rotation(1°)  |  Shift:forcer hors espacement  |  2×clic:réinitialiser")
        painter.setPen(QPen(QColor(0x44, 0x44, 0x88, 0x99)))
        painter.setFont(QFont('Segoe UI', 8))
        painter.drawText(
            QRectF(0, 4, self.width() - 6, 18),
            Qt.AlignmentFlag.AlignRight,
            aide
        )

    # =========================================================================
    # Gestion du transform et des coordonnées
    # =========================================================================

    def _calculer_base_transform(self):
        """
        Calcule le transform de base (sans zoom/pan) à partir des dimensions
        de la plaque et de la taille courante du widget.
        Stocke les résultats dans _base_echelle, _base_ox, _base_oy.
        """
        MARGE = 35
        zone_w = self.width() - 2 * MARGE
        zone_h = self.height() - 2 * MARGE

        if self._largeur_plaque <= 0 or self._hauteur_plaque <= 0 \
                or zone_w <= 0 or zone_h <= 0:
            self._base_echelle = 1.0
            self._base_ox = MARGE
            self._base_oy = MARGE
            return

        self._base_echelle = min(
            zone_w / self._largeur_plaque,
            zone_h / self._hauteur_plaque
        )
        plaque_px_w = self._largeur_plaque * self._base_echelle
        plaque_px_h = self._hauteur_plaque * self._base_echelle
        # Centrer la plaque dans le widget
        self._base_ox = MARGE + (zone_w - plaque_px_w) / 2
        self._base_oy = MARGE + (zone_h - plaque_px_h) / 2

    def _mm_vers_ecran(self, x_mm: float, y_mm: float) -> Tuple[float, float]:
        """Convertit des coordonnées en mm vers des pixels écran."""
        e = self._base_echelle * self._zoom
        px = self._base_ox + self._pan_dx + x_mm * e
        py = self._base_oy + self._pan_dy + (self._hauteur_plaque - y_mm) * e
        return px, py

    def _ecran_vers_mm(self, px: float, py: float) -> Tuple[float, float]:
        """Convertit des pixels écran vers des coordonnées en mm."""
        e = self._base_echelle * self._zoom
        if e <= 0:
            return 0.0, 0.0
        x_mm = (px - self._base_ox - self._pan_dx) / e
        y_mm = self._hauteur_plaque - (py - self._base_oy - self._pan_dy) / e
        return x_mm, y_mm

    def _reinitialiser_vue(self):
        """Remet le zoom à 1 et le panoramique à 0."""
        self._zoom = 1.0
        self._pan_dx = 0.0
        self._pan_dy = 0.0

    # =========================================================================
    # Logique de sélection et déplacement des sections
    # =========================================================================

    def _hit_test(self, x_mm: float, y_mm: float) -> Optional[int]:
        """
        Retourne l'index du premier placement qui contient le point (x_mm, y_mm).
        Utilise un buffer de 1 mm pour faciliter la sélection sur les bords fins.
        Retourne None si aucune pièce n'est sous le curseur.
        """
        pt = Point(x_mm, y_mm)
        for i, (poly, *_) in enumerate(self._placements):
            # buffer(1.0) étend le polygone de 1 mm pour faciliter la sélection
            if poly.buffer(1.0).contains(pt):
                return i
        return None

    def _est_placement_valide(self, poly: Polygon, idx_exclus: int) -> bool:
        """
        Vérifie que `poly` respecte les contraintes d'espacement :
          1. La pièce reste entièrement dans la plaque (marge = espacement).
          2. La pièce ne chevauche aucune autre pièce (distance ≥ espacement).

        Utilise un pré-filtre bounding-box avant le test géométrique complet,
        identique à la stratégie employée dans core/nesting.py.
        """
        esp      = self._espacement
        esp_bord = self._espacement_bord
        minx, miny, maxx, maxy = poly.bounds

        # --- 1. Contrainte plaque (espacement_bord) ---
        if minx < esp_bord - 1e-6:
            return False
        if miny < esp_bord - 1e-6:
            return False
        if maxx > self._largeur_plaque - esp_bord + 1e-6:
            return False
        if maxy > self._hauteur_plaque - esp_bord + 1e-6:
            return False

        # Si espacement inter-pièces = 0, pas de test inter-pièces nécessaire
        if esp <= 0.0:
            return True

        # --- 2. Contrainte inter-pièces ---
        for j, (other_poly, *_) in enumerate(self._placements):
            if j == idx_exclus:
                continue
            ob = other_poly.bounds
            # Pré-filtre BBox : si les boîtes englobantes (étendues d'esp) ne se
            # chevauchent pas, pas de collision possible.
            if maxx + esp <= ob[0] or minx - esp >= ob[2]:
                continue
            if maxy + esp <= ob[1] or miny - esp >= ob[3]:
                continue
            # Test géométrique exact
            if poly.intersects(other_poly.buffer(esp)):
                return False

        return True

    def _deplacer_section(self, idx: int, dx_mm: float, dy_mm: float,
                          force: bool = False):
        """
        Translate le polygone d'index idx de (dx_mm, dy_mm).
        Sans force=True : mouvement refusé si l'espacement est violé.
        Avec force=True  : mouvement toujours appliqué ; self._drag_bloque
                           indique si la position résultante est invalide.
        """
        poly, ox_mm, oy_mm, idx_orig = self._placements[idx]
        new_poly = translate(poly, xoff=dx_mm, yoff=dy_mm)
        valide = self._est_placement_valide(new_poly, idx)

        if not valide and not force:
            self._drag_bloque = True
            return  # mouvement refusé

        self._drag_bloque = not valide
        self._placements[idx] = (new_poly, ox_mm + dx_mm, oy_mm + dy_mm, idx_orig)
        # Invalide la prévisualisation de lissage (géométrie modifiée)
        self._entites_lisses = None

    def _faire_pivoter_section(self, idx: int, angle_deg: float):
        """
        Fait pivoter le polygone d'index idx de angle_deg degrés (incrémental)
        autour de son centroïde. Conservé pour usage éventuel externe.
        """
        poly, ox_mm, oy_mm, idx_orig = self._placements[idx]
        new_poly = rotate(poly, angle_deg, origin='centroid', use_radians=False)
        self._placements[idx] = (new_poly, ox_mm, oy_mm, idx_orig)

    def _appliquer_rotation_snappee(self, idx: int, angle_deg: float,
                                    force: bool = False):
        """
        Applique une rotation ABSOLUE de angle_deg degrés sur le polygone idx,
        depuis l'état initial mémorisé au début du drag (self._rotate_poly_initial).

        Sans force=True : rotation refusée si l'espacement est violé.
        Avec force=True  : rotation toujours appliquée ; self._drag_bloque
                           indique si la position résultante est invalide.

        angle_deg > 0 → sens anti-horaire (convention shapely)
        angle_deg < 0 → sens horaire
        """
        if self._rotate_poly_initial is None:
            return
        _, ox_mm, oy_mm, idx_orig = self._placements[idx]
        new_poly = rotate(
            self._rotate_poly_initial, float(angle_deg),
            origin='centroid', use_radians=False
        )
        valide = self._est_placement_valide(new_poly, idx)

        if not valide and not force:
            self._drag_bloque = True
            return  # rotation refusée — on garde l'état précédent valide

        self._drag_bloque = not valide
        self._placements[idx] = (new_poly, ox_mm, oy_mm, idx_orig)
        # Invalide la prévisualisation de lissage (géométrie modifiée)
        self._entites_lisses = None

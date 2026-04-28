"""
core/geometry.py — Manipulation géométrique des contours.

Fonctions :
  - apply_kerf_offset : offset shapely pour compensation de kerf (optionnel, non utilisé
    quand le GCode utilise G41/G42 ou la gestion matériau ECP1000).
  - add_lead_in / add_lead_out : calcul des points d'approche et sortie.
  - is_interior : détection de la relation d'inclusion entre contours.
  - normalize_orientation : forçage du sens CW/CCW.
  - calculer_aire_signee : aire signée (algorithme du lacet).

Convention coordonnées : Y positif vers le haut (espace DXF/mathématique).
"""

import logging
import math
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Type alias pour un contour
Contour = List[Tuple[float, float]]


# ---------------------------------------------------------------------------
# Orientation
# ---------------------------------------------------------------------------

def calculer_aire_signee(contour: Contour) -> float:
    """
    Calcule l'aire signée d'un contour (algorithme de Gauss/Shoelace).

    Returns:
        Valeur positive si CCW (anti-horaire), négative si CW (horaire).
    """
    n = len(contour)
    if n < 3:
        return 0.0
    aire = 0.0
    for i in range(n):
        x1, y1 = contour[i]
        x2, y2 = contour[(i + 1) % n]
        aire += (x1 * y2 - x2 * y1)
    return aire / 2.0


def normalize_orientation(contour: Contour, exterieur: bool = True) -> Contour:
    """
    Force l'orientation d'un contour.

    Convention plasma :
      - Contour extérieur → sens anti-horaire (CCW, aire positive)
      - Contour intérieur (trou) → sens horaire (CW, aire négative)

    Args:
        contour: Liste de points (x, y).
        exterieur: True pour forcer CCW (extérieur), False pour forcer CW (trou).

    Returns:
        Contour avec l'orientation souhaitée.
    """
    aire = calculer_aire_signee(contour)
    if exterieur and aire < 0:
        return list(reversed(contour))
    elif not exterieur and aire > 0:
        return list(reversed(contour))
    return list(contour)


# ---------------------------------------------------------------------------
# Détection intérieur/extérieur
# ---------------------------------------------------------------------------

def is_interior(contour_a: Contour, contour_b: Contour) -> bool:
    """
    Détermine si le contour_a est entièrement à l'intérieur du contour_b.

    Utilise shapely pour la détection robuste.

    Args:
        contour_a: Contour à tester (potentiellement intérieur).
        contour_b: Contour conteneur.

    Returns:
        True si contour_a est à l'intérieur de contour_b.
    """
    try:
        from shapely.geometry import Polygon, Point

        poly_b = Polygon(contour_b)
        if not poly_b.is_valid:
            poly_b = poly_b.buffer(0)

        # Tester si le centroïde de A est à l'intérieur de B
        if len(contour_a) < 3:
            return False

        # Utiliser le premier point pour le test rapide
        pt = Point(contour_a[0])
        if not poly_b.contains(pt):
            return False

        # Test complet : vérifier que tous les points de A sont dans B
        poly_a = Polygon(contour_a)
        if not poly_a.is_valid:
            poly_a = poly_a.buffer(0)
        return poly_b.contains(poly_a)

    except ImportError:
        logger.warning("shapely non disponible, utilisation de la méthode de repli.")
        return _is_interior_fallback(contour_a, contour_b)
    except Exception as e:
        logger.warning(f"Erreur test intérieur/extérieur : {e}")
        return False


def _is_interior_fallback(contour_a: Contour, contour_b: Contour) -> bool:
    """
    Test d'intérieur basé sur le lancer de rayon (fallback sans shapely).
    Teste uniquement le premier point du contour A.
    """
    px, py = contour_a[0]
    n = len(contour_b)
    dedans = False
    j = n - 1
    for i in range(n):
        xi, yi = contour_b[i]
        xj, yj = contour_b[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            dedans = not dedans
        j = i
    return dedans


# ---------------------------------------------------------------------------
# Offset de kerf (optionnel)
# ---------------------------------------------------------------------------

def apply_kerf_offset(
    contour: Contour,
    kerf_mm: float,
    cote: str = 'gauche',
) -> Contour:
    """
    Applique un offset shapely pour compenser le kerf géométriquement.

    ATTENTION : Cette fonction ne doit PAS être utilisée si le GCode utilise
    G41/G42 ou si la machine gère le kerf via $material (ECP1000 standard).
    L'utiliser en conjonction avec G41/G42 créerait une double compensation.

    Args:
        contour: Liste de points (x, y).
        kerf_mm: Largeur de trait plasma en mm.
        cote: 'gauche' (décalage vers l'intérieur) ou 'droite' (vers l'extérieur).

    Returns:
        Contour offsetté, ou le contour original en cas d'erreur.
    """
    try:
        from shapely.geometry import Polygon

        # Sens de l'offset selon le côté et l'orientation du contour
        aire = calculer_aire_signee(contour)
        distance = kerf_mm / 2.0

        # Pour un contour CCW extérieur : décalage vers l'intérieur = distance positive
        if cote == 'gauche':
            dist_offset = -distance if aire > 0 else distance
        else:
            dist_offset = distance if aire > 0 else -distance

        poly = Polygon(contour)
        if not poly.is_valid:
            poly = poly.buffer(0)

        poly_offset = poly.buffer(dist_offset, join_style=2)  # join_style=2 : miter

        if poly_offset.is_empty:
            logger.warning(
                f"L'offset kerf de {kerf_mm} mm a produit un contour vide. "
                f"Contour original conservé."
            )
            return contour

        # Extraire les coordonnées du polygone résultant
        coords = list(poly_offset.exterior.coords)
        # Retirer le doublon de fermeture shapely
        if len(coords) > 1 and coords[0] == coords[-1]:
            coords = coords[:-1]

        return [(float(x), float(y)) for x, y in coords]

    except ImportError:
        logger.warning("shapely non disponible, offset kerf impossible.")
        return contour
    except Exception as e:
        logger.warning(f"Erreur offset kerf : {e}. Contour original conservé.")
        return contour


# ---------------------------------------------------------------------------
# Lead-in et lead-out
# ---------------------------------------------------------------------------

def calculer_lead_in(
    contour: Contour,
    longueur: float,
) -> Tuple[Tuple[float, float], Contour]:
    """
    Calcule le point de départ du lead-in pour un contour.

    Le lead-in s'approche du premier point du contour en suivant la direction
    inverse du premier segment. Le point de départ est placé à 'longueur' mm
    avant le premier point du contour.

    Args:
        contour: Liste de points (x, y), au moins 2 points.
        longueur: Longueur du lead-in en mm.

    Returns:
        Tuple (point_depart, contour) où point_depart est le point de piquage
        (en dehors du contour) et contour est le contour original inchangé.

    Raises:
        ValueError: Si le contour est trop court ou la longueur invalide.
    """
    if len(contour) < 2:
        raise ValueError(f"Contour trop court pour calculer le lead-in ({len(contour)} points).")

    if longueur <= 0:
        return contour[0], contour

    p0 = contour[0]
    p1 = contour[1]

    # Direction du premier segment
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    longueur_seg = math.sqrt(dx * dx + dy * dy)

    if longueur_seg < 1e-9:
        # Segment nul → chercher le premier segment non nul
        for i in range(1, len(contour) - 1):
            dx = contour[i + 1][0] - contour[i][0]
            dy = contour[i + 1][1] - contour[i][1]
            longueur_seg = math.sqrt(dx * dx + dy * dy)
            if longueur_seg > 1e-9:
                break
        if longueur_seg < 1e-9:
            logger.warning("Tous les segments sont nuls, lead-in défini à p0.")
            return p0, contour

    # Vecteur unitaire dans le sens du premier segment
    ux = dx / longueur_seg
    uy = dy / longueur_seg

    # Respecter exactement la longueur paramétrée (le lead-in s'exécute
    # AVANT d'entrer dans le contour, il n'y a pas de raison de le clamper
    # sur la taille du premier segment).
    start_x = p0[0] - ux * longueur
    start_y = p0[1] - uy * longueur

    return (start_x, start_y), contour


def calculer_lead_out(
    contour: Contour,
    longueur: float,
) -> Tuple[float, float]:
    """
    Calcule le point de fin du lead-out après fermeture du contour.

    Le lead-out continue dans la direction d'approche du dernier segment
    vers le point de fermeture (P[n-1] → P[0]).

    Args:
        contour: Liste de points (x, y), au moins 2 points.
        longueur: Longueur du lead-out en mm.

    Returns:
        Point de fin du lead-out (x, y).
    """
    if len(contour) < 2:
        return contour[0]

    if longueur <= 0:
        return contour[0]

    # Direction du segment final (avant-dernier point → premier point = fermeture)
    p_avant = contour[-1]
    p_fin = contour[0]

    dx = p_fin[0] - p_avant[0]
    dy = p_fin[1] - p_avant[1]
    longueur_seg = math.sqrt(dx * dx + dy * dy)

    if longueur_seg < 1e-9:
        # Dernier segment nul → utiliser la direction du premier segment
        if len(contour) >= 2:
            dx = contour[1][0] - contour[0][0]
            dy = contour[1][1] - contour[0][1]
            longueur_seg = math.sqrt(dx * dx + dy * dy)
        if longueur_seg < 1e-9:
            return p_fin

    ux = dx / longueur_seg
    uy = dy / longueur_seg

    return (p_fin[0] + ux * longueur, p_fin[1] + uy * longueur)


# ---------------------------------------------------------------------------
# Lead-in/out en arc tangent
# ---------------------------------------------------------------------------

# Nombre de segments pour discrétiser un arc de 90° (suffisant pour plasma)
_N_SEG_ARC = 16


def _point_dans_polygone(p: Tuple[float, float], polygone: Contour) -> bool:
    """Test d'appartenance par lancer de rayon (ray casting)."""
    if len(polygone) < 3:
        return False
    px, py = p
    n = len(polygone)
    dedans = False
    j = n - 1
    for i in range(n):
        xi, yi = polygone[i]
        xj, yj = polygone[j]
        if ((yi > py) != (yj > py)):
            x_cross = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < x_cross:
                dedans = not dedans
        j = i
    return dedans


def _arc_quart(
    p0x: float, p0y: float, ux: float, uy: float, R: float, cote_droite: bool,
    sens: str,
) -> List[Tuple[float, float]]:
    """
    Construit un quart de cercle de rayon R tangent à u en p0.

    Args:
        cote_droite : True → centre à droite de u (= (uy,-ux)),
                      False → centre à gauche de u (= (-uy, ux)).
        sens        : 'in'  → arc se TERMINANT en p0 (lead-in),
                      'out' → arc PARTANT de p0 (lead-out).
    """
    if cote_droite:
        cx = p0x + uy * R
        cy = p0y - ux * R
        # Centre à droite + tangente u en p0 → arc CW
        # angle(p0 - C) = atan2(-(-ux), -(uy)) = atan2(ux, -uy)
        theta_p0 = math.atan2(ux, -uy)
        # Quart de tour CW avant p0 : theta_avant = theta_p0 + π/2
        if sens == 'in':
            theta_start, theta_end = theta_p0 + math.pi / 2.0, theta_p0
        else:
            theta_start, theta_end = theta_p0, theta_p0 - math.pi / 2.0
    else:
        cx = p0x - uy * R
        cy = p0y + ux * R
        # Centre à gauche + tangente u en p0 → arc CCW
        # angle(p0 - C) = atan2(-ux, uy)
        theta_p0 = math.atan2(-ux, uy)
        if sens == 'in':
            theta_start, theta_end = theta_p0 - math.pi / 2.0, theta_p0
        else:
            theta_start, theta_end = theta_p0, theta_p0 + math.pi / 2.0

    pts = []
    for k in range(_N_SEG_ARC + 1):
        t = theta_start + (theta_end - theta_start) * (k / _N_SEG_ARC)
        pts.append((cx + R * math.cos(t), cy + R * math.sin(t)))
    # Sécurité numérique : ancrer le point qui doit être p0 exactement.
    if sens == 'in':
        pts[-1] = (p0x, p0y)
    else:
        pts[0] = (p0x, p0y)
    return pts


def _polyline_dans_zone_piece(
    poly: List[Tuple[float, float]],
    contour_ref: Contour,
    est_interieur: bool,
) -> bool:
    """
    Teste si la polyligne traverse la "zone pièce" (matière finie à conserver).

    Pour un contour extérieur (est_interieur=False) : zone pièce = INTÉRIEUR du polygone.
    Pour un contour intérieur (trou)               : zone pièce = EXTÉRIEUR du polygone.

    On échantillonne plusieurs points de la polyline et on retourne True si l'un
    d'eux tombe dans la zone pièce.
    """
    # On ignore le point p0 (extrémité commune au contour) — il est sur le bord.
    pts_test = poly[:-1] if len(poly) >= 2 else poly
    for p in pts_test:
        dedans = _point_dans_polygone(p, contour_ref)
        sur_piece = dedans if not est_interieur else (not dedans)
        if sur_piece:
            return True
    return False


def _premier_segment_unitaire(
    contour: Contour,
) -> Optional[Tuple[float, float, float, float]]:
    """Retourne (p0x, p0y, ux, uy) ou None si contour dégénéré."""
    if len(contour) < 2:
        return None
    p0 = contour[0]
    for i in range(1, len(contour)):
        dx = contour[i][0] - p0[0]
        dy = contour[i][1] - p0[1]
        L = math.sqrt(dx * dx + dy * dy)
        if L > 1e-9:
            return (p0[0], p0[1], dx / L, dy / L)
    return None


def _dernier_segment_unitaire(
    contour: Contour,
) -> Optional[Tuple[float, float, float, float]]:
    """
    Direction entrant en p0 lors de la fermeture du contour (dernier point → p0).
    Retourne (p0x, p0y, ux, uy) ou None.
    """
    if len(contour) < 2:
        return None
    p0 = contour[0]
    for i in range(len(contour) - 1, 0, -1):
        dx = p0[0] - contour[i][0]
        dy = p0[1] - contour[i][1]
        L = math.sqrt(dx * dx + dy * dy)
        if L > 1e-9:
            return (p0[0], p0[1], dx / L, dy / L)
    return None


def lead_in_polyline(
    contour: Contour,
    longueur: float,
    type_lead: str = 'lineaire',
    est_interieur: bool = False,
) -> List[Tuple[float, float]]:
    """
    Calcule la polyline complète du lead-in (piquage → p0).

    Le lead-in est garanti de NE PAS traverser la matière finie de la pièce :
      - contour extérieur → lead-in HORS du polygone (côté chute) ;
      - contour intérieur (trou) → lead-in DANS le polygone (= dans le trou,
        qui est aussi de la chute).

    Args:
        contour       : Contour à découper (Y-haut, fermé).
        longueur      : Longueur paramétrée (mm). Pour l'arc, correspond au rayon.
        type_lead     : 'lineaire' ou 'arc'.
        est_interieur : True si le contour est un trou (la zone pièce devient
                        l'extérieur du polygone).

    Returns:
        Liste de points (x, y) du piquage jusqu'au premier point du contour
        inclus. Pour 'lineaire' → 2 points (basculement perpendiculaire si la
        tangente entre dans la pièce). Pour 'arc' → _N_SEG_ARC+1 points.
    """
    info = _premier_segment_unitaire(contour)
    if info is None or longueur <= 0:
        return [contour[0]] if contour else []
    p0x, p0y, ux, uy = info
    p0 = (p0x, p0y)

    if type_lead.lower().startswith('lin'):
        # 1) Tentative tangentielle (extension arrière le long du 1er segment).
        cand_tan = [(p0x - ux * longueur, p0y - uy * longueur), p0]
        if not _polyline_dans_zone_piece(cand_tan, contour, est_interieur):
            return cand_tan
        # 2) Bascule en perpendiculaire vers le côté chute.
        cand_d = [(p0x + uy * longueur, p0y - ux * longueur), p0]   # droite
        if not _polyline_dans_zone_piece(cand_d, contour, est_interieur):
            return cand_d
        cand_g = [(p0x - uy * longueur, p0y + ux * longueur), p0]   # gauche
        if not _polyline_dans_zone_piece(cand_g, contour, est_interieur):
            return cand_g
        # 3) Aucun candidat valide → on garde la tangente (signalée par
        # ajuster_point_depart comme problème de piquage).
        return cand_tan

    # --- Arc tangent de 90° ---
    # Convention : on tente d'abord le centre à droite de u (= (uy,-ux)) qui
    # est correct pour les contours extérieurs CCW et les trous CW normalisés.
    # Si le résultat envahit la zone pièce (orientation non normalisée ou
    # géométrie pathologique), on bascule sur le centre à gauche.
    cand_d = _arc_quart(p0x, p0y, ux, uy, longueur, cote_droite=True,  sens='in')
    if not _polyline_dans_zone_piece(cand_d, contour, est_interieur):
        return cand_d
    cand_g = _arc_quart(p0x, p0y, ux, uy, longueur, cote_droite=False, sens='in')
    if not _polyline_dans_zone_piece(cand_g, contour, est_interieur):
        return cand_g
    return cand_d


def lead_out_polyline(
    contour: Contour,
    longueur: float,
    type_lead: str = 'lineaire',
    est_interieur: bool = False,
) -> List[Tuple[float, float]]:
    """
    Calcule la polyline complète du lead-out (p0 → point de dégagement).
    Symétrique de lead_in_polyline : garanti hors zone pièce.
    """
    info = _dernier_segment_unitaire(contour)
    if info is None or longueur <= 0:
        return [contour[0]] if contour else []
    p0x, p0y, ux, uy = info
    p0 = (p0x, p0y)

    if type_lead.lower().startswith('lin'):
        cand_tan = [p0, (p0x + ux * longueur, p0y + uy * longueur)]
        if not _polyline_dans_zone_piece(cand_tan, contour, est_interieur):
            return cand_tan
        cand_d = [p0, (p0x + uy * longueur, p0y - ux * longueur)]
        if not _polyline_dans_zone_piece(cand_d, contour, est_interieur):
            return cand_d
        cand_g = [p0, (p0x - uy * longueur, p0y + ux * longueur)]
        if not _polyline_dans_zone_piece(cand_g, contour, est_interieur):
            return cand_g
        return cand_tan

    cand_d = _arc_quart(p0x, p0y, ux, uy, longueur, cote_droite=True,  sens='out')
    if not _polyline_dans_zone_piece(cand_d, contour, est_interieur):
        return cand_d
    cand_g = _arc_quart(p0x, p0y, ux, uy, longueur, cote_droite=False, sens='out')
    if not _polyline_dans_zone_piece(cand_g, contour, est_interieur):
        return cand_g
    return cand_d


# ---------------------------------------------------------------------------
# Ajustement du point de départ (évitement voisins)
# ---------------------------------------------------------------------------

def _distance_min_point_au_contour(
    p: Tuple[float, float], contour: Contour
) -> float:
    """Distance minimale d'un point à un polygone (segments)."""
    if not contour:
        return float('inf')
    x0, y0 = p
    n = len(contour)
    d_min = float('inf')
    for i in range(n):
        ax, ay = contour[i]
        bx, by = contour[(i + 1) % n]
        # Distance point-segment
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            d = math.hypot(x0 - ax, y0 - ay)
        else:
            t = max(0.0, min(1.0, ((x0 - ax) * dx + (y0 - ay) * dy) / L2))
            px = ax + t * dx
            py = ay + t * dy
            d = math.hypot(x0 - px, y0 - py)
        if d < d_min:
            d_min = d
    return d_min


def ajuster_point_depart(
    contour: Contour,
    voisins: List[Contour],
    marge: float,
    longueur_lead_in: float,
    type_lead: str = 'lineaire',
    est_interieur: bool = False,
) -> Tuple[Contour, bool]:
    """
    Cherche une rotation cyclique des points du contour telle que le lead-in
    résultant reste à au moins `marge` mm de tous les contours voisins.

    Args:
        contour            : Contour à ajuster (fermé, Y-haut).
        voisins            : Contours des pièces voisines (tous, y compris trous).
        marge              : Marge minimale (mm) entre le lead-in et les voisins.
        longueur_lead_in   : Longueur du lead-in.
        type_lead          : 'lineaire' ou 'arc'.

    Returns:
        (contour_ajuste, ok)
          - contour_ajuste : contour avec nouveau point de départ (fermé, même
            orientation que l'entrée).
          - ok             : True si une position valide a été trouvée, False
            sinon (auquel cas on retourne le contour d'origine).
    """
    n = len(contour)
    if n < 3 or longueur_lead_in <= 0 or not voisins:
        return list(contour), True

    # Itérer sur toutes les rotations possibles du contour
    meilleur_idx = None
    meilleur_score = -1.0   # on veut maximiser la distance min
    for start in range(n):
        rotated = contour[start:] + contour[:start]
        try:
            poly = lead_in_polyline(rotated, longueur_lead_in, type_lead, est_interieur)
        except Exception:
            continue

        # Distance min entre n'importe quel point du lead-in et n'importe
        # quel voisin. Échantillonnage : tous les points de la polyline
        # (la discrétisation est déjà fine pour l'arc).
        d_min_rot = float('inf')
        for pt in poly:
            for v in voisins:
                d = _distance_min_point_au_contour(pt, v)
                if d < d_min_rot:
                    d_min_rot = d
                    if d_min_rot < marge * 0.5:
                        break
            if d_min_rot < marge * 0.5:
                break

        if d_min_rot >= marge:
            # Position valide — on prend la première trouvée (évite de trop
            # s'éloigner du point de départ initial).
            return rotated, True

        if d_min_rot > meilleur_score:
            meilleur_score = d_min_rot
            meilleur_idx = start

    # Aucune rotation ne satisfait la marge → on renvoie la meilleure
    # trouvée en signalant l'échec.
    if meilleur_idx is not None:
        rotated = contour[meilleur_idx:] + contour[:meilleur_idx]
        return rotated, False
    return list(contour), False


# ---------------------------------------------------------------------------
# Utilitaires géométriques
# ---------------------------------------------------------------------------

def bounding_box(contour: Contour) -> Tuple[float, float, float, float]:
    """
    Calcule la boîte englobante d'un contour.

    Returns:
        Tuple (x_min, y_min, x_max, y_max).
    """
    if not contour:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in contour]
    ys = [p[1] for p in contour]
    return (min(xs), min(ys), max(xs), max(ys))


def centroide(contour: Contour) -> Tuple[float, float]:
    """Calcule le centroïde géométrique d'un contour."""
    if not contour:
        return (0.0, 0.0)
    cx = sum(p[0] for p in contour) / len(contour)
    cy = sum(p[1] for p in contour) / len(contour)
    return (cx, cy)


def translater(contour: Contour, dx: float, dy: float) -> Contour:
    """Translate un contour d'un vecteur (dx, dy)."""
    return [(x + dx, y + dy) for x, y in contour]


def distance_point(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calcule la distance euclidienne entre deux points."""
    return math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)

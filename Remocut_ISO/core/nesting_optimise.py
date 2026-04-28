"""
core/nesting_optimise.py — Nesting optimisé : Bottom-Left Fill + Rotation.

Adapté de l'algorithme du STL Slicer (BL+Fill + 12 rotations + multi-séquençage).

Algorithme :
  - Pour chaque pièce (dans l'ordre défini par `methode`), 12 angles de rotation
    sont testés (pas de 30°). Pour chaque rotation, les positions candidates
    (coins BL + grille croisée des bords des pièces déjà placées) sont évaluées.
  - La position minimisant l'aire de la boîte englobante globale est retenue.
  - Le mode 'multi' essaie 4 ordres de tri et retient le meilleur résultat.

Exporte :
    placer_pieces_optimise(pieces, largeur, hauteur, marge, methode, callback)
        → Tuple[List[ContourPlace], bool]
"""

import logging
import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from shapely.affinity import rotate as shapely_rotate
from shapely.affinity import translate as shapely_translate
from shapely.geometry import Polygon

logger = logging.getLogger(__name__)

# Type alias
Contour = List[Tuple[float, float]]

# Angles candidats pour le nesting optimisé (pas de 30° → 12 orientations)
_ANGLES_OPTIMISE = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]


@dataclass
class _PlacementInfo:
    """Informations de placement d'une pièce (usage interne)."""
    piece_idx: int        # Indice de la pièce dans la liste `pieces`
    angle: float          # Angle de rotation appliqué (degrés)
    cx_cent: float        # Centroïde X de l'extérieur original (avant rotation)
    cy_cent: float        # Centroïde Y de l'extérieur original (avant rotation)
    tx: float             # Translation totale X = cx - bmin_x_roté
    ty: float             # Translation totale Y = cy - bmin_y_roté
    poly_placed: Polygon  # Polygone extérieur final (pour bbox / collision)


def placer_pieces_optimise(
    pieces: List[List[Contour]],
    largeur_tole: float,
    hauteur_tole: float,
    marge: float,
    methode: str = 'multi',
    callback_progression: Optional[Callable[[int, int], None]] = None,
) -> Tuple[list, bool]:
    """
    Place les pièces sur la tôle avec l'algorithme Bottom-Left Fill + Rotation.

    Args:
        pieces               : Liste de pièces [extérieur, trou1, trou2, ...].
        largeur_tole         : Largeur utile de la tôle (mm).
        hauteur_tole         : Hauteur utile de la tôle (mm).
        marge                : Espacement minimum pièce-pièce et pièce-bord (mm).
        methode              : 'aire' | 'perimetre' | 'dim_max' | 'multi'.
        callback_progression : fonction(etape, total) appelée à chaque pièce placée.

    Returns:
        (contours_places, tous_places) :
          - contours_places : List[ContourPlace] avec positions finales.
          - tous_places     : True si toutes les pièces ont pu être placées.
    """
    # Import ici pour éviter l'import circulaire
    from core.nesting import ContourPlace
    from core.geometry import normalize_orientation

    if not pieces:
        return [], True

    # Construire les polygones Shapely depuis les contours extérieurs
    polygones: List[Polygon] = []
    for piece in pieces:
        poly = _contour_vers_polygon(piece[0])
        polygones.append(poly)

    n = len(polygones)

    # --- Construction des ordres à tester ---
    def _dim_max_key(i: int) -> float:
        minx, miny, maxx, maxy = polygones[i].bounds
        return max(maxx - minx, maxy - miny)

    _tous_ordres = {
        'aire':      sorted(range(n), key=lambda i: polygones[i].area, reverse=True),
        'perimetre': sorted(range(n), key=lambda i: polygones[i].length, reverse=True),
        'dim_max':   sorted(range(n), key=_dim_max_key, reverse=True),
        'aire_asc':  sorted(range(n), key=lambda i: polygones[i].area),
    }

    if methode == 'multi':
        ordres_a_tester = list(_tous_ordres.values())
        ordres_uniques: List[List[int]] = []
        vus: set = set()
        for o in ordres_a_tester:
            cle = tuple(o)
            if cle not in vus:
                vus.add(cle)
                ordres_uniques.append(o)
    else:
        ordres_uniques = [_tous_ordres.get(methode, _tous_ordres['aire'])]

    nb_ordres = len(ordres_uniques)
    total_etapes = nb_ordres * n

    meilleur_infos: Optional[List[_PlacementInfo]] = None
    meilleur_nb_non = n + 1
    meilleur_score = float('inf')

    for i_ordre, ordre in enumerate(ordres_uniques):

        def _cb(etape: int, _total: int, _i: int = i_ordre) -> None:
            if callback_progression:
                callback_progression(_i * n + etape, total_etapes)

        infos, nb_non = _run_une_sequence(
            ordre, polygones, largeur_tole, hauteur_tole, marge, _cb
        )

        if infos:
            score = _score_bbox_global([info.poly_placed for info in infos])
        else:
            score = float('inf')

        if nb_non < meilleur_nb_non or (nb_non == meilleur_nb_non and score < meilleur_score):
            meilleur_infos = infos
            meilleur_nb_non = nb_non
            meilleur_score = score

    if callback_progression:
        callback_progression(total_etapes, total_etapes)

    if not meilleur_infos:
        return [], meilleur_nb_non == 0

    # Convertir en ContourPlace
    contours_places = _infos_vers_contours_places(meilleur_infos, pieces,
                                                   ContourPlace, normalize_orientation)
    return contours_places, meilleur_nb_non == 0


# =============================================================================
# Séquence de placement interne (BL+R pour un ordre donné)
# =============================================================================

def _run_une_sequence(
    ordre: List[int],
    polygones: List[Polygon],
    largeur_tole: float,
    hauteur_tole: float,
    marge: float,
    callback: Optional[Callable[[int, int], None]],
) -> Tuple[List[_PlacementInfo], int]:
    """
    Exécute Bottom-Left Fill + Rotation pour un ordre de pièces donné.

    Returns:
        (infos_placements, nb_non_places)
    """
    infos: List[_PlacementInfo] = []
    placed_buffered: List[Polygon] = []
    nb_non = 0

    for etape, idx in enumerate(ordre):
        if callback:
            callback(etape, len(ordre))

        poly_orig = polygones[idx]
        centroid = poly_orig.centroid
        cx_cent = centroid.x
        cy_cent = centroid.y

        meilleur_info: Optional[_PlacementInfo] = None
        meilleur_score = float('inf')
        candidats = _candidats_coins(infos, marge)

        for angle in _ANGLES_OPTIMISE:
            # Rotation autour du centroïde de l'original
            if angle == 0:
                poly_r = poly_orig
            else:
                poly_r = shapely_rotate(poly_orig, angle,
                                        origin='centroid', use_radians=False)

            bmin_x, bmin_y, bmax_x, bmax_y = poly_r.bounds
            pw = bmax_x - bmin_x
            ph = bmax_y - bmin_y

            if pw + 2 * marge > largeur_tole:
                continue
            if ph + 2 * marge > hauteur_tole:
                continue

            # Normaliser à l'origine (coin bas-gauche = 0,0)
            poly_norm = shapely_translate(poly_r, -bmin_x, -bmin_y)

            for cx, cy in candidats:
                if cx < marge - 1e-9:
                    continue
                if cy < marge - 1e-9:
                    continue
                if cx + pw + marge > largeur_tole + 1e-9:
                    continue
                if cy + ph + marge > hauteur_tole + 1e-9:
                    continue

                if not _collision_libre(poly_norm, cx, cy, pw, ph, placed_buffered):
                    continue

                poly_place = shapely_translate(poly_norm, cx, cy)
                score = _score_bbox([info.poly_placed for info in infos], poly_place)

                if score < meilleur_score:
                    meilleur_score = score
                    # tx intègre la normalisation + translation finale
                    meilleur_info = _PlacementInfo(
                        piece_idx=idx,
                        angle=float(angle),
                        cx_cent=cx_cent,
                        cy_cent=cy_cent,
                        tx=cx - bmin_x,
                        ty=cy - bmin_y,
                        poly_placed=poly_place,
                    )

        if meilleur_info is not None:
            infos.append(meilleur_info)
            placed_buffered.append(meilleur_info.poly_placed.buffer(marge))
        else:
            nb_non += 1
            logger.debug(
                f"Pièce {idx} non placée (angle optimisé, marge {marge}mm)."
            )

    return infos, nb_non


# =============================================================================
# Conversion en ContourPlace
# =============================================================================

def _infos_vers_contours_places(
    infos: List[_PlacementInfo],
    pieces: List[List[Contour]],
    ContourPlace,
    normalize_orientation,
) -> list:
    """
    Applique rotation + translation à chaque contour de chaque pièce
    et retourne la liste de ContourPlace.
    """
    contours_places = []
    id_piece_global = 0

    for info in infos:
        piece = pieces[info.piece_idx]
        for idx_c, contour in enumerate(piece):
            est_int = (idx_c > 0)
            pts = _appliquer_transform_contour(
                contour,
                info.cx_cent, info.cy_cent,
                info.angle,
                info.tx, info.ty,
            )
            pts = normalize_orientation(pts, exterieur=not est_int)
            contours_places.append(ContourPlace(
                points=pts,
                est_interieur=est_int,
                id_piece=id_piece_global,
                offset_x=info.tx,
                offset_y=info.ty,
                points_originaux=list(contour),
            ))
        id_piece_global += 1

    return contours_places


def _appliquer_transform_contour(
    contour: Contour,
    cx_cent: float,
    cy_cent: float,
    angle_deg: float,
    tx: float,
    ty: float,
) -> Contour:
    """
    Applique la transformation complète à un contour :
      1. Rotation d'angle `angle_deg` autour du centroïde (cx_cent, cy_cent).
      2. Translation de (tx, ty)  [tx = cx - bmin_x_roté intègre la normalisation].

    Args:
        contour    : Liste de points (x, y) en coordonnées originales.
        cx_cent    : Centroïde X du polygone extérieur original.
        cy_cent    : Centroïde Y du polygone extérieur original.
        angle_deg  : Angle de rotation (degrés, sens trigonométrique).
        tx, ty     : Translation finale.
    """
    if angle_deg == 0:
        return [(x + tx, y + ty) for x, y in contour]

    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    result = []
    for x, y in contour:
        dx = x - cx_cent
        dy = y - cy_cent
        rx = cos_a * dx - sin_a * dy + cx_cent + tx
        ry = sin_a * dx + cos_a * dy + cy_cent + ty
        result.append((rx, ry))
    return result


# =============================================================================
# Fonctions internes BL+Fill
# =============================================================================

def _contour_vers_polygon(contour: Contour) -> Polygon:
    """Convertit un contour (liste de points) en polygone Shapely valide."""
    try:
        poly = Polygon(contour)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            poly = Polygon(contour).convex_hull
    except Exception:
        poly = Polygon(contour).convex_hull
    return poly


def _candidats_coins(infos: List[_PlacementInfo], marge: float) -> list:
    """
    Génère les positions candidates pour le prochain placement.

    Deux niveaux :
      1. Coins classiques (BL) : à droite et au-dessus de chaque pièce.
      2. Grille croisée : toutes les combinaisons (bord_droit, bord_supérieur)
         des pièces déjà placées — permet de « glisser » des pièces dans des
         espaces qui ne coïncident pas avec un unique coin existant.

    Tri par (y, x) — priorité aux positions basses (Bottom-Left).
    """
    pts: set = set()
    pts.add((marge, marge))
    right_xs = [marge]
    top_ys = [marge]

    for info in infos:
        x0, y0, x1, y1 = info.poly_placed.bounds
        pts.add((x1 + marge, marge))
        pts.add((x1 + marge, y0))
        pts.add((marge, y1 + marge))
        pts.add((x0, y1 + marge))
        right_xs.append(x1 + marge)
        top_ys.append(y1 + marge)

    for x in right_xs:
        for y in top_ys:
            pts.add((x, y))

    return sorted(pts, key=lambda p: (round(p[1], 4), round(p[0], 4)))


def _collision_libre(
    poly_norm: Polygon,
    cx: float,
    cy: float,
    pw: float,
    ph: float,
    placed_buffered: List[Polygon],
) -> bool:
    """
    Retourne True si poly_norm placé à (cx, cy) ne chevauche aucune pièce.

    Pré-filtre bounding-box pour éliminer rapidement les pièces distantes,
    puis test shapely uniquement si les boîtes se recoupent.
    """
    c_x0, c_y0 = cx, cy
    c_x1, c_y1 = cx + pw, cy + ph
    poly_place: Optional[Polygon] = None

    for pb in placed_buffered:
        pb_b = pb.bounds
        if c_x1 <= pb_b[0] or c_x0 >= pb_b[2]:
            continue
        if c_y1 <= pb_b[1] or c_y0 >= pb_b[3]:
            continue
        if poly_place is None:
            poly_place = shapely_translate(poly_norm, cx, cy)
        if poly_place.intersects(pb):
            return False
    return True


def _score_bbox(placed_polys: List[Polygon], candidat: Polygon) -> float:
    """
    Score = aire de la boîte englobante de toutes les pièces placées + le candidat.
    Minimiser ce score = minimiser la surface de tôle utilisée.
    """
    all_bounds = [p.bounds for p in placed_polys] + [candidat.bounds]
    min_x = min(b[0] for b in all_bounds)
    min_y = min(b[1] for b in all_bounds)
    max_x = max(b[2] for b in all_bounds)
    max_y = max(b[3] for b in all_bounds)
    return (max_x - min_x) * (max_y - min_y)


def _score_bbox_global(polys: List[Polygon]) -> float:
    """Aire de la boîte englobante globale (pour comparer plusieurs séquences)."""
    if not polys:
        return float('inf')
    min_x = min(p.bounds[0] for p in polys)
    min_y = min(p.bounds[1] for p in polys)
    max_x = max(p.bounds[2] for p in polys)
    max_y = max(p.bounds[3] for p in polys)
    return (max_x - min_x) * (max_y - min_y)


# =============================================================================
# Utilitaire public
# =============================================================================

def calculer_bbox_placements(contours_places: list) -> Tuple[float, float]:
    """
    Retourne (largeur, hauteur) de la boîte englobante de tous les ContourPlace.
    """
    if not contours_places:
        return 0.0, 0.0
    all_pts = [p for cp in contours_places for p in cp.points]
    if not all_pts:
        return 0.0, 0.0
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    return max(xs) - min(xs), max(ys) - min(ys)

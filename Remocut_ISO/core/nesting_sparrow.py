"""
core/nesting_sparrow.py — Nesting 2D irrégulier via spyrrow (sparrow 2025).

Sparrow : meilleur algorithme mondial pour le strip packing 2D irrégulier
(Gardeyn et al., EJOR 2025). Interface Python via la bibliothèque spyrrow.

Installation : pip install spyrrow

Deux profils :
    ANGLES_MOYENNE — rotations à 45° (8 orientations), calcul en ~1 min
    ANGLES_MAXI    — rotations à 1°  (360 orientations), calcul en ~10 min

Helpers publics utilisés par ThreadNestingSparrow (ui/main_window.py) :
    preparer_metas_pieces(pieces)
    placer_depuis_solution_pieces(placed_items, metas, pieces, largeur, hauteur)
    calculer_nesting_sparrow(...)    — appel bloquant (sans progression)
"""

import logging
import math
from typing import List, Optional, Tuple

from shapely.affinity import rotate as shapely_rotate
from shapely.affinity import translate as shapely_translate
from shapely.geometry import Polygon

logger = logging.getLogger(__name__)

# Type alias
Contour = List[Tuple[float, float]]

# Angles pour les deux profils
ANGLES_MOYENNE: List[int] = list(range(0, 360, 45))   # 8 orientations (0°→315°, pas 45°)
ANGLES_MAXI:    List[int] = list(range(0, 360, 1))    # 360 orientations (pas 1°)


# =============================================================================
# Helpers publics
# =============================================================================

def preparer_metas_pieces(pieces: List[List[Contour]]) -> list:
    """
    Normalise chaque pièce (extérieur → polygon shapely normalisé à l'origine)
    et retourne les métadonnées nécessaires à spyrrow et à la reconstruction.

    Returns:
        list de dict : {
            'idx_piece'  : int,     — indice dans `pieces`
            'poly_norm'  : Polygon, — extérieur normalisé (bbox en (0, 0))
            'coords'     : list,    — coords du poly_norm (pour spyrrow Item)
            'norm_dx'    : float,   — décalage de normalisation X (-minx)
            'norm_dy'    : float,   — décalage de normalisation Y (-miny)
        }
    """
    metas = []
    for idx, piece in enumerate(pieces):
        ext = piece[0]
        try:
            poly = Polygon(ext)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                poly = Polygon(ext).convex_hull
        except Exception:
            poly = Polygon(ext).convex_hull

        minx, miny, _, _ = poly.bounds
        poly_norm = shapely_translate(poly, -minx, -miny)
        coords = [(float(x), float(y)) for x, y in poly_norm.exterior.coords]
        metas.append({
            'idx_piece': idx,
            'poly_norm': poly_norm,
            'coords':    coords,
            'norm_dx':   -minx,
            'norm_dy':   -miny,
        })
    return metas


def placer_depuis_solution_pieces(
    placed_items,
    metas: list,
    pieces: List[List[Contour]],
    largeur_tole: float,
    hauteur_tole: float,
) -> Tuple[list, bool]:
    """
    Convertit la solution spyrrow (placed_items) en List[ContourPlace].

    La transformation appliquée à chaque point (x, y) d'un contour original :
      1. Translate par (norm_dx, norm_dy)  — normalisation initiale
      2. Rotation par `angle` autour de (0, 0)
      3. Translate par (tx, ty)  — translation spyrrow

    Args:
        placed_items  : itérable de PlacedItem (solution.placed_items)
        metas         : retour de preparer_metas_pieces()
        pieces        : List[List[Contour]] originales
        largeur_tole  : largeur maximale de la tôle (mm)
        hauteur_tole  : hauteur maximale de la tôle (mm)

    Returns:
        (contours_places, tous_places)
    """
    # Import tardif pour éviter l'import circulaire
    from core.nesting import ContourPlace
    from core.geometry import normalize_orientation

    placed_map = {pi.id: pi for pi in placed_items}
    contours_places = []
    nb_non = 0
    id_piece_global = 0

    for m in metas:
        idx = m['idx_piece']
        pi = placed_map.get(f"p{idx}")

        if pi is None:
            nb_non += 1
            continue

        tx_sol = float(pi.translation[0])
        ty_sol = float(pi.translation[1])
        angle = float(pi.rotation)

        # Vérifier que la pièce est dans les limites de la tôle
        poly_norm = m['poly_norm']
        if abs(angle) > 1e-9:
            poly_rot = shapely_rotate(poly_norm, angle,
                                      origin=(0, 0), use_radians=False)
        else:
            poly_rot = poly_norm
        poly_placed = shapely_translate(poly_rot, tx_sol, ty_sol)

        bx0, by0, bx1, by1 = poly_placed.bounds
        if (bx0 < -1e-3 or by0 < -1e-3
                or bx1 > largeur_tole + 1e-3
                or by1 > hauteur_tole + 1e-3):
            nb_non += 1
            logger.debug(
                f"Pièce {idx} rejetée (hors tôle) : "
                f"bbox [{bx0:.1f},{by0:.1f},{bx1:.1f},{by1:.1f}]"
            )
            continue

        # Appliquer la transformation à tous les contours de la pièce
        piece = pieces[idx]
        for idx_c, contour in enumerate(piece):
            est_int = (idx_c > 0)
            pts = _appliquer_transform_sparrow(
                contour,
                m['norm_dx'], m['norm_dy'],
                angle,
                tx_sol, ty_sol,
            )
            pts = normalize_orientation(pts, exterieur=not est_int)
            contours_places.append(ContourPlace(
                points=pts,
                est_interieur=est_int,
                id_piece=id_piece_global,
                offset_x=tx_sol,
                offset_y=ty_sol,
                points_originaux=list(contour),
            ))
        id_piece_global += 1

    return contours_places, nb_non == 0


def _appliquer_transform_sparrow(
    contour: Contour,
    norm_dx: float,
    norm_dy: float,
    angle_deg: float,
    tx: float,
    ty: float,
) -> Contour:
    """
    Applique la séquence de transformations spyrrow à un contour :
      1. Translate par (norm_dx, norm_dy)  [normalisation bbox → origine]
      2. Rotation par angle_deg autour de (0, 0)
      3. Translate par (tx, ty)  [position finale sur la tôle]

    Args:
        contour  : Points (x, y) du contour en coordonnées originales.
        norm_dx  : -minx du polygone extérieur (normalisation X).
        norm_dy  : -miny du polygone extérieur (normalisation Y).
        angle_deg: Angle de rotation fourni par spyrrow (degrés).
        tx, ty   : Translation fournie par spyrrow.
    """
    if angle_deg == 0:
        return [(x + norm_dx + tx, y + norm_dy + ty) for x, y in contour]

    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    result = []
    for x, y in contour:
        # Étape 1 : normalisation
        xn = x + norm_dx
        yn = y + norm_dy
        # Étape 2 : rotation autour de (0, 0)
        rx = cos_a * xn - sin_a * yn
        ry = sin_a * xn + cos_a * yn
        # Étape 3 : translation finale
        result.append((rx + tx, ry + ty))
    return result


# =============================================================================
# Fonction principale (appel bloquant, sans suivi de progression)
# =============================================================================

def calculer_nesting_sparrow(
    pieces: List[List[Contour]],
    largeur_tole: float,
    hauteur_tole: float,
    marge: float,
    angles_deg: Optional[List[int]],
    time_limit_s: int,
    num_workers: int,
) -> Tuple[list, bool]:
    """
    Nesting sparrow — appel bloquant sans suivi de progression.

    Préférer ThreadNestingSparrow (ui/main_window.py) pour une utilisation
    interactive avec affichage des solutions intermédiaires et bouton stop.

    Args:
        pieces        : List[List[Contour]] — pièces à placer.
        largeur_tole  : Dimension X max de la tôle (mm).
        hauteur_tole  : Dimension Y max / strip_height sparrow (mm).
        marge         : Jeu minimum pièce-pièce (mm).
        angles_deg    : Angles autorisés en degrés (None = libre).
        time_limit_s  : Durée maximale d'optimisation (secondes).
        num_workers   : Threads parallèles (0 = auto-détection).

    Returns:
        (contours_places, tous_places)

    Raises:
        ImportError : si spyrrow n'est pas installé.
    """
    try:
        import spyrrow
    except ImportError:
        raise ImportError(
            "La bibliothèque spyrrow n'est pas installée.\n"
            "Installez-la avec :  pip install spyrrow"
        )

    if not pieces:
        return [], True

    metas = preparer_metas_pieces(pieces)
    items = [
        spyrrow.Item(
            f"p{m['idx_piece']}",
            m['coords'],
            demand=1,
            allowed_orientations=angles_deg,
        )
        for m in metas
    ]

    instance = spyrrow.StripPackingInstance(
        "remocut_nesting",
        strip_height=hauteur_tole,
        items=items,
    )
    config = spyrrow.StripPackingConfig(
        early_termination=True,
        total_computation_time=time_limit_s,
        min_items_separation=marge if marge > 0.0 else None,
        num_workers=num_workers if num_workers > 0 else None,
        seed=42,
    )

    solution = instance.solve(config)
    return placer_depuis_solution_pieces(
        solution.placed_items, metas, pieces, largeur_tole, hauteur_tole
    )

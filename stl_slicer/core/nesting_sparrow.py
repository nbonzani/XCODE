# =============================================================================
# core/nesting_sparrow.py — Nesting 2D irrégulier via sparrow (spyrrow)
#
# Sparrow : meilleur algorithme mondial pour le strip packing 2D irrégulier
# (Gardeyn et al., EJOR 2025). Interface Python via la bibliothèque spyrrow.
#
# Installation : pip install spyrrow
#
# Deux profils :
#   ANGLES_MOYENNE  — rotations à 45° (8 orientations), rapide
#   ANGLES_MAXI     — rotations à 1°  (360 orientations)
#
# Fonctionnement :
#   - solve() est bloquant mais supporte un ProgressQueue pour les solutions
#     intermédiaires. Le thread de calcul fait tourner solve() dans un thread
#     Python daemon et poll queue.drain() toutes les 400 ms.
#   - Les helpers _preparer_metas() et _placer_depuis_solution() sont exposés
#     pour être utilisés directement par ThreadNestingSparrow (ui/main_window).
# =============================================================================

from typing import List, Tuple, Optional

from shapely.geometry import Polygon
from shapely.affinity import rotate as shapely_rotate, translate


# Type partagé avec core/nesting.py
PlacementType = Tuple[Polygon, float, float, int]

# Angles pour les deux profils
ANGLES_MOYENNE: List[int] = list(range(0, 360, 45))   # 8 orientations
ANGLES_MAXI:    List[int] = list(range(0, 360, 1))    # 360 orientations


# =============================================================================
# Helpers publics (utilisés aussi par ThreadNestingSparrow)
# =============================================================================

def preparer_metas(polygones: List[Polygon]) -> list:
    """
    Normalise chaque polygone à l'origine et retourne les métadonnées
    nécessaires à la création des items spyrrow et à la reconstruction
    des placements depuis une solution.

    Retourne une liste de dict :
      { 'idx_orig': int, 'poly_norm': Polygon, 'coords': list[(x,y)] }
    """
    metas = []
    for idx, poly in enumerate(polygones):
        minx, miny, _, _ = poly.bounds
        poly_norm = translate(poly, -minx, -miny)
        coords = [(float(x), float(y)) for x, y in poly_norm.exterior.coords]
        metas.append({
            'idx_orig':  idx,
            'poly_norm': poly_norm,
            'coords':    coords,
        })
    return metas


def placer_depuis_solution(placed_items, metas: list,
                            largeur_plaque: float,
                            hauteur_plaque: float,
                            espacement_bord: float = 0.0) -> Tuple[List[PlacementType], bool]:
    """
    Convertit la liste placed_items d'une StripPackingSolution en
    liste de PlacementType (polygone_placé, tx, ty, idx_original).

    Les pièces dont la boîte englobante dépasse la plaque sont retirées.

    Paramètres :
        placed_items   : solution.placed_items (itérable de PlacedItem)
        metas          : liste retournée par preparer_metas()
        largeur_plaque : largeur maximale de la plaque (mm)
        hauteur_plaque : hauteur maximale de la plaque (mm)
        espacement_bord: marge minimale pièces/bord (mm).
                         Décale toutes les pièces de (+epb, +epb) pour
                         garantir la marge côté gauche et bas.
                         spyrrow doit recevoir strip_height réduit de 2×epb
                         pour que la marge côté haut soit aussi respectée.
    """
    placed_map = {pi.id: pi for pi in placed_items}
    placements: List[PlacementType] = []
    nb_non = 0

    # Limites intérieures de la zone valide (après marge de bord)
    lim_x = largeur_plaque - espacement_bord
    lim_y = hauteur_plaque - espacement_bord

    for m in metas:
        idx = m['idx_orig']
        pi  = placed_map.get(f"p{idx}")

        if pi is None:
            nb_non += 1
            continue

        # Décaler de espacement_bord pour respecter la marge côté gauche/bas
        tx    = float(pi.translation[0]) + espacement_bord
        ty    = float(pi.translation[1]) + espacement_bord
        angle = float(pi.rotation)

        if abs(angle) > 1e-9:
            poly_rot = shapely_rotate(m['poly_norm'], angle,
                                      origin=(0, 0), use_radians=False)
        else:
            poly_rot = m['poly_norm']

        poly_placed = translate(poly_rot, tx, ty)

        bx0, by0, bx1, by1 = poly_placed.bounds
        if bx0 < -1e-3 or by0 < -1e-3:
            nb_non += 1
            continue
        if bx1 > lim_x + 1e-3 or by1 > lim_y + 1e-3:
            nb_non += 1
            continue

        placements.append((poly_placed, tx, ty, idx))

    return placements, nb_non == 0


# =============================================================================
# Fonction principale (appel bloquant, sans suivi de progression)
# =============================================================================

def calculer_nesting_sparrow(
    polygones: List[Polygon],
    largeur_plaque: float,
    hauteur_plaque: float,
    espacement: float,
    angles_deg: Optional[List[int]],
    time_limit_s: int,
    num_workers: int,
    espacement_bord: float = 0.0,
) -> Tuple[List[PlacementType], bool]:
    """
    Nesting optimisé via sparrow — appel bloquant sans suivi de progression.

    Préférer ThreadNestingSparrow (ui/main_window) pour une utilisation
    interactive avec affichage des solutions intermédiaires et bouton stop.

    sparrow résout le strip packing 2D irrégulier :
      - hauteur de la bande fixée = hauteur_plaque − 2×espacement_bord
        (les pièces sont ensuite décalées de +espacement_bord en Y)
      - longueur minimisée (les pièces hors largeur_plaque−espacement_bord sont ignorées)

    Paramètres :
        polygones       : liste de Polygon shapely à placer
        largeur_plaque  : dimension X max de la plaque (mm)
        hauteur_plaque  : dimension Y max / strip_height sparrow (mm)
        espacement      : jeu minimum pièce-pièce (mm) — natif sparrow
        angles_deg      : angles autorisés en degrés (None = rotation libre)
        time_limit_s    : durée maximale d'optimisation en secondes
        num_workers     : threads parallèles (0 ou None = auto-détection)
        espacement_bord : marge minimale pièces/bord de plaque (mm)
    """
    try:
        import spyrrow
    except ImportError:
        raise ImportError(
            "La bibliothèque spyrrow n'est pas installée.\n"
            "Installez-la avec :  pip install spyrrow"
        )

    if not polygones:
        return [], True

    metas = preparer_metas(polygones)
    items = [
        spyrrow.Item(f"p{m['idx_orig']}", m['coords'],
                     demand=1, allowed_orientations=angles_deg)
        for m in metas
    ]

    # Réduire la hauteur de la bande de 2×epb : spyrrow place les pièces dans
    # [0, H−2·epb], puis placer_depuis_solution les décale de +epb en Y.
    effective_height = max(1.0, hauteur_plaque - 2.0 * espacement_bord)

    instance = spyrrow.StripPackingInstance(
        "stl_slicer_nesting",
        strip_height=effective_height,
        items=items
    )
    config = spyrrow.StripPackingConfig(
        early_termination=True,
        total_computation_time=time_limit_s,
        min_items_separation=espacement if espacement > 0.0 else None,
        num_workers=num_workers if num_workers > 0 else None,
        seed=42
    )

    solution = instance.solve(config)
    return placer_depuis_solution(solution.placed_items, metas,
                                  largeur_plaque, hauteur_plaque,
                                  espacement_bord=espacement_bord)

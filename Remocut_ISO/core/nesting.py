"""
core/nesting.py — Placement des pièces sur la tôle (algorithme grille V1).

Algorithme V1 : placement en rangées successives gauche → droite, bas → haut.
Aucune rotation des pièces en V1.

Données exportées :
  - ContourPlace : dataclass représentant un contour positionné sur la tôle.
  - placer() : fonction principale de nesting.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.geometry import (
    bounding_box,
    is_interior,
    normalize_orientation,
    translater,
)

logger = logging.getLogger(__name__)

# Type alias
Contour = List[Tuple[float, float]]


@dataclass
class ContourPlace:
    """
    Contour positionné sur la tôle après nesting.

    Attributs :
        points          : Points en position finale sur la tôle (mm, Y vers le haut).
        est_interieur   : True si ce contour est un trou (intérieur).
        id_piece        : Indice de la pièce d'origine (0-based).
        offset_x        : Décalage X appliqué lors du nesting.
        offset_y        : Décalage Y appliqué lors du nesting.
        points_originaux: Points avant translation (référence pièce).
    """
    points: List[Tuple[float, float]]
    est_interieur: bool
    id_piece: int
    offset_x: float
    offset_y: float
    points_originaux: List[Tuple[float, float]] = field(default_factory=list)
    # Mis à True par ajuster_points_depart() s'il n'a trouvé aucune position de
    # piquage satisfaisant la marge d'écart avec les pièces voisines.
    probleme_piquage: bool = False


def placer(
    contours: List[Contour],
    largeur_tole: float,
    hauteur_tole: float,
    marge: float = 10.0,
) -> List[ContourPlace]:
    """
    Place les contours sur la tôle selon un algorithme de rangées (grille V1).

    Règles de placement :
      - Les pièces sont placées de gauche à droite, puis bas en haut
        (dans le repère interne Y vers le haut).
      - Une marge est respectée entre chaque pièce et les bords de la tôle.
      - Les contours intérieurs (trous) sont regroupés avec leur pièce parent.

    Args:
        contours       : Liste de contours DXF bruts (tous considérés comme extérieurs).
        largeur_tole   : Largeur de la tôle en mm.
        hauteur_tole   : Hauteur de la tôle en mm.
        marge          : Distance minimale entre pièces et bords (mm).

    Returns:
        Liste de ContourPlace avec positions finales sur la tôle.

    Raises:
        ValueError : Si une pièce ne rentre pas dans la tôle.
    """
    if not contours:
        return []

    # --- Étape 1 : Regrouper les contours en pièces ---
    # Chaque "pièce" est une liste de contours (1 extérieur + N trous intérieurs).
    pieces = _regrouper_en_pieces(contours)
    return _placer_pieces(pieces, largeur_tole, hauteur_tole, marge)


def placer_avec_quantites(
    entrees: List[tuple],
    largeur_tole: float,
    hauteur_tole: float,
    marge: float = 10.0,
) -> List[ContourPlace]:
    """
    Place des pièces issues de plusieurs fichiers DXF avec des quantités.

    Chaque entrée est un tuple (contours_dxf, quantite) où :
      - contours_dxf : Liste de contours d'un seul fichier DXF.
      - quantite      : Nombre d'exemplaires à découper (>= 1).

    Le groupage intérieur/extérieur est fait par fichier DXF pour éviter
    les confusions de hiérarchie entre fichiers différents.

    Args:
        entrees      : List[Tuple[List[Contour], int]] — (contours, quantite) par DXF.
        largeur_tole : Largeur de la tôle en mm.
        hauteur_tole : Hauteur de la tôle en mm.
        marge        : Distance minimale entre pièces et bords (mm).

    Returns:
        Liste de ContourPlace avec positions finales sur la tôle.

    Raises:
        ValueError : Si une pièce ne rentre pas dans la tôle.
    """
    import copy

    if not entrees:
        return []

    # Grouper chaque DXF indépendamment, puis répliquer selon la quantité
    pieces_all: List[List[Contour]] = []
    for contours_dxf, quantite in entrees:
        if not contours_dxf or quantite <= 0:
            continue
        pieces_dxf = _regrouper_en_pieces(contours_dxf)
        for _ in range(int(quantite)):
            pieces_all.extend(copy.deepcopy(pieces_dxf))

    if not pieces_all:
        return []

    return _placer_pieces(pieces_all, largeur_tole, hauteur_tole, marge)


def _placer_pieces(
    pieces: List[List[Contour]],
    largeur_tole: float,
    hauteur_tole: float,
    marge: float,
) -> List[ContourPlace]:
    """
    Algorithme de placement en rangées pour une liste de pièces pré-groupées.

    Args:
        pieces       : Liste de pièces, chaque pièce = [exterieur, trou1, ...].
        largeur_tole : Largeur utile de la tôle (mm).
        hauteur_tole : Hauteur utile de la tôle (mm).
        marge        : Espacement entre pièces et bords (mm).

    Returns:
        Liste de ContourPlace positionnés sur la tôle.
    """
    # --- Étape 2 : Vérification que chaque pièce rentre dans la tôle ---
    zone_util_w = largeur_tole - 2 * marge
    zone_util_h = hauteur_tole - 2 * marge

    for i, piece in enumerate(pieces):
        contour_ext = piece[0]
        x_min, y_min, x_max, y_max = bounding_box(contour_ext)
        w = x_max - x_min
        h = y_max - y_min
        if w > zone_util_w or h > zone_util_h:
            raise ValueError(
                f"La pièce {i + 1} ({w:.1f} × {h:.1f} mm) est trop grande pour la tôle "
                f"(zone utile : {zone_util_w:.1f} × {zone_util_h:.1f} mm)."
            )

    # --- Étape 3 : Placement en rangées ---
    contours_places = []
    cursor_x = marge
    cursor_y = marge
    hauteur_rangee_courante = 0.0

    for id_piece, piece in enumerate(pieces):
        contour_ext = piece[0]
        x_min, y_min, x_max, y_max = bounding_box(contour_ext)
        largeur_piece = x_max - x_min
        hauteur_piece = y_max - y_min

        # Passer à la rangée suivante si pas assez de place horizontalement
        if cursor_x + largeur_piece > largeur_tole - marge and cursor_x > marge:
            cursor_x = marge
            cursor_y += hauteur_rangee_courante + marge
            hauteur_rangee_courante = 0.0

        # Vérifier qu'il reste de la place verticalement
        if cursor_y + hauteur_piece > hauteur_tole - marge:
            raise ValueError(
                f"La tôle est pleine : impossible de placer la pièce {id_piece + 1}. "
                f"Augmentez le format de tôle ou réduisez la marge."
            )

        # Calculer le décalage (aligner le coin bas-gauche de la bbox sur cursor_x/y)
        offset_x = cursor_x - x_min
        offset_y = cursor_y - y_min

        # Placer tous les contours de la pièce
        for idx_c, contour in enumerate(piece):
            est_int = (idx_c > 0)  # indice 0 = extérieur, reste = trous
            pts_places = translater(contour, offset_x, offset_y)
            pts_places = normalize_orientation(pts_places, exterieur=not est_int)

            contours_places.append(ContourPlace(
                points=pts_places,
                est_interieur=est_int,
                id_piece=id_piece,
                offset_x=offset_x,
                offset_y=offset_y,
                points_originaux=list(contour),
            ))

        # Avancer le curseur
        cursor_x += largeur_piece + marge
        hauteur_rangee_courante = max(hauteur_rangee_courante, hauteur_piece)

    logger.info(
        f"Nesting : {len(pieces)} pièce(s) placée(s) → "
        f"{len(contours_places)} contour(s) au total."
    )
    return contours_places


def _regrouper_en_pieces(
    contours: List[Contour],
) -> List[List[Contour]]:
    """
    Regroupe les contours en pièces (un contour extérieur + ses trous intérieurs).

    Un contour A est classé comme trou s'il est à l'intérieur d'un autre contour B
    (vérifié avec shapely via is_interior).

    Pour la V1, un contour ne peut être intérieur que d'un seul contour extérieur.

    Args:
        contours: Liste de contours bruts.

    Returns:
        Liste de pièces. Chaque pièce est [contour_exterieur, trou1, trou2, ...].
    """
    n = len(contours)
    if n == 0:
        return []
    if n == 1:
        return [contours]

    # Déterminer pour chaque contour s'il est intérieur à un autre
    # matrice_inclusion[i][j] = True si contour i est à l'intérieur du contour j
    parent = {i: None for i in range(n)}

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            try:
                if is_interior(contours[i], contours[j]):
                    # Choisir le parent le plus immédiat (le plus petit)
                    if parent[i] is None:
                        parent[i] = j
                    else:
                        # Garder le parent dont la bbox est la plus petite
                        bb_cur = bounding_box(contours[parent[i]])
                        bb_new = bounding_box(contours[j])
                        aire_cur = (bb_cur[2] - bb_cur[0]) * (bb_cur[3] - bb_cur[1])
                        aire_new = (bb_new[2] - bb_new[0]) * (bb_new[3] - bb_new[1])
                        if aire_new < aire_cur:
                            parent[i] = j
            except Exception as e:
                logger.debug(f"Erreur test inclusion contour {i} dans {j} : {e}")

    # Construire les pièces : les contours sans parent sont extérieurs
    exterieurs = [i for i in range(n) if parent[i] is None]
    pieces = []

    for ext_idx in exterieurs:
        # Rassembler les trous directs de ce contour extérieur
        trous = [i for i in range(n) if parent[i] == ext_idx]
        piece = [contours[ext_idx]] + [contours[t] for t in trous]
        pieces.append(piece)

    # Contours orphelins (intérieurs sans parent reconnu) → traiter comme extérieurs
    indices_traites = set(exterieurs)
    for ext_idx in exterieurs:
        for t in [i for i in range(n) if parent[i] == ext_idx]:
            indices_traites.add(t)

    for i in range(n):
        if i not in indices_traites:
            logger.warning(
                f"Contour {i} orphelin (aucun parent détecté) → traité comme pièce indépendante."
            )
            pieces.append([contours[i]])

    return pieces


def construire_pieces(entrees: List[tuple]) -> List[List[Contour]]:
    """
    Construit la liste complète de pièces depuis les entrées (contours, quantité).

    Chaque DXF est groupé indépendamment (pour éviter que des contours
    de fichiers différents soient détectés comme intérieur/extérieur l'un de l'autre),
    puis répliqué selon la quantité demandée.

    Args:
        entrees : List[Tuple[List[Contour], int]] — (contours_dxf, quantite) par DXF.

    Returns:
        Liste de pièces — chaque pièce = [extérieur, trou1, ...].
    """
    import copy

    pieces_all: List[List[Contour]] = []
    for contours_dxf, quantite in entrees:
        if not contours_dxf or quantite <= 0:
            continue
        pieces_dxf = _regrouper_en_pieces(contours_dxf)
        for _ in range(int(quantite)):
            pieces_all.extend(copy.deepcopy(pieces_dxf))
    return pieces_all


def placer_avec_methode(
    entrees: List[tuple],
    largeur_tole: float,
    hauteur_tole: float,
    marge: float = 10.0,
    methode: str = 'simple',
    callback_progression=None,
) -> tuple:
    """
    Place des pièces selon la méthode de nesting choisie.

    Méthodes disponibles :
        'simple'      — Rangées gauche→droite (rapide, sans rotation).
        'aire'        — BL+Fill, ordre aire décroissante, 12 rotations.
        'perimetre'   — BL+Fill, ordre périmètre décroissant, 12 rotations.
        'dim_max'     — BL+Fill, ordre dimension max décroissante, 12 rotations.
        'multi'       — BL+Fill, 4 ordres de tri, retient le meilleur résultat.
        'sparrow_moy' — Sparrow, 8 rotations (45°), 1 min. (via ThreadNestingSparrow)
        'sparrow_max' — Sparrow, 360 rotations (1°), 10 min. (via ThreadNestingSparrow)

    Note : pour les méthodes sparrow, préférer ThreadNestingSparrow dans ui/main_window.py
    pour bénéficier du suivi de progression et du bouton d'arrêt.

    Args:
        entrees              : List[Tuple[List[Contour], int]] — (contours, quantite).
        largeur_tole         : Largeur utile de la tôle (mm).
        hauteur_tole         : Hauteur utile de la tôle (mm).
        marge                : Espacement minimum pièce-pièce et pièce-bord (mm).
        methode              : Identifiant de la méthode (voir ci-dessus).
        callback_progression : fonction(etape, total) ou None — pour BL+Fill.

    Returns:
        Pour 'simple' : List[ContourPlace] (lève ValueError si pièce trop grande).
        Pour les autres méthodes : Tuple[List[ContourPlace], bool tous_places].
    """
    if not entrees:
        return ([], True) if methode != 'simple' else []

    pieces = construire_pieces(entrees)
    if not pieces:
        return ([], True) if methode != 'simple' else []

    if methode == 'simple':
        # Comportement identique à placer_avec_quantites — lève ValueError si plein
        return _placer_pieces(pieces, largeur_tole, hauteur_tole, marge)

    elif methode in ('aire', 'perimetre', 'dim_max', 'multi'):
        from core.nesting_optimise import placer_pieces_optimise
        return placer_pieces_optimise(
            pieces, largeur_tole, hauteur_tole, marge,
            methode=methode,
            callback_progression=callback_progression,
        )

    elif methode in ('sparrow_moy', 'sparrow_max'):
        from core.nesting_sparrow import (
            calculer_nesting_sparrow, ANGLES_MOYENNE, ANGLES_MAXI
        )
        import os
        angles = ANGLES_MOYENNE if methode == 'sparrow_moy' else ANGLES_MAXI
        time_limit = 60 if methode == 'sparrow_moy' else 600
        num_workers = max(1, os.cpu_count() or 1)
        if methode == 'sparrow_max':
            num_workers = max(1, int(num_workers * 0.8))
        return calculer_nesting_sparrow(
            pieces, largeur_tole, hauteur_tole, marge,
            angles_deg=angles, time_limit_s=time_limit, num_workers=num_workers,
        )

    else:
        raise ValueError(f"Méthode de nesting inconnue : '{methode}'")


def verifier_chevauchement(contours_places: List[ContourPlace]) -> List[str]:
    """
    Vérifie si des pièces se chevauchent après nesting.

    Args:
        contours_places: Liste de contours placés.

    Returns:
        Liste de messages d'avertissement (vide si pas de chevauchement).
    """
    avertissements = []
    exterieurs = [cp for cp in contours_places if not cp.est_interieur]

    try:
        from shapely.geometry import Polygon

        polys = []
        for cp in exterieurs:
            try:
                poly = Polygon(cp.points)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                polys.append((cp.id_piece, poly))
            except Exception:
                pass

        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                pid_i, poly_i = polys[i]
                pid_j, poly_j = polys[j]
                if pid_i == pid_j:
                    continue
                if poly_i.intersects(poly_j) and not poly_i.touches(poly_j):
                    msg = (
                        f"Chevauchement détecté entre la pièce {pid_i + 1} "
                        f"et la pièce {pid_j + 1} !"
                    )
                    avertissements.append(msg)
                    logger.warning(msg)

    except ImportError:
        logger.debug("shapely non disponible, vérification chevauchement ignorée.")

    return avertissements

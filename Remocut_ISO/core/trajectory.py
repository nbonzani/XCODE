"""
core/trajectory.py — Calcul de l'ordre de découpe et optimisation des trajectoires.

Algorithme en 3 passes :
  1. **Groupement par pièce** : trous d'abord (NN interne), puis contour extérieur.
     Contrainte technologique : une pièce ne peut pas bouger avant la fin de sa découpe.
  2. **Nearest Neighbor** sur la séquence de pièces, en utilisant les points réels
     de piquage (lead-in) et de sortie (lead-out).
  3. **2-opt** : amélioration locale en inversant des sous-séquences de pièces
     pour réduire la distance totale à vide (G00).

Les pièces sont traitées comme des blocs atomiques : 2-opt ne réordonne que
les pièces entre elles, jamais les contours à l'intérieur d'une pièce (pour
préserver la règle "trous avant extérieur").
"""

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.nesting import ContourPlace
from core.geometry import calculer_lead_in, calculer_lead_out

logger = logging.getLogger(__name__)

Contour = List[Tuple[float, float]]
Point = Tuple[float, float]


@dataclass
class StatsTrajectoire:
    """Statistiques de l'optimisation de trajectoire."""
    distance_initiale_mm: float = 0.0
    distance_finale_mm: float = 0.0
    nb_contours: int = 0
    nb_pieces: int = 0
    nb_passes_2opt: int = 0
    gain_pourcent: float = 0.0
    duree_calcul_ms: float = 0.0


@dataclass
class _BlocPiece:
    """
    Bloc atomique représentant une pièce : contours intérieurs dans l'ordre
    NN interne + contour extérieur en dernier. 2-opt ne réordonne que ces blocs.
    """
    id_piece: int
    contours: List[ContourPlace] = field(default_factory=list)
    point_entree: Point = (0.0, 0.0)   # piquage du 1er contour
    point_sortie: Point = (0.0, 0.0)   # sortie du dernier contour


# =============================================================================
# API publique
# =============================================================================

def calculer_trajectoires(
    contours_places: List[ContourPlace],
    longueur_lead_in: float = 5.0,
    longueur_lead_out: float = 5.0,
    origine: Point = (0.0, 0.0),
    activer_2opt: bool = True,
    max_passes_2opt: int = 50,
) -> Tuple[List[ContourPlace], StatsTrajectoire]:
    """
    Calcule l'ordre optimal de découpe et minimise les déplacements G00 à vide.

    Args:
        contours_places   : Contours placés issus du nesting.
        longueur_lead_in  : Longueur du lead-in (mm) — pour calculer le point réel de piquage.
        longueur_lead_out : Longueur du lead-out (mm) — pour calculer le point réel de sortie.
        origine           : Position initiale de la torche (typiquement 0,0).
        activer_2opt      : Activer l'amélioration 2-opt (recommandé).
        max_passes_2opt   : Limite de sécurité pour l'itération 2-opt.

    Returns:
        (contours_ordonnes, stats)
    """
    import time
    t0 = time.time()

    stats = StatsTrajectoire(nb_contours=len(contours_places))

    if not contours_places:
        return [], stats

    # --- Étape 1 : construire les blocs-pièces (trous + extérieur) ---
    blocs = _construire_blocs_pieces(
        contours_places, longueur_lead_in, longueur_lead_out
    )
    stats.nb_pieces = len(blocs)

    if not blocs:
        return [], stats

    # --- Étape 2 : Nearest Neighbor sur les blocs ---
    blocs_nn = _nearest_neighbor_blocs(blocs, origine)
    dist_nn = _distance_totale(blocs_nn, origine)
    stats.distance_initiale_mm = dist_nn

    # --- Étape 3 : 2-opt optionnel ---
    if activer_2opt and len(blocs_nn) >= 4:
        blocs_finaux, n_passes = _deux_opt(blocs_nn, origine, max_passes_2opt)
        stats.nb_passes_2opt = n_passes
    else:
        blocs_finaux = blocs_nn
        stats.nb_passes_2opt = 0

    dist_finale = _distance_totale(blocs_finaux, origine)
    stats.distance_finale_mm = dist_finale
    if dist_nn > 0:
        stats.gain_pourcent = 100.0 * (dist_nn - dist_finale) / dist_nn
    stats.duree_calcul_ms = (time.time() - t0) * 1000.0

    # Aplatir les blocs en liste plate de ContourPlace
    resultat: List[ContourPlace] = []
    for bloc in blocs_finaux:
        resultat.extend(bloc.contours)

    logger.info(
        f"Trajectoire : {stats.nb_pieces} pièce(s), {stats.nb_contours} contour(s) — "
        f"G00 initial {dist_nn:.0f} mm → final {dist_finale:.0f} mm "
        f"(gain {stats.gain_pourcent:.1f}%, {stats.nb_passes_2opt} passes 2-opt, "
        f"{stats.duree_calcul_ms:.0f} ms)"
    )
    return resultat, stats


def ordonner_decoupes(
    contours_places: List[ContourPlace],
    longueur_lead_in: float = 5.0,
    longueur_lead_out: float = 5.0,
) -> List[ContourPlace]:
    """
    [Rétro-compatibilité] Wrapper autour de calculer_trajectoires() qui ne
    retourne que la liste ordonnée.
    """
    contours, _ = calculer_trajectoires(
        contours_places, longueur_lead_in, longueur_lead_out
    )
    return contours


# =============================================================================
# Construction des blocs-pièces
# =============================================================================

def _construire_blocs_pieces(
    contours_places: List[ContourPlace],
    longueur_lead_in: float,
    longueur_lead_out: float,
) -> List[_BlocPiece]:
    """
    Regroupe les contours par pièce avec ordre interne :
      [trous NN-ordonnés..., contour extérieur]
    """
    # Grouper par id_piece
    pieces: dict = {}
    for cp in contours_places:
        d = pieces.setdefault(cp.id_piece, {'trous': [], 'exterieur': None})
        if cp.est_interieur:
            d['trous'].append(cp)
        else:
            d['exterieur'] = cp

    blocs: List[_BlocPiece] = []
    for id_p, contenu in pieces.items():
        # Ordre interne : trous NN, puis extérieur en dernier
        contours_bloc: List[ContourPlace] = []

        trous = contenu['trous']
        if trous:
            # Point d'entrée = centre approximatif de la pièce (via extérieur ou 1er trou)
            if contenu['exterieur'] is not None:
                ref = _point_piquage(contenu['exterieur'], longueur_lead_in)
            else:
                ref = _point_piquage(trous[0], longueur_lead_in)
            contours_bloc.extend(
                _nn_contours(trous, ref, longueur_lead_in, longueur_lead_out)
            )

        if contenu['exterieur'] is not None:
            contours_bloc.append(contenu['exterieur'])
        else:
            logger.warning(
                f"Pièce {id_p} : aucun contour extérieur trouvé. Placée telle quelle."
            )

        if not contours_bloc:
            continue

        bloc = _BlocPiece(id_piece=id_p, contours=contours_bloc)
        bloc.point_entree = _point_piquage(contours_bloc[0], longueur_lead_in)
        bloc.point_sortie = _point_sortie(contours_bloc[-1], longueur_lead_out)
        blocs.append(bloc)

    return blocs


def _nn_contours(
    contours: List[ContourPlace],
    depart: Point,
    longueur_lead_in: float,
    longueur_lead_out: float,
) -> List[ContourPlace]:
    """Ordonne des contours par NN sur piquage/sortie."""
    if len(contours) <= 1:
        return list(contours)
    restants = list(contours)
    pos = depart
    result: List[ContourPlace] = []
    while restants:
        idx = min(
            range(len(restants)),
            key=lambda i: _dist(pos, _point_piquage(restants[i], longueur_lead_in)),
        )
        cp = restants.pop(idx)
        result.append(cp)
        pos = _point_sortie(cp, longueur_lead_out)
    return result


# =============================================================================
# Nearest Neighbor sur les blocs
# =============================================================================

def _nearest_neighbor_blocs(
    blocs: List[_BlocPiece], origine: Point
) -> List[_BlocPiece]:
    """Ordonne les blocs-pièces par plus proche voisin."""
    if len(blocs) <= 1:
        return list(blocs)
    restants = list(blocs)
    pos = origine
    result: List[_BlocPiece] = []
    while restants:
        idx = min(
            range(len(restants)),
            key=lambda i: _dist(pos, restants[i].point_entree),
        )
        bloc = restants.pop(idx)
        result.append(bloc)
        pos = bloc.point_sortie
    return result


# =============================================================================
# 2-opt
# =============================================================================

def _deux_opt(
    blocs: List[_BlocPiece],
    origine: Point,
    max_passes: int = 50,
) -> Tuple[List[_BlocPiece], int]:
    """
    Amélioration locale 2-opt : inverse des sous-séquences de blocs pour
    réduire la distance G00 totale. Préserve la contrainte trous-avant-extérieur
    car 2-opt ne touche pas à l'ordre interne des blocs.

    Retourne (blocs_optimisés, nombre_de_passes_effectives).
    """
    n = len(blocs)
    if n < 4:
        return list(blocs), 0

    courants = list(blocs)
    amelioration = True
    n_passes = 0

    while amelioration and n_passes < max_passes:
        amelioration = False
        dist_courante = _distance_totale(courants, origine)

        for i in range(n - 1):
            for j in range(i + 1, n):
                # Tester l'inversion du segment [i..j]
                candidat = courants[:i] + courants[i:j + 1][::-1] + courants[j + 1:]
                dist_cand = _distance_totale(candidat, origine)
                if dist_cand + 1e-6 < dist_courante:
                    courants = candidat
                    dist_courante = dist_cand
                    amelioration = True
                    break  # recommencer une passe depuis le début
            if amelioration:
                break
        n_passes += 1

    return courants, n_passes


# =============================================================================
# Calculs de distance
# =============================================================================

def _distance_totale(blocs: List[_BlocPiece], origine: Point) -> float:
    """Distance totale G00 (déplacements à vide) : origine → B1.entrée → B1.sortie → B2.entrée → …"""
    if not blocs:
        return 0.0
    total = _dist(origine, blocs[0].point_entree)
    for i in range(len(blocs) - 1):
        total += _dist(blocs[i].point_sortie, blocs[i + 1].point_entree)
    return total


def _dist(a: Point, b: Point) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return math.sqrt(dx * dx + dy * dy)


def _point_piquage(cp: ContourPlace, longueur_lead_in: float) -> Point:
    """Point de piquage (départ lead-in) d'un contour."""
    if not cp.points or len(cp.points) < 2 or longueur_lead_in <= 0:
        return cp.points[0] if cp.points else (0.0, 0.0)
    try:
        piquage, _ = calculer_lead_in(cp.points, longueur_lead_in)
        return piquage
    except Exception:
        return cp.points[0]


def _point_sortie(cp: ContourPlace, longueur_lead_out: float) -> Point:
    """Point de fin (sortie lead-out) d'un contour."""
    if not cp.points or len(cp.points) < 2 or longueur_lead_out <= 0:
        return cp.points[0] if cp.points else (0.0, 0.0)
    try:
        sortie = calculer_lead_out(cp.points, longueur_lead_out)
        return sortie
    except Exception:
        return cp.points[0]

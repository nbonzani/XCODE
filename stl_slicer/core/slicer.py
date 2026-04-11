# =============================================================================
# core/slicer.py — Algorithme de sectionnement STL en tranches 2D
#
# Principe : on intersecte le maillage 3D avec une série de plans parallèles
# espacés de 'epaisseur' mm le long de l'axe choisi.
# Chaque intersection produit un ou plusieurs contours 2D (Shapely Polygon).
# =============================================================================

import numpy as np
import trimesh
from shapely.geometry import Polygon
from typing import List, Tuple


# Correspondance entre le nom d'axe et son indice (0=X, 1=Y, 2=Z)
AXES = {'X': 0, 'Y': 1, 'Z': 2}


def calculer_sections(
    mesh: trimesh.Trimesh,
    axe: str,
    epaisseur: float,
    offset: float = 0.0,
    callback_progression=None
) -> List[Tuple[float, List[Polygon]]]:
    """
    Calcule les sections 2D du maillage par plans parallèles.

    Pour chaque position de coupe, la fonction :
      1. Intersecte le maillage avec un plan perpendiculaire à l'axe choisi.
      2. Convertit le chemin 3D résultant en contours 2D planaires.
      3. Extrait les polygones shapely fermés.

    Paramètres:
        mesh (trimesh.Trimesh) : le maillage 3D source
        axe (str)              : 'X', 'Y' ou 'Z' — direction de coupe
        epaisseur (float)      : épaisseur de chaque tranche en mm
        offset (float)         : décalage de la première coupe en mm
                                 (permet de décaler la grille de coupes)
        callback_progression   : fonction optionnelle appelée avec (i, total)
                                 pour suivre la progression

    Retourne:
        Liste de tuples (position_mm, [polygone_1, polygone_2, ...])
        où position_mm est la cote de la coupe sur l'axe choisi.

    Notes:
        - Les sections sans intersection valide sont ignorées silencieusement.
        - Si un maillage a des géométries complexes (creux, multi-corps),
          chaque coupe peut produire plusieurs polygones distincts.
    """
    axe = axe.upper()
    if axe not in AXES:
        raise ValueError(f"Axe invalide '{axe}'. Choisir parmi : X, Y, Z.")

    idx_axe = AXES[axe]

    # Vecteur normal au plan de coupe (ex: Z → [0, 0, 1])
    normale = np.zeros(3)
    normale[idx_axe] = 1.0

    # Bornes du modèle sur l'axe de coupe
    borne_min = float(mesh.bounds[0][idx_axe])
    borne_max = float(mesh.bounds[1][idx_axe])

    # --- Génération des positions de grille alignées sur offset ---
    # La grille est : ..., offset-epaisseur, offset, offset+epaisseur, ...
    # k=0 correspond TOUJOURS à la position x=offset (l'origine du trièdre quand offset=0).
    #
    # k_min : plus petit entier tel que k*epaisseur+offset couvre la zone du modèle.
    #   → On force k_min ≤ 0 pour que la position offset soit TOUJOURS incluse,
    #     même si offset < borne_min (modèle ne commençant pas exactement à l'origine).
    # k_max : dernier entier avant borne_max.
    import math
    k_min = min(math.ceil((borne_min - offset) / epaisseur), 0)
    k_max = math.floor((borne_max - offset) / epaisseur)
    positions = np.array([k * epaisseur + offset
                          for k in range(k_min, k_max + 1)], dtype=float)
    # Pas de filtre sur la borne basse : les plans avant borne_min retournent None
    # depuis trimesh.section() et sont éliminés plus bas.
    # Filtre sur la borne haute uniquement pour éviter les plans hors modèle.
    positions = positions[positions <= borne_max]

    if len(positions) == 0:
        return []

    sections_resultats = []

    for i, pos in enumerate(positions):
        # Informer l'interface graphique de la progression (si demandé)
        if callback_progression is not None:
            callback_progression(i, len(positions))

        # Origine du plan de coupe (seule la coordonnée sur l'axe compte)
        origine = np.zeros(3)
        origine[idx_axe] = float(pos)

        try:
            # --- Intersection maillage / plan ---
            # trimesh.section() retourne un Path3D (chemin dans l'espace 3D)
            # ou None s'il n'y a pas d'intersection.
            section_3d = mesh.section(
                plane_origin=origine,
                plane_normal=normale
            )

            if section_3d is None:
                continue  # Pas d'intersection à cette hauteur

            # --- Conversion en contours 2D planaires ---
            # to_planar() projette les courbes 3D dans le plan de coupe
            # et retourne un Path2D + la matrice de transformation.
            section_2d, _transform = section_3d.to_planar()

            # --- Extraction des polygones fermés ---
            # polygons_full retourne les polygones shapely en tenant compte
            # des trous éventuels (géométries concaves ou creuses).
            polygones = section_2d.polygons_full

            if polygones and len(polygones) > 0:
                # Filtrer les polygones trop petits (artefacts numériques)
                polygones_valides = [p for p in polygones if p.area > 1e-6]
                if polygones_valides:
                    sections_resultats.append((float(pos), polygones_valides))

        except Exception:
            # Une coupe peut échouer sur des géométries non-manifold ou
            # des cas limites numériques — on ignore et on continue.
            continue

    return sections_resultats


def obtenir_positions_coupes(
    mesh: trimesh.Trimesh,
    axe: str,
    epaisseur: float,
    offset: float = 0.0
) -> Tuple[np.ndarray, int]:
    """
    Calcule les positions de coupe sans effectuer le sectionnement.
    Utile pour prévisualiser le nombre de tranches avant le calcul.

    Retourne:
        (tableau de positions, nombre de tranches estimé)
    """
    axe = axe.upper()
    idx_axe = AXES[axe]
    borne_min = float(mesh.bounds[0][idx_axe])
    borne_max = float(mesh.bounds[1][idx_axe])
    # Même logique que calculer_sections() : grille ancrée sur offset, k=0 toujours inclus
    import math
    k_min = min(math.ceil((borne_min - offset) / epaisseur), 0)
    k_max = math.floor((borne_max - offset) / epaisseur)
    positions = np.array([k * epaisseur + offset
                          for k in range(k_min, k_max + 1)], dtype=float)
    positions = positions[positions <= borne_max]
    return positions, len(positions)

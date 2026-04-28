# =============================================================================
# core/exporter.py — Export DXF des sections et du nesting
#
# Format DXF R2010 (compatible AutoCAD, FreeCAD, LaserCAD, etc.)
# Unités : millimètres
#
# Deux modes :
#   - Sans lissage (precision_lissage=None) : LWPOLYLINE fermée par contour.
#   - Avec lissage  (precision_lissage > 0) : entités natives LINE / ARC / CIRCLE
#     pour optimiser la taille du fichier et restaurer la précision des cercles.
# =============================================================================

import os
from typing import List, Tuple, Optional

import ezdxf
from ezdxf import units
from shapely.geometry import Polygon

from core.lissage import lisser_polygone, _angles_dxf


# Type d'un placement issu de nesting.py
PlacementType = Tuple[Polygon, float, float, int]


# =============================================================================
# Export des sections individuelles
# =============================================================================

def exporter_toutes_sections(
    sections: List[Tuple[float, List[Polygon]]],
    dossier_sortie: str,
    prefixe: str = 'section',
    precision_lissage: Optional[float] = None,
) -> List[str]:
    """
    Exporte chaque section dans un fichier DXF individuel.

    Nommage automatique : <prefixe>_001.dxf, <prefixe>_002.dxf, ...

    Paramètres:
        sections              : liste de (position_mm, [polygones])
        dossier_sortie        : dossier de sortie (créé si absent)
        prefixe               : préfixe du nom (défaut : 'section')
        precision_lissage     : si non None, active la reconnaissance d'arcs
                                et cercles avec cette tolérance (mm)

    Retourne:
        Liste des chemins absolus des fichiers créés.
    """
    os.makedirs(dossier_sortie, exist_ok=True)
    fichiers_crees = []
    prefixe_propre = _nettoyer_nom_fichier(prefixe) if prefixe else 'section'

    for i, (position, polygones) in enumerate(sections):
        nom_fichier = f"{prefixe_propre}_{i + 1:03d}.dxf"
        chemin = os.path.join(dossier_sortie, nom_fichier)
        exporter_section_dxf(polygones, chemin, position_mm=position,
                             precision_lissage=precision_lissage)
        fichiers_crees.append(chemin)

    return fichiers_crees


def _nettoyer_nom_fichier(nom: str) -> str:
    """Supprime les caractères interdits dans un nom de fichier Windows."""
    import re
    return re.sub(r'[\\/:*?"<>|]', '_', nom).strip()


def exporter_section_dxf(
    polygones: List[Polygon],
    chemin_fichier: str,
    position_mm: float = None,
    precision_lissage: Optional[float] = None,
):
    """
    Exporte une section (liste de polygones) dans un fichier DXF.

    Paramètres:
        polygones          : polygones shapely de la section
        chemin_fichier     : chemin .dxf à créer
        position_mm        : position de la coupe (informative)
        precision_lissage  : si non None, applique le lissage en arcs/cercles
    """
    doc = ezdxf.new('R2010')
    doc.units = units.MM

    if position_mm is not None:
        doc.header['$ACADVER'] = 'AC1024'

    msp = doc.modelspace()

    for polygone in polygones:
        _ajouter_polygone_dxf(msp, polygone,
                              layer='CONTOURS', color=7,
                              precision_lissage=precision_lissage)

    doc.saveas(chemin_fichier)


# =============================================================================
# Export du nesting complet
# =============================================================================

def exporter_nesting_dxf(
    placements: List[PlacementType],
    largeur_plaque: float,
    hauteur_plaque: float,
    chemin_fichier: str,
    inclure_cadre: bool = False,
    precision_lissage: Optional[float] = None,
):
    """
    Exporte le nesting complet dans un seul fichier DXF.

    Structure du fichier :
      - Layer 'PLAQUE'      : rectangle de la plaque (optionnel)
      - Layer 'SECTION_XXX' : chaque contour sectionné (couleur bleue)

    Paramètres:
        placements         : résultat de nesting.calculer_nesting()
        largeur_plaque     : dimension X de la plaque (mm)
        hauteur_plaque     : dimension Y de la plaque (mm)
        chemin_fichier     : chemin du fichier .dxf de sortie
        inclure_cadre      : True = ajouter le rectangle de la plaque
        precision_lissage  : si non None, applique le lissage en arcs/cercles
    """
    doc = ezdxf.new('R2010')
    doc.units = units.MM
    msp = doc.modelspace()

    # --- Contour de la plaque (optionnel) ---
    if inclure_cadre:
        msp.add_lwpolyline(
            [(0, 0), (largeur_plaque, 0),
             (largeur_plaque, hauteur_plaque), (0, hauteur_plaque)],
            close=True,
            dxfattribs={'layer': 'PLAQUE', 'color': 1}
        )

    # --- Contours des sections (un layer par section) ---
    for poly_place, _ox, _oy, idx_original in placements:
        layer_name = f'SECTION_{idx_original + 1:03d}'
        _ajouter_polygone_dxf(msp, poly_place,
                              layer=layer_name, color=5,
                              precision_lissage=precision_lissage)

    doc.saveas(chemin_fichier)


# =============================================================================
# Conversion shapely → entités DXF
# =============================================================================

def _ajouter_polygone_dxf(msp, polygone: Polygon,
                           layer: str = '0', color: int = 7,
                           precision_lissage: Optional[float] = None):
    """
    Convertit un polygone shapely en entités DXF.

    Sans lissage (precision_lissage=None) :
        - Chaque anneau → une LWPOLYLINE fermée (comportement historique).

    Avec lissage (precision_lissage > 0) :
        - Chaque anneau est analysé par core/lissage.lisser_polygone
        - Les entités retournées (line/arc/circle) sont ajoutées individuellement.
        - Les segments rectilignes consécutifs sont groupés en LWPOLYLINE
          pour conserver un fichier compact.
    """
    if precision_lissage is not None and precision_lissage > 0:
        _ajouter_polygone_lisse(msp, polygone, layer, color, precision_lissage)
    else:
        _ajouter_polygone_brut(msp, polygone, layer, color)


def _ajouter_polygone_brut(msp, polygone: Polygon, layer: str, color: int):
    """Export classique : chaque anneau → LWPOLYLINE fermée."""
    coords_ext = list(polygone.exterior.coords)
    if len(coords_ext) >= 2:
        points = [(float(x), float(y)) for x, y in coords_ext[:-1]]
        msp.add_lwpolyline(
            points,
            close=True,
            dxfattribs={'layer': layer, 'color': color}
        )

    for interior in polygone.interiors:
        coords_int = list(interior.coords)
        if len(coords_int) >= 2:
            points_int = [(float(x), float(y)) for x, y in coords_int[:-1]]
            msp.add_lwpolyline(
                points_int,
                close=True,
                dxfattribs={'layer': layer, 'color': color}
            )


def _ajouter_polygone_lisse(msp, polygone: Polygon, layer: str, color: int,
                             precision: float):
    """
    Export optimisé : applique le lissage et émet des entités LINE/ARC/CIRCLE.

    Trois cas selon le contenu de chaque anneau :
      1. Un seul cercle           → 1 entité CIRCLE.
      2. Que des segments droits  → 1 LWPOLYLINE fermée (close=True).
      3. Mélange lignes + arcs    → entités individuelles, les lignes
                                    consécutives étant regroupées en
                                    LWPOLYLINE ouvertes pour compacité.
    """
    anneaux_entites = lisser_polygone(polygone, precision)
    attrs = {'layer': layer, 'color': color}

    for entites in anneaux_entites:
        if not entites:
            continue

        # --- Cas 1 : cercle unique ---
        if len(entites) == 1 and entites[0][0] == 'circle':
            _typ, (cx, cy), r = entites[0]
            msp.add_circle((cx, cy), r, dxfattribs=attrs)
            continue

        # --- Cas 2 : aucune courbe → polyligne fermée ---
        if all(e[0] == 'line' for e in entites):
            pts = [entites[0][1]]
            for e in entites:
                pts.append(e[2])
            # Le dernier point reboucle sur le premier ; on le retire pour
            # laisser close=True gérer la fermeture proprement.
            if pts and pts[0] == pts[-1]:
                pts = pts[:-1]
            if len(pts) >= 2:
                msp.add_lwpolyline(pts, close=True, dxfattribs=attrs)
            continue

        # --- Cas 3 : mélange → émission mixte ---
        buffer_points: List[Tuple[float, float]] = []

        def _flush_polyline():
            """Vide le buffer de lignes accumulées en LWPOLYLINE ouverte."""
            if len(buffer_points) >= 2:
                msp.add_lwpolyline(list(buffer_points),
                                   close=False, dxfattribs=attrs)
            buffer_points.clear()

        for ent in entites:
            typ = ent[0]

            if typ == 'line':
                _, p0, p1 = ent
                if not buffer_points:
                    buffer_points.append(p0)
                buffer_points.append(p1)

            elif typ == 'arc':
                _flush_polyline()
                _, (cx, cy), r, p_start, p_end, p_mid = ent
                # p_mid : point source réel ~milieu de l'arc → permet de
                # déterminer le sens (CCW/CW) pour un ARC DXF correctement orienté.
                start_deg, end_deg = _angles_dxf(p_start, p_end, p_mid, cx, cy)
                msp.add_arc(
                    center=(cx, cy),
                    radius=r,
                    start_angle=start_deg,
                    end_angle=end_deg,
                    dxfattribs=attrs,
                )

            elif typ == 'circle':
                # Cercle au sein d'une décomposition (cas rare) : flush d'abord
                _flush_polyline()
                _, (cx, cy), r = ent
                msp.add_circle((cx, cy), r, dxfattribs=attrs)

        # Fin de l'anneau : émettre le dernier tronçon ouvert s'il existe.
        _flush_polyline()



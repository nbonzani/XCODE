# =============================================================================
# core/exporter.py — Export DXF des sections et du nesting
#
# Format DXF R2010 (compatible AutoCAD, FreeCAD, LaserCAD, etc.)
# Unités : millimètres
# Chaque contour shapely est converti en LWPOLYLINE DXF fermée.
# =============================================================================

import os
import ezdxf
from ezdxf import units
from shapely.geometry import Polygon
from typing import List, Tuple


# Type d'un placement issu de nesting.py
PlacementType = Tuple[Polygon, float, float, int]


def exporter_toutes_sections(
    sections: List[Tuple[float, List[Polygon]]],
    dossier_sortie: str,
    prefixe: str = 'section'
) -> List[str]:
    """
    Exporte chaque section dans un fichier DXF individuel.

    Nommage automatique : <prefixe>_001.dxf, <prefixe>_002.dxf, ...
    Si prefixe est fourni (ex. nom du fichier STL sans extension),
    les fichiers seront nommés pied_001.dxf, pied_002.dxf, etc.

    Paramètres:
        sections (list)      : liste de (position_mm, [polygones])
                               telle que retournée par slicer.calculer_sections()
        dossier_sortie (str) : chemin du dossier où créer les fichiers
        prefixe (str)        : préfixe des fichiers (défaut : 'section')

    Retourne:
        Liste des chemins absolus des fichiers créés.
    """
    os.makedirs(dossier_sortie, exist_ok=True)
    fichiers_crees = []

    # Nettoyer le préfixe : supprimer les caractères invalides pour un nom de fichier
    prefixe_propre = _nettoyer_nom_fichier(prefixe) if prefixe else 'section'

    for i, (position, polygones) in enumerate(sections):
        nom_fichier = f"{prefixe_propre}_{i + 1:03d}.dxf"
        chemin = os.path.join(dossier_sortie, nom_fichier)
        exporter_section_dxf(polygones, chemin, position_mm=position)
        fichiers_crees.append(chemin)

    return fichiers_crees


def _nettoyer_nom_fichier(nom: str) -> str:
    """Supprime les caractères interdits dans un nom de fichier Windows."""
    import re
    return re.sub(r'[\\/:*?"<>|]', '_', nom).strip()


def exporter_section_dxf(
    polygones: List[Polygon],
    chemin_fichier: str,
    position_mm: float = None
):
    """
    Exporte une liste de polygones (une seule section) dans un fichier DXF.

    Paramètres:
        polygones (list)      : polygones shapely de la section
        chemin_fichier (str)  : chemin complet du fichier .dxf à créer
        position_mm (float)   : position de la coupe (utilisée dans le commentaire)
    """
    doc = ezdxf.new('R2010')
    doc.units = units.MM

    # Métadonnées dans l'en-tête DXF
    if position_mm is not None:
        doc.header['$ACADVER'] = 'AC1024'  # R2010

    msp = doc.modelspace()

    # Ajouter chaque polygone (contour extérieur + trous)
    for polygone in polygones:
        _ajouter_polygone_dxf(msp, polygone, layer='CONTOURS', color=7)

    doc.saveas(chemin_fichier)


def exporter_nesting_dxf(
    placements: List[PlacementType],
    largeur_plaque: float,
    hauteur_plaque: float,
    chemin_fichier: str,
    inclure_cadre: bool = False
):
    """
    Exporte le nesting complet dans un seul fichier DXF.

    Structure du fichier :
      - Layer 'PLAQUE'      : rectangle de la plaque (optionnel, désactivé par défaut)
      - Layer 'SECTION_XXX' : chaque contour sectionné (couleur bleue)

    Paramètres:
        placements (list)    : résultat de nesting.calculer_nesting()
        largeur_plaque (float)
        hauteur_plaque (float)
        chemin_fichier (str) : chemin du fichier .dxf de sortie
        inclure_cadre (bool) : True = ajouter le rectangle de la plaque dans le DXF
                               False (défaut) = contours seuls, sans cadre
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
        # Nommage du layer : SECTION_001, SECTION_002, ...
        layer_name = f'SECTION_{idx_original + 1:03d}'
        _ajouter_polygone_dxf(msp, poly_place, layer=layer_name, color=5)

    doc.saveas(chemin_fichier)


def _ajouter_polygone_dxf(msp, polygone: Polygon, layer: str = '0', color: int = 7):
    """
    Convertit un polygone shapely en entités DXF LWPOLYLINE.

    Ajoute :
      - Le contour extérieur (exterior ring)
      - Les éventuels trous intérieurs (interior rings) — pour les formes creuses

    Paramètres:
        msp    : ModelSpace ezdxf
        polygone (Polygon) : polygone shapely à convertir
        layer (str)        : nom du layer DXF
        color (int)        : index couleur ACI (1=rouge, 2=jaune, 5=bleu, 7=blanc)
    """
    # --- Contour extérieur ---
    coords_ext = list(polygone.exterior.coords)
    if len(coords_ext) >= 2:
        # On passe les coordonnées sans le point de fermeture doublon
        # (shapely ferme les rings en répétant le premier point)
        points = [(float(x), float(y)) for x, y in coords_ext[:-1]]
        msp.add_lwpolyline(
            points,
            close=True,
            dxfattribs={'layer': layer, 'color': color}
        )

    # --- Trous intérieurs (géométries avec cavités) ---
    for interior in polygone.interiors:
        coords_int = list(interior.coords)
        if len(coords_int) >= 2:
            points_int = [(float(x), float(y)) for x, y in coords_int[:-1]]
            msp.add_lwpolyline(
                points_int,
                close=True,
                dxfattribs={'layer': layer, 'color': color}
            )

# =============================================================================
# core/stl_loader.py — Chargement et parsing de fichiers STL
# Charge le fichier STL en parallèle avec trimesh (pour le sectionnement)
# et PyVista (pour la visualisation 3D).
# =============================================================================

import trimesh
import pyvista as pv
import numpy as np


def charger_stl(chemin_fichier: str):
    """
    Charge un fichier STL (ASCII ou binaire).

    Paramètres:
        chemin_fichier (str) : chemin absolu vers le fichier .stl

    Retourne:
        tuple (trimesh.Trimesh, pyvista.PolyData) — les deux représentations
        du même modèle, utilisées respectivement pour le sectionnement et
        la visualisation 3D.

    Lève:
        RuntimeError si le fichier est introuvable ou corrompu.
    """
    try:
        # --- Chargement avec trimesh ---
        # trimesh gère les fichiers STL ASCII et binaire.
        # force='mesh' assure qu'on obtient un seul maillage unifié,
        # même si le fichier contient plusieurs objets.
        mesh_tri = trimesh.load(chemin_fichier, force='mesh')

        if not isinstance(mesh_tri, trimesh.Trimesh):
            raise ValueError("Le fichier ne contient pas un maillage triangulaire valide.")

        if len(mesh_tri.faces) == 0:
            raise ValueError("Le maillage est vide (aucune face détectée).")

        # --- Chargement avec PyVista ---
        # PyVista lit directement les STL via VTK, format natif pour la 3D.
        mesh_pv = pv.read(chemin_fichier)

        return mesh_tri, mesh_pv

    except FileNotFoundError:
        raise RuntimeError(f"Fichier introuvable : {chemin_fichier}")
    except Exception as e:
        raise RuntimeError(f"Erreur lors du chargement du fichier STL : {e}")


def obtenir_dimensions(mesh_trimesh: trimesh.Trimesh) -> dict:
    """
    Calcule et retourne les dimensions géométriques du modèle.

    Paramètres:
        mesh_trimesh (trimesh.Trimesh) : le maillage chargé

    Retourne:
        dict avec les clés :
          - 'dimensions' : tableau numpy [lx, ly, lz] en mm
          - 'centre'     : tableau numpy [cx, cy, cz] centre de la boîte englobante
          - 'bornes'     : tableau numpy [[xmin,ymin,zmin],[xmax,ymax,zmax]]
          - 'nb_faces'   : nombre de triangles
          - 'volume'     : volume en mm³ (si le maillage est fermé)
    """
    # Boîte englobante axis-aligned
    bornes = mesh_trimesh.bounds            # shape (2, 3)
    dimensions = bornes[1] - bornes[0]     # [lx, ly, lz]
    centre = (bornes[0] + bornes[1]) / 2.0

    # Volume (uniquement si le maillage est un solide fermé et watertight)
    volume = mesh_trimesh.volume if mesh_trimesh.is_watertight else None

    return {
        'dimensions': dimensions,
        'centre': centre,
        'bornes': bornes,
        'nb_faces': len(mesh_trimesh.faces),
        'volume': volume
    }

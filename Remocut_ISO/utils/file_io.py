"""
utils/file_io.py — Entrées/sorties fichiers pour Remocut ISO Generator.

Fonctions :
  - charger_dxf()       : Wrapper autour de dxf_reader.lire_dxf()
  - sauvegarder_gcode() : Écriture du GCode en ASCII/LF (format ECP1000)
  - generer_nom_fichier(): Génération automatique du nom de fichier de sortie
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Répertoire de sortie par défaut (relatif à la racine du projet)
DOSSIER_SORTIE_DEFAUT = "output"

# Extension obligatoire pour l'ECP1000 (confirmé par les programmes réels)
EXTENSION_GCODE = ".iso"


def charger_dxf(
    chemin: str,
    tolerance_fermeture: float = 0.01,
) -> List[List[Tuple[float, float]]]:
    """
    Charge un fichier DXF et retourne la liste des contours.

    Wrapper autour de core.dxf_reader.lire_dxf() avec gestion des erreurs
    orientée interface utilisateur.

    Args:
        chemin              : Chemin absolu ou relatif vers le fichier .dxf
        tolerance_fermeture : Tolérance de fermeture des contours en mm.

    Returns:
        Liste de contours (listes de tuples (x, y) en mm).

    Raises:
        FileNotFoundError : Si le fichier n'existe pas.
        ValueError        : Si le fichier est vide ou ne contient pas de contours.
        IOError           : Si le fichier est illisible.
    """
    chemin_abs = str(Path(chemin).resolve())

    if not os.path.isfile(chemin_abs):
        raise FileNotFoundError(
            f"Fichier DXF introuvable : '{chemin_abs}'"
        )

    if not chemin_abs.lower().endswith('.dxf'):
        logger.warning(
            f"Le fichier '{chemin_abs}' n'a pas l'extension .dxf. "
            f"Tentative de lecture quand même."
        )

    from core.dxf_reader import lire_dxf

    # Essais progressifs de tolérance de fermeture.
    # Certains logiciels CAO génèrent des DXF avec de petits gaps aux jonctions.
    tolerances_a_tester = [tolerance_fermeture]
    for multiplicateur in (10, 100, 500):
        t = tolerance_fermeture * multiplicateur
        if t not in tolerances_a_tester:
            tolerances_a_tester.append(t)

    derniere_erreur = None
    for tol in tolerances_a_tester:
        try:
            contours = lire_dxf(chemin_abs, tol)
            if tol > tolerance_fermeture:
                logger.warning(
                    f"DXF '{os.path.basename(chemin_abs)}' : "
                    f"tolérance élargie à {tol:.3f} mm pour fermer les contours."
                )
            logger.info(
                f"Fichier DXF chargé : '{os.path.basename(chemin_abs)}' "
                f"→ {len(contours)} contour(s) (tol={tol:.3f} mm)"
            )
            return contours
        except ValueError as e:
            derniere_erreur = e
            continue

    # Aucune tolérance n'a fonctionné
    raise ValueError(str(derniere_erreur))


def sauvegarder_gcode(
    contenu_gcode: str,
    chemin_sortie: str,
) -> str:
    """
    Sauvegarde le contenu GCode dans un fichier .iso.

    Le fichier est écrit en encodage ASCII avec des délimiteurs LF (format Unix),
    comme requis par le contrôleur ECP1000 (confirmé par bilan_gcode_remocut.md).

    Args:
        contenu_gcode : Texte GCode complet (produit par gcode_generator.generer()).
        chemin_sortie : Chemin du fichier de destination (avec ou sans extension).

    Returns:
        Chemin absolu du fichier créé.

    Raises:
        IOError     : Si l'écriture échoue.
        ValueError  : Si le contenu est vide.
    """
    if not contenu_gcode or not contenu_gcode.strip():
        raise ValueError("Le contenu GCode est vide, aucun fichier créé.")

    # Assurer l'extension .iso
    chemin = Path(chemin_sortie)
    if chemin.suffix.lower() != EXTENSION_GCODE:
        chemin = chemin.with_suffix(EXTENSION_GCODE)

    # Créer le dossier parent si nécessaire
    chemin.parent.mkdir(parents=True, exist_ok=True)

    # Normaliser les fins de ligne → LF uniquement (Unix, requis ECP1000)
    contenu_normalise = contenu_gcode.replace('\r\n', '\n').replace('\r', '\n')

    try:
        # Encodage ASCII (seuls les caractères ASCII sont présents dans les programmes)
        # Fallback UTF-8 si des accents sont présents (noms de matériaux)
        try:
            octets = contenu_normalise.encode('ascii')
        except UnicodeEncodeError:
            logger.warning(
                "Caractères non-ASCII dans le GCode, utilisation de l'encodage UTF-8."
            )
            octets = contenu_normalise.encode('utf-8')

        with open(str(chemin), 'wb') as f:
            f.write(octets)

    except OSError as e:
        raise IOError(
            f"Impossible d'écrire le fichier GCode '{chemin}' : {e}"
        )

    chemin_abs = str(chemin.resolve())
    taille = os.path.getsize(chemin_abs)
    logger.info(
        f"GCode sauvegardé : '{chemin_abs}' ({taille} octets)"
    )
    return chemin_abs


def generer_nom_fichier(
    chemin_dxf: Optional[str] = None,
    nom_programme: Optional[str] = None,
    dossier_sortie: Optional[str] = None,
) -> str:
    """
    Génère un nom de fichier GCode automatique.

    Schéma : {nom_base}_{YYYYMMDD}_{HHMM}.iso

    Args:
        chemin_dxf    : Chemin du fichier DXF source (pour extraire le nom de base).
        nom_programme : Nom de programme explicite (prioritaire sur chemin_dxf).
        dossier_sortie: Dossier de sortie. Par défaut : output/ relatif au script.

    Returns:
        Chemin complet du fichier de sortie (sans créer le fichier).
    """
    # Déterminer le dossier de sortie
    if dossier_sortie is None:
        # Chercher le dossier output/ relatif à ce fichier
        racine = Path(__file__).parent.parent
        dossier = racine / DOSSIER_SORTIE_DEFAUT
    else:
        dossier = Path(dossier_sortie)

    # Déterminer le nom de base
    if nom_programme:
        nom_base = nom_programme.replace(' ', '_')
    elif chemin_dxf:
        nom_base = Path(chemin_dxf).stem
    else:
        nom_base = "programme"

    # Horodatage
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')

    nom_fichier = f"{nom_base}_{timestamp}{EXTENSION_GCODE}"
    return str(dossier / nom_fichier)

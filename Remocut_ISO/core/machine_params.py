"""
core/machine_params.py — Base de données des paramètres par matériau et épaisseur.

Les noms de matériaux dans 'nom_materiau_machine' correspondent aux entrées exactes
de la base SQLite du contrôleur Eurosoft ECP1000 (source : bilan_gcode_remocut.md).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ParamsDecoupe:
    """
    Paramètres de découpe pour un matériau et une épaisseur donnés.
    Ces paramètres alimentent directement le générateur GCode.
    """
    materiau: str                    # Nom affiché (ex: 'Acier')
    epaisseur: float                 # Épaisseur en mm
    nom_materiau_machine: str        # Chaîne exacte pour $material dans le GCode ECP1000
    vitesse_coupe: float             # Vitesse de coupe nominale en mm/min (informatif)
    kerf: float                      # Largeur de trait plasma en mm
    delai_piercing: float            # Délai de perçage en ms (pour information)
    longueur_lead_in: float          # Longueur du lead-in en mm
    type_lead_in: str                # 'lineaire' ou 'arc'
    longueur_lead_out: float         # Longueur du lead-out en mm
    cote_compensation: str           # 'gauche' (G41) ou 'droite' (G42) — non utilisé en V1
    largeur_tole: float              # Largeur de la tôle en mm
    hauteur_tole: float              # Hauteur de la tôle en mm
    marge_nesting: float             # Marge entre pièces et bords en mm


# ---------------------------------------------------------------------------
# Base de données des paramètres par matériau et épaisseur
# Clé : (materiau_lower, epaisseur_mm)
#
# CHOIX : Les vitesses de coupe et paramètres kerf sont des valeurs estimées
# cohérentes avec les données extraites dans bilan_gcode_remocut.md.
# La vitesse réelle est lue par la machine depuis la base $material.
# Les noms 'nom_materiau_machine' sont les clés exactes de la base ECP1000.
# ---------------------------------------------------------------------------

_BASE_MATERIAUX: Dict[Tuple[str, float], Dict] = {
    # --- Acier — Fine Cut 30 A ---
    ('acier', 0.5): {
        'nom_materiau_machine': 'Acier-30A Fine Cut-Vitesse lente-0.5mm',
        'vitesse_coupe': 3800,
        'kerf': 0.8,
        'delai_piercing': 0,
    },
    ('acier', 0.6): {
        'nom_materiau_machine': 'Acier-30A Fine Cut-Vitesse lente-0.6mm',
        'vitesse_coupe': 3800,
        'kerf': 0.8,
        'delai_piercing': 0,
    },
    ('acier', 0.8): {
        'nom_materiau_machine': 'Acier-30A Fine Cut-Vitesse lente-0.8mm',
        'vitesse_coupe': 3800,
        'kerf': 0.9,
        'delai_piercing': 100,
    },
    ('acier', 1.0): {
        'nom_materiau_machine': 'Acier-30A Fine Cut-Vitesse lente-1mm',
        'vitesse_coupe': 3200,
        'kerf': 1.0,
        'delai_piercing': 200,
    },
    # --- Acier — Fine Cut 45 A ---
    ('acier', 1.5): {
        'nom_materiau_machine': 'Acier-45A FineCut-Vitesse Rapide-1.5mm',
        'vitesse_coupe': 6400,
        'kerf': 1.2,
        'delai_piercing': 400,
    },
    ('acier', 2.0): {
        'nom_materiau_machine': 'Acier-45A Fine Cut- Vitesse lente-2mm',
        'vitesse_coupe': 5000,
        'kerf': 1.3,
        'delai_piercing': 400,
    },
    ('acier', 3.0): {
        'nom_materiau_machine': 'Acier-45A Fine Cut- Vitesse lente-3mm',
        'vitesse_coupe': 2500,
        'kerf': 1.5,
        'delai_piercing': 500,
    },
    # --- Acier — 65 A ---
    ('acier', 4.0): {
        'nom_materiau_machine': 'Acier-65A-4mm',
        'vitesse_coupe': 2200,
        'kerf': 1.8,
        'delai_piercing': 600,
    },
    ('acier', 5.0): {
        'nom_materiau_machine': 'Acier-65A-5mm',
        'vitesse_coupe': 1800,
        'kerf': 1.9,
        'delai_piercing': 700,
    },
    # --- Acier — 85 A ---
    ('acier', 6.0): {
        'nom_materiau_machine': 'Acier-85A-6mm',
        'vitesse_coupe': 1500,
        'kerf': 2.0,
        'delai_piercing': 700,
    },
    ('acier', 8.0): {
        'nom_materiau_machine': 'Acier-85A-8mm',
        'vitesse_coupe': 1200,
        'kerf': 2.2,
        'delai_piercing': 800,
    },
    ('acier', 10.0): {
        'nom_materiau_machine': 'Acier-85A-10mm',
        'vitesse_coupe': 1680,
        'kerf': 2.5,
        'delai_piercing': 500,
    },
    ('acier', 12.0): {
        'nom_materiau_machine': 'Acier-85A-12mm',
        'vitesse_coupe': 1280,
        'kerf': 2.7,
        'delai_piercing': 700,
    },
    ('acier', 15.0): {
        'nom_materiau_machine': 'Acier-85A-15mm',
        'vitesse_coupe': 870,
        'kerf': 3.0,
        'delai_piercing': 1000,
    },
    ('acier', 20.0): {
        'nom_materiau_machine': 'Acier-85A-20mm',
        'vitesse_coupe': 600,
        'kerf': 3.5,
        'delai_piercing': 1500,
    },
    # --- Inox — Fine Cut 30 A ---
    ('inox', 0.5): {
        'nom_materiau_machine': 'Inox-30A FineCut-Vitesse lente-0.5mm',
        'vitesse_coupe': 2500,
        'kerf': 0.8,
        'delai_piercing': 0,
    },
    # --- Inox — Fine Cut 40 A ---
    ('inox', 1.0): {
        'nom_materiau_machine': 'Inox-40A FineCut-Vitesse lente-1mm',
        'vitesse_coupe': 2000,
        'kerf': 1.0,
        'delai_piercing': 200,
    },
    ('inox', 1.5): {
        'nom_materiau_machine': 'Inox-40A FineCut-Vitesse lente-1.5mm',
        'vitesse_coupe': 1500,
        'kerf': 1.2,
        'delai_piercing': 300,
    },
    # --- Inox — Fine Cut 45 A ---
    ('inox', 2.0): {
        'nom_materiau_machine': 'Inox-45A FineCut-Vitesse lente-2mm',
        'vitesse_coupe': 1200,
        'kerf': 1.3,
        'delai_piercing': 400,
    },
    ('inox', 3.0): {
        'nom_materiau_machine': 'Inox-45A FineCut-Vitesse lente-3mm',
        'vitesse_coupe': 900,
        'kerf': 1.5,
        'delai_piercing': 500,
    },
    # --- Inox — 65 A ---
    ('inox', 4.0): {
        'nom_materiau_machine': 'Inox-65A-4mm',
        'vitesse_coupe': 750,
        'kerf': 1.8,
        'delai_piercing': 600,
    },
    ('inox', 5.0): {
        'nom_materiau_machine': 'Inox-65A-5mm',
        'vitesse_coupe': 650,
        'kerf': 1.9,
        'delai_piercing': 700,
    },
    # --- Inox — 85 A ---
    ('inox', 6.0): {
        'nom_materiau_machine': 'Inox-85A-6mm',
        'vitesse_coupe': 600,
        'kerf': 2.0,
        'delai_piercing': 700,
    },
    ('inox', 8.0): {
        'nom_materiau_machine': 'Inox-85A-8mm',
        'vitesse_coupe': 480,
        'kerf': 2.2,
        'delai_piercing': 900,
    },
    ('inox', 10.0): {
        'nom_materiau_machine': 'Inox-85A-10mm',
        'vitesse_coupe': 380,
        'kerf': 2.5,
        'delai_piercing': 1200,
    },
    ('inox', 12.0): {
        'nom_materiau_machine': 'Inox-85A-12mm',
        'vitesse_coupe': 300,
        'kerf': 2.8,
        'delai_piercing': 1500,
    },
    # --- Aluminium — Fine Cut 45 A ---
    ('aluminium', 1.0): {
        'nom_materiau_machine': 'Alu-45A FineCut-Vitesse Rapide-1mm',
        'vitesse_coupe': 4000,
        'kerf': 1.0,
        'delai_piercing': 100,
    },
    ('aluminium', 2.0): {
        'nom_materiau_machine': 'Alu-45A FineCut-Vitesse Rapide-2mm',
        'vitesse_coupe': 3200,
        'kerf': 1.2,
        'delai_piercing': 200,
    },
    # --- Aluminium — 65 A ---
    ('aluminium', 3.0): {
        'nom_materiau_machine': 'Alu-65A-3mm',
        'vitesse_coupe': 2500,
        'kerf': 1.5,
        'delai_piercing': 300,
    },
    ('aluminium', 4.0): {
        'nom_materiau_machine': 'Alu-65A-4mm',
        'vitesse_coupe': 2000,
        'kerf': 1.7,
        'delai_piercing': 400,
    },
    ('aluminium', 5.0): {
        'nom_materiau_machine': 'Alu-65A-5mm',
        'vitesse_coupe': 1700,
        'kerf': 1.9,
        'delai_piercing': 500,
    },
    # --- Aluminium — 85 A ---
    ('aluminium', 6.0): {
        'nom_materiau_machine': 'Alu-85A-6mm',
        'vitesse_coupe': 1500,
        'kerf': 2.0,
        'delai_piercing': 500,
    },
    ('aluminium', 8.0): {
        'nom_materiau_machine': 'Alu-85A-8mm',
        'vitesse_coupe': 1200,
        'kerf': 2.2,
        'delai_piercing': 600,
    },
    ('aluminium', 10.0): {
        'nom_materiau_machine': 'Alu-85A-10mm',
        'vitesse_coupe': 900,
        'kerf': 2.5,
        'delai_piercing': 700,
    },
    ('aluminium', 12.0): {
        'nom_materiau_machine': 'Alu-85A-12mm',
        'vitesse_coupe': 700,
        'kerf': 2.8,
        'delai_piercing': 900,
    },
}

# Paramètres géométriques communs (indépendants du matériau en V1)
_PARAMS_COMMUNS: Dict = {
    'longueur_lead_in': 5.0,
    'type_lead_in': 'lineaire',
    'longueur_lead_out': 5.0,
    'cote_compensation': 'gauche',
    'largeur_tole': 3000.0,
    'hauteur_tole': 1500.0,
    'marge_nesting': 10.0,
}

# Alias de noms de matériaux (insensible à la casse)
_ALIASES_MATERIAUX: Dict[str, str] = {
    'acier': 'acier',
    'steel': 'acier',
    'inox': 'inox',
    'stainless': 'inox',
    'inoxydable': 'inox',
    'aluminium': 'aluminium',
    'aluminum': 'aluminium',
    'alu': 'aluminium',
}


def get_defaults(materiau: str, epaisseur: float) -> dict:
    """
    Retourne les paramètres de découpe par défaut pour un matériau et une épaisseur.

    Stratégie de recherche :
      1. Correspondance exacte (matériau + épaisseur)
      2. Épaisseur la plus proche pour ce matériau
      3. Valeurs par défaut acier 3 mm si matériau inconnu

    Args:
        materiau: Nom du matériau (ex : 'Acier', 'Inox', 'Aluminium')
        epaisseur: Épaisseur en mm (ex : 3.0)

    Returns:
        dict avec les clés : materiau, epaisseur, nom_materiau_machine,
        vitesse_coupe, kerf, delai_piercing, longueur_lead_in, type_lead_in,
        longueur_lead_out, cote_compensation, largeur_tole, hauteur_tole,
        marge_nesting.
    """
    mat_lower = _ALIASES_MATERIAUX.get(materiau.lower().strip(), 'acier')

    # Recherche exacte
    cle = (mat_lower, float(epaisseur))
    params_mat = _BASE_MATERIAUX.get(cle)

    if params_mat is None:
        # Recherche par épaisseur la plus proche pour ce matériau
        epaisseurs_dispo = [k[1] for k in _BASE_MATERIAUX if k[0] == mat_lower]
        if epaisseurs_dispo:
            epaisseur_proche = min(epaisseurs_dispo, key=lambda e: abs(e - epaisseur))
            params_mat = _BASE_MATERIAUX[(mat_lower, epaisseur_proche)]
        else:
            # Matériau inconnu → valeurs par défaut acier 3 mm
            params_mat = _BASE_MATERIAUX[('acier', 3.0)]

    return {
        'materiau': materiau,
        'epaisseur': epaisseur,
        **_PARAMS_COMMUNS,
        **params_mat,
    }


def liste_materiaux() -> List[str]:
    """Retourne la liste des matériaux disponibles pour l'interface."""
    return ['Acier', 'Inox', 'Aluminium']


def liste_epaisseurs(materiau: str) -> List[float]:
    """
    Retourne les épaisseurs disponibles pour un matériau donné, triées.

    Args:
        materiau: Nom du matériau (ex : 'Acier')

    Returns:
        Liste triée d'épaisseurs en mm.
    """
    mat_lower = _ALIASES_MATERIAUX.get(materiau.lower().strip(), 'acier')
    epaisseurs = sorted(k[1] for k in _BASE_MATERIAUX if k[0] == mat_lower)
    return epaisseurs


def nom_materiau_machine(materiau: str, epaisseur: float) -> str:
    """
    Retourne la chaîne exacte du nom de matériau pour le GCode ECP1000.

    Args:
        materiau: Nom du matériau
        epaisseur: Épaisseur en mm

    Returns:
        Chaîne pour la ligne $material = "..." du GCode.
    """
    return get_defaults(materiau, epaisseur)['nom_materiau_machine']

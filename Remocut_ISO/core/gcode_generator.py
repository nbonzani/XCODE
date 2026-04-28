"""
core/gcode_generator.py — Générateur GCode ISO conforme au contrôleur Eurosoft ECP1000.

FORMAT EXACT BASÉ SUR L'ANALYSE DE bilan_gcode_remocut.md ET DES FICHIERS doc/*.iso.

Structure du fichier généré (conforme aux exemples réels) :
───────────────────────────────────────────────────────────
  ; ( DrvEcp1000 BY EUROSOFT S.R.L. BUILD : MAR 18 2020 )
  ; ( PROGRAM NAME=NOM )
  ; ( SHEET DIMENSION L x H )
  $material = "Acier-45A Fine Cut- Vitesse lente-3mm"
  G90

  Pour chaque contour :
    G92 I1 T1              ← sélection torche 1
    G00                    ← mode rapide
    F $vrapid              ← vitesse rapide (45 000 mm/min machine)
    G00 X{xs} Y{-ys}       ← déplacement vers point de piquage
    M17.1                  ← descente torche (détection ohmique)
    G01                    ← mode interpolation
    F $plasma.cut_feed[*0.500000]  ← 50% vitesse (lead-in)
    M20.1                  ← allumage arc + perçage
    M23.1                  ← signal début lead-in
    G01 X{x0} Y{-y0}       ← lead-in (approche vers P0)
    G01 X{p1}...           ← contour complet
    G01 X{x0} Y{-y0}       ← fermeture contour
    M19.1                  ← signal début lead-out
    G01 X{xo} Y{-yo}       ← lead-out (dépassement)
    M21.1                  ← extinction arc
    M24.1                  ← fin séquence coupe
    M18.1                  ← montée torche
    G92 I0                 ← désélection torche

  G90
  M30
───────────────────────────────────────────────────────────

CHOIX TECHNIQUES :
  - Pas de G41/G42 : les vrais programmes ECP1000 n'utilisent PAS G41/G42.
    La compensation kerf est gérée par le contrôleur via $material.
  - Pas de G21 (mm) en en-tête : absent des programmes réels.
  - Coordonnées en 6 décimales, point décimal, format Unix (LF uniquement).
  - Y est négativé : y_gcode = -y_interne (axe Y machine va vers le bas).
  - Utilisation du pattern M23.1/M24.1 pour tous les contours (lead-in linéaire
    à 50% de vitesse) — séquence minimale valide selon section 5.2 du bilan.
  - Extension de sortie : .iso (confirmé par les exemples réels).
"""

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from core.geometry import (
    bounding_box,
    calculer_lead_in,
    calculer_lead_out,
    lead_in_polyline,
    lead_out_polyline,
)
from core.nesting import ContourPlace

logger = logging.getLogger(__name__)


class GenerateurGCode:
    """
    Générateur de programmes GCode ISO pour le contrôleur Eurosoft ECP1000.

    Usage typique :
        gen = GenerateurGCode()
        gcode = gen.generer(contours_places, params, nom_programme="piece_1")
    """

    # En-tête driver ECP1000 (ligne obligatoire pour la reconnaissance par l'IHM)
    ENTETE_DRIVER = "; ( DrvEcp1000 BY EUROSOFT S.R.L. BUILD : MAR 18 2020 )"

    def __init__(self) -> None:
        self._lignes: List[str] = []

    # -----------------------------------------------------------------------
    # Interface publique
    # -----------------------------------------------------------------------

    def generer(
        self,
        contours_places: List[ContourPlace],
        params: dict,
        nom_programme: str = "PROGRAMME",
        mode_simulation: bool = False,
    ) -> str:
        """
        Génère le texte complet d'un programme GCode ECP1000.

        Args:
            contours_places : Contours ordonnés issus de trajectory.ordonner_decoupes().
            params          : Dict de paramètres issu de machine_params.get_defaults().
                              Clés utilisées : nom_materiau_machine, longueur_lead_in,
                              longueur_lead_out, largeur_tole, hauteur_tole.
            nom_programme   : Nom du programme (affiché dans l'IHM ECP1000).
            mode_simulation : Si True, remplace M17/M20/M21/M18 par des commentaires.

        Returns:
            Texte GCode complet (encodage ASCII, délimiteurs LF).
        """
        self._lignes = []

        # Extraction des paramètres
        mat_machine = params.get('nom_materiau_machine', 'Default')
        largeur_tole = float(params.get('largeur_tole', 3000.0))
        hauteur_tole = float(params.get('hauteur_tole', 1500.0))
        longueur_lead_in = float(params.get('longueur_lead_in', 5.0))
        longueur_lead_out = float(params.get('longueur_lead_out', 5.0))
        type_lead = str(params.get('type_lead_in', 'lineaire'))

        # Nom propre (sans espaces pour compatibilité IHM)
        nom_propre = nom_programme.replace(' ', '_').upper()

        # --- ZONE 1 : EN-TÊTE ---
        self._ecrire_entete(
            nom_propre, mat_machine, largeur_tole, hauteur_tole, mode_simulation
        )

        # --- ZONE 2 : SÉQUENCE DE COUPE ---
        for idx, cp in enumerate(contours_places):
            if len(cp.points) < 2:
                logger.warning(
                    f"Contour {idx} ignoré : trop peu de points ({len(cp.points)})."
                )
                continue

            try:
                self._ecrire_contour(
                    contour=cp.points,
                    longueur_lead_in=longueur_lead_in,
                    longueur_lead_out=longueur_lead_out,
                    mode_simulation=mode_simulation,
                    type_lead=type_lead,
                    est_interieur=cp.est_interieur,
                    commentaire=f"Piece {cp.id_piece + 1} - "
                                f"{'trou' if cp.est_interieur else 'exterieur'}",
                )
            except Exception as e:
                logger.error(f"Erreur génération GCode contour {idx} : {e}")
                raise

        # --- ZONE 3 : FIN DE PROGRAMME ---
        self._ecrire_fin()

        # Assembler avec délimiteurs LF (format Unix requis par ECP1000)
        return '\n'.join(self._lignes) + '\n'

    # -----------------------------------------------------------------------
    # Sections du programme
    # -----------------------------------------------------------------------

    def _ecrire_entete(
        self,
        nom: str,
        materiau: str,
        largeur: float,
        hauteur: float,
        simulation: bool,
    ) -> None:
        """Écrit l'en-tête du programme (zone 1)."""
        if simulation:
            self._l(f"; SIMULATION A BLANC — torche désactivée — {datetime.now():%Y-%m-%d %H:%M}")
        self._l(self.ENTETE_DRIVER)
        self._l(f"; ( PROGRAM NAME={nom} )")
        self._l(
            f"; ( SHEET DIMENSION {self._fmt(largeur)} x {self._fmt(hauteur)} )"
        )
        if simulation:
            self._l(f'; ( $material = "{materiau}" ) ; simulation')
        else:
            self._l(f'$material = "{materiau}"')
        self._l("G90")

    def _ecrire_contour(
        self,
        contour: List[Tuple[float, float]],
        longueur_lead_in: float,
        longueur_lead_out: float,
        mode_simulation: bool,
        type_lead: str = 'lineaire',
        est_interieur: bool = False,
        commentaire: str = "",
    ) -> None:
        """
        Écrit la séquence GCode complète pour un seul contour.

        Séquence (conforme aux fichiers 0.5_01.iso, 10_01.iso, etc.) :
          G92 I1 T1
          G00 / F $vrapid / G00 Xls Yls   ← positionnement au point de piquage
          M17.1                             ← descente torche
          G01 / F 50%
          M20.1                             ← allumage arc
          M23.1                             ← signal lead-in
          G01 au premier point du contour   ← lead-in
          G01 pour chaque point du contour  ← découpe
          G01 fermeture vers P[0]
          M19.1                             ← signal lead-out
          G01 au point de sortie            ← lead-out
          M21.1                             ← extinction arc
          M24.1                             ← fin séquence
          M18.1                             ← montée torche
          G92 I0                            ← désélection torche
        """
        if commentaire:
            self._l(f";--- {commentaire} ---")

        # Polyline complète du lead-in (piquage → p0) et lead-out (p0 → sortie).
        # Pour le type linéaire → 2 points ; pour l'arc → discrétisation fine.
        poly_in = lead_in_polyline(contour, longueur_lead_in, type_lead, est_interieur)
        poly_out = lead_out_polyline(contour, longueur_lead_out, type_lead, est_interieur)
        point_piquage = poly_in[0] if poly_in else contour[0]
        point_sortie = poly_out[-1] if poly_out else contour[0]

        # Sélection torche
        self._l("G92 I1 T1")
        self._l("G00")
        self._l("F $vrapid")

        # Déplacement rapide vers le point de piquage
        # Y negated : y_gcode = -y_interne
        self._l(
            f"G00 X{self._coord(point_piquage[0])} Y{self._coord(-point_piquage[1])}"
        )

        # Descente torche (détection ohmique)
        if mode_simulation:
            self._l("; M17.1 (simulation - descente desactivee)")
        else:
            self._l("M17.1")

        # Passage en mode interpolation + vitesse lead-in (50%)
        self._l("G01")
        self._l("F $plasma.cut_feed[*0.500000]")

        # Allumage arc plasma
        if mode_simulation:
            self._l("; M20.1 (simulation - arc desactive)")
        else:
            self._l("M20.1")

        # Signal début lead-in
        self._l("M23.1")

        # --- Lead-in : polyline piquage → P[0]. En linéaire, 2 points (donc
        # un seul G01 vers p0). En arc tangent, discrétisation en N segments
        # G01 — le piquage est déjà atteint par le G00 précédent donc on
        # émet uniquement les points intermédiaires + p0.
        p0 = contour[0]
        for pt in poly_in[1:]:
            self._l(f"G01 X{self._coord(pt[0])} Y{self._coord(-pt[1])}")

        # --- Contour complet : P[0] → P[1] → ... → P[n-1] ---
        for pt in contour[1:]:
            self._l(f"G01 X{self._coord(pt[0])} Y{self._coord(-pt[1])}")

        # --- Fermeture vers P[0] (dernier point → retour au début) ---
        self._l(f"G01 X{self._coord(p0[0])} Y{self._coord(-p0[1])}")

        # Signal début lead-out
        self._l("M19.1")

        # --- Lead-out : polyline P[0] → point de dégagement. Linéaire = 1
        # seul G01 ; arc = discrétisation.
        for pt in poly_out[1:]:
            self._l(f"G01 X{self._coord(pt[0])} Y{self._coord(-pt[1])}")

        # Extinction arc plasma
        if mode_simulation:
            self._l("; M21.1 (simulation - arc desactive)")
        else:
            self._l("M21.1")

        # Fin séquence coupe
        self._l("M24.1")

        # Montée torche
        if mode_simulation:
            self._l("; M18.1 (simulation - montee desactivee)")
        else:
            self._l("M18.1")

        # Désélection torche
        self._l("G92 I0")

    def _ecrire_fin(self) -> None:
        """Écrit la fin du programme (zone 3)."""
        self._l("G90")
        self._l("M30")

    # -----------------------------------------------------------------------
    # Utilitaires de formatage
    # -----------------------------------------------------------------------

    def _l(self, ligne: str) -> None:
        """Ajoute une ligne au programme."""
        self._lignes.append(ligne)

    @staticmethod
    def _coord(valeur: float) -> str:
        """
        Formate une coordonnée en 6 décimales (format ECP1000).
        Utilise le point comme séparateur décimal (jamais la virgule).

        Exemple : 60.35 → '60.350000'
        """
        return f"{valeur:.6f}"

    @staticmethod
    def _fmt(valeur: float) -> str:
        """Formate une valeur numérique sans décimales inutiles pour les commentaires."""
        if valeur == int(valeur):
            return str(int(valeur))
        return f"{valeur:.3f}"


def generer(
    contours_places: List[ContourPlace],
    params: dict,
    nom_programme: str = "PROGRAMME",
    mode_simulation: bool = False,
) -> str:
    """
    Fonction de commodité : instancie GenerateurGCode et génère le programme.

    Args:
        contours_places : Contours ordonnés (issu de trajectory.ordonner_decoupes()).
        params          : Paramètres de découpe (issu de machine_params.get_defaults()).
        nom_programme   : Nom du programme (affiché dans l'IHM ECP1000).
        mode_simulation : Si True, les codes torche sont remplacés par des commentaires.

    Returns:
        Texte GCode complet prêt à être sauvegardé en .iso.
    """
    gen = GenerateurGCode()
    return gen.generer(contours_places, params, nom_programme, mode_simulation)

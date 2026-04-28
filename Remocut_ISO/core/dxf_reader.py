"""
core/dxf_reader.py — Lecture et parsing de fichiers DXF.

Convertit les entités DXF (LINE, ARC, LWPOLYLINE, CIRCLE, SPLINE) en une liste
de contours fermés, chacun représenté comme une liste ordonnée de tuples (x, y) en mm.

Convention de coordonnées : Y positif vers le haut (espace DXF standard).
La conversion Y → -Y pour le GCode machine est faite dans gcode_generator.py.
"""

import logging
import math
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Tolérance par défaut pour la fermeture des contours (mm)
TOLERANCE_FERMETURE_DEFAUT = 0.01

# Résolution angulaire pour la discrétisation des arcs (erreur de corde max en mm)
ERREUR_CORDE_MAX = 0.1

# Nombre minimum de segments pour discrétiser un arc
SEGMENTS_ARC_MIN = 8


def lire_dxf(
    chemin: str,
    tolerance_fermeture: float = TOLERANCE_FERMETURE_DEFAUT,
) -> List[List[Tuple[float, float]]]:
    """
    Lit un fichier DXF et retourne une liste de contours fermés.

    Entités supportées : LINE, ARC, LWPOLYLINE, CIRCLE, SPLINE.
    Les entités non supportées sont ignorées avec un avertissement.

    Args:
        chemin: Chemin vers le fichier .dxf
        tolerance_fermeture: Distance maximale (mm) pour fermer un contour ouvert.

    Returns:
        Liste de contours. Chaque contour est une liste de tuples (x, y) en mm.
        Le dernier point est distinct du premier (pas de doublon de fermeture).

    Raises:
        ValueError: Si le fichier est vide ou ne contient aucune entité reconnue.
        IOError: Si le fichier est illisible ou corrompu.
    """
    try:
        import ezdxf
    except ImportError:
        raise ImportError(
            "La bibliothèque ezdxf n'est pas installée. "
            "Exécutez : pip install ezdxf"
        )

    try:
        doc = ezdxf.readfile(chemin)
    except Exception as e:
        raise IOError(f"Impossible de lire le fichier DXF '{chemin}' : {e}")

    msp = doc.modelspace()

    # Phase 1 : extraire simultanément les contours directs (entités fermées
    # autonomes) et les segments primitifs (entités à assembler).
    #
    # • contours_directs : CIRCLE et LWPOLYLINE fermée — déjà des contours complets,
    #   court-circuitent l'assemblage (évite les faux « contour non fermé »).
    # • segments         : LINE, ARC, SPLINE, LWPOLYLINE ouverte — assemblés en Phase 2.
    contours_directs, segments = _extraire_contours_et_segments(msp)

    if not contours_directs and not segments:
        raise ValueError(
            f"Le fichier DXF '{chemin}' ne contient aucune entité géométrique reconnue."
        )

    # Phase 2 : assembler les segments en contours (seulement si nécessaire)
    contours_assembles: List[List[Tuple[float, float]]] = []
    if segments:
        contours_assembles = _assembler_contours(segments, tolerance_fermeture)

    contours = contours_directs + contours_assembles

    if not contours:
        raise ValueError(
            f"Aucun contour fermé trouvé dans '{chemin}'. "
            f"Vérifiez la tolérance de fermeture (actuellement {tolerance_fermeture} mm)."
        )

    logger.info(
        f"DXF '{chemin}' : {len(contours)} contour(s) "
        f"({len(contours_directs)} direct(s) + {len(contours_assembles)} assemblé(s))."
    )
    return contours


def _extraire_contours_et_segments(
    msp,
) -> tuple:
    """
    Parcourt le modelspace et sépare les entités en deux catégories :

    1. **Contours directs** : entités déjà fermées de façon autonome.
       — CIRCLE           : contour complet, aucun assemblage nécessaire.
       — LWPOLYLINE fermée: contour complet (closed=True), extrait via
                            _points_depuis_lwpolyline() pour gérer les bulges.
       Ces contours court-circuitent _assembler_contours et évitent les faux
       « contour non fermé » dus aux arrondis flottants en bout de chaîne.

    2. **Segments primitifs** : paires de points à assembler.
       — LINE, ARC, SPLINE, LWPOLYLINE ouverte.

    Returns:
        (contours_directs, segments)
        — contours_directs : List[List[Tuple[float,float]]]
        — segments         : List[Tuple[Tuple[float,float], Tuple[float,float]]]
    """
    contours_directs: List[List[Tuple[float, float]]] = []
    segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    entites_ignorees: set = set()

    for entite in msp:
        type_entite = entite.dxftype()

        try:
            if type_entite == 'LINE':
                s = _segment_depuis_line(entite)
                if s is not None:
                    segments.append(s)

            elif type_entite == 'ARC':
                pts = _points_depuis_arc(entite)
                segments.extend(_points_vers_segments(pts))

            elif type_entite == 'CIRCLE':
                # Cercle fermé : contour direct (pas d'assemblage)
                pts = _points_depuis_circle(entite)
                if len(pts) >= 3:
                    contours_directs.append(pts)

            elif type_entite == 'LWPOLYLINE':
                pts_lw = _points_depuis_lwpolyline(entite)
                if not pts_lw:
                    continue
                if entite.closed and len(pts_lw) >= 3:
                    # LWPOLYLINE fermée : contour direct (pas d'assemblage)
                    contours_directs.append(pts_lw)
                else:
                    # LWPOLYLINE ouverte : segments à assembler avec d'autres entités
                    segments.extend(_points_vers_segments(pts_lw))

            elif type_entite == 'SPLINE':
                pts = _points_depuis_spline(entite)
                segments.extend(_points_vers_segments(pts))

            elif type_entite in ('INSERT', 'DIMENSION', 'TEXT', 'MTEXT',
                                  'HATCH', 'ATTDEF', 'ATTRIB', 'VIEWPORT'):
                pass  # Entités non géométriques → ignorer silencieusement

            else:
                if type_entite not in entites_ignorees:
                    logger.warning(
                        f"Entité DXF non supportée ignorée : {type_entite}"
                    )
                    entites_ignorees.add(type_entite)

        except Exception as e:
            logger.warning(
                f"Erreur lors du traitement de l'entité {type_entite} : {e}"
            )
            continue

    return contours_directs, segments


def _segment_depuis_line(
    entite,
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Extrait un segment depuis une entité LINE."""
    try:
        start = entite.dxf.start
        end = entite.dxf.end
        p1 = (float(start.x), float(start.y))
        p2 = (float(end.x), float(end.y))
        # Ignorer les segments de longueur nulle
        if math.dist(p1, p2) < 1e-9:
            return None
        return (p1, p2)
    except Exception as e:
        logger.warning(f"Erreur lecture LINE : {e}")
        return None


def _points_depuis_arc(entite) -> List[Tuple[float, float]]:
    """
    Discrétise une entité ARC en liste de points.
    Respecte la convention ezdxf : angles en degrés, sens anti-horaire.
    """
    try:
        cx = float(entite.dxf.center.x)
        cy = float(entite.dxf.center.y)
        r = float(entite.dxf.radius)
        angle_debut = math.radians(float(entite.dxf.start_angle))
        angle_fin = math.radians(float(entite.dxf.end_angle))

        # Normaliser pour avoir angle_fin > angle_debut (sens anti-horaire DXF)
        if angle_fin <= angle_debut:
            angle_fin += 2 * math.pi

        angle_total = angle_fin - angle_debut
        n_segments = max(
            SEGMENTS_ARC_MIN,
            int(math.ceil(angle_total / _angle_par_erreur_corde(r))),
        )

        points = []
        for i in range(n_segments + 1):
            angle = angle_debut + i * angle_total / n_segments
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            points.append((x, y))

        return points

    except Exception as e:
        logger.warning(f"Erreur discrétisation ARC : {e}")
        return []


def _points_depuis_circle(entite) -> List[Tuple[float, float]]:
    """Discrétise un CIRCLE en polygone régulier fermé."""
    try:
        cx = float(entite.dxf.center.x)
        cy = float(entite.dxf.center.y)
        r = float(entite.dxf.radius)

        # Nombre de segments basé sur l'erreur de corde maximale
        angle_seg = _angle_par_erreur_corde(r)
        n_segments = max(
            int(math.ceil(2 * math.pi / angle_seg)),
            32,  # minimum 32 segments pour un cercle complet
        )

        points = []
        for i in range(n_segments):
            angle = 2 * math.pi * i / n_segments
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            points.append((x, y))

        return points

    except Exception as e:
        logger.warning(f"Erreur discrétisation CIRCLE : {e}")
        return []


def _points_depuis_lwpolyline(entite) -> List[Tuple[float, float]]:
    """
    Extrait les points d'une LWPOLYLINE en gérant les bulges (arcs intégrés).

    Un bulge ≠ 0 entre deux sommets signifie un arc ; on le discrétise.
    Un bulge = 0 donne un segment droit.

    Returns:
        Liste de points (x, y) — sans doublon de fermeture.
    """
    try:
        # Récupérer les données brutes (x, y, start_width, end_width, bulge)
        points_raw = list(entite.get_points('xyb'))  # (x, y, bulge)
    except Exception:
        try:
            # Fallback : itérer les sommets
            points_raw = [(v[0], v[1], v[4] if len(v) > 4 else 0.0)
                          for v in entite.get_points()]
        except Exception as e:
            logger.warning(f"Erreur lecture LWPOLYLINE : {e}")
            return []

    if not points_raw:
        return []

    n = len(points_raw)
    pts_out: List[Tuple[float, float]] = []

    for i in range(n):
        x1, y1, bulge = float(points_raw[i][0]), float(points_raw[i][1]), float(points_raw[i][2])
        # Indice du sommet suivant (boucle pour la fermeture)
        j = (i + 1) % n

        # Toujours ajouter le sommet courant
        pts_out.append((x1, y1))

        x2, y2 = float(points_raw[j][0]), float(points_raw[j][1])

        if abs(bulge) > 1e-9 and (entite.closed or i < n - 1):
            # Arc encodé par bulge — discrétiser
            arc_pts = _arc_depuis_bulge(x1, y1, x2, y2, bulge)
            # arc_pts[0] = (x1,y1) (déjà ajouté), arc_pts[-1] = (x2,y2) (ajouté à l'iter suivante)
            if len(arc_pts) > 2:
                pts_out.extend(arc_pts[1:-1])  # Points intermédiaires de l'arc

    return pts_out


def _arc_depuis_bulge(
    x1: float, y1: float,
    x2: float, y2: float,
    bulge: float,
) -> List[Tuple[float, float]]:
    """
    Calcule les points d'un arc défini par le bulge DXF.

    Convention DXF : bulge = tan(angle_arc / 4).
    Signe : positif = sens CCW (anti-horaire), négatif = sens CW (horaire).

    Returns:
        Liste de points incluant (x1,y1) et (x2,y2).
    """
    if abs(bulge) < 1e-9:
        return [(x1, y1), (x2, y2)]

    # Angle inclus de l'arc
    theta = 4 * math.atan(abs(bulge))
    # Distance entre les deux points
    d = math.dist((x1, y1), (x2, y2))
    if d < 1e-12:
        return [(x1, y1)]

    # Rayon de l'arc
    r = d / (2 * math.sin(theta / 2))

    # Centre de l'arc
    # Le centre est à distance r du milieu du segment, perpendiculairement
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    # Vecteur perpendiculaire normalisé
    dx, dy = x2 - x1, y2 - y1
    perp_x, perp_y = -dy / d, dx / d

    # Distance du milieu au centre
    dist_mc = math.sqrt(max(0.0, r * r - (d / 2) ** 2))

    # Convention de signe : bulge > 0 → arc CCW → centre à gauche
    if bulge > 0:
        cx = mx - perp_x * dist_mc
        cy = my - perp_y * dist_mc
    else:
        cx = mx + perp_x * dist_mc
        cy = my + perp_y * dist_mc

    # Angles de début et de fin
    angle_start = math.atan2(y1 - cy, x1 - cx)
    angle_end = math.atan2(y2 - cy, x2 - cx)

    # Sens de parcours
    if bulge > 0:  # CCW
        while angle_end < angle_start:
            angle_end += 2 * math.pi
    else:          # CW
        while angle_end > angle_start:
            angle_end -= 2 * math.pi

    # Discrétiser
    angle_total = abs(angle_end - angle_start)
    n_seg = max(SEGMENTS_ARC_MIN, int(math.ceil(angle_total / _angle_par_erreur_corde(r))))

    pts = []
    for k in range(n_seg + 1):
        t = k / n_seg
        if bulge > 0:
            a = angle_start + t * (angle_end - angle_start)
        else:
            a = angle_start + t * (angle_end - angle_start)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    return pts


def _points_depuis_spline(entite) -> List[Tuple[float, float]]:
    """Échantillonne une SPLINE ezdxf en liste de points via flattening."""
    try:
        points_3d = list(entite.flattening(distance=ERREUR_CORDE_MAX))
        return [(float(p.x), float(p.y)) for p in points_3d]
    except Exception as e:
        logger.warning(f"Erreur discrétisation SPLINE : {e}")
        return []


def _angle_par_erreur_corde(rayon: float) -> float:
    """
    Calcule l'angle (radians) entre deux points d'un arc tel que
    l'erreur de corde soit au plus ERREUR_CORDE_MAX.

    Formule : e = R * (1 - cos(theta/2)) → theta = 2*arccos(1 - e/R)
    """
    if rayon <= 0:
        return math.pi / 36  # 5° par défaut
    ratio = 1.0 - ERREUR_CORDE_MAX / rayon
    ratio = max(-1.0, min(1.0, ratio))
    return 2 * math.acos(ratio)


def _points_vers_segments(
    points: List[Tuple[float, float]],
    ferme: bool = False,
) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """
    Convertit une liste de points en liste de segments consécutifs.

    Args:
        points: Liste de points (x, y).
        ferme: Si True, ajoute un segment du dernier au premier point.

    Returns:
        Liste de segments ((x1,y1), (x2,y2)).
    """
    segments = []
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        if math.dist(p1, p2) > 1e-9:
            segments.append((p1, p2))

    if ferme and len(points) >= 2:
        p1 = points[-1]
        p2 = points[0]
        if math.dist(p1, p2) > 1e-9:
            segments.append((p1, p2))

    return segments


# ---------------------------------------------------------------------------
# Assemblage des segments en contours
# ---------------------------------------------------------------------------

def _assembler_contours(
    segments: List[Tuple[Tuple[float, float], Tuple[float, float]]],
    tolerance: float,
) -> List[List[Tuple[float, float]]]:
    """
    Assemble une liste de segments en chaînes de points (contours).

    Algorithme :
    1. Construire un graphe de connectivité entre segments.
    2. Parcourir en chaîne jusqu'à fermeture ou impasse.
    3. Conserver uniquement les contours fermés (premier ≈ dernier).

    Args:
        segments: Liste de segments ((x1,y1), (x2,y2)).
        tolerance: Distance max pour considérer deux points comme identiques.

    Returns:
        Liste de contours fermés (listes de points).
    """
    if not segments:
        return []

    # Copie de travail des segments (chacun peut être parcouru dans les 2 sens)
    segments_restants = list(segments)
    contours = []

    while segments_restants:
        # Démarrer un nouveau contour avec le premier segment disponible
        seg = segments_restants.pop(0)
        chaine = [seg[0], seg[1]]
        ferme = False  # True dès que la fermeture est confirmée dans la boucle

        # Étendre la chaîne tant qu'on trouve un segment connexe
        continuer = True
        while continuer:
            continuer = False
            extremite = chaine[-1]

            for i, s in enumerate(segments_restants):
                # Essai connexion directe (début du segment = extremite courante)
                if math.dist(extremite, s[0]) <= tolerance:
                    chaine.append(s[1])
                    segments_restants.pop(i)
                    continuer = True
                    break
                # Essai connexion inversée (fin du segment = extremite courante)
                elif math.dist(extremite, s[1]) <= tolerance:
                    chaine.append(s[0])
                    segments_restants.pop(i)
                    continuer = True
                    break

            # Vérifier si le contour est déjà fermé (point ajouté = point de départ)
            if len(chaine) >= 3 and math.dist(chaine[-1], chaine[0]) <= tolerance:
                # Contour fermé — retirer le doublon de fermeture
                chaine.pop()
                ferme = True
                break

        # Vérifier la fermeture du contour
        if len(chaine) >= 3:
            if ferme:
                # Fermeture confirmée dans la boucle — accepter directement.
                # (Ne pas re-vérifier dist_fermeture : après le pop(), chaine[-1]
                # est le dernier point UNIQUE, pas le doublon retiré.)
                contours.append(chaine)
            else:
                dist_fermeture = math.dist(chaine[-1], chaine[0])
                if dist_fermeture <= tolerance:
                    # Contour fermé sans doublon (dernière extrémité = début)
                    contours.append(chaine)
                elif dist_fermeture <= tolerance * 50:
                    # Contour presque fermé — forcer la fermeture avec avertissement
                    logger.warning(
                        f"Contour presque fermé (écart {dist_fermeture:.4f} mm) — "
                        f"fermeture forcée."
                    )
                    contours.append(chaine)
                else:
                    logger.warning(
                        f"Contour non fermé ignoré "
                        f"(écart {dist_fermeture:.4f} mm > tolérance {tolerance * 50:.4f} mm). "
                        f"Vérifiez la continuité des entités DXF."
                    )
        else:
            logger.debug(
                f"Chaîne de {len(chaine)} point(s) trop courte — ignorée."
            )

    return contours


def detecter_orientation(contour: List[Tuple[float, float]]) -> str:
    """
    Détecte le sens de parcours d'un contour via l'aire signée (algorithme du lacet).

    Args:
        contour: Liste de points (x, y).

    Returns:
        'ccw' (anti-horaire, aire positive) ou 'cw' (horaire, aire négative).
    """
    aire = _aire_signee(contour)
    return 'ccw' if aire > 0 else 'cw'


def _aire_signee(contour: List[Tuple[float, float]]) -> float:
    """
    Calcule l'aire signée d'un contour (algorithme de Gauss/Shoelace).
    Résultat positif = sens anti-horaire (CCW), négatif = sens horaire (CW).
    """
    n = len(contour)
    if n < 3:
        return 0.0
    aire = 0.0
    for i in range(n):
        x1, y1 = contour[i]
        x2, y2 = contour[(i + 1) % n]
        aire += (x1 * y2 - x2 * y1)
    return aire / 2.0

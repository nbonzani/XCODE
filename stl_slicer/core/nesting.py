# =============================================================================
# core/nesting.py — Algorithmes de répartition des contours 2D sur une plaque
#
# Deux algorithmes disponibles :
#
#   calculer_nesting()          — Nesting simple : placement en rangées, sans
#                                 rotation. Rapide, résultat prévisible.
#
#   calculer_nesting_optimise() — Nesting optimisé : Bottom-Left Fill avec
#                                 multi-séquençage (4 ordres de tri) et
#                                 rotation à 12 angles (pas de 30°).
#                                 Pour chaque ordre, les positions candidates
#                                 sont enrichies par grille croisée des bords
#                                 des pièces déjà placées.
#                                 Retourne le meilleur résultat (score = aire
#                                 de la boîte englobante globale).
# =============================================================================

from shapely.geometry import Polygon
from shapely.affinity import translate, rotate as shapely_rotate
from typing import List, Tuple, Optional, Callable


# Type d'un résultat de placement :
# (polygone_déplacé, offset_x, offset_y, indice_original)
PlacementType = Tuple[Polygon, float, float, int]

# Angles candidats pour le nesting optimisé (pas de 30° → 12 orientations)
_ANGLES_OPTIMISE = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]


# =============================================================================
# Nesting simple (rangées, sans rotation)
# =============================================================================

def calculer_nesting(
    polygones: List[Polygon],
    largeur_plaque: float,
    hauteur_plaque: float,
    espacement: float,
    espacement_bord: Optional[float] = None,
) -> Tuple[List[PlacementType], bool]:
    """
    Répartit les polygones 2D sur la plaque par placement en rangées.

    Algorithme :
      1. Trier les polygones par hauteur de boîte englobante (décroissant).
      2. Placer chaque pièce à la position courante (x_courant, y_courant).
      3. Si la pièce dépasse le bord droit, passer à la rangée suivante.
      4. Si la pièce dépasse le bord haut, elle n'est pas placée (signalé).

    Paramètres:
        polygones (list)            : liste de Polygon shapely à placer
        largeur_plaque (float)      : largeur de la plaque en mm
        hauteur_plaque (float)      : hauteur de la plaque en mm
        espacement (float)          : distance minimale entre pièces (mm)
        espacement_bord (float|None): distance minimale pièces/bord (mm).
                                      Si None, utilise la valeur de espacement.

    Retourne:
        tuple (placements, tous_places)
    """
    if espacement_bord is None:
        espacement_bord = espacement

    if not polygones:
        return [], True

    indices_tries = sorted(
        range(len(polygones)),
        key=lambda i: _hauteur_bbox(polygones[i]),
        reverse=True
    )

    placements: List[PlacementType] = []
    nb_non_places = 0

    x_courant = espacement_bord
    y_courant = espacement_bord
    hauteur_rangee = 0.0

    for idx in indices_tries:
        poly = polygones[idx]
        minx, miny, maxx, maxy = poly.bounds
        largeur_piece = maxx - minx
        hauteur_piece = maxy - miny

        if largeur_piece + 2 * espacement_bord > largeur_plaque:
            nb_non_places += 1
            continue
        if hauteur_piece + 2 * espacement_bord > hauteur_plaque:
            nb_non_places += 1
            continue

        if x_courant + largeur_piece + espacement_bord > largeur_plaque:
            x_courant = espacement_bord
            y_courant += hauteur_rangee + espacement
            hauteur_rangee = 0.0

        if y_courant + hauteur_piece + espacement_bord > hauteur_plaque:
            nb_non_places += 1
            continue

        offset_x = x_courant - minx
        offset_y = y_courant - miny
        poly_place = translate(poly, xoff=offset_x, yoff=offset_y)
        placements.append((poly_place, offset_x, offset_y, idx))

        x_courant += largeur_piece + espacement
        hauteur_rangee = max(hauteur_rangee, hauteur_piece)

    return placements, (nb_non_places == 0)


# =============================================================================
# Nesting optimisé (Bottom-Left Fill + rotation + multi-séquençage)
# =============================================================================

def calculer_nesting_optimise(
    polygones: List[Polygon],
    largeur_plaque: float,
    hauteur_plaque: float,
    espacement: float,
    callback_progression: Optional[Callable[[int, int], None]] = None,
    methode: str = 'multi',
    espacement_bord: Optional[float] = None,
) -> Tuple[List[PlacementType], bool]:
    """
    Nesting optimisé : minimise l'aire de la boîte englobante des pièces placées.

    Algorithme Bottom-Left Fill + Rotation (BL+R), avec choix de séquençage :

      methode='aire'      — Trie les pièces par aire décroissante (grandes en premier).
                            1 séquence, rapide.
      methode='perimetre' — Trie par périmètre décroissant.
                            1 séquence, rapide.
      methode='dim_max'   — Trie par dimension maximale décroissante (max(w, h)).
                            1 séquence, rapide.
      methode='multi'     — Essaie 4 ordres de tri (aire ↓, périmètre ↓, dim_max ↓,
                            aire ↑) et retourne le meilleur résultat.
                            ~4× plus lent, meilleur résultat global.

    Pour chaque séquence, le placement BL+R :
      1. Pour chaque pièce, explore 12 rotations (pas de 30°).
      2. Pour chaque rotation, teste les positions candidates (coins des pièces
         déjà placées + grille croisée des bords droit/haut).
      3. Choisit la position qui minimise l'aire de la boîte englobante globale.

    Contraintes respectées :
      - Espacement minimum `espacement` entre toutes les pièces.
      - Espacement minimum `espacement` entre les pièces et les bords de plaque.
      - Dimensions de la plaque non dépassées.

    Paramètres:
        polygones              : liste de Polygon shapely à placer
        largeur_plaque         : largeur maximale de la plaque (mm)
        hauteur_plaque         : hauteur maximale de la plaque (mm)
        espacement             : distance minimum entre pièces (mm)
        callback_progression   : fonction(etape, total) appelée à chaque pièce
        methode                : 'aire' | 'perimetre' | 'dim_max' | 'multi'
        espacement_bord        : distance minimum pièces/bord (mm). Si None,
                                 utilise la valeur de espacement.

    Retourne:
        tuple (placements, tous_places)
          - placements : liste de (polygone_décalé, ox, oy, idx_original)
          - tous_places : True si toutes les pièces ont pu être placées
    """
    if espacement_bord is None:
        espacement_bord = espacement

    if not polygones:
        return [], True

    n = len(polygones)

    # --- Construction des ordres disponibles ---
    def _dim_max_key(i):
        minx, miny, maxx, maxy = polygones[i].bounds
        return max(maxx - minx, maxy - miny)

    _tous_ordres = {
        'aire':      sorted(range(n), key=lambda i: polygones[i].area, reverse=True),
        'perimetre': sorted(range(n), key=lambda i: polygones[i].length, reverse=True),
        'dim_max':   sorted(range(n), key=_dim_max_key, reverse=True),
        'aire_asc':  sorted(range(n), key=lambda i: polygones[i].area),
    }

    if methode == 'multi':
        # 4 ordres + déduplification (peu de pièces → certains ordres identiques)
        ordres_a_tester = list(_tous_ordres.values())
        ordres_uniques: List[List[int]] = []
        vus: set = set()
        for o in ordres_a_tester:
            cle = tuple(o)
            if cle not in vus:
                vus.add(cle)
                ordres_uniques.append(o)
    else:
        ordres_uniques = [_tous_ordres.get(methode, _tous_ordres['aire'])]

    nb_ordres = len(ordres_uniques)
    total_etapes = nb_ordres * n

    meilleur_places: Optional[List[PlacementType]] = None
    meilleur_nb_non = n + 1
    meilleur_score: float = float('inf')

    for i_ordre, ordre in enumerate(ordres_uniques):

        def _cb(etape: int, _total: int, _i=i_ordre):
            if callback_progression:
                callback_progression(_i * n + etape, total_etapes)

        places, nb_non = _run_une_sequence(
            ordre, polygones, largeur_plaque, hauteur_plaque,
            espacement, _cb, espacement_bord
        )

        # Score : priorité au plus grand nombre de pièces placées,
        # puis à la plus petite boîte englobante.
        if places:
            bw, bh = calculer_bbox_placements(places)
            score = bw * bh
        else:
            score = float('inf')

        if nb_non < meilleur_nb_non or (
            nb_non == meilleur_nb_non and score < meilleur_score
        ):
            meilleur_places = places
            meilleur_nb_non = nb_non
            meilleur_score = score

    # Signal de fin à 100 %
    if callback_progression:
        callback_progression(total_etapes, total_etapes)

    return meilleur_places or [], meilleur_nb_non == 0


# =============================================================================
# Séquence de placement interne (BL+R pour un ordre donné)
# =============================================================================

def _run_une_sequence(
    ordre: List[int],
    polygones: List[Polygon],
    largeur_plaque: float,
    hauteur_plaque: float,
    espacement: float,
    callback: Optional[Callable[[int, int], None]] = None,
    espacement_bord: Optional[float] = None,
) -> Tuple[List[PlacementType], int]:
    """
    Exécute l'algorithme Bottom-Left Fill + Rotation pour un ordre de pièces donné.

    Retourne:
        (places, nb_non_places)
    """
    if espacement_bord is None:
        espacement_bord = espacement

    places: List[PlacementType] = []
    placed_buffered: List[Polygon] = []
    nb_non = 0

    for etape, idx in enumerate(ordre):
        if callback:
            callback(etape, len(ordre))

        poly_orig = polygones[idx]
        meilleur: Optional[PlacementType] = None
        meilleur_score: float = float('inf')

        # Candidats classiques sur la plaque
        candidats = _candidats_coins(places, espacement, espacement_bord)

        # Zones utilisables à l'intérieur des trous des pièces déjà placées
        zones_trous = _extraire_zones_trous(places, espacement)

        for angle in _ANGLES_OPTIMISE:
            # --- Rotation + normalisation (coin bas-gauche à l'origine) ---
            poly_r = shapely_rotate(poly_orig, angle,
                                    origin='centroid', use_radians=False)
            bmin_x, bmin_y, bmax_x, bmax_y = poly_r.bounds
            pw = bmax_x - bmin_x
            ph = bmax_y - bmin_y

            poly_norm = translate(poly_r, -bmin_x, -bmin_y)

            # ── Candidats sur la plaque (placement classique) ────────────────
            if pw + 2 * espacement_bord <= largeur_plaque and \
               ph + 2 * espacement_bord <= hauteur_plaque:

                for cx, cy in candidats:
                    if cx < espacement_bord - 1e-9:
                        continue
                    if cy < espacement_bord - 1e-9:
                        continue
                    if cx + pw + espacement_bord > largeur_plaque + 1e-9:
                        continue
                    if cy + ph + espacement_bord > hauteur_plaque + 1e-9:
                        continue

                    if not _collision_libre(poly_norm, cx, cy, pw, ph, placed_buffered):
                        continue

                    poly_place = translate(poly_norm, cx, cy)
                    score = _score_bbox(places, poly_place)

                    if score < meilleur_score:
                        meilleur_score = score
                        meilleur = (poly_place, cx, cy, idx)

            # ── Candidats dans les trous des pièces placées ──────────────────
            # Une pièce dans un trou ne peut qu'améliorer (ou égaler) le score
            # car elle n'étend pas la bbox globale. On lui donne une légère
            # préférence (−1e-6) pour départager les égalités.
            for trou_zone in zones_trous:
                for cx, cy in _candidats_dans_trou(trou_zone, pw, ph):
                    poly_place = translate(poly_norm, cx, cy)

                    # La pièce doit être entièrement contenue dans la zone du trou
                    if not trou_zone.contains(poly_place):
                        continue

                    # Pas de collision avec les pièces déjà placées
                    if not _collision_libre(poly_norm, cx, cy, pw, ph, placed_buffered):
                        continue

                    score = _score_bbox(places, poly_place) - 1e-6

                    if score < meilleur_score:
                        meilleur_score = score
                        meilleur = (poly_place, cx, cy, idx)

        if meilleur is not None:
            poly_place, cx, cy, idx_orig = meilleur
            places.append((poly_place, cx, cy, idx_orig))
            placed_buffered.append(poly_place.buffer(espacement))
        else:
            nb_non += 1

    return places, nb_non


# =============================================================================
# Fonctions utilitaires communes
# =============================================================================

def calculer_surface_utilisee(
    placements: List[PlacementType],
    largeur_plaque: float,
    hauteur_plaque: float,
    espacement_pieces: float = 0.0,
    espacement_bord: float = 0.0,
) -> float:
    """
    Taux de remplissage (%) selon la formule géométrique :

        remplissage = (S1 + L2·Epp/2 + L3·(Epb − Epp/2)) / S3

    où :
        S1  = surface totale des pièces (mm²)
        L2  = somme des périmètres extérieurs des pièces (mm)
        S3  = surface de la boîte englobante des pièces (mm²)
        L3  = périmètre de la boîte englobante (mm)
        Epp = espacement pièce-pièce (mm)
        Epb = espacement pièce-bord (mm)

    Interprétation : S1 représente les pièces, L2·Epp/2 la surface des
    demi-marges inter-pièces, L3·(Epb−Epp/2) la bande de bord corrigée
    de la demi-marge déjà comptée sur le périmètre de la bbox. Le tout
    rapporté à la surface de la boîte englobante donne l'efficacité de placement.

    Si les deux espacements sont nuls → formule réduite à S1/S3.
    Le dénominateur utilise toujours la bbox brute des pièces (sans Epb),
    car l'affichage de la taille tôle est géré séparément via
    calculer_bbox_placements(espacement_bord=...).
    """
    if not placements:
        return 0.0

    # S1 : surface totale des pièces
    S1 = sum(poly.area for poly, *_ in placements)

    # L2 : somme des périmètres extérieurs
    L2 = sum(poly.exterior.length for poly, *_ in placements)

    # Boîte englobante brute (sans marge bord)
    bw, bh = calculer_bbox_placements(placements, espacement_bord=0.0)
    S3 = bw * bh
    if S3 <= 0:
        return 0.0

    # L3 : périmètre de la boîte englobante
    L3 = 2.0 * (bw + bh)

    numerateur = S1 + L2 * espacement_pieces / 2.0 + L3 * (espacement_bord - espacement_pieces / 2.0)
    return min(100.0, numerateur / S3 * 100.0)


def calculer_bbox_placements(
    placements: List[PlacementType],
    espacement_bord: float = 0.0,
) -> Tuple[float, float]:
    """
    Retourne (largeur, hauteur) de la boîte englobante des polygones placés,
    augmentée de 2×espacement_bord pour obtenir la taille de tôle minimale.

    Avec espacement_bord=0 (défaut) : bbox brute des pièces.
    Avec espacement_bord>0          : taille tôle minimum = bbox + 2×Epb.
    """
    if not placements:
        return 0.0, 0.0
    min_x = min(poly.bounds[0] for poly, *_ in placements)
    min_y = min(poly.bounds[1] for poly, *_ in placements)
    max_x = max(poly.bounds[2] for poly, *_ in placements)
    max_y = max(poly.bounds[3] for poly, *_ in placements)
    return (max_x - min_x + 2 * espacement_bord,
            max_y - min_y + 2 * espacement_bord)


# =============================================================================
# Fonctions internes de l'algorithme optimisé
# =============================================================================

def _extraire_zones_trous(places: List[PlacementType], espacement: float) -> List[Polygon]:
    """
    Extrait les zones utilisables à l'intérieur des trous des pièces placées.

    Chaque anneau intérieur (trou) est érodé de `espacement` pour garantir la
    distance minimale entre la pièce insérée et le bord du trou.
    Les zones trop petites (aire < 1 mm²) sont ignorées.
    """
    zones: List[Polygon] = []
    for poly_placed, *_ in places:
        for interior in poly_placed.interiors:
            trou = Polygon(interior.coords)
            zone = trou.buffer(-espacement) if espacement > 0 else trou
            if zone is None or zone.is_empty or not zone.is_valid:
                continue
            if zone.area < 1.0:
                continue
            zones.append(zone)
    return zones


def _candidats_dans_trou(
    trou_zone: Polygon,
    pw: float,
    ph: float,
    nb_pas: int = 3
) -> list:
    """
    Génère des candidats (cx, cy) pour placer une pièce de taille (pw × ph)
    à l'intérieur d'une zone de trou.

    (cx, cy) est le coin bas-gauche de la bounding-box de la pièce.
    Un grid nb_pas × nb_pas est balayé dans la plage valide du coin bas-gauche
    dans la bbox du trou, pour couvrir les positions possibles.

    Retourne une liste vide si la pièce est trop grande pour le trou.
    """
    tz_minx, tz_miny, tz_maxx, tz_maxy = trou_zone.bounds
    cx_min, cx_max = tz_minx, tz_maxx - pw
    cy_min, cy_max = tz_miny, tz_maxy - ph

    if cx_max < cx_min - 1e-6 or cy_max < cy_min - 1e-6:
        return []   # Pièce plus grande que la bbox du trou → impossible

    candidats = []
    steps = nb_pas - 1 if nb_pas > 1 else 1
    for i in range(nb_pas):
        cx = cx_min + i * (cx_max - cx_min) / steps if steps else cx_min
        for j in range(nb_pas):
            cy = cy_min + j * (cy_max - cy_min) / steps if steps else cy_min
            candidats.append((cx, cy))
    return candidats


def _candidats_coins(
    places: List[PlacementType],
    espacement: float,
    espacement_bord: Optional[float] = None,
) -> list:
    """
    Génère les positions candidates pour le prochain placement.

    Deux niveaux de candidats :

    1. Coins classiques (Bottom-Left Fill) :
       Pour chaque pièce placée, on génère les coins à droite et au-dessus,
       qui sont les meilleurs points de départ pour la pièce suivante.

    2. Grille croisée (enrichissement) :
       Produit cartésien des bords droits (x1+espacement) × bords supérieurs
       (y1+espacement) de toutes les pièces placées, incluant les bords de
       la plaque (espacement_bord, espacement_bord).
       Ces candidats supplémentaires permettent de « glisser » une pièce dans
       des espaces qui ne coïncident pas avec un unique coin existant.

    Le tri par (y, x) donne le critère Bottom-Left : on préfère les
    positions basses et à gauche, ce qui favorise un remplissage compact.
    """
    if espacement_bord is None:
        espacement_bord = espacement

    pts: set = set()
    pts.add((espacement_bord, espacement_bord))

    # Accumulation des bords pour la grille croisée
    right_xs = [espacement_bord]   # position initiale : bord gauche de plaque
    top_ys   = [espacement_bord]   # position initiale : bord bas de plaque

    for poly_place, *_ in places:
        x0, y0, x1, y1 = poly_place.bounds

        # --- Coins classiques ---
        pts.add((x1 + espacement, espacement_bord))  # à droite, au ras du bas
        pts.add((x1 + espacement, y0))               # à droite, aligné avec le bas de la pièce
        pts.add((espacement_bord, y1 + espacement))  # à gauche, au-dessus
        pts.add((x0, y1 + espacement))               # aligné avec le bord gauche de la pièce

        # --- Accumulation grille croisée ---
        right_xs.append(x1 + espacement)
        top_ys.append(y1 + espacement)

    # --- Grille croisée : toutes les combinaisons (x_droit, y_haut) ---
    for x in right_xs:
        for y in top_ys:
            pts.add((x, y))

    # Tri Bottom-Left : priorité aux positions basses, puis à gauche
    return sorted(pts, key=lambda p: (round(p[1], 4), round(p[0], 4)))


def _collision_libre(
    poly_norm: Polygon,
    cx: float,
    cy: float,
    pw: float,
    ph: float,
    placed_buffered: List[Polygon]
) -> bool:
    """
    Retourne True si poly_norm placé à (cx, cy) ne chevauche aucune des
    pièces dans placed_buffered (qui sont déjà expandées d'`espacement`).

    Technique :
      - Pré-filtre bounding-box pour éliminer rapidement les pièces distantes.
      - Test géométrique shapely uniquement si les BBox se recoupent.
      - Traduction lazy : translate() n'est appelé qu'une fois par candidat.
    """
    c_x0, c_y0 = cx, cy
    c_x1, c_y1 = cx + pw, cy + ph

    poly_place: Optional[Polygon] = None

    for pb in placed_buffered:
        pb_b = pb.bounds
        if c_x1 <= pb_b[0] or c_x0 >= pb_b[2]:
            continue
        if c_y1 <= pb_b[1] or c_y0 >= pb_b[3]:
            continue
        if poly_place is None:
            poly_place = translate(poly_norm, cx, cy)
        if poly_place.intersects(pb):
            return False

    return True


def _score_bbox(places: List[PlacementType], candidat: Polygon) -> float:
    """
    Score d'un placement candidat = aire de la boîte englobante de toutes
    les pièces déjà placées + le candidat.

    Minimiser ce score correspond à minimiser la surface de la plaque utilisée.
    """
    all_bounds = [poly.bounds for poly, *_ in places] + [candidat.bounds]
    min_x = min(b[0] for b in all_bounds)
    min_y = min(b[1] for b in all_bounds)
    max_x = max(b[2] for b in all_bounds)
    max_y = max(b[3] for b in all_bounds)
    return (max_x - min_x) * (max_y - min_y)


def _hauteur_bbox(poly: Polygon) -> float:
    """Hauteur de la boîte englobante (utilisée pour le tri du nesting simple)."""
    minx, miny, maxx, maxy = poly.bounds
    return maxy - miny

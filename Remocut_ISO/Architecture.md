# Architecture — Remocut ISO Generator

## Vue d'ensemble

```
Fichiers DXF → [dxf_reader] → Contours géométriques
                                      ↓
Paramètres UI → [geometry] → Contours offsettés + lead-in/out
                                      ↓
Format tôle → [nesting] → Positions XY des pièces
                                      ↓
              [trajectory] → Ordre de découpe + parcours complet
                                      ↓
              [gcode_generator] → Fichier GCode ISO ECP1000
```

## Modules et responsabilités

| Module | Rôle | Dépendances |
|---|---|---|
| main.py | Point d'entrée, lancement PyQt6 | ui/main_window |
| ui/main_window.py | Fenêtre principale, orchestration des modules | Tous les modules ui et core |
| ui/dxf_viewer.py | Affichage 2D des contours DXF importés | core/dxf_reader |
| ui/nesting_view.py | Visualisation du placement sur tôle | core/nesting |
| ui/params_panel.py | Saisie des paramètres de découpe | core/machine_params |
| core/dxf_reader.py | Parsing DXF → liste de contours (listes de points) | ezdxf |
| core/geometry.py | Offset kerf, lead-in/out, sens CW/CCW, fermeture contours | shapely, numpy |
| core/nesting.py | Placement des pièces sur la tôle (algorithme grille V1) | shapely |
| core/trajectory.py | Ordre de découpe, regroupement intérieur/extérieur | core/geometry |
| core/gcode_generator.py | Génération du GCode ISO conforme ECP1000 | core/trajectory, core/machine_params |
| core/machine_params.py | Paramètres par défaut par matériau/épaisseur | — |
| utils/file_io.py | Lecture DXF, écriture GCode | ezdxf, core/gcode_generator |

## Flux de données

1. Utilisateur ouvre fichier(s) DXF
   → dxf_reader.parse() → List[Contour]  (Contour = liste ordonnée de segments)

2. Utilisateur saisit paramètres (matériau, kerf, vitesse…)
   → machine_params.get_defaults(matériau, épaisseur) → Dict[params]

3. Utilisateur lance le nesting
   → nesting.place(contours, format_tole, marge) → List[ContourPlacé] (avec offset XY)

4. Calcul automatique des trajectoires
   → geometry.apply_kerf_offset(contours, kerf, côté) → contours offsettés
   → geometry.add_lead_in_out(contours, longueur, type) → contours avec approches
   → trajectory.order_cuts(contours) → parcours ordonné (trous avant contours extérieurs)

5. Génération GCode
   → gcode_generator.generate(parcours, params) → str (texte GCode complet)

6. Export fichier
   → file_io.write_gcode(texte, chemin) → fichier .nc / .iso sur disque

## Choix techniques justifiés

- **ezdxf** plutôt que dxfgrabber → maintenance active, supporte DXF R12 à 2024, extraction fiable des LWPOLYLINE et SPLINE
- **shapely** pour les calculs géométriques → offset de polygones (kerf) robuste, détection intérieur/extérieur (contains), union/intersection pour nesting
- **PyQt6** plutôt que tkinter → rendu 2D via QPainter suffisamment performant pour visualisation plasma, cohérent avec les autres applications du projet XCODE de Nico
- **Nesting en grille V1** plutôt qu'algorithme génétique → suffisant pour un usage atelier avec peu de pièces, implémentable en moins de 100 lignes
- **G41/G42 avec D1** → la compensation de kerf est gérée par le contrôleur ECP1000 côté machine, l'application ne doit pas pré-calculer l'offset dans les coordonnées XY (double compensation sinon)
- **Structure de données Contour** : liste ordonnée de tuples (x, y) en mm, sens anti-horaire pour contours extérieurs, horaire pour contours intérieurs (convention ISO)

## Structure des fichiers

```
Remocut_ISO/
├── CLAUDE.md                  # lu automatiquement par Claude Code
├── Fonctionnalités.md         # périmètre fonctionnel
├── Architecture.md            # ce fichier
├── main.py                    # point d'entrée
├── requirements.txt           # ezdxf, shapely, numpy, PyQt6
├── ui/
│   ├── __init__.py
│   ├── main_window.py         # fenêtre principale, menus, onglets
│   ├── dxf_viewer.py          # canvas 2D QPainter pour affichage DXF
│   ├── nesting_view.py        # canvas 2D QPainter pour affichage nesting
│   └── params_panel.py        # formulaire paramètres découpe
├── core/
│   ├── __init__.py
│   ├── dxf_reader.py          # parsing DXF → contours
│   ├── geometry.py            # offset, lead-in/out, sens
│   ├── nesting.py             # placement pièces sur tôle
│   ├── trajectory.py          # ordre et parcours de découpe
│   ├── gcode_generator.py     # générateur GCode ECP1000 (module critique)
│   └── machine_params.py      # base de données paramètres matériaux
├── utils/
│   ├── __init__.py
│   └── file_io.py             # entrées/sorties fichiers
├── doc/                       # exemples GCode réels (NE PAS MODIFIER)
└── output/                    # GCode générés par l'application
```

## Points d'intégration critiques

- **dxf_reader → geometry** : les contours doivent être des listes de points (x,y) avec le bon sens de rotation — source de bugs si les entités DXF ont des orientations mixtes
- **geometry (kerf offset) → gcode_generator** : si G41/G42 est utilisé, NE PAS appliquer l'offset shapely en plus (double compensation). Utiliser G41/G42 machine et ne PAS appliquer l'offset géométrique en Python.
- **trajectory (ordre) → gcode_generator** : les trous doivent absolument être découpés avant le contour extérieur de la pièce — à vérifier par un test avec shapely.contains()
- **gcode_generator → format ECP1000** : ce module est le plus critique. Il DOIT être développé en lisant d'abord bilan_gcode_remocut.md et les fichiers du dossier doc/

# CLAUDE.md — Remocut ISO Generator

## Objectif du projet
Application Python de génération automatique de programmes de découpe plasma au format GCode ISO,
destinée à la machine REMOCUT II – h2o équipée du contrôleur Eurosoft ECP1000.
L'application prend en entrée un ou plusieurs fichiers DXF, permet le nesting des pièces sur un
format de tôle, calcule les trajectoires de découpe avec lead-in/lead-out, gère la compensation
de kerf (G41/G42), et exporte un fichier GCode directement exécutable sur la machine.
Utilisateur unique : Nico (enseignant-ingénieur), usage atelier à Polytech Nancy.

## Stack technique
- Langage principal : Python 3.11+
- Framework UI : PyQt6
- Bibliothèques principales :
  - ezdxf (lecture fichiers DXF)
  - shapely (géométrie 2D, offset de kerf, nesting)
  - numpy (calculs numériques)
  - PyQt6 (interface graphique)
- Gestionnaire de paquets : pip

## Plateforme cible
Windows 10/11 (PC Polytech Nancy, machines bonzani1.PNY-GM-NBO)
Application desktop standalone, pas de serveur, pas de connexion réseau.

## Référence GCode machine
Le format GCode attendu par l'ECP1000 Eurosoft est documenté dans :
C:\Users\bonzani1.PNY-GM-NBO\Documents\CLAUDE\XCODE\Remocut_ISO\bilan_gcode_remocut.md

Des exemples de programmes réels se trouvent dans :
C:\Users\bonzani1.PNY-GM-NBO\Documents\CLAUDE\XCODE\Remocut_ISO\doc\

LIRE CES FICHIERS EN PRIORITÉ avant de générer la moindre ligne de GCode.
Les M-codes, structure d'en-tête et séquence torche doivent être conformes à ces exemples.

## Contraintes non négociables
- Le GCode généré doit être 100% conforme aux exemples de la machine réelle (dossier doc/)
- M03 = allumage torche, M05 = extinction torche (à confirmer sur les exemples réels)
- Le THC (contrôle hauteur torche) est géré automatiquement par l'ECP1000 — ne pas l'inclure dans le GCode utilisateur
- G41/G42 pour la compensation de kerf (rayon = kerf/2, stocké dans registre D1)
- G21 (mm), G90 (coordonnées absolues), G40 (annulation kerf) en initialisation
- Lead-in linéaire ou en arc avant chaque contour, lead-out après
- G04 P[ms] pour les temporisations si nécessaires
- G00 pour les déplacements rapides hors matière
- G01/G02/G03 pour les trajectoires de découpe
- M30 en fin de programme
- Encodage fichier : UTF-8 ou ASCII (à confirmer sur les exemples)
- Extension fichier : à confirmer sur les exemples (probable .nc ou .iso)

## Architecture des modules
- main.py : point d'entrée, lancement UI PyQt6
- ui/main_window.py : fenêtre principale, menus, onglets
- ui/dxf_viewer.py : visualisation 2D des géométries importées
- ui/nesting_view.py : vue de nesting sur tôle
- ui/params_panel.py : panneau paramètres (matériau, vitesse, kerf, etc.)
- core/dxf_reader.py : lecture et parsing de fichiers DXF avec ezdxf
- core/geometry.py : manipulation géométrique (offset, lead-in, lead-out, sens de découpe)
- core/nesting.py : algorithme de nesting des pièces sur la tôle
- core/trajectory.py : calcul des trajectoires de découpe (ordre, approches)
- core/gcode_generator.py : génération du GCode ISO ECP1000
- core/machine_params.py : base de données des paramètres par matériau (acier, alu, inox)
- utils/file_io.py : lecture/écriture fichiers (DXF entrée, GCode sortie)

## Structure des dossiers
```
Remocut_ISO/
├── CLAUDE.md
├── Fonctionnalités.md
├── Architecture.md
├── main.py
├── requirements.txt
├── ui/
│   ├── __init__.py
│   ├── main_window.py
│   ├── dxf_viewer.py
│   ├── nesting_view.py
│   └── params_panel.py
├── core/
│   ├── __init__.py
│   ├── dxf_reader.py
│   ├── geometry.py
│   ├── nesting.py
│   ├── trajectory.py
│   ├── gcode_generator.py
│   └── machine_params.py
├── utils/
│   ├── __init__.py
│   └── file_io.py
├── doc/
└── output/
```

## Conventions de code
- Langue des commentaires : français
- Style de nommage : snake_case pour fonctions/variables, PascalCase pour classes
- Indentation : 4 espaces
- Gestion des erreurs : try/except avec messages d'erreur explicites en français, logging dans console PyQt6
- Type hints Python sur toutes les fonctions publiques

## Ordre de développement recommandé
1. Lire bilan_gcode_remocut.md et les fichiers du dossier doc/ — comprendre le format exact ECP1000
2. core/machine_params.py — paramètres matériaux (acier, alu, inox) + structure de données
3. core/dxf_reader.py — lecture DXF, extraction des entités (LINE, ARC, LWPOLYLINE, CIRCLE, SPLINE)
4. core/geometry.py — offset kerf, lead-in/lead-out, détection sens (CW/CCW)
5. core/gcode_generator.py — générateur GCode conforme ECP1000 (module le plus critique)
6. core/trajectory.py — calcul ordre de découpe, regroupement contours
7. core/nesting.py — placement pièces sur tôle (algo simple en V1 : placement en rangées)
8. ui/main_window.py + ui/params_panel.py — interface principale
9. ui/dxf_viewer.py — visualisation géométrie importée
10. ui/nesting_view.py — visualisation nesting
11. main.py — intégration finale

## Points d'attention
- PRIORITÉ ABSOLUE : lire les exemples GCode réels avant d'écrire une seule ligne de gcode_generator.py
- Le nesting en V1 peut être simple (placement en grille avec marges) — pas besoin d'optimisation
- Les arcs DXF peuvent avoir des sens CW/CCW différents selon les logiciels — vérifier la convention ezdxf
- La compensation de kerf G41/G42 doit être activée AVANT le lead-in et annulée G40 APRÈS le lead-out
- Prévoir un mode "simulation à blanc" (génération GCode sans allumage torche) pour test machine
- L'interface doit permettre de visualiser le GCode avant export (prévisualisation trajectoire)
- Paramètres par défaut raisonnables pour acier 3mm : F=2500, kerf=1.5mm, lead-in=5mm

# STL Slicer — Découpe Laser par empilement de plaques

Application desktop Python pour sectionner des pièces 3D (STL) en tranches
2D, répartir les contours sur une plaque, et exporter en DXF pour découpe laser.

## Installation

```bash
cd stl_slicer
pip install -r requirements.txt
```

## Lancement

```bash
python main.py
```

## Workflow

1. **Ouvrir un STL** : `Fichier > Ouvrir` ou bouton "Ouvrir un fichier STL..."
2. **Visualiser** : rotater (clic gauche), zoomer (molette), panoramique (clic droit)
3. **Sectionner** : choisir l'axe (Z/X/Y), l'épaisseur (mm), puis "Calculer les sections"
4. **Nesting** : saisir dimensions plaque + espacement, puis "Calculer le nesting"
5. **Exporter** : DXF individuels (un par tranche) ou DXF nesting complet

## Structure

```
stl_slicer/
├── main.py              # Point d'entrée
├── requirements.txt     # Dépendances pip
├── core/
│   ├── stl_loader.py    # Chargement STL (trimesh + PyVista)
│   ├── slicer.py        # Sectionnement par plans parallèles
│   ├── nesting.py       # Placement en rangées sur plaque
│   └── exporter.py      # Export DXF (ezdxf)
└── ui/
    ├── main_window.py   # Fenêtre principale PyQt6
    ├── viewer_3d.py     # Vue 3D PyVista/VTK
    └── nesting_view.py  # Vue nesting 2D QPainter
```

## Dépendances principales

| Bibliothèque | Rôle |
|---|---|
| PyQt6 | Interface graphique |
| pyvista + pyvistaqt | Visualisation 3D VTK/OpenGL |
| trimesh | Sectionnement STL |
| shapely | Géométrie 2D des contours |
| ezdxf | Export DXF |

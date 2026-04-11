# =============================================================================
# ui/viewer_3d.py — Widget de visualisation 3D PyVista intégré dans PyQt6
#
# Fonctionnalités :
#   - Affichage STL en mode solide (Phong 3 lumières) ou filaire
#   - Navigation interactive (rotation / zoom / panoramique) via PyVista/VTK
#   - Trièdre XYZ positionné à l'origine du modèle, à l'échelle de la pièce
#   - Widget d'orientation (coin bas-gauche) pour référence de navigation
#   - Plans de coupe semi-transparents (aperçu du sectionnement)
# =============================================================================

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PyQt6.QtWidgets import QWidget, QVBoxLayout


class Viewer3D(QWidget):
    """
    Widget Qt encapsulant le rendu PyVista (VTK/OpenGL).
    S'intègre dans n'importe quel layout PyQt6 comme un widget standard.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Layout sans marges pour maximiser la zone de rendu
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Création du plotter PyVista intégré Qt ---
        self._plotter = QtInteractor(self)
        layout.addWidget(self._plotter)

        # --- État interne ---
        self._mesh_pv = None       # Maillage PyVista courant
        self._mode = 'solid'       # 'solid' ou 'wireframe'

        # --- Configuration initiale du rendu ---
        self._plotter.set_background('#1a1a2e')

        # Widget d'orientation dans le coin (référence de navigation)
        self._plotter.add_axes(
            interactive=False,
            line_width=3,
            xlabel='X', ylabel='Y', zlabel='Z'
        )

    # =========================================================================
    # Méthodes publiques
    # =========================================================================

    def charger_mesh(self, mesh_pv: pv.PolyData):
        """
        Charge et affiche un maillage PyVista dans la vue 3D.
        Configure les lumières et le trièdre selon les dimensions du modèle.

        Paramètres:
            mesh_pv (pv.PolyData) : maillage issu de pv.read()
        """
        self._mesh_pv = mesh_pv
        self._rafraichir_affichage()

    def set_mode_solid(self):
        """Passe en mode rendu solide avec éclairage 3 lumières."""
        self._mode = 'solid'
        self._rafraichir_affichage()

    def set_mode_wireframe(self):
        """Passe en mode filaire (arêtes uniquement)."""
        self._mode = 'wireframe'
        self._rafraichir_affichage()

    def afficher_plans_coupe(self, positions: list, normale: list):
        """
        Ajoute tous les plans de coupe semi-transparents dans la vue 3D
        pour prévisualiser le sectionnement.

        Paramètres:
            positions (list) : positions de coupe en mm
            normale (list)   : vecteur normal, ex. [0, 0, 1] pour Z
        """
        if self._mesh_pv is None or not positions:
            return

        # Réafficher le mesh proprement avant d'ajouter les plans
        self._rafraichir_affichage()

        normale_np = np.array(normale, dtype=float)
        idx_axe = int(np.argmax(np.abs(normale_np)))

        # Dimensions du plan limitées à la boîte englobante du modèle
        # bounds = (xmin, xmax, ymin, ymax, zmin, zmax) dans PyVista
        bounds = self._mesh_pv.bounds
        autres_axes = [j for j in range(3) if j != idx_axe]
        i_size = (bounds[autres_axes[0] * 2 + 1] - bounds[autres_axes[0] * 2]) * 1.02
        j_size = (bounds[autres_axes[1] * 2 + 1] - bounds[autres_axes[1] * 2]) * 1.02
        # Sécurité : taille minimale si la boîte est plate dans un sens
        i_size = max(i_size, 1.0)
        j_size = max(j_size, 1.0)

        for pos in positions:
            # Centre du plan : centre du modèle dans les axes du plan,
            # position de coupe sur l'axe normal
            centre = list(self._mesh_pv.center)
            centre[idx_axe] = float(pos)

            plan = pv.Plane(
                center=centre,
                direction=normale_np,
                i_size=i_size,
                j_size=j_size
            )
            self._plotter.add_mesh(
                plan, color='yellow', opacity=0.22,
                show_edges=False, lighting=False
            )

        self._plotter.render()

    # =========================================================================
    # Méthodes internes
    # =========================================================================

    def _rafraichir_affichage(self):
        """
        Efface la scène et reconstruit le rendu complet :
        lumières, mesh, trièdre à l'origine du modèle.
        """
        if self._mesh_pv is None:
            return

        self._plotter.clear()

        # --- Éclairage : 3 sources positionnées autour du modèle ---
        self._configurer_eclairage()

        # --- Widget d'orientation (coin de la fenêtre) ---
        self._plotter.add_axes(
            interactive=False, line_width=3,
            xlabel='X', ylabel='Y', zlabel='Z'
        )

        # --- Mesh selon le mode ---
        if self._mode == 'wireframe':
            self._plotter.add_mesh(
                self._mesh_pv,
                style='wireframe',
                color='#4FC3F7',
                line_width=1,
                lighting=False
            )
        else:
            # Rendu solide : shading de Phong avec specular/diffuse/ambient
            # opacity < 1 pour laisser apparaître le trièdre à travers la pièce
            self._plotter.add_mesh(
                self._mesh_pv,
                color='#9EC4D8',        # Bleu acier clair
                smooth_shading=True,
                specular=0.9,           # Reflets brillants
                specular_power=60,      # Concentration du reflet (plus = plus net)
                diffuse=0.85,           # Composante diffuse (éclairage lambertien)
                ambient=0.15,           # Lumière ambiante (évite les zones trop noires)
                opacity=0.82,           # Semi-transparent : trièdre visible à travers
                show_edges=False
            )

        # --- Trièdre XYZ à l'origine du modèle ---
        self._ajouter_trihedre()

        # --- Centrage de la caméra ---
        self._plotter.reset_camera()
        self._plotter.render()

    def _configurer_eclairage(self):
        """
        Configure 3 sources lumineuses positionnées autour du modèle :
          - Lumière principale (key light) : blanche, forte, devant-dessus-droite
          - Lumière de remplissage (fill light) : bleue douce, gauche
          - Lumière de contour (rim light) : blanche faible, derrière
        """
        centre = np.array(self._mesh_pv.center)
        d = self._mesh_pv.length  # Diagonale de la boîte englobante

        self._plotter.remove_all_lights()

        # Lumière principale — devant, au-dessus, légèrement à droite
        kl = pv.Light(
            position=tuple(centre + np.array([d * 0.6, d * 0.5, d * 1.0])),
            focal_point=tuple(centre),
            color='white',
            intensity=1.0,
            light_type='scene light'
        )
        self._plotter.add_light(kl)

        # Lumière de remplissage — gauche, légèrement teinée bleu
        fl = pv.Light(
            position=tuple(centre + np.array([-d * 0.8, -d * 0.3, d * 0.4])),
            focal_point=tuple(centre),
            color='#BBCCFF',
            intensity=0.5,
            light_type='scene light'
        )
        self._plotter.add_light(fl)

        # Lumière de contour — derrière/dessous, faible
        rl = pv.Light(
            position=tuple(centre + np.array([0.0, -d * 0.9, -d * 0.5])),
            focal_point=tuple(centre),
            color='white',
            intensity=0.25,
            light_type='scene light'
        )
        self._plotter.add_light(rl)

    def _ajouter_trihedre(self):
        """
        Ajoute un trièdre XYZ 3D à l'ORIGINE DES COORDONNÉES (0, 0, 0),
        qui est l'origine du repère du fichier STL (coordonnées préservées
        à l'import, sans recentrage).

        - Taille des axes : 25 % de la diagonale du modèle
        - Couleurs : rouge=X, vert=Y, bleu=Z
        - Labels X, Y, Z visibles en permanence, fond transparent
        """
        if self._mesh_pv is None:
            return

        # Origine = (0, 0, 0) = origine des coordonnées du fichier STL.
        # trimesh.load() et pv.read() préservent les coordonnées d'origine
        # sans recentrage ni transformation (reset_camera ne déplace pas la géométrie).
        origine = np.array([0.0, 0.0, 0.0])

        # Taille proportionnelle à la pièce pour rester lisible
        taille = self._mesh_pv.length * 0.25   # 25 % de la diagonale

        axes_config = [
            ('X', np.array([1.0, 0.0, 0.0]), 'red'),
            ('Y', np.array([0.0, 1.0, 0.0]), 'lime'),
            ('Z', np.array([0.0, 0.0, 1.0]), '#4499FF'),
        ]

        for label, direction, couleur in axes_config:
            # Flèche : départ à l'origine, pointe dans la direction × taille
            fleche = pv.Arrow(
                start=origine,
                direction=direction,
                tip_length=0.22,
                tip_radius=0.07,
                shaft_radius=0.022,
                scale=taille
            )
            self._plotter.add_mesh(fleche, color=couleur, lighting=False)

            # Label au bout de la flèche — fond TRANSPARENT (shape_opacity=0)
            pos_label = origine + direction * taille * 1.18
            self._plotter.add_point_labels(
                [pos_label.tolist()],
                [label],
                font_size=18,
                text_color=couleur,
                bold=True,
                show_points=False,
                always_visible=True,
                shadow=True,
                shape_opacity=0.0,   # fond entièrement transparent
                fill_shape=False     # pas de remplissage de la forme de fond
            )

    def closeEvent(self, event):
        """Fermeture propre : libère le contexte OpenGL VTK."""
        self._plotter.close()
        super().closeEvent(event)

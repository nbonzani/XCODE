# =============================================================================
# ui/main_window.py — Fenêtre principale de l'application STL Slicer
#
# Architecture de l'interface :
#   ┌─────────────────────────────────────────────────────────────────┐
#   │ Barre de menus                                                  │
#   ├──────────────────┬──────────────────────────────────────────────┤
#   │                  │  [Onglet Vue 3D]   [Onglet Nesting]         │
#   │  Panel de        │                                              │
#   │  contrôle        │         Zone de visualisation                │
#   │  (gauche fixe)   │         (occupe toute la droite)             │
#   │                  │                                              │
#   └──────────────────┴──────────────────────────────────────────────┘
#   │ Barre de statut                                                 │
#   └─────────────────────────────────────────────────────────────────┘
# =============================================================================

import os
import time

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QDoubleSpinBox,
    QFileDialog, QGroupBox, QSplitter, QMessageBox,
    QProgressBar, QTabWidget, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QSettings
from PyQt6.QtGui import QAction, QPalette, QColor

from core.stl_loader import charger_stl, obtenir_dimensions
from core.slicer import calculer_sections, obtenir_positions_coupes
from core.nesting import (calculer_nesting, calculer_nesting_optimise,
                          calculer_surface_utilisee, calculer_bbox_placements)
from core.exporter import exporter_toutes_sections, exporter_nesting_dxf
from ui.viewer_3d import Viewer3D
from ui.nesting_view import NestingView


# =============================================================================
# Thread de calcul — Sectionnement (opération longue, ne pas bloquer l'UI)
# =============================================================================

class ThreadSlicing(QThread):
    """
    Lance le calcul des sections dans un thread séparé pour ne pas
    geler l'interface pendant le traitement (qui peut durer plusieurs secondes
    sur des maillages complexes).
    """
    # Signal émis quand le calcul est terminé avec succès
    termine = pyqtSignal(list)
    # Signal émis en cas d'erreur
    erreur = pyqtSignal(str)
    # Signal de progression (section_courante, total)
    progression = pyqtSignal(int, int)

    def __init__(self, mesh, axe: str, epaisseur: float, offset: float = 0.0):
        super().__init__()
        self.mesh = mesh
        self.axe = axe
        self.epaisseur = epaisseur
        self.offset = offset

    def run(self):
        """Méthode exécutée dans le thread secondaire."""
        try:
            sections = calculer_sections(
                self.mesh,
                self.axe,
                self.epaisseur,
                offset=self.offset,
                callback_progression=lambda i, n: self.progression.emit(i, n)
            )
            self.termine.emit(sections)
        except Exception as e:
            self.erreur.emit(str(e))


# =============================================================================
# Thread de calcul — Nesting optimisé (peut durer plusieurs secondes)
# =============================================================================

class ThreadNesting(QThread):
    """
    Lance le nesting optimisé dans un thread séparé pour ne pas bloquer l'UI.
    Le nesting optimisé (BL+Rotation) peut prendre plusieurs secondes selon
    le nombre de pièces et les rotations testées.
    """
    termine   = pyqtSignal(list, bool)   # (placements, tous_places)
    erreur    = pyqtSignal(str)
    progression = pyqtSignal(int, int)   # (etape_courante, total)

    def __init__(self, polygones, largeur, hauteur, espacement, methode='multi'):
        super().__init__()
        self._polygones  = polygones
        self._largeur    = largeur
        self._hauteur    = hauteur
        self._espacement = espacement
        self._methode    = methode

    def run(self):
        try:
            placements, tous_places = calculer_nesting_optimise(
                self._polygones, self._largeur, self._hauteur, self._espacement,
                callback_progression=lambda i, n: self.progression.emit(i, n),
                methode=self._methode
            )
            self.termine.emit(placements, tous_places)
        except Exception as e:
            self.erreur.emit(str(e))


# =============================================================================
# Thread de calcul — Nesting sparrow (bloquant, sans callback de progression)
# =============================================================================

class ThreadNestingSparrow(QThread):
    """
    Lance le nesting sparrow avec affichage des solutions intermédiaires.

    Architecture :
      - solve() tourne dans un thread daemon Python (non bloquant pour le QThread)
      - Le QThread poll queue.drain() toutes les 400 ms via msleep()
      - Chaque solution intermédiaire est émise via le signal `intermediaire`
      - arreter() stoppe le polling ; le thread daemon finit seul (time_limit_s)
    """
    termine       = pyqtSignal(list, bool)           # résultat final
    erreur        = pyqtSignal(str)
    intermediaire = pyqtSignal(list, bool, float)    # placements, tous_places, densité

    def __init__(self, polygones, largeur, hauteur, espacement,
                 angles, time_limit_s, num_workers):
        super().__init__()
        self._polygones   = polygones
        self._largeur     = largeur
        self._hauteur     = hauteur
        self._espacement  = espacement
        self._angles      = angles
        self._time_limit  = time_limit_s
        self._num_workers = num_workers
        self._stop_demand = False

    def arreter(self):
        """Demande l'arrêt anticipé du polling (le solve() daemon finit seul)."""
        self._stop_demand = True

    def run(self):
        import threading

        try:
            import spyrrow
        except ImportError:
            self.erreur.emit(
                "spyrrow non installé.\nInstallez-la avec : pip install spyrrow"
            )
            return

        try:
            from core.nesting_sparrow import preparer_metas, placer_depuis_solution

            metas = preparer_metas(self._polygones)
            items = [
                spyrrow.Item(f"p{m['idx_orig']}", m['coords'],
                             demand=1, allowed_orientations=self._angles)
                for m in metas
            ]

            instance = spyrrow.StripPackingInstance(
                "stl_slicer_nesting",
                strip_height=self._hauteur,
                items=items
            )
            config = spyrrow.StripPackingConfig(
                early_termination=True,
                total_computation_time=self._time_limit,
                min_items_separation=self._espacement if self._espacement > 0 else None,
                num_workers=self._num_workers if self._num_workers > 0 else None,
                seed=42
            )

            queue = spyrrow.ProgressQueue()
            result_holder = [None, None]   # [solution, exception]

            def _do_solve():
                try:
                    result_holder[0] = instance.solve(config, progress=queue)
                except Exception as ex:
                    result_holder[1] = ex

            solve_thread = threading.Thread(target=_do_solve, daemon=True)
            solve_thread.start()

            # Polling des solutions intermédiaires
            while solve_thread.is_alive() and not self._stop_demand:
                for _report_type, solution in queue.drain():
                    placements, tous_places = placer_depuis_solution(
                        solution.placed_items, metas,
                        self._largeur, self._hauteur
                    )
                    self.intermediaire.emit(
                        placements, tous_places, float(solution.density)
                    )
                self.msleep(400)

            if self._stop_demand:
                # L'utilisateur a demandé l'arrêt — les placements intermédiaires
                # sont déjà affichés dans la vue ; on n'émet pas termine.
                return

            # Attendre la fin naturelle du solve (devrait être immédiate ici)
            solve_thread.join(timeout=10)

            if result_holder[1] is not None:
                self.erreur.emit(str(result_holder[1]))
                return

            if result_holder[0] is not None:
                placements, tous_places = placer_depuis_solution(
                    result_holder[0].placed_items, metas,
                    self._largeur, self._hauteur
                )
                self.termine.emit(placements, tous_places)

        except Exception as e:
            self.erreur.emit(str(e))


# =============================================================================
# Fenêtre principale
# =============================================================================

class MainWindow(QMainWindow):
    """Fenêtre principale de l'application STL Slicer."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("STL Slicer — Découpe Laser")
        self.setMinimumSize(1100, 720)
        self.resize(1400, 850)

        # --- Données de l'application ---
        self._mesh_trimesh = None    # Maillage trimesh (pour le sectionnement)
        self._mesh_pyvista = None    # Maillage PyVista (pour la 3D)
        self._sections = []          # [(position_mm, [polygones]), ...]
        self._placements = []        # [(poly_place, ox, oy, idx), ...]
        self._nb_non_places = 0
        self._thread_slicing         = None
        self._thread_nesting         = None
        self._thread_nesting_sparrow = None
        self._methode_nesting        = 'multi'
        self._nesting_sparrow_debut   = 0.0
        self._nesting_sparrow_limite  = 60
        self._meilleure_solution_sparrow      = []   # placements avec score bbox minimal
        self._meilleure_score_sparrow         = float('inf')

        # Timer de progression pour nesting sparrow (1 tick/s)
        self._timer_nesting_sparrow = QTimer(self)
        self._timer_nesting_sparrow.setInterval(500)   # 500 ms
        self._timer_nesting_sparrow.timeout.connect(self._tick_progression_sparrow)

        # --- Construction de l'interface ---
        self._appliquer_theme_sombre()
        self._construire_interface()
        self._construire_menus()

        self.statusBar().showMessage("Bienvenue — Ouvrez un fichier STL pour commencer.")

    # =========================================================================
    # Thème
    # =========================================================================

    def _appliquer_theme_sombre(self):
        """Applique une palette sombre et augmente la police de l'interface."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor('#2b2b2b'))
        palette.setColor(QPalette.ColorRole.WindowText, QColor('#dddddd'))
        palette.setColor(QPalette.ColorRole.Base, QColor('#1e1e1e'))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor('#353535'))
        palette.setColor(QPalette.ColorRole.Text, QColor('#dddddd'))
        palette.setColor(QPalette.ColorRole.Button, QColor('#3c3c3c'))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor('#dddddd'))
        palette.setColor(QPalette.ColorRole.Highlight, QColor('#4FC3F7'))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor('#000000'))
        self.setPalette(palette)

        # Police plus lisible pour tous les widgets du panel
        self.setStyleSheet("""
            QWidget        { font-size: 13px; }
            QPushButton    { font-size: 13px; padding: 5px 10px; }
            QGroupBox      { font-size: 13px; font-weight: bold; padding-top: 10px; }
            QLabel         { font-size: 13px; }
            QComboBox      { font-size: 13px; padding: 3px 6px; }
            QDoubleSpinBox { font-size: 13px; padding: 3px 4px; }
            QTabBar::tab   { font-size: 13px; padding: 6px 14px; }
            QMenuBar       { font-size: 13px; }
            QMenu          { font-size: 13px; }
            QStatusBar     { font-size: 12px; }
        """)

    # =========================================================================
    # Menus
    # =========================================================================

    def _construire_menus(self):
        """Construit la barre de menus."""
        menubar = self.menuBar()

        # --- Menu Fichier ---
        menu_fichier = menubar.addMenu("Fichier")

        action_ouvrir = QAction("Ouvrir un STL...", self)
        action_ouvrir.setShortcut("Ctrl+O")
        action_ouvrir.triggered.connect(self._ouvrir_stl)
        menu_fichier.addAction(action_ouvrir)

        # Sous-menu fichiers récents (peuplé dynamiquement)
        self._menu_recents = menu_fichier.addMenu("Fichiers récents")
        self._mettre_a_jour_menu_recents()

        menu_fichier.addSeparator()

        action_quitter = QAction("Quitter", self)
        action_quitter.setShortcut("Ctrl+Q")
        action_quitter.triggered.connect(self.close)
        menu_fichier.addAction(action_quitter)

        # --- Menu Exporter ---
        menu_export = menubar.addMenu("Exporter")

        self._action_export_sections = QAction(
            "Exporter toutes les sections (DXF individuels)...", self)
        self._action_export_sections.setEnabled(False)
        self._action_export_sections.triggered.connect(self._exporter_sections)
        menu_export.addAction(self._action_export_sections)

        self._action_export_nesting = QAction(
            "Exporter le nesting complet (un seul DXF)...", self)
        self._action_export_nesting.setEnabled(False)
        self._action_export_nesting.triggered.connect(self._exporter_nesting)
        menu_export.addAction(self._action_export_nesting)

        # --- Menu Aide ---
        menu_aide = menubar.addMenu("Aide")
        action_apropos = QAction("À propos", self)
        action_apropos.triggered.connect(self._afficher_apropos)
        menu_aide.addAction(action_apropos)

    # =========================================================================
    # Fichiers récents
    # =========================================================================

    _RECENTS_KEY = 'recent_files'
    _RECENTS_MAX = 10

    def _lire_recents(self) -> list:
        """Lit la liste des fichiers récents depuis QSettings."""
        s = QSettings('PolytechNancy', 'STLSlicer')
        recents = s.value(self._RECENTS_KEY, [])
        # QSettings retourne parfois une str au lieu d'une list si 1 seul élément
        if isinstance(recents, str):
            recents = [recents]
        return [r for r in recents if os.path.isfile(r)]  # ignorer les fichiers supprimés

    def _sauvegarder_recent(self, chemin: str):
        """Ajoute chemin en tête de l'historique (max 10 entrées) et rafraîchit le menu."""
        s = QSettings('PolytechNancy', 'STLSlicer')
        recents = self._lire_recents()
        if chemin in recents:
            recents.remove(chemin)
        recents.insert(0, chemin)
        recents = recents[:self._RECENTS_MAX]
        s.setValue(self._RECENTS_KEY, recents)
        self._mettre_a_jour_menu_recents()

    def _mettre_a_jour_menu_recents(self):
        """Reconstruit le sous-menu 'Fichiers récents'."""
        self._menu_recents.clear()
        recents = self._lire_recents()

        if not recents:
            vide = QAction("(aucun fichier récent)", self)
            vide.setEnabled(False)
            self._menu_recents.addAction(vide)
            return

        for i, chemin in enumerate(recents):
            # Numéro de raccourci 1-9 pour les 9 premiers
            raccourci = f"&{i + 1}  " if i < 9 else "   "
            nom = os.path.basename(chemin)
            action = QAction(f"{raccourci}{nom}", self)
            action.setToolTip(chemin)
            # Capturer chemin dans la lambda avec la valeur actuelle (c=chemin)
            action.triggered.connect(lambda checked=False, c=chemin: self._ouvrir_stl_chemin(c))
            self._menu_recents.addAction(action)

        self._menu_recents.addSeparator()
        action_effacer = QAction("Effacer l'historique", self)
        action_effacer.triggered.connect(self._effacer_recents)
        self._menu_recents.addAction(action_effacer)

    def _effacer_recents(self):
        """Vide l'historique des fichiers récents."""
        QSettings('PolytechNancy', 'STLSlicer').remove(self._RECENTS_KEY)
        self._mettre_a_jour_menu_recents()
        self.statusBar().showMessage("Historique des fichiers récents effacé.")

    # =========================================================================
    # Persistance des paramètres utilisateur
    # =========================================================================

    def _sauvegarder_parametres(self, _valeur=None):
        """
        Enregistre dans QSettings les valeurs courantes de tous les paramètres
        modifiables. Appelé automatiquement à chaque changement de valeur.
        Le paramètre _valeur est ignoré (il est passé par les signaux Qt).
        """
        s = QSettings('PolytechNancy', 'STLSlicer')
        s.setValue('param/axe_index',  self._combo_axe.currentIndex())
        s.setValue('param/epaisseur',  self._spin_epaisseur.value())
        s.setValue('param/offset',     self._spin_offset.value())
        s.setValue('param/larg_plaque', self._spin_larg.value())
        s.setValue('param/haut_plaque', self._spin_haut.value())
        s.setValue('param/espacement',  self._spin_esp.value())

    def _charger_parametres(self):
        """
        Restaure depuis QSettings les paramètres sauvegardés lors de la
        session précédente. Appelé une fois après la construction des widgets,
        dans _construire_interface(). Les signaux sont temporairement bloqués
        pour éviter des sauvegardes en cascade pendant l'initialisation.
        """
        s = QSettings('PolytechNancy', 'STLSlicer')

        # Bloquer les signaux pour éviter les appels à _sauvegarder_parametres
        widgets = [
            self._combo_axe, self._spin_epaisseur, self._spin_offset,
            self._spin_larg, self._spin_haut, self._spin_esp
        ]
        for w in widgets:
            w.blockSignals(True)

        try:
            idx = s.value('param/axe_index', None)
            if idx is not None:
                self._combo_axe.setCurrentIndex(int(idx))

            ep = s.value('param/epaisseur', None)
            if ep is not None:
                self._spin_epaisseur.setValue(float(ep))

            off = s.value('param/offset', None)
            if off is not None:
                self._spin_offset.setValue(float(off))

            larg = s.value('param/larg_plaque', None)
            if larg is not None:
                self._spin_larg.setValue(float(larg))

            haut = s.value('param/haut_plaque', None)
            if haut is not None:
                self._spin_haut.setValue(float(haut))

            esp = s.value('param/espacement', None)
            if esp is not None:
                self._spin_esp.setValue(float(esp))
        finally:
            for w in widgets:
                w.blockSignals(False)

    # =========================================================================
    # Interface principale
    # =========================================================================

    def _construire_interface(self):
        """Construit le layout principal avec splitter horizontal."""
        widget_central = QWidget()
        self.setCentralWidget(widget_central)
        layout_racine = QHBoxLayout(widget_central)
        layout_racine.setContentsMargins(4, 4, 4, 4)
        layout_racine.setSpacing(4)

        # Splitter : panel gauche | zone 3D/nesting droite
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout_racine.addWidget(splitter)

        # ⚠️ Les vues doivent être créées EN PREMIER car le panel de contrôle
        # (_groupe_affichage) y connecte des signaux dès sa construction.
        self._tabs = QTabWidget()
        self._viewer3d = Viewer3D()
        self._tabs.addTab(self._viewer3d, "Vue 3D")
        self._nesting_view = NestingView()
        self._tabs.addTab(self._nesting_view, "Plan de nesting")

        # Panel de contrôle scrollable (créé après les vues)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(280)
        scroll.setMaximumWidth(600)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self._creer_panel_controle())
        splitter.addWidget(scroll)

        splitter.addWidget(self._tabs)

        splitter.setSizes([300, 800])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # Restaurer les paramètres de la session précédente
        self._charger_parametres()

    def _creer_panel_controle(self) -> QWidget:
        """Crée le panel de contrôle gauche avec tous les groupes."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(8)
        layout.setContentsMargins(6, 6, 6, 6)

        layout.addWidget(self._groupe_fichier())
        layout.addWidget(self._groupe_affichage())
        layout.addWidget(self._groupe_slicing())
        layout.addWidget(self._groupe_nesting())
        layout.addWidget(self._groupe_export())
        layout.addStretch()

        return widget

    # -------------------------------------------------------------------------
    # Groupes du panel
    # -------------------------------------------------------------------------

    def _groupe_fichier(self) -> QGroupBox:
        """Groupe : chargement du fichier STL."""
        groupe = QGroupBox("Fichier STL")
        layout = QVBoxLayout(groupe)

        self._lbl_fichier = QLabel("Aucun fichier chargé")
        self._lbl_fichier.setWordWrap(True)
        self._lbl_fichier.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(self._lbl_fichier)

        btn = QPushButton("Ouvrir un fichier STL...")
        btn.clicked.connect(self._ouvrir_stl)
        layout.addWidget(btn)

        self._lbl_info_mesh = QLabel("")
        self._lbl_info_mesh.setWordWrap(True)
        self._lbl_info_mesh.setStyleSheet("font-size: 10px; color: #aaaaaa;")
        layout.addWidget(self._lbl_info_mesh)

        return groupe

    def _groupe_affichage(self) -> QGroupBox:
        """Groupe : mode d'affichage 3D."""
        groupe = QGroupBox("Affichage 3D")
        layout = QHBoxLayout(groupe)

        btn_solid = QPushButton("Solide")
        btn_solid.setToolTip("Rendu solide avec éclairage")
        btn_solid.clicked.connect(self._viewer3d.set_mode_solid)
        layout.addWidget(btn_solid)

        btn_wire = QPushButton("Filaire")
        btn_wire.setToolTip("Affichage des arêtes uniquement")
        btn_wire.clicked.connect(self._viewer3d.set_mode_wireframe)
        layout.addWidget(btn_wire)

        return groupe

    def _groupe_slicing(self) -> QGroupBox:
        """Groupe : paramètres de sectionnement."""
        groupe = QGroupBox("Sectionnement")
        layout = QVBoxLayout(groupe)

        # Axe de coupe
        row_axe = QHBoxLayout()
        row_axe.addWidget(QLabel("Axe de coupe :"))
        self._combo_axe = QComboBox()
        self._combo_axe.addItems(["Z  (coupe horizontale)", "X  (coupe sagittale)", "Y  (coupe frontale)"])
        self._combo_axe.currentIndexChanged.connect(self._mettre_a_jour_apercu_tranches)
        self._combo_axe.currentIndexChanged.connect(self._sauvegarder_parametres)
        row_axe.addWidget(self._combo_axe)
        layout.addLayout(row_axe)

        # Épaisseur
        row_ep = QHBoxLayout()
        row_ep.addWidget(QLabel("Épaisseur (mm) :"))
        self._spin_epaisseur = QDoubleSpinBox()
        self._spin_epaisseur.setRange(0.1, 500.0)
        self._spin_epaisseur.setValue(3.0)
        self._spin_epaisseur.setSingleStep(0.5)
        self._spin_epaisseur.setSuffix(" mm")
        self._spin_epaisseur.setDecimals(2)
        self._spin_epaisseur.valueChanged.connect(self._mettre_a_jour_apercu_tranches)
        self._spin_epaisseur.valueChanged.connect(self._sauvegarder_parametres)
        row_ep.addWidget(self._spin_epaisseur)
        layout.addLayout(row_ep)

        # Décalage (offset) des plans de coupe
        row_off = QHBoxLayout()
        lbl_off = QLabel("Décalage coupes :")
        lbl_off.setToolTip(
            "Décale la grille de coupes dans la direction choisie.\n"
            "0 mm = premier plan passant par l'origine du trièdre (0, 0, 0).\n"
            "5 mm = premier plan à 5 mm de l'origine, puis ±épaisseur, ±2×épaisseur..."
        )
        row_off.addWidget(lbl_off)
        self._spin_offset = QDoubleSpinBox()
        self._spin_offset.setRange(-500.0, 500.0)
        self._spin_offset.setValue(0.0)
        self._spin_offset.setSingleStep(0.5)
        self._spin_offset.setSuffix(" mm")
        self._spin_offset.setDecimals(2)
        self._spin_offset.setToolTip(lbl_off.toolTip())
        self._spin_offset.valueChanged.connect(self._mettre_a_jour_apercu_tranches)
        self._spin_offset.valueChanged.connect(self._sauvegarder_parametres)
        row_off.addWidget(self._spin_offset)
        layout.addLayout(row_off)

        # Aperçu du nombre de tranches
        self._lbl_apercu_tranches = QLabel("Tranches estimées : —")
        self._lbl_apercu_tranches.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(self._lbl_apercu_tranches)

        # Bouton calcul
        self._btn_slicer = QPushButton("Calculer les sections")
        self._btn_slicer.setEnabled(False)
        self._btn_slicer.clicked.connect(self._lancer_slicing)
        layout.addWidget(self._btn_slicer)

        # Résultat
        self._lbl_sections = QLabel("Résultat : —")
        self._lbl_sections.setWordWrap(True)
        self._lbl_sections.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(self._lbl_sections)

        # Barre de progression
        self._barre = QProgressBar()
        self._barre.setVisible(False)
        self._barre.setTextVisible(True)
        layout.addWidget(self._barre)

        return groupe

    def _groupe_nesting(self) -> QGroupBox:
        """Groupe : paramètres du nesting."""
        groupe = QGroupBox("Nesting (répartition plaque)")
        layout = QVBoxLayout(groupe)

        # --- Mode de nesting ---
        r_mode = QHBoxLayout()
        r_mode.addWidget(QLabel("Mode :"))
        self._combo_nesting_mode = QComboBox()
        self._combo_nesting_mode.addItems([
            "Simple  (sans rotation)",
            "Optimisé — Aire décroissante",
            "Optimisé — Périmètre décroissant",
            "Optimisé — Dim. max. décroissante",
            "Optimisé — Multi-séquençage",
            "Sparrow — Moyenne  (45°, 1 min)",
            "Sparrow — Maxi  (1°, 10 min)",
        ])
        self._combo_nesting_mode.setToolTip(
            "Simple : placement en rangées, sans rotation.\n"
            "Optimisé : Bottom-Left Fill + 12 rotations, minimise la boîte englobante.\n"
            "  • Aire / Périmètre / Dim. max. : 1 séquence de tri, calcul rapide.\n"
            "  • Multi-séquençage : essaie 4 ordres de tri, retient le meilleur résultat.\n"
            "Sparrow : algorithme mondial 2025 (Gardeyn et al., EJOR). Nécessite spyrrow.\n"
            "  • Moyenne : 8 rotations (0°→315° par 45°), 1 minute max.\n"
            "  • Maxi : 360 rotations (1° par 1°), 10 minutes max, 80 % des CPU."
        )
        r_mode.addWidget(self._combo_nesting_mode)
        layout.addLayout(r_mode)

        # Largeur plaque
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Largeur plaque :"))
        self._spin_larg = QDoubleSpinBox()
        self._spin_larg.setRange(10, 10000)
        self._spin_larg.setValue(600.0)
        self._spin_larg.setSuffix(" mm")
        self._spin_larg.setDecimals(1)
        self._spin_larg.valueChanged.connect(self._sauvegarder_parametres)
        r1.addWidget(self._spin_larg)
        layout.addLayout(r1)

        # Hauteur plaque
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Hauteur plaque :"))
        self._spin_haut = QDoubleSpinBox()
        self._spin_haut.setRange(10, 10000)
        self._spin_haut.setValue(400.0)
        self._spin_haut.setSuffix(" mm")
        self._spin_haut.setDecimals(1)
        self._spin_haut.valueChanged.connect(self._sauvegarder_parametres)
        r2.addWidget(self._spin_haut)
        layout.addLayout(r2)

        # Espacement
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Espacement :"))
        self._spin_esp = QDoubleSpinBox()
        self._spin_esp.setRange(0, 100)
        self._spin_esp.setValue(5.0)
        self._spin_esp.setSuffix(" mm")
        self._spin_esp.setDecimals(1)
        self._spin_esp.valueChanged.connect(self._sauvegarder_parametres)
        self._spin_esp.valueChanged.connect(self._nesting_view.definir_espacement)
        r3.addWidget(self._spin_esp)
        layout.addLayout(r3)

        self._btn_nesting = QPushButton("Calculer le nesting")
        self._btn_nesting.setEnabled(False)
        self._btn_nesting.clicked.connect(self._lancer_nesting)
        layout.addWidget(self._btn_nesting)

        self._barre_nesting = QProgressBar()
        self._barre_nesting.setVisible(False)
        self._barre_nesting.setTextVisible(True)
        layout.addWidget(self._barre_nesting)

        self._btn_stop_sparrow = QPushButton("⏹  Arrêter le calcul")
        self._btn_stop_sparrow.setVisible(False)
        self._btn_stop_sparrow.setStyleSheet(
            "QPushButton { background-color: #7f1d1d; color: #fecaca; "
            "border: 1px solid #ef4444; border-radius: 4px; padding: 4px; }"
            "QPushButton:hover { background-color: #991b1b; }"
        )
        self._btn_stop_sparrow.clicked.connect(self._stopper_nesting_sparrow)
        layout.addWidget(self._btn_stop_sparrow)

        self._lbl_nesting_info = QLabel("")
        self._lbl_nesting_info.setWordWrap(True)
        self._lbl_nesting_info.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(self._lbl_nesting_info)

        return groupe

    def _groupe_export(self) -> QGroupBox:
        """Groupe : export DXF."""
        groupe = QGroupBox("Export DXF")
        layout = QVBoxLayout(groupe)

        self._btn_exp_sections = QPushButton("Exporter sections individuelles...")
        self._btn_exp_sections.setEnabled(False)
        self._btn_exp_sections.setToolTip(
            "Crée un fichier DXF par tranche (section_001.dxf, section_002.dxf, ...)"
        )
        self._btn_exp_sections.clicked.connect(self._exporter_sections)
        layout.addWidget(self._btn_exp_sections)

        self._btn_exp_nesting = QPushButton("Exporter nesting complet...")
        self._btn_exp_nesting.setEnabled(False)
        self._btn_exp_nesting.setToolTip(
            "Crée un seul fichier DXF avec toutes les sections sur la plaque"
        )
        self._btn_exp_nesting.clicked.connect(self._exporter_nesting)
        layout.addWidget(self._btn_exp_nesting)

        return groupe

    # =========================================================================
    # Actions : Fichier
    # =========================================================================

    def _ouvrir_stl(self):
        """Ouvre un fichier STL via la boîte de dialogue système."""
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un fichier STL", "",
            "Fichiers STL (*.stl);;Tous les fichiers (*.*)"
        )
        if chemin:
            self._ouvrir_stl_chemin(chemin)

    def _ouvrir_stl_chemin(self, chemin: str):
        """
        Charge le fichier STL depuis chemin (appelé par le dialogue ou
        par le menu 'Fichiers récents').
        """
        if not os.path.isfile(chemin):
            QMessageBox.warning(self, "Fichier introuvable",
                                f"Le fichier n'existe plus :\n{chemin}")
            self._mettre_a_jour_menu_recents()
            return

        self.statusBar().showMessage(f"Chargement de {os.path.basename(chemin)}...")
        self.repaint()

        try:
            self._mesh_trimesh, self._mesh_pyvista = charger_stl(chemin)
            self._fichier_stl = chemin

            # Affichage 3D
            self._viewer3d.charger_mesh(self._mesh_pyvista)

            # Informations dimensionnelles
            info = obtenir_dimensions(self._mesh_trimesh)
            dim = info['dimensions']
            vol_txt = (f"{info['volume']:.1f} mm³" if info['volume'] is not None
                       else "N/A (maillage ouvert)")
            self._lbl_fichier.setText(os.path.basename(chemin))
            self._lbl_fichier.setStyleSheet("color: #4FC3F7; font-weight: bold;")
            self._lbl_info_mesh.setText(
                f"X : {dim[0]:.2f} mm\n"
                f"Y : {dim[1]:.2f} mm\n"
                f"Z : {dim[2]:.2f} mm\n"
                f"Triangles : {info['nb_faces']:,}\n"
                f"Volume : {vol_txt}"
            )

            # Réinitialiser les résultats précédents
            self._sections = []
            self._placements = []
            self._nb_non_places = 0
            self._lbl_sections.setText("Résultat : —")
            self._lbl_nesting_info.setText("")
            self._nesting_view.effacer()

            # Activer les contrôles
            self._btn_slicer.setEnabled(True)
            self._btn_nesting.setEnabled(False)
            self._btn_exp_sections.setEnabled(False)
            self._btn_exp_nesting.setEnabled(False)
            self._action_export_sections.setEnabled(False)
            self._action_export_nesting.setEnabled(False)

            # Mettre à jour l'aperçu du nombre de tranches
            self._mettre_a_jour_apercu_tranches()

            # Sauvegarder dans l'historique et rafraîchir le menu
            self._sauvegarder_recent(chemin)

            self.statusBar().showMessage(
                f"Chargé : {os.path.basename(chemin)}  "
                f"({dim[0]:.1f} × {dim[1]:.1f} × {dim[2]:.1f} mm)"
            )

        except RuntimeError as e:
            QMessageBox.critical(self, "Erreur de chargement", str(e))
            self.statusBar().showMessage("Erreur lors du chargement du fichier.")

    # =========================================================================
    # Actions : Sectionnement
    # =========================================================================

    def _axe_selectionne(self) -> str:
        """Retourne la lettre de l'axe sélectionné : 'X', 'Y' ou 'Z'."""
        texte = self._combo_axe.currentText()
        return texte[0]  # Premier caractère : 'Z', 'X' ou 'Y'

    def _mettre_a_jour_apercu_tranches(self):
        """Calcule et affiche le nombre de tranches estimé sans lancer le calcul."""
        if self._mesh_trimesh is None:
            self._lbl_apercu_tranches.setText("Tranches estimées : —")
            return
        try:
            _positions, nb = obtenir_positions_coupes(
                self._mesh_trimesh,
                self._axe_selectionne(),
                self._spin_epaisseur.value(),
                offset=self._spin_offset.value()
            )
            self._lbl_apercu_tranches.setText(f"Tranches estimées : {nb}")
        except Exception:
            self._lbl_apercu_tranches.setText("Tranches estimées : —")

    def _lancer_slicing(self):
        """Lance le calcul des sections dans un thread secondaire."""
        if self._mesh_trimesh is None:
            return

        axe = self._axe_selectionne()
        epaisseur = self._spin_epaisseur.value()
        offset = self._spin_offset.value()

        # Verrouiller l'UI pendant le calcul
        self._btn_slicer.setEnabled(False)
        self._btn_slicer.setText("Calcul en cours...")
        self._barre.setVisible(True)
        self._barre.setRange(0, 0)   # Mode indéterminé (animation)
        self.statusBar().showMessage("Calcul des sections en cours...")

        # Lancer dans un thread pour ne pas bloquer l'interface
        self._thread_slicing = ThreadSlicing(
            self._mesh_trimesh, axe, epaisseur, offset
        )
        self._thread_slicing.termine.connect(self._slicing_termine)
        self._thread_slicing.erreur.connect(self._slicing_erreur)
        self._thread_slicing.progression.connect(self._slicing_progression)
        self._thread_slicing.start()

    def _slicing_progression(self, courant: int, total: int):
        """Met à jour la barre de progression pendant le sectionnement."""
        if self._barre.maximum() == 0 and total > 0:
            self._barre.setRange(0, total)
        self._barre.setValue(courant)

    def _slicing_termine(self, sections: list):
        """Appelé quand le sectionnement s'est terminé avec succès."""
        self._sections = sections

        # Restaurer les contrôles
        self._btn_slicer.setEnabled(True)
        self._btn_slicer.setText("Calculer les sections")
        self._barre.setVisible(False)

        nb_sections = len(sections)
        nb_contours = sum(len(polys) for _, polys in sections)

        if nb_sections == 0:
            self._lbl_sections.setText(
                "Résultat : aucune section trouvée.\n"
                "(Vérifiez l'axe de coupe et l'épaisseur.)"
            )
            self.statusBar().showMessage("Sectionnement terminé : aucune section générée.")
            return

        self._lbl_sections.setText(
            f"Résultat : {nb_sections} sections\n"
            f"{nb_contours} contour(s) au total"
        )

        # Afficher les plans de coupe dans la vue 3D.
        # On utilise les positions de la GRILLE complète (pas seulement là où une
        # section valide existe) afin que le plan à x=offset soit toujours visible,
        # même si trimesh n'a pas produit de polygone à cette position (face du modèle).
        axe = self._axe_selectionne()
        normales = {'X': [1, 0, 0], 'Y': [0, 1, 0], 'Z': [0, 0, 1]}
        positions_grille, _ = obtenir_positions_coupes(
            self._mesh_trimesh, axe,
            self._spin_epaisseur.value(),
            offset=self._spin_offset.value()
        )
        self._viewer3d.afficher_plans_coupe(list(positions_grille), normales[axe])

        # Activer le nesting et l'export sections
        self._btn_nesting.setEnabled(True)
        self._btn_exp_sections.setEnabled(True)
        self._action_export_sections.setEnabled(True)

        self.statusBar().showMessage(
            f"Sectionnement terminé : {nb_sections} sections, {nb_contours} contours."
        )

    def _slicing_erreur(self, message: str):
        """Appelé en cas d'erreur pendant le sectionnement."""
        self._btn_slicer.setEnabled(True)
        self._btn_slicer.setText("Calculer les sections")
        self._barre.setVisible(False)
        QMessageBox.critical(self, "Erreur de sectionnement", message)
        self.statusBar().showMessage("Erreur lors du sectionnement.")

    # =========================================================================
    # Actions : Nesting
    # =========================================================================

    # =========================================================================
    # Actions : Nesting
    # =========================================================================

    # Correspondance index combo → methode calculer_nesting_optimise
    _METHODES_NESTING = {1: 'aire', 2: 'perimetre', 3: 'dim_max', 4: 'multi'}

    def _lancer_nesting(self):
        """Dispatche vers le nesting simple, optimisé ou sparrow selon le mode choisi."""
        if not self._sections:
            return
        idx = self._combo_nesting_mode.currentIndex()
        if idx == 0:
            self._lancer_nesting_simple()
        elif idx in self._METHODES_NESTING:
            self._lancer_nesting_optimise(self._METHODES_NESTING[idx])
        elif idx == 5:
            self._lancer_nesting_sparrow('sparrow_moy')
        elif idx == 6:
            self._lancer_nesting_sparrow('sparrow_max')

    def _rassembler_polygones(self) -> list:
        """Collecte tous les polygones de toutes les sections."""
        polys = []
        for _pos, polygones in self._sections:
            polys.extend(polygones)
        return polys

    def _lancer_nesting_simple(self):
        """Nesting simple (rangées, sans rotation) — synchrone, immédiat."""
        tous_polygones = self._rassembler_polygones()
        if not tous_polygones:
            QMessageBox.warning(self, "Nesting", "Aucun contour à placer.")
            return

        largeur   = self._spin_larg.value()
        hauteur   = self._spin_haut.value()
        espacement = self._spin_esp.value()

        try:
            placements, tous_places = calculer_nesting(
                tous_polygones, largeur, hauteur, espacement
            )
            self._nesting_termine(placements, tous_places,
                                  len(tous_polygones), largeur, hauteur,
                                  mode='simple')
        except Exception as e:
            QMessageBox.critical(self, "Erreur de nesting", str(e))
            self.statusBar().showMessage("Erreur lors du nesting.")

    def _lancer_nesting_optimise(self, methode: str = 'multi'):
        """Nesting optimisé (BL+Rotation) — asynchrone dans un thread."""
        tous_polygones = self._rassembler_polygones()
        if not tous_polygones:
            QMessageBox.warning(self, "Nesting", "Aucun contour à placer.")
            return

        largeur    = self._spin_larg.value()
        hauteur    = self._spin_haut.value()
        espacement = self._spin_esp.value()

        _labels = {
            'aire':      "Aire décroissante",
            'perimetre': "Périmètre décroissant",
            'dim_max':   "Dimension max. décroissante",
            'multi':     "Multi-séquençage",
        }
        nb_seq = 4 if methode == 'multi' else 1
        label  = _labels.get(methode, methode)

        # Verrouiller l'UI
        self._btn_nesting.setEnabled(False)
        self._btn_nesting.setText("Optimisation en cours…")
        self._barre_nesting.setVisible(True)
        self._barre_nesting.setRange(0, nb_seq * len(tous_polygones))
        self._barre_nesting.setValue(0)
        self.statusBar().showMessage(
            f"Nesting optimisé [{label}] : {len(tous_polygones)} pièces, "
            f"{nb_seq} séquence(s) × 12 rotations…"
        )

        self._nb_total_nesting = len(tous_polygones)
        self._larg_nesting     = largeur
        self._haut_nesting     = hauteur
        self._methode_nesting  = methode

        self._thread_nesting = ThreadNesting(
            tous_polygones, largeur, hauteur, espacement, methode=methode
        )
        self._thread_nesting.termine.connect(self._nesting_optimise_termine)
        self._thread_nesting.erreur.connect(self._nesting_optimise_erreur)
        self._thread_nesting.progression.connect(self._nesting_progression)
        self._thread_nesting.start()

    def _nesting_progression(self, courant: int, total: int):
        """Met à jour la barre de progression du nesting optimisé."""
        self._barre_nesting.setMaximum(total)
        self._barre_nesting.setValue(courant)
        n = self._nb_total_nesting
        if total > n:
            # Multi-séquençage : indiquer la séquence en cours
            seq = courant // n + 1
            nb_seq = total // n
            self._barre_nesting.setFormat(f"Séquence {seq}/{nb_seq} — pièce {courant % n}/{n}")
        else:
            self._barre_nesting.setFormat(f"Pièce {courant}/{total}")

    def _nesting_optimise_termine(self, placements: list, tous_places: bool):
        """Callback de fin du thread nesting optimisé."""
        self._btn_nesting.setEnabled(True)
        self._btn_nesting.setText("Calculer le nesting")
        self._barre_nesting.setVisible(False)

        self._nesting_termine(placements, tous_places,
                              self._nb_total_nesting,
                              self._larg_nesting, self._haut_nesting,
                              mode=self._methode_nesting)

    def _nesting_optimise_erreur(self, message: str):
        """Callback d'erreur du thread nesting optimisé."""
        self._btn_nesting.setEnabled(True)
        self._btn_nesting.setText("Calculer le nesting")
        self._barre_nesting.setVisible(False)
        QMessageBox.critical(self, "Erreur de nesting optimisé", message)
        self.statusBar().showMessage("Erreur lors du nesting optimisé.")

    def _lancer_nesting_sparrow(self, methode: str):
        """Nesting sparrow — asynchrone dans un thread, progression par timer."""
        from core.nesting_sparrow import ANGLES_MOYENNE, ANGLES_MAXI

        tous_polygones = self._rassembler_polygones()
        if not tous_polygones:
            QMessageBox.warning(self, "Nesting", "Aucun contour à placer.")
            return

        largeur    = self._spin_larg.value()
        hauteur    = self._spin_haut.value()
        espacement = self._spin_esp.value()

        if methode == 'sparrow_moy':
            angles       = ANGLES_MOYENNE
            time_limit_s = 60
            num_workers  = max(1, os.cpu_count() or 1)
            label        = "Sparrow — Moyenne (45°, 1 min)"
        else:
            angles       = ANGLES_MAXI
            time_limit_s = 600
            num_workers  = max(1, int((os.cpu_count() or 1) * 0.8))
            label        = "Sparrow — Maxi (1°, 10 min)"

        self._methode_nesting        = methode
        self._nb_total_nesting       = len(tous_polygones)
        self._larg_nesting           = largeur
        self._haut_nesting           = hauteur
        self._nesting_sparrow_limite = time_limit_s
        self._nesting_sparrow_debut          = time.time()
        self._meilleure_solution_sparrow     = []
        self._meilleure_score_sparrow        = float('inf')

        # Verrouiller l'UI
        self._btn_nesting.setEnabled(False)
        self._btn_nesting.setText("Sparrow en cours…")
        self._barre_nesting.setVisible(True)
        self._barre_nesting.setRange(0, 100)
        self._barre_nesting.setValue(0)
        self._barre_nesting.setFormat("00:00 / --:--")
        self._btn_stop_sparrow.setVisible(True)
        self.statusBar().showMessage(
            f"{label} : {len(tous_polygones)} pièces, {num_workers} worker(s)…"
        )

        self._thread_nesting_sparrow = ThreadNestingSparrow(
            tous_polygones, largeur, hauteur, espacement,
            angles, time_limit_s, num_workers
        )
        self._thread_nesting_sparrow.intermediaire.connect(
            self._nesting_sparrow_intermediaire)
        self._thread_nesting_sparrow.termine.connect(self._nesting_sparrow_termine)
        self._thread_nesting_sparrow.erreur.connect(self._nesting_sparrow_erreur)
        self._thread_nesting_sparrow.start()
        self._timer_nesting_sparrow.start()

    def _tick_progression_sparrow(self):
        """Mise à jour de l'affichage du temps écoulé (valeur gérée par intermediaire)."""
        elapsed = time.time() - self._nesting_sparrow_debut
        e_min, e_sec = int(elapsed // 60), int(elapsed % 60)
        l_min = self._nesting_sparrow_limite // 60
        l_sec = self._nesting_sparrow_limite % 60
        pct = self._barre_nesting.value()
        self._barre_nesting.setFormat(
            f"{e_min:02d}:{e_sec:02d} / {l_min:02d}:{l_sec:02d}"
            f"  —  densité {pct}%"
        )

    def _nesting_sparrow_intermediaire(self, placements: list,
                                       tous_places: bool, densite: float):
        """Affiche une solution intermédiaire sparrow dans la vue nesting.
        Conserve en parallèle la meilleure solution (aire bbox minimale)."""
        self._placements = placements
        self._nb_non_places = self._nb_total_nesting - len(placements)

        # Tracker la meilleure solution par aire de boîte englobante
        if placements:
            bw, bh = calculer_bbox_placements(placements)
            score = bw * bh
            if score < self._meilleure_score_sparrow:
                self._meilleure_score_sparrow    = score
                self._meilleure_solution_sparrow = list(placements)

        # Mettre à jour la vue (animation — on montre la solution courante)
        self._nesting_view.definir_plaque(self._larg_nesting, self._haut_nesting)
        self._nesting_view.definir_espacement(self._spin_esp.value())
        self._nesting_view.definir_placements(placements, self._nb_non_places)
        self._tabs.setCurrentIndex(1)

        # Barre de progression = densité en %
        pct = min(100, int(densite * 100))
        self._barre_nesting.setValue(pct)

        # Activer l'export avec le résultat intermédiaire courant
        if placements:
            self._btn_exp_nesting.setEnabled(True)
            self._action_export_nesting.setEnabled(True)

    def _nesting_sparrow_termine(self, placements: list, tous_places: bool):
        """Callback de fin naturelle du thread sparrow."""
        self._timer_nesting_sparrow.stop()
        self._btn_nesting.setEnabled(True)
        self._btn_nesting.setText("Calculer le nesting")
        self._barre_nesting.setVisible(False)
        self._btn_stop_sparrow.setVisible(False)
        self._nesting_termine(placements, tous_places,
                              self._nb_total_nesting,
                              self._larg_nesting, self._haut_nesting,
                              mode=self._methode_nesting)

    def _nesting_sparrow_erreur(self, message: str):
        """Callback d'erreur du thread sparrow."""
        self._timer_nesting_sparrow.stop()
        self._btn_nesting.setEnabled(True)
        self._btn_nesting.setText("Calculer le nesting")
        self._barre_nesting.setVisible(False)
        self._btn_stop_sparrow.setVisible(False)
        QMessageBox.critical(self, "Erreur sparrow", message)
        self.statusBar().showMessage("Erreur lors du nesting sparrow.")

    def _stopper_nesting_sparrow(self):
        """Arrête le polling sparrow et applique la meilleure solution intermédiaire
        (celle dont la boîte englobante est la plus petite)."""
        if self._thread_nesting_sparrow and self._thread_nesting_sparrow.isRunning():
            self._thread_nesting_sparrow.arreter()

        self._timer_nesting_sparrow.stop()
        self._btn_nesting.setEnabled(True)
        self._btn_nesting.setText("Calculer le nesting")
        self._barre_nesting.setVisible(False)
        self._btn_stop_sparrow.setVisible(False)

        # Utiliser la meilleure solution (bbox minimale), pas la dernière affichée
        meilleure = self._meilleure_solution_sparrow or self._placements
        if meilleure:
            self._placements     = meilleure
            self._nb_non_places  = self._nb_total_nesting - len(meilleure)

            # Mettre à jour la vue avec la meilleure solution
            self._nesting_view.definir_placements(meilleure, self._nb_non_places)

            taux = calculer_surface_utilisee(
                meilleure, self._larg_nesting, self._haut_nesting)
            bw, bh = calculer_bbox_placements(meilleure)
            nb     = len(meilleure)
            _labels = {'sparrow_moy': "Sparrow Moyenne", 'sparrow_max': "Sparrow Maxi"}
            label   = _labels.get(self._methode_nesting, "Sparrow")
            self._lbl_nesting_info.setText(
                f"[{label}]  Arrêté — {nb}/{self._nb_total_nesting} pièce(s)\n"
                f"Meilleure boîte englobante : {bw:.1f} × {bh:.1f} mm\n"
                f"Taux d'utilisation : {taux:.1f}%"
            )
            self.statusBar().showMessage(
                f"Sparrow arrêté — meilleure solution : {nb} pièces, "
                f"bbox {bw:.0f}×{bh:.0f} mm, taux {taux:.1f}%"
            )

    def _nesting_termine(self, placements: list, tous_places: bool,
                         nb_total: int, largeur: float, hauteur: float,
                         mode: str = 'simple'):
        """Gestionnaire commun de fin de nesting (simple ou optimisé)."""
        self._placements = placements
        nb_places = len(placements)
        self._nb_non_places = nb_total - nb_places

        taux = calculer_surface_utilisee(placements, largeur, hauteur)

        # Mettre à jour la vue nesting
        self._nesting_view.definir_plaque(largeur, hauteur)
        self._nesting_view.definir_espacement(self._spin_esp.value())
        self._nesting_view.definir_placements(placements, self._nb_non_places)
        self._tabs.setCurrentIndex(1)   # basculer sur l'onglet nesting

        # Construire le texte d'information
        _mode_labels = {
            'simple':      "Simple",
            'aire':        "Optimisé — Aire ↓",
            'perimetre':   "Optimisé — Périmètre ↓",
            'dim_max':     "Optimisé — Dim. max. ↓",
            'multi':       "Optimisé — Multi-séquençage",
            'sparrow_moy': "Sparrow — Moyenne (45°)",
            'sparrow_max': "Sparrow — Maxi (1°)",
        }
        mode_txt = _mode_labels.get(mode, mode)
        if mode != 'simple' and placements:
            bw, bh = calculer_bbox_placements(placements)
            bbox_txt = f"\nBoîte englobante : {bw:.1f} × {bh:.1f} mm"
        else:
            bbox_txt = ""

        if tous_places:
            info = (f"[{mode_txt}]  {nb_places}/{nb_total} pièce(s) placée(s)\n"
                    f"Taux d'utilisation plaque : {taux:.1f}%{bbox_txt}")
            self.statusBar().showMessage(
                f"Nesting {mode_txt.lower()} terminé : "
                f"{nb_places} pièces, taux {taux:.1f}%"
            )
        else:
            info = (f"[{mode_txt}]  {nb_places}/{nb_total} pièce(s) placée(s)\n"
                    f"{self._nb_non_places} non placée(s) — augmentez la plaque.\n"
                    f"Taux d'utilisation : {taux:.1f}%{bbox_txt}")
            self.statusBar().showMessage(
                f"Nesting {mode_txt.lower()} partiel : "
                f"{nb_places}/{nb_total} pièces placées."
            )

        self._lbl_nesting_info.setText(info)

        if placements:
            self._btn_exp_nesting.setEnabled(True)
            self._action_export_nesting.setEnabled(True)

    # =========================================================================
    # Actions : Export DXF
    # =========================================================================

    def _exporter_sections(self):
        """
        Exporte chaque section dans un fichier DXF séparé.
        Le préfixe du nom de fichier est le nom du STL chargé
        (ex. roue_001.dxf, roue_002.dxf, ...).
        """
        if not self._sections:
            QMessageBox.warning(self, "Export", "Aucune section à exporter.")
            return

        dossier = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier d'export des sections"
        )
        if not dossier:
            return

        # Utiliser le nom du fichier STL comme préfixe
        prefixe = (os.path.splitext(os.path.basename(self._fichier_stl))[0]
                   if self._fichier_stl else 'section')

        try:
            fichiers = exporter_toutes_sections(self._sections, dossier,
                                                prefixe=prefixe)
            QMessageBox.information(
                self, "Export réussi",
                f"{len(fichiers)} fichier(s) DXF créé(s) dans :\n{dossier}\n\n"
                f"Nommage : {prefixe}_001.dxf … {prefixe}_{len(fichiers):03d}.dxf"
            )
            self.statusBar().showMessage(
                f"Export terminé : {len(fichiers)} fichiers ({prefixe}_*) dans {dossier}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", str(e))

    def _exporter_nesting(self):
        """Exporte le nesting complet dans un seul fichier DXF."""
        if not self._placements:
            QMessageBox.warning(self, "Export", "Aucun nesting calculé.")
            return

        chemin, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le nesting",
            "nesting_complet.dxf",
            "Fichiers DXF (*.dxf);;Tous les fichiers (*.*)"
        )
        if not chemin:
            return

        try:
            exporter_nesting_dxf(
                self._placements,
                self._spin_larg.value(),
                self._spin_haut.value(),
                chemin
            )
            QMessageBox.information(
                self, "Export réussi",
                f"Nesting exporté dans :\n{chemin}"
            )
            self.statusBar().showMessage(
                f"Nesting exporté : {os.path.basename(chemin)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", str(e))

    # =========================================================================
    # Aide
    # =========================================================================

    def _afficher_apropos(self):
        """Affiche une boîte de dialogue À propos."""
        QMessageBox.about(
            self,
            "À propos — STL Slicer",
            "<b>STL Slicer — Découpe Laser</b><br><br>"
            "Application de découpe de pièces 3D par empilement de plaques.<br><br>"
            "<b>Workflow :</b><br>"
            "1. Ouvrir un fichier STL<br>"
            "2. Définir l'axe et l'épaisseur de coupe<br>"
            "3. Calculer les sections 2D<br>"
            "4. Répartir sur la plaque (nesting)<br>"
            "5. Exporter en DXF pour la découpe laser<br><br>"
            "Polytech Nancy — Génie Mécanique"
        )

    # =========================================================================
    # Fermeture
    # =========================================================================

    def closeEvent(self, event):
        """Fermeture propre : attendre la fin des threads de calcul si actifs."""
        self._timer_nesting_sparrow.stop()
        if (self._thread_nesting_sparrow
                and self._thread_nesting_sparrow.isRunning()):
            self._thread_nesting_sparrow.arreter()
        for thread in (self._thread_slicing, self._thread_nesting,
                       self._thread_nesting_sparrow):
            if thread and thread.isRunning():
                thread.quit()
                thread.wait(3000)
        super().closeEvent(event)

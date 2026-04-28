"""
ui/main_window.py — Fenêtre principale de Remocut ISO Generator.

Layout :
  ┌──────────────────────────────────────────────────────────┐
  │ Menu : Fichier | Aide                                     │
  │ Toolbar : [Ajouter DXF] [Nesting] [Générer] [Exporter]   │
  ├───────────────────┬──────────────────────────────────────┤
  │  DxfListPanel     │  DXF Viewer  |  Nesting View         │
  │  (liste + qty)    │                                       │
  ├───────────────────┴──────────────────────────────────────┤
  │                  Params Panel                             │
  ├──────────────────────────────────────────────────────────┤
  │  [████░░] Nesting…  [⏹ Arrêter]   Barre de statut        │
  └──────────────────────────────────────────────────────────┘

Modes de nesting :
  0 — Simple (rangées, sans rotation) — synchrone
  1-4 — Optimisé BL+Fill (12 rotations) — ThreadNesting
  5-6 — Sparrow (spyrrow) — ThreadNestingSparrow + solutions intermédiaires
"""

import logging
import math
import os
import time
import threading
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ui.dxf_list_panel import DxfListPanel, EntreeDxf
from ui.dxf_viewer import DxfViewer
from ui.gcode_viewer import GCodeViewer
from ui.nesting_view import NestingView
from ui.params_panel import ParamsPanel

logger = logging.getLogger(__name__)

# Correspondance index combo → identifiant méthode
_METHODES_NESTING = {
    1: 'aire',
    2: 'perimetre',
    3: 'dim_max',
    4: 'multi',
}


# =============================================================================
# Threads de nesting
# =============================================================================

class ThreadNesting(QThread):
    """
    Lance le nesting optimisé (BL+Fill + rotation) dans un thread séparé.
    Le calcul peut prendre plusieurs secondes selon le nombre de pièces.

    Signaux :
        termine(list, bool)    — (contours_places, tous_places)
        erreur(str)            — message d'erreur
        progression(int, int)  — (etape_courante, total)
    """
    termine     = pyqtSignal(list, bool)
    erreur      = pyqtSignal(str)
    progression = pyqtSignal(int, int)

    def __init__(
        self,
        pieces: list,
        largeur: float,
        hauteur: float,
        marge: float,
        methode: str = 'multi',
    ) -> None:
        super().__init__()
        self._pieces   = pieces
        self._largeur  = largeur
        self._hauteur  = hauteur
        self._marge    = marge
        self._methode  = methode

    def run(self) -> None:
        try:
            from core.nesting_optimise import placer_pieces_optimise
            result, tous = placer_pieces_optimise(
                self._pieces,
                self._largeur,
                self._hauteur,
                self._marge,
                methode=self._methode,
                callback_progression=lambda i, n: self.progression.emit(i, n),
            )
            self.termine.emit(result, tous)
        except Exception as e:
            logger.exception("Erreur ThreadNesting")
            self.erreur.emit(str(e))


class ThreadNestingSparrow(QThread):
    """
    Lance le nesting sparrow avec affichage des solutions intermédiaires.

    Architecture :
      - solve() tourne dans un thread daemon Python (non bloquant pour le QThread).
      - Le QThread poll queue.drain() toutes les 400 ms via msleep().
      - Chaque solution intermédiaire est émise via `intermediaire`.
      - arreter() stoppe le polling ; le thread daemon finit seul.

    Signaux :
        termine(list, bool)              — résultat final (contours_places, tous)
        erreur(str)                      — message d'erreur
        intermediaire(list, bool, float) — (contours_places, tous, densité)
    """
    termine       = pyqtSignal(list, bool)
    erreur        = pyqtSignal(str)
    intermediaire = pyqtSignal(list, bool, float)

    def __init__(
        self,
        pieces: list,
        largeur: float,
        hauteur: float,
        marge: float,
        angles: list,
        time_limit_s: int,
        num_workers: int,
    ) -> None:
        super().__init__()
        self._pieces       = pieces
        self._largeur      = largeur
        self._hauteur      = hauteur
        self._marge        = marge
        self._angles       = angles
        self._time_limit   = time_limit_s
        self._num_workers  = num_workers
        self._stop_demand  = False

    def arreter(self) -> None:
        """Demande l'arrêt du polling (le solve() daemon finit seul)."""
        self._stop_demand = True

    def run(self) -> None:
        try:
            import spyrrow
        except ImportError:
            self.erreur.emit(
                "spyrrow non installé.\nInstallez-la avec : pip install spyrrow"
            )
            return

        try:
            from core.nesting_sparrow import (
                preparer_metas_pieces,
                placer_depuis_solution_pieces,
            )

            metas = preparer_metas_pieces(self._pieces)
            items = [
                spyrrow.Item(
                    f"p{m['idx_piece']}",
                    m['coords'],
                    demand=1,
                    allowed_orientations=self._angles,
                )
                for m in metas
            ]
            instance = spyrrow.StripPackingInstance(
                "remocut_nesting",
                strip_height=self._hauteur,
                items=items,
            )
            config = spyrrow.StripPackingConfig(
                early_termination=True,
                total_computation_time=self._time_limit,
                min_items_separation=self._marge if self._marge > 0 else None,
                num_workers=self._num_workers if self._num_workers > 0 else None,
                seed=42,
            )

            queue = spyrrow.ProgressQueue()
            result_holder = [None, None]  # [solution, exception]

            def _do_solve() -> None:
                try:
                    result_holder[0] = instance.solve(config, progress=queue)
                except Exception as ex:
                    result_holder[1] = ex

            solve_thread = threading.Thread(target=_do_solve, daemon=True)
            solve_thread.start()

            # Polling des solutions intermédiaires (toutes les 400 ms)
            while solve_thread.is_alive() and not self._stop_demand:
                for _report_type, solution in queue.drain():
                    places, tous = placer_depuis_solution_pieces(
                        solution.placed_items, metas, self._pieces,
                        self._largeur, self._hauteur,
                    )
                    self.intermediaire.emit(places, tous, float(solution.density))
                self.msleep(400)

            if self._stop_demand:
                # L'utilisateur a arrêté — les résultats intermédiaires sont déjà
                # affichés dans la vue ; on n'émet pas termine.
                return

            solve_thread.join(timeout=10)

            if result_holder[1] is not None:
                self.erreur.emit(str(result_holder[1]))
                return

            if result_holder[0] is not None:
                places, tous = placer_depuis_solution_pieces(
                    result_holder[0].placed_items, metas, self._pieces,
                    self._largeur, self._hauteur,
                )
                self.termine.emit(places, tous)

        except Exception as e:
            logger.exception("Erreur ThreadNestingSparrow")
            self.erreur.emit(str(e))


# =============================================================================
# Fenêtre principale
# =============================================================================

class MainWindow(QMainWindow):
    """Fenêtre principale de l'application Remocut ISO Generator."""

    def __init__(self) -> None:
        super().__init__()
        # État de l'application
        self._contours_places: List = []
        self._contours_ordonnes: List = []        # après optimisation trajectoire
        self._stats_trajectoire = None             # StatsTrajectoire
        self._gcode: Optional[str] = None

        # Threads de nesting
        self._thread_nesting: Optional[ThreadNesting] = None
        self._thread_nesting_sparrow: Optional[ThreadNestingSparrow] = None

        # Données nesting en cours (pour les callbacks)
        self._nb_total_nesting = 0
        self._larg_nesting = 0.0
        self._haut_nesting = 0.0
        self._methode_nesting = 'simple'
        self._nesting_sparrow_debut = 0.0
        self._nesting_sparrow_limite = 60
        self._meilleure_solution_sparrow: list = []
        self._meilleure_score_sparrow = float('inf')
        # Une fois que l'utilisateur appuie sur "Arrêter", on ne veut plus que
        # `isRunning()` du thread en voie d'extinction désactive le bouton
        # trajectoire. Ce flag force l'état "pas de nesting en cours".
        self._nesting_force_arrete: bool = False

        self._construire_ui()
        self._creer_menus()
        self._creer_toolbar()
        self._connecter_signaux()
        self._mettre_a_jour_etat_boutons()

    # -----------------------------------------------------------------------
    # Construction interface
    # -----------------------------------------------------------------------

    def _construire_ui(self) -> None:
        """Construit la structure principale de la fenêtre."""
        self.setWindowTitle("Remocut ISO Generator — ECP1000")
        self.setMinimumSize(1200, 750)
        self.resize(1400, 900)

        widget_central = QWidget()
        self.setCentralWidget(widget_central)
        layout_principal = QVBoxLayout(widget_central)
        layout_principal.setContentsMargins(4, 4, 4, 4)
        layout_principal.setSpacing(4)

        # ── Splitter principal vertical : zone vues (haute) | paramètres (bas) ──
        self._splitter_principal = QSplitter(Qt.Orientation.Vertical)
        self._splitter_principal.setChildrenCollapsible(False)
        self._splitter_principal.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # ── Splitter horizontal : liste DXF (gauche) | vues (droite) ──
        self._splitter_haut = QSplitter(Qt.Orientation.Horizontal)
        self._splitter_haut.setChildrenCollapsible(False)
        self._splitter_haut.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # ── Panneau liste DXF (gauche) ──
        self._dxf_list_panel = DxfListPanel()
        self._dxf_list_panel.setMinimumWidth(220)
        self._dxf_list_panel.setMaximumWidth(380)
        self._dxf_list_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self._splitter_haut.addWidget(self._dxf_list_panel)

        # ── Splitter vues DXF + Nesting (droite) ──
        self._splitter_vues = QSplitter(Qt.Orientation.Horizontal)
        self._splitter_vues.setChildrenCollapsible(False)
        self._splitter_vues.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        grp_dxf = QWidget()
        grp_dxf.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay_dxf = QVBoxLayout(grp_dxf)
        lay_dxf.setContentsMargins(0, 0, 0, 0)
        lay_dxf.setSpacing(2)
        self._lbl_vue_gauche = QLabel("Aperçu DXF")
        self._lbl_vue_gauche.setStyleSheet("font-weight: bold; color: #333; padding: 2px 4px;")
        lay_dxf.addWidget(self._lbl_vue_gauche)

        # StackedWidget : page 0 = DxfViewer, page 1 = GCodeViewer
        self._stack_gauche = QStackedWidget()
        self._stack_gauche.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._dxf_viewer = DxfViewer()
        self._gcode_viewer = GCodeViewer()
        self._stack_gauche.addWidget(self._dxf_viewer)    # index 0
        self._stack_gauche.addWidget(self._gcode_viewer)  # index 1
        self._stack_gauche.setCurrentIndex(0)
        lay_dxf.addWidget(self._stack_gauche, 1)

        grp_nesting = QWidget()
        grp_nesting.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay_nest = QVBoxLayout(grp_nesting)
        lay_nest.setContentsMargins(0, 0, 0, 0)
        lay_nest.setSpacing(2)
        lbl_nest = QLabel("Nesting sur tôle")
        lbl_nest.setStyleSheet("font-weight: bold; color: #333; padding: 2px 4px;")
        self._nesting_view = NestingView()
        lay_nest.addWidget(lbl_nest)
        lay_nest.addWidget(self._nesting_view, 1)

        self._splitter_vues.addWidget(grp_dxf)
        self._splitter_vues.addWidget(grp_nesting)
        self._splitter_vues.setStretchFactor(0, 1)
        self._splitter_vues.setStretchFactor(1, 1)

        self._splitter_haut.addWidget(self._splitter_vues)
        self._splitter_haut.setStretchFactor(0, 0)   # liste DXF : taille fixe
        self._splitter_haut.setStretchFactor(1, 1)   # vues : prend tout l'espace

        # ── Panneau paramètres (bas, hauteur fixe) ──
        self._params_panel = ParamsPanel()
        self._params_panel.setMinimumHeight(160)
        self._params_panel.setMaximumHeight(220)
        self._params_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        self._splitter_principal.addWidget(self._splitter_haut)
        self._splitter_principal.addWidget(self._params_panel)
        self._splitter_principal.setStretchFactor(0, 1)   # vues : s'étire
        self._splitter_principal.setStretchFactor(1, 0)   # params : hauteur fixe
        self._splitter_principal.setSizes([680, 200])

        layout_principal.addWidget(self._splitter_principal, 1)

        # Barre de statut
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._lbl_statut = QLabel("Prêt — Ajoutez un ou plusieurs fichiers DXF.")
        self._status_bar.addWidget(self._lbl_statut, 1)

        # Barre de progression nesting (dans la status bar, droite)
        self._barre_nesting = QProgressBar()
        self._barre_nesting.setVisible(False)
        self._barre_nesting.setMinimumWidth(200)
        self._barre_nesting.setMaximumWidth(320)
        self._barre_nesting.setMaximumHeight(16)
        self._barre_nesting.setTextVisible(True)
        self._status_bar.addPermanentWidget(self._barre_nesting)

        self._btn_stop_nesting = QPushButton("⏹ Arrêter")
        self._btn_stop_nesting.setVisible(False)
        self._btn_stop_nesting.setMaximumHeight(20)
        self._btn_stop_nesting.setStyleSheet(
            "QPushButton { color: #b00; font-weight: bold; padding: 0 6px; }"
            "QPushButton:hover { background: #fdd; }"
        )
        self._btn_stop_nesting.clicked.connect(self._stopper_nesting_sparrow)
        self._status_bar.addPermanentWidget(self._btn_stop_nesting)

    def _creer_menus(self) -> None:
        """Crée la barre de menus."""
        barre = self.menuBar()

        menu_fichier = barre.addMenu("&Fichier")

        self._action_ajouter = QAction("&Ajouter DXF…", self)
        self._action_ajouter.setShortcut(QKeySequence.StandardKey.Open)
        self._action_ajouter.setStatusTip("Ajouter un ou plusieurs fichiers DXF")
        menu_fichier.addAction(self._action_ajouter)

        # Sous-menu : fichiers récents
        self._menu_recents = menu_fichier.addMenu("Fichiers &récents")
        self._reconstruire_menu_recents()

        menu_fichier.addSeparator()

        self._action_exporter = QAction("&Exporter GCode…", self)
        self._action_exporter.setShortcut(QKeySequence.StandardKey.Save)
        self._action_exporter.setStatusTip("Sauvegarder le GCode généré (.iso)")
        self._action_exporter.setEnabled(False)
        menu_fichier.addAction(self._action_exporter)

        menu_fichier.addSeparator()

        action_quitter = QAction("&Quitter", self)
        action_quitter.setShortcut(QKeySequence.StandardKey.Quit)
        action_quitter.triggered.connect(self.close)
        menu_fichier.addAction(action_quitter)

        menu_vue = barre.addMenu("&Vue")

        self._action_preview = QAction("Prévisualiser &GCode", self)
        self._action_preview.setShortcut("Ctrl+P")
        self._action_preview.setEnabled(False)
        menu_vue.addAction(self._action_preview)

        menu_aide = barre.addMenu("&Aide")
        action_a_propos = QAction("À &propos…", self)
        action_a_propos.triggered.connect(self._afficher_a_propos)
        menu_aide.addAction(action_a_propos)

    def _creer_toolbar(self) -> None:
        """Crée la barre d'outils principale."""
        toolbar = QToolBar("Workflow")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._btn_ajouter = toolbar.addAction("📂 Ajouter DXF…")
        self._btn_ajouter.setStatusTip("Ajouter un ou plusieurs fichiers DXF (Ctrl+O)")

        toolbar.addSeparator()

        self._btn_nesting = toolbar.addAction("🧩 Calculer Nesting")
        self._btn_nesting.setStatusTip("Placer les pièces sur la tôle selon les quantités")
        self._btn_nesting.setEnabled(False)

        toolbar.addSeparator()

        self._btn_trajectoire = toolbar.addAction("🛣 Calculer Trajectoires")
        self._btn_trajectoire.setStatusTip(
            "Optimiser l'ordre de découpe pour minimiser les déplacements à vide (G00)"
        )
        self._btn_trajectoire.setEnabled(False)

        toolbar.addSeparator()

        self._btn_generer = toolbar.addAction("⚙ Générer GCode")
        self._btn_generer.setStatusTip("Générer le programme GCode ECP1000")
        self._btn_generer.setEnabled(False)

        toolbar.addSeparator()

        self._btn_exporter = toolbar.addAction("💾 Exporter .iso")
        self._btn_exporter.setStatusTip("Sauvegarder le fichier GCode")
        self._btn_exporter.setEnabled(False)

    def _connecter_signaux(self) -> None:
        """Connecte tous les signaux aux slots."""
        self._action_ajouter.triggered.connect(self._dxf_list_panel._ajouter_dxf_dialogue)
        self._action_exporter.triggered.connect(self._exporter_gcode)
        self._action_preview.triggered.connect(self._afficher_preview_gcode)

        self._btn_ajouter.triggered.connect(self._dxf_list_panel._ajouter_dxf_dialogue)
        self._btn_nesting.triggered.connect(self._calculer_nesting)
        self._btn_trajectoire.triggered.connect(self._calculer_trajectoires)
        self._btn_generer.triggered.connect(self._generer_gcode)
        self._btn_exporter.triggered.connect(self._exporter_gcode)

        # Quand la liste DXF change → mettre à jour le viewer + état des boutons
        self._dxf_list_panel.list_changed.connect(self._on_liste_dxf_changed)
        # Sélection dans la liste → afficher la pièce seule dans le viewer
        self._dxf_list_panel.selection_changee.connect(self._on_dxf_selection_changee)

        # GCode viewer : ligne sélectionnée → marqueur position outil / retour
        self._gcode_viewer.position_changee.connect(self._on_position_outil_changee)
        self._gcode_viewer.retour_demande.connect(self._afficher_vue_dxf)

        self._params_panel.params_changed.connect(self._on_params_changed)

    def _on_position_outil_changee(self, pos) -> None:
        """Met à jour le marqueur de position outil dans le NestingView."""
        self._nesting_view.set_position_outil(pos)

    def _afficher_vue_gcode(self) -> None:
        """Bascule la vue de gauche en mode GCode."""
        self._stack_gauche.setCurrentIndex(1)
        self._lbl_vue_gauche.setText("Programme GCode")

    def _afficher_vue_dxf(self) -> None:
        """Bascule la vue de gauche en mode aperçu DXF."""
        self._stack_gauche.setCurrentIndex(0)
        self._lbl_vue_gauche.setText("Aperçu DXF")
        # Effacer le marqueur de position outil
        self._nesting_view.set_position_outil(None)

    def _on_dxf_selection_changee(self, entree) -> None:
        """Affiche uniquement l'entrée DXF sélectionnée dans l'aperçu."""
        if entree is None:
            # Si rien sélectionné mais liste non vide, afficher tout
            entrees = self._dxf_list_panel.get_entrees()
            if entrees:
                self._dxf_viewer.set_entrees_multiples(entrees)
            else:
                self._dxf_viewer.vider()
        else:
            self._dxf_viewer.set_entree_unique(entree)

    # -----------------------------------------------------------------------
    # Réaction aux changements de la liste DXF
    # -----------------------------------------------------------------------

    def _on_liste_dxf_changed(self) -> None:
        """
        Appelé quand la liste DXF est modifiée (ajout, suppression, quantité).
        Met à jour le viewer DXF et invalide le nesting/GCode courants.
        """
        entrees = self._dxf_list_panel.get_entrees()

        # Enregistrer dans les "fichiers récents" tout chemin nouvellement présent
        for e in entrees:
            if e.chemin:
                self._ajouter_fichier_recent(e.chemin)

        if entrees:
            # Afficher la pièce sélectionnée (par défaut la dernière ajoutée)
            selection = self._dxf_list_panel.get_entree_selectionnee()
            if selection is not None:
                self._dxf_viewer.set_entree_unique(selection)
            else:
                self._dxf_viewer.set_entree_unique(entrees[0])
        else:
            self._dxf_viewer.vider()

        self._contours_places = []
        self._contours_ordonnes = []
        self._stats_trajectoire = None
        self._gcode = None
        self._nesting_view.vider()
        self._gcode_viewer.vider()
        self._afficher_vue_dxf()

        self._mettre_a_jour_etat_boutons()

        n_fichiers = len(entrees)
        if n_fichiers == 0:
            self._statut("Liste vide — ajoutez des fichiers DXF.")
        else:
            total_qty = sum(e.quantite for e in entrees)
            self._statut(
                f"{n_fichiers} fichier(s) · {total_qty} pièce(s) à découper — "
                f"cliquez sur 'Calculer Nesting'."
            )

    # -----------------------------------------------------------------------
    # Nesting — dispatch selon le mode
    # -----------------------------------------------------------------------

    def _calculer_nesting(self) -> None:
        """Dispatche vers le bon algorithme selon le mode choisi dans ParamsPanel."""
        entrees = self._dxf_list_panel.get_entrees()
        if not entrees:
            self._avertissement(
                "Aucun fichier DXF",
                "Veuillez d'abord ajouter au moins un fichier DXF."
            )
            return

        # Ne pas relancer si un thread est en cours
        if self._thread_nesting and self._thread_nesting.isRunning():
            return
        if self._thread_nesting_sparrow and self._thread_nesting_sparrow.isRunning():
            return

        # Nouveau nesting → on efface le flag d'arrêt forcé précédent
        self._nesting_force_arrete = False

        params = self._params_panel.get_params()
        methode = params.get('mode_nesting', 'simple')

        if methode == 'simple':
            self._lancer_nesting_simple(entrees, params)
        elif methode in _METHODES_NESTING.values():
            self._lancer_nesting_optimise(entrees, params, methode)
        elif methode in ('sparrow_moy', 'sparrow_max'):
            self._lancer_nesting_sparrow(entrees, params, methode)
        else:
            self._lancer_nesting_simple(entrees, params)

    def _lancer_nesting_simple(self, entrees, params: dict) -> None:
        """Nesting simple (rangées, sans rotation) — synchrone."""
        from core.nesting import placer_avec_quantites

        total_qty = sum(e.quantite for e in entrees)
        self._statut(f"Calcul du nesting simple ({total_qty} pièce(s))…")

        try:
            entrees_nesting = [(e.contours, e.quantite) for e in entrees]
            self._contours_places = placer_avec_quantites(
                entrees=entrees_nesting,
                largeur_tole=params['largeur_tole'],
                hauteur_tole=params['hauteur_tole'],
                marge=params['marge_nesting'],
            )
            self._appliquer_resultats_nesting(
                self._contours_places, True, total_qty,
                params['largeur_tole'], params['hauteur_tole'],
                mode='simple',
            )
        except ValueError as e:
            self._erreur("Erreur de nesting", str(e))
        except Exception as e:
            logger.exception("Erreur inattendue lors du nesting simple")
            self._erreur("Erreur inattendue", f"Erreur nesting :\n{e}")

    def _lancer_nesting_optimise(self, entrees, params: dict, methode: str) -> None:
        """Nesting optimisé (BL+Fill + rotation) — asynchrone."""
        from core.nesting import construire_pieces

        _labels = {
            'aire':      "Aire décroissante",
            'perimetre': "Périmètre décroissant",
            'dim_max':   "Dimension max. décroissante",
            'multi':     "Multi-séquençage (4 ordres)",
        }
        label = _labels.get(methode, methode)
        nb_seq = 4 if methode == 'multi' else 1

        entrees_nesting = [(e.contours, e.quantite) for e in entrees]
        pieces = construire_pieces(entrees_nesting)
        if not pieces:
            self._avertissement("Nesting", "Aucune pièce à placer.")
            return

        self._nb_total_nesting = len(pieces)
        self._larg_nesting = params['largeur_tole']
        self._haut_nesting = params['hauteur_tole']
        self._methode_nesting = methode

        # Verrouiller l'UI
        self._btn_nesting.setEnabled(False)
        self._barre_nesting.setRange(0, nb_seq * len(pieces))
        self._barre_nesting.setValue(0)
        self._barre_nesting.setFormat(f"Nesting {label}…")
        self._barre_nesting.setVisible(True)
        self._statut(
            f"Nesting optimisé [{label}] : {len(pieces)} pièce(s), "
            f"{nb_seq} séquence(s) × 12 rotations…"
        )

        self._thread_nesting = ThreadNesting(
            pieces,
            params['largeur_tole'],
            params['hauteur_tole'],
            params['marge_nesting'],
            methode=methode,
        )
        self._thread_nesting.termine.connect(self._on_nesting_optimise_termine)
        self._thread_nesting.erreur.connect(self._on_nesting_optimise_erreur)
        self._thread_nesting.progression.connect(self._on_nesting_progression)
        self._thread_nesting.start()

    def _lancer_nesting_sparrow(self, entrees, params: dict, methode: str) -> None:
        """Nesting sparrow — asynchrone avec solutions intermédiaires."""
        from core.nesting import construire_pieces
        from core.nesting_sparrow import ANGLES_MOYENNE, ANGLES_MAXI

        entrees_nesting = [(e.contours, e.quantite) for e in entrees]
        pieces = construire_pieces(entrees_nesting)
        if not pieces:
            self._avertissement("Nesting", "Aucune pièce à placer.")
            return

        if methode == 'sparrow_moy':
            angles = ANGLES_MOYENNE
            time_limit_s = 60
            num_workers = max(1, os.cpu_count() or 1)
            label = "Sparrow — Moyenne (45°, 1 min)"
        else:
            angles = ANGLES_MAXI
            time_limit_s = 600
            num_workers = max(1, int((os.cpu_count() or 1) * 0.8))
            label = "Sparrow — Maxi (1°, 10 min)"

        self._nb_total_nesting = len(pieces)
        self._larg_nesting = params['largeur_tole']
        self._haut_nesting = params['hauteur_tole']
        self._methode_nesting = methode
        self._nesting_sparrow_limite = time_limit_s
        self._nesting_sparrow_debut = time.time()
        self._meilleure_solution_sparrow = []
        self._meilleure_score_sparrow = float('inf')

        # Verrouiller l'UI + montrer barre + bouton stop
        self._btn_nesting.setEnabled(False)
        self._barre_nesting.setRange(0, 100)
        self._barre_nesting.setValue(0)
        self._barre_nesting.setFormat("00:00 / --:--  densité 0%")
        self._barre_nesting.setVisible(True)
        self._btn_stop_nesting.setVisible(True)
        self._statut(
            f"{label} : {len(pieces)} pièce(s), {num_workers} worker(s)…"
        )

        self._thread_nesting_sparrow = ThreadNestingSparrow(
            pieces,
            params['largeur_tole'],
            params['hauteur_tole'],
            params['marge_nesting'],
            angles,
            time_limit_s,
            num_workers,
        )
        self._thread_nesting_sparrow.intermediaire.connect(
            self._on_nesting_sparrow_intermediaire
        )
        self._thread_nesting_sparrow.termine.connect(self._on_nesting_sparrow_termine)
        self._thread_nesting_sparrow.erreur.connect(self._on_nesting_sparrow_erreur)
        self._thread_nesting_sparrow.start()

    # -----------------------------------------------------------------------
    # Callbacks nesting optimisé
    # -----------------------------------------------------------------------

    def _on_nesting_progression(self, courant: int, total: int) -> None:
        """Met à jour la barre de progression du nesting optimisé."""
        self._barre_nesting.setMaximum(total)
        self._barre_nesting.setValue(courant)
        n = self._nb_total_nesting
        if total > n and n > 0:
            seq = courant // n + 1
            nb_seq = total // n
            piece_cur = courant % n
            self._barre_nesting.setFormat(
                f"Séquence {seq}/{nb_seq}  pièce {piece_cur}/{n}"
            )
        else:
            self._barre_nesting.setFormat(f"Pièce {courant}/{total}")

    def _on_nesting_optimise_termine(self, contours_places: list, tous: bool) -> None:
        """Callback de fin du thread nesting optimisé."""
        self._barre_nesting.setVisible(False)
        self._appliquer_resultats_nesting(
            contours_places, tous,
            self._nb_total_nesting,
            self._larg_nesting, self._haut_nesting,
            mode=self._methode_nesting,
        )
        self._mettre_a_jour_etat_boutons()

    def _on_nesting_optimise_erreur(self, message: str) -> None:
        """Callback d'erreur du thread nesting optimisé."""
        self._barre_nesting.setVisible(False)
        self._mettre_a_jour_etat_boutons()
        self._erreur("Erreur de nesting optimisé", message)

    # -----------------------------------------------------------------------
    # Callbacks nesting sparrow
    # -----------------------------------------------------------------------

    def _on_nesting_sparrow_intermediaire(
        self, contours_places: list, tous: bool, densite: float
    ) -> None:
        """
        Affiche une solution intermédiaire sparrow dans la vue nesting.
        Conserve en parallèle la meilleure solution (bbox minimale).
        """
        params = self._params_panel.get_params()

        # Tracker la meilleure solution par score bbox
        if contours_places:
            from core.nesting_optimise import calculer_bbox_placements
            bw, bh = calculer_bbox_placements(contours_places)
            score = bw * bh
            if score < self._meilleure_score_sparrow:
                self._meilleure_score_sparrow = score
                self._meilleure_solution_sparrow = list(contours_places)

        # Mettre à jour la vue
        self._contours_places = contours_places
        self._nesting_view.set_nesting(
            contours_places=contours_places,
            largeur_tole=self._larg_nesting,
            hauteur_tole=self._haut_nesting,
            longueur_lead_in=params.get('longueur_lead_in', 5.0),
            longueur_lead_out=params.get('longueur_lead_out', 5.0),
            type_lead=params.get('type_lead_in', 'lineaire'),
        )

        # Barre de progression : densité en %
        pct = min(100, int(densite * 100))
        elapsed = time.time() - self._nesting_sparrow_debut
        e_min, e_sec = int(elapsed // 60), int(elapsed % 60)
        l_min = self._nesting_sparrow_limite // 60
        l_sec = self._nesting_sparrow_limite % 60
        self._barre_nesting.setValue(pct)
        self._barre_nesting.setFormat(
            f"{e_min:02d}:{e_sec:02d} / {l_min:02d}:{l_sec:02d}  densité {pct}%"
        )

        self._mettre_a_jour_etat_boutons()

    def _on_nesting_sparrow_termine(self, contours_places: list, tous: bool) -> None:
        """Callback de fin naturelle du thread sparrow."""
        self._barre_nesting.setVisible(False)
        self._btn_stop_nesting.setVisible(False)
        self._appliquer_resultats_nesting(
            contours_places, tous,
            self._nb_total_nesting,
            self._larg_nesting, self._haut_nesting,
            mode=self._methode_nesting,
        )
        self._mettre_a_jour_etat_boutons()

    def _on_nesting_sparrow_erreur(self, message: str) -> None:
        """Callback d'erreur du thread sparrow."""
        self._barre_nesting.setVisible(False)
        self._btn_stop_nesting.setVisible(False)
        self._mettre_a_jour_etat_boutons()
        self._erreur("Erreur sparrow", message)

    def _stopper_nesting_sparrow(self) -> None:
        """
        Arrête le polling sparrow et applique la meilleure solution intermédiaire
        (celle dont la boîte englobante est la plus petite). Le résultat est
        validé comme un nesting normal : les trajectoires peuvent être calculées.
        """
        # À partir de maintenant, le nesting est considéré comme terminé côté UI,
        # même si le thread met encore ~400ms à sortir de sa boucle de polling.
        self._nesting_force_arrete = True

        if self._thread_nesting_sparrow and self._thread_nesting_sparrow.isRunning():
            self._thread_nesting_sparrow.arreter()

        self._barre_nesting.setVisible(False)
        self._btn_stop_nesting.setVisible(False)

        # Appliquer la meilleure solution connue (bbox minimale)
        meilleure = self._meilleure_solution_sparrow or self._contours_places
        if not meilleure:
            self._mettre_a_jour_etat_boutons()
            return

        # Considérer toutes les pièces placées = nesting complet (tous_places=True)
        nb_places = len(set(cp.id_piece for cp in meilleure))
        tous_places = (nb_places >= self._nb_total_nesting)

        # Passe par le chemin commun : reset trajectoire/GCode, vue DXF, etc.
        self._appliquer_resultats_nesting(
            meilleure, tous_places,
            self._nb_total_nesting,
            self._larg_nesting, self._haut_nesting,
            mode=self._methode_nesting,
        )

        # Surcharger le message de statut pour indiquer l'arrêt manuel + bbox
        from core.nesting_optimise import calculer_bbox_placements
        bw, bh = calculer_bbox_placements(meilleure)
        _labels = {
            'sparrow_moy': "Sparrow Moyenne",
            'sparrow_max': "Sparrow Maxi",
        }
        label = _labels.get(self._methode_nesting, "Sparrow")
        self._statut(
            f"⏹ [{label}] Arrêté manuellement — {nb_places}/{self._nb_total_nesting} "
            f"pièce(s), bbox {bw:.0f}×{bh:.0f} mm. "
            f"Vous pouvez calculer les trajectoires."
        )
        self._mettre_a_jour_etat_boutons()

    # -----------------------------------------------------------------------
    # Résultats nesting communs
    # -----------------------------------------------------------------------

    def _appliquer_resultats_nesting(
        self,
        contours_places: list,
        tous_places: bool,
        nb_total: int,
        largeur: float,
        hauteur: float,
        mode: str = 'simple',
    ) -> None:
        """
        Applique les résultats de nesting : met à jour la vue + statut.
        Commun à simple, optimisé et sparrow.
        """
        from core.nesting import verifier_chevauchement

        self._contours_places = contours_places
        self._contours_ordonnes = []           # trajectoire invalidée par un nouveau nesting
        self._stats_trajectoire = None
        self._gcode = None
        self._gcode_viewer.vider()
        self._afficher_vue_dxf()
        # Pas de trajectoires affichées tant qu'elles n'ont pas été calculées
        self._nesting_view.set_afficher_trajectoires(False)

        params = self._params_panel.get_params()
        self._nesting_view.set_nesting(
            contours_places=contours_places,
            largeur_tole=largeur,
            hauteur_tole=hauteur,
            longueur_lead_in=params.get('longueur_lead_in', 5.0),
            longueur_lead_out=params.get('longueur_lead_out', 5.0),
            type_lead=params.get('type_lead_in', 'lineaire'),
        )

        n_places = len(set(cp.id_piece for cp in contours_places))
        n_non = nb_total - n_places

        # Libellés des modes
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

        # Vérifier les chevauchements
        avertissements = verifier_chevauchement(contours_places)
        for msg in avertissements:
            logger.warning(msg)

        if tous_places:
            msg = (
                f"✓ [{mode_txt}]  {n_places}/{nb_total} pièce(s) placée(s)."
            )
        else:
            msg = (
                f"⚠ [{mode_txt}]  {n_places}/{nb_total} pièce(s) — "
                f"{n_non} non placée(s) (tôle trop petite ou marge trop grande)."
            )

        if avertissements:
            msg += f" ⚠ {len(avertissements)} chevauchement(s) détecté(s)."

        self._statut(msg)

        # Avertissement utilisateur explicite si toutes les pièces ne rentrent
        # pas dans le format de tôle paramétré.
        if not tous_places:
            QMessageBox.warning(
                self,
                "Pièces non placées",
                f"{n_non} pièce(s) sur {nb_total} n'ont pas pu être placée(s) "
                f"sur la tôle {largeur:.0f} × {hauteur:.0f} mm.\n\n"
                "Causes possibles :\n"
                "  • tôle trop petite,\n"
                "  • marge inter-pièces trop grande,\n"
                "  • quantité trop élevée pour ce format.\n\n"
                "Augmentez les dimensions de la tôle ou réduisez les quantités."
            )

    # -----------------------------------------------------------------------
    # Actions principales
    # -----------------------------------------------------------------------

    def _calculer_trajectoires(self) -> None:
        """
        Étape dédiée : optimise l'ordre de découpe pour minimiser les
        déplacements G00 à vide. Doit être appelée après le nesting.
        """
        if not self._contours_places:
            self._avertissement(
                "Aucun nesting",
                "Veuillez d'abord calculer le nesting."
            )
            return

        params = self._params_panel.get_params()
        longueur_lead_in = params.get('longueur_lead_in', 5.0)
        longueur_lead_out = params.get('longueur_lead_out', 5.0)
        type_lead = params.get('type_lead_in', 'lineaire')
        marge = params.get('marge_nesting', 10.0)

        self._statut("Calcul des trajectoires optimisées…")

        try:
            # --- Étape préalable : ajuster le point de départ de chaque
            # contour pour garantir un écart >= marge entre le lead-in
            # et les pièces voisines. Si impossible, marquer comme problème.
            from core.geometry import ajuster_point_depart

            n_probleme = 0
            for cp in self._contours_places:
                # Voisins = tous les autres contours (extérieurs ET trous
                # d'autres pièces). On exclut les trous de la même pièce
                # pour ne pas pénaliser le lead-in d'un contour proche
                # de son propre intérieur.
                voisins = [
                    autre.points
                    for autre in self._contours_places
                    if autre is not cp and autre.id_piece != cp.id_piece
                ]
                nouveau, ok = ajuster_point_depart(
                    cp.points,
                    voisins,
                    marge=marge,
                    longueur_lead_in=longueur_lead_in,
                    type_lead=type_lead,
                    est_interieur=cp.est_interieur,
                )
                cp.points = nouveau
                cp.probleme_piquage = not ok
                if not ok:
                    n_probleme += 1

            from core.trajectory import calculer_trajectoires
            contours_ordonnes, stats = calculer_trajectoires(
                contours_places=self._contours_places,
                longueur_lead_in=longueur_lead_in,
                longueur_lead_out=longueur_lead_out,
                origine=(0.0, 0.0),
                activer_2opt=True,
            )
            self._contours_ordonnes = contours_ordonnes
            self._stats_trajectoire = stats
            self._gcode = None   # GCode invalide tant que la trajectoire n'est pas réappliquée

            # Mettre à jour la vue de nesting avec l'ordre optimisé (G00 en pointillés)
            self._nesting_view.set_nesting(
                contours_places=contours_ordonnes,
                largeur_tole=self._larg_nesting or params['largeur_tole'],
                hauteur_tole=self._haut_nesting or params['hauteur_tole'],
                longueur_lead_in=longueur_lead_in,
                longueur_lead_out=longueur_lead_out,
                type_lead=params.get('type_lead_in', 'lineaire'),
            )
            # Maintenant, afficher les trajectoires (lead-in/out + G00)
            self._nesting_view.set_afficher_trajectoires(True)

            msg = (
                f"✓ Trajectoire optimisée : G00 {stats.distance_initiale_mm:.0f} → "
                f"{stats.distance_finale_mm:.0f} mm "
                f"(gain {stats.gain_pourcent:.1f}%, {stats.nb_passes_2opt} passes 2-opt) "
                f"— {stats.nb_pieces} pièce(s), {stats.nb_contours} contour(s)"
            )
            if n_probleme:
                msg += (
                    f"  ⚠ {n_probleme} contour(s) sans piquage sûr "
                    f"à ≥ {marge:.1f} mm (colorés en rouge)."
                )
            self._statut(msg)

            if n_probleme:
                QMessageBox.warning(
                    self,
                    "Piquage trop proche d'une pièce voisine",
                    f"{n_probleme} contour(s) n'ont pas pu trouver de point "
                    f"de départ permettant un lead-in à ≥ {marge:.1f} mm "
                    f"des pièces voisines.\n\n"
                    "Ces contours sont colorés en rouge dans la vue nesting.\n\n"
                    "Solutions : augmenter la marge de nesting, relancer le "
                    "nesting, ou réduire la longueur du lead-in."
                )

            self._mettre_a_jour_etat_boutons()

        except Exception as e:
            logger.exception("Erreur lors du calcul de trajectoire")
            self._erreur("Erreur trajectoire", str(e))

    def _generer_gcode(self) -> None:
        """Lance la génération du GCode (utilise la trajectoire optimisée)."""
        if not self._contours_ordonnes:
            # Si pas encore calculée, la calculer à la volée
            if not self._contours_places:
                self._avertissement(
                    "Aucun nesting",
                    "Veuillez d'abord calculer le nesting."
                )
                return
            self._calculer_trajectoires()
            if not self._contours_ordonnes:
                return

        params = self._params_panel.get_params()
        mode_sim = params.get('mode_simulation', False)
        self._statut("Génération du GCode en cours…")

        try:
            from core.gcode_generator import generer

            entrees = self._dxf_list_panel.get_entrees()
            if entrees:
                nom_prog = Path(entrees[0].chemin).stem.upper()
                if len(entrees) > 1:
                    nom_prog += f"_PLUS{len(entrees)-1}"
            else:
                nom_prog = "PROGRAMME"

            self._gcode = generer(
                contours_places=self._contours_ordonnes,
                params=params,
                nom_programme=nom_prog,
                mode_simulation=mode_sim,
            )

            n_lignes = self._gcode.count('\n')
            sim_str = " [SIMULATION]" if mode_sim else ""
            self._statut(
                f"✓ GCode généré{sim_str} — {n_lignes} lignes. "
                f"Cliquez sur 'Exporter .iso' pour sauvegarder."
            )

            # Charger le GCode dans le viewer et basculer la vue de gauche
            self._gcode_viewer.set_gcode(self._gcode)
            self._afficher_vue_gcode()

            self._mettre_a_jour_etat_boutons()

        except Exception as e:
            logger.exception("Erreur lors de la génération GCode")
            self._erreur("Erreur génération GCode", f"{e}")

    def _exporter_gcode(self) -> None:
        """Exporte le GCode dans un fichier .iso."""
        if not self._gcode:
            self._avertissement("Aucun GCode", "Veuillez d'abord générer le GCode.")
            return

        from utils.file_io import generer_nom_fichier
        entrees = self._dxf_list_panel.get_entrees()
        chemin_dxf = entrees[0].chemin if entrees else None
        nom_defaut = generer_nom_fichier(chemin_dxf=chemin_dxf)

        chemin, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter le GCode",
            nom_defaut,
            "Programmes ISO (*.iso);;Tous les fichiers (*)",
        )
        if not chemin:
            return

        try:
            from utils.file_io import sauvegarder_gcode
            chemin_final = sauvegarder_gcode(self._gcode, chemin)
            taille = os.path.getsize(chemin_final)
            self._statut(
                f"✓ GCode exporté : '{os.path.basename(chemin_final)}' ({taille} octets)"
            )
            QMessageBox.information(
                self,
                "Export réussi",
                f"Le fichier GCode a été sauvegardé :\n{chemin_final}",
            )
        except Exception as e:
            logger.exception("Erreur lors de l'export GCode")
            self._erreur("Erreur d'export", str(e))

    def _afficher_preview_gcode(self) -> None:
        """Affiche la fenêtre de prévisualisation du GCode."""
        if not self._gcode:
            self._avertissement("Aucun GCode", "Générez d'abord le GCode.")
            return
        dialogue = DialoguePreviewGCode(self._gcode, self)
        dialogue.exec()

    # -----------------------------------------------------------------------
    # Gestion des paramètres
    # -----------------------------------------------------------------------

    def _on_params_changed(self, params: dict) -> None:
        """Invalide le GCode quand les paramètres changent."""
        if self._gcode is not None:
            self._gcode = None
            self._mettre_a_jour_etat_boutons()
            self._statut("Paramètres modifiés — regénérez le GCode.")

    # -----------------------------------------------------------------------
    # État des boutons
    # -----------------------------------------------------------------------

    def _mettre_a_jour_etat_boutons(self) -> None:
        """Active/désactive les boutons selon l'état courant."""
        a_dxf = bool(self._dxf_list_panel.get_entrees())
        a_nesting = bool(self._contours_places)
        a_trajectoire = bool(self._contours_ordonnes)
        a_gcode = bool(self._gcode)

        # Le bouton nesting est désactivé si un thread tourne ;
        # après un arrêt utilisateur on considère le nesting comme terminé
        # même si le thread met encore quelques centaines de ms à sortir.
        nesting_en_cours = (not self._nesting_force_arrete) and (
            (self._thread_nesting is not None and self._thread_nesting.isRunning())
            or (self._thread_nesting_sparrow is not None
                and self._thread_nesting_sparrow.isRunning())
        )

        self._btn_nesting.setEnabled(a_dxf and not nesting_en_cours)
        self._btn_trajectoire.setEnabled(a_nesting and not nesting_en_cours)
        self._btn_generer.setEnabled(a_trajectoire)
        self._btn_exporter.setEnabled(a_gcode)
        self._action_exporter.setEnabled(a_gcode)
        self._action_preview.setEnabled(a_gcode)

    # -----------------------------------------------------------------------
    # Utilitaires UI
    # -----------------------------------------------------------------------

    def _statut(self, msg: str) -> None:
        self._lbl_statut.setText(msg)
        logger.info(msg)

    def _erreur(self, titre: str, message: str) -> None:
        logger.error(f"{titre} : {message}")
        QMessageBox.critical(self, titre, message)
        self._statut(f"✗ Erreur : {titre}")

    def _avertissement(self, titre: str, message: str) -> None:
        QMessageBox.warning(self, titre, message)

    def _afficher_a_propos(self) -> None:
        QMessageBox.about(
            self,
            "À propos de Remocut ISO Generator",
            "<b>Remocut ISO Generator</b><br><br>"
            "Générateur de programmes GCode ISO pour la machine<br>"
            "<b>REMOCUT II – h2o</b> / Contrôleur Eurosoft ECP1000<br><br>"
            "Polytech Nancy — Usage atelier<br><br>"
            "Stack technique : Python 3.11+ · PyQt6 · ezdxf · shapely",
        )

    def charger_fichier(self, chemin: str) -> None:
        """
        Charge un fichier DXF programmatiquement (depuis argv ou menu récents).

        Args:
            chemin: Chemin vers le fichier .dxf à charger.
        """
        if not os.path.isfile(chemin):
            logger.warning(f"Fichier introuvable : '{chemin}'")
            # Si le fichier manque, l'enlever des récents
            self._retirer_fichier_recent(chemin)
            return
        try:
            from utils.file_io import charger_dxf
            contours = charger_dxf(chemin, tolerance_fermeture=0.01)
            entree = EntreeDxf(
                chemin=chemin,
                nom=os.path.basename(chemin),
                contours=contours,
                quantite=1,
            )
            self._dxf_list_panel.ajouter_entree(entree)
            self._ajouter_fichier_recent(chemin)
        except Exception as e:
            logger.error(f"Erreur chargement '{chemin}' : {e}")
            self._erreur("Erreur chargement DXF", str(e))

    # -----------------------------------------------------------------------
    # Fichiers récents (QSettings)
    # -----------------------------------------------------------------------

    _MAX_RECENTS = 10
    _CLE_RECENTS = "recent_files"

    def _lire_fichiers_recents(self) -> List[str]:
        """Lit la liste des fichiers récents depuis QSettings."""
        s = QSettings()
        val = s.value(self._CLE_RECENTS, [])
        if isinstance(val, str):
            val = [val] if val else []
        elif val is None:
            val = []
        # Filtrer seulement les chemins existants
        return [p for p in val if isinstance(p, str) and p]

    def _ecrire_fichiers_recents(self, chemins: List[str]) -> None:
        """Sauvegarde la liste des fichiers récents dans QSettings."""
        s = QSettings()
        s.setValue(self._CLE_RECENTS, chemins[: self._MAX_RECENTS])

    def _ajouter_fichier_recent(self, chemin: str) -> None:
        """Ajoute un chemin en tête de la liste des récents (max 10, sans doublons)."""
        chemin = os.path.abspath(chemin)
        recents = self._lire_fichiers_recents()
        # Dédoublonner (insensible à la casse sous Windows)
        recents = [p for p in recents if os.path.normcase(p) != os.path.normcase(chemin)]
        recents.insert(0, chemin)
        self._ecrire_fichiers_recents(recents)
        self._reconstruire_menu_recents()

    def _retirer_fichier_recent(self, chemin: str) -> None:
        """Retire un chemin introuvable de la liste des récents."""
        recents = self._lire_fichiers_recents()
        recents = [p for p in recents
                   if os.path.normcase(p) != os.path.normcase(chemin)]
        self._ecrire_fichiers_recents(recents)
        self._reconstruire_menu_recents()

    def _reconstruire_menu_recents(self) -> None:
        """Reconstruit le sous-menu 'Fichiers récents'."""
        if not hasattr(self, '_menu_recents'):
            return
        self._menu_recents.clear()
        recents = self._lire_fichiers_recents()
        if not recents:
            action_vide = QAction("(aucun)", self)
            action_vide.setEnabled(False)
            self._menu_recents.addAction(action_vide)
            return
        for i, chemin in enumerate(recents):
            nom = os.path.basename(chemin)
            action = QAction(f"&{i + 1}  {nom}", self)
            action.setStatusTip(chemin)
            action.setToolTip(chemin)
            # Capture du chemin par défaut de paramètre
            action.triggered.connect(lambda _checked=False, c=chemin: self.charger_fichier(c))
            self._menu_recents.addAction(action)
        self._menu_recents.addSeparator()
        action_clear = QAction("Effacer la liste", self)
        action_clear.triggered.connect(self._effacer_fichiers_recents)
        self._menu_recents.addAction(action_clear)

    def _effacer_fichiers_recents(self) -> None:
        """Vide la liste des fichiers récents."""
        self._ecrire_fichiers_recents([])
        self._reconstruire_menu_recents()


class DialoguePreviewGCode(QDialog):
    """Fenêtre de prévisualisation du GCode généré."""

    def __init__(self, gcode: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prévisualisation GCode — ECP1000")
        self.setMinimumSize(700, 500)
        self.resize(820, 620)

        layout = QVBoxLayout(self)

        n_lignes = gcode.count('\n')
        lbl = QLabel(f"Programme GCode ({n_lignes} lignes) :")
        lbl.setStyleSheet("font-weight: bold; margin-bottom: 4px;")
        layout.addWidget(lbl)

        self._editeur = QPlainTextEdit()
        self._editeur.setReadOnly(True)
        self._editeur.setFont(QFont("Courier New", 10))
        self._editeur.setPlainText(gcode)
        self._editeur.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._editeur)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)

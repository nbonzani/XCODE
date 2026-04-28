"""
ui/params_panel.py — Panneau de paramètres de découpe.

QWidget avec QFormLayout permettant la saisie de tous les paramètres
nécessaires à la génération GCode (matériau, vitesse, kerf, lead-in, tôle, etc.).

Signal émis : params_changed(dict) — déclenché à chaque modification.
"""

import logging
from typing import Optional

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.machine_params import get_defaults, liste_epaisseurs, liste_materiaux

logger = logging.getLogger(__name__)

# Correspondance index combo → identifiant méthode nesting
_MODE_NESTING_INDEX_VERS_ID = {
    0: 'simple',
    1: 'aire',
    2: 'perimetre',
    3: 'dim_max',
    4: 'multi',
    5: 'sparrow_moy',
    6: 'sparrow_max',
}
_MODE_NESTING_VERS_INDEX = {v: k for k, v in _MODE_NESTING_INDEX_VERS_ID.items()}


class ParamsPanel(QWidget):
    """
    Panneau de saisie des paramètres de découpe plasma.

    Signaux :
        params_changed(dict) : émis quand un paramètre est modifié.
    """

    params_changed = pyqtSignal(dict)

    # Préfixe QSettings pour les valeurs utilisateur (persistantes entre sessions)
    _CLE_PARAMS = "user_params"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._construction_en_cours = False
        # Bloque la persistance QSettings tant que la restauration n'est pas faite :
        # sinon l'émission finale de _charger_defaults() écraserait les valeurs
        # sauvegardées lors de la session précédente avant qu'on puisse les lire.
        self._initialisation_terminee = False
        self._construire_ui()
        self._connecter_signaux()
        self._charger_defaults()
        # Restaurer les valeurs modifiées précédemment par l'utilisateur,
        # qui deviennent ainsi les valeurs par défaut pour la suite.
        self._restaurer_params_utilisateur()
        # À partir d'ici, toute modification utilisateur sera persistée.
        self._initialisation_terminee = True

    # -----------------------------------------------------------------------
    # Construction de l'interface
    # -----------------------------------------------------------------------

    def _construire_ui(self) -> None:
        """Construit le layout et tous les widgets du panneau."""
        layout_principal = QHBoxLayout(self)
        layout_principal.setContentsMargins(6, 6, 6, 6)
        layout_principal.setSpacing(12)

        # --- Groupe Matériau ---
        grp_mat = QGroupBox("Matériau")
        form_mat = QFormLayout(grp_mat)
        form_mat.setSpacing(6)

        self.combo_materiau = QComboBox()
        self.combo_materiau.addItems(liste_materiaux())
        form_mat.addRow("Matériau :", self.combo_materiau)

        self.combo_epaisseur = QComboBox()
        form_mat.addRow("Épaisseur (mm) :", self.combo_epaisseur)

        self.spin_vitesse = QDoubleSpinBox()
        self.spin_vitesse.setRange(100, 20000)
        self.spin_vitesse.setSuffix(" mm/min")
        self.spin_vitesse.setDecimals(0)
        self.spin_vitesse.setSingleStep(100)
        form_mat.addRow("Vitesse coupe :", self.spin_vitesse)

        self.spin_kerf = QDoubleSpinBox()
        self.spin_kerf.setRange(0.1, 10.0)
        self.spin_kerf.setSuffix(" mm")
        self.spin_kerf.setDecimals(2)
        self.spin_kerf.setSingleStep(0.1)
        form_mat.addRow("Kerf :", self.spin_kerf)

        self.spin_piercing = QSpinBox()
        self.spin_piercing.setRange(0, 5000)
        self.spin_piercing.setSuffix(" ms")
        self.spin_piercing.setSingleStep(100)
        form_mat.addRow("Délai piercing :", self.spin_piercing)

        layout_principal.addWidget(grp_mat)

        # --- Groupe Lead-in / Lead-out ---
        grp_lead = QGroupBox("Lead-in / Lead-out")
        form_lead = QFormLayout(grp_lead)
        form_lead.setSpacing(6)

        self.spin_lead_in = QDoubleSpinBox()
        self.spin_lead_in.setRange(0.5, 50.0)
        self.spin_lead_in.setSuffix(" mm")
        self.spin_lead_in.setDecimals(1)
        self.spin_lead_in.setSingleStep(0.5)
        form_lead.addRow("Longueur lead-in :", self.spin_lead_in)

        self.combo_type_lead_in = QComboBox()
        self.combo_type_lead_in.addItems(["Linéaire", "Arc"])
        form_lead.addRow("Type lead-in :", self.combo_type_lead_in)

        self.spin_lead_out = QDoubleSpinBox()
        self.spin_lead_out.setRange(0.5, 50.0)
        self.spin_lead_out.setSuffix(" mm")
        self.spin_lead_out.setDecimals(1)
        self.spin_lead_out.setSingleStep(0.5)
        form_lead.addRow("Longueur lead-out :", self.spin_lead_out)

        self.combo_cote = QComboBox()
        self.combo_cote.addItems(["Gauche (G41)", "Droite (G42)"])
        self.combo_cote.setToolTip(
            "Non utilisé en V1 (compensation kerf gérée par la machine via $material)"
        )
        form_lead.addRow("Côté compensation :", self.combo_cote)

        layout_principal.addWidget(grp_lead)

        # --- Groupe Format tôle / Nesting ---
        grp_tole = QGroupBox("Format tôle & Nesting")
        form_tole = QFormLayout(grp_tole)
        form_tole.setSpacing(6)

        self.spin_tole_l = QDoubleSpinBox()
        self.spin_tole_l.setRange(100, 12000)
        self.spin_tole_l.setSuffix(" mm")
        self.spin_tole_l.setDecimals(0)
        self.spin_tole_l.setSingleStep(100)
        form_tole.addRow("Largeur tôle :", self.spin_tole_l)

        self.spin_tole_h = QDoubleSpinBox()
        self.spin_tole_h.setRange(100, 6000)
        self.spin_tole_h.setSuffix(" mm")
        self.spin_tole_h.setDecimals(0)
        self.spin_tole_h.setSingleStep(100)
        form_tole.addRow("Hauteur tôle :", self.spin_tole_h)

        self.spin_marge = QDoubleSpinBox()
        self.spin_marge.setRange(0, 100)
        self.spin_marge.setSuffix(" mm")
        self.spin_marge.setDecimals(1)
        self.spin_marge.setSingleStep(1.0)
        form_tole.addRow("Marge nesting :", self.spin_marge)

        self.combo_nesting_mode = QComboBox()
        self.combo_nesting_mode.addItems([
            "Simple  (sans rotation)",
            "Optimisé — Aire décroissante",
            "Optimisé — Périmètre décroissant",
            "Optimisé — Dim. max. décroissante",
            "Optimisé — Multi-séquençage",
            "Sparrow — Moyenne  (45°, 1 min)",
            "Sparrow — Maxi  (1°, 10 min)",
        ])
        self.combo_nesting_mode.setToolTip(
            "Simple : placement en rangées, sans rotation.\n"
            "Optimisé : Bottom-Left Fill + 12 rotations, minimise la boîte englobante.\n"
            "  • Aire / Périmètre / Dim. max. : 1 séquence de tri, calcul rapide.\n"
            "  • Multi-séquençage : essaie 4 ordres de tri, retient le meilleur.\n"
            "Sparrow : algorithme mondial 2025 (Gardeyn et al., EJOR). Nécessite spyrrow.\n"
            "  • Moyenne : 8 rotations (0°→315° par 45°), 1 minute max.\n"
            "  • Maxi : 360 rotations (1° par 1°), 10 minutes max."
        )
        form_tole.addRow("Mode nesting :", self.combo_nesting_mode)

        # Bouton "Valeurs par défaut"
        self.btn_defaults = QPushButton("Appliquer valeurs par défaut")
        self.btn_defaults.setToolTip(
            "Recharge les valeurs par défaut pour le matériau et l'épaisseur sélectionnés"
        )
        form_tole.addRow("", self.btn_defaults)

        layout_principal.addWidget(grp_tole)

        # Mode simulation
        grp_sim = QGroupBox("Options")
        form_sim = QFormLayout(grp_sim)

        from PyQt6.QtWidgets import QCheckBox
        self.check_simulation = QCheckBox("Mode simulation à blanc")
        self.check_simulation.setToolTip(
            "Les codes torche (M17, M20, M21, M18) sont remplacés par des commentaires. "
            "Permet de tester le déplacement machine sans allumer la torche."
        )
        form_sim.addRow(self.check_simulation)

        layout_principal.addWidget(grp_sim)
        layout_principal.addStretch()

    def _connecter_signaux(self) -> None:
        """Connecte tous les signaux de changement de valeur."""
        self.combo_materiau.currentTextChanged.connect(self._on_materiau_change)
        self.combo_epaisseur.currentTextChanged.connect(self._emettre_changement)

        self.spin_vitesse.valueChanged.connect(self._emettre_changement)
        self.spin_kerf.valueChanged.connect(self._emettre_changement)
        self.spin_piercing.valueChanged.connect(self._emettre_changement)
        self.spin_lead_in.valueChanged.connect(self._emettre_changement)
        self.combo_type_lead_in.currentTextChanged.connect(self._emettre_changement)
        self.spin_lead_out.valueChanged.connect(self._emettre_changement)
        self.combo_cote.currentIndexChanged.connect(self._emettre_changement)
        self.spin_tole_l.valueChanged.connect(self._emettre_changement)
        self.spin_tole_h.valueChanged.connect(self._emettre_changement)
        self.spin_marge.valueChanged.connect(self._emettre_changement)
        self.combo_nesting_mode.currentIndexChanged.connect(self._emettre_changement)
        self.check_simulation.stateChanged.connect(self._emettre_changement)

        self.btn_defaults.clicked.connect(self._charger_defaults)

    # -----------------------------------------------------------------------
    # Slots
    # -----------------------------------------------------------------------

    def _on_materiau_change(self, materiau: str) -> None:
        """Met à jour la liste des épaisseurs quand le matériau change."""
        self._construction_en_cours = True
        self.combo_epaisseur.clear()
        epaisseurs = liste_epaisseurs(materiau)
        for ep in epaisseurs:
            self.combo_epaisseur.addItem(f"{ep:g}", ep)
        # Sélectionner 3mm par défaut si disponible
        idx_3 = self.combo_epaisseur.findText("3")
        if idx_3 >= 0:
            self.combo_epaisseur.setCurrentIndex(idx_3)
        self._construction_en_cours = False
        self._charger_defaults()

    def _charger_defaults(self) -> None:
        """Charge les valeurs par défaut pour le matériau et l'épaisseur sélectionnés."""
        self._construction_en_cours = True
        try:
            materiau = self.combo_materiau.currentText()
            epaisseur = self.combo_epaisseur.currentData()
            if epaisseur is None:
                return
            params = get_defaults(materiau, float(epaisseur))

            self.spin_vitesse.setValue(params.get('vitesse_coupe', 2500))
            self.spin_kerf.setValue(params.get('kerf', 1.5))
            self.spin_piercing.setValue(int(params.get('delai_piercing', 500)))
            self.spin_lead_in.setValue(params.get('longueur_lead_in', 5.0))
            self.spin_lead_out.setValue(params.get('longueur_lead_out', 5.0))
            self.spin_tole_l.setValue(params.get('largeur_tole', 3000.0))
            self.spin_tole_h.setValue(params.get('hauteur_tole', 1500.0))
            self.spin_marge.setValue(params.get('marge_nesting', 10.0))

            type_lead = params.get('type_lead_in', 'lineaire')
            self.combo_type_lead_in.setCurrentIndex(
                0 if 'lin' in type_lead.lower() else 1
            )

            cote = params.get('cote_compensation', 'gauche')
            self.combo_cote.setCurrentIndex(0 if 'gauche' in cote.lower() else 1)

            logger.debug(f"Valeurs par défaut chargées : {materiau} {epaisseur}mm")
        except Exception as e:
            logger.warning(f"Erreur chargement des valeurs par défaut : {e}")
        finally:
            self._construction_en_cours = False
            self._emettre_changement()

    def _emettre_changement(self, *args) -> None:
        """Émet le signal params_changed avec le dictionnaire de paramètres courant."""
        if self._construction_en_cours:
            return
        params = self.get_params()
        # Persister les valeurs modifiées comme nouvelles valeurs par défaut
        self._sauvegarder_params_utilisateur(params)
        self.params_changed.emit(params)

    # -----------------------------------------------------------------------
    # Persistance des paramètres utilisateur (QSettings)
    # -----------------------------------------------------------------------

    # Clés à persister (on ne sauvegarde pas 'nom_materiau_machine' qui est dérivé)
    _CLES_PERSISTANTES = (
        'materiau', 'epaisseur', 'vitesse_coupe', 'kerf', 'delai_piercing',
        'longueur_lead_in', 'type_lead_in', 'longueur_lead_out',
        'cote_compensation', 'largeur_tole', 'hauteur_tole',
        'marge_nesting', 'mode_nesting', 'mode_simulation',
    )

    def _sauvegarder_params_utilisateur(self, params: dict) -> None:
        """Sauvegarde les paramètres courants dans QSettings (seulement après init)."""
        if not self._initialisation_terminee:
            return
        s = QSettings()
        s.beginGroup(self._CLE_PARAMS)
        for cle in self._CLES_PERSISTANTES:
            if cle in params:
                s.setValue(cle, params[cle])
        s.endGroup()
        s.sync()

    def _restaurer_params_utilisateur(self) -> None:
        """
        Restaure les paramètres utilisateur depuis QSettings (s'ils existent).
        Les valeurs modifiées par l'utilisateur lors d'une session précédente
        remplacent les valeurs par défaut du matériau.
        """
        s = QSettings()
        s.beginGroup(self._CLE_PARAMS)
        cles_dispo = s.childKeys()
        if not cles_dispo:
            s.endGroup()
            return

        params: dict = {}
        for cle in self._CLES_PERSISTANTES:
            if cle in cles_dispo:
                params[cle] = s.value(cle)
        s.endGroup()

        # Convertir les types numériques (QSettings retourne des str sous Windows)
        for k in ('epaisseur', 'vitesse_coupe', 'kerf',
                  'longueur_lead_in', 'longueur_lead_out',
                  'largeur_tole', 'hauteur_tole', 'marge_nesting'):
            if k in params:
                try:
                    params[k] = float(params[k])
                except (TypeError, ValueError):
                    del params[k]
        if 'delai_piercing' in params:
            try:
                params['delai_piercing'] = int(float(params['delai_piercing']))
            except (TypeError, ValueError):
                del params['delai_piercing']
        if 'mode_simulation' in params:
            val = params['mode_simulation']
            if isinstance(val, str):
                params['mode_simulation'] = val.lower() in ('true', '1', 'yes')
            else:
                params['mode_simulation'] = bool(val)

        self.set_params(params)
        logger.info(f"Paramètres utilisateur restaurés depuis la session précédente.")

    # -----------------------------------------------------------------------
    # Accès aux paramètres
    # -----------------------------------------------------------------------

    def get_params(self) -> dict:
        """
        Retourne le dictionnaire complet des paramètres actuels.

        Returns:
            dict compatible avec gcode_generator.generer() et nesting.placer().
        """
        materiau = self.combo_materiau.currentText()
        epaisseur = self.combo_epaisseur.currentData() or 3.0
        cote_idx = self.combo_cote.currentIndex()
        type_lead_idx = self.combo_type_lead_in.currentIndex()

        # Récupérer le nom machine depuis la base
        from core.machine_params import get_defaults
        params_base = get_defaults(materiau, float(epaisseur))

        return {
            'materiau': materiau,
            'epaisseur': float(epaisseur),
            'nom_materiau_machine': params_base.get('nom_materiau_machine', 'Default'),
            'vitesse_coupe': self.spin_vitesse.value(),
            'kerf': self.spin_kerf.value(),
            'delai_piercing': self.spin_piercing.value(),
            'longueur_lead_in': self.spin_lead_in.value(),
            'type_lead_in': 'lineaire' if type_lead_idx == 0 else 'arc',
            'longueur_lead_out': self.spin_lead_out.value(),
            'cote_compensation': 'gauche' if cote_idx == 0 else 'droite',
            'largeur_tole': self.spin_tole_l.value(),
            'hauteur_tole': self.spin_tole_h.value(),
            'marge_nesting': self.spin_marge.value(),
            'mode_nesting': self._mode_nesting_id(),
            'mode_simulation': self.check_simulation.isChecked(),
        }

    def _mode_nesting_id(self) -> str:
        """Retourne l'identifiant de la méthode de nesting sélectionnée."""
        return _MODE_NESTING_INDEX_VERS_ID.get(
            self.combo_nesting_mode.currentIndex(), 'simple'
        )

    def set_params(self, params: dict) -> None:
        """
        Applique un dictionnaire de paramètres aux widgets.

        Args:
            params: Dictionnaire de paramètres (mêmes clés que get_params()).
        """
        self._construction_en_cours = True
        try:
            if 'materiau' in params:
                idx = self.combo_materiau.findText(params['materiau'])
                if idx >= 0:
                    self.combo_materiau.setCurrentIndex(idx)
            if 'epaisseur' in params:
                idx = self.combo_epaisseur.findText(str(params['epaisseur']))
                if idx < 0:
                    idx = self.combo_epaisseur.findText(f"{params['epaisseur']:g}")
                if idx >= 0:
                    self.combo_epaisseur.setCurrentIndex(idx)
            if 'vitesse_coupe' in params:
                self.spin_vitesse.setValue(float(params['vitesse_coupe']))
            if 'kerf' in params:
                self.spin_kerf.setValue(float(params['kerf']))
            if 'delai_piercing' in params:
                self.spin_piercing.setValue(int(params['delai_piercing']))
            if 'longueur_lead_in' in params:
                self.spin_lead_in.setValue(float(params['longueur_lead_in']))
            if 'longueur_lead_out' in params:
                self.spin_lead_out.setValue(float(params['longueur_lead_out']))
            if 'largeur_tole' in params:
                self.spin_tole_l.setValue(float(params['largeur_tole']))
            if 'hauteur_tole' in params:
                self.spin_tole_h.setValue(float(params['hauteur_tole']))
            if 'marge_nesting' in params:
                self.spin_marge.setValue(float(params['marge_nesting']))
            if 'mode_simulation' in params:
                self.check_simulation.setChecked(bool(params['mode_simulation']))
            if 'type_lead_in' in params:
                val = str(params['type_lead_in']).lower()
                self.combo_type_lead_in.setCurrentIndex(0 if 'lin' in val else 1)
            if 'cote_compensation' in params:
                val = str(params['cote_compensation']).lower()
                self.combo_cote.setCurrentIndex(0 if 'gauche' in val else 1)
            if 'mode_nesting' in params:
                # Accepte le string ID ('simple', 'multi', ...) ou un index entier
                val = params['mode_nesting']
                if isinstance(val, int):
                    self.combo_nesting_mode.setCurrentIndex(
                        max(0, min(val, self.combo_nesting_mode.count() - 1))
                    )
                else:
                    _idx = _MODE_NESTING_VERS_INDEX.get(str(val), 0)
                    self.combo_nesting_mode.setCurrentIndex(_idx)
        finally:
            self._construction_en_cours = False
            self._emettre_changement()

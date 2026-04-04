from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QPushButton, QLabel, QLineEdit,
    QComboBox, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt

# Langues proposées dans les filtres (code → libellé, synonymes pour la recherche)
EUROPEAN_LANGUAGES = {
    "FR": ("Francais", ["FR", "FRENCH", "FRANCE"]),
    "EN": ("Anglais",  ["EN", "ENGLISH", "UK", "US", "GB"]),
    "IT": ("Italien",  ["IT", "ITALIAN", "ITALIANO"]),
    "ES": ("Espagnol", ["ES", "SPANISH", "ESPANOL"]),
}


class FilterPanel(QWidget):
    """
    Panneau de filtres gauche.
    Le filtrage est déclenché uniquement par le bouton "Appliquer les filtres".
    """
    apply_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        self._all_groups = []

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(8)

        # --- Section type de contenu (colorée) ---
        grp_type = QGroupBox("Type de contenu")
        vbox_type = QVBoxLayout(grp_type)
        self.cb_live   = QCheckBox("Chaines live")
        self.cb_vod    = QCheckBox("Films (VOD)")
        self.cb_series = QCheckBox("Series")
        # Colorer le texte des checkboxes comme le surlignage du tableau
        self.cb_live.setStyleSheet("QCheckBox { color: #1565C0; font-weight: bold; }")
        self.cb_vod.setStyleSheet("QCheckBox { color: #2E7D32; font-weight: bold; }")
        self.cb_series.setStyleSheet("QCheckBox { color: #E65100; font-weight: bold; }")
        self.cb_live.setChecked(True)
        self.cb_vod.setChecked(True)
        self.cb_series.setChecked(True)
        vbox_type.addWidget(self.cb_live)
        vbox_type.addWidget(self.cb_vod)
        vbox_type.addWidget(self.cb_series)
        hbox_type_btns = QHBoxLayout()
        btn_type_all  = QPushButton("Tout")
        btn_type_none = QPushButton("Rien")
        btn_type_all.setFixedHeight(24)
        btn_type_none.setFixedHeight(24)
        btn_type_all.clicked.connect(
            lambda: [cb.setChecked(True)
                     for cb in [self.cb_live, self.cb_vod, self.cb_series]])
        btn_type_none.clicked.connect(
            lambda: [cb.setChecked(False)
                     for cb in [self.cb_live, self.cb_vod, self.cb_series]])
        hbox_type_btns.addWidget(btn_type_all)
        hbox_type_btns.addWidget(btn_type_none)
        vbox_type.addLayout(hbox_type_btns)
        layout.addWidget(grp_type)

        # --- Section qualité ---
        grp_qual = QGroupBox("Qualite")
        vbox_qual = QVBoxLayout(grp_qual)
        self.cb_4k      = QCheckBox("4K / UHD")
        self.cb_fhd     = QCheckBox("Full HD (1080)")
        self.cb_hd      = QCheckBox("HD (720)")
        self.cb_sd      = QCheckBox("SD")
        self.cb_unknown = QCheckBox("Non defini")
        for cb in [self.cb_4k, self.cb_fhd, self.cb_hd, self.cb_sd, self.cb_unknown]:
            cb.setChecked(True)
            vbox_qual.addWidget(cb)
        qual_cbs = [self.cb_4k, self.cb_fhd, self.cb_hd, self.cb_sd, self.cb_unknown]
        hbox_qual_btns = QHBoxLayout()
        btn_qual_all  = QPushButton("Tout")
        btn_qual_none = QPushButton("Rien")
        btn_qual_all.setFixedHeight(24)
        btn_qual_none.setFixedHeight(24)
        btn_qual_all.clicked.connect(lambda: [cb.setChecked(True) for cb in qual_cbs])
        btn_qual_none.clicked.connect(lambda: [cb.setChecked(False) for cb in qual_cbs])
        hbox_qual_btns.addWidget(btn_qual_all)
        hbox_qual_btns.addWidget(btn_qual_none)
        vbox_qual.addLayout(hbox_qual_btns)
        layout.addWidget(grp_qual)

        # --- Section catégorie ---
        grp_group = QGroupBox("Categorie")
        vbox_group = QVBoxLayout(grp_group)
        self.combo_group = QComboBox()
        self.combo_group.addItem("-- Toutes --", "")
        self.combo_group.setEditable(True)
        self.combo_group.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        vbox_group.addWidget(self.combo_group)
        layout.addWidget(grp_group)

        # --- Section langue (européennes, construite dynamiquement) ---
        grp_lang = QGroupBox("Langue (dans les categories)")
        vbox_lang = QVBoxLayout(grp_lang)
        self._lang_checkboxes = {}
        self._lang_container = QWidget()
        self._lang_layout = QVBoxLayout(self._lang_container)
        self._lang_layout.setSpacing(2)
        vbox_lang.addWidget(self._lang_container)
        hbox_lang_btns = QHBoxLayout()
        btn_lang_all  = QPushButton("Tout")
        btn_lang_none = QPushButton("Rien")
        btn_lang_all.setFixedHeight(24)
        btn_lang_none.setFixedHeight(24)
        btn_lang_all.clicked.connect(
            lambda: [cb.setChecked(True) for cb in self._lang_checkboxes.values()])
        btn_lang_none.clicked.connect(
            lambda: [cb.setChecked(False) for cb in self._lang_checkboxes.values()])
        hbox_lang_btns.addWidget(btn_lang_all)
        hbox_lang_btns.addWidget(btn_lang_none)
        vbox_lang.addLayout(hbox_lang_btns)
        layout.addWidget(grp_lang)

        # --- Recherche texte libre ---
        grp_search = QGroupBox("Recherche par nom")
        vbox_search = QVBoxLayout(grp_search)
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("Tapez un mot-cle...")
        vbox_search.addWidget(self.edit_search)
        layout.addWidget(grp_search)

        # --- Bouton Appliquer ---
        self.btn_apply = QPushButton("Appliquer les filtres")
        self.btn_apply.setFixedHeight(40)
        self.btn_apply.setStyleSheet(
            "QPushButton { background-color: #2E7D32; color: white; "
            "font-weight: bold; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #388E3C; }"
        )
        self.btn_apply.clicked.connect(self._on_apply)
        layout.addWidget(self.btn_apply)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def set_groups(self, groups: list):
        """Alimente la liste déroulante des catégories."""
        self._all_groups = groups
        self.combo_group.blockSignals(True)
        self.combo_group.clear()
        self.combo_group.addItem("-- Toutes --", "")
        for g in groups:
            self.combo_group.addItem(g, g)
        self.combo_group.blockSignals(False)

    def update_groups_from_filtered(self, filtered_entries: list):
        """Met à jour les catégories avec celles présentes dans la liste filtrée."""
        groups = sorted(set(e["group"] for e in filtered_entries if e["group"]))
        self.combo_group.blockSignals(True)
        current = self.combo_group.currentData()
        self.combo_group.clear()
        self.combo_group.addItem("-- Toutes --", "")
        for g in groups:
            self.combo_group.addItem(g, g)
        idx = self.combo_group.findData(current)
        if idx >= 0:
            self.combo_group.setCurrentIndex(idx)
        self.combo_group.blockSignals(False)

    def set_lang_codes(self, detected_codes: list):
        """Construit les cases langue : seulement les langues européennes
        qui sont effectivement présentes dans la liste brute."""
        for cb in self._lang_checkboxes.values():
            self._lang_layout.removeWidget(cb)
            cb.deleteLater()
        self._lang_checkboxes.clear()

        # Ne garder que les codes européens détectés
        for code in sorted(EUROPEAN_LANGUAGES.keys()):
            if code not in detected_codes:
                continue
            label_name, _ = EUROPEAN_LANGUAGES[code]
            cb = QCheckBox(f"{code} - {label_name}")
            cb.setChecked(True)
            if code == "FR":
                cb.setStyleSheet(
                    "QCheckBox { font-weight: bold; font-size: 13px; }"
                )
            self._lang_layout.addWidget(cb)
            self._lang_checkboxes[code] = cb

    def get_filter_config(self) -> dict:
        content_types = set()
        if self.cb_live.isChecked():   content_types.add("live")
        if self.cb_vod.isChecked():    content_types.add("vod")
        if self.cb_series.isChecked(): content_types.add("series")

        qualities = set()
        if self.cb_4k.isChecked():      qualities.add("4K")
        if self.cb_fhd.isChecked():     qualities.add("FHD")
        if self.cb_hd.isChecked():      qualities.add("HD")
        if self.cb_sd.isChecked():      qualities.add("SD")
        if self.cb_unknown.isChecked(): qualities.add("unknown")

        group_val = self.combo_group.currentData()
        if group_val is None:
            group_val = ""

        # Mots-clés langue cochés (synonymes européens)
        lang_keywords = []
        for code, cb in self._lang_checkboxes.items():
            if cb.isChecked():
                _, synonymes = EUROPEAN_LANGUAGES.get(code, ("", [code]))
                lang_keywords.extend(synonymes)

        return {
            "content_types": content_types,
            "qualities":     qualities,
            "group":         group_val,
            "lang_keywords": lang_keywords,
            "search_text":   self.edit_search.text(),
        }

    def _on_apply(self):
        self.apply_requested.emit(self.get_filter_config())

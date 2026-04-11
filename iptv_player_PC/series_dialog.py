"""
series_dialog.py - Dialogue de sélection d'un épisode pour une série.

Affiche les informations de la série, ainsi qu'un arbre des saisons
et épisodes permettant à l'utilisateur de sélectionner quoi regarder.
Le chargement des épisodes est asynchrone (thread) pour ne pas bloquer
l'interface.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
    QSplitter, QWidget, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QFont, QColor

import requests

from xtream_api import XtreamClient
from cache_db import mark_episode_watched, get_watched_episodes_set


# ============================================================
# Thread de chargement des épisodes
# ============================================================

class SeriesInfoLoader(QThread):
    """
    Thread qui charge les informations détaillées d'une série
    (saisons + épisodes) en arrière-plan pour ne pas geler l'UI.
    """

    loaded = pyqtSignal(dict)   # Signal avec les données reçues
    error  = pyqtSignal(str)    # Signal en cas d'erreur

    def __init__(self, client: XtreamClient, series_id: int):
        super().__init__()
        self.client = client
        self.series_id = series_id

    def run(self):
        """Effectue la requête API dans le thread secondaire."""
        try:
            info = self.client.get_series_info(self.series_id)
            self.loaded.emit(info)
        except Exception as e:
            self.error.emit(str(e))


# ============================================================
# Thread de chargement de l'image de couverture
# ============================================================

class CoverLoader(QThread):
    """Thread qui télécharge l'image de couverture de la série."""

    loaded = pyqtSignal(QPixmap)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            resp = requests.get(self.url, timeout=10)
            if resp.status_code == 200:
                img = QImage()
                img.loadFromData(resp.content)
                if not img.isNull():
                    self.loaded.emit(QPixmap.fromImage(img))
        except Exception:
            pass


# ============================================================
# Dialogue principal
# ============================================================

class SeriesDialog(QDialog):
    """
    Dialogue qui présente les détails d'une série et permet
    de sélectionner un épisode à lire.

    Signal émis :
        play_episode(url: str, title: str)
            → URL du flux + titre formaté de l'épisode
    """

    play_episode     = pyqtSignal(str, str)       # (url, titre complet)
    download_episode = pyqtSignal(dict, str)      # (episode_data, series_name)
    play_season      = pyqtSignal(list)           # [(url, titre), …] pour tous les épisodes
    download_season  = pyqtSignal(list, str)      # (episode_dicts, series_name)

    def __init__(self, series_data: dict, client: XtreamClient, parent=None):
        super().__init__(parent)
        self.series_data = series_data
        self.client = client

        self.setWindowTitle(series_data.get("name", "Série"))
        self.setMinimumSize(820, 580)
        self.resize(900, 620)

        self.setStyleSheet("""
            QDialog   { background-color: #0f0f1a; color: white; }
            QLabel    { color: white; }
            QTreeWidget {
                background-color: #1e1e2e;
                color: white;
                border: 1px solid #333;
                border-radius: 4px;
                font-size: 13px;
            }
            QTreeWidget::item { padding: 4px; }
            QTreeWidget::item:hover    { background-color: #2d2d44; }
            QTreeWidget::item:selected { background-color: #1565C0; }
            QScrollBar:vertical {
                background: #1e1e2e; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #444; border-radius: 4px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self._setup_ui()
        self._load_cover()
        self._load_episodes()

    # ------------------------------------------------------------------ #
    #  Interface                                                            #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        """Construit l'interface du dialogue."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ---- En-tête : image + informations générales ----
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)

        # Image de couverture
        self.lbl_cover = QLabel()
        self.lbl_cover.setFixedSize(100, 140)
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover.setStyleSheet("background-color: #1e1e2e; border-radius: 4px; color: #666;")
        self.lbl_cover.setText("🎬")
        header_layout.addWidget(self.lbl_cover)

        # Infos textuelles
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(6)

        # Titre
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        lbl_name = QLabel(self.series_data.get("name", ""))
        lbl_name.setFont(title_font)
        lbl_name.setWordWrap(True)
        info_layout.addWidget(lbl_name)

        # Métadonnées (genre, année, note)
        meta_parts = []
        if self.series_data.get("genre"):
            meta_parts.append(self.series_data["genre"])
        if self.series_data.get("release_date"):
            meta_parts.append(self.series_data["release_date"][:4])
        if self.series_data.get("rating"):
            meta_parts.append(f"⭐ {self.series_data['rating']}")
        if meta_parts:
            lbl_meta = QLabel("  |  ".join(str(p) for p in meta_parts))
            lbl_meta.setStyleSheet("color: #aaa; font-size: 12px;")
            info_layout.addWidget(lbl_meta)

        # Synopsis
        plot = self.series_data.get("plot", "")
        if plot:
            lbl_plot = QLabel(plot[:280] + ("…" if len(plot) > 280 else ""))
            lbl_plot.setWordWrap(True)
            lbl_plot.setStyleSheet("color: #ccc; font-size: 12px;")
            info_layout.addWidget(lbl_plot)

        info_layout.addStretch()
        header_layout.addWidget(info_widget)
        main_layout.addWidget(header)

        # ---- Arbre des saisons / épisodes ----
        lbl_episodes = QLabel("Saisons et épisodes")
        lbl_episodes.setStyleSheet("color: #7eb8f7; font-size: 14px; font-weight: bold;")
        main_layout.addWidget(lbl_episodes)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        main_layout.addWidget(self.tree)

        # Label de chargement (affiché pendant le chargement)
        self.lbl_loading = QLabel("⏳  Chargement des épisodes en cours…")
        self.lbl_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_loading.setStyleSheet("color: #888; font-size: 13px; padding: 10px;")
        main_layout.addWidget(self.lbl_loading)

        # ---- Boutons ----
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_close = QPushButton("Fermer")
        btn_close.setStyleSheet("""
            QPushButton { background-color: #333; color: white; border: none;
                          border-radius: 4px; padding: 9px 20px; }
            QPushButton:hover { background-color: #444; }
        """)
        btn_close.clicked.connect(self.reject)

        self.btn_download = QPushButton("⬇️  Télécharger")
        self.btn_download.setStyleSheet("""
            QPushButton { background-color: #2e7d32; color: white; border: none;
                          border-radius: 4px; padding: 9px 22px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #388e3c; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._download_action)

        self.btn_play = QPushButton("▶  Lire")
        self.btn_play.setStyleSheet("""
            QPushButton { background-color: #1565C0; color: white; border: none;
                          border-radius: 4px; padding: 9px 22px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self._play_action)

        btn_row.addWidget(btn_close)
        btn_row.addWidget(self.btn_download)
        btn_row.addWidget(self.btn_play)
        main_layout.addLayout(btn_row)

    # ------------------------------------------------------------------ #
    #  Chargement de la couverture                                         #
    # ------------------------------------------------------------------ #

    def _load_cover(self):
        """Lance le téléchargement de l'image de couverture."""
        cover_url = self.series_data.get("cover")
        if cover_url:
            self.cover_loader = CoverLoader(cover_url)
            self.cover_loader.loaded.connect(self._set_cover)
            self.cover_loader.start()

    def _set_cover(self, pixmap: QPixmap):
        """Affiche l'image de couverture une fois téléchargée."""
        scaled = pixmap.scaled(
            100, 140,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.lbl_cover.setPixmap(scaled)
        self.lbl_cover.setText("")

    # ------------------------------------------------------------------ #
    #  Chargement des épisodes                                             #
    # ------------------------------------------------------------------ #

    def _load_episodes(self):
        """Lance le chargement des épisodes en arrière-plan."""
        series_id = self.series_data.get("series_id")
        if not series_id:
            self.lbl_loading.setText("Identifiant de série introuvable.")
            return

        self.loader = SeriesInfoLoader(self.client, series_id)
        self.loader.loaded.connect(self._populate_tree)
        self.loader.error.connect(self._on_load_error)
        self.loader.start()

    def _populate_tree(self, info: dict):
        """
        Remplit l'arbre avec les saisons et épisodes reçus.

        Fonctionnalités :
          - Les épisodes déjà visionnés sont affichés en vert.
          - Après remplissage, le premier épisode non visionné est
            automatiquement sélectionné et centré.

        La structure retournée par Xtream est :
            info["episodes"] = {
                "1": [ {episode_num, title, id, container_extension, ...}, ... ],
                "2": [ ... ],
                ...
            }
        """
        self.lbl_loading.hide()
        self.tree.clear()

        episodes_by_season = info.get("episodes", {})
        if not episodes_by_season:
            self.lbl_loading.setText("Aucun épisode disponible pour cette série.")
            self.lbl_loading.show()
            return

        # Récupérer les épisodes déjà visionnés pour cette série
        series_id   = self.series_data.get("series_id", 0)
        watched_set = get_watched_episodes_set(series_id)

        # Trier les saisons numériquement
        def season_key(s):
            try:
                return int(s)
            except ValueError:
                return 0

        first_unwatched_item = None   # Premier épisode non visionné

        for season_num in sorted(episodes_by_season.keys(), key=season_key):
            eps = episodes_by_season[season_num]

            # Compter les épisodes non visionnés dans cette saison
            n_watched   = sum(1 for ep in eps if ep.get("id") in watched_set)
            n_unwatched = len(eps) - n_watched

            season_item = QTreeWidgetItem(self.tree)
            # Suffixe : progression de la saison
            if n_watched == len(eps):
                suffix = "  ✅ terminée"
                season_item.setForeground(0, QColor("#4caf50"))   # vert
            elif n_watched > 0:
                suffix = f"  {n_watched}/{len(eps)} vus"
            else:
                suffix = f"  {len(eps)} épisode{'s' if len(eps) > 1 else ''}"

            season_item.setText(
                0, f"  📂  Saison {season_num}{suffix}"
            )
            season_item.setData(0, Qt.ItemDataRole.UserRole, {
                "_type": "season",
                "season_num": season_num,
                "episodes": eps
            })

            for ep in eps:
                ep_num   = ep.get("episode_num", "?")
                ep_id    = ep.get("id")
                ep_title = ep.get("title", "") or f"Épisode {ep_num}"
                ep_item  = QTreeWidgetItem(season_item)

                if ep_id in watched_set:
                    # Épisode déjà visionné → vert + icône
                    ep_item.setText(0, f"    ✅ Ép. {ep_num}  —  {ep_title}")
                    ep_item.setForeground(0, QColor("#4caf50"))
                else:
                    ep_item.setText(0, f"    Ép. {ep_num}  —  {ep_title}")
                    if first_unwatched_item is None:
                        first_unwatched_item = ep_item

                ep_item.setData(0, Qt.ItemDataRole.UserRole, ep)

        self.tree.expandAll()
        self.tree.currentItemChanged.connect(self._on_selection_changed)

        # Sélectionner et centrer automatiquement le premier épisode non visionné
        if first_unwatched_item is not None:
            self.tree.setCurrentItem(first_unwatched_item)
            self.tree.scrollToItem(
                first_unwatched_item,
                QTreeWidget.ScrollHint.PositionAtCenter
            )
            # Activer les boutons pour cet épisode
            self.btn_play.setEnabled(True)
            self.btn_download.setEnabled(True)
            self.btn_play.setText("▶  Lire l'épisode")

    def _on_load_error(self, error_msg: str):
        """Affiche un message d'erreur en cas d'échec du chargement."""
        self.lbl_loading.setText(f"❌  Erreur lors du chargement : {error_msg}")
        self.lbl_loading.show()

    # ------------------------------------------------------------------ #
    #  Sélection et lecture                                                #
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self, current, previous):
        """
        Met à jour les boutons selon la sélection :
          - Nœud saison → "Lire la saison" / "Télécharger la saison"
          - Nœud épisode → "Lire l'épisode" / "Télécharger cet épisode"
        """
        if current is None:
            self.btn_play.setEnabled(False)
            self.btn_download.setEnabled(False)
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            # Cas inattendu
            self.btn_play.setEnabled(False)
            self.btn_download.setEnabled(False)
            return

        if isinstance(data, dict) and data.get("_type") == "season":
            n = len(data.get("episodes", []))
            self.btn_play.setText(f"▶  Lire la saison ({n} épisodes)")
            self.btn_download.setText(f"⬇️  Télécharger la saison ({n} épisodes)")
            self.btn_play.setEnabled(n > 0)
            self.btn_download.setEnabled(n > 0)
        else:
            # Épisode individuel
            self.btn_play.setText("▶  Lire l'épisode")
            self.btn_download.setText("⬇️  Télécharger cet épisode")
            self.btn_play.setEnabled(True)
            self.btn_download.setEnabled(True)

    def _on_double_click(self, item, column):
        """Double-clic : lecture directe d'un épisode (ignoré pour les nœuds saison)."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and not (isinstance(data, dict) and data.get("_type") == "season"):
            self._launch_episode(data)

    # ------------------------------------------------------------------ #
    #  Actions : boutons Lire / Télécharger                                #
    # ------------------------------------------------------------------ #

    def _play_action(self):
        """Délègue vers Lire épisode OU Lire saison selon la sélection."""
        selected = self.tree.currentItem()
        if not selected:
            return
        data = selected.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        if isinstance(data, dict) and data.get("_type") == "season":
            self._play_season_action(data)
        else:
            self._launch_episode(data)

    def _download_action(self):
        """Délègue vers Télécharger épisode OU Télécharger saison selon la sélection."""
        selected = self.tree.currentItem()
        if not selected:
            return
        data = selected.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        if isinstance(data, dict) and data.get("_type") == "season":
            self._download_season_action(data)
        else:
            series_name = self.series_data.get("name", "")
            self.download_episode.emit(data, series_name)
            self.accept()

    # ------------------------------------------------------------------ #
    #  Lecture                                                              #
    # ------------------------------------------------------------------ #

    def _launch_episode(self, episode: dict):
        """
        Construit l'URL de l'épisode, l'enregistre comme visionné,
        puis émet play_episode et ferme le dialogue.
        """
        stream_id = episode.get("id")
        ext = episode.get("container_extension", "mkv")
        url = self.client.get_episode_url(stream_id, ext)

        series_name = self.series_data.get("name", "")
        series_id   = self.series_data.get("series_id", 0)
        ep_title    = episode.get("title", "") or f"Épisode {episode.get('episode_num', '')}"
        full_title  = f"{series_name}  —  {ep_title}"

        # Marquer l'épisode comme visionné AVANT d'émettre le signal
        if stream_id and series_id:
            mark_episode_watched(stream_id, series_id)

        self.play_episode.emit(url, full_title)
        self.accept()

    def _play_season_action(self, season_data: dict):
        """
        Construit la liste de toutes les URLs de la saison,
        marque tous les épisodes comme visionnés,
        et émet play_season([(url, title), …]).
        """
        series_name = self.series_data.get("name", "")
        series_id   = self.series_data.get("series_id", 0)
        episodes    = season_data.get("episodes", [])
        url_title_pairs = []
        for ep in episodes:
            stream_id = ep.get("id")
            ext       = ep.get("container_extension", "mkv")
            url       = self.client.get_episode_url(stream_id, ext)
            ep_title  = ep.get("title", "") or f"Épisode {ep.get('episode_num', '')}"
            full_title = f"{series_name}  —  {ep_title}"
            url_title_pairs.append((url, full_title))
            # Marquer chaque épisode de la saison comme visionné
            if stream_id and series_id:
                mark_episode_watched(stream_id, series_id)

        self.play_season.emit(url_title_pairs)
        self.accept()

    def _download_season_action(self, season_data: dict):
        """Émet download_season avec la liste des épisodes de la saison."""
        series_name = self.series_data.get("name", "")
        episodes    = season_data.get("episodes", [])
        self.download_season.emit(episodes, series_name)
        self.accept()

from urllib.parse import urlparse

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTabWidget, QStatusBar, QMenuBar, QMenu,
    QFileDialog, QMessageBox, QLabel,
    QPlainTextEdit, QPushButton, QSplitter
)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction, QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextOption
)

from core.m3u_parser import parse_m3u
from core.filters import (
    apply_filters, apply_filters_no_groups,
    extract_groups, extract_lang_keywords,
)
from core.exporter import export_m3u, append_m3u, export_csv
from core.config_manager import (
    add_recent_file, get_recent_files,
    save_m3u_cache, load_m3u_cache, clear_m3u_cache,
    save_ratings_cache, load_ratings_cache,
    save_config,
)
from ui.channel_table import ChannelTable
from ui.filter_panel import FilterPanel
from ui.connection_dialog import ConnectionDialog
from ui.vlc_player import VLCPlayerWindow
from ui.spinner_widget import SpinnerWidget
from ui.download_dialog import DownloadDialog
from ui.loading_overlay import LoadingOverlay
from core.xtream_client import XtreamClient


def _extract_connection_from_url(url: str) -> dict | None:
    """
    Extrait serveur/login/mot de passe depuis une URL Xtream Codes.

    Formats supportés :
      http://server:port/login/password/stream_id
      http://server:port/live|movie|series/login/password/stream_id.ext

    Retourne {"base_url": ..., "username": ..., "password": ...} ou None.
    """
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        server = f"{parsed.scheme}://{parsed.netloc}"
        segments = [s for s in parsed.path.split("/") if s]
        if len(segments) < 3:
            return None
        return {
            "base_url": server,
            "username": segments[-3],
            "password": segments[-2],
        }
    except Exception:
        return None


# Couleurs de surlignage identiques au tableau filtré
BG_LIVE    = QColor("#DDEEFF")   # Bleu clair
BG_VOD     = QColor("#DDFFD8")   # Vert clair
BG_SERIES  = QColor("#FFF0CC")   # Orange clair


# ── Colorisation du texte M3U brut (surlignage fond coloré) ──────
class M3UHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._fmt_live = QTextCharFormat()
        self._fmt_live.setBackground(BG_LIVE)

        self._fmt_vod = QTextCharFormat()
        self._fmt_vod.setBackground(BG_VOD)

        self._fmt_series = QTextCharFormat()
        self._fmt_series.setBackground(BG_SERIES)

        self._fmt_header = QTextCharFormat()
        self._fmt_header.setForeground(QColor("#757575"))
        self._fmt_header.setFontWeight(QFont.Weight.Bold)

        self._fmt_comment = QTextCharFormat()
        self._fmt_comment.setForeground(QColor("#9E9E9E"))

    def _fmt_for_url(self, url: str):
        """Retourne le format correspondant à une URL http (ou None si non-http)."""
        if not url.lower().startswith("http"):
            return None
        lower = url.lower()
        if "/series/" in lower:
            return self._fmt_series
        if "/movie/" in lower:
            return self._fmt_vod
        return self._fmt_live

    def highlightBlock(self, text):
        if text.startswith("#EXTM3U"):
            self.setFormat(0, len(text), self._fmt_header)
            return

        if text.startswith("#EXTINF:"):
            # Couleur déterminée par la ligne URL qui suit (look-ahead)
            next_block = self.currentBlock().next()
            next_text = next_block.text() if next_block.isValid() else ""
            fmt = self._fmt_for_url(next_text)
            if fmt is not None:
                self.setFormat(0, len(text), fmt)
            return

        if text.startswith("#"):
            self.setFormat(0, len(text), self._fmt_comment)
            return

        # Ligne URL : colorée uniquement si elle commence par http
        fmt = self._fmt_for_url(text)
        if fmt is not None:
            self.setFormat(0, len(text), fmt)


# ── Thread de chargement fichier local ───────────────────────────
class FileLoadWorker(QThread):
    """Charge et parse un fichier M3U local dans un thread séparé."""
    finished      = pyqtSignal(str, list, str)   # raw_text, entries, message
    error         = pyqtSignal(str)
    phase_changed = pyqtSignal(str, str)
    read_progress = pyqtSignal(int, int, str)    # bytes_read, total, detail

    def __init__(self, filepath: str):
        super().__init__()
        self.filepath = filepath

    def run(self):
        import os
        basename = os.path.basename(self.filepath)
        try:
            total = os.path.getsize(self.filepath)

            # Phase 1 : Lecture par blocs
            self.phase_changed.emit(
                "Lecture du fichier…", basename
            )
            chunks = []
            read = 0
            with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
                while True:
                    chunk = f.read(256 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    read += len(chunk.encode("utf-8", errors="replace"))
                    pct = int(read * 100 / total) if total else 0
                    detail = f"{read / (1024*1024):.1f} / {total / (1024*1024):.1f} Mo ({pct} %)"
                    self.read_progress.emit(read, total, detail)
            content = "".join(chunks)

            # Phase 2 : Analyse
            self.phase_changed.emit(
                "Analyse du fichier M3U…",
                f"{len(content) / (1024*1024):.1f} Mo à analyser…"
            )
            entries = parse_m3u(content)

            self.finished.emit(
                content, entries,
                f"{len(entries):,} entrées chargées depuis {basename}"
            )
        except Exception as e:
            self.error.emit(str(e))


# ── Thread de chargement depuis le cache ─────────────────────────
class CacheLoadWorker(QThread):
    """Parse le texte M3U du cache et injecte les scores sauvegardés."""
    finished      = pyqtSignal(str, list, str)   # raw_text, entries, message
    phase_changed = pyqtSignal(str, str)

    def __init__(self, cached_text: str):
        super().__init__()
        self.cached_text = cached_text

    def run(self):
        self.phase_changed.emit(
            "Chargement depuis le cache…",
            "Analyse de la playlist sauvegardée…"
        )
        entries = parse_m3u(self.cached_text)

        self.phase_changed.emit(
            "Chargement depuis le cache…",
            "Injection des scores…"
        )
        ratings = load_ratings_cache()
        if ratings:
            import re as _re
            for entry in entries:
                if entry.get("rating"):
                    continue
                url = entry.get("url", "")
                match = _re.search(r'/(\d+)\.\w+$', url)
                if match:
                    sid = match.group(1)
                    if sid in ratings:
                        entry["rating"] = ratings[sid]
                        continue
                name = entry.get("name", "")
                if name in ratings:
                    entry["rating"] = ratings[name]

        self.finished.emit(
            self.cached_text, entries,
            f"{len(entries):,} entrées chargées depuis le cache"
        )


# ── Thread de chargement M3U ─────────────────────────────────────
class LoadWorker(QThread):
    finished        = pyqtSignal(str, list, dict, str)   # raw_text, entries, ratings, message
    error           = pyqtSignal(str)
    # Signaux de progression : (phase_text, detail, value, maximum)
    # value=-1 → indéterminé
    phase_changed   = pyqtSignal(str, str)
    download_progress = pyqtSignal(int, int, str)  # received, total, detail

    def __init__(self, client):
        super().__init__()
        self.client = client

    def _on_download_progress(self, received, total):
        if total > 0:
            pct = int(received * 100 / total)
            detail = f"{received / (1024*1024):.1f} / {total / (1024*1024):.1f} Mo ({pct} %)"
            self.download_progress.emit(received, total, detail)
        else:
            detail = f"{received / (1024*1024):.1f} Mo téléchargés…"
            self.download_progress.emit(received, 0, detail)

    def run(self):
        try:
            # Phase 1 : Téléchargement
            self.phase_changed.emit(
                "Téléchargement de la playlist…",
                "Connexion au serveur…"
            )
            text = self.client.download_m3u(
                progress_callback=self._on_download_progress
            )

            # Phase 2 : Analyse
            self.phase_changed.emit(
                "Analyse du fichier M3U…",
                "Extraction des entrées…"
            )
            entries = parse_m3u(text)
            self.phase_changed.emit(
                "Analyse du fichier M3U…",
                f"{len(entries):,} entrées trouvées"
            )

            # Phase 3 : Enrichissement des scores
            self.phase_changed.emit(
                "Récupération des scores…",
                "Chargement des métadonnées VOD et séries…"
            )
            ratings = {}
            try:
                vod_list = self.client.get_vod_streams()
                for item in vod_list:
                    sid = str(item.get("stream_id", ""))
                    rating = item.get("rating", "") or item.get("rating_5based", "")
                    name = item.get("name", "")
                    if rating:
                        if sid:
                            ratings[sid] = str(rating)
                        if name:
                            ratings[name] = str(rating)

                series_list = self.client.get_series_list()
                for item in series_list:
                    sid = str(item.get("series_id", ""))
                    rating = item.get("rating", "") or item.get("rating_5based", "")
                    name = item.get("name", "")
                    if rating:
                        if sid:
                            ratings[sid] = str(rating)
                        if name:
                            ratings[name] = str(rating)

                self.phase_changed.emit(
                    "Enrichissement des entrées…",
                    f"Application de {len(ratings):,} scores…"
                )

                import re
                for entry in entries:
                    if entry.get("rating"):
                        continue
                    url = entry.get("url", "")
                    match = re.search(r'/(\d+)\.\w+$', url)
                    if match:
                        sid = match.group(1)
                        if sid in ratings:
                            entry["rating"] = ratings[sid]
                            continue
                    name = entry.get("name", "")
                    if name in ratings:
                        entry["rating"] = ratings[name]
            except Exception:
                pass

            self.finished.emit(
                text, entries, ratings, f"{len(entries):,} entrées chargées"
            )
        except Exception as e:
            self.error.emit(str(e))


# ── Fenêtre principale ────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self, client):
        super().__init__()
        self.client  = client
        self._all_entries = []
        self._filtered_entries = []
        self._load_worker = None
        self._file_load_worker = None
        self._cache_load_worker = None

        self.setWindowTitle("M3U Manager")
        self.resize(1400, 900)

        # Police globale plus grande
        app_font = QFont()
        app_font.setPointSize(11)
        self.setFont(app_font)

        # ── Menu ──────────────────────────────────────────────────
        menubar = self.menuBar()
        menu_file = menubar.addMenu("Fichier")

        act_open = QAction("Ouvrir un fichier M3U…", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._open_file)
        menu_file.addAction(act_open)

        self._menu_recent = menu_file.addMenu("Fichiers récents")
        self._rebuild_recent_menu()

        act_reload = QAction("Recharger depuis le serveur", self)
        act_reload.setShortcut("F5")
        act_reload.triggered.connect(self._reload_m3u)
        menu_file.addAction(act_reload)

        act_sync = QAction("Synchroniser depuis la liste chargée…", self)
        act_sync.setShortcut("F6")
        act_sync.triggered.connect(self._sync_from_list)
        menu_file.addAction(act_sync)

        act_connection = QAction("Paramètres de connexion…", self)
        act_connection.triggered.connect(self._open_connection_dialog)
        menu_file.addAction(act_connection)

        menu_file.addSeparator()

        act_save_m3u = QAction("Enregistrer la liste filtrée (M3U)…", self)
        act_save_m3u.triggered.connect(self._save_m3u)
        menu_file.addAction(act_save_m3u)

        act_append_m3u = QAction("Ajouter la liste filtrée à un fichier M3U…", self)
        act_append_m3u.triggered.connect(self._append_m3u)
        menu_file.addAction(act_append_m3u)

        act_append_sel = QAction("Ajouter la sélection à un fichier M3U…", self)
        act_append_sel.triggered.connect(self._append_selected_m3u)
        menu_file.addAction(act_append_sel)

        act_save_csv = QAction("Exporter en CSV…", self)
        act_save_csv.triggered.connect(self._save_csv)
        menu_file.addAction(act_save_csv)

        act_download = QAction("Telecharger la selection…", self)
        act_download.setShortcut("Ctrl+D")
        act_download.triggered.connect(self._download_selected)
        menu_file.addAction(act_download)

        menu_file.addSeparator()

        act_quit = QAction("Quitter", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        menu_file.addAction(act_quit)

        # ── Widget central (splitter redimensionnable) ─────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # Panneau de filtres (gauche)
        self.filter_panel = FilterPanel()
        self.filter_panel.apply_requested.connect(self._apply_filters)
        splitter.addWidget(self.filter_panel)

        # Zone droite : bouton + onglets (dans un QWidget pour l'overlay)
        self._right_container = QWidget()
        right_layout = QVBoxLayout(self._right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(self._right_container)

        # Proportions initiales : ~30% filtres, ~70% contenu
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 1020])

        # Barre supérieure : bouton sync + bouton téléchargement
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.btn_sync = QPushButton("Synchroniser depuis la liste")
        self.btn_sync.setFixedHeight(36)
        self.btn_sync.setToolTip(
            "Extrait les paramètres de connexion de la liste chargée\n"
            "et synchronise depuis le serveur (F6)"
        )
        self.btn_sync.setStyleSheet(
            "QPushButton { background-color: #6A1B9A; color: white; "
            "font-weight: bold; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #7B1FA2; }"
        )
        self.btn_sync.clicked.connect(self._sync_from_list)
        top_bar.addWidget(self.btn_sync)

        self.btn_download = QPushButton("Telecharger la selection")
        self.btn_download.setFixedHeight(36)
        self.btn_download.setStyleSheet(
            "QPushButton { background-color: #1565C0; color: white; "
            "font-weight: bold; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #1976D2; }"
        )
        self.btn_download.clicked.connect(self._download_selected)
        top_bar.addWidget(self.btn_download)

        right_layout.addLayout(top_bar)

        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs)

        # Onglet 1 — Texte brut M3U
        self.raw_text = QPlainTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.raw_text.setFont(QFont("Consolas", 10))
        self._highlighter = M3UHighlighter(self.raw_text.document())
        self.tabs.addTab(self.raw_text, "Fichier brut")

        # Onglet 2 — Liste filtrée (tableau)
        self.table_filtered = ChannelTable()
        self.table_filtered.entry_double_clicked.connect(self._on_double_click)
        self.tabs.addTab(self.table_filtered, "Liste filtrée")

        # Lecteur VLC dans une fenetre independante
        self._vlc_window = None

        # ── Barre de statut ───────────────────────────────────────
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.lbl_status = QLabel("Prêt.")
        self.status_bar.addPermanentWidget(self.lbl_status)

        # Spinner circulaire animé (affiché pendant les traitements longs)
        self._spinner = SpinnerWidget(size=22, color="#1565C0")
        self.status_bar.addPermanentWidget(self._spinner)

        # Overlay de chargement (centré sur la zone droite, filtres restent accessibles)
        self._loading_overlay = LoadingOverlay(self._right_container)

        # Le chargement sera lancé par showEvent (fenêtre entièrement affichée)
        self._initial_load_done = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_load_done:
            self._initial_load_done = True
            # Laisser Qt finir le rendu de la fenêtre avant de lancer le chargement
            QTimer.singleShot(50, self._load_m3u)

    # ── Animation "en cours" ──────────────────────────────────────
    def _start_busy(self, message: str = ""):
        self.lbl_status.setText(message)
        self._spinner.start()

    def _stop_busy(self, message: str = ""):
        self._spinner.stop()
        if message:
            self.lbl_status.setText(message)

    def _load_m3u(self, force_reload: bool = False):
        if self.client is None:
            self.lbl_status.setText("Mode hors ligne — ouvrez un fichier M3U local.")
            self.filter_panel.btn_apply.setEnabled(True)
            return

        # Tenter de charger depuis le cache (sauf rechargement forcé)
        if not force_reload:
            cached = load_m3u_cache(
                self.client.base_url, self.client.username, self.client.password
            )
            if cached:
                self._start_busy("Chargement du cache…")
                self._loading_overlay.show_phase(
                    "Chargement depuis le cache…",
                    "Analyse de la playlist sauvegardée…"
                )
                self._cache_load_worker = CacheLoadWorker(cached)
                self._cache_load_worker.phase_changed.connect(self._on_load_phase)
                self._cache_load_worker.finished.connect(self._on_cache_load_finished)
                self._cache_load_worker.start()
                return

        self._start_busy("Téléchargement en cours…")
        # Les filtres restent accessibles pendant le chargement
        self.filter_panel.btn_apply.setEnabled(True)

        self._loading_overlay.show_phase(
            "Connexion au serveur…", "Initialisation du téléchargement…"
        )

        self._load_worker = LoadWorker(self.client)
        self._load_worker.finished.connect(self._on_load_finished)
        self._load_worker.error.connect(self._on_load_error)
        self._load_worker.phase_changed.connect(self._on_load_phase)
        self._load_worker.download_progress.connect(self._on_load_download_progress)
        self._load_worker.start()

    def _reload_m3u(self):
        """Rechargement forcé depuis le serveur (F5)."""
        self._load_m3u(force_reload=True)

    def _sync_from_list(self):
        """
        Extrait les paramètres de connexion depuis la première URL de la liste
        chargée, demande confirmation, puis synchronise depuis le serveur.
        """
        if not self._all_entries:
            QMessageBox.information(
                self, "Synchronisation",
                "Aucune liste chargée.\n"
                "Ouvrez d'abord un fichier M3U local."
            )
            return

        # Trouver la première URL HTTP valide
        sample_url = None
        for entry in self._all_entries:
            u = entry.get("url", "")
            if u.lower().startswith("http"):
                sample_url = u
                break

        if not sample_url:
            QMessageBox.warning(
                self, "Synchronisation",
                "Aucune URL HTTP trouvée dans la liste chargée."
            )
            return

        params = _extract_connection_from_url(sample_url)
        if not params:
            QMessageBox.warning(
                self, "Synchronisation",
                f"Impossible d'extraire les paramètres depuis :\n{sample_url}\n\n"
                "L'URL doit contenir au moins 3 segments de chemin."
            )
            return

        msg = (
            f"Paramètres extraits de la liste chargée :\n\n"
            f"  Serveur       : {params['base_url']}\n"
            f"  Login         : {params['username']}\n"
            f"  Mot de passe  : {params['password']}\n\n"
            f"Sauvegarder ces paramètres et synchroniser depuis le serveur ?"
        )
        reply = QMessageBox.question(
            self, "Synchronisation",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        save_config(params)
        self.client = XtreamClient(
            params["base_url"], params["username"], params["password"]
        )
        self._load_m3u(force_reload=True)

    def _on_cache_load_finished(self, raw_text, entries, message):
        self._loading_overlay.finish()
        self._on_load_finished_from_text(raw_text, entries, message)

    def _on_load_phase(self, phase_text, detail):
        self._loading_overlay.show_phase(phase_text, detail)

    def _on_load_download_progress(self, received, total, detail):
        if total > 0:
            self._loading_overlay.update_progress(received, total, detail)
        else:
            self._loading_overlay.show_phase(
                "Téléchargement de la playlist…", detail
            )

    def _on_load_finished_from_text(self, raw_text, entries, message):
        self._all_entries = entries
        self._filtered_entries = []   # réinitialiser à chaque nouveau fichier
        self.table_filtered.populate([])

        # Onglet brut
        self.raw_text.setPlainText(raw_text)

        # Alimenter les filtres avec toutes les catégories
        groups = extract_groups(entries)
        lang_codes = extract_lang_keywords(entries)
        self.filter_panel.set_groups(groups)
        self.filter_panel.set_lang_codes(lang_codes)

        self.filter_panel.btn_apply.setEnabled(True)
        self._stop_busy(
            f"Brut : {len(entries):,} entrées  |  Filtré : —  |  {message}"
        )

    def _on_load_finished(self, raw_text, entries, ratings, message):
        self._loading_overlay.finish()
        # Sauvegarder le cache M3U + scores pour la prochaine session
        if self.client is not None:
            save_m3u_cache(
                raw_text,
                self.client.base_url,
                self.client.username,
                self.client.password,
            )
            save_ratings_cache(ratings)
        self._on_load_finished_from_text(raw_text, entries, message)

    def _on_load_error(self, error_msg):
        self._loading_overlay.finish()
        self.filter_panel.btn_apply.setEnabled(True)
        self._stop_busy(f"Erreur : {error_msg}")
        QMessageBox.critical(self, "Erreur de chargement", error_msg)

    def _apply_filters(self, filter_config: dict):
        self._start_busy("Filtrage en cours…")

        # 1) Filtrer sans catégorie → déterminer les catégories disponibles
        pre_filtered = apply_filters_no_groups(self._all_entries, filter_config)
        self.filter_panel.update_groups_from_filtered(pre_filtered)

        # 2) Appliquer le filtre complet (y compris catégories cochées)
        self._filtered_entries = apply_filters(self._all_entries, filter_config)
        self.table_filtered.populate(self._filtered_entries)

        self.tabs.setCurrentIndex(1)
        self._stop_busy(
            f"Brut : {len(self._all_entries):,}  |  "
            f"Filtré : {len(self._filtered_entries):,} entrées affichées"
        )

    def _on_double_click(self, entry: dict):
        """Lance la lecture dans une fenetre VLC independante."""
        url = entry.get("url", "")
        if not url:
            return
        title = entry.get("name", "")
        if self._vlc_window is None:
            self._vlc_window = VLCPlayerWindow()
        self._vlc_window.play_url(url, title)

    def _rebuild_recent_menu(self):
        """Reconstruit le sous-menu des fichiers récents."""
        self._menu_recent.clear()
        recent = get_recent_files()
        if not recent:
            act = QAction("(aucun fichier récent)", self)
            act.setEnabled(False)
            self._menu_recent.addAction(act)
        else:
            for path in recent:
                import os
                act = QAction(os.path.basename(path), self)
                act.setToolTip(path)
                act.setData(path)
                act.triggered.connect(lambda checked, p=path: self._open_file_path(p))
                self._menu_recent.addAction(act)

    def _open_file_path(self, filepath: str):
        """Ouvre un fichier M3U par son chemin (dans un thread séparé)."""
        import os
        basename = os.path.basename(filepath)
        self._start_busy(f"Ouverture de {basename}…")
        self._loading_overlay.show_phase("Lecture du fichier…", basename)

        add_recent_file(filepath)
        self._rebuild_recent_menu()

        self._file_load_worker = FileLoadWorker(filepath)
        self._file_load_worker.phase_changed.connect(self._on_load_phase)
        self._file_load_worker.read_progress.connect(self._on_file_read_progress)
        self._file_load_worker.finished.connect(self._on_file_load_finished)
        self._file_load_worker.error.connect(self._on_file_load_error)
        self._file_load_worker.start()

    def _on_file_read_progress(self, read_bytes, total, detail):
        if total > 0:
            self._loading_overlay.update_progress(read_bytes, total, detail)
        else:
            self._loading_overlay.show_phase("Lecture du fichier…", detail)

    def _on_file_load_finished(self, raw_text, entries, message):
        self._loading_overlay.finish()
        self._on_load_finished_from_text(raw_text, entries, message)

    def _on_file_load_error(self, error_msg):
        self._loading_overlay.finish()
        self._stop_busy(f"Erreur : {error_msg}")
        QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir le fichier :\n{error_msg}")

    def _open_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un fichier M3U", "",
            "Fichiers M3U (*.m3u *.m3u8);;Tous les fichiers (*)"
        )
        if not filepath:
            return
        self._open_file_path(filepath)

    def _open_connection_dialog(self):
        dlg = ConnectionDialog(self)
        dlg.connection_changed.connect(self._on_connection_changed)
        dlg.exec()

    def _on_connection_changed(self, new_client):
        self.client = new_client
        # Nouvelle connexion → forcer le téléchargement (ignore le cache)
        self._load_m3u(force_reload=True)

    def _save_m3u(self):
        if not self._filtered_entries:
            QMessageBox.information(self, "Info", "La liste filtrée est vide.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer M3U", "", "Fichiers M3U (*.m3u *.m3u8)"
        )
        if path:
            self._start_busy("Enregistrement M3U…")
            export_m3u(self._filtered_entries, path)
            self._stop_busy(f"M3U enregistré : {path}")

    def _append_m3u(self):
        if not self._filtered_entries:
            QMessageBox.information(self, "Info", "La liste filtrée est vide.")
            return
        import os
        path, _ = QFileDialog.getOpenFileName(
            self, "Ajouter à un fichier M3U existant", "",
            "Fichiers M3U (*.m3u *.m3u8);;Tous les fichiers (*)"
        )
        if not path:
            return
        self._start_busy("Ajout en cours…")
        append_m3u(self._filtered_entries, path)
        size = os.path.getsize(path)
        self._stop_busy(
            f"{len(self._filtered_entries):,} entrées ajoutées à {os.path.basename(path)} "
            f"({size / 1024:.0f} Ko)"
        )

    def _append_selected_m3u(self):
        selected = self.table_filtered.get_selected_entries()
        if not selected:
            QMessageBox.information(
                self, "Info",
                "Selectionnez des lignes dans la liste filtree."
            )
            return
        import os
        path, _ = QFileDialog.getOpenFileName(
            self, "Ajouter la sélection à un fichier M3U existant", "",
            "Fichiers M3U (*.m3u *.m3u8);;Tous les fichiers (*)"
        )
        if not path:
            return
        self._start_busy("Ajout en cours…")
        append_m3u(selected, path)
        size = os.path.getsize(path)
        self._stop_busy(
            f"{len(selected):,} entrées ajoutées à {os.path.basename(path)} "
            f"({size / 1024:.0f} Ko)"
        )

    def _save_csv(self):
        if not self._filtered_entries:
            QMessageBox.information(
                self, "Info",
                "La liste filtrée est vide.\n"
                "Appliquez d'abord les filtres pour obtenir une liste à exporter."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter CSV", "", "Fichiers CSV (*.csv)"
        )
        if path:
            self._start_busy("Export CSV…")
            export_csv(self._filtered_entries, path)
            self._stop_busy(
                f"CSV exporté : {len(self._filtered_entries):,} entrées → {path}"
            )

    def _download_selected(self):
        selected = self.table_filtered.get_selected_entries()
        if not selected:
            QMessageBox.information(
                self, "Info",
                "Selectionnez des lignes dans la liste filtree avant de telecharger."
            )
            return

        dest_dir = QFileDialog.getExistingDirectory(
            self, "Dossier de destination"
        )
        if not dest_dir:
            return

        dlg = DownloadDialog(selected, dest_dir, self)
        dlg.exec()

    def closeEvent(self, event):
        if self._vlc_window is not None:
            self._vlc_window.close()
        super().closeEvent(event)

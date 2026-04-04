from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTabWidget, QStatusBar, QMenuBar, QMenu,
    QFileDialog, QMessageBox, QProgressDialog, QLabel,
    QPlainTextEdit, QPushButton
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import (
    QAction, QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextOption
)

from core.m3u_parser import parse_m3u
from core.filters import apply_filters, extract_groups, extract_lang_keywords
from core.exporter import export_m3u, append_m3u, export_csv
from core.config_manager import add_recent_file, get_recent_files
from ui.channel_table import ChannelTable
from ui.filter_panel import FilterPanel
from ui.connection_dialog import ConnectionDialog
from ui.vlc_player import VLCPlayerWindow
from ui.spinner_widget import SpinnerWidget
from ui.download_dialog import DownloadDialog


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


# ── Thread de chargement M3U ─────────────────────────────────────
class LoadWorker(QThread):
    finished = pyqtSignal(str, list, str)
    error    = pyqtSignal(str)

    def __init__(self, client):
        super().__init__()
        self.client = client

    def run(self):
        try:
            text = self.client.download_m3u()
            entries = parse_m3u(text)

            # Récupérer les scores depuis l'API Xtream (VOD + séries)
            try:
                ratings = {}  # stream_id ou name → rating
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

                # Injecter les scores dans les entrées parsées
                import re
                for entry in entries:
                    if entry.get("rating"):
                        continue  # Déjà un score dans le M3U
                    # Essayer par stream_id extrait de l'URL
                    url = entry.get("url", "")
                    match = re.search(r'/(\d+)\.\w+$', url)
                    if match:
                        sid = match.group(1)
                        if sid in ratings:
                            entry["rating"] = ratings[sid]
                            continue
                    # Sinon essayer par nom exact
                    name = entry.get("name", "")
                    if name in ratings:
                        entry["rating"] = ratings[name]
            except Exception:
                pass  # Les scores sont optionnels

            self.finished.emit(
                text, entries, f"{len(entries):,} entrées chargées"
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
        act_reload.triggered.connect(self._load_m3u)
        menu_file.addAction(act_reload)

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

        # ── Widget central ────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(8)

        # Panneau de filtres (gauche)
        self.filter_panel = FilterPanel()
        self.filter_panel.apply_requested.connect(self._apply_filters)
        main_layout.addWidget(self.filter_panel)

        # Zone droite : bouton + onglets
        right_layout = QVBoxLayout()
        main_layout.addLayout(right_layout, stretch=1)

        # Bouton telechargement
        self.btn_download = QPushButton("Telecharger la selection")
        self.btn_download.setFixedHeight(36)
        self.btn_download.setStyleSheet(
            "QPushButton { background-color: #1565C0; color: white; "
            "font-weight: bold; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #1976D2; }"
        )
        self.btn_download.clicked.connect(self._download_selected)
        right_layout.addWidget(self.btn_download)

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

        # ── Chargement initial ────────────────────────────────────
        self._load_m3u()

    # ── Animation "en cours" ──────────────────────────────────────
    def _start_busy(self, message: str = ""):
        self.lbl_status.setText(message)
        self._spinner.start()

    def _stop_busy(self, message: str = ""):
        self._spinner.stop()
        if message:
            self.lbl_status.setText(message)

    def _load_m3u(self):
        if self.client is None:
            self.lbl_status.setText("Mode hors ligne — ouvrez un fichier M3U local.")
            self.filter_panel.btn_apply.setEnabled(True)
            return

        self._start_busy("Téléchargement en cours…")
        self.filter_panel.btn_apply.setEnabled(False)

        self._load_worker = LoadWorker(self.client)
        self._load_worker.finished.connect(self._on_load_finished)
        self._load_worker.error.connect(self._on_load_error)
        self._load_worker.start()

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

    def _on_load_finished(self, raw_text, entries, message):
        self._on_load_finished_from_text(raw_text, entries, message)

    def _on_load_error(self, error_msg):
        self.filter_panel.btn_apply.setEnabled(True)
        self._stop_busy(f"Erreur : {error_msg}")
        QMessageBox.critical(self, "Erreur de chargement", error_msg)

    def _apply_filters(self, filter_config: dict):
        self._start_busy("Filtrage en cours…")
        self._filtered_entries = apply_filters(self._all_entries, filter_config)
        self.table_filtered.populate(self._filtered_entries)

        # Mettre à jour les catégories avec seulement celles de la liste filtrée
        self.filter_panel.update_groups_from_filtered(self._filtered_entries)

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
        """Ouvre un fichier M3U par son chemin."""
        self._start_busy(f"Ouverture de {filepath}…")
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            self._stop_busy()
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir le fichier :\n{e}")
            return
        add_recent_file(filepath)
        self._rebuild_recent_menu()
        import os
        entries = parse_m3u(content)
        self._on_load_finished_from_text(
            content, entries,
            f"{len(entries):,} entrées chargées depuis {os.path.basename(filepath)}"
        )

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
        self._load_m3u()

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

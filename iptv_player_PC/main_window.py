"""
main_window.py - Fenêtre principale de l'application IPTV Player.

Architecture :
  - Barre de recherche et filtres (nom, catégorie, année, FR uniquement)
  - Onglets Films / Séries
  - Grille de vignettes avec posters et titres
  - Thread de synchronisation asynchrone du catalogue
  - Pool de threads limité à 8 pour le chargement des posters
"""

import requests

import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLineEdit, QPushButton, QComboBox,
    QLabel, QScrollArea, QGridLayout, QFrame,
    QMessageBox, QStatusBar, QSizePolicy, QApplication,
    QListWidget, QListWidgetItem, QMenu
)
from PyQt6.QtCore import (
    Qt, QThread, QThreadPool, QRunnable,
    pyqtSignal, pyqtSlot, QObject, QTimer, QSize
)
from PyQt6.QtGui import QPixmap, QImage, QAction

from config import load_config, save_config, is_configured
from xtream_api import XtreamClient
from cache_db import (
    initialize_db,
    save_vod_categories, save_movies,
    save_series_categories, save_series_list,
    search_movies, search_series,
    get_vod_categories_list, get_series_categories_list,
    get_movie_count, get_series_count,
    clear_cache,
    get_thumbnail_path,
    save_thumbnail_from_bytes,
    get_items_without_thumbnail,
    needs_sync, set_last_sync_date, get_last_sync_date,
    add_download, get_downloads, delete_download
)
from settings_dialog import SettingsDialog
from player_window import PlayerWindow
from series_dialog import SeriesDialog
from play_options_dialog import PlayOptionsDialog
from download_manager import (
    DownloadProgressDialog, SeasonDownloadDialog,
    get_download_path, DOWNLOADS_DIR, MOVIES_DIR,
    get_series_dir, _safe_filename
)


# ============================================================
# Pool de threads pour le chargement des posters
# ============================================================
# Un seul pool partagé par toute l'application.
# maxThreadCount = 8 : au maximum 8 images téléchargées en même temps.
# Cela évite de lancer 300 threads en parallèle, qui planteraient le système.
_POSTER_POOL = QThreadPool()
_POSTER_POOL.setMaxThreadCount(8)


# ============================================================
# Thread : synchronisation du catalogue
# ============================================================

class SyncThread(QThread):
    """
    Thread qui récupère le catalogue complet depuis le serveur Xtream
    et le sauvegarde dans la base de données locale.

    Tourne en arrière-plan pour ne pas geler l'interface.
    """

    progress = pyqtSignal(str)       # Message d'avancement
    finished = pyqtSignal(bool, str) # (succès, message)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config

    def run(self):
        try:
            client = XtreamClient(
                server_url=self.config["server_url"],
                port=self.config["port"],
                username=self.config["username"],
                password=self.config["password"]
            )

            self.progress.emit("Connexion au serveur…")
            client.authenticate()

            self.progress.emit("Récupération des catégories de films…")
            vod_cats = client.get_vod_categories()
            save_vod_categories(vod_cats)
            vod_cats_map = {str(c["category_id"]): c["category_name"] for c in vod_cats}

            self.progress.emit(f"Récupération des films… ({len(vod_cats)} catégories)")
            movies = client.get_vod_streams()
            save_movies(movies, vod_cats_map)

            self.progress.emit("Récupération des catégories de séries…")
            ser_cats = client.get_series_categories()
            save_series_categories(ser_cats)
            ser_cats_map = {str(c["category_id"]): c["category_name"] for c in ser_cats}

            self.progress.emit("Récupération des séries…")
            series = client.get_series()
            save_series_list(series, ser_cats_map)

            n_films  = get_movie_count(french_only=False)
            n_series = get_series_count(french_only=False)

            # Enregistrer la date de synchronisation réussie.
            # Les vignettes sont téléchargées séparément par ThrottledThumbnailThread
            # pour ne pas ralentir la synchronisation des titres.
            set_last_sync_date()

            self.finished.emit(
                True,
                f"Synchronisation terminée : {n_films} film(s) et {n_series} série(s)."
            )

        except Exception as e:
            self.finished.emit(False, str(e))


# ============================================================
# Chargement des posters via QThreadPool (remplace QThread)
# ============================================================
# Pourquoi QRunnable + QThreadPool plutôt que QThread ?
#   - QThread crée un thread OS complet pour chaque image.
#     300 images = 300 threads → plantage garanti sous Windows.
#   - QThreadPool réutilise un pool de N threads (ici 8).
#     300 images → 8 threads qui traitent les images une par une,
#     dans l'ordre, sans surcharger le système.

class _PosterSignals(QObject):
    """
    QObject portant le signal loaded.
    Nécessaire car QRunnable n'hérite pas de QObject
    et ne peut donc pas définir de signaux directement.
    """
    loaded = pyqtSignal(QPixmap)


class PosterLoader(QRunnable):
    """
    Tâche de téléchargement d'un poster, exécutée dans le pool _POSTER_POOL.

    En plus d'émettre le QPixmap pour l'affichage immédiat, sauvegarde
    automatiquement l'image sur le disque (cache local) pour éviter de
    retélécharger lors des prochains affichages.

    Utilisation :
        loader = PosterLoader(url, item_id, item_type)
        loader.signals.loaded.connect(ma_fonction)
        _POSTER_POOL.start(loader)
    """

    def __init__(self, url: str, item_id: int = None, item_type: str = "movie"):
        super().__init__()
        self.url       = url
        self.item_id   = item_id
        self.item_type = item_type
        self.signals   = _PosterSignals()
        # autoDelete=True : Qt libère l'objet après run() automatiquement
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        """
        Télécharge l'image, émet le signal loaded avec le QPixmap,
        et sauvegarde l'image sur le disque pour le cache local.
        """
        try:
            resp = requests.get(self.url, timeout=8)
            if resp.status_code == 200:
                content = resp.content

                # Persistance sur le disque : évite de retélécharger à chaque démarrage
                if self.item_id:
                    save_thumbnail_from_bytes(
                        self.url, self.item_id, self.item_type, content
                    )

                img = QImage()
                img.loadFromData(content)
                if not img.isNull():
                    self.signals.loaded.emit(QPixmap.fromImage(img))
        except Exception:
            pass  # Silencieux : image indisponible, la vignette reste vide


# ============================================================
# Thread : téléchargement des vignettes manquantes avec débit limitable
# ============================================================

class ThrottledThumbnailThread(QThread):
    """
    Télécharge en arrière-plan toutes les vignettes qui ne sont pas
    encore présentes sur le disque local.

    Le paramètre delay_s introduit un délai entre chaque vignette,
    ce qui permet de limiter la bande passante consommée :

        delay_s = 0.05  → téléchargement rapide (mode inactivité)
                           ~1 000 vignettes en ≈ 1 min
        delay_s = 2.0   → téléchargement lent (mode visionnage)
                           une vignette toutes les 2 s ≈ 25–50 Ko/s max,
                           sans impact perceptible sur le flux vidéo

    Signals :
        progress(done: int, total: int)  → avancement
        finished_all()                   → toutes les vignettes traitées
    """

    progress     = pyqtSignal(int, int)   # (nombre traités, total)
    finished_all = pyqtSignal()

    def __init__(self, delay_s: float = 0.05, parent=None):
        super().__init__(parent)
        self.delay_s    = delay_s
        self._stop_flag = False

    def stop(self) -> None:
        """Demande l'arrêt propre du thread (au prochain délai)."""
        self._stop_flag = True

    def run(self) -> None:
        """
        Récupère tous les items sans vignette et les télécharge un par un,
        en respectant le délai delay_s entre chaque requête.
        """
        import time

        # Collecter tous les items manquants (films + séries)
        items: list = []
        for item_type in ("movie", "series"):
            for item in get_items_without_thumbnail(item_type, limit=2000):
                items.append((item, item_type))

        total = len(items)
        if total == 0:
            self.finished_all.emit()
            return

        for i, (item, item_type) in enumerate(items):
            # Vérifier l'arrêt demandé
            if self._stop_flag or self.isInterruptionRequested():
                break

            url     = item.get("stream_icon") or item.get("cover", "")
            item_id = item.get("stream_id")   or item.get("series_id")

            if url and item_id:
                # Télécharger et sauvegarder (utilise la même fonction que _download_single_thumbnail)
                try:
                    resp = requests.get(url, timeout=8)
                    if resp.status_code == 200:
                        save_thumbnail_from_bytes(url, item_id, item_type, resp.content)
                except Exception:
                    pass  # Silencieux : image indisponible

            self.progress.emit(i + 1, total)

            # Pause configurable entre chaque vignette pour limiter le débit
            if self.delay_s > 0:
                elapsed = 0.0
                step    = 0.1  # vérification de l'arrêt toutes les 100 ms
                while elapsed < self.delay_s:
                    if self._stop_flag:
                        return
                    time.sleep(step)
                    elapsed += step

        self.finished_all.emit()


# ============================================================
# Widget : vignette d'un film ou d'une série
# ============================================================

class ContentCard(QFrame):
    """
    Petite vignette affichant le poster et le titre d'un film/série.
    Émet clicked(data) lorsque l'utilisateur clique dessus.
    """

    clicked = pyqtSignal(dict)  # data = dict décrivant le film/la série

    CARD_W = 158
    CARD_H = 245
    IMG_W  = 150
    IMG_H  = 200

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            ContentCard {
                background-color: #1e1e2e;
                border: 1px solid #2a2a3e;
                border-radius: 8px;
            }
            ContentCard:hover {
                border: 2px solid #2196F3;
                background-color: #252540;
            }
        """)
        self._setup_ui()
        self._load_poster()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Image du poster
        self.lbl_poster = QLabel()
        self.lbl_poster.setFixedSize(self.IMG_W, self.IMG_H)
        self.lbl_poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_poster.setStyleSheet(
            "background-color: #2a2a3e; border-radius: 4px; color: #555; font-size: 28px;"
        )
        self.lbl_poster.setText("🎬")
        layout.addWidget(self.lbl_poster)

        # Titre (2 lignes max)
        name = self.data.get("name", "")
        lbl_title = QLabel(name)
        lbl_title.setWordWrap(True)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet("color: #ddd; font-size: 11px;")
        lbl_title.setFixedHeight(38)
        layout.addWidget(lbl_title)

    def _load_poster(self):
        """
        Charge le poster du film ou de la série.

        Stratégie en deux étapes pour un démarrage ultra-rapide :
        1. Si la vignette est déjà sur le disque local → lecture immédiate
           (aucun réseau, quelques millisecondes).
        2. Sinon → téléchargement réseau en arrière-plan via PosterLoader
           (uniquement si aucune vignette locale n'est disponible).
        """
        # --- Étape 1 : Chercher la vignette sur le disque ---
        item_id   = self.data.get("stream_id") or self.data.get("series_id")
        item_type = "movie" if "stream_id" in self.data else "series"
        url       = self.data.get("stream_icon") or self.data.get("cover", "")

        # Vérifier d'abord la colonne cover_local (chemin absolu sauvegardé)
        local_path = self.data.get("cover_local", "")
        if not local_path and url and item_id:
            # Calculer le chemin attendu sans ouvrir la base de données
            local_path = get_thumbnail_path(url, item_id, item_type) or ""

        if local_path:
            # Vignette locale trouvée → chargement immédiat depuis le disque
            pixmap = QPixmap(local_path)
            if not pixmap.isNull():
                self._set_poster(pixmap)
                return  # Fin : pas besoin du réseau

        # --- Étape 2 : Pas de vignette locale → téléchargement via le pool ---
        # On passe item_id et item_type pour que PosterLoader sauvegarde
        # l'image sur le disque après téléchargement (cache persistant).
        if url:
            loader = PosterLoader(url, item_id=item_id, item_type=item_type)
            loader.signals.loaded.connect(self._set_poster)
            _POSTER_POOL.start(loader)  # soumis au pool, pas de thread dédié

    def _set_poster(self, pixmap: QPixmap):
        """Affiche le poster (qu'il vienne du disque ou du réseau)."""
        scaled = pixmap.scaled(
            self.IMG_W, self.IMG_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.lbl_poster.setPixmap(scaled)
        self.lbl_poster.setText("")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.data)
        super().mousePressEvent(event)


# ============================================================
# Widget : grille de vignettes
# ============================================================

class ContentGrid(QWidget):
    """
    Grille scrollable affichant des ContentCard avec chargement progressif.

    Les vignettes sont chargées par pages (PAGE_SIZE items à la fois).
    Quand l'utilisateur approche du bas de la liste, la page suivante
    est automatiquement rendue — les images se téléchargent au fur et
    à mesure du défilement.

    Émet item_clicked(data, content_type) lors d'un clic.
    """

    item_clicked = pyqtSignal(dict, str)  # data, "movie" | "series"

    PAGE_SIZE = 60   # Nombre de vignettes chargées par page

    def __init__(self, content_type: str, parent=None):
        super().__init__(parent)
        self.content_type    = content_type
        self._cards          = []
        self._all_items      = []   # Tous les items (liste complète)
        self._displayed_count = 0   # Nombre de vignettes déjà rendues
        self._setup_ui()

    def _setup_ui(self):
        # Zone de défilement
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background-color: #0f0f1a; }")

        self.container = QWidget()
        self.container.setStyleSheet("background-color: #0f0f1a;")
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(12)
        self.grid.setContentsMargins(12, 12, 12, 12)

        self.scroll.setWidget(self.container)

        # Détecter l'approche du bas de la liste → charger la page suivante
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        # Label "aucun résultat"
        self.lbl_empty = QLabel("Aucun résultat.")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet("color: #555; font-size: 16px; padding: 40px;")
        self.lbl_empty.hide()

        # Label compteur d'items (affiché sous la grille)
        self.lbl_count = QLabel("")
        self.lbl_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_count.setStyleSheet("color: #555; font-size: 11px; padding: 6px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)
        layout.addWidget(self.lbl_empty)
        layout.addWidget(self.lbl_count)

    def display(self, items: list):
        """
        Réaffiche la grille avec les items fournis.
        Seule la première page (PAGE_SIZE vignettes) est rendue immédiatement.
        Les pages suivantes sont chargées au défilement.

        Args:
            items : Liste complète de dicts (films ou séries).
        """
        # Stocker la liste complète
        self._all_items       = items
        self._displayed_count = 0

        # Supprimer les anciennes cartes
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

        # Vider le layout de la grille
        while self.grid.count():
            item_layout = self.grid.takeAt(0)
            if item_layout.widget():
                item_layout.widget().deleteLater()

        if not items:
            self.scroll.hide()
            self.lbl_empty.show()
            self.lbl_count.hide()
            return

        self.lbl_empty.hide()
        self.scroll.show()
        self.lbl_count.show()

        # Remettre la barre de défilement en haut
        self.scroll.verticalScrollBar().setValue(0)

        # Charger la première page
        self._load_next_page()

    def _cols(self) -> int:
        """Calcule le nombre de colonnes en fonction de la largeur disponible."""
        return max(2, (self.width() - 24) // (ContentCard.CARD_W + 12))

    def _load_next_page(self):
        """Rend la page suivante de vignettes (PAGE_SIZE items maximum)."""
        start = self._displayed_count
        end   = min(start + self.PAGE_SIZE, len(self._all_items))
        if start >= end:
            return   # Tout est déjà affiché

        cols = self._cols()

        for idx in range(start, end):
            item_data = self._all_items[idx]
            card = ContentCard(item_data)
            card.clicked.connect(
                lambda data, ct=self.content_type: self.item_clicked.emit(data, ct)
            )
            self.grid.addWidget(card, idx // cols, idx % cols)
            self._cards.append(card)

        self._displayed_count = end

        # Mettre à jour le stretch et le compteur
        self.grid.setRowStretch(end // cols + 1, 1)
        total = len(self._all_items)
        if self._displayed_count < total:
            self.lbl_count.setText(
                f"Affichage de {self._displayed_count} / {total} — faites défiler pour charger la suite"
            )
        else:
            self.lbl_count.setText(f"{total} résultat(s)")

    def _on_scroll(self, value: int):
        """
        Déclenché à chaque mouvement de la barre de défilement.
        Si l'utilisateur approche du bas (>= 80 % de la hauteur max),
        la page suivante de vignettes est chargée.
        """
        if self._displayed_count >= len(self._all_items):
            return  # Tout est déjà chargé
        sb = self.scroll.verticalScrollBar()
        if sb.maximum() > 0 and value >= sb.maximum() * 0.80:
            self._load_next_page()

    def resizeEvent(self, event):
        """Relance l'affichage pour recalculer le nombre de colonnes."""
        super().resizeEvent(event)


# ============================================================
# Fenêtre principale
# ============================================================

class MainWindow(QMainWindow):
    """Fenêtre principale de l'application IPTV Player."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("IPTV Player")
        self.setMinimumSize(960, 640)
        self.resize(1280, 800)

        # État
        self.config       = load_config()
        self.sync_thread  = None
        self.player_win   = None

        # ----------------------------------------------------------------
        # Spinner d'animation (affiché pendant sync et téléchargement)
        # ----------------------------------------------------------------
        self._spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_idx   = 0
        self._spinner_active_count = 0  # Nombre d'opérations en cours
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(100)   # 100 ms → 10 fps
        self._spinner_timer.timeout.connect(self._spinner_tick)

        # ----------------------------------------------------------------
        # Thread de téléchargement des vignettes en arrière-plan
        # ----------------------------------------------------------------
        # Une seule instance à la fois : on stop/relance si besoin.
        self._bg_thumb_thread: ThrottledThumbnailThread = None

        # ----------------------------------------------------------------
        # Timer d'inactivité (1 minute)
        # ----------------------------------------------------------------
        # Après 1 min sans interaction, on lance le téléchargement rapide
        # de toutes les vignettes manquantes.
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(4_000)    # 4 secondes
        self._idle_timer.timeout.connect(self._on_idle)

        # Intercepter les événements souris/clavier sur toute l'application
        # pour réinitialiser le timer d'inactivité.
        QApplication.instance().installEventFilter(self)

        # Initialiser la base de données
        initialize_db()

        # Construire l'interface
        self._build_ui()
        self._build_menu()
        self._apply_theme()

        # Charger le contenu du cache
        self._refresh()
        self._refresh_downloads()

        # Démarrer le timer d'inactivité dès le lancement
        self._idle_timer.start()

        # Vérifier si une synchronisation automatique est nécessaire
        # (1er démarrage ou catalogue > 30 jours)
        # Délai de 1,5 s pour laisser l'interface se construire d'abord.
        QTimer.singleShot(1500, self._auto_sync_if_needed)

        # Si l'app n'est pas configurée, ouvrir les paramètres automatiquement
        if not is_configured(self.config):
            QTimer.singleShot(400, self._open_settings)

    # ------------------------------------------------------------------ #
    #  Détection de l'inactivité                                           #
    # ------------------------------------------------------------------ #

    def eventFilter(self, obj, event) -> bool:
        """
        Intercepte tous les événements de l'application.

        Dès qu'une interaction souris ou clavier est détectée :
          - Le téléchargement de vignettes en cours est stoppé immédiatement.
          - Le compte à rebours d'inactivité (4 s) est relancé.
        Pendant le visionnage, le timer est suspendu.
        """
        from PyQt6.QtCore import QEvent
        if event.type() in (
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.KeyPress,
            QEvent.Type.Wheel,
        ):
            if self.player_win is None:
                # Stopper immédiatement le téléchargement de vignettes si actif
                if self._bg_thumb_thread and self._bg_thumb_thread.isRunning():
                    self._bg_thumb_thread.stop()
                self._idle_timer.start()   # relance le compte à rebours de 4 s
        return super().eventFilter(obj, event)

    def _on_idle(self) -> None:
        """
        Déclenché après 4 secondes d'inactivité complète de l'utilisateur.

        Lance le téléchargement rapide de toutes les vignettes manquantes
        (délai très court entre chaque image : charge maximale du réseau,
        puisque l'utilisateur ne regarde pas de vidéo).
        """
        self.status.showMessage(
            "Inactivité détectée — téléchargement des vignettes en arrière-plan…"
        )
        self._start_bg_thumbnails(delay_s=0.05)

    # ------------------------------------------------------------------ #
    #  Téléchargement des vignettes en arrière-plan                        #
    # ------------------------------------------------------------------ #

    def _start_bg_thumbnails(self, delay_s: float = 0.05) -> None:
        """
        Lance (ou relance) ThrottledThumbnailThread.

        Si un thread est déjà en cours avec un délai différent, il est
        interrompu proprement avant d'être remplacé.

        Args:
            delay_s : Délai entre chaque vignette (s).
                      0.05 → mode inactivité (rapide)
                      2.0  → mode visionnage (lent, préserve la bande passante)
        """
        if self._bg_thumb_thread and self._bg_thumb_thread.isRunning():
            # Arrêter l'ancien thread proprement (max 2 s d'attente)
            self._bg_thumb_thread.stop()
            self._bg_thumb_thread.wait(2000)

        self._bg_thumb_thread = ThrottledThumbnailThread(delay_s=delay_s, parent=self)
        self._bg_thumb_thread.finished_all.connect(self._on_bg_thumbnails_done)
        self._bg_thumb_thread.start()
        self._spinner_start()   # Spinner visible pendant le téléchargement

    def _on_bg_thumbnails_done(self) -> None:
        """Appelé quand toutes les vignettes manquantes ont été téléchargées."""
        self._spinner_stop()
        self.status.showMessage("Toutes les vignettes sont à jour.")

    # ------------------------------------------------------------------ #
    #  Spinner d'animation                                                  #
    # ------------------------------------------------------------------ #

    def _spinner_start(self) -> None:
        """Démarre (ou maintient) le spinner. Peut être appelé plusieurs fois."""
        self._spinner_active_count += 1
        if not self._spinner_timer.isActive():
            self._spinner_idx = 0
            self.lbl_spinner.show()
            self._spinner_timer.start()

    def _spinner_stop(self) -> None:
        """Arrête le spinner si aucune opération n'est encore en cours."""
        self._spinner_active_count = max(0, self._spinner_active_count - 1)
        if self._spinner_active_count == 0:
            self._spinner_timer.stop()
            self.lbl_spinner.hide()

    def _spinner_tick(self) -> None:
        """Avance le spinner d'un cran à chaque tick du timer."""
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_chars)
        self.lbl_spinner.setText(self._spinner_chars[self._spinner_idx])

    # ------------------------------------------------------------------ #
    #  Synchronisation automatique au démarrage                            #
    # ------------------------------------------------------------------ #

    def _auto_sync_if_needed(self) -> None:
        """
        Vérifie si une synchronisation est nécessaire et la lance silencieusement.

        Conditions de déclenchement :
          - Aucune synchronisation n'a jamais eu lieu (premier démarrage), ou
          - La dernière synchronisation date de plus de 30 jours.

        La synchronisation ne se déclenche pas si :
          - Le serveur n'est pas encore configuré, ou
          - Une synchronisation manuelle est déjà en cours.
        """
        if not is_configured(self.config):
            return   # Attendre que l'utilisateur configure le serveur
        if self.sync_thread and self.sync_thread.isRunning():
            return   # Déjà en cours

        if needs_sync(max_age_days=30):
            last = get_last_sync_date()
            if last is None:
                msg = "Premier démarrage — synchronisation automatique du catalogue…"
            else:
                days = (
                    __import__("datetime").datetime.now() - last
                ).days
                msg = (
                    f"Catalogue de {days} jours — mise à jour automatique…"
                )
            self.status.showMessage(msg)
            self._start_sync()

    # ------------------------------------------------------------------ #
    #  Construction de l'interface                                          #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        """Crée tous les widgets de la fenêtre principale."""
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ===== Barre d'outils (recherche + filtres) =====
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #13132a; border-bottom: 1px solid #2a2a44;")
        toolbar.setFixedHeight(58)
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(14, 8, 14, 8)
        tl.setSpacing(10)

        # Champ de recherche
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍  Rechercher par titre…")
        self.search_edit.setMinimumWidth(260)
        self.search_edit.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e38;
                color: white;
                border: 1px solid #3a3a5a;
                border-radius: 18px;
                padding: 7px 16px;
                font-size: 13px;
            }
            QLineEdit:focus { border-color: #2196F3; }
        """)
        self.search_edit.textChanged.connect(self._apply_filters)
        tl.addWidget(self.search_edit)

        # Séparateur
        sep = QLabel("|")
        sep.setStyleSheet("color: #333;")
        tl.addWidget(sep)

        # Filtre catégorie
        tl.addWidget(QLabel("Catégorie :"))
        self.combo_category = QComboBox()
        self.combo_category.addItem("Toutes", "")
        self.combo_category.setMinimumWidth(180)
        self.combo_category.setStyleSheet(self._combo_style())
        self.combo_category.currentIndexChanged.connect(self._apply_filters)
        tl.addWidget(self.combo_category)

        # Filtre année
        tl.addWidget(QLabel("Année :"))
        self.edit_year = QLineEdit()
        self.edit_year.setPlaceholderText("ex: 2023")
        self.edit_year.setMaximumWidth(90)
        self.edit_year.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e38; color: white;
                border: 1px solid #3a3a5a; border-radius: 4px; padding: 6px 10px;
            }
            QLineEdit:focus { border-color: #2196F3; }
        """)
        self.edit_year.textChanged.connect(self._apply_filters)
        tl.addWidget(self.edit_year)

        # Bouton filtre FR
        self.btn_fr = QPushButton("🇫🇷 FR uniquement")
        self.btn_fr.setCheckable(True)
        self.btn_fr.setChecked(self.config.get("language_filter") == "french")
        self.btn_fr.setStyleSheet("""
            QPushButton {
                background-color: #1e1e38; color: #aaa;
                border: 1px solid #3a3a5a; border-radius: 4px; padding: 7px 14px;
            }
            QPushButton:checked {
                background-color: #1565C0; color: white; border-color: #2196F3;
            }
            QPushButton:hover { border-color: #2196F3; }
        """)
        self.btn_fr.clicked.connect(self._apply_filters)
        tl.addWidget(self.btn_fr)

        tl.addStretch()

        # Bouton Synchroniser
        self.btn_sync = QPushButton("🔄  Synchroniser")
        self.btn_sync.setStyleSheet("""
            QPushButton {
                background-color: #1565C0; color: white;
                border: none; border-radius: 4px;
                padding: 8px 18px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover    { background-color: #1976D2; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)
        self.btn_sync.clicked.connect(self._start_sync)
        tl.addWidget(self.btn_sync)

        # Bouton Paramètres
        btn_settings = QPushButton("⚙  Paramètres")
        btn_settings.setStyleSheet("""
            QPushButton { background-color: #2a2a44; color: white;
                          border: none; border-radius: 4px; padding: 8px 16px; }
            QPushButton:hover { background-color: #383860; }
        """)
        btn_settings.clicked.connect(self._open_settings)
        tl.addWidget(btn_settings)

        # Spinner animé (caché par défaut, affiché pendant sync/téléchargement)
        self.lbl_spinner = QLabel("⠋")
        self.lbl_spinner.setFixedWidth(28)
        self.lbl_spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_spinner.setStyleSheet("color: #2196F3; font-size: 18px; font-weight: bold;")
        self.lbl_spinner.hide()
        tl.addWidget(self.lbl_spinner)

        root.addWidget(toolbar)

        # ===== Onglets Films / Séries =====
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane  { border: none; background-color: #0f0f1a; }
            QTabBar::tab      {
                background-color: #13132a; color: #888;
                padding: 10px 24px; border: none; font-size: 14px;
            }
            QTabBar::tab:selected { background-color: #0f0f1a; color: white;
                                    border-bottom: 3px solid #2196F3; }
            QTabBar::tab:hover    { color: #ccc; }
        """)

        self.grid_movies = ContentGrid("movie")
        self.grid_movies.item_clicked.connect(self._on_item_clicked)
        self.tabs.addTab(self.grid_movies, "🎬  Films")

        self.grid_series = ContentGrid("series")
        self.grid_series.item_clicked.connect(self._on_item_clicked)
        self.tabs.addTab(self.grid_series, "📺  Séries")

        # ---- Onglet 3 : Films téléchargés ----
        self.downloads_tab = self._build_downloads_tab()
        self.tabs.addTab(self.downloads_tab, "⬇️  Téléchargés")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs)

        # ===== Barre de statut =====
        self.status = QStatusBar()
        self.status.setStyleSheet(
            "background-color: #13132a; color: #777; border-top: 1px solid #2a2a44;"
        )
        self.setStatusBar(self.status)
        self.status.showMessage("Prêt")

    def _build_menu(self):
        """Crée la barre de menus."""
        bar = self.menuBar()
        bar.setStyleSheet(
            "background-color: #13132a; color: white; font-size: 13px;"
        )

        fichier = bar.addMenu("Fichier")
        act_settings = QAction("Paramètres", self)
        act_settings.triggered.connect(self._open_settings)
        fichier.addAction(act_settings)

        fichier.addSeparator()
        act_quit = QAction("Quitter", self)
        act_quit.triggered.connect(self.close)
        fichier.addAction(act_quit)

        catalogue = bar.addMenu("Catalogue")
        act_sync = QAction("Synchroniser le catalogue", self)
        act_sync.triggered.connect(self._start_sync)
        catalogue.addAction(act_sync)
        act_clear = QAction("Vider le cache", self)
        act_clear.triggered.connect(self._clear_cache)
        catalogue.addAction(act_clear)

        catalogue.addSeparator()

        act_m3u_all = QAction("⬇  Télécharger la liste M3U complète", self)
        act_m3u_all.triggered.connect(self._download_m3u_all)
        catalogue.addAction(act_m3u_all)

        act_m3u_fr = QAction("🇫🇷  Télécharger la liste M3U (FR uniquement)", self)
        act_m3u_fr.triggered.connect(self._download_m3u_fr)
        catalogue.addAction(act_m3u_fr)

        catalogue.addSeparator()

        act_csv = QAction("📄  Exporter le catalogue en CSV…", self)
        act_csv.triggered.connect(self._export_catalogue_csv)
        catalogue.addAction(act_csv)

    def _apply_theme(self):
        """Applique le thème sombre à l'ensemble de l'application."""
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #0f0f1a; color: white; }
            QLabel { color: #ccc; }
            QScrollBar:vertical {
                background: #1a1a2e; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #3a3a5a; border-radius: 4px; min-height: 24px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QMenuBar {
                background-color: #13132a; color: white;
                font-size: 13px; padding: 2px 0;
            }
            QMenuBar::item { padding: 6px 14px; }
            QMenuBar::item:selected { background-color: #1565C0; }
            QMenu {
                background-color: #1e1e38; color: white;
                border: 1px solid #333; font-size: 13px;
            }
            QMenu::item { padding: 8px 28px; }
            QMenu::item:selected { background-color: #1565C0; }
            QMenu::separator { height: 1px; background: #333; margin: 4px 0; }
        """)

    @staticmethod
    def _combo_style() -> str:
        return """
            QComboBox {
                background-color: #1e1e38; color: white;
                border: 1px solid #3a3a5a; border-radius: 4px; padding: 6px 10px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background-color: #1e1e38; color: white;
                selection-background-color: #1565C0;
            }
        """

    # ------------------------------------------------------------------ #
    #  Synchronisation                                                      #
    # ------------------------------------------------------------------ #

    def _start_sync(self):
        """Lance la synchronisation du catalogue depuis le serveur."""
        if not is_configured(self.config):
            QMessageBox.warning(
                self, "Non configuré",
                "Veuillez d'abord renseigner les paramètres de connexion Xtream."
            )
            self._open_settings()
            return

        if self.sync_thread and self.sync_thread.isRunning():
            return  # Déjà en cours

        self.btn_sync.setEnabled(False)
        self.btn_sync.setText("⏳  Synchronisation…")
        self.status.showMessage("Synchronisation en cours…")
        self._spinner_start()

        self.sync_thread = SyncThread(self.config)
        self.sync_thread.progress.connect(self.status.showMessage)
        self.sync_thread.finished.connect(self._on_sync_done)
        self.sync_thread.start()

    def _on_sync_done(self, success: bool, message: str):
        """Appelé à la fin de la synchronisation."""
        self._spinner_stop()
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("🔄  Synchroniser")

        if success:
            self.status.showMessage(message)
            self._refresh()
        else:
            QMessageBox.critical(self, "Erreur de synchronisation", message)
            self.status.showMessage("Synchronisation échouée.")

    # ------------------------------------------------------------------ #
    #  Affichage du catalogue                                               #
    # ------------------------------------------------------------------ #

    def _refresh(self):
        """Recharge et affiche le contenu depuis le cache."""
        french_only = self.btn_fr.isChecked()

        # limit=99999 : on charge tout le catalogue en mémoire.
        # ContentGrid ne rend que PAGE_SIZE vignettes à la fois (lazy loading).
        movies = search_movies(french_only=french_only, limit=99999)
        self.grid_movies.display(movies)

        series = search_series(french_only=french_only, limit=99999)
        self.grid_series.display(series)

        n_films  = get_movie_count(french_only)
        n_series = get_series_count(french_only)
        self.tabs.setTabText(0, f"🎬  Films ({n_films})")
        self.tabs.setTabText(1, f"📺  Séries ({n_series})")

        self._reload_categories(french_only)
        self.status.showMessage(
            f"{n_films} film(s) et {n_series} série(s) dans le cache."
        )

    def _reload_categories(self, french_only: bool):
        """Recharge la liste des catégories dans le combo."""
        self.combo_category.blockSignals(True)
        self.combo_category.clear()
        self.combo_category.addItem("Toutes", "")

        if self.tabs.currentIndex() == 0:
            cats = get_vod_categories_list(french_only)
        else:
            cats = get_series_categories_list(french_only)

        for cat in cats:
            self.combo_category.addItem(cat["category_name"], cat["category_id"])

        self.combo_category.blockSignals(False)

    def _apply_filters(self):
        """Applique les filtres et rafraîchit la grille active."""
        query       = self.search_edit.text().strip()
        year        = self.edit_year.text().strip()
        french_only = self.btn_fr.isChecked()
        cat_id      = self.combo_category.currentData() or ""

        if self.tabs.currentIndex() == 0:
            results = search_movies(
                query=query, year=year,
                french_only=french_only, category_id=cat_id, limit=99999
            )
            self.grid_movies.display(results)
            self.status.showMessage(f"{len(results)} film(s) trouvé(s)")
        else:
            results = search_series(
                query=query, year=year,
                french_only=french_only, category_id=cat_id, limit=99999
            )
            self.grid_series.display(results)
            self.status.showMessage(f"{len(results)} série(s) trouvée(s)")

    def _build_downloads_tab(self) -> QWidget:
        """Construit l'onglet des films téléchargés."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # En-tête
        header = QHBoxLayout()
        lbl = QLabel("Films et épisodes téléchargés")
        lbl.setStyleSheet("color: #7eb8f7; font-size: 13px;")
        header.addWidget(lbl)
        header.addStretch()

        btn_open_folder = QPushButton("📁  Ouvrir le dossier")
        btn_open_folder.setStyleSheet("""
            QPushButton { background-color: #1e1e38; color: white;
                          border: 1px solid #3a3a5a; border-radius: 4px; padding: 6px 14px; }
            QPushButton:hover { border-color: #2196F3; }
        """)
        btn_open_folder.clicked.connect(self._open_downloads_folder)
        header.addWidget(btn_open_folder)
        layout.addLayout(header)

        # Liste
        self.downloads_list = QListWidget()
        self.downloads_list.setStyleSheet("""
            QListWidget { background-color: #0f0f1a; border: 1px solid #2a2a44;
                          border-radius: 4px; color: white; font-size: 13px; }
            QListWidget::item { padding: 10px 14px; border-bottom: 1px solid #1a1a2e; }
            QListWidget::item:hover    { background-color: #1e1e38; }
            QListWidget::item:selected { background-color: #1565C0; }
        """)
        self.downloads_list.itemDoubleClicked.connect(self._play_downloaded)
        self.downloads_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.downloads_list.customContextMenuRequested.connect(self._downloads_context_menu)
        layout.addWidget(self.downloads_list)

        # Message si vide
        self.lbl_no_downloads = QLabel(
            "Aucun film ni épisode téléchargé.\n\n"
            "Films : cliquez sur une vignette puis choisissez « Télécharger le film ».\n"
            "Séries : ouvrez une série et cliquez sur « Télécharger cet épisode »."
        )
        self.lbl_no_downloads.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_no_downloads.setStyleSheet("color: #555; font-size: 14px; padding: 40px;")
        layout.addWidget(self.lbl_no_downloads)

        return widget

    def _make_download_row_widget(self, dl: dict, item: QListWidgetItem) -> QWidget:
        """
        Crée le widget affiché sur chaque ligne de la liste des téléchargements.

        Structure :
            [ icône + texte info (stretch) ]  [ ▶ Lire ]  [ 🗑 Supprimer ]

        Args:
            dl   : Dictionnaire décrivant le téléchargement.
            item : QListWidgetItem associé (pour récupérer dl via UserRole).

        Returns:
            QWidget prêt à être passé à setItemWidget().
        """
        exists   = os.path.exists(dl.get("file_path", ""))
        size_mb  = dl.get("file_size", 0) / (1024 * 1024)
        date     = dl.get("downloaded_at", "")[:10]
        icon     = "📁" if dl.get("_disk_only") else "🎬"
        date_str = "disque local" if dl.get("_disk_only") else date
        warn     = "  ⚠️ introuvable" if not exists else ""

        text = (
            f"{icon}  {dl['name']}"
            f"   ·   {size_mb:.0f} Mo"
            f"   ·   {date_str}"
            f"{warn}"
        )

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(10, 4, 6, 4)
        hl.setSpacing(8)

        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {'#cc7744' if not exists else '#dddddd'}; font-size: 13px;"
        )
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        hl.addWidget(lbl)

        # Bouton Lire
        btn_play = QPushButton("▶  Lire")
        btn_play.setFixedSize(80, 28)
        btn_play.setStyleSheet("""
            QPushButton {
                background-color: #1565C0; color: white;
                border: none; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)
        btn_play.setEnabled(exists)
        btn_play.clicked.connect(lambda _, i=item: self._play_downloaded(i))
        hl.addWidget(btn_play)

        # Bouton Supprimer le fichier
        btn_del = QPushButton("🗑")
        btn_del.setFixedSize(36, 28)
        btn_del.setToolTip("Supprimer définitivement le fichier")
        btn_del.setStyleSheet("""
            QPushButton {
                background-color: #3a1a1a; color: #cc4444;
                border: 1px solid #552222; border-radius: 4px; font-size: 14px;
            }
            QPushButton:hover { background-color: #551a1a; color: #ff6666; }
        """)
        btn_del.clicked.connect(lambda _, i=item: self._delete_download_file(i))
        hl.addWidget(btn_del)

        return row

    def _delete_download_file(self, item: QListWidgetItem):
        """
        Supprime définitivement le fichier vidéo associé à un élément
        de la liste des téléchargements (déclenché par le bouton 🗑).
        """
        dl = item.data(Qt.ItemDataRole.UserRole)
        if not dl:
            return
        file_path = dl.get("file_path", "")
        nom       = dl.get("name", file_path)
        reply = QMessageBox.question(
            self, "Supprimer le fichier",
            f"Supprimer définitivement :\n\n{nom}\n\nCette action est irréversible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Impossible de supprimer :\n{e}")
                return
        if not dl.get("_disk_only"):
            delete_download(dl["id"])
        self._refresh_downloads()

    def _refresh_downloads(self):
        """
        Recharge la liste des téléchargements.

        Fusionne deux sources :
          1. La base de données SQLite (téléchargements enregistrés).
          2. Le scan du dossier DOWNLOADS_DIR : fichiers vidéo présents sur
             le disque mais absents de la base (ex. séries téléchargées avant
             l'introduction de la table, ou si l'enregistrement a échoué).

        Chaque ligne affiche un widget avec les boutons ▶ Lire et 🗑 Supprimer.
        """
        VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".webm"}

        self.downloads_list.clear()

        # --- 1. Fichiers enregistrés en base ---
        db_downloads = get_downloads()
        db_paths = {dl["file_path"] for dl in db_downloads}

        # --- 2. Scan disque (fichiers non encore en base) ---
        disk_extras = []
        try:
            for root, _dirs, files in os.walk(str(DOWNLOADS_DIR)):
                for fname in sorted(files):
                    if os.path.splitext(fname)[1].lower() in VIDEO_EXTS:
                        fpath = os.path.join(root, fname)
                        if fpath not in db_paths:
                            disk_extras.append({
                                "name":          os.path.splitext(fname)[0],
                                "file_path":     fpath,
                                "file_size":     os.path.getsize(fpath),
                                "downloaded_at": "",
                                "_disk_only":    True,
                            })
        except Exception:
            pass

        all_downloads = db_downloads + disk_extras

        if all_downloads:
            self.lbl_no_downloads.hide()
            self.downloads_list.show()
            for dl in all_downloads:
                # Créer l'item (sans texte : le widget le remplace)
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, dl)
                item.setSizeHint(QSize(0, 44))   # Hauteur fixe de chaque ligne
                self.downloads_list.addItem(item)
                # Insérer le widget avec les boutons
                row_widget = self._make_download_row_widget(dl, item)
                self.downloads_list.setItemWidget(item, row_widget)
            self.tabs.setTabText(2, f"⬇️  Téléchargés ({len(all_downloads)})")
        else:
            self.downloads_list.hide()
            self.lbl_no_downloads.show()
            self.tabs.setTabText(2, "⬇️  Téléchargés")

    def _play_downloaded(self, item: QListWidgetItem):
        """Lit un film téléchargé (double-clic)."""
        dl = item.data(Qt.ItemDataRole.UserRole)
        if not dl:
            return
        file_path = dl.get("file_path", "")
        if not os.path.exists(file_path):
            QMessageBox.warning(
                self, "Fichier introuvable",
                f"Le fichier n'existe plus :\n{file_path}\n\n"
                "Vous pouvez supprimer cet élément via le clic droit."
            )
            return
        # Ouvrir le dialogue de sélection de l'écran
        from PyQt6.QtWidgets import QInputDialog
        screens   = QApplication.screens()
        has_sec   = len(screens) > 1
        if has_sec:
            choices = ["Écran principal", "Écran secondaire"]
            choice, ok = QInputDialog.getItem(
                self, "Quel écran ?",
                f"Lire « {dl['name']} » sur :", choices, 0, False
            )
            if not ok:
                return
            screen_idx = 0 if choice == "Écran principal" else 1
        else:
            screen_idx = 0

        self._open_player(file_path, dl.get("name", ""), screen_idx)

    def _downloads_context_menu(self, pos):
        """Menu contextuel (clic droit) sur la liste des téléchargements."""
        item = self.downloads_list.itemAt(pos)
        if not item:
            return
        dl = item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1e1e38; color: white; border: 1px solid #333; }
            QMenu::item:selected { background-color: #1565C0; }
        """)

        act_play   = menu.addAction("▶  Lire")
        act_folder = menu.addAction("📁  Voir dans l'explorateur")
        menu.addSeparator()
        act_delete_entry = menu.addAction("🗑  Supprimer de la liste")
        act_delete_file  = menu.addAction("🗑  Supprimer la liste ET le fichier")

        action = menu.exec(self.downloads_list.mapToGlobal(pos))

        if action == act_play:
            self._play_downloaded(item)
        elif action == act_folder:
            import subprocess
            file_path = dl.get("file_path", "")
            if os.path.exists(file_path):
                subprocess.Popen(f'explorer /select,"{file_path}"')
        elif action == act_delete_entry:
            if dl.get("_disk_only"):
                # Fichier trouvé sur disque mais absent de la base : rien à supprimer en base
                QMessageBox.information(
                    self, "Information",
                    "Ce fichier a été détecté sur le disque mais n'est pas "
                    "enregistré dans la base.\nUtilisez « Supprimer la liste ET le fichier » "
                    "pour le retirer."
                )
            else:
                delete_download(dl["id"])
                self._refresh_downloads()
        elif action == act_delete_file:
            file_path = dl.get("file_path", "")
            nom       = dl.get("name", file_path)
            reply = QMessageBox.question(
                self, "Supprimer le fichier",
                f"Supprimer définitivement le fichier ?\n\n{nom}\n\n"
                "Cette action est irréversible.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No   # bouton par défaut = Non
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    QMessageBox.warning(self, "Erreur", f"Impossible de supprimer : {e}")
                    return
            if not dl.get("_disk_only"):
                delete_download(dl["id"])
            self._refresh_downloads()

    def _open_downloads_folder(self):
        """Ouvre le dossier des téléchargements dans l'explorateur Windows."""
        import subprocess
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(f'explorer "{DOWNLOADS_DIR}"')

    def _on_tab_changed(self, index: int):
        """Met à jour les catégories et applique les filtres lors d'un changement d'onglet."""
        if index == 2:
            # Onglet téléchargements : rafraîchir la liste
            self._refresh_downloads()
            return
        self._reload_categories(self.btn_fr.isChecked())
        self._apply_filters()

    # ------------------------------------------------------------------ #
    #  Paramètres                                                           #
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    #  Téléchargement des listes M3U                                        #
    # ------------------------------------------------------------------ #

    def _download_m3u_all(self):
        """Télécharge la liste M3U complète depuis le serveur Xtream."""
        from PyQt6.QtWidgets import QFileDialog
        import datetime

        if not is_configured(self.config):
            QMessageBox.warning(
                self, "Non configuré",
                "Configurez d'abord la connexion Xtream dans les Paramètres."
            )
            return

        base = self.config["server_url"].rstrip("/")
        port = self.config.get("port", "").strip()
        if port:
            base = f"{base}:{port}"
        user = self.config["username"]
        pwd  = self.config["password"]
        url  = f"{base}/get.php?username={user}&password={pwd}&type=m3u_plus"

        today = datetime.date.today().strftime("%Y-%m-%d")
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer la liste M3U complète",
            f"IPTV_Complet_{today}.m3u",
            "Fichiers M3U (*.m3u *.m3u8)"
        )
        if not path:
            return

        self.status.showMessage("Téléchargement de la liste M3U complète…")
        self._spinner_start()
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            with open(path, "wb") as f:
                f.write(resp.content)
            self._spinner_stop()
            self.status.showMessage(f"Liste M3U complète sauvegardée : {path}")
            QMessageBox.information(
                self, "Téléchargement terminé",
                f"La liste M3U complète a été sauvegardée :\n{path}"
            )
        except Exception as e:
            self._spinner_stop()
            self.status.showMessage("Échec du téléchargement M3U.")
            QMessageBox.critical(self, "Erreur", f"Impossible de télécharger la liste :\n{e}")

    def _download_m3u_fr(self):
        """Génère et sauvegarde une liste M3U des films/séries français (depuis le cache local)."""
        from PyQt6.QtWidgets import QFileDialog
        import datetime

        if not is_configured(self.config):
            QMessageBox.warning(
                self, "Non configuré",
                "Configurez d'abord la connexion Xtream dans les Paramètres."
            )
            return

        client = self._get_client()
        if not client:
            return

        self.status.showMessage("Génération de la liste M3U FR…")
        self._spinner_start()

        movies = search_movies(french_only=True, limit=99999)
        series = search_series(french_only=True, limit=99999)

        lines = ["#EXTM3U"]

        for m in movies:
            sid  = m.get("stream_id")
            ext  = m.get("container_extension", "mkv")
            name = m.get("name", "")
            cat  = m.get("category_name", "")
            logo = m.get("stream_icon", "")
            stream_url = client.get_stream_url(sid, ext)
            lines.append(
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="Films FR | {cat}",{name}'
            )
            lines.append(stream_url)

        for s in series:
            sid  = s.get("series_id")
            name = s.get("name", "")
            cat  = s.get("category_name", "")
            logo = s.get("cover", "")
            # URL de la page série (pas un stream direct — pointe vers la liste)
            stream_url = (
                f"{client.base_url}/series/"
                f"{client.username}/{client.password}/{sid}"
            )
            lines.append(
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="Séries FR | {cat}",{name}'
            )
            lines.append(stream_url)

        content = "\r\n".join(lines) + "\r\n"

        today = datetime.date.today().strftime("%Y-%m-%d")
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer la liste M3U FR",
            f"IPTV_FR_{today}.m3u",
            "Fichiers M3U (*.m3u *.m3u8)"
        )
        self._spinner_stop()
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.status.showMessage(f"Liste M3U FR sauvegardée : {path}")
            QMessageBox.information(
                self, "Génération terminée",
                f"{len(movies)} film(s) et {len(series)} série(s) exportés.\n\n"
                f"Fichier sauvegardé :\n{path}"
            )
        except Exception as e:
            self.status.showMessage("Erreur lors de la sauvegarde M3U FR.")
            QMessageBox.critical(self, "Erreur", f"Impossible d'écrire le fichier :\n{e}")

    def _export_catalogue_csv(self):
        """
        Exporte la liste complète des films, séries et chaînes live
        dans un fichier CSV avec trois colonnes :
            Catégorie | Titre | Lien HTTP de la vidéo

        Les liens vers les vignettes ne sont pas inclus.
        Les chaînes live sont récupérées directement depuis le serveur
        (elles ne sont pas stockées dans le cache local).
        """
        from PyQt6.QtWidgets import QFileDialog
        import csv
        import datetime

        if not is_configured(self.config):
            QMessageBox.warning(
                self, "Non configuré",
                "Configurez d'abord la connexion Xtream dans les Paramètres."
            )
            return

        client = self._get_client()
        if not client:
            return

        today = datetime.date.today().strftime("%Y-%m-%d")
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le catalogue en CSV",
            f"Catalogue_IPTV_{today}.csv",
            "Fichiers CSV (*.csv)"
        )
        if not path:
            return

        self.status.showMessage("Export CSV en cours — récupération des chaînes live…")
        self._spinner_start()

        # Films et séries depuis le cache local (sans filtre de langue)
        films  = search_movies(french_only=False, limit=99999)
        series = search_series(french_only=False, limit=99999)

        # Chaînes live : récupérées directement depuis le serveur
        # (non stockées dans le cache local)
        try:
            self.status.showMessage("Export CSV — récupération des catégories live…")
            live_cats  = client.get_live_categories()
            live_cats_map = {str(c["category_id"]): c["category_name"] for c in live_cats}

            self.status.showMessage("Export CSV — récupération des chaînes live…")
            chaines = client.get_live_streams()
        except Exception as e:
            self._spinner_stop()
            QMessageBox.critical(
                self, "Erreur réseau",
                f"Impossible de récupérer les chaînes live depuis le serveur :\n{e}\n\n"
                "Les films et séries du cache seront quand même exportés."
            )
            chaines = []

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                # utf-8-sig : BOM UTF-8 pour compatibilité Excel français
                writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)

                # En-tête
                writer.writerow(["Type", "Catégorie", "Titre", "Lien HTTP"])

                # Films
                for m in films:
                    sid  = m.get("stream_id")
                    ext  = m.get("container_extension", "mkv")
                    cat  = m.get("category_name", "")
                    name = m.get("name", "")
                    url  = client.get_stream_url(sid, ext)
                    writer.writerow(["Film", cat, name, url])

                # Séries
                for s in series:
                    sid  = s.get("series_id")
                    cat  = s.get("category_name", "")
                    name = s.get("name", "")
                    url  = (
                        f"{client.base_url}/series/"
                        f"{client.username}/{client.password}/{sid}"
                    )
                    writer.writerow(["Série", cat, name, url])

                # Chaînes live
                for ch in chaines:
                    sid     = ch.get("stream_id")
                    cat_id  = str(ch.get("category_id", ""))
                    cat     = live_cats_map.get(cat_id, cat_id)
                    name    = ch.get("name", "")
                    url     = client.get_live_stream_url(sid, ext="ts")
                    writer.writerow(["Chaîne live", cat, name, url])

            self._spinner_stop()
            total = len(films) + len(series) + len(chaines)
            self.status.showMessage(
                f"Export terminé : {len(films)} film(s), {len(series)} série(s), "
                f"{len(chaines)} chaîne(s) → {path}"
            )
            QMessageBox.information(
                self, "Export CSV terminé",
                f"{total} entrées exportées :\n"
                f"  • {len(films)} films\n"
                f"  • {len(series)} séries\n"
                f"  • {len(chaines)} chaînes live\n\n"
                f"Fichier sauvegardé :\n{path}"
            )

        except Exception as e:
            self._spinner_stop()
            self.status.showMessage("Erreur lors de l'export CSV.")
            QMessageBox.critical(self, "Erreur", f"Impossible d'écrire le fichier :\n{e}")

    def _open_settings(self):
        """Ouvre le dialogue de paramétrage."""
        dlg = SettingsDialog(self)
        if dlg.exec():
            self.config = load_config()
            self.btn_fr.setChecked(self.config.get("language_filter") == "french")
            self._refresh()

    def _clear_cache(self):
        """Vide le cache après confirmation de l'utilisateur."""
        reply = QMessageBox.question(
            self, "Vider le cache",
            "Toutes les données du catalogue seront supprimées.\n"
            "Vous devrez resynchroniser avant de pouvoir naviguer.\n\n"
            "Confirmer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            clear_cache()
            self._refresh()
            self.status.showMessage("Cache vidé.")

    # ------------------------------------------------------------------ #
    #  Lecture                                                              #
    # ------------------------------------------------------------------ #

    def _on_item_clicked(self, data: dict, content_type: str):
        """
        Appelé quand l'utilisateur clique sur une vignette.

        Films   → dialogue de choix (Voir / Télécharger).
        Séries  → ouverture directe de SeriesDialog (choix épisode/saison).
        """
        if content_type == "movie":
            dlg = PlayOptionsDialog(data, content_type, self)
            dlg.play_on_screen.connect(
                lambda screen_idx: self._play_movie(data, screen_idx)
            )
            dlg.download.connect(
                lambda: self._start_download(data)
            )
            dlg.exec()
        else:
            # Séries : ouvrir directement le dialogue de sélection d'épisodes
            self._open_series(data)

    def _get_client(self) -> XtreamClient | None:
        """Crée et retourne un client Xtream si l'app est configurée."""
        if not is_configured(self.config):
            QMessageBox.warning(
                self, "Non configuré",
                "Configurez d'abord la connexion Xtream dans les Paramètres."
            )
            return None
        return XtreamClient(
            server_url=self.config["server_url"],
            port=self.config["port"],
            username=self.config["username"],
            password=self.config["password"]
        )

    def _play_movie(self, movie: dict, screen_index: int = -1):
        """Lance la lecture d'un film sur l'écran demandé."""
        client = self._get_client()
        if not client:
            return
        stream_id = movie.get("stream_id")
        ext       = movie.get("container_extension", "mkv")
        url       = client.get_stream_url(stream_id, ext)
        self._open_player(url, movie.get("name", ""), screen_index)

    def _open_series(self, series: dict):
        """Ouvre le dialogue de sélection d'épisode/saison pour une série."""
        client = self._get_client()
        if not client:
            return
        dlg = SeriesDialog(series, client, self)
        # Lecture d'un épisode individuel
        dlg.play_episode.connect(
            lambda url, title: self._open_player(url, title, 0)
        )
        # Téléchargement d'un épisode individuel
        dlg.download_episode.connect(self._start_download_episode)
        # Lecture de toute la saison (liste de (url, titre))
        dlg.play_season.connect(self._play_season_playlist)
        # Téléchargement de toute la saison
        dlg.download_season.connect(self._download_season)
        dlg.exec()

    def _open_player(self, url: str, title: str, screen_index: int = -1):
        """
        Ouvre (ou réutilise) la fenêtre du lecteur vidéo.

        Pendant le visionnage :
          - Le timer d'inactivité est suspendu (pas de déclenchement intempestif).
          - Un téléchargement très lent des vignettes manquantes est lancé
            (delay_s = 2 s entre chaque image ≈ 25–50 Ko/s max),
            pour ne pas concurrencer le flux vidéo.
          - Si le catalogue a plus de 24 h, une re-synchronisation silencieuse
            des titres est démarrée en arrière-plan.
        """
        # Si le lecteur est déjà ouvert sur le même écran, on change juste le flux
        if (self.player_win and self.player_win.isVisible()
                and self.player_win._screen_index == screen_index):
            self.player_win.play(url, title)
        else:
            # Fermer l'ancien lecteur si nécessaire
            if self.player_win and self.player_win.isVisible():
                self.player_win.close_player()
            self.player_win = PlayerWindow(screen_index=screen_index)
            self.player_win.closed.connect(self._on_player_closed)
            self.player_win.show()
            QTimer.singleShot(300, lambda: self.player_win.play(url, title))

        # --- Mode visionnage ---

        # 0. Réduire la fenêtre principale pour laisser toute la place à la vidéo
        self.showMinimized()

        # 1. Suspendre le timer d'inactivité
        self._idle_timer.stop()

        # 2. Lancer le téléchargement très lent des vignettes manquantes
        #    (une vignette toutes les 2 s = bande passante quasi nulle)
        self._start_bg_thumbnails(delay_s=2.0)

        # 3. Re-synchronisation silencieuse des titres si > 24 h
        #    (uniquement si ce n'est pas déjà en cours)
        if needs_sync(max_age_days=1) and is_configured(self.config):
            if not (self.sync_thread and self.sync_thread.isRunning()):
                self.sync_thread = SyncThread(self.config)
                # Pas de connexion aux signaux UI : synchronisation silencieuse
                self.sync_thread.finished.connect(
                    lambda ok, _msg: self._refresh() if ok else None
                )
                self.sync_thread.start()

    def _on_player_closed(self):
        """
        Appelé à la fermeture du lecteur.

        Restitue le mode normal :
          - Arrête le téléchargement lent des vignettes.
          - Redémarre le timer d'inactivité pour permettre le mode rapide.
        """
        self.player_win = None

        # Arrêter le téléchargement throttlé du mode visionnage
        if self._bg_thumb_thread and self._bg_thumb_thread.isRunning():
            self._bg_thumb_thread.stop()
            # Pas d'attente bloquante ici : le thread s'arrêtera au prochain délai

        # Reprendre la surveillance de l'inactivité
        self._idle_timer.start()

        # Restaurer la fenêtre principale
        self.showNormal()
        self.activateWindow()

    def _start_download(self, movie: dict):
        """Lance le téléchargement d'un film dans le sous-répertoire Films."""
        client = self._get_client()
        if not client:
            return

        stream_id = movie.get("stream_id")
        ext       = movie.get("container_extension", "mkv")
        url       = client.get_stream_url(stream_id, ext)
        name      = movie.get("name", "Film")

        dlg = DownloadProgressDialog(url, name, ext, dest_dir=MOVIES_DIR, parent=self)
        dlg.download_finished.connect(
            lambda success, path: self._on_download_finished(success, path, movie)
        )
        dlg.exec()

    def _on_download_finished(self, success: bool, file_path: str, movie: dict):
        """Appelé à la fin d'un téléchargement de film."""
        if success and file_path:
            import os
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            add_download(
                name        = movie.get("name", ""),
                stream_id   = movie.get("stream_id", 0),
                file_path   = file_path,
                file_size   = file_size,
                extension   = movie.get("container_extension", "mkv"),
                cover_local = movie.get("cover_local", "")
            )
            self._refresh_downloads()
            self.status.showMessage(
                f"✅  Téléchargement terminé : {movie.get('name', '')}"
            )
        else:
            self.status.showMessage("❌  Téléchargement annulé ou échoué.")

    def _start_download_episode(self, episode: dict, series_name: str):
        """
        Lance le téléchargement d'un épisode dans le sous-répertoire
        portant le nom de la série.
        """
        client = self._get_client()
        if not client:
            return

        stream_id = episode.get("id")
        ext       = episode.get("container_extension", "mkv")
        url       = client.get_episode_url(stream_id, ext)

        ep_num   = episode.get("episode_num", "")
        ep_title = episode.get("title", "") or f"Épisode {ep_num}"
        full_name = f"{series_name}  —  Ép. {ep_num}  —  {ep_title}"

        series_dest = get_series_dir(series_name)   # …/IPTVPlayer/<Nom série>/
        dlg = DownloadProgressDialog(
            url, full_name, ext, dest_dir=series_dest, parent=self
        )
        dlg.download_finished.connect(
            lambda success, path: self._on_episode_download_finished(
                success, path, episode, series_name
            )
        )
        dlg.exec()

    def _on_episode_download_finished(self, success: bool, file_path: str,
                                      episode: dict, series_name: str):
        """Appelé à la fin d'un téléchargement d'épisode."""
        if success and file_path:
            import os
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            ep_num   = episode.get("episode_num", "")
            ep_title = episode.get("title", "") or f"Épisode {ep_num}"
            full_name = f"{series_name}  —  Ép. {ep_num}  —  {ep_title}"
            add_download(
                name        = full_name,
                stream_id   = episode.get("id", 0),
                file_path   = file_path,
                file_size   = file_size,
                extension   = episode.get("container_extension", "mkv"),
                cover_local = ""
            )
            self._refresh_downloads()
            self.status.showMessage(f"✅  Téléchargement terminé : {full_name}")
        else:
            self.status.showMessage("❌  Téléchargement annulé ou échoué.")

    def _play_season_playlist(self, url_title_pairs: list):
        """Lance la lecture séquentielle de tous les épisodes d'une saison."""
        if not url_title_pairs:
            return
        if self.player_win and self.player_win.isVisible():
            self.player_win.close_player()
        self.player_win = PlayerWindow(screen_index=0)
        self.player_win.closed.connect(self._on_player_closed)
        self.player_win.show()
        QTimer.singleShot(300, lambda: self.player_win.play_playlist(url_title_pairs))

        # Mode visionnage : même comportement que _open_player
        self._idle_timer.stop()
        self._start_bg_thumbnails(delay_s=2.0)

    def _download_season(self, episodes: list, series_name: str):
        """Lance le téléchargement séquentiel de tous les épisodes d'une saison."""
        client = self._get_client()
        if not client:
            return

        # Construire la liste des infos à télécharger
        episodes_to_dl = []
        for ep in episodes:
            stream_id = ep.get("id")
            ext       = ep.get("container_extension", "mkv")
            url       = client.get_episode_url(stream_id, ext)
            ep_num    = ep.get("episode_num", "")
            ep_title  = ep.get("title", "") or f"Épisode {ep_num}"
            full_name = f"{series_name}  —  Ép. {ep_num}  —  {ep_title}"
            episodes_to_dl.append({
                "url": url, "name": full_name, "ext": ext,
                "episode": ep, "series_name": series_name
            })

        series_dest = get_series_dir(series_name)   # …/IPTVPlayer/<Nom série>/
        dlg = SeasonDownloadDialog(episodes_to_dl, dest_dir=series_dest, parent=self)
        dlg.season_download_finished.connect(
            lambda results: self._on_season_download_finished(results, episodes_to_dl)
        )
        dlg.exec()

    def _on_season_download_finished(self, results: list, episodes_meta: list):
        """Enregistre en base les épisodes téléchargés avec succès."""
        n_ok = 0
        for i, (success, file_path) in enumerate(results):
            if success and file_path and i < len(episodes_meta):
                import os
                meta      = episodes_meta[i]
                file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                ep        = meta.get("episode", {})
                add_download(
                    name        = meta["name"],
                    stream_id   = ep.get("id", 0),
                    file_path   = file_path,
                    file_size   = file_size,
                    extension   = meta["ext"],
                    cover_local = ""
                )
                n_ok += 1
        self._refresh_downloads()
        self.status.showMessage(f"✅  Saison téléchargée : {n_ok} / {len(results)} épisodes.")

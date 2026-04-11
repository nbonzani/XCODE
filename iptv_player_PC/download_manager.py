"""
download_manager.py - Téléchargement de films et d'épisodes en local.

Composants :
  DownloadThread         → QThread qui télécharge un fichier en streaming
                           et émet la progression octet par octet.
  DownloadProgressDialog → Fenêtre de progression (un seul fichier)
                           avec vitesse, ETA et bouton Annuler.
  SeasonDownloadDialog   → Fenêtre de progression pour le téléchargement
                           séquentiel de tous les épisodes d'une saison.

Les fichiers sont sauvegardés dans :
    %USERPROFILE%\\Videos\\IPTVPlayer\\
"""

import re
import time
import requests

from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer


# Dossier racine des téléchargements
DOWNLOADS_DIR = Path.home() / "Videos" / "IPTVPlayer"

# Sous-répertoire pour les films
MOVIES_DIR = DOWNLOADS_DIR / "Films"


def get_series_dir(series_name: str) -> Path:
    """
    Retourne le sous-répertoire de destination pour une série.

    Exemple : "Breaking Bad" → …/IPTVPlayer/Breaking Bad/

    Args:
        series_name : Nom de la série (sera nettoyé pour être utilisé comme dossier).
    """
    return DOWNLOADS_DIR / _safe_filename(series_name)


def _safe_filename(name: str) -> str:
    """
    Transforme un titre en nom de fichier valide sous Windows.
    Remplace les caractères interdits par des underscores.
    """
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()


# ============================================================
# Thread de téléchargement
# ============================================================

class DownloadThread(QThread):
    """
    Télécharge un fichier vidéo en mode streaming (par blocs).
    N'occupe pas l'interface graphique (tourne en arrière-plan).

    Signals :
        progress(bytes_done: float, bytes_total: float, speed_kbps: float)
            → émis toutes les 500 ms environ (throttlé pour ne pas saturer l'UI)
            → bytes exprimés en float pour supporter les fichiers > 2 Go sans
              risque de dépassement de capacité des entiers C++ de Qt
        finished(success: bool, message: str, file_path: str)
            → émis à la fin (succès ou erreur)
    """

    # float, float, float : évite tout problème d'overflow pour les fichiers > 2 Go
    progress = pyqtSignal(float, float, float)   # (téléchargé, total, Ko/s)
    finished = pyqtSignal(bool, str, str)         # (succès, message, chemin)

    CHUNK_SIZE = 1024 * 512   # 512 Ko par bloc (réduit le nombre d'itérations)

    def __init__(self, url: str, filename: str,
                 dest_dir: Path = None, parent=None):
        """
        Args:
            url      : URL du flux vidéo Xtream (directe).
            filename : Nom du fichier de destination (sans chemin).
            dest_dir : Répertoire de destination. Par défaut : DOWNLOADS_DIR.
                       Passer MOVIES_DIR pour les films, ou get_series_dir(name)
                       pour les épisodes d'une série.
        """
        super().__init__(parent)
        self.url       = url
        self.filename  = filename
        self.dest_dir  = dest_dir if dest_dir is not None else DOWNLOADS_DIR
        self._cancel   = False

    def cancel(self) -> None:
        """Demande l'arrêt du téléchargement au prochain bloc."""
        self._cancel = True

    def run(self) -> None:
        """
        Télécharge le fichier bloc par bloc et met à jour la progression.

        Améliorations vs version précédente :
          - Signal émis en float → supporte les fichiers > 2 Go
          - Throttle : 1 signal max toutes les 500 ms → UI réactive même pour
            les très gros fichiers (sans saturer la file d'événements Qt)
          - Taille lue depuis 'X-Content-Length' si 'Content-Length' absent
        """
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        dest = self.dest_dir / self.filename

        try:
            resp = requests.get(self.url, stream=True, timeout=30)
            resp.raise_for_status()

            # Certains serveurs IPTV n'envoient pas Content-Length (chunked).
            # On tente aussi X-Content-Length (header non standard mais parfois présent).
            total = float(
                resp.headers.get("Content-Length")
                or resp.headers.get("X-Content-Length")
                or 0
            )
            done     = 0.0
            t0       = time.time()
            last_emit = 0.0   # timestamp du dernier signal émis

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=self.CHUNK_SIZE):
                    if self._cancel:
                        f.close()
                        try:
                            dest.unlink()
                        except Exception:
                            pass
                        self.finished.emit(False, "Téléchargement annulé.", "")
                        return

                    if chunk:
                        f.write(chunk)
                        done += len(chunk)

                        now     = time.time()
                        elapsed = now - t0
                        # Throttle : émettre au maximum 1 signal toutes les 500 ms
                        if now - last_emit >= 0.5:
                            speed      = (done / elapsed / 1024) if elapsed > 0 else 0.0
                            self.progress.emit(done, total, speed)
                            last_emit  = now

            self.finished.emit(
                True,
                f"Téléchargement terminé : {self.filename}",
                str(dest)
            )

        except Exception as e:
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
            self.finished.emit(False, f"Erreur : {e}", "")


# ============================================================
# Dialogue de progression
# ============================================================

class DownloadProgressDialog(QDialog):
    """
    Fenêtre de progression du téléchargement.

    Affiche :
      - Nom du film
      - Barre de progression
      - Vitesse de téléchargement (Ko/s ou Mo/s)
      - Temps estimé restant (ETA)
      - Bouton Annuler

    Signal :
        download_finished(success: bool, file_path: str)
            → émis à la fin du téléchargement
    """

    download_finished = pyqtSignal(bool, str)

    def __init__(self, url: str, movie_name: str,
                 container_extension: str = "mkv",
                 dest_dir: Path = None,
                 parent=None):
        """
        Args:
            url                 : URL du flux vidéo.
            movie_name          : Titre du film (affiché + utilisé pour le nom de fichier).
            container_extension : Extension vidéo (mkv, mp4…).
            dest_dir            : Répertoire de destination (défaut : DOWNLOADS_DIR).
        """
        super().__init__(parent)
        self.setWindowTitle("Téléchargement en cours")
        self.setModal(True)
        self.setFixedWidth(480)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self._dest_dir = dest_dir if dest_dir is not None else DOWNLOADS_DIR
        filename = f"{_safe_filename(movie_name)}.{container_extension}"

        self.setStyleSheet("""
            QDialog       { background-color: #0f0f1a; color: white; }
            QLabel        { color: white; }
            QProgressBar  {
                background-color: #1e1e38; border: 1px solid #3a3a5a;
                border-radius: 4px; height: 20px; text-align: center;
                color: white;
            }
            QProgressBar::chunk { background-color: #1565C0; border-radius: 3px; }
        """)

        self._build_ui(movie_name, filename)

        # Lancer le thread de téléchargement avec le bon répertoire de destination
        self._thread = DownloadThread(url, filename, dest_dir=self._dest_dir)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_finished)
        self._thread.start()

        # Timer pour calculer l'ETA
        self._start_time = time.time()

    def _build_ui(self, movie_name: str, filename: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Titre
        lbl_title = QLabel(f"⬇️  {movie_name}")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: white;")
        lbl_title.setWordWrap(True)
        layout.addWidget(lbl_title)

        # Destination
        dest_path = self._dest_dir / filename
        lbl_dest = QLabel(f"📁  {dest_path}")
        lbl_dest.setStyleSheet("color: #888; font-size: 11px;")
        lbl_dest.setWordWrap(True)
        layout.addWidget(lbl_dest)

        # Barre de progression
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        # Infos (vitesse + ETA + taille)
        info_row = QHBoxLayout()
        self.lbl_speed = QLabel("Connexion…")
        self.lbl_speed.setStyleSheet("color: #aaa; font-size: 12px;")
        self.lbl_eta = QLabel("")
        self.lbl_eta.setStyleSheet("color: #aaa; font-size: 12px;")
        self.lbl_size = QLabel("")
        self.lbl_size.setStyleSheet("color: #aaa; font-size: 12px;")
        info_row.addWidget(self.lbl_speed)
        info_row.addStretch()
        info_row.addWidget(self.lbl_size)
        info_row.addStretch()
        info_row.addWidget(self.lbl_eta)
        layout.addLayout(info_row)

        # Bouton annuler
        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.setStyleSheet("""
            QPushButton { background-color: #c0392b; color: white;
                          border: none; border-radius: 4px; padding: 9px 20px; }
            QPushButton:hover { background-color: #e74c3c; }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(self.btn_cancel, alignment=Qt.AlignmentFlag.AlignRight)

    # ------------------------------------------------------------------ #
    #  Slots                                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _fmt_size(octets: float) -> str:
        """Formate une taille en octets en Mo ou Go selon la valeur."""
        go = octets / (1024 ** 3)
        if go >= 1.0:
            return f"{go:.2f} Go"
        return f"{octets / (1024 ** 2):.1f} Mo"

    def _on_progress(self, done: float, total: float, speed_kbps: float):
        """
        Met à jour la barre, la vitesse, la taille et l'ETA.

        Gère correctement les fichiers > 2 Go (paramètres float).
        Quand le serveur ne fournit pas la taille totale (total == 0),
        affiche la taille téléchargée et la vitesse sans ETA.
        """
        if total > 0:
            percent = int(done * 100 / total)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)

            # Taille (Mo ou Go selon la taille)
            self.lbl_size.setText(
                f"{self._fmt_size(done)} / {self._fmt_size(total)}"
            )

            # ETA
            if speed_kbps > 0:
                remaining_kb = (total - done) / 1024
                eta_s        = int(remaining_kb / speed_kbps)
                h, rem = divmod(eta_s, 3600)
                m, s   = divmod(rem, 60)
                if h > 0:
                    self.lbl_eta.setText(f"Reste : {h}h{m:02d}m")
                else:
                    self.lbl_eta.setText(f"Reste : {m}:{s:02d}")
        else:
            # Taille totale inconnue (serveur en chunked transfer)
            # → barre indéterminée + taille téléchargée uniquement
            self.progress_bar.setRange(0, 0)
            self.lbl_size.setText(
                f"{self._fmt_size(done)}  (taille totale inconnue)"
            )
            self.lbl_eta.setText("")

        # Vitesse
        if speed_kbps >= 1024:
            self.lbl_speed.setText(f"↓ {speed_kbps/1024:.1f} Mo/s")
        else:
            self.lbl_speed.setText(f"↓ {speed_kbps:.0f} Ko/s")

    def _on_finished(self, success: bool, message: str, file_path: str):
        """Appelé à la fin du téléchargement."""
        self.download_finished.emit(success, file_path)
        self.accept()

    def _on_cancel(self):
        """Annule le téléchargement."""
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Annulation…")
        self._thread.cancel()

    def closeEvent(self, event):
        """Empêche la fermeture pendant le téléchargement."""
        if self._thread.isRunning():
            self._thread.cancel()
        super().closeEvent(event)


# ============================================================
# Helpers
# ============================================================

def get_download_path(movie_name: str, extension: str,
                      dest_dir: Path = None) -> str:
    """
    Retourne le chemin complet où serait sauvegardé ce fichier.

    Args:
        movie_name : Titre (utilisé pour le nom du fichier).
        extension  : Extension vidéo (mkv, mp4…).
        dest_dir   : Répertoire de destination. Par défaut : DOWNLOADS_DIR.
    """
    base = dest_dir if dest_dir is not None else DOWNLOADS_DIR
    return str(base / f"{_safe_filename(movie_name)}.{extension}")


# ============================================================
# Dialogue de téléchargement d'une saison complète
# ============================================================

class SeasonDownloadDialog(QDialog):
    """
    Télécharge séquentiellement tous les épisodes d'une saison.

    Affiche :
      - Titre de la saison et avancement global (X / Y épisodes)
      - Titre de l'épisode en cours
      - Barre de progression de l'épisode en cours
      - Vitesse et ETA
      - Bouton Annuler (arrête après l'épisode en cours)

    Signal :
        season_download_finished(results: list)
            → liste de (success: bool, file_path: str) pour chaque épisode
    """

    season_download_finished = pyqtSignal(list)  # [(success, path), …]

    def __init__(self, episodes_to_download: list,
                 dest_dir: Path = None, parent=None):
        """
        Args:
            episodes_to_download : Liste de dicts avec clés :
                url      → URL du flux
                name     → Nom affiché et utilisé pour le fichier
                ext      → Extension (mkv, mp4…)
            dest_dir : Répertoire de destination commun à tous les épisodes.
        """
        super().__init__(parent)
        self.setWindowTitle("Téléchargement de la saison")
        self.setModal(True)
        self.setFixedWidth(520)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self._episodes   = episodes_to_download
        self._dest_dir   = dest_dir if dest_dir is not None else DOWNLOADS_DIR
        self._current    = 0
        self._results    = []          # accumule (success, path)
        self._cancelled  = False
        self._thread     = None
        self._start_time = 0.0

        self.setStyleSheet("""
            QDialog       { background-color: #0f0f1a; color: white; }
            QLabel        { color: white; }
            QProgressBar  {
                background-color: #1e1e38; border: 1px solid #3a3a5a;
                border-radius: 4px; height: 18px; text-align: center; color: white;
            }
            QProgressBar::chunk { background-color: #1565C0; border-radius: 3px; }
        """)

        self._build_ui()
        self._start_next()

    # ------------------------------------------------------------------ #
    #  Interface                                                            #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        total = len(self._episodes)

        # Titre principal
        self.lbl_header = QLabel(f"⬇️  Téléchargement de la saison — épisode 1 / {total}")
        self.lbl_header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.lbl_header)

        # Nom de l'épisode en cours
        self.lbl_ep = QLabel("")
        self.lbl_ep.setStyleSheet("color: #aaa; font-size: 12px;")
        self.lbl_ep.setWordWrap(True)
        layout.addWidget(self.lbl_ep)

        # Barre de progression : épisode en cours
        layout.addWidget(QLabel("Progression épisode :"))
        self.bar_ep = QProgressBar()
        self.bar_ep.setRange(0, 100)
        self.bar_ep.setValue(0)
        layout.addWidget(self.bar_ep)

        # Barre de progression : globale (nombre d'épisodes)
        layout.addWidget(QLabel("Progression globale :"))
        self.bar_total = QProgressBar()
        self.bar_total.setRange(0, total)
        self.bar_total.setValue(0)
        self.bar_total.setFormat(f"0 / {total} épisodes")
        layout.addWidget(self.bar_total)

        # Vitesse / ETA
        info_row = QHBoxLayout()
        self.lbl_speed = QLabel("Connexion…")
        self.lbl_speed.setStyleSheet("color: #aaa; font-size: 12px;")
        self.lbl_eta = QLabel("")
        self.lbl_eta.setStyleSheet("color: #aaa; font-size: 12px;")
        self.lbl_size = QLabel("")
        self.lbl_size.setStyleSheet("color: #aaa; font-size: 12px;")
        info_row.addWidget(self.lbl_speed)
        info_row.addStretch()
        info_row.addWidget(self.lbl_size)
        info_row.addStretch()
        info_row.addWidget(self.lbl_eta)
        layout.addLayout(info_row)

        # Boutons d'annulation (ligne de boutons)
        btn_cancel_row = QHBoxLayout()
        btn_cancel_row.addStretch()

        # Bouton 1 : attendre la fin de l'épisode en cours avant d'arrêter
        self.btn_cancel = QPushButton("⏭  Arrêter après cet épisode")
        self.btn_cancel.setStyleSheet("""
            QPushButton { background-color: #e67e22; color: white;
                          border: none; border-radius: 4px; padding: 9px 20px; }
            QPushButton:hover { background-color: #f39c12; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel)

        # Bouton 2 : stopper immédiatement le téléchargement en cours
        self.btn_cancel_now = QPushButton("⛔  Annuler maintenant")
        self.btn_cancel_now.setStyleSheet("""
            QPushButton { background-color: #c0392b; color: white;
                          border: none; border-radius: 4px; padding: 9px 20px;
                          font-weight: bold; }
            QPushButton:hover { background-color: #e74c3c; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self.btn_cancel_now.clicked.connect(self._on_cancel_now)

        btn_cancel_row.addWidget(self.btn_cancel)
        btn_cancel_row.addWidget(self.btn_cancel_now)
        layout.addLayout(btn_cancel_row)

    # ------------------------------------------------------------------ #
    #  Logique de téléchargement séquentiel                                #
    # ------------------------------------------------------------------ #

    def _start_next(self):
        """Lance le téléchargement de l'épisode courant."""
        if self._cancelled or self._current >= len(self._episodes):
            self._finish()
            return

        ep    = self._episodes[self._current]
        total = len(self._episodes)

        self.lbl_header.setText(
            f"⬇️  Téléchargement de la saison — épisode {self._current + 1} / {total}"
        )
        self.lbl_ep.setText(f"📄  {ep['name']}")
        self.bar_ep.setRange(0, 100)
        self.bar_ep.setValue(0)
        self.lbl_speed.setText("Connexion…")
        self.lbl_eta.setText("")
        self.lbl_size.setText("")
        self._start_time = time.time()

        filename = f"{_safe_filename(ep['name'])}.{ep['ext']}"
        self._thread = DownloadThread(ep["url"], filename, dest_dir=self._dest_dir)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_episode_finished)
        self._thread.start()

    @staticmethod
    def _fmt_size(octets: float) -> str:
        go = octets / (1024 ** 3)
        if go >= 1.0:
            return f"{go:.2f} Go"
        return f"{octets / (1024 ** 2):.1f} Mo"

    def _on_progress(self, done: float, total: float, speed_kbps: float):
        """Met à jour les indicateurs de l'épisode en cours."""
        if total > 0:
            self.bar_ep.setRange(0, 100)
            self.bar_ep.setValue(int(done * 100 / total))
            self.lbl_size.setText(
                f"{self._fmt_size(done)} / {self._fmt_size(total)}"
            )
            if speed_kbps > 0:
                remaining_kb = (total - done) / 1024
                eta_s = int(remaining_kb / speed_kbps)
                h, rem = divmod(eta_s, 3600)
                m, s   = divmod(rem, 60)
                if h > 0:
                    self.lbl_eta.setText(f"Reste : {h}h{m:02d}m")
                else:
                    self.lbl_eta.setText(f"Reste : {m}:{s:02d}")
        else:
            self.bar_ep.setRange(0, 0)
            self.lbl_size.setText(
                f"{self._fmt_size(done)}  (taille inconnue)"
            )
            self.lbl_eta.setText("")

        if speed_kbps >= 1024:
            self.lbl_speed.setText(f"↓ {speed_kbps/1024:.1f} Mo/s")
        else:
            self.lbl_speed.setText(f"↓ {speed_kbps:.0f} Ko/s")

    def _on_episode_finished(self, success: bool, message: str, file_path: str):
        """Appelé à la fin de chaque épisode. Lance le suivant."""
        self._results.append((success, file_path))
        self._current += 1
        n_done = self._current
        total  = len(self._episodes)
        self.bar_total.setValue(n_done)
        self.bar_total.setFormat(f"{n_done} / {total} épisodes")
        self._start_next()

    def _finish(self):
        """Tous les épisodes traités : émet le signal final et ferme."""
        self.season_download_finished.emit(self._results)
        self.accept()

    def _on_cancel(self):
        """
        Annulation douce : l'épisode en cours continue jusqu'à la fin,
        puis la saison s'arrête sans passer à l'épisode suivant.
        """
        self._cancelled = True
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Arrêt après cet épisode…")
        self.btn_cancel_now.setEnabled(True)   # toujours possible d'arrêter maintenant

    def _on_cancel_now(self):
        """
        Annulation immédiate : coupe le téléchargement en cours,
        supprime le fichier partiel, émet les résultats et ferme.
        """
        self._cancelled = True
        self.btn_cancel.setEnabled(False)
        self.btn_cancel_now.setEnabled(False)
        self.btn_cancel_now.setText("Annulation…")
        if self._thread and self._thread.isRunning():
            self._thread.cancel()
            # Attendre au maximum 3 secondes que le thread s'arrête
            self._thread.wait(3000)
        # Émettre les résultats partiels et fermer
        self.season_download_finished.emit(self._results)
        self.reject()

    def closeEvent(self, event):
        """Empêche la fermeture accidentelle (croix fenêtre) ; annule proprement."""
        if self._thread and self._thread.isRunning():
            self._cancelled = True
            self._thread.cancel()
            self._thread.wait(2000)
        self.season_download_finished.emit(self._results)
        super().closeEvent(event)

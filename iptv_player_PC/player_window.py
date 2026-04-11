"""
player_window.py - Fenêtre du lecteur vidéo intégrant VLC.

Fonctionnalités :
  - Lecture des flux IPTV via python-vlc
  - Écran cible paramétrable (principal ou secondaire)
  - Contrôles affichés au mouvement OU au clic sur l'écran
  - Masquage automatique des contrôles après 3 secondes d'inactivité

Raccourcis clavier :
  Espace      → Lecture / Pause
  Échap        → Fermer le lecteur
  → (droite)  → Avancer de 10 secondes
  ← (gauche)  → Reculer de 10 secondes
  Pg.Suiv     → Avancer de 5 minutes
  Pg.Préc     → Reculer de 5 minutes
  ↑ (haut)    → Volume + 5
  ↓ (bas)     → Volume - 5
  M           → Muet / Son
"""

import sys
import vlc

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor


class _ClickOverlay(QWidget):
    """
    Widget transparent superposé à la zone vidéo.

    Pourquoi ce widget est nécessaire :
        VLC dessine la vidéo dans une fenêtre Win32 native créée à
        l'intérieur de video_frame (via set_hwnd). Cette fenêtre Win32
        capture tous les événements souris avant PyQt6. L'overlay est
        positionné AU-DESSUS de cette fenêtre Win32 (il est un frère de
        video_frame, créé après lui, donc plus haut dans l'ordre Z) :
        les clics arrivent donc à l'overlay, qui les transmet à
        PlayerWindow.
    """

    def __init__(self, parent: "PlayerWindow"):
        super().__init__(parent)
        self.setMouseTracking(True)
        # Fond complètement transparent — l'overlay ne cache pas la vidéo
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event) -> None:
        """Transmet le clic à PlayerWindow."""
        self.parent().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Transmet le mouvement à PlayerWindow."""
        self.parent().mouseMoveEvent(event)


class PlayerWindow(QWidget):
    """
    Fenêtre plein-écran de lecture vidéo.

    Paramètres :
        screen_index : écran cible
            -1  → automatique (secondaire si dispo, sinon principal)
             0  → toujours l'écran principal
             1  → toujours l'écran secondaire
    """

    closed = pyqtSignal()

    def __init__(self, screen_index: int = -1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IPTV Player")
        self.setWindowFlags(Qt.WindowType.Window)
        self._screen_index = screen_index
        self._is_muted = False

        # --- VLC ---
        self.vlc_instance = vlc.Instance("--no-video-title-show", "--quiet")
        self.player = self.vlc_instance.media_player_new()

        # --- Timer mise à jour progression ---
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(500)
        self.progress_timer.timeout.connect(self._update_progress)

        # --- Timer masquage des contrôles ---
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(3000)
        self.hide_timer.timeout.connect(self._hide_controls)

        # --- Playlist (lecture séquentielle d'épisodes) ---
        self._playlist: list = []        # liste de (url, titre)
        self._playlist_index: int = 0
        # Vérifie toutes les 2 secondes si l'épisode en cours est terminé
        self.playlist_timer = QTimer(self)
        self.playlist_timer.setInterval(2000)
        self.playlist_timer.timeout.connect(self._check_playlist_advance)

        self.setMouseTracking(True)

        self._setup_ui()
        self._setup_screen()

        # --- Overlay transparent pour capturer les clics sur la vidéo ---
        # (voir docstring de _ClickOverlay pour l'explication)
        self.overlay = _ClickOverlay(self)
        self.overlay.raise_()   # S'assure qu'il est au premier plan

    # ------------------------------------------------------------------ #
    #  Interface                                                            #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        """Construit l'interface : zone vidéo + barre de contrôles."""
        self.setStyleSheet("background-color: black;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Zone vidéo (VLC dessine ici)
        self.video_frame = QFrame(self)
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.video_frame.setMouseTracking(True)
        main_layout.addWidget(self.video_frame)

        # Barre de contrôles
        self.controls = QWidget(self)
        self.controls.setStyleSheet("""
            QWidget   { background-color: rgba(0, 0, 0, 200); }
            QPushButton {
                background-color: transparent; color: white;
                border: none; font-size: 18px; padding: 6px 10px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,25); border-radius: 4px; }
            QLabel { color: white; font-size: 12px; }
            QSlider::groove:horizontal {
                height: 5px; background: rgba(255,255,255,50); border-radius: 2px;
            }
            QSlider::sub-page:horizontal { background: #2196F3; border-radius: 2px; }
            QSlider::handle:horizontal {
                background: white; width: 14px; height: 14px;
                margin: -4px 0; border-radius: 7px;
            }
        """)
        self.controls.setMouseTracking(True)

        ctrl_layout = QVBoxLayout(self.controls)
        ctrl_layout.setContentsMargins(12, 6, 12, 10)
        ctrl_layout.setSpacing(4)

        # Barre de progression
        prog_row = QHBoxLayout()
        self.lbl_time = QLabel("0:00")
        self.lbl_time.setFixedWidth(50)
        self.slider_progress = QSlider(Qt.Orientation.Horizontal)
        self.slider_progress.setRange(0, 1000)
        self.slider_progress.sliderMoved.connect(self._seek)
        self.lbl_duration = QLabel("0:00")
        self.lbl_duration.setFixedWidth(50)
        self.lbl_duration.setAlignment(Qt.AlignmentFlag.AlignRight)
        prog_row.addWidget(self.lbl_time)
        prog_row.addWidget(self.slider_progress)
        prog_row.addWidget(self.lbl_duration)
        ctrl_layout.addLayout(prog_row)

        # Boutons
        btn_row = QHBoxLayout()

        self.btn_play = QPushButton("⏸")
        self.btn_play.setFixedSize(42, 42)
        self.btn_play.clicked.connect(self._toggle_play)

        self.btn_stop = QPushButton("⏹")
        self.btn_stop.setFixedSize(42, 42)
        self.btn_stop.clicked.connect(self._stop)

        self.lbl_title = QLabel("")
        self.lbl_title.setStyleSheet(
            "color: white; font-size: 13px; font-weight: bold;"
        )

        self.btn_mute = QPushButton("🔊")
        self.btn_mute.setFixedSize(42, 42)
        self.btn_mute.clicked.connect(self._toggle_mute)

        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(100)
        self.slider_volume.setFixedWidth(110)
        self.slider_volume.valueChanged.connect(self._set_volume)

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(42, 42)
        self.btn_close.setStyleSheet("""
            QPushButton { color: #ccc; font-size: 16px; }
            QPushButton:hover { background-color: #c0392b; border-radius: 4px; }
        """)
        self.btn_close.clicked.connect(self.close_player)

        btn_row.addWidget(self.btn_play)
        btn_row.addWidget(self.btn_stop)
        btn_row.addSpacing(10)
        btn_row.addWidget(self.lbl_title)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_mute)
        btn_row.addWidget(self.slider_volume)
        btn_row.addSpacing(10)
        btn_row.addWidget(self.btn_close)

        ctrl_layout.addLayout(btn_row)

        # Aide raccourcis (ligne discrète en bas)
        shortcuts_label = QLabel(
            "Espace : pause  ·  ←/→ : ±10s  ·  Pg.↑↓ : ±5min  ·  ↑/↓ : volume  ·  M : muet  ·  Échap : fermer"
        )
        shortcuts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shortcuts_label.setStyleSheet("color: rgba(255,255,255,80); font-size: 10px;")
        ctrl_layout.addWidget(shortcuts_label)

        main_layout.addWidget(self.controls)

    # ------------------------------------------------------------------ #
    #  Redimensionnement                                                   #
    # ------------------------------------------------------------------ #

    def resizeEvent(self, event) -> None:
        """
        Met à jour la taille et la position de l'overlay à chaque
        redimensionnement de la fenêtre, pour qu'il couvre exactement
        la zone vidéo.
        """
        super().resizeEvent(event)
        if hasattr(self, "overlay") and hasattr(self, "video_frame"):
            self.overlay.setGeometry(self.video_frame.geometry())
            self.overlay.raise_()

    # ------------------------------------------------------------------ #
    #  Positionnement sur l'écran                                          #
    # ------------------------------------------------------------------ #

    def _setup_screen(self):
        """
        Positionne la fenêtre sur l'écran cible défini par screen_index.

        screen_index :
            -1  → secondaire si disponible, sinon principal
             0  → principal
             1  → secondaire
        """
        screens = QApplication.screens()

        if self._screen_index == 0:
            target = screens[0]
        elif self._screen_index == 1 and len(screens) > 1:
            target = screens[1]
        else:
            # Automatique : secondaire si disponible
            target = screens[1] if len(screens) > 1 else screens[0]

        self.setGeometry(target.geometry())
        self.showFullScreen()

    # ------------------------------------------------------------------ #
    #  Lecture                                                              #
    # ------------------------------------------------------------------ #

    def play(self, url: str, title: str = "") -> None:
        """
        Lance la lecture d'un flux vidéo.

        Args:
            url   : URL du flux (locale ou distante).
            title : Titre affiché dans la barre de contrôles.
        """
        media = self.vlc_instance.media_new(url)
        self.player.set_media(media)

        if sys.platform == "win32":
            self.player.set_hwnd(int(self.video_frame.winId()))
        elif sys.platform == "darwin":
            self.player.set_nsobject(int(self.video_frame.winId()))
        else:
            self.player.set_xwindow(int(self.video_frame.winId()))

        self.player.play()
        self.progress_timer.start()
        self.btn_play.setText("⏸")
        self.lbl_title.setText(title)
        self.hide_timer.start()

        # Force PlayerWindow à capturer tous les événements clavier,
        # même si VLC ou un autre widget a pris le focus.
        self.setFocus()
        self.grabKeyboard()

    def play_playlist(self, url_title_pairs: list) -> None:
        """
        Lit une liste de médias en séquence automatique.

        Args:
            url_title_pairs : Liste de tuples (url, titre) à enchaîner.
        """
        if not url_title_pairs:
            return
        self._playlist       = list(url_title_pairs)
        self._playlist_index = 0
        url, title = self._playlist[0]
        self.play(url, title)
        if len(self._playlist) > 1:
            # Démarrer la surveillance d'avancement
            self.playlist_timer.start()

    def _check_playlist_advance(self) -> None:
        """
        Appelé toutes les 2 secondes : détecte la fin de l'épisode
        en cours et passe automatiquement au suivant.
        """
        state = self.player.get_state()
        # vlc.State.Ended = 6, vlc.State.Stopped = 5
        if state in (vlc.State.Ended, vlc.State.Stopped):
            self._playlist_index += 1
            if self._playlist_index < len(self._playlist):
                url, title = self._playlist[self._playlist_index]
                self.play(url, title)
            else:
                # Fin de la playlist
                self.playlist_timer.stop()
                self._playlist = []

    def _toggle_play(self) -> None:
        """Bascule lecture / pause."""
        if self.player.is_playing():
            self.player.pause()
            self.btn_play.setText("▶")
            self.hide_timer.stop()
        else:
            self.player.play()
            self.btn_play.setText("⏸")
            self.hide_timer.start()

    def _stop(self) -> None:
        """Arrête la lecture."""
        self.player.stop()
        self.progress_timer.stop()
        self.btn_play.setText("▶")
        self.slider_progress.setValue(0)
        self.lbl_time.setText("0:00")
        self.lbl_duration.setText("0:00")

    def _seek(self, value: int) -> None:
        """Déplace la position de lecture (0–1000)."""
        if self.player.get_length() > 0:
            self.player.set_position(value / 1000.0)

    def _set_volume(self, value: int) -> None:
        """Règle le volume (0–100)."""
        self.player.audio_set_volume(value)
        self._is_muted = (value == 0)
        self.btn_mute.setText("🔇" if self._is_muted else "🔊")

    def _toggle_mute(self) -> None:
        """Bascule muet / son."""
        if self._is_muted:
            self._is_muted = False
            self.player.audio_set_mute(False)
            self.btn_mute.setText("🔊")
        else:
            self._is_muted = True
            self.player.audio_set_mute(True)
            self.btn_mute.setText("🔇")

    # ------------------------------------------------------------------ #
    #  Mise à jour de la progression                                        #
    # ------------------------------------------------------------------ #

    def _update_progress(self) -> None:
        """Met à jour le slider et les labels de temps."""
        if not self.player.is_playing():
            return

        pos         = self.player.get_position()
        time_ms     = self.player.get_time()
        duration_ms = self.player.get_length()

        self.slider_progress.blockSignals(True)
        self.slider_progress.setValue(int(pos * 1000))
        self.slider_progress.blockSignals(False)

        self.lbl_time.setText(self._fmt(time_ms))
        self.lbl_duration.setText(self._fmt(duration_ms))

    @staticmethod
    def _fmt(ms: int) -> str:
        """Convertit des millisecondes en H:MM:SS ou M:SS."""
        if ms <= 0:
            return "0:00"
        s = ms // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

    # ------------------------------------------------------------------ #
    #  Affichage / masquage des contrôles                                  #
    # ------------------------------------------------------------------ #

    def _show_controls(self) -> None:
        """Affiche la barre de contrôles et le curseur."""
        if not self.controls.isVisible():
            self.controls.show()
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def _hide_controls(self) -> None:
        """Cache la barre de contrôles et le curseur."""
        self.controls.hide()
        self.setCursor(QCursor(Qt.CursorShape.BlankCursor))

    def _reset_hide_timer(self) -> None:
        """Relance le timer de masquage si la vidéo est en cours."""
        if self.player.is_playing():
            self.hide_timer.start()

    def mouseMoveEvent(self, event) -> None:
        """Affiche les contrôles au mouvement de la souris."""
        self._show_controls()
        self._reset_hide_timer()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        """
        Clic gauche : bascule l'affichage des contrôles.
        Clic droit  : lecture / pause.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            if self.controls.isVisible():
                self._hide_controls()
                self.hide_timer.stop()
            else:
                self._show_controls()
                self._reset_hide_timer()
        elif event.button() == Qt.MouseButton.RightButton:
            self._toggle_play()
        super().mousePressEvent(event)

    # ------------------------------------------------------------------ #
    #  Raccourcis clavier                                                  #
    # ------------------------------------------------------------------ #

    def keyPressEvent(self, event) -> None:
        """
        Raccourcis clavier disponibles :
          Espace       → Lecture / Pause
          Échap         → Fermer le lecteur
          → (droite)   → Avancer de 10 secondes
          ← (gauche)   → Reculer de 10 secondes
          Page Suivant → Avancer de 5 minutes
          Page Préc.   → Reculer de 5 minutes
          ↑ (haut)     → Volume + 5
          ↓ (bas)      → Volume - 5
          M            → Muet / Son
        """
        key = event.key()

        if key == Qt.Key.Key_Space:
            self._toggle_play()

        elif key == Qt.Key.Key_Escape:
            self.close_player()

        elif key == Qt.Key.Key_Right:
            self.player.set_time(self.player.get_time() + 10_000)

        elif key == Qt.Key.Key_Left:
            self.player.set_time(max(0, self.player.get_time() - 10_000))

        elif key == Qt.Key.Key_PageDown:
            self.player.set_time(self.player.get_time() + 300_000)   # +5 min

        elif key == Qt.Key.Key_PageUp:
            self.player.set_time(max(0, self.player.get_time() - 300_000))  # -5 min

        elif key == Qt.Key.Key_Up:
            vol = min(100, self.player.audio_get_volume() + 5)
            self.player.audio_set_volume(vol)
            self.slider_volume.setValue(vol)

        elif key == Qt.Key.Key_Down:
            vol = max(0, self.player.audio_get_volume() - 5)
            self.player.audio_set_volume(vol)
            self.slider_volume.setValue(vol)

        elif key == Qt.Key.Key_M:
            self._toggle_mute()

        else:
            super().keyPressEvent(event)

        # Afficher les contrôles brièvement à chaque action clavier
        self._show_controls()
        self._reset_hide_timer()

    # ------------------------------------------------------------------ #
    #  Fermeture                                                            #
    # ------------------------------------------------------------------ #

    def close_player(self) -> None:
        """Arrête la lecture et ferme proprement la fenêtre."""
        self.releaseKeyboard()   # Libère la capture clavier
        self.player.stop()
        self.progress_timer.stop()
        self.hide_timer.stop()
        self.playlist_timer.stop()
        self._playlist = []
        self.closed.emit()
        self.close()

    def closeEvent(self, event) -> None:
        self.releaseKeyboard()   # Libère la capture clavier
        self.player.stop()
        self.progress_timer.stop()
        self.hide_timer.stop()
        self.playlist_timer.stop()
        self._playlist = []
        self.closed.emit()
        super().closeEvent(event)

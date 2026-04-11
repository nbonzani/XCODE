import sys
import vlc

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSlider, QLabel, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QLinearGradient


# ── Raccourcis affichés dans l'overlay ──────────────────────────────
_SHORTCUTS = [
    ("Espace",        "Lecture / Pause"),
    ("←  /  →",       "Reculer / Avancer 10 s"),
    ("↑  /  ↓",       "Volume  +10  /  -10"),
    ("M",             "Muet / Son"),
    ("F  /  Echap",   "Quitter le plein ecran"),
    ("Double-clic",   "Basculer plein ecran"),
    ("H  /  ?",       "Afficher / masquer les raccourcis"),
]

_BOX_W   = 500
_ROW_H   = 38
_TITLE_H = 42
_SEP_Y   = 44
_PAD_TOP = 52
_BOX_H   = _PAD_TOP + len(_SHORTCUTS) * _ROW_H + 16


# ── Overlay raccourcis ───────────────────────────────────────────────
class _ShortcutsOverlay(QWidget):
    """Overlay semi-transparent listant les raccourcis clavier."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setVisible(False)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width()  // 2
        cy = self.height() // 2
        x  = cx - _BOX_W // 2
        y  = cy - _BOX_H // 2

        p.setBrush(QColor(10, 10, 10, 200))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(x, y, _BOX_W, _BOX_H, 16, 16)

        tf = QFont()
        tf.setBold(True)
        tf.setPointSize(15)
        p.setFont(tf)
        p.setPen(QColor(255, 255, 255))
        p.drawText(x, y + 4, _BOX_W, _TITLE_H,
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   "Raccourcis clavier")

        p.setPen(QColor(180, 180, 180, 100))
        p.drawLine(x + 20, y + _SEP_Y, x + _BOX_W - 20, y + _SEP_Y)

        col_key_w  = 180
        col_sep    = 12
        col_desc_x = x + 20 + col_key_w + col_sep

        kf = QFont()
        kf.setBold(True)
        kf.setPointSize(13)
        df = QFont()
        df.setPointSize(13)

        for i, (key, desc) in enumerate(_SHORTCUTS):
            ry = y + _PAD_TOP + i * _ROW_H

            p.setFont(kf)
            p.setPen(QColor(255, 215, 60))
            p.drawText(x + 20, ry, col_key_w, _ROW_H,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       key)

            p.setPen(QColor(120, 120, 120, 160))
            mid_x = x + 20 + col_key_w + col_sep // 2
            p.drawLine(mid_x, ry + 6, mid_x, ry + _ROW_H - 6)

            p.setFont(df)
            p.setPen(QColor(225, 225, 225))
            p.drawText(col_desc_x, ry, _BOX_W - (col_desc_x - x) - 16, _ROW_H,
                       Qt.AlignmentFlag.AlignVCenter, desc)


# ── Barre de contrôles plein écran ──────────────────────────────────
class _ControlsBar(QWidget):
    """
    Barre de contrôles semi-transparente ancrée en bas de la zone vidéo.
    Visible uniquement en mode plein écran, sur activité souris.
    Émet des signaux vers VLCPlayerWindow ; ne touche pas à l'état plein écran.
    """

    play_pause_clicked = pyqtSignal()
    seek_clicked       = pyqtSignal(int)    # delta en ms
    mute_clicked       = pyqtSignal()
    volume_clicked     = pyqtSignal(int)    # delta
    position_seeked    = pyqtSignal(float)  # fraction 0.0–1.0

    BAR_H = 110

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedHeight(self.BAR_H)
        self.setMouseTracking(True)
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 6, 24, 14)
        layout.setSpacing(8)

        # Slider de progression
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setStyleSheet(
            "QSlider::groove:horizontal {"
            "  height: 6px; background: rgba(255,255,255,70); border-radius: 3px;}"
            "QSlider::sub-page:horizontal {"
            "  background: rgba(255,255,255,210); border-radius: 3px;}"
            "QSlider::handle:horizontal {"
            "  background: white; width: 16px; height: 16px;"
            "  margin: -5px 0; border-radius: 8px;}"
        )
        self.seek_slider.sliderReleased.connect(
            lambda: self.position_seeked.emit(self.seek_slider.value() / 1000.0)
        )
        layout.addWidget(self.seek_slider)

        # Rangée de boutons
        row = QHBoxLayout()
        row.setSpacing(10)

        self.btn_back = self._btn("◄◄  10s",
                                  lambda: self.seek_clicked.emit(-10_000))
        self.btn_play = self._btn("▶",      self.play_pause_clicked.emit)
        self.btn_fwd  = self._btn("10s  ►►",
                                  lambda: self.seek_clicked.emit(+10_000))
        self.btn_mute = self._btn("Muet",   self.mute_clicked.emit)
        self.btn_volm = self._btn("Vol  —",
                                  lambda: self.volume_clicked.emit(-10))
        self.btn_volp = self._btn("Vol  +",
                                  lambda: self.volume_clicked.emit(+10))

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet(
            "color: white; font-size: 14px; font-weight: bold; padding: 0 10px;"
        )

        for w in (self.btn_back, self.btn_play, self.btn_fwd,
                  self.btn_mute, self.btn_volm, self.btn_volp):
            row.addWidget(w)
        row.addStretch()
        row.addWidget(self.lbl_time)
        layout.addLayout(row)

    @staticmethod
    def _btn(text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(44)
        b.setMinimumWidth(90)
        b.setStyleSheet(
            "QPushButton {"
            "  background-color: rgba(15, 15, 15, 175);"
            "  color: white; font-size: 14px; font-weight: bold;"
            "  border: 1px solid rgba(255,255,255,60);"
            "  border-radius: 8px; padding: 0 14px;"
            "}"
            "QPushButton:hover   { background-color: rgba(80,80,80,210); }"
            "QPushButton:pressed { background-color: rgba(150,150,150,230); }"
        )
        b.clicked.connect(slot)
        return b

    def update_state(self, pos_frac: float, time_str: str,
                     is_playing: bool, muted: bool):
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(int(pos_frac * 1000))
        self.lbl_time.setText(time_str)
        self.btn_play.setText("❚❚" if is_playing else "▶")
        self.btn_mute.setText("Son" if muted else "Muet")

    def paintEvent(self, event):
        """Dégradé sombre en bas, transparent en haut."""
        p = QPainter(self)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.00, QColor(0, 0, 0,   0))
        grad.setColorAt(0.30, QColor(0, 0, 0, 160))
        grad.setColorAt(1.00, QColor(0, 0, 0, 225))
        p.fillRect(self.rect(), grad)


# ── Fenêtre principale du lecteur ────────────────────────────────────
class VLCPlayerWindow(QWidget):
    """Fenetre independante pour la lecture video VLC."""

    _SEEK_STEP_MS = 10_000
    _VOL_STEP     = 10

    def __init__(self):
        super().__init__()
        self._instance = vlc.Instance("--no-xlib", "--quiet")
        self._player   = self._instance.media_player_new()
        self._slider_dragging = False
        self._is_fullscreen   = False
        self._muted           = False
        self._vol_before_mute = 80

        self.setWindowTitle("Lecteur video")
        self.resize(900, 600)
        self.setMouseTracking(True)

        self._setup_ui()

        # Timer mise à jour UI
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._update_ui)

        # Timer auto-masquage overlay raccourcis (plein écran)
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.setInterval(3000)
        self._overlay_timer.timeout.connect(self._hide_shortcuts)

        # Timer inactivité souris → masquer barre de contrôles + curseur
        self._mouse_timer = QTimer(self)
        self._mouse_timer.setSingleShot(True)
        self._mouse_timer.setInterval(3000)
        self._mouse_timer.timeout.connect(self._on_mouse_idle)

    # ── Construction UI ──────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Zone vidéo
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setMinimumHeight(300)
        self.video_frame.setMouseTracking(True)
        layout.addWidget(self.video_frame, stretch=1)

        # Titre (mode fenêtré)
        self.lbl_title = QLabel("")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet("color: #ccc; font-size: 12px; padding: 2px;")
        layout.addWidget(self.lbl_title)

        # Slider de position (mode fenêtré)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(self._slider_pressed)
        self.slider.sliderReleased.connect(self._slider_released)
        layout.addWidget(self.slider)

        # Barre de contrôles (mode fenêtré)
        self._ctrl_widget = QWidget()
        ctrl = QHBoxLayout(self._ctrl_widget)
        ctrl.setSpacing(8)
        ctrl.setContentsMargins(4, 0, 4, 4)

        self.btn_play = QPushButton("Pause")
        self.btn_play.setFixedSize(70, 32)
        self.btn_play.clicked.connect(self._toggle_play)
        ctrl.addWidget(self.btn_play)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setFixedSize(70, 32)
        self.btn_stop.clicked.connect(self._stop)
        ctrl.addWidget(self.btn_stop)

        self.btn_mute = QPushButton("Muet")
        self.btn_mute.setFixedSize(60, 32)
        self.btn_mute.setCheckable(True)
        self.btn_mute.clicked.connect(self._toggle_mute)
        ctrl.addWidget(self.btn_mute)

        self.btn_fullscreen = QPushButton("Plein ecran")
        self.btn_fullscreen.setFixedSize(110, 32)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        ctrl.addWidget(self.btn_fullscreen)

        self.btn_help = QPushButton("?")
        self.btn_help.setFixedSize(32, 32)
        self.btn_help.setToolTip("Afficher / masquer les raccourcis (H)")
        self.btn_help.clicked.connect(self._toggle_shortcuts_manual)
        ctrl.addWidget(self.btn_help)

        ctrl.addStretch()
        ctrl.addWidget(QLabel("Vol:"))
        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(80)
        self.slider_volume.setFixedWidth(120)
        self.slider_volume.valueChanged.connect(self._set_volume)
        ctrl.addWidget(self.slider_volume)

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setFixedWidth(120)
        ctrl.addWidget(self.lbl_time)

        layout.addWidget(self._ctrl_widget)

        # ── Widgets flottants (enfants de self, z-order élevé) ───────

        # Overlay raccourcis (transparent aux clics)
        self._shortcuts = _ShortcutsOverlay(self)

        # Barre de contrôles plein écran
        self._ctrl_bar = _ControlsBar(self)
        self._ctrl_bar.play_pause_clicked.connect(self._toggle_play)
        self._ctrl_bar.seek_clicked.connect(self._seek)
        self._ctrl_bar.mute_clicked.connect(self._toggle_mute)
        self._ctrl_bar.volume_clicked.connect(self._change_volume)
        self._ctrl_bar.position_seeked.connect(
            lambda f: self._player.set_position(f)
        )

        # Suivi souris sur video_frame et barre de contrôles
        self.video_frame.installEventFilter(self)
        self._install_tracking(self._ctrl_bar)

    def _install_tracking(self, widget: QWidget):
        """Active le suivi souris et installe le filtre d'événements sur widget et ses enfants."""
        widget.setMouseTracking(True)
        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget):
            child.setMouseTracking(True)
            child.installEventFilter(self)

    # ── Plein écran ──────────────────────────────────────────────────

    def _show_windowed_controls(self, visible: bool):
        self.lbl_title.setVisible(visible)
        self.slider.setVisible(visible)
        self._ctrl_widget.setVisible(visible)

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        self._show_windowed_controls(False)
        self._is_fullscreen = True
        self.showFullScreen()
        self.setCursor(Qt.CursorShape.BlankCursor)
        # Affiche les raccourcis 3 s pour rappel
        QTimer.singleShot(120, lambda: self._show_shortcuts(auto_hide=True))

    def _exit_fullscreen(self):
        self._overlay_timer.stop()
        self._mouse_timer.stop()
        self._shortcuts.setVisible(False)
        self._ctrl_bar.setVisible(False)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._is_fullscreen = False
        self.showNormal()
        self._show_windowed_controls(True)

    # ── Overlay raccourcis ───────────────────────────────────────────

    def _show_shortcuts(self, auto_hide: bool = False):
        self._overlay_timer.stop()
        self._shortcuts.setGeometry(self.video_frame.geometry())
        self._shortcuts.setVisible(True)
        self._shortcuts.raise_()
        self._shortcuts.update()
        if auto_hide:
            self._overlay_timer.start()

    def _hide_shortcuts(self):
        self._shortcuts.setVisible(False)

    def _toggle_shortcuts_manual(self):
        if self._shortcuts.isVisible():
            self._overlay_timer.stop()
            self._hide_shortcuts()
        else:
            self._show_shortcuts(auto_hide=False)

    # ── Barre de contrôles plein écran ───────────────────────────────

    def _position_ctrl_bar(self):
        w, h = self.width(), self.height()
        self._ctrl_bar.setGeometry(0, h - _ControlsBar.BAR_H, w, _ControlsBar.BAR_H)

    def _on_mouse_activity(self):
        """Appelé sur tout mouvement/clic souris en mode plein écran."""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._position_ctrl_bar()
        self._ctrl_bar.setVisible(True)
        self._ctrl_bar.raise_()
        self._mouse_timer.start()   # (re)démarre le compte à rebours 3 s

    def _on_mouse_idle(self):
        """Après 3 s sans activité souris : masque barre + curseur."""
        self._ctrl_bar.setVisible(False)
        self.setCursor(Qt.CursorShape.BlankCursor)

    # ── Filtre d'événements (mouse tracking) ─────────────────────────

    def eventFilter(self, obj, event):
        if self._is_fullscreen and event.type() in (
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonPress,
        ):
            self._on_mouse_activity()
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event):
        if self._is_fullscreen:
            self._on_mouse_activity()
        super().mouseMoveEvent(event)

    # ── Redimensionnement ────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._shortcuts.isVisible():
            self._shortcuts.setGeometry(self.video_frame.geometry())
        if self._ctrl_bar.isVisible():
            self._position_ctrl_bar()

    # ── Lecture ──────────────────────────────────────────────────────

    def play_url(self, url: str, title: str = ""):
        media = self._instance.media_new(url)
        self._player.set_media(media)

        if sys.platform == "win32":
            self._player.set_hwnd(int(self.video_frame.winId()))
        elif sys.platform == "darwin":
            self._player.set_nsobject(int(self.video_frame.winId()))
        else:
            self._player.set_xwindow(int(self.video_frame.winId()))

        self._player.audio_set_volume(self.slider_volume.value())
        self._player.play()
        self.btn_play.setText("Pause")
        self.lbl_title.setText(title or url)
        self.setWindowTitle(title or "Lecteur video")
        self._timer.start()
        self.show()
        self.raise_()
        self.activateWindow()

    def _stop(self):
        self._player.stop()
        self._timer.stop()
        self.btn_play.setText("Play")
        self.slider.setValue(0)
        self.lbl_time.setText("00:00 / 00:00")

    def _toggle_play(self):
        if self._player.is_playing():
            self._player.pause()
            self.btn_play.setText("Play")
        else:
            self._player.play()
            self.btn_play.setText("Pause")
            self._timer.start()

    # ── Volume / Muet ────────────────────────────────────────────────

    def _set_volume(self, value: int):
        self._player.audio_set_volume(value)

    def _toggle_mute(self):
        if self._muted:
            self._muted = False
            vol = self._vol_before_mute
            self.slider_volume.setValue(vol)
            self._player.audio_set_volume(vol)
            self.btn_mute.setChecked(False)
            self.btn_mute.setText("Muet")
        else:
            self._muted = True
            self._vol_before_mute = self.slider_volume.value()
            self._player.audio_set_volume(0)
            self.btn_mute.setChecked(True)
            self.btn_mute.setText("Son")

    def _change_volume(self, delta: int):
        new_vol = max(0, min(100, self.slider_volume.value() + delta))
        self.slider_volume.setValue(new_vol)
        if self._muted and new_vol > 0:
            self._muted = False
            self.btn_mute.setChecked(False)
            self.btn_mute.setText("Muet")

    # ── Déplacement dans la vidéo ────────────────────────────────────

    def _seek(self, delta_ms: int):
        current = self._player.get_time()
        total   = self._player.get_length()
        if current < 0 or total <= 0:
            return
        self._player.set_time(max(0, min(total, current + delta_ms)))

    # ── Mise à jour UI (timer 500 ms) ────────────────────────────────

    def _slider_pressed(self):
        self._slider_dragging = True

    def _slider_released(self):
        self._slider_dragging = False
        self._player.set_position(self.slider.value() / 1000.0)

    def _update_ui(self):
        state = self._player.get_state()
        if not self._player.is_playing() and state == vlc.State.Ended:
            self._timer.stop()
            self.btn_play.setText("Play")
            return

        pos     = self._player.get_position()
        current = self._player.get_time()
        total   = self._player.get_length()

        # Slider fenêtré
        if not self._slider_dragging and pos >= 0:
            self.slider.setValue(int(pos * 1000))

        time_str = "00:00 / 00:00"
        if current >= 0 and total >= 0:
            time_str = f"{self._ms_to_str(current)} / {self._ms_to_str(total)}"
            self.lbl_time.setText(time_str)

        # Barre de contrôles plein écran
        if self._ctrl_bar.isVisible() and pos >= 0:
            self._ctrl_bar.update_state(
                pos, time_str,
                self._player.is_playing(),
                self._muted,
            )

    @staticmethod
    def _ms_to_str(ms: int) -> str:
        s = ms // 1000
        m, h = s // 60, s // 3600
        if h > 0:
            return f"{h}:{m % 60:02d}:{s % 60:02d}"
        return f"{m}:{s % 60:02d}"

    # ── Événements clavier / souris ──────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()

        if key in (Qt.Key.Key_Escape, Qt.Key.Key_F):
            if self._is_fullscreen:
                self._exit_fullscreen()

        elif key == Qt.Key.Key_Space:
            self._toggle_play()

        elif key == Qt.Key.Key_Left:
            self._seek(-self._SEEK_STEP_MS)

        elif key == Qt.Key.Key_Right:
            self._seek(+self._SEEK_STEP_MS)

        elif key == Qt.Key.Key_Up:
            self._change_volume(+self._VOL_STEP)

        elif key == Qt.Key.Key_Down:
            self._change_volume(-self._VOL_STEP)

        elif key == Qt.Key.Key_M:
            self._toggle_mute()

        elif key in (Qt.Key.Key_H, Qt.Key.Key_Question):
            self._toggle_shortcuts_manual()

        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._toggle_fullscreen()

    def closeEvent(self, event):
        self._player.stop()
        self._timer.stop()
        super().closeEvent(event)

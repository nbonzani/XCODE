import sys
import vlc

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSlider, QLabel, QFrame
)
from PyQt6.QtCore import Qt, QTimer


class VLCPlayerWindow(QWidget):
    """Fenetre independante pour la lecture video VLC."""

    def __init__(self):
        super().__init__()
        self._instance = vlc.Instance("--no-xlib", "--quiet")
        self._player = self._instance.media_player_new()
        self._slider_dragging = False
        self._is_fullscreen = False

        self.setWindowTitle("Lecteur video")
        self.resize(900, 600)

        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._update_ui)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Zone video
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setMinimumHeight(300)
        layout.addWidget(self.video_frame, stretch=1)

        # Label titre
        self.lbl_title = QLabel("")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet("color: #ccc; font-size: 12px; padding: 2px;")
        layout.addWidget(self.lbl_title)

        # Slider de position
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(self._slider_pressed)
        self.slider.sliderReleased.connect(self._slider_released)
        layout.addWidget(self.slider)

        # Boutons de controle
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        self.btn_play = QPushButton("Pause")
        self.btn_play.setFixedSize(70, 32)
        self.btn_play.clicked.connect(self._toggle_play)
        ctrl.addWidget(self.btn_play)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setFixedSize(70, 32)
        self.btn_stop.clicked.connect(self._stop)
        ctrl.addWidget(self.btn_stop)

        self.btn_fullscreen = QPushButton("Plein ecran")
        self.btn_fullscreen.setFixedSize(110, 32)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        ctrl.addWidget(self.btn_fullscreen)

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

        layout.addLayout(ctrl)

    def play_url(self, url: str, title: str = ""):
        """Lance la lecture d'une URL dans cette fenetre."""
        media = self._instance.media_new(url)
        self._player.set_media(media)

        # Attacher la sortie video au QFrame
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

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self.showNormal()
            self._is_fullscreen = False
        else:
            self.showFullScreen()
            self._is_fullscreen = True

    def _set_volume(self, value):
        self._player.audio_set_volume(value)

    def _slider_pressed(self):
        self._slider_dragging = True

    def _slider_released(self):
        self._slider_dragging = False
        pos = self.slider.value() / 1000.0
        self._player.set_position(pos)

    def _update_ui(self):
        if not self._player.is_playing() and self._player.get_state() == vlc.State.Ended:
            self._timer.stop()
            self.btn_play.setText("Play")
            return

        if not self._slider_dragging:
            pos = self._player.get_position()
            if pos >= 0:
                self.slider.setValue(int(pos * 1000))

        current = self._player.get_time()
        total = self._player.get_length()
        if current >= 0 and total >= 0:
            self.lbl_time.setText(
                f"{self._ms_to_str(current)} / {self._ms_to_str(total)}"
            )

    @staticmethod
    def _ms_to_str(ms: int) -> str:
        s = ms // 1000
        m = s // 60
        h = m // 60
        if h > 0:
            return f"{h}:{m % 60:02d}:{s % 60:02d}"
        return f"{m}:{s % 60:02d}"

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F):
            if self._is_fullscreen:
                self.showNormal()
                self._is_fullscreen = False
        elif event.key() == Qt.Key.Key_Space:
            self._toggle_play()
        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._toggle_fullscreen()

    def closeEvent(self, event):
        self._player.stop()
        self._timer.stop()
        super().closeEvent(event)

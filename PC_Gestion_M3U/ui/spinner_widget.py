from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QConicalGradient


class SpinnerWidget(QWidget):
    """
    Widget spinner circulaire animé style moderne.
    Un arc de cercle tournant avec dégradé de couleur.
    """

    def __init__(self, parent=None, size: int = 24, color: str = "#1565C0"):
        super().__init__(parent)
        self._size = size
        self._color = QColor(color)
        self._angle = 0

        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setVisible(False)

        self._timer = QTimer(self)
        self._timer.setInterval(16)          # ~60 fps
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._angle = 0
        self.setVisible(True)
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.setVisible(False)

    def _tick(self):
        self._angle = (self._angle - 6) % 360   # 6° par frame = 1 tour/seconde
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size   = self._size
        margin = 2
        rect   = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)

        # Arc de fond (gris clair)
        bg_pen = QPen(QColor("#E0E0E0"))
        bg_pen.setWidth(3)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # Arc animé (dégradé conique autour du centre)
        gradient = QConicalGradient(rect.center(), self._angle)
        c_solid = self._color
        c_transp = QColor(c_solid)
        c_transp.setAlpha(30)
        gradient.setColorAt(0.0, c_solid)
        gradient.setColorAt(0.75, c_transp)
        gradient.setColorAt(1.0, c_solid)

        arc_pen = QPen(gradient, 3)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        # Arc de 270° qui tourne
        painter.drawArc(rect, self._angle * 16, 270 * 16)

        painter.end()

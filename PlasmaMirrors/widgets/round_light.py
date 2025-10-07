from PyQt6 import QtCore, QtGui, QtWidgets

class RoundLight(QtWidgets.QWidget):
    clicked = QtCore.pyqtSignal()

    def __init__(self, diameter: int = 14, color_on: str = "#11c466",
                 color_off: str = "#4a4a4a", clickable: bool = False, parent=None):
        super().__init__(parent)
        self._on = False
        self._diameter = diameter
        self._color_on = color_on
        self._color_off = color_off
        self._clickable = clickable
        self.setFixedSize(diameter, diameter)
        if clickable:
            self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if self._clickable:
            self.clicked.emit()
        super().mousePressEvent(e)

    def set_on(self, value: bool) -> None:
        self._on = bool(value)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        color = QtGui.QColor(self._color_on if self._on else self._color_off)
        p.setBrush(color)
        p.setPen(QtGui.QPen(QtGui.QColor("#202020"), 1))
        p.drawEllipse(rect.adjusted(1, 1, -1, -1))
        if self._on:
            center = QtCore.QPointF(rect.center())
            glow = QtGui.QRadialGradient(center, float(rect.width())/2.0)
            glow.setColorAt(0.0, QtGui.QColor(color.red(), color.green(), color.blue(), 180))
            glow.setColorAt(1.0, QtGui.QColor(color.red(), color.green(), color.blue(), 0))
            p.setBrush(QtGui.QBrush(glow))
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.drawEllipse(rect)

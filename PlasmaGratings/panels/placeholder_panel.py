from PyQt6 import QtCore, QtWidgets
from widgets.motor_row import MotorRow
from widgets.round_light import RoundLight

class PlaceholderPanel(QtWidgets.QWidget):
    #not used now
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("placeholder")
        lab_title = QtWidgets.QLabel(title)
        lab_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        lab_msg = QtWidgets.QLabel("(Reserved — we will implement this next)")
        lab_msg.setStyleSheet("color: #aaaaaa;")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(lab_title)
        layout.addWidget(lab_msg)
        layout.addStretch(1)
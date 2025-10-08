from PyQt6 import QtCore, QtWidgets
from MotorInfo import MotorInfo
from widgets.motor_row import MotorRow

class MotorStatusPanel(QtWidgets.QWidget):
    def __init__(self, motors: list[MotorInfo]):
        super().__init__()
        title = QtWidgets.QLabel("Stages")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")

        self.rows: list[MotorRow] = [MotorRow(m, i) for i, m in enumerate(motors, start=1)]

        container = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        for r in self.rows:
            v.addWidget(r)
        v.addStretch(1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        topbar = QtWidgets.QHBoxLayout()
        topbar.addWidget(title)
        topbar.addStretch(1)

        layout = QtWidgets.QVBoxLayout(self)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMaximumWidth(760)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(topbar)
        layout.addWidget(scroll)

    # called by MainWindow on readbacks
    def update_address(self, steps: float, pos: float, stage_no: int):
        try:
            row = self.rows[stage_no - 1]
        except Exception:
            return
        row.info.steps = int(steps)
        row.info.eng_value = float(pos)
        row.lbl_steps.setText(row._fmt_steps(row.info.steps))
        row.lbl_units.setText(row._fmt_units(row.info.eng_value, row.info.unit, rich=True))
        row.bar.setValue(row._progress_from_value(row.info.eng_value))

    def update_speed(self, speed: float, stage_no: int):
        try:
            row = self.rows[stage_no - 1]
        except Exception:
            return
        row.info.speed = float(speed)
        row.lbl_speed_units.setText(row._fmt_units(row.info.speed, row.info.speed_unit, rich=True))
    
    def update_bounds(self, lower: float, upper: float, stage_no: int):
        try:
            row = self.rows[stage_no - 1]
        except Exception:
            return
        row.info.lbound = float(lower)
        row.info.ubound = float(upper)
        row.bar.setValue(row._progress_from_value(row.info.eng_value))

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

        # btn_sim_all = QtWidgets.QPushButton("Simulate All")
        # btn_sim_all.setCheckable(True)
        # btn_sim_all.toggled.connect(self._toggle_all)

        topbar = QtWidgets.QHBoxLayout()
        topbar.addWidget(title)
        topbar.addStretch(1)
        # topbar.addWidget(btn_sim_all)

        layout = QtWidgets.QVBoxLayout(self)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMaximumWidth(760)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(topbar)
        layout.addWidget(scroll)

        # self.timer = QtCore.QTimer(self)
        # self.timer.setInterval(50)
        # self.timer.timeout.connect(self._tick)
        # self.timer.start()

    # def _toggle_all(self, on: bool):
    #     for r in self.rows:
    #         r.set_moving(on)

    # def _tick(self):
    #     for r in self.rows:
    #         r.tick()

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

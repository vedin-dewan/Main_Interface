from PyQt6 import QtCore, QtWidgets
from .round_light import RoundLight
from MotorInfo import MotorInfo

class MotorRow(QtWidgets.QWidget):
    toggled_motion = QtCore.pyqtSignal(bool)

    def __init__(self, info: MotorInfo, index: int, parent=None):
        super().__init__(parent)
        self.info = info
        self.index = index
        self._moving = False
        self._step_per_tick = 0

        self.light_green = RoundLight(diameter=14, color_on="#22cc66", color_off="#2b2b2b", clickable=False)
        self.light_red   = RoundLight(diameter=14, color_on="#d9534f", color_off="#7a2f2e", clickable=True)
        self.light_red.set_on(True)

        self.lbl_index = QtWidgets.QLabel(f"{index}")
        self.lbl_index.setMinimumWidth(20)
        self.lbl_index.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

        self.lbl_short = QtWidgets.QLabel(self.info.short)
        self.lbl_short.setMinimumWidth(55)
        self.lbl_short.setStyleSheet("font-weight: 600;")

        self.lbl_long = QtWidgets.QLabel(self.info.long)
        self.lbl_long.setMinimumWidth(100)
        self.lbl_long.setStyleSheet("font-weight: 700;")

        self.lbl_units = QtWidgets.QLabel(self._fmt_units(self.info.eng_value, self.info.unit, rich=True))
        self.lbl_units.setTextFormat(QtCore.Qt.TextFormat.RichText)
        # fixed width so long numeric values don't push the progress bar column
        self.lbl_units.setFixedWidth(90)

        self.lbl_speed_units = QtWidgets.QLabel(self._fmt_units(self.info.speed, self.info.speed_unit, rich=True))
        self.lbl_speed_units.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.lbl_speed_units.setFixedWidth(90)

        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(self._progress_from_value(self.info.eng_value))
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(16)
        self.bar.setStyleSheet(
            "QProgressBar { background: #2a2a2a; border-radius: 8px; }"
            "QProgressBar::chunk { background-color: #1db954; border-radius: 8px; }"
        )

        self.lbl_steps = QtWidgets.QLabel(self._fmt_steps(self.info.steps))
        # keep steps column a fixed width to align progress bars
        self.lbl_steps.setFixedWidth(100)

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(8)
        lay.addWidget(self.light_green)
        lay.addWidget(self.light_red)
        lay.addWidget(self.lbl_index)
        lay.addWidget(self.lbl_short)
        lay.addWidget(self.lbl_long)
        lay.addSpacing(2)
        lay.addWidget(self.lbl_units)
        lay.addSpacing(2)
        lay.addWidget(self.bar, stretch=1)
        lay.addSpacing(2)
        lay.addWidget(self.lbl_speed_units)
        lay.addSpacing(2)
        lay.addWidget(self.lbl_steps)
        lay.addSpacing(6)

        self.installEventFilter(self)

    # --- utilities ---
    def _fmt_steps(self, steps: int) -> str:
        return f"{steps:,} steps".replace(",", " ")

    def _fmt_units(self, v: float, unit: str, rich: bool = False) -> str:
        # Display values with three decimal places for all units
        try:
            val = f"{float(v):.3f}"
        except Exception:
            val = str(v)
        s = f"<b>{val}</b> {unit}" if rich else f"{val} {unit}"
        return s

    def _progress_from_value(self, v: float) -> int:
        lo, hi = float(self.info.lbound), float(self.info.ubound)
        if hi <= lo:
            return 0
        v = max(lo, min(hi, v))
        return int(round((v - lo) / (hi - lo) * 100))


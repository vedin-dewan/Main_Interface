from PyQt6 import QtCore, QtWidgets
from widgets.motor_row import MotorRow
from widgets.round_light import RoundLight

# ---------------------------
# FlipControl panel (GUI only)
# ---------------------------

class FlipRow(QtWidgets.QWidget):
    """One flip row: two lights (On/Open), a Toggle button, and a Name edit."""
    def __init__(self, name: str = "Pump A", parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(8)

        # Two indicator lights (left): red + green (no behavior)
        self.light_on  = RoundLight(diameter=16, color_on="#b23b3b", color_off="#5a2a2a")
        self.light_open = RoundLight(diameter=16, color_on="#2e8b57", color_off="#2b2b2b")
        # Default visual state (both off except green “open”? tweak as desired)
        self.light_on.set_on(False)
        self.light_open.set_on(True)

        # Toggle button (no logic yet)
        self.btn_toggle = QtWidgets.QPushButton("Toggle")
        self.btn_toggle.setCheckable(False)
        self.btn_toggle.setFixedWidth(120)
        self.btn_toggle.setStyleSheet(
            "QPushButton { background:#d9d9d9; border:1px solid #a0a0a0; "
            "padding:4px 10px; border-radius:4px; color:#222; }"
            "QPushButton:pressed { background:#cfcfcf; }"
        )

        # Name entry (bold text like screenshot)
        self.edit_name = QtWidgets.QLineEdit(name)
        f = self.edit_name.font(); f.setBold(True); self.edit_name.setFont(f)
        self.edit_name.setMinimumWidth(180)

        # Compose row
        lay.addWidget(self.light_on)
        lay.addWidget(self.light_open)
        lay.addWidget(self.btn_toggle)
        lay.addWidget(self.edit_name, 1)


class FlipControlPanel(QtWidgets.QGroupBox):
    """Panel containing header labels and several FlipRows. GUI only, no wiring."""
    def __init__(self, parent=None):
        super().__init__("Flip Control", parent)

        # Header row
        hdr = QtWidgets.QHBoxLayout()
        hdr.setContentsMargins(6, 4, 6, 2)
        hdr.setSpacing(8)

        def _lab(text, minw=None):
            l = QtWidgets.QLabel(text)
            l.setStyleSheet("color:#2a2a2a; font-weight:600;")
            if minw: l.setMinimumWidth(minw)
            return l

        hdr.addWidget(_lab("On"))
        hdr.addWidget(_lab("Open"))
        hdr.addSpacing(16)
        hdr.addWidget(_lab("Switch", 120))
        hdr.addSpacing(16)
        hdr.addWidget(_lab("Name"))
        hdr.addStretch(1)

        # Rows (example four items)
        rows = QtWidgets.QVBoxLayout()
        rows.setContentsMargins(4, 0, 4, 6)
        rows.setSpacing(8)
        self.row1 = FlipRow("Pump A")
        self.row2 = FlipRow("Pump B")
        self.row3 = FlipRow("Probe")
        self.row4 = FlipRow("Long Pulse")
        for r in (self.row1, self.row2, self.row3, self.row4):
            rows.addWidget(r)

        # Panel layout
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        outer.addLayout(hdr)
        outer.addLayout(rows)

        # Optional compact style to match your UI
        self.setStyleSheet(
            "QGroupBox { font-weight:700; }"
            "QLineEdit { border:1px solid #a0a0a0; background:#f5f5f5; padding:2px 6px; }"
        )

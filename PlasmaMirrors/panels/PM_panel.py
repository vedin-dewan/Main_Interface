from PyQt6 import QtCore, QtWidgets
from widgets.motor_row import MotorRow
from widgets.round_light import RoundLight

class ToggleBypassButton(QtWidgets.QPushButton):
    """Right-bottom BYPASS/ENGAGE toggle button."""
    def __init__(self, parent=None):
        super().__init__("BYPASS", parent)
        self.setCheckable(True)
        self._apply_style(False)
        self.toggled.connect(self._apply_style)
        self.setFixedHeight(26)

    def _apply_style(self, engaged: bool):
        if engaged:
            # ENGAGE = red
            self.setText("ENGAGE")
            self.setStyleSheet(
                "background:#7a2f2e; color:#fff; border:1px solid #a24946; font-weight:700; border-radius:6px;"
            )
        else:
            # BYPASS = green
            self.setText("BYPASS")
            self.setStyleSheet(
                "background:#2f7a4a; color:#fff; border:1px solid #4ea36b; font-weight:700; border-radius:6px;"
            )

class PMStageRow(QtWidgets.QWidget):
    """One row: RX / Y / Z / SD with Min, Max, Zero Pos, MO Pos, Current, Direction.
       Direction dropdown is optional (for RX and Y only in your layout)."""
    def __init__(self, label: str, parent=None, direction_enabled: bool = True):
        super().__init__(parent)
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0,0,0,0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        # Left stage label
        lab = QtWidgets.QLabel(label)
        lab.setMinimumWidth(18)
        grid.addWidget(lab, 0, 0)
        # Stage number (small int)
        self.stage_num = QtWidgets.QSpinBox(); self.stage_num.setRange(0, 999); self.stage_num.setFixedWidth(40)
        grid.addWidget(self.stage_num, 0, 1)
        # Min/Max
        self.min = QtWidgets.QDoubleSpinBox(); self.min.setDecimals(3); self.min.setRange(-9999, 9999); self.min.setFixedWidth(70)
        self.max = QtWidgets.QDoubleSpinBox(); self.max.setDecimals(3); self.max.setRange(-9999, 9999); self.max.setFixedWidth(70)
        grid.addWidget(self.min, 0, 2); grid.addWidget(self.max, 0, 3)
        # Zero Pos / MO Pos / Current
        self.zero = QtWidgets.QDoubleSpinBox(); self.zero.setDecimals(3); self.zero.setRange(-9999, 9999); self.zero.setFixedWidth(70)
        self.mo   = QtWidgets.QDoubleSpinBox(); self.mo.setDecimals(3);   self.mo.setRange(-9999, 9999);   self.mo.setFixedWidth(70)
        self.cur  = QtWidgets.QDoubleSpinBox(); self.cur.setDecimals(3);  self.cur.setRange(-9999, 9999);  self.cur.setFixedWidth(70)
        grid.addWidget(self.zero, 0, 4); grid.addWidget(self.mo, 0, 5); grid.addWidget(self.cur, 0, 6)
        # Direction (only if enabled)
        if direction_enabled:
            self.dir = QtWidgets.QComboBox(); self.dir.addItems(["Pos", "Neg"]); self.dir.setFixedWidth(70)
            grid.addWidget(self.dir, 0, 7)
        else:
            self.dir = None
            spacer = QtWidgets.QLabel("")
            spacer.setFixedWidth(70)
            grid.addWidget(spacer, 0, 7)

class PMMirrorGroup(QtWidgets.QGroupBox):
    def __init__(self, title: str, parent=None):
        super().__init__("", parent)
        self.setStyleSheet("QGroupBox{font-weight:700;}")

        # --- Top header: labels row + widgets row (to match screenshot) ---
        top = QtWidgets.QGridLayout()
        top.setHorizontalSpacing(8)
        top.setVerticalSpacing(2)
        # Row 0: header labels
        headers = ["On", "Name", "Act.", "Auto", "Dist. (mm)", "Target Type"]
        for col, text in enumerate(headers):
            lab = QtWidgets.QLabel(text)
            lab.setStyleSheet("color:#cfcfcf;")
            top.addWidget(lab, 0, col)
        # Row 1: actual controls aligned under labels
        self.on_light = RoundLight(14, "#22cc66", "#2b2b2b"); self.on_light.set_on(True)
        top.addWidget(self.on_light, 1, 0)
        self.name = QtWidgets.QLineEdit(title); self.name.setFixedWidth(180)
        top.addWidget(self.name, 1, 1)
        self.act_light = RoundLight(14, "#22cc66", "#2b2b2b")
        top.addWidget(self.act_light, 1, 2)
        self.auto = QtWidgets.QCheckBox(); self.auto.setChecked(True)
        top.addWidget(self.auto, 1, 3)
        self.dist = QtWidgets.QDoubleSpinBox(); self.dist.setDecimals(3); self.dist.setRange(0, 9999); self.dist.setValue(0.5); self.dist.setFixedWidth(80)
        top.addWidget(self.dist, 1, 4)
        self.target_type = QtWidgets.QComboBox(); self.target_type.addItems(["Circular", "Rectangular"]); self.target_type.setFixedWidth(110)
        top.addWidget(self.target_type, 1, 5)

        # --- Stage table header ---
        hdr = QtWidgets.QGridLayout()
        hdr.setHorizontalSpacing(6)
        header_labels = ["Stage", "Min", "Max", "Zero Pos", "MO Pos", "Current", "Direction"]
        hdr.addWidget(QtWidgets.QLabel(""), 0, 0)  # empty for RX/Y/Z/SD label col
        for i, t in enumerate(header_labels, start=1):
            lab = QtWidgets.QLabel(t); lab.setStyleSheet("color:#cfcfcf;")
            hdr.addWidget(lab, 0, i)

        # --- Four rows (Direction only for RX & Y) ---
        self.row_rx = PMStageRow("RX", direction_enabled=True)
        self.row_y  = PMStageRow("Y",  direction_enabled=True)
        self.row_z  = PMStageRow("Z",  direction_enabled=False)
        self.row_sd = PMStageRow("SD", direction_enabled=False)

        # --- Bottom info strip: plain text (no buttons) + BYPASS/ENGAGE toggle ---
        bottom = QtWidgets.QHBoxLayout()
        lab_off = QtWidgets.QLabel("SD Off")
        lab_on  = QtWidgets.QLabel("SD On")
        lab_off.setStyleSheet("color:#cfcfcf;")
        lab_on.setStyleSheet("color:#cfcfcf;")
        bottom.addWidget(lab_off)
        bottom.addSpacing(16)
        bottom.addWidget(lab_on)
        bottom.addStretch(1)
        self.bypass = ToggleBypassButton()
        bottom.addWidget(self.bypass)

        # Compose panel
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(8,8,8,8)
        v.setSpacing(2)
        v.addLayout(top)
        v.addLayout(hdr)
        v.addWidget(self.row_rx)
        v.addWidget(self.row_y)
        v.addWidget(self.row_z)
        v.addWidget(self.row_sd)
        v.addLayout(bottom)

class PMPanel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.pm1 = PMMirrorGroup("Plasma Mirror 1")
        self.pm2 = PMMirrorGroup("Plasma Mirror 2")
        self.pm3 = PMMirrorGroup("Plasma Mirror 3")

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(8,8,8,8)
        v.setSpacing(2)
        v.addWidget(self.pm1)
        v.addWidget(self.pm2)
        v.addWidget(self.pm3)
        v.addStretch(1)

        # Match app style
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(520)
        self.setMaximumWidth(700)
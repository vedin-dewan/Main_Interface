# panels/fire_controls_panel.py
from __future__ import annotations
from PyQt6 import QtCore, QtWidgets

# panels/fire_controls_panel.py
from PyQt6 import QtCore, QtWidgets

class FireControlsPanel(QtWidgets.QWidget):
    # GUI -> backend
    request_mode  = QtCore.pyqtSignal(str)   # "continuous" | "single" | "burst"
    request_shots = QtCore.pyqtSignal(int)   # applies to both Single and Burst
    request_fire  = QtCore.pyqtSignal()      # start action

    def __init__(self, parent=None):
        super().__init__(parent)
        grp = QtWidgets.QGroupBox("Trigger Mode")
        grp.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                          QtWidgets.QSizePolicy.Policy.Fixed)
        g = QtWidgets.QGridLayout(grp)
        g.setContentsMargins(30, 30, 30, 30)
        g.setHorizontalSpacing(20)
        g.setVerticalSpacing(16)

        # Radios in a clean vertical column
        self.rb_cont   = QtWidgets.QRadioButton("Continuous")
        self.rb_single = QtWidgets.QRadioButton("Single Shot")
        self.rb_burst  = QtWidgets.QRadioButton("Burst")
        self.rb_cont.setChecked(True)

        col_modes = QtWidgets.QVBoxLayout()
        col_modes.addWidget(self.rb_cont)
        col_modes.addWidget(self.rb_single)
        col_modes.addWidget(self.rb_burst)
        col_modes.addStretch(1)
        g.addLayout(col_modes, 0, 0, 3, 1)

        # Shots row (shared for Single & Burst)
        lab_shots = QtWidgets.QLabel("# Shots:")
        self.spin_shots = QtWidgets.QSpinBox()
        self.spin_shots.setRange(1, 9999)
        self.spin_shots.setValue(10)
        self.spin_shots.setFixedWidth(100)
        self.spin_shots.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        hint = QtWidgets.QLabel("(press Fire to start)")
        hint.setStyleSheet("color:#888;")

        shots_row = QtWidgets.QHBoxLayout()
        shots_row.addWidget(lab_shots)
        shots_row.addWidget(self.spin_shots)
        shots_row.addSpacing(12)
        shots_row.addWidget(hint)
        shots_row.addStretch(1)
        g.addLayout(shots_row, 0, 1, 1, 2)

        # Big Fire button spanning the width
        self.btn_fire = QtWidgets.QPushButton("Fire")
        self.btn_fire.setMinimumHeight(44)
        self.btn_fire.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                    QtWidgets.QSizePolicy.Policy.Fixed)
        self.btn_fire.setStyleSheet("background:#D30000; color:white; font-weight:700;")
        g.addWidget(self.btn_fire, 1, 1, 1, 2)

        # Status line
        self.lab_status = QtWidgets.QLabel("Ready")
        g.addWidget(self.lab_status, 2, 0, 1, 3)

        # column stretch so the button gets space
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 2)
        g.setColumnStretch(2, 3)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(grp)

        # wire signals
        self.rb_cont.toggled.connect(lambda on: on and self._emit_mode("continuous"))
        self.rb_single.toggled.connect(lambda on: on and self._emit_mode("single"))
        self.rb_burst.toggled.connect(lambda on: on and self._emit_mode("burst"))
        self.spin_shots.editingFinished.connect(self._emit_shots)
        self.btn_fire.clicked.connect(self.request_fire)

    # ----- slots for backend to update UI -----
    @QtCore.pyqtSlot(str)
    def set_status(self, text: str):
        self.lab_status.setText(text)

    # ----- internals -----
    def _emit_mode(self, m: str):
        self.request_mode.emit(m)

    def _emit_shots(self):
        self.request_shots.emit(int(self.spin_shots.value()))

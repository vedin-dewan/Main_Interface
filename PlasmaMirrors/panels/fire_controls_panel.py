# panels/fire_controls_panel.py
from __future__ import annotations
from PyQt6 import QtCore, QtWidgets

class FireControlsPanel(QtWidgets.QWidget):
    """
    Panel for fire control.
    """
    request_mode = QtCore.pyqtSignal(str)   # "continuous" | "single" | "burst"
    request_burst = QtCore.pyqtSignal(int)  # N shots
    request_fire = QtCore.pyqtSignal()      # press Fire

    def __init__(self, parent=None):
        super().__init__(parent)

        grp = QtWidgets.QGroupBox("Fire Controls")
        layout = QtWidgets.QGridLayout(grp)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(6)

        # Mode radios
        self.rb_cont = QtWidgets.QRadioButton("Continuous")
        self.rb_single = QtWidgets.QRadioButton("Single")
        self.rb_burst = QtWidgets.QRadioButton("Burst")
        self.rb_single.setChecked(True)

        self.rb_cont.toggled.connect(lambda on: on and self._emit_mode("continuous"))
        self.rb_single.toggled.connect(lambda on: on and self._emit_mode("single"))
        self.rb_burst.toggled.connect(lambda on: on and self._emit_mode("burst"))

        # Burst spin
        self.spin_burst = QtWidgets.QSpinBox()
        self.spin_burst.setRange(1, 9999)
        self.spin_burst.setValue(10)
        self.spin_burst.editingFinished.connect(self._emit_burst)
        lab_burst = QtWidgets.QLabel("# Shots")

        # Fire button
        self.btn_fire = QtWidgets.QPushButton("Fire")
        self.btn_fire.setStyleSheet("background:#D30000; color:white; font-weight:700;")
        self.btn_fire.clicked.connect(self.request_fire.emit)

        # Status line + progress
        self.lab_status = QtWidgets.QLabel("Ready")
        self.prog = QtWidgets.QProgressBar()
        self.prog.setRange(0, 10)
        self.prog.setValue(0)
        self.prog.setTextVisible(True)

        # Layout
        layout.addWidget(self.rb_cont, 0, 0)
        layout.addWidget(self.rb_single, 0, 1)
        layout.addWidget(self.rb_burst, 0, 2)

        layout.addWidget(lab_burst, 1, 0)
        layout.addWidget(self.spin_burst, 1, 1)
        layout.addWidget(self.btn_fire, 1, 2)

        layout.addWidget(self.lab_status, 2, 0, 1, 3)
        layout.addWidget(self.prog, 3, 0, 1, 3)

        outer = QtWidgets.QVBoxLayout(self)
        outer.addWidget(grp)
        outer.addStretch(1)

    # ---- public helpers for MainWindow/IO to update UI ----
    @QtCore.pyqtSlot(str)
    def set_status(self, text: str):
        self.lab_status.setText(text)

    @QtCore.pyqtSlot(int, int)
    def set_progress(self, cur: int, total: int):
        total = max(1, int(total))
        cur = max(0, min(int(cur), total))
        self.prog.setRange(0, total)
        self.prog.setValue(cur)
        self.prog.setFormat(f"{cur}/{total}")

    # ---- internals ----
    def _emit_mode(self, mode: str):
        self.request_mode.emit(mode)

    def _emit_burst(self):
        self.request_burst.emit(int(self.spin_burst.value()))

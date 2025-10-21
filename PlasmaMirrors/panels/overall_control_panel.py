from __future__ import annotations
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import QFileDialog, QStyle
from widgets.round_light import RoundLight
import os, json


class SavingPanel(QtWidgets.QGroupBox):
    # signals for the two alignment quick-toggle groups: (stage_addr:int, target:float, on:bool)
    alignment_pg_switch_requested = QtCore.pyqtSignal(int, float, bool)
    alignment_hene_switch_requested = QtCore.pyqtSignal(int, float, bool)

    def __init__(self, parent=None):
        super().__init__("Saving", parent)

        layout = QtWidgets.QGridLayout(self)
        self.setFixedHeight(220)

        # --- 1. Output Directory ---
        self.dir_label = QtWidgets.QLabel("Output Directory")
        self.dir_edit = QtWidgets.QLineEdit()
        self.dir_button = QtWidgets.QToolButton()
        self.dir_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.dir_button.clicked.connect(self._choose_folder)

        layout.addWidget(self.dir_label, 0, 0)
        layout.addWidget(self.dir_edit, 0, 1)
        layout.addWidget(self.dir_button, 0, 2)

        # --- 2. Experiment Name ---
        self.exp_label = QtWidgets.QLabel("Experiment Name")
        self.exp_edit = QtWidgets.QLineEdit()
        layout.addWidget(self.exp_label, 1, 0)
        layout.addWidget(self.exp_edit, 1, 1, 1, 2)

        # --- 3. Burst Save Folder (Relative) ---
        self.burst_label = QtWidgets.QLabel("Burst Save Folder (Relative)")
        self.burst_edit = QtWidgets.QLineEdit()
        layout.addWidget(self.burst_label, 2, 0)
        layout.addWidget(self.burst_edit, 2, 1, 1, 2)

        # --- 4. Alignment-controlled stage quick toggles ---
        # Two groups side-by-side: PG and HeNe. Each group: [light] [stage spin] [off pos] [on pos] [ON] [OFF]

        # PG group widgets
        self.alignment_pg_label = QtWidgets.QLabel("PG Alignment")
        self.alignment_pg_label.setStyleSheet("font-weight:600")
        self.alignment_pg_light = RoundLight(diameter=16, clickable=False)
        self.alignment_pg_stage_spin = QtWidgets.QSpinBox()
        # Stage index only needs up to two digits
        self.alignment_pg_stage_spin.setRange(0, 99)
        self.alignment_pg_stage_spin.setFixedWidth(44)
        self.alignment_pg_stage_spin.setToolTip('Stage number (address) for PG alignment quick toggle')
        self.alignment_pg_off_spin = QtWidgets.QDoubleSpinBox()
        # Positions: three digits before decimal, three after (e.g. 999.999)
        self.alignment_pg_off_spin.setRange(-999.999, 999.999)
        self.alignment_pg_off_spin.setDecimals(3)
        self.alignment_pg_off_spin.setFixedWidth(84)
        self.alignment_pg_off_spin.setToolTip('Absolute position to move to when PG OFF pressed')

        self.alignment_pg_on_spin = QtWidgets.QDoubleSpinBox()
        self.alignment_pg_on_spin.setRange(-999.999, 999.999)
        self.alignment_pg_on_spin.setDecimals(3)
        self.alignment_pg_on_spin.setFixedWidth(84)
        self.alignment_pg_on_spin.setToolTip('Absolute position to move to when PG ON pressed')

        self.alignment_pg_btn_on = QtWidgets.QPushButton('ON')
        self.alignment_pg_btn_on.setFixedWidth(50)
        self.alignment_pg_btn_off = QtWidgets.QPushButton('OFF')
        self.alignment_pg_btn_off.setFixedWidth(50)

        # HeNe group widgets
        self.alignment_hene_label = QtWidgets.QLabel("HeNe Alignment")
        self.alignment_hene_label.setStyleSheet("font-weight:600")
        self.alignment_hene_light = RoundLight(diameter=16, clickable=False)
        self.alignment_hene_stage_spin = QtWidgets.QSpinBox()
        # Stage index only needs up to two digits
        self.alignment_hene_stage_spin.setRange(0, 99)
        self.alignment_hene_stage_spin.setFixedWidth(44)
        self.alignment_hene_stage_spin.setToolTip('Stage number (address) for HeNe alignment quick toggle')
        self.alignment_hene_off_spin = QtWidgets.QDoubleSpinBox()
        self.alignment_hene_off_spin.setRange(-999.999, 999.999)
        self.alignment_hene_off_spin.setDecimals(3)
        self.alignment_hene_off_spin.setFixedWidth(84)
        self.alignment_hene_off_spin.setToolTip('Absolute position to move to when HeNe OFF pressed')

        self.alignment_hene_on_spin = QtWidgets.QDoubleSpinBox()
        self.alignment_hene_on_spin.setRange(-999.999, 999.999)
        self.alignment_hene_on_spin.setDecimals(3)
        self.alignment_hene_on_spin.setFixedWidth(84)
        self.alignment_hene_on_spin.setToolTip('Absolute position to move to when HeNe ON pressed')

        self.alignment_hene_btn_on = QtWidgets.QPushButton('ON')
        self.alignment_hene_btn_on.setFixedWidth(50)
        self.alignment_hene_btn_off = QtWidgets.QPushButton('OFF')
        self.alignment_hene_btn_off.setFixedWidth(50)

        # layout the PG row (left column)
        pg_row = QtWidgets.QHBoxLayout()
        pg_row.setContentsMargins(0, 0, 0, 0)
        pg_row.addWidget(self.alignment_pg_light)
        pg_row.addWidget(self.alignment_pg_stage_spin)
        pg_row.addWidget(self.alignment_pg_off_spin)
        pg_row.addWidget(self.alignment_pg_on_spin)
        pg_row.addWidget(self.alignment_pg_btn_on)
        pg_row.addSpacing(8)
        pg_row.addWidget(self.alignment_pg_btn_off)
        pg_row.addStretch(1)

        # layout the HeNe row (right column)
        hene_row = QtWidgets.QHBoxLayout()
        hene_row.setContentsMargins(0, 0, 0, 0)
        hene_row.addWidget(self.alignment_hene_light)
        hene_row.addWidget(self.alignment_hene_stage_spin)
        hene_row.addWidget(self.alignment_hene_off_spin)
        hene_row.addWidget(self.alignment_hene_on_spin)
        hene_row.addWidget(self.alignment_hene_btn_on)
        hene_row.addSpacing(8)
        hene_row.addWidget(self.alignment_hene_btn_off)
        hene_row.addStretch(1)

        # place headings and rows in the grid: PG group first, HeNe group below it
        # increase spacing above these rows so they don't feel cramped under the Burst Save field
        layout.setRowMinimumHeight(3, 8)
        layout.addWidget(self.alignment_pg_label, 3, 0)
        layout.addLayout(pg_row, 4, 0, 1, 2)

        layout.addWidget(self.alignment_hene_label, 5, 0)
        layout.addLayout(hene_row, 6, 0, 1, 2)

        # Configure button (common) — opens dialog to edit all values and save to JSON
        self.alignment_config_btn = QtWidgets.QPushButton('Configure')
        self.alignment_config_btn.setFixedWidth(110)
        layout.addWidget(self.alignment_config_btn, 7, 0, 1, 2, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        # Make the display spinboxes read-only and remove arrow buttons so they're only editable via Configure
        try:
            for sb in (self.alignment_pg_stage_spin, self.alignment_pg_off_spin, self.alignment_pg_on_spin,
                       self.alignment_hene_stage_spin, self.alignment_hene_off_spin, self.alignment_hene_on_spin):
                try:
                    sb.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
                except Exception:
                    pass
                try:
                    sb.setReadOnly(True)
                except Exception:
                    pass
        except Exception:
            pass

        # Wire configure button and group ON/OFF buttons
        try:
            self.alignment_config_btn.clicked.connect(self._open_config_dialog)
        except Exception:
            pass
        try:
            self.alignment_pg_btn_on.clicked.connect(lambda: self._emit_alignment_pg_switch(True))
            self.alignment_pg_btn_off.clicked.connect(lambda: self._emit_alignment_pg_switch(False))
            self.alignment_hene_btn_on.clicked.connect(lambda: self._emit_alignment_hene_switch(True))
            self.alignment_hene_btn_off.clicked.connect(lambda: self._emit_alignment_hene_switch(False))
        except Exception:
            pass

        layout.setVerticalSpacing(2)     # reduce space between rows (default ~6–10)
        # Increase top margin so the groupbox title ('Saving') doesn't overlap the first row
        layout.setContentsMargins(8, 18, 8, 8)

        self.setLayout(layout)

        # Load initial values from JSON (if present)
        try:
            self._load_alignment_values()
        except Exception:
            pass

    def _emit_alignment_pg_switch(self, on: bool):
        try:
            addr = int(self.alignment_pg_stage_spin.value())
            target = float(self.alignment_pg_on_spin.value() if on else self.alignment_pg_off_spin.value())
            try:
                getattr(self, 'alignment_pg_switch_requested', None) and self.alignment_pg_switch_requested.emit(addr, target, on)
            except Exception:
                pass
        except Exception:
            pass

    def _emit_alignment_hene_switch(self, on: bool):
        try:
            addr = int(self.alignment_hene_stage_spin.value())
            target = float(self.alignment_hene_on_spin.value() if on else self.alignment_hene_off_spin.value())
            try:
                getattr(self, 'alignment_hene_switch_requested', None) and self.alignment_hene_switch_requested.emit(addr, target, on)
            except Exception:
                pass
        except Exception:
            pass

    # Persistence: load/save JSON for both groups
    def _get_vals_path(self) -> str:
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            params_dir = os.path.join(base_dir, 'parameters')
            if not os.path.isdir(params_dir):
                try:
                    os.makedirs(params_dir, exist_ok=True)
                except Exception:
                    pass
            return os.path.join(params_dir, 'HeNe_PG_vals.json')
        except Exception:
            return os.path.join(os.getcwd(), 'HeNe_PG_vals.json')

    def _load_alignment_values(self):
        path = self._get_vals_path()
        try:
            if os.path.isfile(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                pg = data.get('pg', {}) if isinstance(data, dict) else {}
                hene = data.get('hene', {}) if isinstance(data, dict) else {}
                try:
                    self.alignment_pg_stage_spin.setValue(int(pg.get('stage', 0)))
                except Exception:
                    pass
                try:
                    self.alignment_pg_off_spin.setValue(float(pg.get('off', 0.0)))
                except Exception:
                    pass
                try:
                    self.alignment_pg_on_spin.setValue(float(pg.get('on', 0.0)))
                except Exception:
                    pass
                try:
                    self.alignment_hene_stage_spin.setValue(int(hene.get('stage', 0)))
                except Exception:
                    pass
                try:
                    self.alignment_hene_off_spin.setValue(float(hene.get('off', 0.0)))
                except Exception:
                    pass
                try:
                    self.alignment_hene_on_spin.setValue(float(hene.get('on', 0.0)))
                except Exception:
                    pass
                return
        except Exception:
            pass
        # Defaults if load failed
        try:
            self.alignment_pg_stage_spin.setValue(0)
            self.alignment_pg_off_spin.setValue(0.0)
            self.alignment_pg_on_spin.setValue(0.0)
            self.alignment_hene_stage_spin.setValue(0)
            self.alignment_hene_off_spin.setValue(0.0)
            self.alignment_hene_on_spin.setValue(0.0)
        except Exception:
            pass

    def _open_config_dialog(self):
        # Build a modal dialog to edit both PG and HeNe values
        d = QtWidgets.QDialog(self)
        d.setWindowTitle('Configure Alignment Values')
        lay = QtWidgets.QGridLayout(d)

        # PG editors
        lay.addWidget(QtWidgets.QLabel('PG Alignment'), 0, 0)
        pg_stage = QtWidgets.QSpinBox(); pg_stage.setRange(0,999)
        pg_off = QtWidgets.QDoubleSpinBox(); pg_off.setRange(-1e6,1e6); pg_off.setDecimals(3)
        pg_on = QtWidgets.QDoubleSpinBox(); pg_on.setRange(-1e6,1e6); pg_on.setDecimals(3)
        pg_stage.setValue(int(self.alignment_pg_stage_spin.value()))
        pg_off.setValue(float(self.alignment_pg_off_spin.value()))
        pg_on.setValue(float(self.alignment_pg_on_spin.value()))
        lay.addWidget(QtWidgets.QLabel('Stage'), 1, 0); lay.addWidget(pg_stage, 1, 1)
        lay.addWidget(QtWidgets.QLabel('OFF pos'), 2, 0); lay.addWidget(pg_off, 2, 1)
        lay.addWidget(QtWidgets.QLabel('ON pos'), 3, 0); lay.addWidget(pg_on, 3, 1)

        # HeNe editors
        lay.addWidget(QtWidgets.QLabel('HeNe Alignement'), 0, 2)
        hene_stage = QtWidgets.QSpinBox(); hene_stage.setRange(0,999)
        hene_off = QtWidgets.QDoubleSpinBox(); hene_off.setRange(-1e6,1e6); hene_off.setDecimals(3)
        hene_on = QtWidgets.QDoubleSpinBox(); hene_on.setRange(-1e6,1e6); hene_on.setDecimals(3)
        hene_stage.setValue(int(self.alignment_hene_stage_spin.value()))
        hene_off.setValue(float(self.alignment_hene_off_spin.value()))
        hene_on.setValue(float(self.alignment_hene_on_spin.value()))
        lay.addWidget(QtWidgets.QLabel('Stage'), 1, 2); lay.addWidget(hene_stage, 1, 3)
        lay.addWidget(QtWidgets.QLabel('OFF pos'), 2, 2); lay.addWidget(hene_off, 2, 3)
        lay.addWidget(QtWidgets.QLabel('ON pos'), 3, 2); lay.addWidget(hene_on, 3, 3)

        # Save / Cancel buttons
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        lay.addWidget(btn_box, 4, 0, 1, 4)
        btn_box.accepted.connect(d.accept)
        btn_box.rejected.connect(d.reject)

        if d.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            # write values to JSON and update display spinboxes
            data = {
                'pg': {'stage': int(pg_stage.value()), 'off': float(pg_off.value()), 'on': float(pg_on.value())},
                'hene': {'stage': int(hene_stage.value()), 'off': float(hene_off.value()), 'on': float(hene_on.value())}
            }
            try:
                path = self._get_vals_path()
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
            try:
                self.alignment_pg_stage_spin.setValue(int(pg_stage.value()))
                self.alignment_pg_off_spin.setValue(float(pg_off.value()))
                self.alignment_pg_on_spin.setValue(float(pg_on.value()))
                self.alignment_hene_stage_spin.setValue(int(hene_stage.value()))
                self.alignment_hene_off_spin.setValue(float(hene_off.value()))
                self.alignment_hene_on_spin.setValue(float(hene_on.value()))
            except Exception:
                pass

    def set_alignment_pg_light_state(self, on: bool):
        try:
            self.alignment_pg_light.set_on(bool(on))
        except Exception:
            pass

    def set_alignment_hene_light_state(self, on: bool):
        try:
            self.alignment_hene_light.set_on(bool(on))
        except Exception:
            pass
    # legacy single-light API removed; use set_alignment_pg_light_state / set_alignment_hene_light_state

    def _choose_folder(self):
        start_dir = self.dir_edit.text().strip() or QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.DocumentsLocation
        )
        dirname = QFileDialog.getExistingDirectory(self, "Select Output Directory", start_dir)
        if dirname:
            self.dir_edit.setText(dirname)

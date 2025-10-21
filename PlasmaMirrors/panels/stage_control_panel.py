from PyQt6 import QtCore, QtWidgets
from widgets.motor_row import MotorRow
import os
import json
from datetime import datetime, timezone

class StageControlPanel(QtWidgets.QWidget):
    action_performed = QtCore.pyqtSignal(str)
    request_move_absolute = QtCore.pyqtSignal(int, float)
    request_home = QtCore.pyqtSignal(int)
    request_move_delta = QtCore.pyqtSignal(int, float)
    request_set_speed = QtCore.pyqtSignal(int, float)
    request_set_lbound = QtCore.pyqtSignal(int, float)
    request_set_ubound = QtCore.pyqtSignal(int, float)
    request_move_to_saved = QtCore.pyqtSignal(str)
    request_stop_all = QtCore.pyqtSignal()

    def __init__(self, rows: list[MotorRow]):
        super().__init__()
        self.rows = rows
        self.current_index = 0
        grp = QtWidgets.QGroupBox("Stage Controls")
        self.selector = QtWidgets.QComboBox()
        for i, r in enumerate(self.rows, start=1):
            # display long name; store index
            self.selector.addItem(r.info.long, userData=i-1)
        self.selector.currentIndexChanged.connect(self._on_selection_changed)

        # Absolute position control
        self.abs_value = QtWidgets.QDoubleSpinBox()
        self.abs_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.abs_value.setDecimals(4)
        self.abs_value.setMinimum(0.0)
        self.abs_value.setMaximum(99999.0)
        #self.abs_unit = QtWidgets.QLabel("mm")
        #set units from the varaible "unit"
        self.abs_unit = QtWidgets.QLabel(self.rows[0].info.unit)
        self.abs_unit.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        abs_stack = QtWidgets.QVBoxLayout()
        abs_stack.setSpacing(2)
        abs_stack.addWidget(self.abs_value)
        abs_stack.addWidget(self.abs_unit)
        abs_stack_w = QtWidgets.QWidget(); abs_stack_w.setLayout(abs_stack)

        self.btn_home = QtWidgets.QPushButton("Home")
        self.btn_home.clicked.connect(self._home)
        self.btn_absolute = QtWidgets.QPushButton("Absolute")
        self.btn_absolute.clicked.connect(self._move_absolute)

        # Jog control
        self.jog_value = QtWidgets.QDoubleSpinBox()
        self.jog_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.jog_value.setDecimals(4)
        self.jog_value.setMinimum(0.0001)
        self.jog_value.setMaximum(99999.0)
        self.jog_value.setValue(0.01)
        self.jog_unit = QtWidgets.QLabel(self.rows[0].info.unit)
        self.jog_unit.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        jog_stack = QtWidgets.QVBoxLayout(); jog_stack.setSpacing(2)
        jog_stack.addWidget(self.jog_value); jog_stack.addWidget(self.jog_unit)
        jog_stack_w = QtWidgets.QWidget(); jog_stack_w.setLayout(jog_stack)

        self.btn_back = QtWidgets.QPushButton("Back")
        self.btn_back.clicked.connect(lambda: self._jog(-1))
        self.btn_fwd = QtWidgets.QPushButton("Forward")
        self.btn_fwd.clicked.connect(lambda: self._jog(+1))

        #add buttons to set ubound and lbound
        self.btn_set_lbound = QtWidgets.QPushButton("Set Lower Bound")
        self.btn_set_lbound.clicked.connect(self._set_lbound)
        self.btn_set_ubound = QtWidgets.QPushButton("Set Upper Bound")
        self.btn_set_ubound.clicked.connect(self._set_ubound)
        self.lbound_value = QtWidgets.QDoubleSpinBox()
        self.lbound_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.lbound_value.setDecimals(4)
        self.lbound_value.setMinimum(-99999.0)
        self.lbound_value.setMaximum(99999.0)
        self.ubound_value = QtWidgets.QDoubleSpinBox()
        self.ubound_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.ubound_value.setDecimals(4)
        self.ubound_value.setMinimum(-99999.0)
        self.ubound_value.setMaximum(99999.0)


        #add button for speed
        self.btn_set_speed = QtWidgets.QPushButton("Set Speed")
        self.btn_set_speed.clicked.connect(self._set_speed)
        self.speed_value = QtWidgets.QDoubleSpinBox()
        self.speed_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.speed_value.setDecimals(2)
        self.speed_value.setMinimum(0.01)
        self.speed_value.setMaximum(1000.0)

        #add text label for speed unit and bounds unit
        self.speed_unit = QtWidgets.QLabel(self.rows[0].info.speed_unit)
        self.speed_unit.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.bound_unit = QtWidgets.QLabel(self.rows[0].info.unit)
        self.bound_unit.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.bound_unit_2 = QtWidgets.QLabel(self.rows[0].info.unit)
        self.bound_unit_2.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)

        # Layout inside group
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.addWidget(self.selector, 0, 0, 1, 3)
        grid.addWidget(self.btn_home, 1, 0)
        grid.addWidget(abs_stack_w, 1, 1)
        grid.addWidget(self.btn_absolute, 1, 2)
        grid.addWidget(self.btn_back, 2, 0)
        grid.addWidget(jog_stack_w, 2, 1)
        grid.addWidget(self.btn_fwd, 2, 2)
        grid.addWidget(self.btn_set_lbound, 3, 0)
        grid.addWidget(self.lbound_value, 3, 1)
        grid.addWidget(self.btn_set_ubound, 4, 0)
        grid.addWidget(self.ubound_value, 4, 1)
        grid.addWidget(self.btn_set_speed, 5, 0)
        grid.addWidget(self.speed_value, 5, 1)
        grid.addWidget(self.bound_unit, 3, 2)
        grid.addWidget(self.bound_unit_2, 4, 2)
        grid.addWidget(self.speed_unit, 5, 2)
        grp.setLayout(grid)

        # Overall layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(grp)

        # --- Move to Saved (GUI only) ---------------------------------
        self.saved_grp = QtWidgets.QGroupBox("")

        # Top bar: preset drop-down on the right (like your screenshot)
        topbar = QtWidgets.QHBoxLayout()

        self.saved_preset = QtWidgets.QComboBox()
        self.saved_preset.currentIndexChanged.connect(self._on_preset_changed)
        self.saved_preset.setFixedWidth(220)
        topbar.addWidget(self.saved_preset)

        # Second line: "Last Saved: <timestamp>"
        stamp_line = QtWidgets.QHBoxLayout()
        stamp_line.addWidget(QtWidgets.QLabel("Last Saved:"))
        self.saved_time = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.saved_time.setDisplayFormat("M/d/yyyy h:mm:ss AP")
        self.saved_time.setCalendarPopup(False)
        self.saved_time.setReadOnly(True)
        self.saved_time.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.saved_time.setFixedWidth(220)
        stamp_line.addWidget(self.saved_time)
        stamp_line.addStretch(1)

        # Table: Num | Name | Position | Order
        self.saved_table = QtWidgets.QTableWidget(0, 4)
        self.saved_table.verticalHeader().setDefaultSectionSize(20)
        self.saved_table.setWordWrap(False)
        self.saved_table.setStyleSheet(
            "QTableWidget { background-color: #d3d3d3; color: #000; }"
            "QTableWidget::item { padding: 2px 4px; }"
        )
        self.saved_table.setHorizontalHeaderLabels(["Num", "Name", "Position", "Order"])
        self.saved_table.horizontalHeader().setStyleSheet("QHeaderView::section { color: #000000; }")
        self.saved_table.verticalHeader().setVisible(False)
        self.saved_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.saved_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.saved_table.setMinimumHeight(180)

        hh = self.saved_table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        # Buttons row 1
        row1 = QtWidgets.QHBoxLayout()
        self.btn_configure   = QtWidgets.QPushButton("Configure")
        self.btn_save_current = QtWidgets.QPushButton("Save Current")
        self.btn_save_current.clicked.connect(self._on_save_current)
        self.btn_move_to_saved = QtWidgets.QPushButton("Move to Saved")
        self.btn_move_to_saved.clicked.connect(lambda: self.request_move_to_saved.emit(self.saved_preset.currentText().strip()))

        row1.addWidget(self.btn_configure)
        row1.addWidget(self.btn_save_current)
        row1.addWidget(self.btn_move_to_saved)

        # connect configure button to open editor
        self.btn_configure.clicked.connect(self._open_configure_dialog)

        # Buttons row 2 (Home All | Scan Stage | Stop All)
        row2 = QtWidgets.QHBoxLayout()
        self.btn_home_all  = QtWidgets.QPushButton("Home All")
        # Clicking Home All should trigger the Move-to-Saved flow for the preset "HOME ALL"
        self.btn_home_all.clicked.connect(lambda: self.request_move_to_saved.emit("HOME ALL"))
        self.btn_scan_stage = QtWidgets.QPushButton("Scan Stage")
        self.btn_stop_all   = QtWidgets.QPushButton("Stop All")
        # Clicking Stop All should request stopping of all stages and cancel queued moves
        self.btn_stop_all.clicked.connect(lambda: self.request_stop_all.emit())
        row2.addWidget(self.btn_home_all)
        row2.addWidget(self.btn_scan_stage)
        row2.addWidget(self.btn_stop_all)

        # Pack group
        sv = QtWidgets.QVBoxLayout()
        sv.setContentsMargins(8, 8, 8, 8)
        sv.setSpacing(6)
        sv.addLayout(topbar)
        sv.addLayout(stamp_line)
        sv.addWidget(self.saved_table)
        sv.addLayout(row1)
        sv.addLayout(row2)
        self.saved_grp.setLayout(sv)

        layout.addWidget(self.saved_grp)
        # Load saved positions
        self.load_saved_positions()
        # keep trailing stretch at the bottom so saved_grp sits above it
        layout.addStretch(1)

        # Styling to echo your example
        grp.setStyleSheet("QGroupBox { font-weight: 600; margin-top: 14px; } QGroupBox::title { subcontrol-origin: margin; left: 8px; }")
        # keep this section compact in the horizontal layout
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMaximumWidth(380)
        self.btn_home.setStyleSheet("background:#5e8f6d; border:1px solid #486d53; padding:4px 10px; border-radius:6px;")
        for b in (self.btn_absolute, self.btn_back, self.btn_fwd):
            b.setStyleSheet("background:#2c2c2c; border:1px solid #3a3a3a; padding:4px 10px; border-radius:6px;")
        for sp in (self.abs_value, self.jog_value):
            sp.setFixedWidth(100)

        # Initialize with first row
        self._on_selection_changed(0)

    def refresh_rows(self, rows: list[MotorRow]):
        """Refresh internal rows reference and update selector entries and unit labels.
        Called when the MotorStatusPanel rows are rebuilt or reordered.
        """
        self.rows = rows
        # repopulate selector
        try:
            self.selector.blockSignals(True)
            self.selector.clear()
            for i, r in enumerate(self.rows, start=1):
                self.selector.addItem(r.info.long, userData=i-1)
            self.selector.blockSignals(False)
        except Exception:
            pass
        # update unit labels based on first row if available
        try:
            if self.rows:
                self.abs_unit.setText(self.rows[0].info.unit)
                self.jog_unit.setText(self.rows[0].info.unit)
                self.bound_unit.setText(self.rows[0].info.unit)
                self.bound_unit_2.setText(self.rows[0].info.unit)
                self.speed_unit.setText(self.rows[0].info.speed_unit)
        except Exception:
            pass
        
    def _on_selection_changed(self, _idx: int):
        self.current_index = self.selector.currentData() if self.selector.currentData() is not None else 0
        row = self.rows[self.current_index]
        self.abs_unit.setText(row.info.unit)
        self.jog_unit.setText(row.info.unit)
        self.bound_unit.setText(row.info.unit)
        self.bound_unit_2.setText(row.info.unit)
        self.speed_unit.setText(row.info.speed_unit)
        if row.info.unit == "deg":
            self.abs_value.setDecimals(2); self.jog_value.setDecimals(2)
        else:
            self.abs_value.setDecimals(4); self.jog_value.setDecimals(4)
        self.abs_value.setRange(float(row.info.lbound), float(row.info.ubound))
        self.jog_value.setRange(0.0, float(row.info.span))
        self.abs_value.setValue(float(row.info.eng_value))

    def _emit_move(self, row: MotorRow, value: float, verb: str = "Move"):
        num = getattr(row, 'index', 1)
        idx = num - 1
        unit = row.info.unit
        val = f"{value:.2f} {unit}" if unit == "deg" else f"{value:.6f} {unit}"
        self.action_performed.emit(f"{verb} {row.info.short}, Index {idx} (Num {num}) to {val}")

    def _home(self):
        row = self.rows[self.current_index]
        self.request_home.emit(int(row.index))
        self._emit_move(row, 0.0, verb="Home")

    def _move_absolute(self):
        row = self.rows[self.current_index]
        val = float(self.abs_value.value())
        self.request_move_absolute.emit(int(row.index), float(val))
        self._emit_move(row, val)

    def _jog(self, direction: int):
        row = self.rows[self.current_index]
        delta = float(self.jog_value.value()) * float(direction)
        self.request_move_delta.emit(int(row.index), float(delta))
        self._emit_move(row, float(row.info.eng_value), verb="Jog")

    def _set_lbound(self):
        row = self.rows[self.current_index]
        val = float(self.lbound_value.value())
        if val >= row.info.ubound:
            val = row.info.ubound - 0.01  # ensure lbound < ubound
        row.info.lbound = val
        msg = f"Set Lower Bound of {row.info.short}, Index {row.index} to {val:.4f} {row.info.unit}"
        self.request_set_lbound.emit(int(row.index), float(val))
        self.action_performed.emit(msg)
        self.lbound_value.setValue(val)  # update spinbox in case it was adjusted

    def _set_ubound(self):
        row = self.rows[self.current_index]
        val = float(self.ubound_value.value())
        if val <= row.info.lbound:
            val = row.info.lbound + 0.01  # ensure ubound > lbound
        row.info.ubound = val
        msg = f"Set Upper Bound of {row.info.short}, Index {row.index} to {val:.4f} {row.info.unit}"
        self.request_set_ubound.emit(int(row.index), float(val))
        self.action_performed.emit(msg)
        self.ubound_value.setValue(val)  # update spinbox in case it was adjusted
        
    def _set_speed(self):
        row = self.rows[self.current_index]
        val = float(self.speed_value.value())
        self.request_set_speed.emit(int(row.index), float(val))
        self.action_performed.emit(f"Set Speed request for {row.info.short}, Index {row.index} to {val:.2f} {row.info.speed_unit}")
    
    def _on_preset_changed(self, idx):
        if hasattr(self, "_saved_blocks") and 0 <= idx < len(self._saved_blocks):
            self._update_saved_display(self._saved_blocks[idx])

    def load_saved_positions(self):
        """Read saved positions from a json file and populate dropdown, timestamp, and table."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base_dir, "parameters/Saved_positions.json")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)   # {preset: {"last_saved_time": "...", "stages":[...]}, ...}
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return

        # Preserve insertion order of keys (JSON -> dict order is preserved in Py3.7+)
        blocks = []
        for preset, payload in data.items():
            blocks.append({
                "name":  preset,
                "time":  payload.get("last_saved_time"),
                "stages": payload.get("stages", []),
            })

        # Fill the preset dropdown
        self._saved_blocks = blocks
        self.saved_preset.blockSignals(True)
        self.saved_preset.clear()
        self.saved_preset.addItems([b["name"] for b in blocks])
        self.saved_preset.blockSignals(False)

        if blocks:
            self._update_saved_display(blocks[0])

    def _update_saved_display(self, block):
        """Update time and table from a parsed JSON 'block' dict."""
        # Time
        t = QtCore.QDateTime.fromString(block.get("time", ""), QtCore.Qt.DateFormat.ISODate)
        self.saved_time.setDateTime(t if t.isValid() else QtCore.QDateTime.currentDateTime())

        # Table: Num | Name | Position | Order
        self.saved_table.setRowCount(0)
        for idx, st in enumerate(block.get("stages", []), start=1):
            name = st.get("name", "")
            pos  = st.get("position", "")
            order = st.get("order", "")
            stage_num = st.get("stage_num")

            row = self.saved_table.rowCount()
            self.saved_table.insertRow(row)
            # If stage_num present in JSON use it, otherwise fall back to sequential idx
            num_display = str(stage_num) if stage_num is not None else str(idx)
            self.saved_table.setItem(row, 0, QtWidgets.QTableWidgetItem(num_display))
            self.saved_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(name)))
            # Format numeric positions nicely; otherwise show as-is
            if isinstance(pos, (int, float)):
                self.saved_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{pos:.6f}"))
            else:
                self.saved_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(pos)))
            self.saved_table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(order)))

    def _on_save_current(self):
        """
        Save the CURRENT positions of all motors (from Part 1 rows) into the
        currently selected preset in Saved_positions.json, then refresh the UI.
        """
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base_dir, "parameters/Saved_positions.json")
        preset = self.saved_preset.currentText().strip() or "Last position"

        # Load existing JSON
        data = {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        except Exception as e:
            self.action_performed.emit(f"Failed to read {file_path}: {e}")
            return

        payload = data[preset]
        stages = payload.get("stages", [])

        # Build a quick map from GUI (Part 1) short names -> current engineering value
        gui_pos = {}
        for r in self.rows:
            try:
                gui_pos[r.info.short] = float(r.info.eng_value)
            except Exception:
                pass

        # Update ONLY existing stages by name; keep order & other fields intact
        updated_count = 0
        for st in stages:
            name = st.get("name")
            if name in gui_pos:
                st["position"] = gui_pos[name]
                updated_count += 1

        # Update timestamp
        now = datetime.now()
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
        payload["last_saved_time"] = now_iso

        # Write back
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.action_performed.emit(f"Failed to write {file_path}: {e}")
            return

        # Also append entries into a Saved_positions log file in the same folder
        try:
            log_path = os.path.join(os.path.dirname(file_path), 'Saved_positions_LOG.txt')
            # append one row per stage for this preset (do not overwrite previous rows)
            try:
                self._append_saved_positions_log(log_path, preset, payload)
            except Exception:
                # fallback: best-effort full rewrite
                try:
                    self._write_saved_positions_log(log_path, data)
                except Exception:
                    pass
        except Exception:
            pass

        # Refresh in-memory blocks and UI without changing stage order
        blocks = []
        for preset_name, pl in data.items():
            blocks.append({
                "name":  preset_name,
                "time":  pl.get("last_saved_time"),
                "stages": pl.get("stages", []),   # keep as-is (order preserved)
            })
        self._saved_blocks = blocks

        # Keep current preset selected and refresh timestamp + table
        try:
            self.saved_preset.blockSignals(True)
            self.saved_preset.clear()
            self.saved_preset.addItems([b["name"] for b in blocks])
            idx = next((i for i, b in enumerate(blocks) if b["name"] == preset), 0)
            self.saved_preset.setCurrentIndex(idx)
            self.saved_preset.blockSignals(False)
            self._update_saved_display(blocks[idx])
        except Exception:
            pass

        # Log result
        self.action_performed.emit(
            f'Updated "{preset}" at {now_iso}: {updated_count} stage(s) updated; order preserved.'
        )

    # ------------------ Configure dialog ------------------
    def _open_configure_dialog(self):
        """Open a modal dialog to edit the Saved_positions.json presets.

        The dialog allows selecting a preset, editing its stages (name, stage_num,
        position, order), adding/removing/reordering stages, and editing premoves
        (comma-separated positions). On Save the JSON file is updated and the
        UI refreshed.
        """
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base_dir, "parameters/Saved_positions.json")

        # Load data
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self.action_performed.emit(f"Failed to read saved positions: {e}")
            return

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Configure Saved Positions")
        dialog.setModal(True)
        dlg_layout = QtWidgets.QVBoxLayout(dialog)

        # Preset selector
        preset_selector = QtWidgets.QComboBox()
        presets = list(data.keys())
        preset_selector.addItems(presets)
        dlg_layout.addWidget(preset_selector)

        # Table for stages
        table = QtWidgets.QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["Name", "Stage Num", "Position", "Order", "Premoves", "Actions"])
        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        # Make header and vertical header text black for legibility
        try:
            table.horizontalHeader().setStyleSheet("QHeaderView::section { color: #000000; }")
        except Exception:
            pass
        try:
            table.verticalHeader().setStyleSheet("QHeaderView::section { color: #000000; }")
        except Exception:
            pass
        dlg_layout.addWidget(table)

        # Helper buttons: add, remove (Move Up/Down removed)
        btn_row = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton("Add Stage")
        btn_remove = QtWidgets.QPushButton("Remove Selected")
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_remove)
        dlg_layout.addLayout(btn_row)

        # Dialog buttons
        dlg_buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        dlg_layout.addWidget(dlg_buttons)

        # selection state for Select buttons (remember previous selection)
        prev_btn = {'btn': None}
        def on_select_row(row_idx: int, btn: QtWidgets.QPushButton):
            try:
                table.selectRow(row_idx)
            except Exception:
                pass
            try:
                if prev_btn['btn'] is not None and prev_btn['btn'] is not btn:
                    prev_btn['btn'].setStyleSheet('')
            except Exception:
                pass
            try:
                btn.setStyleSheet('background-color: #4CAF50; color: white;')
                prev_btn['btn'] = btn
            except Exception:
                pass

        def load_preset_to_table(preset_name: str):
            table.setRowCount(0)
            payload = data.get(preset_name, {})
            stages = payload.get('stages', []) or []
            for st in stages:
                r = table.rowCount()
                table.insertRow(r)
                # Name
                name_item = QtWidgets.QLineEdit(str(st.get('name', '')))
                name_item.setStyleSheet('color: #000000;')
                table.setCellWidget(r, 0, name_item)
                # Stage Num
                sn = QtWidgets.QSpinBox(); sn.setMinimum(0); sn.setMaximum(9999)
                sn.setStyleSheet('color: #000000;')
                try:
                    if st.get('stage_num') is not None:
                        sn.setValue(int(st.get('stage_num')))
                except Exception:
                    pass
                table.setCellWidget(r, 1, sn)
                # Position
                pos = QtWidgets.QDoubleSpinBox(); pos.setDecimals(6); pos.setMinimum(-99999.0); pos.setMaximum(99999.0)
                pos.setStyleSheet('color: #000000;')
                try:
                    if st.get('position') is not None:
                        pos.setValue(float(st.get('position')))
                except Exception:
                    pass
                table.setCellWidget(r, 2, pos)
                # Order
                ordw = QtWidgets.QSpinBox(); ordw.setMinimum(0); ordw.setMaximum(9999)
                ordw.setStyleSheet('color: #000000;')
                try:
                    if st.get('order') is not None:
                        ordw.setValue(int(st.get('order')))
                except Exception:
                    pass
                table.setCellWidget(r, 3, ordw)
                # Premoves (comma separated)
                prem = QtWidgets.QLineEdit()
                prem.setStyleSheet('color: #000000;')
                premoves = st.get('premoves', [])
                if isinstance(premoves, (list, tuple)):
                    prem.setText(','.join([str(x) for x in premoves]))
                else:
                    prem.setText(str(premoves))
                table.setCellWidget(r, 4, prem)
                # Actions (placeholder)
                aw = QtWidgets.QWidget(); ah = QtWidgets.QHBoxLayout(); ah.setContentsMargins(0,0,0,0)
                sel_btn = QtWidgets.QPushButton("Select")
                sel_btn.setProperty('row_index', r)
                sel_btn.clicked.connect(lambda _checked, rr=r, b=sel_btn: on_select_row(rr, b))
                ah.addWidget(sel_btn)
                aw.setLayout(ah)
                table.setCellWidget(r, 5, aw)

        # initial load
        if presets:
            load_preset_to_table(presets[0])

        def on_preset_changed(i):
            name = preset_selector.itemText(i)
            load_preset_to_table(name)

        preset_selector.currentIndexChanged.connect(on_preset_changed)

        def add_stage():
            r = table.rowCount()
            table.insertRow(r)
            le = QtWidgets.QLineEdit('New Stage'); le.setStyleSheet('color: #000000;'); table.setCellWidget(r, 0, le)
            sn = QtWidgets.QSpinBox(); sn.setMinimum(0); sn.setMaximum(9999); sn.setStyleSheet('color: #000000;'); table.setCellWidget(r, 1, sn)
            pos = QtWidgets.QDoubleSpinBox(); pos.setDecimals(6); pos.setMinimum(-99999.0); pos.setMaximum(99999.0); pos.setStyleSheet('color: #000000;'); table.setCellWidget(r, 2, pos)
            ordw = QtWidgets.QSpinBox(); ordw.setMinimum(0); ordw.setMaximum(9999); ordw.setStyleSheet('color: #000000;'); table.setCellWidget(r, 3, ordw)
            prem_le = QtWidgets.QLineEdit(''); prem_le.setStyleSheet('color: #000000;'); table.setCellWidget(r, 4, prem_le)
            aw = QtWidgets.QWidget(); ah = QtWidgets.QHBoxLayout(); ah.setContentsMargins(0,0,0,0); sel_btn = QtWidgets.QPushButton('Select'); sel_btn.setProperty('row_index', r); sel_btn.clicked.connect(lambda _checked, rr=r, b=sel_btn: on_select_row(rr, b)); ah.addWidget(sel_btn); aw.setLayout(ah); table.setCellWidget(r, 5, aw)

        def remove_selected():
            sel = table.selectionModel().selectedRows()
            rows = sorted([s.row() for s in sel], reverse=True)
            for rr in rows:
                table.removeRow(rr)

        btn_add.clicked.connect(add_stage)
        btn_remove.clicked.connect(remove_selected)

        def on_save():
            # Build updated payload for the current preset
            pname = preset_selector.currentText()
            payload = data.get(pname, {})
            stages = []
            for r in range(table.rowCount()):
                try:
                    name = table.cellWidget(r, 0).text()
                    stage_num = int(table.cellWidget(r, 1).value()) if table.cellWidget(r,1) else None
                    position = float(table.cellWidget(r, 2).value()) if table.cellWidget(r,2) else None
                    orderv = int(table.cellWidget(r, 3).value()) if table.cellWidget(r,3) else None
                    prem_text = table.cellWidget(r,4).text() if table.cellWidget(r,4) else ''
                    premoves = []
                    if prem_text:
                        for p in prem_text.split(','):
                            try:
                                premoves.append(float(p.strip()))
                            except Exception:
                                pass
                    st = {
                        'name': name,
                        'stage_num': stage_num,
                        'position': position,
                        'order': orderv,
                        'premoves': premoves,
                    }
                    stages.append(st)
                except Exception:
                    pass

            # update payload and timestamp
            payload['stages'] = stages
            now_iso = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            payload['last_saved_time'] = now_iso
            data[pname] = payload

            # write back to file
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                self.action_performed.emit(f"Failed to write saved positions: {e}")
                return

            # refresh UI
            try:
                self.load_saved_positions()
            except Exception:
                pass
            self.action_performed.emit(f"Saved preset {pname} at {now_iso}")
            dialog.accept()

        dlg_buttons.accepted.connect(on_save)
        dlg_buttons.rejected.connect(dialog.reject)

        dialog.exec()

    def _write_saved_positions_log(self, log_path: str, data: dict):
        """(Legacy) Full-write human-readable log. Kept as a fallback.
        This writes a block-style log; prefer the append-style CSV produced by
        `_append_saved_positions_log` which preserves history by appending rows.
        """
        try:
            lines = []
            now = datetime.now()
            header = now.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"Saved Positions Log - generated {header}")
            lines.append("")
            for preset, payload in data.items():
                lines.append(f"Preset: {preset}")
                lst = payload.get('stages', [])
                last = payload.get('last_saved_time', '')
                if last:
                    lines.append(f"  Last saved: {last}")
                if not lst:
                    lines.append("  (no stages)")
                    lines.append("")
                    continue
                for st in lst:
                    name = st.get('name', '')
                    pos = st.get('position', '')
                    stage_num = st.get('stage_num', '')
                    order = st.get('order', '')
                    # Only list the final visible positions (no pre-move details)
                    lines.append(f"  - {name} (stage_num={stage_num}) order={order} → {pos}")
                lines.append("")

            tmp = log_path + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))
            try:
                os.replace(tmp, log_path)
            except Exception:
                try:
                    os.remove(log_path)
                except Exception:
                    pass
                os.replace(tmp, log_path)
        except Exception:
            pass

    def _append_saved_positions_log(self, log_path: str, preset_name: str, payload: dict):
        """Append a single row for this preset to Saved_positions_LOG.txt.

        Row format (double-space separated):
        Preset  Date  Time  Addr1  Abbr1  Pos1  Order1  Addr2  Abbr2  Pos2  Order2 ...

        Stages are ordered by their numeric address (`stage_num`). A dynamic
        header line matching the columns for this row is written only when the
        file does not yet exist.
        """
        try:
            # determine timestamp: prefer payload['last_saved_time'] in ISO, else now
            ts = payload.get('last_saved_time') if isinstance(payload.get('last_saved_time'), str) else None
            if ts:
                try:
                    dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
                except Exception:
                    try:
                        dt = datetime.fromisoformat(ts)
                    except Exception:
                        dt = datetime.now()
            else:
                dt = datetime.now()
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M:%S")

            stages = payload.get('stages', []) or []
            # sort by stage_num (address); missing stage_num sorts to the end
            def _addr_key(s):
                try:
                    return int(s.get('stage_num'))
                except Exception:
                    return 10**9

            stages_sorted = sorted(stages, key=_addr_key)

            # Build header dynamically for this payload (only if file missing)
            header_fields = ["Preset", "Date", "Time"]
            for i, st in enumerate(stages_sorted, start=1):
                header_fields.extend([
                    f"Addr{i}",
                    f"Abbr{i}",
                    f"Pos{i}",
                    f"Order{i}",
                ])
            header_line = "  ".join(header_fields)

            # Build the data row
            row_fields = [str(preset_name), date_str, time_str]
            for st in stages_sorted:
                addr = st.get('stage_num', '')
                abbr = st.get('name', '')
                pos = st.get('position', '')
                order = st.get('order', '')
                # format numbers: positions as floats with 6 decimals if numeric
                try:
                    pos = f"{float(pos):.6f}"
                except Exception:
                    pos = str(pos)
                row_fields.extend([str(addr), str(abbr), pos, str(order)])

            line = "  ".join(row_fields)

            write_header = not os.path.exists(log_path)
            # Append atomically by writing then flushing
            with open(log_path, 'a', encoding='utf-8') as f:
                if write_header:
                    f.write(header_line + "\n")
                f.write(line + "\n")
        except Exception:
            # Don't let logging break saving flow
            pass

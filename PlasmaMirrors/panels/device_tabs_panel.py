from PyQt6 import QtWidgets, QtCore
import os, json

class DeviceTabsPanel(QtWidgets.QWidget):
    """Left-side panel with tabs: Zaber Stages, Cameras, Spectrometers, Picomotors.
    The Zaber Stages tab is populated from parameters/stages.json.
    """
    # signal emitted when user requests to connect to a port/baud
    connectRequested = QtCore.pyqtSignal(str, int)

    def __init__(self, stages_file=None, default_port=None, default_baud: int = 115200, parent=None):
        super().__init__(parent)
        self.stages_file = stages_file or os.path.join(os.path.dirname(__file__), '..', 'parameters', 'stages.json')
        # path to device connections file (global device connection defaults)
        base_dir = os.path.dirname(os.path.dirname(__file__))
        self.connections_file = os.path.join(base_dir, 'parameters', 'device_connections.json')
        # cameras file
        self.cameras_file = os.path.join(base_dir, 'parameters', 'cameras.json')
        # spectrometers file
        self.spectrometers_file = os.path.join(base_dir, 'parameters', 'spectrometers.json')
        # defaults passed from caller
        self._default_port = default_port
        self._default_baud = default_baud
        self._build_ui()
        self._load_stages()
        # load cameras after UI built
        try:
            self._load_cameras()
        except Exception:
            self._cameras = []
        # load spectrometers after UI built
        try:
            self._load_spectrometers()
        except Exception:
            self._spectrometers = []

    # emit when stages.json is changed by the UI (provides the new list of stage dicts)
    stages_changed = QtCore.pyqtSignal(list)
    # emit when cameras/spectrometers definitions change
    cameras_changed = QtCore.pyqtSignal(list)
    spectrometers_changed = QtCore.pyqtSignal(list)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        # place the tabs at the top of the panel
        self.tabs.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)
        # allow the tab widget to expand to show its contents
        self.tabs.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        # four tabs
        self.tab_stages = QtWidgets.QWidget()
        self.tab_cams = QtWidgets.QWidget()
        self.tab_specs = QtWidgets.QWidget()
        self.tab_pico = QtWidgets.QWidget()
        self.tabs.addTab(self.tab_stages, "Zaber Stages")
        self.tabs.addTab(self.tab_cams, "Cameras")
        self.tabs.addTab(self.tab_specs, "Spectrometers")
        self.tabs.addTab(self.tab_pico, "Picomotors")

        layout.addWidget(self.tabs)

        # --- Picomotors tab placeholder (MainWindow will insert real panel) ---
        pico_layout = QtWidgets.QVBoxLayout(self.tab_pico)
        self.pico_container = QtWidgets.QWidget()
        pico_layout.addWidget(self.pico_container)

        # --- build cameras tab layout ---
        cam_layout = QtWidgets.QVBoxLayout(self.tab_cams)
        lab = QtWidgets.QLabel("Camera Info Listbox")
        lab.setStyleSheet("font-weight: bold; margin-bottom: 6px; color: #0b3b0b;")
        cam_layout.addWidget(lab)

        # Table: Name | Purpose | Filters | Serial
        self.cameras_table = QtWidgets.QTableWidget(0, 4)
        self.cameras_table.setHorizontalHeaderLabels(['Name', 'Purpose', 'Filters', 'Serial'])
        # Configure header resize modes so Filters (col 2) is the flexible wide column
        header = self.cameras_table.horizontalHeader()
        try:
            # Make all columns fixed so typing long values won't auto-resize the table.
            # Choose sensible fixed widths matching the desired layout from the screenshot.
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Fixed)
            # Set explicit widths (pixels): Name | Purpose | Filters | Serial
            # Narrow Name and Purpose so the full row typically fits in a narrower panel
            self.cameras_table.setColumnWidth(0, 70)
            self.cameras_table.setColumnWidth(1, 120)
            self.cameras_table.setColumnWidth(2, 250)
            self.cameras_table.setColumnWidth(3, 70)
        except Exception:
            # If fixed sizing isn't supported, fall back to stretch-last behaviour
            try:
                self.cameras_table.horizontalHeader().setStretchLastSection(True)
            except Exception:
                pass
        self.cameras_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.cameras_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked | QtWidgets.QAbstractItemView.EditTrigger.SelectedClicked | QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed)
        # Improve readability: alternating row colors, clearer header and selection
        try:
            self.cameras_table.setAlternatingRowColors(True)
            self.cameras_table.setStyleSheet(
                "QTableWidget { background: #ffffff; color: #0a0a0a; gridline-color: #d0d0d0; }"
                "QTableWidget::item { padding: 4px; }"
                "QTableWidget::item:selected { background: #1f5fa8; color: #ffffff; }"
                "QHeaderView::section { background: #f0f0f0; color: #000000; font-weight: bold; padding: 6px; border: 1px solid #d0d0d0; }"
            )
            # make headers stand out
            self.cameras_table.horizontalHeader().setStyleSheet("QHeaderView::section { padding: 6px; }")
        except Exception:
            pass
        cam_layout.addWidget(self.cameras_table)

        # Add / Remove buttons
        btn_row = QtWidgets.QHBoxLayout()
        self.btn_cam_add = QtWidgets.QPushButton('Add')
        self.btn_cam_remove = QtWidgets.QPushButton('Remove')
        btn_row.addWidget(self.btn_cam_add)
        btn_row.addWidget(self.btn_cam_remove)
        btn_row.addStretch()
        cam_layout.addLayout(btn_row)

        # connect camera table signals
        self.cameras_table.cellChanged.connect(self._on_camera_cell_changed)
        self.btn_cam_add.clicked.connect(self._add_camera)
        self.btn_cam_remove.clicked.connect(self._remove_selected_camera)

        # --- build spectrometers tab layout ---
        spec_layout = QtWidgets.QFormLayout(self.tab_specs)
        # Visible spectrometer filename
        self.spec_vis_edit = QtWidgets.QLineEdit()
        self.spec_vis_edit.setFixedWidth(150)
        spec_layout.addRow("Visible spectrometer filename", self.spec_vis_edit)
        # Visible spectrometer filters (text label, e.g. filter names) — use QLineEdit like filename
        self.spec_vis_filters = QtWidgets.QLineEdit()
        self.spec_vis_filters.setFixedWidth(280)
        spec_layout.addRow("Visible spectrometer filters", self.spec_vis_filters)

        # XUV spectrometer filename
        self.spec_xuv_edit = QtWidgets.QLineEdit()
        self.spec_xuv_edit.setFixedWidth(150)
        spec_layout.addRow("XUV spectrometer filename", self.spec_xuv_edit)
        # XUV spectrometer filters (text)
        self.spec_xuv_filters = QtWidgets.QLineEdit()
        self.spec_xuv_filters.setFixedWidth(280)
        spec_layout.addRow("XUV spectrometer filters", self.spec_xuv_filters)

        # connect edits to save handlers
        self.spec_vis_edit.editingFinished.connect(self._on_spec_changed)
        self.spec_xuv_edit.editingFinished.connect(self._on_spec_changed)
        self.spec_vis_filters.editingFinished.connect(self._on_spec_changed)
        self.spec_xuv_filters.editingFinished.connect(self._on_spec_changed)

        # -- build stages tab layout --
        s_layout = QtWidgets.QHBoxLayout(self.tab_stages)

        # left column: list of stages plus action buttons
        left_col = QtWidgets.QWidget()
        left_col_layout = QtWidgets.QVBoxLayout(left_col)
        # list of stages
        self.stage_list = QtWidgets.QListWidget()
        self.stage_list.setFixedWidth(220)
        left_col_layout.addWidget(self.stage_list)
        # small spacer
        left_col_layout.addSpacing(8)

        # COM port selector combo (for Zaber stages) - placed in left column
        self.com_combo = QtWidgets.QComboBox()
        self.com_combo.setEditable(True)
        # populate with common ports
        try:
            self.com_combo.addItems(["COM1","COM2","COM3","COM4","/dev/ttyUSB0","/dev/ttyUSB1","/dev/tty.usbserial-0001"])
        except Exception:
            pass
        row_com = QtWidgets.QHBoxLayout()
        row_com.addWidget(QtWidgets.QLabel('COM'))
        row_com.addWidget(self.com_combo)
        left_col_layout.addLayout(row_com)

        # Baud rate selector - placed in left column
        self.baud_combo = QtWidgets.QComboBox()
        self.baud_combo.setEditable(True)
        try:
            self.baud_combo.addItems([str(x) for x in (9600, 19200, 38400, 57600, 115200, 230400)])
        except Exception:
            pass
        row_baud = QtWidgets.QHBoxLayout()
        row_baud.addWidget(QtWidgets.QLabel('Baud'))
        row_baud.addWidget(self.baud_combo)
        left_col_layout.addLayout(row_baud)

        # Connect button and stage controls (placed under the list)
        self.btn_connect = QtWidgets.QPushButton("Connect")
        # Configure / Save / Add / Remove buttons for stages (configure enables editing)
        self.btn_stage_configure = QtWidgets.QPushButton('Configure')
        self.btn_stage_save = QtWidgets.QPushButton('Save')
        self.btn_stage_save.setEnabled(False)
        self.btn_stage_add = QtWidgets.QPushButton('Add')
        self.btn_stage_remove = QtWidgets.QPushButton('Remove')
        # Ensure Configure and Remove buttons are wide enough to show full labels
        try:
            self.btn_stage_configure.setMinimumWidth(90)
            self.btn_stage_remove.setMinimumWidth(90)
        except Exception:
            pass

        # Buttons layout under the stage list
        btns_top = QtWidgets.QHBoxLayout()
        btns_top.addWidget(self.btn_connect)
        btns_top.addStretch()
        left_col_layout.addLayout(btns_top)
        left_col_layout.addSpacing(6)

        btns2 = QtWidgets.QHBoxLayout()
        btns2.addWidget(self.btn_stage_configure)
        btns2.addWidget(self.btn_stage_save)
        btns2.addWidget(self.btn_stage_add)
        btns2.addWidget(self.btn_stage_remove)
        left_col_layout.addLayout(btns2)
        left_col_layout.addStretch()

        # right: detail form (keeps COM/Baud fields and other details)
        form = QtWidgets.QFormLayout()
        right = QtWidgets.QWidget()
        right.setLayout(form)
        # add left and right widgets to the horizontal layout
        s_layout.addWidget(left_col)
        s_layout.addWidget(right)

        # make these editable so user can change parameters
        self.name_edit = QtWidgets.QLineEdit()
        self.model_edit = QtWidgets.QLineEdit()
        self.type_combo = QtWidgets.QComboBox(); self.type_combo.addItems(["Linear","Rotation"])
        self.num_spin = QtWidgets.QSpinBox(); self.num_spin.setRange(0, 999)
        self.abr_edit = QtWidgets.QLineEdit()
        self.desc_edit = QtWidgets.QPlainTextEdit()
        # Limit is read-only (populated from JSON initially, and updated from device-reported upper bound)
        self.limit_edit = QtWidgets.QLineEdit(); self.limit_edit.setReadOnly(True)

        form.addRow("Name", self.name_edit)
        form.addRow("Model Number", self.model_edit)
        form.addRow("Type", self.type_combo)
        form.addRow("Num", self.num_spin)
        form.addRow("Abr", self.abr_edit)
        form.addRow("Description", self.desc_edit)
        form.addRow("Limit", self.limit_edit)

    # COM/Baud controls moved to the left column near the stage list

        # connect selection change
        self.stage_list.currentRowChanged.connect(self._on_stage_selected)
        # initially editing disabled; configure mode enables editing
        try:
            self._configure_mode = False
            self._staged_stages = None
            # make fields read-only / disabled by default
            self.name_edit.setReadOnly(True)
            self.model_edit.setReadOnly(True)
            self.type_combo.setEnabled(False)
            self.num_spin.setEnabled(False)
            self.abr_edit.setReadOnly(True)
            self.desc_edit.setReadOnly(True)
            self.com_combo.setEnabled(False)
            self.baud_combo.setEnabled(False)
        except Exception:
            pass

        # connect selection change handlers and editing signals (edits are staged when configure_mode)
        self.name_edit.editingFinished.connect(lambda: self._on_field_changed('name'))
        self.model_edit.editingFinished.connect(lambda: self._on_field_changed('model_number'))
        self.type_combo.currentTextChanged.connect(lambda _: self._on_field_changed('type'))
        self.num_spin.valueChanged.connect(lambda _: self._on_field_changed('num'))
        self.abr_edit.editingFinished.connect(lambda: self._on_field_changed('Abr'))
        # QPlainTextEdit has no editingFinished, use textChanged
        self.desc_edit.textChanged.connect(lambda: self._on_field_changed('description'))
        self.com_combo.editTextChanged.connect(lambda _: self._on_com_changed())
        self.baud_combo.currentTextChanged.connect(lambda _: self._on_baud_changed())
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        # configure/save/add/remove handlers
        self.btn_stage_configure.clicked.connect(self._on_stage_configure_clicked)
        self.btn_stage_save.clicked.connect(self._on_stage_save_clicked)
        self.btn_stage_add.clicked.connect(self._on_stage_add)
        self.btn_stage_remove.clicked.connect(self._on_stage_remove)
        # add/remove disabled until configure mode
        self.btn_stage_add.setEnabled(False)
        self.btn_stage_remove.setEnabled(False)

        # (default_port/default_baud are handled in __init__ after _load_stages)

        # Styling: ensure tab labels and selection highlights are visible on a white background
        try:
            # Tab appearance
            self.tabs.setStyleSheet(
                "QTabWidget::pane { background: white; border: none; }"
                "QTabBar::tab { background: white; color: #000000; padding: 6px 10px; margin: 2px; border-radius: 4px; }"
                "QTabBar::tab:selected { background: #3399ff; color: #ffffff; }"
                "QTabBar::tab:hover { background: #e6f2ff; }"
            )

            # Stage list appearance (selected item highlight)
            self.stage_list.setStyleSheet(
                "QListWidget { background: white; color: #000000; }"
                "QListWidget::item:selected { background: #3399ff; color: #ffffff; }"
                "QListWidget::item:hover { background: #e6f2ff; }"
            )
        except Exception:
            pass

    def _load_stages(self):
        try:
            with open(self.stages_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = []
        # Load device connections defaults and apply to combos if present
        try:
            with open(self.connections_file, 'r', encoding='utf-8') as cf:
                con = json.load(cf)
                z = con.get('zaber', {}) if isinstance(con, dict) else {}
                port = z.get('PORT') or z.get('port')
                baud = z.get('BAUD') or z.get('baud')
                if port:
                    if self.com_combo.findText(str(port)) == -1:
                        self.com_combo.addItem(str(port))
                    self.com_combo.setCurrentText(str(port))
                elif getattr(self, '_default_port', None):
                    if self.com_combo.findText(str(self._default_port)) == -1:
                        self.com_combo.addItem(str(self._default_port))
                    self.com_combo.setCurrentText(str(self._default_port))
                if baud:
                    if self.baud_combo.findText(str(baud)) == -1:
                        self.baud_combo.addItem(str(baud))
                    self.baud_combo.setCurrentText(str(baud))
                elif getattr(self, '_default_baud', None):
                    if self.baud_combo.findText(str(self._default_baud)) == -1:
                        self.baud_combo.addItem(str(self._default_baud))
                    self.baud_combo.setCurrentText(str(self._default_baud))
        except Exception:
            # fallback to passed defaults if available
            try:
                if getattr(self, '_default_port', None):
                    if self.com_combo.findText(str(self._default_port)) == -1:
                        self.com_combo.addItem(str(self._default_port))
                    self.com_combo.setCurrentText(str(self._default_port))
            except Exception:
                pass
            try:
                if getattr(self, '_default_baud', None):
                    if self.baud_combo.findText(str(self._default_baud)) == -1:
                        self.baud_combo.addItem(str(self._default_baud))
                    self.baud_combo.setCurrentText(str(self._default_baud))
            except Exception:
                pass
        # sort by 'num'
        data = sorted(data, key=lambda s: s.get('num', 0))
        self._stages = data
        self.stage_list.clear()
        for s in data:
            self.stage_list.addItem(s.get('name',''))
        if data:
            self.stage_list.setCurrentRow(0)

    # ---------------- cameras helpers ----------------
    def _load_cameras(self):
        try:
            with open(self.cameras_file, 'r', encoding='utf-8') as f:
                cams = json.load(f)
        except Exception:
            cams = []
        if not isinstance(cams, list):
            cams = []
        self._cameras = cams
        # populate table without triggering cellChanged
        try:
            self.cameras_table.blockSignals(True)
            self.cameras_table.setRowCount(0)
            for c in cams:
                row = self.cameras_table.rowCount()
                self.cameras_table.insertRow(row)
                self.cameras_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(c.get('Name', ''))))
                self.cameras_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(c.get('Purpose', ''))))
                self.cameras_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(c.get('Filters', ''))))
                self.cameras_table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(c.get('Serial', ''))))
        finally:
            try: self.cameras_table.blockSignals(False)
            except Exception: pass

    def _save_cameras(self):
        try:
            out = []
            for r in range(self.cameras_table.rowCount()):
                try:
                    name = self.cameras_table.item(r, 0).text() if self.cameras_table.item(r, 0) else ''
                    purpose = self.cameras_table.item(r, 1).text() if self.cameras_table.item(r, 1) else ''
                    filters = self.cameras_table.item(r, 2).text() if self.cameras_table.item(r, 2) else ''
                    serial = self.cameras_table.item(r, 3).text() if self.cameras_table.item(r, 3) else ''
                    out.append({'Name': name, 'Purpose': purpose, 'Filters': filters, 'Serial': serial})
                except Exception:
                    continue
            with open(self.cameras_file, 'w', encoding='utf-8') as f:
                json.dump(out, f, indent=2)
            self._cameras = out
            try:
                self.cameras_changed.emit(self._cameras)
            except Exception:
                pass
        except Exception:
            pass

    # ---------------- spectrometers helpers ----------------
    def _load_spectrometers(self):
        try:
            with open(self.spectrometers_file, 'r', encoding='utf-8') as f:
                specs = json.load(f)
        except Exception:
            specs = []
        if not isinstance(specs, list):
            specs = []
        # Expect two entries: Visible and XUV (by convention); fallback to blanks
        self._spectrometers = specs
        vis = ''
        xuv = ''
        vis_filters = ''
        xuv_filters = ''
        try:
            if len(specs) > 0:
                vis = str(specs[0].get('filename', ''))
                vis_filters = specs[0].get('filters', '') or ''
            if len(specs) > 1:
                xuv = str(specs[1].get('filename', ''))
                xuv_filters = specs[1].get('filters', '') or ''
        except Exception:
            pass
        try:
            self.spec_vis_edit.blockSignals(True)
            self.spec_xuv_edit.blockSignals(True)
            self.spec_vis_filters.blockSignals(True)
            self.spec_xuv_filters.blockSignals(True)
            self.spec_vis_edit.setText(vis)
            self.spec_xuv_edit.setText(xuv)
            try:
                self.spec_vis_filters.setText(str(vis_filters))
            except Exception:
                pass
            try:
                self.spec_xuv_filters.setText(str(xuv_filters))
            except Exception:
                pass
        finally:
            try: self.spec_vis_edit.blockSignals(False)
            except Exception: pass
            try: self.spec_xuv_edit.blockSignals(False)
            except Exception: pass
            try: self.spec_vis_filters.blockSignals(False)
            except Exception: pass
            try: self.spec_xuv_filters.blockSignals(False)
            except Exception: pass

    def _save_spectrometers(self):
        try:
            vis = self.spec_vis_edit.text() if self.spec_vis_edit else ''
            xuv = self.spec_xuv_edit.text() if self.spec_xuv_edit else ''
            vis_filters = self.spec_vis_filters.text() if getattr(self, 'spec_vis_filters', None) is not None else ''
            xuv_filters = self.spec_xuv_filters.text() if getattr(self, 'spec_xuv_filters', None) is not None else ''
            out = []
            out.append({'name': 'Visible', 'filename': vis, 'filters': vis_filters})
            out.append({'name': 'XUV', 'filename': xuv, 'filters': xuv_filters})
            with open(self.spectrometers_file, 'w', encoding='utf-8') as f:
                json.dump(out, f, indent=2)
            self._spectrometers = out
            try:
                self.spectrometers_changed.emit(self._spectrometers)
            except Exception:
                pass
        except Exception:
            pass

    def _on_spec_changed(self):
        try:
            self._save_spectrometers()
        except Exception:
            pass

    def _on_camera_cell_changed(self, row: int, col: int):
        # save cameras whenever a cell is edited
        try:
            self._save_cameras()
        except Exception:
            pass

    def _add_camera(self):
        try:
            row = self.cameras_table.rowCount()
            self.cameras_table.insertRow(row)
            # add empty cells
            for c in range(4):
                self.cameras_table.setItem(row, c, QtWidgets.QTableWidgetItem(''))
            # focus on name cell
            self.cameras_table.editItem(self.cameras_table.item(row, 0))
            self._save_cameras()
        except Exception:
            pass

    def _remove_selected_camera(self):
        try:
            sel = self.cameras_table.selectionModel().selectedRows()
            # remove from bottom to top to avoid index shift
            rows = sorted([r.row() for r in sel], reverse=True)
            for r in rows:
                self.cameras_table.removeRow(r)
            self._save_cameras()
        except Exception:
            pass

    def _save_stages(self):
        """Write the in-memory stages list back to the JSON file (atomic-ish)."""
        try:
            # ensure numeric keys are proper types
            out = []
            for s in self._stages:
                # make a shallow copy and coerce types
                copy = dict(s)
                try:
                    copy['num'] = int(copy.get('num', 0))
                except Exception:
                    copy['num'] = 0
                # keep floats for limit when present
                if 'limit' in copy:
                    try:
                        copy['limit'] = float(copy.get('limit'))
                    except Exception:
                        pass
                out.append(copy)
            # write with indent for readability
            with open(self.stages_file, 'w', encoding='utf-8') as f:
                json.dump(out, f, indent=2)
            # Also update device_connections.json zaber entry with current COM/BAUD
            try:
                try:
                    with open(self.connections_file, 'r', encoding='utf-8') as cf:
                        con = json.load(cf)
                except Exception:
                    con = {}
                if not isinstance(con, dict):
                    con = {}
                port = str(self.com_combo.currentText() or '')
                baud_txt = str(self.baud_combo.currentText() or '')
                try:
                    baud_val = int(baud_txt)
                except Exception:
                    baud_val = baud_txt
                con['zaber'] = con.get('zaber', {})
                con['zaber']['PORT'] = port
                con['zaber']['BAUD'] = baud_val
                with open(self.connections_file, 'w', encoding='utf-8') as cf:
                    json.dump(con, cf, indent=2)
            except Exception:
                pass
            # notify listeners (MainWindow) that stages changed unless caller
            # specifically requested no emit. Default behavior keeps existing
            # behavior for external callers.
            try:
                emit = True
                # callers may have set a temporary attribute to suppress emit
                if hasattr(self, '_suppress_emit') and self._suppress_emit:
                    emit = False
                if emit:
                    try:
                        self.stages_changed.emit(self._stages)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    def _on_stage_selected(self, idx):
        if idx < 0:
            return
        # If we're in configure mode and have a staged copy, show staged values
        try:
            if getattr(self, '_configure_mode', False) and getattr(self, '_staged_stages', None) is not None:
                staged = self._staged_stages
                if 0 <= idx < len(staged):
                    s = staged[idx]
                else:
                    # fallback to persisted if index out of range
                    if 0 <= idx < len(getattr(self, '_stages', [])):
                        s = self._stages[idx]
                    else:
                        return
            else:
                if idx < 0 or idx >= len(self._stages):
                    return
                s = self._stages[idx]
        except Exception:
            try:
                s = self._stages[idx]
            except Exception:
                return
        # Populate form fields without emitting change signals. Several widgets
        # are connected to autosave handlers; setting them programmatically
        # would trigger _save_stages and cause the MainWindow to rebuild the
        # MotorStatusPanel (resetting readback values). Block signals here.
        try:
            self.name_edit.blockSignals(True)
            self.model_edit.blockSignals(True)
            self.type_combo.blockSignals(True)
            self.num_spin.blockSignals(True)
            self.abr_edit.blockSignals(True)
            self.desc_edit.blockSignals(True)
            self.com_combo.blockSignals(True)
            self.baud_combo.blockSignals(True)

            self.name_edit.setText(str(s.get('name','')))
            self.model_edit.setText(str(s.get('model_number','')))
            t = s.get('type','Linear')
            if t not in ("Linear","Rotation"):
                t = 'Linear'
            self.type_combo.setCurrentText(t)
            # populate numeric value
            try:
                self.num_spin.setValue(int(s.get('num', 0)))
            except Exception:
                pass
            self.abr_edit.setText(str(s.get('Abr','')))
            self.desc_edit.setPlainText(str(s.get('description','')))
            # limit: use 'limit' field if present; this field is read-only and will be updated
            # from device-reported bounds via set_limit_for_stage
            limit = s.get('limit', '')
            try:
                if limit == '' or limit is None:
                    txt = ''
                else:
                    txt = f"{float(limit):.5g}"
            except Exception:
                txt = str(limit)
            self.limit_edit.setText(txt)
            # populate COM if stored previously
            com = s.get('com', '')
            if com:
                # make sure it's present in combo
                if self.com_combo.findText(com) == -1:
                    self.com_combo.addItem(com)
                self.com_combo.setCurrentText(com)
            # populate baud if present
            baud = s.get('baud', '')
            if baud:
                try:
                    if self.baud_combo.findText(str(baud)) == -1:
                        self.baud_combo.addItem(str(baud))
                    self.baud_combo.setCurrentText(str(baud))
                except Exception:
                    pass
        finally:
            try: self.name_edit.blockSignals(False)
            except Exception: pass
            try: self.model_edit.blockSignals(False)
            except Exception: pass
            try: self.type_combo.blockSignals(False)
            except Exception: pass
            try: self.num_spin.blockSignals(False)
            except Exception: pass
            try: self.abr_edit.blockSignals(False)
            except Exception: pass
            try: self.desc_edit.blockSignals(False)
            except Exception: pass
            try: self.com_combo.blockSignals(False)
            except Exception: pass
            try: self.baud_combo.blockSignals(False)
            except Exception: pass
        # limit: use 'limit' field if present; this field is read-only and will be updated
        # from device-reported bounds via set_limit_for_stage
        limit = s.get('limit', '')
        try:
            if limit == '' or limit is None:
                txt = ''
            else:
                txt = f"{float(limit):.5g}"
        except Exception:
            txt = str(limit)
        self.limit_edit.setText(txt)
        # populate COM if stored previously
        com = s.get('com', '')
        if com:
            # make sure it's present in combo
            if self.com_combo.findText(com) == -1:
                self.com_combo.addItem(com)
            self.com_combo.setCurrentText(com)

    def get_stages(self):
        """Return list of stage dicts loaded from JSON, sorted by num."""
        return getattr(self, '_stages', [])

    def _on_field_changed(self, key: str):
        """When in configure mode, stage edits are applied to a staged copy and saved on Save.
        When not in configure mode, ignore edits and revert UI to persisted values."""
        try:
            if not getattr(self, '_configure_mode', False):
                # ignore edits when not in configure mode; revert UI to persisted
                try:
                    self._on_stage_selected(self.stage_list.currentRow())
                except Exception:
                    pass
                return
            idx = self.stage_list.currentRow()
            if idx < 0:
                return
            # ensure we have a staged copy
            try:
                staged = self._staged_stages
                if staged is None:
                    self._staged_stages = [dict(s) for s in getattr(self, '_stages', [])]
                    staged = self._staged_stages
            except Exception:
                staged = [dict(s) for s in getattr(self, '_stages', [])]
                self._staged_stages = staged

            s = staged[idx]
            try:
                if key == 'name':
                    new_val = self.name_edit.text()
                elif key == 'model_number':
                    new_val = self.model_edit.text()
                elif key == 'type':
                    new_val = self.type_combo.currentText()
                elif key == 'num':
                    try:
                        new_val = int(self.num_spin.value())
                    except Exception:
                        new_val = self.num_spin.value()
                elif key == 'Abr':
                    new_val = self.abr_edit.text()
                elif key == 'description':
                    new_val = self.desc_edit.toPlainText()
                elif key == 'com':
                    new_val = self.com_combo.currentText()
                elif key == 'baud':
                    new_val = self.baud_combo.currentText()
                else:
                    return
            except Exception:
                return

            old_val = s.get(key, '')
            if str(new_val) == str(old_val):
                return
            # stage the change
            try:
                s[key] = new_val
            except Exception:
                pass
            # update list display for name changes
            try:
                if key == 'name':
                    try: self.stage_list.item(idx).setText(str(new_val))
                    except Exception: pass
            except Exception:
                pass
            # mark Save enabled if any differences between staged and persisted
            try:
                if self._staged_stages is not None:
                    changed = False
                    orig = getattr(self, '_stages', [])
                    if len(orig) != len(self._staged_stages):
                        changed = True
                    else:
                        for a, b in zip(orig, self._staged_stages):
                            if a != b:
                                changed = True
                                break
                    self.btn_stage_save.setEnabled(bool(changed))
            except Exception:
                self.btn_stage_save.setEnabled(True)
        except Exception:
            pass

    def _on_baud_changed(self):
        # Store baud choice in currently selected stage record (not the same as connect)
        idx = self.stage_list.currentRow()
        if idx < 0 or idx >= len(getattr(self, '_stages', [])):
            return
        s = self._stages[idx]
        try:
            s['baud'] = int(str(self.baud_combo.currentText()).strip())
            self._save_stages()
        except Exception:
            pass

    def _on_com_changed(self):
        """Handle edits to the COM combo: update the selected stage's 'com' field and persist.
        Also triggers writing the `device_connections.json` via _save_stages().
        """
        try:
            idx = self.stage_list.currentRow()
            if 0 <= idx < len(getattr(self, '_stages', [])):
                s = self._stages[idx]
                try:
                    s['com'] = str(self.com_combo.currentText()).strip()
                except Exception:
                    pass
            # persist stages and device_connections.json
            try:
                self._save_stages()
            except Exception:
                pass
        except Exception:
            pass

    def _on_connect_clicked(self):
        port = str(self.com_combo.currentText() or '').strip()
        try:
            baud = int(str(self.baud_combo.currentText()).strip())
        except Exception:
            baud = 115200
        try:
            self.connectRequested.emit(port, baud)
        except Exception:
            pass

    def set_limit_for_stage(self, num: int, upper: float):
        """Update the 'limit' (upper bound) for the stage with given num.
        This updates the in-memory dict, the visible read-only field (if selected), and persists to disk.
        """
        try:
            # find the stage by its 'num' key
            for i, s in enumerate(self._stages):
                try:
                    if int(s.get('num', -1)) == int(num):
                        s['limit'] = float(upper)
                        # if currently selected, update the visible widget
                        if self.stage_list.currentRow() == i:
                            try:
                                txt = '' if upper is None else f"{float(upper):.5g}"
                            except Exception:
                                txt = str(upper)
                            self.limit_edit.setText(txt)
                        # Device-reported bounds should update in-memory state and the UI,
                        # but should NOT persist to disk or emit a global stages_changed
                        # notification. Persisting/emitting here causes MainWindow to
                        # rebuild panels (resetting scroll/selection and displayed values)
                        # whenever bounds are read from hardware. Leave persistence to
                        # explicit user edits via the DeviceTabs UI.
                        break
                except Exception:
                    continue
        except Exception:
            pass

    def _on_stage_save_clicked(self):
        """Show a confirmation dialog summarizing staged changes before saving.
        If the user confirms, commit staged changes to the persisted stages file.
        """
        try:
            # If there is no staged copy, just save and close configure mode
            if not getattr(self, '_staged_stages', None):
                try:
                    self._save_stages()
                except Exception:
                    pass
                # exit configure mode and clear staged state
                try:
                    self._staged_stages = None
                    self._configure_mode = False
                    # make fields read-only/disabled again
                    self.name_edit.setReadOnly(True)
                    self.model_edit.setReadOnly(True)
                    self.type_combo.setEnabled(False)
                    self.num_spin.setEnabled(False)
                    self.abr_edit.setReadOnly(True)
                    self.desc_edit.setReadOnly(True)
                    self.com_combo.setEnabled(False)
                    self.baud_combo.setEnabled(False)
                    self.btn_stage_add.setEnabled(False)
                    self.btn_stage_remove.setEnabled(False)
                    self.btn_stage_save.setEnabled(False)
                    try:
                        self.btn_stage_configure.setText('Configure')
                    except Exception:
                        pass
                except Exception:
                    pass
                return

            orig = getattr(self, '_stages', []) or []
            staged = self._staged_stages or []

            # Build a human-readable summary of differences
            lines = []
            try:
                if len(orig) != len(staged):
                    lines.append(f"Original count: {len(orig)}, Staged count: {len(staged)}")
                # check for per-item differences by index
                common = min(len(orig), len(staged))
                for i in range(common):
                    a = orig[i]
                    b = staged[i]
                    diffs = []
                    # union of keys
                    for k in sorted(set(list(a.keys()) + list(b.keys()))):
                        va = a.get(k, '')
                        vb = b.get(k, '')
                        if str(va) != str(vb):
                            diffs.append(f"{k}: '{va}' -> '{vb}'")
                    if diffs:
                        lines.append(f"[{i}] {a.get('name','')} changes:")
                        for d in diffs:
                            lines.append(f"  - {d}")
                # added entries
                if len(staged) > len(orig):
                    for i in range(len(orig), len(staged)):
                        lines.append(f"[+] Added [{i}] {staged[i].get('name','(unnamed)')}")
                # removed entries
                if len(orig) > len(staged):
                    for i in range(len(staged), len(orig)):
                        lines.append(f"[-] Removed [{i}] {orig[i].get('name','(unnamed)')}")
            except Exception:
                lines.append("(Could not compute detailed diff)")

            summary = "\n".join(lines) if lines else "No changes detected."

            # Ask the user to confirm; put the detailed diff into the detailed text
            try:
                msg = QtWidgets.QMessageBox(self)
                msg.setIcon(QtWidgets.QMessageBox.Icon.Question)
                msg.setWindowTitle("Confirm Save")
                msg.setText("Save staged changes to stages.json?")
                msg.setInformativeText("Press Yes to write the changes to disk, or Cancel to return to Configure mode.")
                msg.setDetailedText(summary)
                msg.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel)
                res = msg.exec()
            except Exception:
                # fallback to a simpler dialog
                res = QtWidgets.QMessageBox.StandardButton.Yes

            if res == QtWidgets.QMessageBox.StandardButton.Yes:
                try:
                    # commit staged copy to the persisted list
                    self._stages = [dict(s) for s in staged]
                except Exception:
                    pass
                try:
                    # perform actual write
                    # suppress extra emit if caller wants it, but default is to emit
                    if hasattr(self, '_suppress_emit'):
                        prev = self._suppress_emit
                    else:
                        prev = False
                    try:
                        self._save_stages()
                    finally:
                        # restore flag if present
                        if hasattr(self, '_suppress_emit'):
                            self._suppress_emit = prev
                except Exception:
                    pass

                # exit configure mode and clear staged state
                try:
                    self._staged_stages = None
                    self._configure_mode = False
                    # make fields read-only/disabled again
                    self.name_edit.setReadOnly(True)
                    self.model_edit.setReadOnly(True)
                    self.type_combo.setEnabled(False)
                    self.num_spin.setEnabled(False)
                    self.abr_edit.setReadOnly(True)
                    self.desc_edit.setReadOnly(True)
                    self.com_combo.setEnabled(False)
                    self.baud_combo.setEnabled(False)
                    self.btn_stage_add.setEnabled(False)
                    self.btn_stage_remove.setEnabled(False)
                    self.btn_stage_save.setEnabled(False)
                    try:
                        self.btn_stage_configure.setText('Configure')
                    except Exception:
                        pass
                except Exception:
                    pass
            else:
                # user cancelled: keep staged edits and remain in configure mode
                try:
                    # ensure Save stays enabled since there are staged changes
                    self.btn_stage_save.setEnabled(True)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_stage_configure_clicked(self):
        """Toggle configure mode. When entering configure mode create a staged copy.
        When leaving configure mode (without Save), discard staged changes.
        """
        try:
            # toggle mode
            cur = bool(getattr(self, '_configure_mode', False))
            new = not cur
            self._configure_mode = new
            if new:
                # entering configure mode: create staged copy from current persisted stages
                try:
                    self._staged_stages = [dict(s) for s in getattr(self, '_stages', [])]
                except Exception:
                    self._staged_stages = [dict(s) for s in getattr(self, '_stages', [])]
                # enable editing controls
                try:
                    self.name_edit.setReadOnly(False)
                    self.model_edit.setReadOnly(False)
                    self.type_combo.setEnabled(True)
                    self.num_spin.setEnabled(True)
                    self.abr_edit.setReadOnly(False)
                    self.desc_edit.setReadOnly(False)
                    self.com_combo.setEnabled(True)
                    self.baud_combo.setEnabled(True)
                    self.btn_stage_add.setEnabled(True)
                    self.btn_stage_remove.setEnabled(True)
                    # keep Save disabled until a change is made
                    self.btn_stage_save.setEnabled(False)
                except Exception:
                    pass
                # update Configure button appearance
                try:
                    self.btn_stage_configure.setText('Cancel')
                except Exception:
                    pass
            else:
                # leaving configure mode without saving: discard staged changes
                try:
                    self._staged_stages = None
                except Exception:
                    pass
                # disable editing controls
                try:
                    self.name_edit.setReadOnly(True)
                    self.model_edit.setReadOnly(True)
                    self.type_combo.setEnabled(False)
                    self.num_spin.setEnabled(False)
                    self.abr_edit.setReadOnly(True)
                    self.desc_edit.setReadOnly(True)
                    self.com_combo.setEnabled(False)
                    self.baud_combo.setEnabled(False)
                    self.btn_stage_add.setEnabled(False)
                    self.btn_stage_remove.setEnabled(False)
                    self.btn_stage_save.setEnabled(False)
                except Exception:
                    pass
                # restore Configure button appearance
                try:
                    self.btn_stage_configure.setText('Configure')
                except Exception:
                    pass
                # refresh UI to persisted values
                try:
                    self._on_stage_selected(self.stage_list.currentRow())
                except Exception:
                    pass
        except Exception:
            pass

    def _on_stage_add(self):
        """Add a new blank staged stage when in configure mode."""
        try:
            if not getattr(self, '_configure_mode', False):
                return
            # ensure staged list exists
            try:
                if self._staged_stages is None:
                    self._staged_stages = [dict(s) for s in getattr(self, '_stages', [])]
            except Exception:
                self._staged_stages = [dict(s) for s in getattr(self, '_stages', [])]
            # create a blank stage with sensible defaults
            new_stage = {'name': 'New Stage', 'model_number': '', 'type': 'Linear', 'num': 0, 'Abr': '', 'description': '', 'limit': '', 'com': '', 'baud': ''}
            self._staged_stages.append(new_stage)
            # update list widget
            try:
                self.stage_list.addItem(new_stage.get('name',''))
                self.stage_list.setCurrentRow(self.stage_list.count()-1)
            except Exception:
                pass
            # mark Save enabled
            try:
                self.btn_stage_save.setEnabled(True)
            except Exception:
                pass
        except Exception:
            pass

    def _on_stage_remove(self):
        """Remove the currently selected staged stage when in configure mode."""
        try:
            if not getattr(self, '_configure_mode', False):
                return
            idx = self.stage_list.currentRow()
            if idx < 0:
                return
            try:
                # ensure staged exists
                if self._staged_stages is None:
                    self._staged_stages = [dict(s) for s in getattr(self, '_stages', [])]
            except Exception:
                self._staged_stages = [dict(s) for s in getattr(self, '_stages', [])]
            # remove from staged and list widget
            try:
                if 0 <= idx < len(self._staged_stages):
                    del self._staged_stages[idx]
                self.stage_list.takeItem(idx)
                # select a sensible nearby index
                new_idx = min(idx, self.stage_list.count()-1)
                if new_idx >= 0:
                    self.stage_list.setCurrentRow(new_idx)
            except Exception:
                pass
            # enable Save since staged changed
            try:
                self.btn_stage_save.setEnabled(True)
            except Exception:
                pass
        except Exception:
            pass

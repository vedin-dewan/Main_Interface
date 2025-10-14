from PyQt6 import QtWidgets, QtCore
import os, json

class DeviceTabsPanel(QtWidgets.QWidget):
    """Left-side panel with tabs: Zaber Stages, Cameras, Spectrometers, Picomotors.
    The Zaber Stages tab is populated from parameters/stages.json.
    """
    def __init__(self, stages_file=None, parent=None):
        super().__init__(parent)
        self.stages_file = stages_file or os.path.join(os.path.dirname(__file__), '..', 'parameters', 'stages.json')
        self._build_ui()
        self._load_stages()

    # emit when stages.json is changed by the UI (provides the new list of stage dicts)
    stages_changed = QtCore.pyqtSignal(list)

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

        # -- build stages tab layout --
        s_layout = QtWidgets.QHBoxLayout(self.tab_stages)

        # left: list of stages
        self.stage_list = QtWidgets.QListWidget()
        self.stage_list.setFixedWidth(200)
        s_layout.addWidget(self.stage_list)

        # right: detail form
        form = QtWidgets.QFormLayout()
        right = QtWidgets.QWidget()
        right.setLayout(form)
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

        # COM port selector combo (for Zaber stages)
        self.com_combo = QtWidgets.QComboBox()
        self.com_combo.setEditable(True)
        # populate with common ports
        self.com_combo.addItems(["COM1","COM2","COM3","COM4","/dev/ttyUSB0","/dev/ttyUSB1","/dev/tty.usbserial-0001"])
        form.addRow("COM", self.com_combo)

        # connect selection change
        self.stage_list.currentRowChanged.connect(self._on_stage_selected)

        # connect editing signals to autosave handlers
        self.name_edit.editingFinished.connect(lambda: self._on_field_changed('name'))
        self.model_edit.editingFinished.connect(lambda: self._on_field_changed('model_number'))
        self.type_combo.currentTextChanged.connect(lambda _: self._on_field_changed('type'))
        self.num_spin.valueChanged.connect(lambda _: self._on_field_changed('num'))
        self.abr_edit.editingFinished.connect(lambda: self._on_field_changed('Abr'))
        # QPlainTextEdit has no editingFinished, use focusOutEvent based commit via textChanged debounce
        self.desc_edit.textChanged.connect(lambda: self._on_field_changed('description'))
        self.com_combo.editTextChanged.connect(lambda _: self._on_field_changed('com'))

    def _load_stages(self):
        try:
            with open(self.stages_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = []
        # sort by 'num'
        data = sorted(data, key=lambda s: s.get('num', 0))
        self._stages = data
        self.stage_list.clear()
        for s in data:
            self.stage_list.addItem(s.get('name',''))
        if data:
            self.stage_list.setCurrentRow(0)

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
            # notify listeners (MainWindow) that stages changed
            try:
                self.stages_changed.emit(self._stages)
            except Exception:
                pass
        except Exception:
            pass

    def _on_stage_selected(self, idx):
        if idx < 0 or idx >= len(self._stages):
            return
        s = self._stages[idx]
        self.name_edit.setText(str(s.get('name','')))
        self.model_edit.setText(str(s.get('model_number','')))
        t = s.get('type','Linear')
        if t not in ("Linear","Rotation"):
            t = 'Linear'
        self.type_combo.setCurrentText(t)
        # populate numeric value
        try:
            self.num_spin.blockSignals(True)
            self.num_spin.setValue(int(s.get('num', 0)))
        finally:
            self.num_spin.blockSignals(False)
        self.abr_edit.setText(str(s.get('Abr','')))
        self.desc_edit.blockSignals(True)
        self.desc_edit.setPlainText(str(s.get('description','')))
        self.desc_edit.blockSignals(False)
        # limit: use 'limit' field if present; this field is read-only and will be updated
        # from device-reported bounds via set_limit_for_stage
        limit = s.get('limit', '')
        self.limit_edit.setText(str(limit))
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
        """Generic handler when a field is edited for the currently selected stage.
        Updates the in-memory dict and persists to disk.
        """
        idx = self.stage_list.currentRow()
        if idx < 0 or idx >= len(getattr(self, '_stages', [])):
            return
        s = self._stages[idx]
        try:
            if key == 'name':
                s['name'] = self.name_edit.text()
            elif key == 'model_number':
                s['model_number'] = self.model_edit.text()
            elif key == 'type':
                s['type'] = self.type_combo.currentText()
            elif key == 'num':
                # spinbox is int
                s['num'] = int(self.num_spin.value())
            elif key == 'Abr':
                s['Abr'] = self.abr_edit.text()
            elif key == 'description':
                s['description'] = self.desc_edit.toPlainText()
            elif key == 'com':
                s['com'] = self.com_combo.currentText()
            # refresh visible list label if name changed
            try:
                self.stage_list.item(idx).setText(s.get('name',''))
            except Exception:
                pass
            # after edits, make sure stages are kept sorted by num in memory and on-disk
            try:
                self._stages = sorted(self._stages, key=lambda x: int(x.get('num', 0)))
            except Exception:
                pass
            self._save_stages()
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
                            self.limit_edit.setText(str(upper))
                        # persist immediately
                        self._save_stages()
                        break
                except Exception:
                    continue
        except Exception:
            pass

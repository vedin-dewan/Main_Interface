from PyQt6 import QtWidgets, QtCore
from widgets.round_light import RoundLight
import typing
import os
import json


class PicoMotorRow(QtWidgets.QWidget):
    def __init__(self, addr: int, parent=None):
        super().__init__(parent)
        self.addr = int(addr)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(2,2,2,2)
        # address spin + name edit + position label
        self.spin = QtWidgets.QSpinBox(); self.spin.setRange(0, 9999); self.spin.setFixedWidth(50)
        self.spin.setValue(int(addr))
        self.name = QtWidgets.QLineEdit('')
        self.pos = QtWidgets.QLineEdit('0'); self.pos.setReadOnly(True); self.pos.setFixedWidth(90)
        h.addWidget(self.spin)
        h.addWidget(self.name)
        h.addStretch()
        h.addWidget(QtWidgets.QLabel('Position:'))
        h.addWidget(self.pos)


class PicoPanel(QtWidgets.QWidget):
    """UI for Picomotors tab: controller selector, motor list, relative jog and stop."""

    request_open = QtCore.pyqtSignal()
    request_close = QtCore.pyqtSignal()
    request_move = QtCore.pyqtSignal(str, int, int, int)  # adapter_key, address, axis, steps
    request_stop_all = QtCore.pyqtSignal()
    request_query_position = QtCore.pyqtSignal(str, int, int)  # adapter_key, address, axis

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)

        # Selected Controller
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel('Selected Controller:'))
        self.controller_combo = QtWidgets.QComboBox()
        self.controller_combo.setEditable(False)
        # make combo shorter so the dropdown arrow is visible but still readable
        self.controller_combo.setMinimumWidth(240)
        self.controller_combo.setMaximumWidth(480)
        top.addWidget(self.controller_combo)
        # allow setting axis count per-controller
        self.axis_count_spin = QtWidgets.QSpinBox()
        self.axis_count_spin.setRange(1, 16)
        self.axis_count_spin.setValue(4)
        self.axis_count_spin.setFixedWidth(80)
        top.addWidget(QtWidgets.QLabel('Axes:'))
        top.addWidget(self.axis_count_spin)
        v.addLayout(top)

        # Motor rows (scroll area)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QtWidgets.QWidget()
        self.inner_layout = QtWidgets.QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(2, 2, 2, 2)
        # start with an empty stretch so insertWidget(index-1) works
        self.inner_layout.addStretch()
        self.scroll.setWidget(self.inner)
        v.addWidget(self.scroll, 1)

        # Selected motor controls
        mid = QtWidgets.QHBoxLayout()
        mid.addWidget(QtWidgets.QLabel('Selected Motor:'))
        self.motor_selector = QtWidgets.QComboBox()
        self.motor_selector.setFixedWidth(60)
        mid.addWidget(self.motor_selector)
        self.light = RoundLight(14, '#22cc66', '#2b2b2b')
        mid.addWidget(self.light)
        self.btn_stop = QtWidgets.QPushButton('Stop')
        self.btn_stop.setStyleSheet('background:#7a2f2e; color:white;')
        mid.addWidget(self.btn_stop)
        mid.addStretch()
        v.addLayout(mid)

        # Relative move row
        jog = QtWidgets.QHBoxLayout()
        self.btn_back = QtWidgets.QPushButton('Back')
        self.step_edit = QtWidgets.QLineEdit('0')
        self.step_edit.setFixedWidth(80)
        self.btn_forward = QtWidgets.QPushButton('Forward')
        jog.addStretch()
        jog.addWidget(self.btn_back)
        jog.addWidget(self.step_edit)
        jog.addWidget(self.btn_forward)
        jog.addStretch()
        v.addLayout(jog)

        # Status text area
        self.status = QtWidgets.QPlainTextEdit()
        self.status.setReadOnly(True)
        self.status.setFixedHeight(120)
        v.addWidget(self.status)

        # connections (Open/Close are handled by MainWindow lifecycle now)
        # keep signals for compatibility if other code emits them
        self.btn_back.clicked.connect(self._on_back)
        self.btn_forward.clicked.connect(self._on_forward)
        self.btn_stop.clicked.connect(lambda: self.request_stop_all.emit())
        # update axis rows whenever axis-count changes
        self.axis_count_spin.valueChanged.connect(lambda v: self._on_controller_changed(self.controller_combo.currentIndex()))
    # No periodic polling: position queries are requested by the IO after moves.


        # internal state
        # controllers: list of tuples (adapter_key, address, model_serial)
        self._controllers = []
        self._last_mapping = {}
        # mapping (adapter_key, address, axis) -> PicoMotorRow widget for live updates
        self._axis_widgets = {}

        # load persisted axis names
        self._load_axis_names()
    def set_controllers(self, controllers: typing.List[str]):
        # controllers here may be adapter_key strings; clear the combo and add as-is
        self._controllers = []
        self.controller_combo.blockSignals(True)
        self.controller_combo.clear()
        for c in (controllers or []):
            self.controller_combo.addItem(str(c), c)
            self._controllers.append((c, 1, ''))
        self.controller_combo.blockSignals(False)

    def set_discovered_items(self, items: typing.List[dict]):
        """Populate controller dropdown with 'Model Serial (Address n)' entries and motor selector with addresses.
        items: list of dicts {'adapter_key','address','model_serial'}
        """
        try:
            # build mapping adapter_key -> list of (address, model_serial)
            mapping = {}
            for it in items or []:
                key = str(it.get('adapter_key') or '')
                addr = int(it.get('address') or 0)
                ms = str(it.get('model_serial') or '')
                mapping.setdefault(key, []).append((addr, ms))

            # populate controller combo with one entry per address (primary + slaves).
            # Store userData as a tuple (adapter_key, address) so each row maps to
            # a concrete controller address.
            entries = []
            for k, addrs in mapping.items():
                for a, ms in addrs:
                    entries.append((k, int(a), ms))

            # sort entries by adapter key then address
            entries.sort(key=lambda x: (str(x[0]), int(x[1])))

            self.controller_combo.blockSignals(True)
            self.controller_combo.clear()
            for k, a, ms in entries:
                label = f"{ms} (Address {a})" if ms else f"Address {a}"
                # userData is (adapter_key, address)
                self.controller_combo.addItem(label, (k, int(a)))
            self.controller_combo.blockSignals(False)

            # keep mapping for backward-compatible lookups
            self._last_mapping = mapping
            # initialize UI for first controller if present
            self._refresh_motor_selector_for_current_controller()
            # ensure changes to controller selection update the axis rows
            try:
                self.controller_combo.currentIndexChanged.disconnect(self._on_controller_changed)
            except Exception:
                pass
            self.controller_combo.currentIndexChanged.connect(self._on_controller_changed)
            # restore axis_count per controller if present in persisted file
            try:
                # load persisted per-controller axis counts
                p = self._axis_counts_path()
                if os.path.isfile(p):
                    with open(p, 'r', encoding='utf-8') as f:
                        self._axis_counts = json.load(f)
                else:
                    self._axis_counts = {}
            except Exception:
                self._axis_counts = {}
        except Exception:
            pass

    # persistence for axis names
    def _axis_names_path(self) -> str:
        return os.path.join(os.path.expanduser('~'), '.plasmamirrors_pico_axis_names.json')

    def _axis_counts_path(self) -> str:
        return os.path.join(os.path.expanduser('~'), '.plasmamirrors_pico_axis_counts.json')

    def _load_axis_names(self):
        self._axis_names = {}
        try:
            p = self._axis_names_path()
            if os.path.isfile(p):
                with open(p, 'r', encoding='utf-8') as f:
                    self._axis_names = json.load(f)
            # ensure keys as tuples when used
            newmap = {}
            for k, v in (self._axis_names or {}).items():
                try:
                    parts = k.split('|')
                    newmap[(parts[0], int(parts[1]), int(parts[2]))] = v
                except Exception:
                    continue
            self._axis_names = newmap
        except Exception:
            self._axis_names = {}

    def _save_axis_names(self):
        try:
            out = {}
            for (k, addr, axis), name in (getattr(self, '_axis_names', {}) or {}).items():
                out_key = f"{k}|{addr}|{axis}"
                out[out_key] = name
            p = self._axis_names_path()
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(out, f, indent=2)
        except Exception:
            pass

    # helper to clear a layout completely (widgets and spacers)
    def _clear_layout(self, layout: QtWidgets.QLayout):
        try:
            while layout.count():
                item = layout.takeAt(layout.count() - 1)
                if item is None:
                    continue
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                else:
                    # spacer or layout - nothing to widget-parent, but ensure child layout cleared
                    sub = item.layout()
                    if sub is not None:
                        self._clear_layout(sub)
        except Exception:
            pass

    def _refresh_motor_selector_for_current_controller(self):
        try:
            self.motor_selector.blockSignals(True)
            self.motor_selector.clear()
            data = self.controller_combo.currentData()
            # New behavior: controller combo itemData is (adapter_key, address)
            if isinstance(data, (list, tuple)) and len(data) >= 2:
                try:
                    # populate axes (1..N) for selected controller using axis_count_spin
                    axis_count = int(self.axis_count_spin.value() if hasattr(self, 'axis_count_spin') else 4)
                    for axis in range(1, axis_count + 1):
                        self.motor_selector.addItem(str(axis), axis)
                    # also populate the axis rows area
                    adapter = str(data[0])
                    addr = int(data[1])
                    self._populate_axis_rows(adapter, addr, axis_count=axis_count)
                except Exception:
                    pass
                self.motor_selector.blockSignals(False)
                return

            # Backwards-compatible: data may be adapter_key string; populate all addresses
            key = data
            if not key:
                self.motor_selector.blockSignals(False)
                return
            addrs = self._last_mapping.get(key, [])
            for a, ms in sorted(addrs, key=lambda x: int(x[0])):
                self.motor_selector.addItem(str(a), a)
            self.motor_selector.blockSignals(False)
        except Exception:
            pass

    def _on_controller_changed(self, idx: int):
        try:
            # update axis_count spin based on persisted per-controller value if available
            try:
                data = self.controller_combo.itemData(idx)
                if isinstance(data, (list, tuple)) and len(data) >= 2:
                    ak = str(data[0]); addr = int(data[1])
                    key = f"{ak}|{addr}"
                    if getattr(self, '_axis_counts', None) and key in self._axis_counts:
                        try:
                            self.axis_count_spin.blockSignals(True)
                            self.axis_count_spin.setValue(int(self._axis_counts.get(key, int(self.axis_count_spin.value()))))
                            self.axis_count_spin.blockSignals(False)
                        except Exception:
                            pass
            except Exception:
                pass
            self._refresh_motor_selector_for_current_controller()
        except Exception:
            pass

    def set_motor_rows(self, rows: typing.List[dict]):
        # rows: list of { 'adapter_key', 'address', 'model_serial' }
        # clear existing rows
        # clear everything including stretches/spacers
        self._clear_layout(self.inner_layout)
        for r in rows:
            pr = PicoMotorRow(r.get('address', 0))
            pr.name.setText(str(r.get('model_serial','')))
            self.inner_layout.insertWidget(self.inner_layout.count()-1, pr)
        self.inner_layout.addStretch()

    def _populate_axis_rows(self, adapter_key: str, address: int, axis_count: int = 4):
        """Create axis rows (1..axis_count) for the selected adapter/address.
        Axis names are editable and stored in self._axis_names mapping.
        """
        # clear existing rows and spacers
        self._clear_layout(self.inner_layout)
        # reset mapping for axis widgets
        try:
            self._axis_widgets = {}
        except Exception:
            pass
        # add rows for each axis
        for axis in range(1, int(axis_count) + 1):
            pr = PicoMotorRow(axis)
            # axis spin is for display only
            try:
                pr.spin.setValue(int(axis))
                pr.spin.setEnabled(False)
            except Exception:
                pass
            # name: use stored name if present
            name = self._axis_names.get((adapter_key, int(address), int(axis))) if hasattr(self, '_axis_names') else None
            if not name:
                name = f'Axis {axis}'
            pr.name.setText(str(name))
            # connect name edits to save mapping
            def _make_on_name_change(a_key, a_addr, a_axis, widget):
                def _on_name_changed(txt):
                    try:
                        if not hasattr(self, '_axis_names'):
                            self._axis_names = {}
                        self._axis_names[(a_key, int(a_addr), int(a_axis))] = str(txt)
                    except Exception:
                        pass
                return _on_name_changed

            pr.name.textChanged.connect(_make_on_name_change(adapter_key, address, axis, pr.name))
            # save name immediately
            pr.name.textChanged.connect(lambda txt, a_key=adapter_key, a_addr=address, a_axis=axis: (self._axis_names.__setitem__((a_key, int(a_addr), int(a_axis)), str(txt)), self._save_axis_names()))
            # store widget mapping for live updates
            try:
                self._axis_widgets[(str(adapter_key), int(address), int(axis))] = pr
            except Exception:
                pass
            self.inner_layout.insertWidget(self.inner_layout.count()-1, pr)
        self.inner_layout.addStretch()
        # persist the axis_count for this controller
        try:
            key = f"{adapter_key}|{int(address)}"
            self._axis_counts[key] = int(axis_count)
            p = self._axis_counts_path()
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(self._axis_counts, f, indent=2)
        except Exception:
            pass

    @QtCore.pyqtSlot(str, int, int, float)
    def position_update(self, adapter_key: str, address: int, axis: int, value: float):
        """Slot to receive position updates from the Pico IO worker and update axis rows."""
        try:
            key = (str(adapter_key), int(address), int(axis))
            pr = self._axis_widgets.get(key)
            if pr is not None:
                try:
                    # format with moderate precision
                    pr.pos.setText(f"{float(value):.6f}")
                except Exception:
                    pr.pos.setText(str(value))
        except Exception:
            pass

    def _on_back(self):
        try:
            steps = int(self.step_edit.text())
        except Exception:
            steps = 0
        # negative step
        # Determine adapter_key and address. Prefer controller_combo userData shape (adapter,addr)
        adapter = None
        addr = None
        try:
            cdata = self.controller_combo.currentData()
            if isinstance(cdata, (list, tuple)) and len(cdata) >= 2:
                adapter = str(cdata[0])
                addr = int(cdata[1])
            else:
                adapter = str(cdata or self.controller_combo.currentText())
        except Exception:
            adapter = str(self.controller_combo.currentText() or '')

        # address fallback to motor_selector if not present in controller combo
        if addr is None:
            try:
                data = self.motor_selector.currentData()
                if data is None:
                    addr = int(self.motor_selector.currentText() or 1)
                else:
                    addr = int(data)
            except Exception:
                addr = 1
        axis = 1
        self.request_move.emit(adapter, int(addr), int(axis), -int(steps))

    def _on_forward(self):
        try:
            steps = int(self.step_edit.text())
        except Exception:
            steps = 0
        adapter = None
        addr = None
        try:
            cdata = self.controller_combo.currentData()
            if isinstance(cdata, (list, tuple)) and len(cdata) >= 2:
                adapter = str(cdata[0])
                addr = int(cdata[1])
            else:
                adapter = str(cdata or self.controller_combo.currentText())
        except Exception:
            adapter = str(self.controller_combo.currentText() or '')

        if addr is None:
            try:
                data = self.motor_selector.currentData()
                if data is None:
                    addr = int(self.motor_selector.currentText() or 1)
                else:
                    addr = int(data)
            except Exception:
                addr = 1
        axis = 1
        self.request_move.emit(adapter, int(addr), int(axis), int(steps))

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
        # axis number label + name edit + position label
        self.spin = QtWidgets.QLabel(str(addr))
        self.spin.setFixedWidth(40)
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
    # position queries are handled locally by the UI based on relative moves

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
        self.motor_selector.setFixedWidth(80)
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

        # connections
        self.btn_back.clicked.connect(self._on_back)
        self.btn_forward.clicked.connect(self._on_forward)
        self.btn_stop.clicked.connect(lambda: self.request_stop_all.emit())

        # No periodic polling: UI tracks positions locally and updates on move events.

        # internal state
        # mapping (adapter_key, address, axis) -> PicoMotorRow widget for live updates
        self._axis_widgets = {}

        # persisted names file in parameters/pico_names.json
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._names_file = os.path.join(base_dir, 'parameters', 'pico_names.json')
        self._axis_names = {}
        # load persisted axis names
        self._load_axis_names()
        # position cache: start at zero for all axes when created
        self._pos_cache = {}
        # pending moves mapping: (adapter,addr,axis) -> pending delta (int)
        self._pending_moves = {}
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

            # sort entries by adapter key then numeric address
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
            # populate combo now (entries already sorted by address)
            self.controller_combo.blockSignals(True)
            self.controller_combo.clear()
            for k, a, ms in entries:
                label = f"{ms} (Address {a})" if ms else f"Address {a}"
                self.controller_combo.addItem(label, (k, int(a)))
            self.controller_combo.blockSignals(False)
            # refresh UI for first controller if present
            self._refresh_motor_selector_for_current_controller()
            # log discovery
            try:
                self.append_line(f"Discovered Devices: {len(entries)}")
            except Exception:
                pass
            # ensure changes to controller selection update the axis rows
            try:
                self.controller_combo.currentIndexChanged.disconnect(self._on_controller_changed)
            except Exception:
                pass
            self.controller_combo.currentIndexChanged.connect(self._on_controller_changed)
        except Exception:
            pass

    # persistence for axis names
    def _axis_names_path(self) -> str:
        return self._names_file

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
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(out, f, indent=2)
        except Exception:
            pass

    def append_line(self, txt: str):
        try:
            self.status.appendPlainText(str(txt))
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
            data = self.controller_combo.currentData()
            if isinstance(data, (list, tuple)) and len(data) >= 2:
                try:
                    adapter = str(data[0])
                    addr = int(data[1])
                    self._populate_axis_rows(adapter, addr, axis_count=4)
                    try:
                        self.current_axis_label.setText('1')
                    except Exception:
                        pass
                except Exception:
                    pass
                return
            # fallback: do nothing
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
        for axis in range(1, 5):
            pr = PicoMotorRow(axis)
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
                        self._save_axis_names()
                    except Exception:
                        pass
                return _on_name_changed

            pr.name.textChanged.connect(_make_on_name_change(adapter_key, address, axis, pr.name))
            # initialize position to zero in cache and widget
            try:
                self._pos_cache[(str(adapter_key), int(address), int(axis))] = 0.0
                pr.pos.setText(f"{0.0:.6f}")
            except Exception:
                pass
            # store widget mapping for updates
            try:
                self._axis_widgets[(str(adapter_key), int(address), int(axis))] = pr
            except Exception:
                pass
            self.inner_layout.insertWidget(self.inner_layout.count()-1, pr)
        self.inner_layout.addStretch()
        # save names file after populating
        try:
            self._save_axis_names()
        except Exception:
            pass

    @QtCore.pyqtSlot(str, int, int)
    def _on_io_moved(self, adapter_key: str, address: int, axis: int):
        """Handle moved signal from IO: apply pending delta to cached position and update display."""
        try:
            key = (str(adapter_key), int(address), int(axis))
            delta = 0
            try:
                delta = int(self._pending_moves.pop(key, 0))
            except Exception:
                delta = 0
            try:
                cur = float(self._pos_cache.get(key, 0.0) or 0.0)
            except Exception:
                cur = 0.0
            try:
                new = float(cur + float(delta))
            except Exception:
                new = cur
            # update cache and widget
            try:
                self._pos_cache[key] = float(new)
                pr = self._axis_widgets.get(key)
                if pr is not None:
                    pr.pos.setText(f"{float(new):.6f}")
                # append an explicit move-complete message to the picomotors status area
                try:
                    # format delta with sign
                    try:
                        delta_int = int(delta)
                    except Exception:
                        delta_int = 0
                    delta_str = f"{delta_int:+d}"
                    # format new position: prefer integer if whole, otherwise 6-decimal float
                    try:
                        if float(new).is_integer():
                            new_str = str(int(float(new)))
                        else:
                            new_str = f"{float(new):.6f}"
                    except Exception:
                        new_str = f"{float(new):.6f}"
                    self.append_line(f"Move complete: Address {int(address)} Axis {int(axis)} \u2206={delta_str} steps — new pos {new_str}")
                except Exception:
                    pass
            except Exception:
                pass
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

        # address fallback to controller combo text if not present in controller combo data
        if addr is None:
            try:
                addr = int(self.controller_combo.currentText() or 1)
            except Exception:
                addr = 1
        try:
            axis = int(self.motor_selector.currentData() or self.motor_selector.currentText() or 1)
        except Exception:
            axis = 1
        delta = -int(steps)
        try:
            self._pending_moves[(str(adapter), int(addr), int(axis))] = int(delta)
        except Exception:
            pass
        self.request_move.emit(adapter, int(addr), int(axis), int(delta))

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
                addr = int(self.controller_combo.currentText() or 1)
            except Exception:
                addr = 1
        try:
            axis = int(self.motor_selector.currentData() or self.motor_selector.currentText() or 1)
        except Exception:
            axis = 1
        delta = int(steps)
        try:
            self._pending_moves[(str(adapter), int(addr), int(axis))] = int(delta)
        except Exception:
            pass
        self.request_move.emit(adapter, int(addr), int(axis), int(delta))

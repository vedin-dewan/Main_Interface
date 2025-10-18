from PyQt6 import QtWidgets, QtCore
from widgets.round_light import RoundLight
import typing


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

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(6,6,6,6)

        # Selected Controller
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel('Selected Controller:'))
        self.controller_combo = QtWidgets.QComboBox()
        self.controller_combo.setEditable(False)
        top.addWidget(self.controller_combo)
        self.btn_open = QtWidgets.QPushButton('Open')
        self.btn_close = QtWidgets.QPushButton('Close')
        top.addWidget(self.btn_open)
        top.addWidget(self.btn_close)
        v.addLayout(top)

        # Motor rows (scroll area)
        self.scroll = QtWidgets.QScrollArea(); self.scroll.setWidgetResizable(True)
        self.inner = QtWidgets.QWidget()
        self.inner_layout = QtWidgets.QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(2,2,2,2)
        self.inner_layout.addStretch()
        self.scroll.setWidget(self.inner)
        v.addWidget(self.scroll, 1)

        # Selected motor controls
        mid = QtWidgets.QHBoxLayout()
        mid.addWidget(QtWidgets.QLabel('Selected Motor:'))
        self.motor_selector = QtWidgets.QComboBox(); self.motor_selector.setFixedWidth(50)
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
        self.step_edit = QtWidgets.QLineEdit('0'); self.step_edit.setFixedWidth(80)
        self.btn_forward = QtWidgets.QPushButton('Forward')
        jog.addStretch()
        jog.addWidget(self.btn_back)
        jog.addWidget(self.step_edit)
        jog.addWidget(self.btn_forward)
        jog.addStretch()
        v.addLayout(jog)

        # Status text area
        self.status = QtWidgets.QPlainTextEdit(); self.status.setReadOnly(True); self.status.setFixedHeight(120)
        v.addWidget(self.status)

        # connections
        self.btn_open.clicked.connect(lambda: self.request_open.emit())
        self.btn_close.clicked.connect(lambda: self.request_close.emit())
        self.btn_back.clicked.connect(self._on_back)
        self.btn_forward.clicked.connect(self._on_forward)
        self.btn_stop.clicked.connect(lambda: self.request_stop_all.emit())

        # internal state
        # controllers: list of tuples (adapter_key, address, model_serial)
        self._controllers = []
        self._last_mapping = {}

    def append_status(self, txt: str):
        try:
            self.status.appendPlainText(str(txt))
        except Exception:
            pass

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

            # populate controller combo with one entry per adapter key (show primary + count)
            self.controller_combo.blockSignals(True)
            self.controller_combo.clear()
            for k, addrs in mapping.items():
                # find primary 1 entry label if present
                labels = []
                for a, ms in sorted(addrs, key=lambda x: int(x[0])):
                    labels.append(f"{ms} (Address {a})")
                label = ", ".join(labels)
                self.controller_combo.addItem(label, k)
            self.controller_combo.blockSignals(False)

            # populate motor_selector with addresses for currently selected controller
            self._last_mapping = mapping
            self._refresh_motor_selector_for_current_controller()
        except Exception:
            pass

    def _refresh_motor_selector_for_current_controller(self):
        try:
            self.motor_selector.blockSignals(True)
            self.motor_selector.clear()
            key = self.controller_combo.currentData()
            if not key:
                self.motor_selector.blockSignals(False)
                return
            addrs = self._last_mapping.get(key, [])
            for a, ms in sorted(addrs, key=lambda x: int(x[0])):
                self.motor_selector.addItem(str(a), a)
            self.motor_selector.blockSignals(False)
        except Exception:
            pass

    def set_motor_rows(self, rows: typing.List[dict]):
        # rows: list of { 'adapter_key', 'address', 'model_serial' }
        # clear existing rows
        for i in reversed(range(self.inner_layout.count())):
            w = self.inner_layout.itemAt(i).widget()
            if w is not None:
                w.setParent(None)
        for r in rows:
            pr = PicoMotorRow(r.get('address', 0))
            pr.name.setText(str(r.get('model_serial','')))
            self.inner_layout.insertWidget(self.inner_layout.count()-1, pr)
        self.inner_layout.addStretch()

    def _on_back(self):
        try:
            steps = int(self.step_edit.text())
        except Exception:
            steps = 0
        # negative step
        try:
            adapter = str(self.controller_combo.currentData() or self.controller_combo.currentText())
        except Exception:
            adapter = str(self.controller_combo.currentText() or '')
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
        try:
            adapter = str(self.controller_combo.currentData() or self.controller_combo.currentText())
        except Exception:
            adapter = str(self.controller_combo.currentText() or '')
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

from PyQt6 import QtCore, QtWidgets
from widgets.motor_row import MotorRow

class StageControlPanel(QtWidgets.QWidget):
    action_performed = QtCore.pyqtSignal(str)
    request_move_absolute = QtCore.pyqtSignal(int, float)
    request_home = QtCore.pyqtSignal(int)
    request_move_delta = QtCore.pyqtSignal(int, float)
    request_set_speed = QtCore.pyqtSignal(int, float)
    request_set_lbound = QtCore.pyqtSignal(int, float)
    request_set_ubound = QtCore.pyqtSignal(int, float)

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

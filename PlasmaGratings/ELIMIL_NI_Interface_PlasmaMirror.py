# Zaber Stages GUI – (PyQt6)
# -------------------------------------------------------------
# • Left green light = ON when the row is moving (simulated).
# • Right red light = STOP button for that row.
# • The green bar shows the relative position (0–100%).
# • Columns: [green ON light] [red stop] [short name] [long name]
#            [steps label] [engineering units label] [green bar]
# -------------------------------------------------------------

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from zaber_motion import Library , Units
from zaber_motion.binary import Connection, CommandCode, BinarySettings

# --- Zaber connection defaults (update as needed) ---
PORT = "COM8"
BAUD = 115200


@dataclass
class MotorInfo:
    short: str
    long: str
    steps: int
    eng_value: float  # "Engineering value", stage position in mm or deg
    unit: str         # "mm" or "deg"
    span: float       # range for progress bar (e.g., 304.8 mm or 360 deg), should be changed?
    lbound: float     # min value the stage is allowed
    ubound: float     # max value the stage is allowed
    speed: float      # speed of the stage in mm or degrees / sec
    speed_unit: str   # "mm/s" or "deg/s"


class RoundLight(QtWidgets.QWidget):
    """A small round indicator light. Set color via .set_on(True/False).
       For the red light, we expose .clicked signal when used as a button.
    """
    clicked = QtCore.pyqtSignal()

    def __init__(self, diameter: int = 14, color_on: str = "#11c466", color_off: str = "#4a4a4a", clickable: bool = False):
        super().__init__()
        self._on = False
        self._diameter = diameter
        self._color_on = color_on
        self._color_off = color_off
        self._clickable = clickable
        self.setFixedSize(diameter, diameter)
        if clickable:
            self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if self._clickable:
            self.clicked.emit()
        return super().mousePressEvent(e)

    def set_on(self, value: bool) -> None:
        self._on = bool(value)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        color = QtGui.QColor(self._color_on if self._on else self._color_off)
        p.setBrush(color)
        p.setPen(QtGui.QPen(QtGui.QColor("#202020"), 1))
        p.drawEllipse(rect.adjusted(1, 1, -1, -1))
        if self._on:
            # subtle glow
            center = QtCore.QPointF(rect.center())
            glow = QtGui.QRadialGradient(center, float(rect.width())/2.0)
            glow.setColorAt(0.0, QtGui.QColor(color.red(), color.green(), color.blue(), 180))
            glow.setColorAt(1.0, QtGui.QColor(color.red(), color.green(), color.blue(), 0))
            p.setBrush(QtGui.QBrush(glow))
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.drawEllipse(rect)

class MotorRow(QtWidgets.QWidget):
    #Used to show status for a specific stage in class MotorStatusPanel
    toggled_motion = QtCore.pyqtSignal(bool)  # emits True/False when motion state changes

    def __init__(self, info: MotorInfo, index: int, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.info = info
        self._moving = False
        self._step_per_tick = 0  # 0 until user starts simulated motion

        # Widgets
        self.light_green = RoundLight(diameter=14, color_on="#22cc66", color_off="#2b2b2b", clickable=False)
        self.light_red = RoundLight(diameter=14, color_on="#d9534f", color_off="#7a2f2e", clickable=True)
        self.light_red.set_on(True)  # visually present red button
        self.light_red.clicked.connect(self.stop_motion)

        # Row order index
        self.index = index
        self.lbl_index = QtWidgets.QLabel(f"{index}")
        self.lbl_index.setMinimumWidth(20)
        self.lbl_index.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

        self.lbl_short = QtWidgets.QLabel(self.info.short)
        self.lbl_short.setMinimumWidth(55)
        self.lbl_short.setStyleSheet("font-weight: 600;")

        self.lbl_long = QtWidgets.QLabel(self.info.long)
        self.lbl_long.setMinimumWidth(100)
        self.lbl_long.setStyleSheet("font-weight: 700;")

        self.lbl_units = QtWidgets.QLabel(self._fmt_units(self.info.eng_value, self.info.unit, rich=True))
        self.lbl_units.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.lbl_units.setMinimumWidth(60)

        self.lbl_speed_units = QtWidgets.QLabel(self._fmt_units(self.info.speed, self.info.speed_unit, rich=True))
        self.lbl_speed_units.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.lbl_speed_units.setMinimumWidth(60)

        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(self._progress_from_value(self.info.eng_value))
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(16)
        
        self.lbl_steps = QtWidgets.QLabel(self._fmt_steps(self.info.steps))
        self.lbl_steps.setMinimumWidth(100)

        # style the bar green
        self.bar.setStyleSheet(
            "QProgressBar { background: #2a2a2a; border-radius: 8px; }"
            "QProgressBar::chunk { background-color: #1db954; border-radius: 8px; }"
        )

        # Layout
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(8)
        lay.addWidget(self.light_green)
        lay.addWidget(self.light_red)
        lay.addWidget(self.lbl_index)
        lay.addWidget(self.lbl_short)
        lay.addWidget(self.lbl_long)
        lay.addSpacing(2)
        lay.addWidget(self.lbl_units)
        lay.addSpacing(2)
        lay.addWidget(self.bar, stretch=1)
        lay.addSpacing(2)
        lay.addWidget(self.lbl_speed_units)
        lay.addSpacing(2)
        lay.addWidget(self.lbl_steps)
        lay.addSpacing(6)

        # interactions: double-click row to toggle simulated motion
        self.installEventFilter(self)

    # --- Utilities ---
    def _fmt_steps(self, steps: int) -> str:
        return f"{steps:,} steps".replace(",", " ")

    def _fmt_units(self, v: float, unit: str, rich: bool = False) -> str:
        if unit == "deg" or "deg/s":
            val, u = f"{v:.0f}", unit
        else:
            val, u = f"{v:.4g}", unit
        return f"<b>{val}</b> {u}" if rich else f"{val} {u}"

    def _progress_from_value(self, v: float) -> int:
        # clamp to [0, span]
        # Need to be changed to [lbound, ubound]
        v = max(0.0, min(self.info.span, v))
        return int(round((v / self.info.span) * 100))

    # --- Motion simulation controls ---
    def set_moving(self, moving: bool, step_per_tick: int = 3000):
        self._moving = moving
        self._step_per_tick = step_per_tick if moving else 0
        self.light_green.set_on(moving)
        self.toggled_motion.emit(moving)

    def stop_motion(self):
        # red light acts as STOP
        self.set_moving(False)

    def eventFilter(self, obj, event):
        # double click anywhere on the row toggles simulated motion
        if event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
            self.set_moving(not self._moving)
            return True
        return super().eventFilter(obj, event)

    def tick(self):
        if not self._moving:
            return
        # update steps and engineering value with a simple linear model
        self.info.steps += self._step_per_tick
        # map steps to span: assume 100k steps == 1 mm (mock), adjust as needed
        self.info.eng_value = (self.info.steps / 100000.0) % self.info.span
        self.lbl_steps.setText(self._fmt_steps(self.info.steps))
        self.lbl_units.setText(self._fmt_units(self.info.eng_value, self.info.unit, rich=True))
        self.bar.setValue(self._progress_from_value(self.info.eng_value))

class MotorStatusPanel(QtWidgets.QWidget):
    # Show the current status of all motors
    def __init__(self, motors: list[MotorInfo]):
        super().__init__()

        title = QtWidgets.QLabel("Stages")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")

        self.rows: list[MotorRow] = [MotorRow(m, i) for i, m in enumerate(motors, start=1)]

        container = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        for r in self.rows:
            v.addWidget(r)
        v.addStretch(1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        btn_sim_all = QtWidgets.QPushButton("Simulate All")
        btn_sim_all.setCheckable(True)
        btn_sim_all.toggled.connect(self._toggle_all)

        topbar = QtWidgets.QHBoxLayout()
        topbar.addWidget(title)
        topbar.addStretch(1)
        topbar.addWidget(btn_sim_all)

        layout = QtWidgets.QVBoxLayout(self)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMaximumWidth(760)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(topbar)
        layout.addWidget(scroll)

        # timer to drive simulation
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(50)  # 20 Hz
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _toggle_all(self, on: bool):
        for r in self.rows:
            r.set_moving(on)

    def _tick(self):
        for r in self.rows:
            r.tick()
    
    def update_address(self, steps: float, pos: float, stage_no: int):
        try:
            row = self.rows[stage_no-1]
        except Exception:
            return
        row.info.steps = int(steps)
        row.info.eng_value = float(pos)
        row.lbl_steps.setText(row._fmt_steps(row.info.steps))
        row.lbl_units.setText(row._fmt_units(row.info.eng_value, row.info.unit, rich=True))
        row.bar.setValue(row._progress_from_value(row.info.eng_value))

    def update_speed(self, speed: float, stage_no: int):
        try:
            row = self.rows[stage_no-1]
        except Exception:
            return
        row.info.speed = float(speed)
        row.lbl_speed_units.setText(row._fmt_units(row.info.speed, row.info.speed_unit, rich=True))

class StageControlPanel(QtWidgets.QWidget):
    """Part 2 — Stage position controls (GUI only, no hardware).
    Provides: selector, Home, Absolute move, Back/Forward jog. Change Limit. Change Speed
    """
    action_performed = QtCore.pyqtSignal(str)
    request_move_absolute = QtCore.pyqtSignal(int, float)
    request_home = QtCore.pyqtSignal(int)
    request_move_delta = QtCore.pyqtSignal(int, float)  # address (1-based), delta pos (+/-)
    request_set_speed = QtCore.pyqtSignal(int, float)

    def __init__(self, rows: list[MotorRow]):
        super().__init__()
        self.rows = rows
        self.current_index = 0  # 0-based index into rows

        # --- Widgets ---
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

    # --- Helpers ---
    def _steps_per_unit(self, row: MotorRow) -> float:
        # purely for GUI mock; adjust mapping as desired
        return 100000.0

    def _on_selection_changed(self, _idx: int):
        self.current_index = self.selector.currentData() if self.selector.currentData() is not None else 0
        row = self.rows[self.current_index]
        # set units/decimals/range
        # if row.info.unit == "deg":
        #     self.abs_unit.setText("deg"); self.jog_unit.setText("deg")
        #     self.abs_value.setDecimals(0); self.jog_value.setDecimals(0)
        # else:
        #     self.abs_unit.setText("mm"); self.jog_unit.setText("mm")
        #     self.abs_value.setDecimals(4); self.jog_value.setDecimals(4)
        self.abs_unit.setText(row.info.unit); self.jog_unit.setText(row.info.unit)
        self.bound_unit.setText(row.info.unit)
        self.speed_unit.setText(row.info.speed_unit)
        self.bound_unit_2.setText(row.info.unit)
        if row.info.unit == "deg":
            self.abs_value.setDecimals(2); self.jog_value.setDecimals(2)
        else:
            self.abs_value.setDecimals(4); self.jog_value.setDecimals(4)
        self.abs_value.setRange(0.0, float(row.info.span))
        self.jog_value.setRange(0.0, float(row.info.span))
        self.abs_value.setValue(float(row.info.eng_value))

    def _apply_value(self, row: MotorRow, new_val: float):
        new_val = max(0.0, min(row.info.span, new_val))
        row.info.eng_value = new_val
        # update steps according to mock conversion
        row.info.steps = int(round(new_val * self._steps_per_unit(row)))
        row.lbl_units.setText(row._fmt_units(row.info.eng_value, row.info.unit, rich=True))
        row.lbl_steps.setText(row._fmt_steps(row.info.steps))
        row.bar.setValue(row._progress_from_value(row.info.eng_value))

    def _emit_move(self, row: MotorRow, value: float, verb: str = "Move"):
        num = getattr(row, 'index', 1)
        idx = num - 1
        if row.info.unit == 'deg':
            val = f"{value:.2f} deg"
        else:
            val = f"{value:.6f} mm"
        msg = f"{verb} {row.info.short}, Index {idx} (Num {num}) to {val}"
        self.action_performed.emit(msg)

    def _home(self):
        row = self.rows[self.current_index]
        address = getattr(row, 'index', self.current_index + 1)
        self.request_home.emit(int(address))
        self._emit_move(row, 0.0, verb="Home")

    def _move_absolute(self):
        row = self.rows[self.current_index]
        val = float(self.abs_value.value())
        address = getattr(row, 'index', self.current_index + 1)
        self.request_move_absolute.emit(int(address), float(val))
        self._emit_move(row, val)

    def _jog(self, direction: int):
        row = self.rows[self.current_index]
        delta = float(self.jog_value.value()) * float(direction)
        address = getattr(row, 'index', self.current_index + 1)
        self.request_move_delta.emit(int(address), float(delta))
        self._emit_move(row, float(row.info.eng_value), verb="Jog")

    def _set_lbound(self):
        row = self.rows[self.current_index]
        val = float(self.lbound_value.value())
        if val >= row.info.ubound:
            val = row.info.ubound - 0.01  # ensure lbound < ubound
        row.info.lbound = val
        msg = f"Set Lower Bound of {row.info.short}, Index {row.index} to {val:.4f} {row.info.unit}"
        self.action_performed.emit(msg)
        self.lbound_value.setValue(val)  # update spinbox in case it was adjusted

    def _set_ubound(self):
        row = self.rows[self.current_index]
        val = float(self.ubound_value.value())
        if val <= row.info.lbound:
            val = row.info.lbound + 0.01  # ensure ubound > lbound
        row.info.ubound = val
        msg = f"Set Upper Bound of {row.info.short}, Index {row.index} to {val:.4f} {row.info.unit}"
        self.action_performed.emit(msg)
        self.ubound_value.setValue(val)  # update spinbox in case it was adjusted

    def _set_speed(self):
        row = self.rows[self.current_index]
        val = float(self.speed_value.value())
        address = getattr(row, 'index', self.current_index + 1)
        # emit backend request; Part 1 will refresh via speed signal on readback
        self.request_set_speed.emit(int(address), float(val))
        msg = f"Set Speed request for {row.info.short}, Index {row.index} to {val:.2f} {row.info.speed_unit}"
        self.action_performed.emit(msg)

class StatusPanel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(420)        # pick your preferred baseline width
        self.setMaximumWidth(600) 
        grp = QtWidgets.QGroupBox("Status")
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        fm = self.log.fontMetrics()
        row_h = fm.lineSpacing()
        self.log.setMinimumHeight(int(row_h * 35 + 12))
        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.clicked.connect(self.log.clear)
        btn_copy = QtWidgets.QPushButton("Copy All")
        btn_copy.clicked.connect(self._copy_all)
        top = QtWidgets.QHBoxLayout(); top.addStretch(1); top.addWidget(btn_copy); top.addWidget(btn_clear)
        v = QtWidgets.QVBoxLayout(); v.addLayout(top); v.addWidget(self.log)
        grp.setLayout(v)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(grp)
        layout.addStretch(1)
        grp.setStyleSheet("QGroupBox { font-weight: 600; }")

    @QtCore.pyqtSlot(str)
    def append_line(self, text: str):
        self.log.appendPlainText(text)
        # ensure view stays at bottom
        self.log.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _copy_all(self):
        self.log.selectAll()
        self.log.copy()

class PlaceholderPanel(QtWidgets.QWidget):
    #not used now
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("placeholder")
        lab_title = QtWidgets.QLabel(title)
        lab_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        lab_msg = QtWidgets.QLabel("(Reserved — we will implement this next)")
        lab_msg.setStyleSheet("color: #aaaaaa;")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(lab_title)
        layout.addWidget(lab_msg)
        layout.addStretch(1)

class ZaberDiscoveryWorker(QtCore.QObject):
    """Run Zaber device discovery off the GUI thread and stream logs."""
    #not used now
    log = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(list)


    def __init__(self, port: str, baud: int):
        super().__init__()
        self.port = port
        self.baud = baud


    @QtCore.pyqtSlot()
    def run(self):

        def _reply_data(obj):
            try:
                return obj.data
            except AttributeError:
                return obj[0].data if isinstance(obj, (list, tuple)) and obj else None


        Library.enable_device_db_store()
        try:
            self.log.emit(f"Opening {self.port} (Binary, {self.baud} baud)...")
            with Connection.open_serial_port(self.port, baud_rate=self.baud) as conn:
                devices = conn.detect_devices(identify_devices=True)
                self.log.emit(f"Found {len(devices)} device(s) on {self.port}:")
                found = []
                for dev in devices:
                    addr = dev.device_address
                    name = None
                    try:
                        ident = dev.identify()
                        name = getattr(ident, "name", None) or getattr(dev, "name", None)
                    except Exception:
                        pass


                    dev_id = fw = serial = None
                    try:
                        dev_id = _reply_data(conn.generic_command(dev, CommandCode.RETURN_DEVICE_ID))
                    except Exception:
                        pass
                    try:
                        fw_raw = _reply_data(conn.generic_command(dev, CommandCode.RETURN_FIRMWARE_VERSION))
                        fw = f"{fw_raw/100:.2f}" if isinstance(fw_raw, int) else fw_raw
                    except Exception:
                        pass
                    try:
                        serial = _reply_data(conn.generic_command(dev, CommandCode.RETURN_SERIAL_NUMBER))
                    except Exception:
                        pass


                    label = name or f"Unknown (DeviceID={dev_id})"
                    self.log.emit(f"- Address {addr}: {label}" + (f", FW {fw}" if fw else "") + (f", Serial {serial}" if serial else ""))
                    found.append({"address": addr, "label": label, "fw": fw, "serial": serial})
                self.finished.emit(found)
        except Exception as e:
            self.log.emit(f"Discovery failed: {e}")
            self.finished.emit([])

class StageIO(QtCore.QObject):
    """Single persistent I/O thread that owns the serial connection.
    All device actions (discover/read/move/home) happen here to avoid port races.
    """
    # Notice: StageIO don't have "unit" parameter, you have to pass it external
    log = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    opened = QtCore.pyqtSignal()
    discovered = QtCore.pyqtSignal(list)        # list[{address:int,label:str}]
    position = QtCore.pyqtSignal(int, float, float)  # address, steps, mm/deg
    moved = QtCore.pyqtSignal(int, float)       # address, final_mm/final_deg
    homed = QtCore.pyqtSignal(int)              # address
    speed = QtCore.pyqtSignal(int, float)       # address, target speed in mm/s or deg/s

    def __init__(self, port: str, baud: int):
        super().__init__()
        self.port = port
        self.baud = baud
        self.conn = None

    @QtCore.pyqtSlot()
    def open(self):
        try:
            from zaber_motion import Library
            from zaber_motion.binary import Connection
            Library.enable_device_db_store()
            self.conn = Connection.open_serial_port(self.port, baud_rate=self.baud)
            self.log.emit(f"I/O opened {self.port} (Binary, {self.baud} baud)")
            self.opened.emit()
        except Exception as e:
            self.error.emit(f"Open failed: {e}")

    @QtCore.pyqtSlot()
    def close(self):
        try:
            if self.conn is not None:
                self.conn.close()
                self.log.emit("I/O closed")
        except Exception as e:
            self.error.emit(f"Close error: {e}")
        finally:
            self.conn = None

    @QtCore.pyqtSlot()
    def discover(self):
        try:
            if self.conn is None:
                self.open()
                if self.conn is None:
                    return
            devices = self.conn.detect_devices(identify_devices=True)
            self.log.emit(f"Found {len(devices)} device(s) on {self.port}:")
            found = []
            for dev in devices:
                addr = dev.device_address
                label = getattr(dev, "name", None)
                try:
                    ident = dev.identify()
                    label = label or getattr(ident, "name", None)
                except Exception:
                    pass
                # Optional: more metadata via CommandCode if needed
                self.log.emit(f"- Address {addr}: {label or 'Unknown'}")
                found.append({"address": addr, "label": label or "Unknown"})
            self.discovered.emit(found)
        except Exception as e:
            self.error.emit(f"Discover failed: {e}")

    @QtCore.pyqtSlot(int)
    def read_position_speed(self, address: int, unit):
        try:
            if self.conn is None:
                self.error.emit("Not connected")
                return
            dev = self.conn.get_device(int(address))
            try:
                dev.identify()
            except Exception:
                pass
            steps = dev.get_position()
            if unit == "mm":
                mm = dev.get_position(Units.LENGTH_MILLIMETRES)
                spd = dev.settings.get(BinarySettings.TARGET_SPEED, Units.VELOCITY_MILLIMETRES_PER_SECOND)
                self.position.emit(int(address), float(steps), float(mm))
                self.speed.emit(int(address), float(spd))
                self.log.emit(f"Address {address}: {steps:.0f} steps, {mm:.6f} mm, {spd:.0f} mm/s")
            elif unit == "deg":
                deg = dev.get_position(Units.ANGLE_DEGREES)
                spd = dev.settings.get(BinarySettings.TARGET_SPEED, Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
                self.position.emit(int(address), float(steps), float(deg))
                self.speed.emit(int(address), float(spd))
                self.log.emit(f"Address {address}: {steps:.0f} steps, {deg:.6f} deg, {spd:.0f} deg/s")
        except Exception as e:
            self.error.emit(f"Read position failed: {e}")



    @QtCore.pyqtSlot(int, float)
    def move_absolute(self, address: int, target_pos: float, unit):
        try:
            if self.conn is None:
                self.error.emit("Not connected")
                return
            dev = self.conn.get_device(int(address))
            try:
                dev.identify()
            except Exception:
                pass
            if unit == "mm":
                dev.move_absolute(float(target_pos), Units.LENGTH_MILLIMETRES)
                dev.wait_until_idle()
                steps = dev.get_position()
                pos = dev.get_position(Units.LENGTH_MILLIMETRES)
                self.position.emit(int(address), float(steps), float(pos))
                self.moved.emit(int(address), float(pos))
            elif unit == "deg":
                dev.move_absolute(float(target_pos), Units.ANGLE_DEGREES)
                dev.wait_until_idle()
                steps = dev.get_position()
                pos = dev.get_position(Units.ANGLE_DEGREES)
                self.position.emit(int(address), float(steps), float(pos))
                self.moved.emit(int(address), float(pos))

        except Exception as e:
            self.error.emit(f"Move failed: {e}")

    @QtCore.pyqtSlot(int)
    def home(self, address: int):
        try:
            if self.conn is None:
                self.error.emit("Not connected")
                return
            dev = self.conn.get_device(int(address))
            dev.home()
            dev.wait_until_idle()
            self.homed.emit(int(address))
        except Exception as e:
            self.error.emit(f"Home failed: {e}")

    @QtCore.pyqtSlot(int, float)
    def move_delta(self, address: int, delta_pos: float, unit):
        """Move by a relative delta (mm/deg). Positive=forward, negative=back."""
        try:
            if self.conn is None:
                self.error.emit("Not connected")
                return
            dev = self.conn.get_device(int(address))
            try:
                dev.identify()
            except Exception:
                pass
            if unit == "mm":
                cur_mm = float(dev.get_position(Units.LENGTH_MILLIMETRES))
                target_mm = cur_mm + float(delta_pos)
                dev.move_absolute(target_mm, Units.LENGTH_MILLIMETRES)
                dev.wait_until_idle()
                # Broadcast fresh position
                steps = dev.get_position()
                mm = dev.get_position(Units.LENGTH_MILLIMETRES)
                self.position.emit(int(address), float(steps), float(mm))
                self.moved.emit(int(address), float(mm))
                self.log.emit(f"Address {address} jog {delta_pos:+.6f} mm → {mm:.6f} mm")
            elif unit == "deg":
                cur_deg = float(dev.get_position(Units.ANGLE_DEGREES))
                target_deg = cur_deg + float(delta_pos)
                dev.move_absolute(target_deg, Units.ANGLE_DEGREES)
                dev.wait_until_idle()
                # Broadcast fresh position
                steps = dev.get_position()
                deg = dev.get_position(Units.ANGLE_DEGREES)
                self.position.emit(int(address), float(steps), float(deg))
                self.moved.emit(int(address), float(deg))
                self.log.emit(f"Address {address} jog {delta_pos:+.6f} deg → {deg:.6f} deg")
        except Exception as e:
            self.error.emit(f"Move delta failed: {e}")

    @QtCore.pyqtSlot(int, float)
    def set_target_speed(self, address: int, new_spd: float, unit):
        """Set target speed in mm/s or deg/s"""
        try:
            if self.conn is None:
                self.error.emit("Not connected")
                return
            dev = self.conn.get_device(int(address))
            try:
                dev.identify()
            except Exception:
                pass
            
            if unit == "mm/s":
                try:
                    dev.settings.set(BinarySettings.TARGET_SPEED, float(new_spd), Units.VELOCITY_MILLIMETRES_PER_SECOND)
                except Exception:
                    self.error.emit(f"Set speed fallback failed: {e}")
                    return
                # Read back target speed
                ts = dev.settings.get(BinarySettings.TARGET_SPEED, Units.VELOCITY_MILLIMETRES_PER_SECOND)
                if ts is not None:
                    self.speed.emit(int(address), float(ts))
                    self.log.emit(f"Address {address} target speed set to: {ts:.6f} mm/s")
                else:
                    self.log.emit("Target Speed set; read-back unavailable")
            elif unit == "deg/s":
                try:
                    dev.settings.set(BinarySettings.TARGET_SPEED, float(new_spd), Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
                except Exception:
                    self.error.emit(f"Set speed fallback failed: {e}")
                    return
                # Read back target speed
                ts = dev.settings.get(BinarySettings.TARGET_SPEED, Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
                if ts is not None:
                    self.speed.emit(int(address), float(ts))
                    self.log.emit(f"Address {address} target speed set to: {ts:.2f} deg/s")
                else:
                    self.log.emit("Target Speed set; read-back unavailable")

        except Exception as e:
            self.error.emit(f"Set target speed failed: {e}")

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zaber GUI")
        self.resize(920, 720)

        # sample motors matching your screenshot
        motors = [
            MotorInfo("PM1R",  "PM1 Rotation",     0,        0.0,      "deg", 360.0, 0.0, 360.0, 90.0, "deg/s"),
            MotorInfo("PM1Y",  "PM1 Y Scan",       4_266_667, 203.2,   "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("PM1Z",  "PM1 Z Scan",       1_066_667, 50.8,    "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("PM1D",  "PM1 Redirect",     2_133_334, 101.6,   "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("PM3Y",  "PM3 Y Scan",       3_038_763, 301.502, "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("PM3Z",  "PM3 Z Scan",         771_029, 76.5005, "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("R2",    "Rotation 2",       0,        0.0,      "deg", 360.0, 0.0, 360.0, 90.0, "deg/s"),
            MotorInfo("XM",    "XUV Mirror",       3_200_000, 152.4,   "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("S2",    "Beam Diag.",       3_200_000, 152.4,   "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("PM2D",  "PM2 Redirect",     2_133_334, 101.6,   "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("PM2Y",  "PM2 Y Scan",       1_526_940, 151.501, "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("PM2Z",  "PM2 Z Scan",         771_029, 76.5005, "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("PM2V",  "PM2 Vertical",     2_133_334, 101.6,   "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("PM3X",  "PM3 Vertical",     2_133_334, 76.5005, "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("S3",    "HeNe",             2_133_334, 101.6,   "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
            MotorInfo("PG",    "Plasma",           2_133_334, 101.6,   "mm", 304.8, 0.0, 304.8, 50.0, "mm/s"),
        ]

        # build three parts
        self.part1 = MotorStatusPanel(motors)
        self.part2 = StageControlPanel(self.part1.rows)
        self.status_panel = StatusPanel()
        self.part2.action_performed.connect(self.status_panel.append_line)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        layout.addWidget(self.part1, stretch=3)
        layout.addWidget(self.part2, stretch=1)
        layout.addWidget(self.status_panel, stretch=1)
        # Ensure Part 1 widget reference is used in layout (already added above)
        self.setCentralWidget(central)

        # --- Start persistent I/O thread and auto-discover ---
        self.io_thread = QtCore.QThread(self)
        self.stage = StageIO(PORT, BAUD)
        self.stage.moveToThread(self.io_thread)

        # thread life-cycle
        self.io_thread.started.connect(self.stage.open)
        self.stage.opened.connect(self.stage.discover)               # once open, run discovery in the I/O thread
        self.stage.log.connect(self.status_panel.append_line)
        self.stage.error.connect(self.status_panel.append_line)
        self.stage.discovered.connect(self._on_discovered)
        self.stage.position.connect(self._on_position)
        self.stage.speed.connect(self._on_speed)
        self.stage.moved.connect(self._on_moved)
        self.stage.homed.connect(self._on_homed)

        # wire Part 2 (Absolute/Home) to backend
        self.part2.request_move_absolute.connect(self._on_request_move_absolute)
        self.part2.request_home.connect(self._on_request_home)
        self.part2.request_move_delta.connect(self._on_request_move_delta)
        self.part2.request_set_speed.connect(self._on_request_set_speed)

        self.io_thread.start()

        # overall dark style
        self.setStyleSheet(
            "QWidget { background-color: #1e1e1e; color: #e6e6e6; font-size: 12px; }"
            "QGroupBox { border: 1px solid #333; margin-top: 6px; }"
            "QLabel { background: transparent; }"
            "QScrollArea { border: none; }"
            "QPushButton { background: #2c2c2c; border: 1px solid #3a3a3a; padding: 4px 8px; border-radius: 6px; }"
            "QPushButton:checked { background: #3a523a; }"
        )

    @QtCore.pyqtSlot(list)
    def _on_discovered(self, devices: list):
        if devices:
            self.status_panel.append_line(f"Discovery complete. {len(devices)} device(s) ready.")
            # Read Address 1 after discovery
            QtCore.QTimer.singleShot(0, lambda: self.stage.read_position_speed(1, "deg"))
            # Read Address 15 right after discovery
            QtCore.QTimer.singleShot(0, lambda: self.stage.read_position_speed(15, "mm"))
        else:
            self.status_panel.append_line("Discovery finished with no devices.")

    @QtCore.pyqtSlot(int, float, float)
    def _on_position(self, address: int, steps: float, pos: float):
        if address == 1 or 15:
            try:
                self.part1.update_address(steps, pos, address)
                #self.status_panel.append_line(f"Part 1 updated for Address {address:.0f} → {steps:.0f} steps, {mm:.6f} mm")
            except Exception:
                pass

    @QtCore.pyqtSlot(int, float)
    def _on_speed(self, address: int, speed: float):
        if address == 1 or 15:
            try:
                self.part1.update_speed(speed, address)
                #self.status_panel.append_line(f"Part 1 updated for address {address} target speed: {speed:.0f} mm/s")
            except Exception:
                pass

    @QtCore.pyqtSlot(int, float)
    def _on_moved(self, address: int, final_pos: float):
        # After motion completes, read back precise position then update Part 1
        row = self.part1.rows[address - 1]
        unit = getattr(row.info, 'unit')
        if unit == "mm":
            self.status_panel.append_line(
                f"Move complete on Address {address}: {final_pos:.6f} mm (reading back...)"
            )
            self.stage.read_position_speed(address, "mm")
        elif unit == "deg":
            self.status_panel.append_line(
                f"Move complete on Address {address}: {final_pos:.2f} deg (reading back...)"
            )
            self.stage.read_position_speed(address, "deg")


    @QtCore.pyqtSlot(int, float)
    def _on_request_move_absolute(self, address: int, target_pos: float):
        row = self.part1.rows[address - 1]
        unit = getattr(row.info, 'unit')
        self.status_panel.append_line(
            f"Absolute requested → Address {address}, Target {target_pos:.6f} {unit}"
        )
        try:
            self.stage.move_absolute(address, target_pos, unit)
        except Exception as e:
            self.status_panel.append_line(f"Move request failed: {e}")
    
    @QtCore.pyqtSlot(int)
    def _on_homed(self, address: int):
        row = self.part1.rows[address - 1]
        unit = getattr(row.info, 'unit')
        QtCore.QTimer.singleShot(50, lambda a=address: self.stage.read_position_speed(a, unit))
        self.status_panel.append_line(f"Home complete on Address {address} → reading back position…")

    @QtCore.pyqtSlot(int)
    def _on_request_home(self, address: int):
        self.status_panel.append_line(f"Home requested → Address {address}")
        try:
            self.stage.home(address)
        except Exception as e:
            self.status_panel.append_line(f"Home request failed: {e}")
    
    @QtCore.pyqtSlot(int, float)
    def _on_request_move_delta(self, address: int, delta_pos: float):
        row = self.part1.rows[address - 1]
        unit = getattr(row.info, 'unit')
        self.status_panel.append_line(f"Jog requested → Address {address}, Delta {delta_pos:+.6f} {unit}")
        self.stage.move_delta(address, delta_pos, unit)

    @QtCore.pyqtSlot(int, float)
    def _on_request_set_speed(self, address: int, new_spd: float):
        row = self.part1.rows[address - 1]
        unit = getattr(row.info, 'speed_unit')
        self.status_panel.append_line(
            f"Set speed requested → Address {address}: {new_spd:.6f} {unit}"
        )
        try:
            self.stage.set_target_speed(address, new_spd, unit)
        except Exception as e:
            self.status_panel.append_line(f"Set speed request failed: {e}")

    def closeEvent(self, e: QtGui.QCloseEvent) -> None:
        try:
            if hasattr(self, 'stage') and self.stage is not None:
                self.stage.close()
        except Exception:
            pass
        try:
            if hasattr(self, 'io_thread') and self.io_thread is not None:
                self.io_thread.quit()
                self.io_thread.wait(1000)
        except Exception:
            pass
        return super().closeEvent(e)

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
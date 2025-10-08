import sys
from PyQt6 import QtCore, QtGui, QtWidgets
# from matplotlib.pyplot import grid
from MotorInfo import MotorInfo
from device_io.zaber_stage_io import ZaberStageIO
from panels.motor_status_panel import MotorStatusPanel
from panels.stage_control_panel import StageControlPanel
from panels.status_panel import StatusPanel
from panels.PM_panel import PMPanel
from panels.fire_controls_panel import FireControlsPanel
from device_io.kinesis_fire_io import KinesisFireIO, FireConfig
from panels.placeholder_panel import PlaceholderPanel

PORT = "COM8"; BAUD = 115200

class MainWindow(QtWidgets.QMainWindow):
    # requests forwarded to I/O worker (queued)
    req_read = QtCore.pyqtSignal(int, str)
    req_bounds = QtCore.pyqtSignal(int, str)
    req_set_lbound = QtCore.pyqtSignal(int, float, str)
    req_set_ubound = QtCore.pyqtSignal(int, float, str)
    req_abs  = QtCore.pyqtSignal(int, float, str)
    req_jog  = QtCore.pyqtSignal(int, float, str)
    req_home = QtCore.pyqtSignal(int)
    req_spd  = QtCore.pyqtSignal(int, float, str)
    req_stop = QtCore.pyqtSignal(int, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zaber GUI")
        self.resize(920, 720)

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

        self.overall_controls = PlaceholderPanel("Overall Controls")
        self.fire_panel    = FireControlsPanel()
        self.pm_panel= PMPanel()
        self.part1 = MotorStatusPanel(motors)
        self.part2 = StageControlPanel(self.part1.rows)
        self.status_panel = StatusPanel()
        
        # --- Center layout: 2x3 grid ---------------------------------
        central = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(central)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        # Top row: Overall Controls | Fire Controls | PM panel
        grid.addWidget(self.overall_controls, 0, 0)
        grid.addWidget(self.fire_panel, 0, 1)
        grid.addWidget(self.pm_panel, 0, 2)

        # Bottom row: Status | Stages (part1) | Stage Controls (part2)
        grid.addWidget(self.status_panel, 0 + 1, 0)   # row 1, col 0
        grid.addWidget(self.part2,        1, 1)       # Stage controls
        grid.addWidget(self.part1,        1, 2)       # Motor_status

        # Make Stages (col 1) the widest
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)   # Part 1 wider
        grid.setColumnStretch(2, 3)

        # Even row heights (tweak if you want the bottom row taller)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        self.setCentralWidget(central)

        # --- Stage I/O thread ---
        self.io_thread = QtCore.QThread(self)
        self.stage = ZaberStageIO(PORT, BAUD)
        self.stage.moveToThread(self.io_thread)

        # # start/stop lifecycle
        self.io_thread.started.connect(self.stage.open)
        self.stage.opened.connect(self.stage.discover)
        self.stage.log.connect(self.status_panel.append_line)
        self.stage.error.connect(self.status_panel.append_line)
        self.stage.discovered.connect(self._on_discovered)
        self.stage.position.connect(self._on_position)
        self.stage.speed.connect(self._on_speed)
        self.stage.moving.connect(self._on_moving)
        self.stage.moved.connect(self._on_moved)
        self.stage.homed.connect(self._on_homed)
        self.stage.bounds.connect(self._on_bounds)
        self.io_thread.start()

        # --- Fire I/O thread ---
        self.fire_thread = QtCore.QThread(self)
        cfg = FireConfig(
            serial=None,                 # or "6800xxxx" to pin a specific unit
            out_pin_shutter="Dev1/port0/line0",
            out_pin_cam="Dev1/port0/line2",
            out_pin_spec="Dev1/port0/line3",
            input_trigger="Dev1/PFI0",
            poll_period_s=0.02,
            start_enabled=False,
        )
        self.fire_io = KinesisFireIO(cfg)
        self.fire_io.moveToThread(self.fire_thread)

        # start/stop lifecycle
        self.fire_thread.started.connect(self.fire_io.open)
        # OPTIONAL: if the thread ever stops, ensure close got called
        self.fire_thread.finished.connect(self.fire_io.close)
        self.fire_thread.start()

        # Panel → IO
        self.fire_panel.request_mode.connect(self.fire_io.set_mode)
        self.fire_panel.request_shots.connect(self.fire_io.set_num_shots)
        self.fire_panel.request_fire.connect(self.fire_io.fire)

        # worker -> UI
        self.fire_io.status.connect(self.fire_panel.set_status)
        #self.fire_io.shots_progress.connect(self.fire_panel.set_progress)
        self.fire_io.log.connect(self.status_panel.append_line)     # if you have a log area
        self.fire_io.error.connect(self.status_panel.append_line)

        # thread-safe wiring
        self.req_read.connect(self.stage.read_position_speed, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_bounds.connect(self.stage.get_limits, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_set_lbound.connect(self.stage.set_lower_limit, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_set_ubound.connect(self.stage.set_upper_limit, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_abs.connect(self.stage.move_absolute, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_jog.connect(self.stage.move_delta, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_home.connect(self.stage.home, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_spd.connect(self.stage.set_target_speed, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_stop.connect(self.stage.stop, QtCore.Qt.ConnectionType.QueuedConnection)

        #connect each rows red button to the stop function
        for addr, row in enumerate(self.part1.rows, start=1):
            row.light_red.clicked.connect(lambda checked=False, a=addr, u=row.info.unit: self.req_stop.emit(a, u))

        # UI → main window handlers
        self.part2.action_performed.connect(self.status_panel.append_line)
        self.part2.request_move_absolute.connect(self._on_request_move_absolute)
        self.part2.request_home.connect(self._on_request_home)
        self.part2.request_move_delta.connect(self._on_request_move_delta)
        self.part2.request_set_speed.connect(self._on_request_set_speed)
        self.part2.request_set_lbound.connect(self._on_request_set_lbound)
        self.part2.request_set_ubound.connect(self._on_request_set_ubound)

        # style
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
            # emit a read request for each discovered device so the UI gets initial position/speed
            # devices is a list of dicts with keys 'address' and 'label' as emitted by ZaberStageIO.discover
            for d in devices:
                try:
                    addr = int(d.get('address'))
                except Exception:
                    continue
                # determine unit from configured rows if available; default to mm
                try:
                    row = self.part1.rows[addr - 1]
                    unit = getattr(row.info, 'unit', 'mm') or 'mm'
                except Exception:
                    unit = 'mm'
                # schedule the read on the Qt event loop to keep ordering predictable
                QtCore.QTimer.singleShot(0, lambda a=addr, u=unit: self.req_read.emit(a, u))
                QtCore.QTimer.singleShot(0, lambda a=addr, u=unit: self.req_bounds.emit(a, u))
        else:
            self.status_panel.append_line("Discovery finished with no devices.")

    @QtCore.pyqtSlot(int, float, float)
    def _on_position(self, address: int, steps: float, pos: float):
        self.part1.update_address(steps, pos, address)

    @QtCore.pyqtSlot(int, float)
    def _on_speed(self, address: int, speed: float):
        self.part1.update_speed(speed, address)
        
    @QtCore.pyqtSlot(int, float, float)
    def _on_bounds(self, address: int, lower: float, upper: float):
        self.part1.update_bounds(lower, upper, address)

    @QtCore.pyqtSlot(int, bool)
    def _on_moving(self, address: int, is_moving: bool):
        if 1 <= address <= len(self.part1.rows):
            row = self.part1.rows[address - 1]
            row.light_green.set_on(is_moving)

    @QtCore.pyqtSlot(int, float)
    def _on_moved(self, address: int, final_pos: float):
        row = self.part1.rows[address - 1]
        unit = row.info.unit
        prec = 2 if unit == "deg" else 6
        self.status_panel.append_line(
            f"Move complete on Address {address}: {final_pos:.{prec}f} {unit} (reading back...)"
        )
        self.req_read.emit(address, unit)

    @QtCore.pyqtSlot(int, float)
    def _on_request_move_absolute(self, address: int, target_pos: float):
        unit = self.part1.rows[address - 1].info.unit
        self.status_panel.append_line(f"Absolute requested → Address {address}, Target {target_pos:.6f} {unit}")
        self.req_abs.emit(address, target_pos, unit)

    @QtCore.pyqtSlot(int)
    def _on_homed(self, address: int):
        row = self.part1.rows[address - 1]
        unit = getattr(row.info, 'unit')
        QtCore.QTimer.singleShot(50, lambda a=address: self.stage.read_position_speed(a, unit))
        self.status_panel.append_line(f"Home complete on Address {address} → reading back position…")

    @QtCore.pyqtSlot(int)
    def _on_request_home(self, address: int):
        self.status_panel.append_line(f"Home requested → Address {address}")
        self.req_home.emit(address)

    @QtCore.pyqtSlot(int, float)
    def _on_request_move_delta(self, address: int, delta_pos: float):
        unit = self.part1.rows[address - 1].info.unit
        self.status_panel.append_line(f"Jog requested → Address {address}, Delta {delta_pos:+.6f} {unit}")
        self.req_jog.emit(address, delta_pos, unit)

    @QtCore.pyqtSlot(int, float)
    def _on_request_set_speed(self, address: int, new_spd: float):
        unit = self.part1.rows[address - 1].info.speed_unit
        self.status_panel.append_line(f"Set speed requested → Address {address}: {new_spd:.6f} {unit}")
        self.req_spd.emit(address, new_spd, unit)

    @QtCore.pyqtSlot(int, float)
    def _on_request_set_lbound(self, address: int, new_lbound: float):
        unit = self.part1.rows[address - 1].info.unit
        self.status_panel.append_line(f"Set lower bound requested → Address {address}: {new_lbound:.6f} {unit}")
        self.req_set_lbound.emit(address, new_lbound, unit)

    @QtCore.pyqtSlot(int, float)
    def _on_request_set_ubound(self, address: int, new_ubound: float):
        unit = self.part1.rows[address - 1].info.unit
        self.status_panel.append_line(f"Set upper bound requested → Address {address}: {new_ubound:.6f} {unit}")
        self.req_set_ubound.emit(address, new_ubound, unit)

    def closeEvent(self, a0: QtGui.QCloseEvent | None) -> None:
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
        try:
            QtCore.QMetaObject.invokeMethod(self.fire_io, "close", QtCore.Qt.ConnectionType.QueuedConnection)
        except Exception:
            pass
        try:
            self.fire_thread.quit()
            self.fire_thread.wait(1500)
        except Exception:
            pass
        super().closeEvent(a0)

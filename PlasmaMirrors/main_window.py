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
from panels.device_tabs_panel import DeviceTabsPanel
from device_io.newfocus_pico_io import NewFocusPicoIO
from panels.picomotor_panel import PicoPanel
from panels.overall_control_panel import SavingPanel
import os
import json
import time
from datetime import datetime
from utilities.file_info_writer import InfoWriter
import utilities.file_renamer as file_renamer
import math
from utilities.pm_auto import PMAutoManager

# legacy module defaults are kept only as fallbacks; we prefer device_connections.json
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
        self.setWindowTitle("Plasma Mirrors GUI")
        self.resize(1400, 1300)

        # Load stage definitions from parameters/stages.json and convert to MotorInfo list
        motors = []
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            stages_file = os.path.join(base_dir, 'parameters', 'stages.json')
            # load device connections defaults if present
            con_file = os.path.join(base_dir, 'parameters', 'device_connections.json')
            detected_port = None
            detected_baud = None
            try:
                with open(con_file, 'r', encoding='utf-8') as cf:
                    con = json.load(cf)
                    z = con.get('zaber', {}) if isinstance(con, dict) else {}
                    detected_port = z.get('PORT') or z.get('port')
                    detected_baud = z.get('BAUD') or z.get('baud')
            except Exception:
                detected_port = None
                detected_baud = None

            with open(stages_file, 'r', encoding='utf-8') as f:
                stages = sorted(json.load(f), key=lambda s: int(s.get('num', 0)))
            for s in stages:
                short = s.get('Abr', '')
                long = s.get('name', '')
                num = int(s.get('num', 0))
                # approximate steps and engineering value are left as 0 unless you want a mapping
                steps = 0
                eng_value = 0.0
                typ = s.get('type', 'Linear')
                unit = 'mm' if typ == 'Linear' else 'deg'
                span = float(s.get('limit', 0.0) or 0.0)
                lbound = 0.0
                ubound = float(s.get('limit', 0.0) or 0.0)
                speed = 50.0 if unit == 'mm' else 90.0
                speed_unit = 'mm/s' if unit == 'mm' else 'deg/s'
                motors.append(MotorInfo(short, long, steps, eng_value, unit, span, lbound, ubound, speed, speed_unit))
        except Exception:
            motors = []

        # Determine defaults for DeviceTabs and stage IO
        port_default = detected_port if detected_port is not None else PORT
        try:
            baud_default = int(detected_baud) if detected_baud is not None else BAUD
        except Exception:
            baud_default = BAUD

        self.device_tabs = DeviceTabsPanel(default_port=port_default, default_baud=baud_default)
        # when the device tabs edit the stages.json, update our motors list
        try:
            self.device_tabs.stages_changed.connect(lambda new_stages: self._on_stages_edited(new_stages))
        except Exception:
            pass
        self.overall_controls = SavingPanel()
        self.fire_panel    = FireControlsPanel()
        # Ensure burst relative folder field is only editable in Burst mode
        try:
            # connect FireControlsPanel mode changes to enable/disable overall_controls.burst_edit
            def _on_mode_changed(mode: str):
                try:
                    be = getattr(self, 'overall_controls', None) and getattr(self.overall_controls, 'burst_edit', None)
                    if be is not None:
                        be.setEnabled(mode == 'burst')
                except Exception:
                    pass
            try:
                self.fire_panel.request_mode.connect(_on_mode_changed)
                # initialize state according to current panel mode
                _on_mode_changed(getattr(self.fire_panel, '_current_mode', 'continuous'))
            except Exception:
                pass
        except Exception:
            pass
        # -- Shot counter persistence --
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self._shot_counter_file = os.path.join(base_dir, "parameters", "shot_counter.json")
            try:
                # allow the panel to notify us when the user configures a new value
                self.fire_panel.shot_config_saved.connect(self._on_shot_config_saved)
            except Exception:
                pass
            # load persisted value if present
            try:
                self._load_shot_counter()
            except Exception:
                pass
        except Exception:
            pass
        # Use the Interval (ms) control from the Fire panel as the rename wait budget (ms)
        try:
            # initialize attribute from current UI value
            self._rename_max_wait_ms = int(self.fire_panel.spin_interval.value())
            # keep it updated whenever the user changes the interval
            self.fire_panel.spin_interval.valueChanged.connect(lambda v: setattr(self, '_rename_max_wait_ms', int(v)))
        except Exception:
            # fallback default
            self._rename_max_wait_ms = getattr(self, '_rename_max_wait_ms', 5000)
        self.pm_panel= PMPanel()
        self.part1 = MotorStatusPanel(motors)
        self.part2 = StageControlPanel(self.part1.rows)
        self.status_panel = StatusPanel()
        self.placeholder_panel = PlaceholderPanel("Placeholder")
        # track background write + auto-move state so we can control Fire button
        self._info_write_pending = False
        self._pending_auto_addresses = set()
        # queued fire request when a sequence is active and user clicks Fire again
        self._queued_fire_request = False
        # per-shot run progress (shots completed within the current run)
        self._per_shot_completed_in_run = 0
        # timer to poll completion conditions for queued runs
        self._queued_check_timer = None
        # when True, a next shot should be queued only once post-processing and autos complete
        self._next_shot_when_ready = False

        # --- Info writer thread (background) ---
        try:
            if InfoWriter is not None:
                self._info_thread = QtCore.QThread(self)
                self._info_writer = InfoWriter()
                self._info_writer.moveToThread(self._info_thread)
                # route writer logs to status panel
                try:
                    self._info_writer.log.connect(self.status_panel.append_line)
                except Exception:
                    pass
                # start hook and listen for write completion so we can trigger PM "Auto" moves
                try:
                    self._info_thread.started.connect(lambda: None)
                    if getattr(self._info_writer, 'write_complete', None) is not None:
                        self._info_writer.write_complete.connect(self._on_info_written)
                except Exception:
                    pass
                self._info_thread.start()
            else:
                self._info_thread = None
                self._info_writer = None
        except Exception:
            self._info_thread = None
            self._info_writer = None
        # PM Auto manager (computes move descriptors; MainWindow emits jogs)
        try:
            self._pm_auto = PMAutoManager(getattr(self, 'pm_panel', None), getattr(self, 'part1', None).rows if getattr(self, 'part1', None) is not None else [], logger=getattr(self, 'status_panel', None).append_line)
        except Exception:
            self._pm_auto = None
        # alignment quick-toggle mappings: addr -> on_position (float)
        # maintain separate mappings for PG and HeNe groups
        self._alignment_pg_onpos = {}
        self._alignment_hene_onpos = {}
        # connect overall_controls alignment switch signals if available
        try:
            if getattr(self, 'overall_controls', None):
                try:
                    if getattr(self.overall_controls, 'alignment_pg_switch_requested', None) is not None:
                        self.overall_controls.alignment_pg_switch_requested.connect(self._on_alignment_pg_switch_requested)
                except Exception:
                    pass
                try:
                    if getattr(self.overall_controls, 'alignment_hene_switch_requested', None) is not None:
                        self.overall_controls.alignment_hene_switch_requested.connect(self._on_alignment_hene_switch_requested)
                except Exception:
                    pass
        except Exception:
            pass
        
        # --- Center layout: 2x3 grid ---------------------------------
        central = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(central)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        # Layout (4 columns left -> right):
        # col0 (leftmost): placeholder_panel (top) / device_tabs (bottom)
        # col1: overall_controls (top) / status_panel (bottom)
        # col2: fire_panel (top) / part2 (stage_control_panel) (bottom)
        # col3 (rightmost): pm_panel (top) / part1 (motor_status_panel) (bottom)

        # Top row (row 0)
        grid.addWidget(self.placeholder_panel, 0, 0)
        grid.addWidget(self.overall_controls, 0, 1)
        grid.addWidget(self.fire_panel, 0, 2)
        grid.addWidget(self.pm_panel, 0, 3)

    # Bottom row (row 1)
    # allow device_tabs to expand so its tab contents are visible
        grid.addWidget(self.device_tabs, 1, 0)
        grid.addWidget(self.status_panel, 1, 1)
        grid.addWidget(self.part2, 1, 2)
        grid.addWidget(self.part1, 1, 3)

        # Column stretch (left -> right): give the rightmost column (motor_status) most space
        # Give the left column a bit more room so the tabs and their contents are visible
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 2)
        grid.setColumnStretch(3, 3)

        # ensure the DeviceTabsPanel is wide enough to show its internal list/form
        try:
            self.device_tabs.setMinimumWidth(260)
        except Exception:
            pass

        # Even row heights (tweak if you want the bottom row taller)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        # Make the central area scrollable so the user can resize the main window
        # arbitrarily and scroll horizontally/vertically when parts are cut off.
        scroll = QtWidgets.QScrollArea()
        # ensure the inner widget keeps its preferred size so scrollbars appear
        central.adjustSize()
        central.setMinimumSize(central.sizeHint())
        scroll.setWidget(central)
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setCentralWidget(scroll)

        # --- Load PM panel settings (if present) -------------------------
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            pm_file = os.path.join(base_dir, "parameters/pm_settings.json")
            # Pass status_panel.append_line as logger callback to get feedback in UI
            try:
                self.pm_panel.load_from_file(pm_file, logger=self.status_panel.append_line)
                # ensure Saved_positions.json values are applied after pm settings
                QtCore.QTimer.singleShot(50, lambda: getattr(self.pm_panel, '_load_saved_values', lambda: None)())
                # react to bypass toggles to move SD to min/max
                try:
                    self.pm_panel.bypass_clicked.connect(self._on_pm_bypass_clicked)
                except Exception:
                    pass
            except Exception:
                # status_panel may not yet be set up — try again slightly later
                QtCore.QTimer.singleShot(50, lambda: getattr(self.pm_panel, 'load_from_file', lambda *a, **k: None)(pm_file, logger=getattr(self.status_panel, 'append_line', None)))
        except Exception:
            pass

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

        # After Zaber opened/discovered we want to open Picomotors; hook the opened signal
        try:
            def _open_pico_after_zaber():
                try:
                    if getattr(self, 'pico_io', None) is not None:
                        QtCore.QMetaObject.invokeMethod(self.pico_io, 'open', QtCore.Qt.ConnectionType.QueuedConnection)
                except Exception:
                    pass
            try:
                self.stage.opened.connect(_open_pico_after_zaber)
            except Exception:
                pass
        except Exception:
            pass

        # --- NewFocus Picomotor I/O thread (start after Zaber opened) ---
        try:
            self.pico_thread = QtCore.QThread(self)
            # dll dir can be configured via device_connections.json; fallback to vendor path
            base_dir = os.path.dirname(os.path.abspath(__file__))
            vendor_bin = r"C:\Program Files\New Focus\New Focus Picomotor Application\Bin"
            self.pico_io = NewFocusPicoIO(dll_dir=vendor_bin)
            self.pico_io.moveToThread(self.pico_thread)

            # UI panel for picomotors will be created and inserted into the device_tabs pico container
            try:
                self.pico_panel = PicoPanel()
                # insert into device tabs
                try:
                    cont = getattr(self.device_tabs, 'pico_container', None)
                    if cont is not None:
                        lay = QtWidgets.QVBoxLayout(cont)
                        lay.setContentsMargins(0,0,0,0)
                        lay.addWidget(self.pico_panel)
                except Exception:
                    pass
                # forward UI requests to IO via queued connections
                self.pico_panel.request_open.connect(lambda: QtCore.QMetaObject.invokeMethod(self.pico_io, 'open', QtCore.Qt.ConnectionType.QueuedConnection))
                self.pico_panel.request_close.connect(lambda: QtCore.QMetaObject.invokeMethod(self.pico_io, 'close', QtCore.Qt.ConnectionType.QueuedConnection))
                self.pico_panel.request_move.connect(lambda adapter, addr, axis, steps: QtCore.QMetaObject.invokeMethod(self.pico_io, 'relative_move', QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(str, adapter), QtCore.Q_ARG(int, addr), QtCore.Q_ARG(int, axis), QtCore.Q_ARG(int, steps)))
                self.pico_panel.request_stop_all.connect(lambda: QtCore.QMetaObject.invokeMethod(self.pico_io, 'stop_all', QtCore.Qt.ConnectionType.QueuedConnection))
                # wire IO moved updates → panel so the panel can update its cached positions
                try:
                    # pico_io.moved(adapter_key, address, axis) will be emitted when a move completes
                    self.pico_io.moved.connect(self.pico_panel._on_io_moved)
                except Exception:
                    pass
            except Exception:
                self.pico_panel = None

            # Route picomotor signals:
            # - opened_count and init_error should go to the global status panel
            # - general log/error messages should appear in the Picomotors panel status area
            try:
                try:
                    # emit a single concise global message when opened_count arrives
                    self.pico_io.opened_count.connect(lambda n: self.status_panel.append_line(f"Picomotor I/O opened; adapters: {n}"))
                except Exception:
                    pass
                try:
                    # initialization-time errors should be visible globally
                    self.pico_io.init_error.connect(self.status_panel.append_line)
                except Exception:
                    pass

                # route general logs/errors to the Picomotors panel when available
                try:
                    if getattr(self, 'pico_panel', None) is not None:
                        self.pico_io.log.connect(self.pico_panel.append_line)
                        self.pico_io.error.connect(self.pico_panel.append_line)
                except Exception:
                    pass

                # when discovered, populate UI lists
                def _on_pico_discovered(items: list):
                    try:
                        # items are dicts {'adapter_key','address','model_serial'}
                        if getattr(self, 'pico_panel', None) is not None:
                            try:
                                self.pico_panel.set_discovered_items(items)
                            except Exception:
                                pass
                    except Exception:
                        pass
                self.pico_io.discovered.connect(_on_pico_discovered)
            except Exception:
                pass

            # start pico thread now but do NOT call open until zaber opened
            self.pico_thread.started.connect(lambda: None)
            self.pico_thread.start()
        except Exception:
            self.pico_thread = None
            self.pico_io = None
            self.pico_panel = None

        # handle connect requests from the DeviceTabsPanel (UI thread)
        try:
            self.device_tabs.connectRequested.connect(self._on_device_connect_requested)
        except Exception:
            pass

        # track pending bypass moves: addr -> pm_index
        self._pending_bypass_moves = {}

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
        # record when the user changes the # Shots so we don't treat the resulting shots_progress(0,N)
        # as a user-requested counter reset; store timestamp in seconds
        try:
            self._last_shots_set_time = 0.0
            self.fire_panel.request_shots.connect(lambda n: setattr(self, '_last_shots_set_time', time.time()))
        except Exception:
            pass
        # wire Reset Counter button -> reset internal state and UI
        try:
            self.fire_panel.request_reset.connect(self._on_reset_counter)
        except Exception:
            pass
        # forward Fire to IO and also handle UI-side bookkeeping in MainWindow
        # For per-shot control, hook request_fire to a MainWindow handler that
        # will orchestrate firing one shot at a time and wait for rename before next.
        self.fire_panel.request_fire.connect(self._on_fire_clicked)

        # worker -> UI
        self.fire_io.status.connect(self.fire_panel.set_status)
        #self.fire_io.shots_progress.connect(self.fire_panel.set_progress)
        self.fire_io.log.connect(self.status_panel.append_line)     # if you have a log area
        self.fire_io.error.connect(self.status_panel.append_line)
        # hook into shots progress to rename output files after single-shot captures
        try:
            self.fire_io.shots_progress.connect(self._on_shots_progress)
            # connect the new single-shot-done signal from the worker (if available)
            try:
                # single_shot_done now provides a float timestamp (seconds since epoch)
                self.fire_io.single_shot_done.connect(self._on_single_shot_done)
            except Exception:
                pass
        except Exception:
            pass

        # thread-safe wiring
        self.req_read.connect(self.stage.read_position_speed, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_abs.connect(self.stage.move_absolute, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_bounds.connect(self.stage.get_limits, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_set_lbound.connect(self.stage.set_lower_limit, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_set_ubound.connect(self.stage.set_upper_limit, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_jog.connect(self.stage.move_delta, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_home.connect(self.stage.home, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_spd.connect(self.stage.set_target_speed, QtCore.Qt.ConnectionType.QueuedConnection)
        self.req_stop.connect(self.stage.stop, QtCore.Qt.ConnectionType.QueuedConnection)
        self.part2.request_move_absolute.connect(self._on_request_move_absolute)
        self.part2.request_home.connect(self._on_request_home)
        self.part2.request_move_delta.connect(self._on_request_move_delta)
        self.part2.request_set_speed.connect(self._on_request_set_speed)
        self.part2.request_set_lbound.connect(self._on_request_set_lbound)
        self.part2.request_set_ubound.connect(self._on_request_set_ubound)

        self.part2.request_move_to_saved.connect(self._on_request_move_to_saved)
        # Stop All request from StageControlPanel: cancel queued saved moves and stop hardware
        try:
            self.part2.request_stop_all.connect(lambda: self._on_request_stop_all())
        except Exception:
            pass
        self._saved_move_queue = []
        self._saved_move_active = False

        # bookkeeping for renaming files produced by cameras/spectrometers
        self._processed_output_files = set()  # full paths already renamed/handled
        self._last_shots_done = 0
        # per-shot orchestration state
        self._per_shot_active = False
        self._per_shot_total = 0
        self._per_shot_current = 0
        # When arming a per-shot sequence the worker may emit shots_progress(0,N).
        # Suppress that immediate zero-reset so the displayed counter isn't cleared when the user fires.
        self._suppress_next_zero_progress = False

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
        # update PM panel Current display if any PM row references this address
        try:
            if hasattr(self, 'pm_panel') and self.pm_panel is not None:
                try:
                    self.pm_panel.update_current_by_address(address, pos)
                except Exception:
                    pass
        except Exception:
            pass

    @QtCore.pyqtSlot(int, float)
    def _on_speed(self, address: int, speed: float):
        self.part1.update_speed(speed, address)
        
    @QtCore.pyqtSlot(int, float, float)
    def _on_bounds(self, address: int, lower: float, upper: float):
        self.part1.update_bounds(lower, upper, address)
        # update stages.json Limit for this address (if present)
        try:
            # find stage by num and update its limit via device_tabs helper
            self.device_tabs.set_limit_for_stage(address, upper)
        except Exception:
            pass

    def _on_stages_edited(self, new_stages: list):
        """Rebuild MotorStatusPanel rows when stages.json changes from the device tabs panel.
        This is a light-weight refresh: rebuild the motors list and replace part1 contents.
        """
        try:
            motors = []
            for s in sorted(new_stages, key=lambda x: int(x.get('num', 0))):
                short = s.get('Abr', '')
                long = s.get('name', '')
                num = int(s.get('num', 0))
                steps = 0
                eng_value = 0.0
                typ = s.get('type', 'Linear')
                unit = 'mm' if typ == 'Linear' else 'deg'
                span = float(s.get('limit', 0.0) or 0.0)
                lbound = 0.0
                ubound = float(s.get('limit', 0.0) or 0.0)
                speed = 50.0 if unit == 'mm' else 90.0
                speed_unit = 'mm/s' if unit == 'mm' else 'deg/s'
                motors.append(MotorInfo(short, long, steps, eng_value, unit, span, lbound, ubound, speed, speed_unit))
            # Refresh part1 in-place to avoid changing layout positions.
            try:
                # MotorStatusPanel provides refresh_motors to update rows in-place
                try:
                    self.part1.refresh_motors(motors)
                except Exception:
                    # fallback: recreate if refresh not available
                    old = self.part1
                    self.part1 = MotorStatusPanel(motors)
                    old.hide()
                # Update stage_control_panel rows and selector
                try:
                    if hasattr(self, 'part2') and hasattr(self.part2, 'refresh_rows'):
                        self.part2.refresh_rows(self.part1.rows)
                except Exception:
                    pass
                # After rebuilding the motor rows, request fresh position/speed/bounds
                # reads for each configured stage so the UI displays real values
                try:
                    for addr, row in enumerate(self.part1.rows, start=1):
                        try:
                            unit = getattr(row.info, 'unit', 'mm') or 'mm'
                        except Exception:
                            unit = 'mm'
                        # schedule immediate read and speed request
                        try:
                            QtCore.QTimer.singleShot(0, lambda a=addr, u=unit: self.req_read.emit(a, u))
                        except Exception:
                            pass
                        
                        # request bounds shortly after to update limits
                        try:
                            QtCore.QTimer.singleShot(50, lambda a=addr, u=unit: self.req_bounds.emit(a, u))
                        except Exception:
                            pass
                except Exception:
                    pass
                # Rebind stop button handlers (remove old connections first)
                try:
                    for addr, row in enumerate(self.part1.rows, start=1):
                        try:
                            row.light_red.clicked.disconnect()
                        except Exception:
                            pass
                        row.light_red.clicked.connect(lambda checked=False, a=addr, u=row.info.unit: self.req_stop.emit(a, u))
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass

    def _on_fire_clicked(self):
        """Called in the UI thread when the Fire button is clicked.
        If Single Shot mode is selected, start watching for new output files to rename after shots complete.
        """
        try:
            # determine selected mode (prefer the panel radios when available)
            mode = 'continuous'
            try:
                if getattr(self.fire_panel, 'rb_single', None) and self.fire_panel.rb_single.isChecked():
                    mode = 'single'
                elif getattr(self.fire_panel, 'rb_burst', None) and self.fire_panel.rb_burst.isChecked():
                    mode = 'burst'
                else:
                    mode = 'continuous'
            except Exception:
                mode = 'continuous'

            # Ensure the fire worker receives the current mode before we queue any fire() calls.
            # This avoids a race where a UI-mode toggle queued set_mode after a queued fire(),
            # leaving the worker still in the previous mode when fire() runs.
            try:
                QtCore.QMetaObject.invokeMethod(self.fire_io, 'set_mode', QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(str, mode))
            except Exception:
                pass

            # Pre-fire checks: output dir & experiment name for single or burst modes
            try:
                if mode in ('single', 'burst'):
                    outdir = (self.overall_controls.dir_edit.text() or '').strip() if getattr(self, 'overall_controls', None) and getattr(self.overall_controls, 'dir_edit', None) else ''
                    exp_name = (self.overall_controls.exp_edit.text() or '').strip() if getattr(self, 'overall_controls', None) and getattr(self.overall_controls, 'exp_edit', None) else ''
                    bads = []
                    import os as _os
                    if not outdir:
                        bads.append('Output directory is empty')
                    else:
                        try:
                            if not _os.path.isdir(outdir):
                                bads.append(f'Output directory does not exist or is not a directory: {outdir}')
                        except Exception:
                            bads.append(f'Invalid output directory: {outdir}')
                    if not exp_name:
                        bads.append('Experiment name is empty')
                    if bads:
                        from PyQt6.QtWidgets import QMessageBox
                        mb = QMessageBox(self)
                        mb.setIcon(QMessageBox.Icon.Warning)
                        mb.setWindowTitle('Pre-fire validation')
                        mb.setText('Pre-fire checks failed:')
                        mb.setInformativeText('\n'.join(bads) + '\n\nDo you want to continue firing?')
                        mb.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes)
                        mb.setDefaultButton(QMessageBox.StandardButton.Cancel)
                        resp = mb.exec()
                        if resp == QMessageBox.StandardButton.Cancel:
                            try: self.status_panel.append_line('Firing cancelled by user due to pre-fire validation failure')
                            except Exception: pass
                            return
                        else:
                            try: self.status_panel.append_line('User chose to continue despite pre-fire validation warnings')
                            except Exception: pass
            except Exception:
                pass

            # PM Auto bounds check only for single-shot mode (performed at click time before any queuing)
            try:
                if mode == 'single' and getattr(self, '_pm_auto', None) is not None:
                    try:
                        violations = self._pm_auto.check_bounds()
                    except Exception:
                        violations = []
                    if violations:
                        # Build a short message summarizing the first few violations
                        msgs = []
                        for v in violations[:5]:
                            relation = 'below Min' if v.get('relation') == 'below' else 'above Max'
                            msgs.append(f"{v.get('pm_name')} {v.get('row_label')} (Addr {v.get('address')}): {v.get('position'):.3f} {relation} [{v.get('min')},{v.get('max')}]")
                        more = ''
                        if len(violations) > 5:
                            more = f"\n...and {len(violations)-5} more"
                        from PyQt6.QtWidgets import QMessageBox
                        mb = QMessageBox(self)
                        mb.setIcon(QMessageBox.Icon.Warning)
                        mb.setWindowTitle("PM Auto bounds warning")
                        mb.setText("One or more PM axes configured for Auto are outside their allowed bounds:")
                        mb.setInformativeText('\n'.join(msgs) + more + '\n\nDo you want to continue firing?')
                        mb.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes)
                        mb.setDefaultButton(QMessageBox.StandardButton.Cancel)
                        resp = mb.exec()
                        if resp == QMessageBox.StandardButton.Cancel:
                            try: self.status_panel.append_line('Firing cancelled by user due to PM Auto bounds violation')
                            except Exception: pass
                            return
                        else:
                            try: self.status_panel.append_line('User chose to continue despite PM Auto bounds violations')
                            except Exception: pass
            except Exception:
                pass

            # Single-mode: start or queue a per-shot loop. The displayed counter is a cumulative tally
            # that is never auto-reset; it increments only after each shot's rename completes.
            if mode == 'single':
                # if a per-shot sequence is already active, queue this request to run when it finishes
                if getattr(self, '_per_shot_active', False):
                    try:
                        # set queued flag so UI will start another sequence when current one fully finishes
                        self._queued_fire_request = True
                        self.status_panel.append_line('Per-shot sequence already running; queued a new sequence to start after completion')
                        # start a watchdog timer to check when the sequence has fully finished
                        try:
                            if getattr(self, '_queued_check_timer', None) is None:
                                t = QtCore.QTimer(self)
                                t.setInterval(250)
                                t.timeout.connect(self._check_and_start_queued_run)
                                t.setSingleShot(False)
                                self._queued_check_timer = t
                                t.start()
                        except Exception:
                            pass
                    except Exception:
                        pass
                    return

                # otherwise start a new per-shot sequence
                try:
                    self._start_per_shot_sequence()
                except Exception as e:
                    try: self.status_panel.append_line(f'Failed to start per-shot sequence: {e}')
                    except Exception: pass
                return

            #Burst: forward to worker fire() which arms burst behavior
            if mode == 'burst':
                # If a burst/save is already active or post-processing pending, queue this request
                if getattr(self, '_burst_save_active', False) or getattr(self, '_info_write_pending', False) or getattr(self, '_per_shot_active', False):
                    try:
                        self._queued_fire_request = True
                        self.status_panel.append_line('Burst already active; queued next burst to start after post-processing')
                        # start watchdog timer to monitor finishing conditions (if not already started)
                        try:
                            if getattr(self, '_queued_check_timer', None) is None:
                                t = QtCore.QTimer(self)
                                t.setInterval(250)
                                t.timeout.connect(self._check_and_start_queued_run)
                                t.setSingleShot(False)
                                self._queued_check_timer = t
                                t.start()
                        except Exception:
                            pass
                    except Exception:
                        pass
                    return

                # queue the fire call on the worker
                try:
                    QtCore.QMetaObject.invokeMethod(self.fire_io, 'fire', QtCore.Qt.ConnectionType.QueuedConnection)
                except Exception:
                    try: self.status_panel.append_line('Failed to queue burst fire()')
                    except Exception: pass

                # After firing, perform burst save: create the Burst_n folder and move/rename matching files
                try:
                    # gather parameters from UI
                    outdir = (self.overall_controls.dir_edit.text() or '').strip() if getattr(self, 'overall_controls', None) and getattr(self.overall_controls, 'dir_edit', None) else ''
                    burst_rel = (self.overall_controls.burst_edit.text() or '').strip() if getattr(self, 'overall_controls', None) and getattr(self.overall_controls, 'burst_edit', None) else ''
                    exp_name = (self.overall_controls.exp_edit.text() or '').strip() if getattr(self, 'overall_controls', None) and getattr(self.overall_controls, 'exp_edit', None) else 'Experiment'
                    # tokens: camera names and spectrometer filenames
                    cams = [str(c.get('Name','')).strip() for c in getattr(self.device_tabs, '_cameras', []) if c.get('Name')]
                    specs = [str(s.get('filename','')).strip() for s in getattr(self.device_tabs, '_spectrometers', []) if s.get('filename')]
                    tokens = cams + specs
                    # use rename wait timeout from settings (camera buffer)
                    camera_buffer_ms = int(getattr(self, '_rename_max_wait_ms', 5000))
                    # estimate burst emission time: shots * (pulse_ms + gap_ms) when available
                    try:
                        shots = int(self.fire_panel.spin_shots.value()) if getattr(self.fire_panel, 'spin_shots', None) else getattr(self.fire_io, '_num_shots', 1)
                    except Exception:
                        shots = getattr(self.fire_io, '_num_shots', 1) if getattr(self, 'fire_io', None) else 1
                    # compute a shorter, conservative wait: shots/10 seconds + camera buffer
                    try:
                        # shots/10 seconds -> convert to ms
                        est_shot_ms = int((float(shots) / 10.0) * 1000.0)
                    except Exception:
                        est_shot_ms = 0
                    # total timeout = estimated shot period + camera buffer
                    timeout_ms = int(camera_buffer_ms + est_shot_ms)
                    poll_ms = int(getattr(self, '_rename_poll_ms', 200)) if getattr(self, '_rename_poll_ms', None) is not None else 200
                    stable_s = float(getattr(self, '_rename_stable_time', 0.3)) if getattr(self, '_rename_stable_time', None) is not None else 0.3
                    # perform burst save (blocking poll similar to single-shot rename)
                    try:
                        # use the current displayed shot counter as the Burst folder index
                        try:
                            current_shot = int(self.fire_panel.disp_counter.value())
                        except Exception:
                            current_shot = None
                        # start burst save (runs in background worker if available)
                        self._handle_burst_save(outdir=outdir, burst_rel=burst_rel, tokens=tokens, experiment=exp_name, timeout_ms=timeout_ms, poll_ms=poll_ms, stable_s=stable_s, burst_index=current_shot)
                    except Exception as e:
                        try: self.status_panel.append_line(f'Burst save failed: {e}')
                        except Exception: pass
                except Exception:
                    pass
                return

            # Continuous: forward to worker (worker treats continuous fire as a no-op/arm)
            try:
                QtCore.QMetaObject.invokeMethod(self.fire_io, 'fire', QtCore.Qt.ConnectionType.QueuedConnection)
            except Exception:
                try: self.status_panel.append_line('Failed to queue continuous fire()')
                except Exception: pass
            return
        except Exception:
            pass

    @QtCore.pyqtSlot(int, int)
    def _on_shots_progress(self, current: int, total: int):
        """Handle shots progress updates from the fire IO.
        Note: shot tally UI is controlled exclusively by MainWindow and only changes after each
        shot completes and its rename is done. We ignore worker shots_progress updates.
        """
        # intentionally ignore shots_progress: UI tally is updated only after per-shot completion
        try:
            return
        except Exception:
            pass

    def _start_per_shot_sequence(self):
        """Initialize and queue the first shot of a per-shot sequence."""
        try:
            try:
                self._rename_experiment = (self.overall_controls.exp_edit.text() or 'Experiment').strip()
            except Exception:
                self._rename_experiment = getattr(self, '_rename_experiment', 'Experiment')

            try:
                shots = int(self.fire_panel.spin_shots.value()) if getattr(self.fire_panel, 'spin_shots', None) else getattr(self.fire_io, '_num_shots', 1)
            except Exception:
                shots = getattr(self.fire_io, '_num_shots', 1)

            # initialize per-shot counters; start from the current displayed tally
            self._per_shot_active = True
            self._per_shot_total = max(1, int(shots))
            try:
                self._per_shot_current = int(self.fire_panel.disp_counter.value())
            except Exception:
                self._per_shot_current = 0

            # compute absolute target tally: stop when displayed counter reaches this value
            try:
                self._per_shot_target = self._per_shot_current + int(self._per_shot_total)
            except Exception:
                self._per_shot_target = self._per_shot_current + int(self._per_shot_total or 1)

            # reset per-run completed counter and enable sequence progress UI
            try:
                self._per_shot_completed_in_run = 0
                self.fire_panel.set_sequence_active(True, int(self._per_shot_total))
                self.fire_panel.set_sequence_progress(0)
            except Exception:
                pass

            # queue first one-shot in the worker
            try:
                QtCore.QMetaObject.invokeMethod(self.fire_io, 'fire_one_shot', QtCore.Qt.ConnectionType.QueuedConnection)
                # keep Fire faded/visually disabled but still clickable (panel manages visual state)
                try:
                    self.fire_panel.set_sequence_active(True, int(self._per_shot_total))
                except Exception:
                    pass
                try: self.status_panel.append_line(f"Per-shot start: current={self._per_shot_current}, total={self._per_shot_total}, target={getattr(self,'_per_shot_target',None)}")
                except Exception: pass
                try: self.status_panel.append_line("Queued first one-shot")
                except Exception: pass
            except Exception:
                try: self.status_panel.append_line('Failed to queue first one-shot')
                except Exception: pass
                self._per_shot_active = False
        except Exception:
            pass

    def _on_reset_counter(self):
        """Reset shot counter and per-shot internal state on user request."""
        try:
            self.fire_panel.disp_counter.setValue(0)
            self._per_shot_current = 0
            self._per_shot_active = False
            try: self._per_shot_target = None
            except Exception: pass
        except Exception:
            pass

    def _on_single_shot_done(self, event_ts: float = None):
        """Called when the fire worker signals that a single shot/pulse finished.
        This runs in the UI thread because the worker emits the signal; perform rename then continue if per-shot active.
        """
        try:
            # perform rename now (best-effort)
            try:
                # set the current shot number used for naming (per-shot)
                try:
                    self._rename_shotnum = int(getattr(self, '_per_shot_current', 0))
                except Exception:
                    pass

                # pass the DAQ event timestamp into the rename so filenames and info share the same ts
                try:
                    self._rename_output_files(event_ts=event_ts)
                except Exception:
                    # fallback to no-ts
                    try:
                        self._rename_output_files()
                    except Exception as e:
                        try: self.status_panel.append_line(f"Rename on-shot failed: {e}")
                        except Exception: pass
            except Exception as e:
                try: self.status_panel.append_line(f"Rename on-shot failed: {e}")
                except Exception: pass
        except Exception as e:
            try: self.status_panel.append_line(f"Rename on-shot failed: {e}")
            except Exception: pass

        # If we are orchestrating per-shot and haven't finished, trigger the next shot
        if getattr(self, '_per_shot_active', False):
            self._per_shot_current += 1
            # update per-run completed counter
            try:
                self._per_shot_completed_in_run += 1
                # update progress bar UI if present
                try:
                    total = int(getattr(self, '_per_shot_total', 1))
                    self.fire_panel.set_sequence_progress(int(min(self._per_shot_completed_in_run, total)))
                except Exception:
                    pass
            except Exception:
                pass
            # update display
            try: self.fire_panel.disp_counter.setValue(self._per_shot_current)
            except Exception: pass

            # continue until displayed counter reaches absolute target
            target = getattr(self, '_per_shot_target', None)
            if target is not None and self._per_shot_current < target:
                # schedule the next shot depending on whether any PM Auto is enabled
                try:
                    interval_ms = int(getattr(self, '_rename_max_wait_ms', 1000))
                    # If any PM Auto is enabled, wait until autos finish (do not use interval)
                    if self._any_pm_auto_enabled():
                        try:
                            self._next_shot_when_ready = True
                            self.status_panel.append_line('Next shot will start after PM Auto moves complete (ignoring Interval)')
                        except Exception:
                            pass
                    else:
                        # schedule the next shot after the configured Interval (ms)
                        def _queue_next():
                            try:
                                QtCore.QMetaObject.invokeMethod(self.fire_io, 'fire_one_shot', QtCore.Qt.ConnectionType.QueuedConnection)
                            except Exception:
                                try: self.status_panel.append_line("Failed to queue next one-shot")
                                except Exception: pass
                        QtCore.QTimer.singleShot(interval_ms, _queue_next)
                except Exception:
                    try: self.status_panel.append_line("Failed to schedule next one-shot")
                    except Exception: pass
            else:
                # finished
                self._per_shot_active = False
                try: self._per_shot_target = None
                except Exception: pass
                try: self.status_panel.append_line("Per-shot sequence complete")
                except Exception: pass
                # sequence fully complete (renames + info writer dispatched). Fire remains faded
                # until all post-processing (info writes + autos) finish. Check whether we can
                # finish the sequence now (might start a queued run if present).
                try:
                    self._try_finish_sequence()
                except Exception:
                    pass
                # if user queued another Fire while this run was active, start it now
                try:
                    if getattr(self, '_queued_fire_request', False):
                        # leave the queued flag set so the run will start when post-processing completes
                        try:
                            QtCore.QTimer.singleShot(50, lambda: self.status_panel.append_line('Queued run will start after current post-processing completes'))
                        except Exception:
                            pass
                except Exception:
                    pass

    def _rename_output_files(self, event_ts: float = None):
        # Delegate to file_renamer.rename_shot_files for maintainability and testability
        try:
            outdir = (self.overall_controls.dir_edit.text() or '').strip()
            cams = [str(c.get('Name','')).strip() for c in getattr(self.device_tabs, '_cameras', []) if c.get('Name')]
            specs = [str(s.get('filename','')).strip() for s in getattr(self.device_tabs, '_spectrometers', []) if s.get('filename')]
            tokens = cams + specs
            shotnum = getattr(self, '_rename_shotnum', 1)
            exp = getattr(self, '_rename_experiment', 'Experiment')
            max_wait_ms = getattr(self, '_rename_max_wait_ms', 5000)
            poll_ms = getattr(self, '_rename_poll_ms', 200)
            stable_time = getattr(self, '_rename_stable_time', 0.3)

            renamed, processed = file_renamer.rename_shot_files(
                outdir=outdir,
                tokens=tokens,
                shotnum=shotnum,
                experiment=exp,
                timeout_ms=max_wait_ms,
                poll_ms=poll_ms,
                stable_s=stable_time,
                processed_paths=self._processed_output_files,
                logger=getattr(self.status_panel, 'append_line', None),
                write_info=False,
                info_label='Info',
                event_ts=event_ts,
            )
            # keep processed set updated (function already mutates the set passed in)
            try:
                self._processed_output_files.update(processed)
            except Exception:
                pass
            # Build a mapping token -> newfull for files we renamed
            try:
                renamed_map = {}
                for old, new in renamed:
                    nb = os.path.basename(new).lower()
                    for t in tokens:
                        if t and t.lower() in nb:
                            renamed_map[t] = new
                            break
            except Exception:
                renamed_map = {}

            # Delegate Info + SHOT_LOG composition and write to the InfoWriter (background) so the UI
            # thread remains thin. Prepare a compact payload containing only serializable fields.
            try:
                payload = {
                    'outdir': outdir,
                    'experiment': exp,
                    'shotnum': int(shotnum),
                    'renamed': renamed,
                    'part_rows': [(getattr(r.info, 'short', ''), float(getattr(r.info, 'eng_value', 0.0) or 0.0)) for r in getattr(self.part1, 'rows', [])],
                    'cameras': getattr(self.device_tabs, '_cameras', []) or [],
                    'spectrometers': getattr(self.device_tabs, '_spectrometers', []) or [],
                    'event_ts': event_ts,
                }

                # mark info write pending so Fire stays disabled until post-processing completes
                try:
                    self._info_write_pending = True
                    self._pending_auto_addresses.clear()
                    # keep sequence UI active; MainWindow will enable Fire only when all post-processing completes
                    try:
                        self.fire_panel.set_sequence_active(True, int(getattr(self, '_per_shot_total', 1)))
                    except Exception:
                        pass
                except Exception:
                    pass
                if getattr(self, '_info_writer', None) is not None and getattr(self._info_writer, 'write_info_and_shot_log', None) is not None:
                    try:
                        QtCore.QMetaObject.invokeMethod(self._info_writer, 'write_info_and_shot_log', QtCore.Qt.ConnectionType.QueuedConnection,
                                                        QtCore.Q_ARG(dict, payload))
                    except Exception:
                        # fallback: direct call (best-effort)
                        try:
                            self._info_writer.write_info_and_shot_log(payload)
                        except Exception as e:
                            try: self.status_panel.append_line(f"Failed to schedule info write: {e}")
                            except Exception: pass
                else:
                    # No background writer available — run synchronously via a local InfoWriter instance
                    try:
                        tmp = InfoWriter()
                        tmp.write_info_and_shot_log(payload)
                        # if synchronous, emulate write_complete behavior so autos run
                        try:
                            self._on_info_written(dict(payload or {}))
                        except Exception:
                            pass
                    except Exception as e:
                        try: self.status_panel.append_line(f"Failed to write shot info (fallback): {e}")
                        except Exception: pass
            except Exception as e:
                try: self.status_panel.append_line(f"Failed to dispatch shot info: {e}")
                except Exception: pass
        except Exception as e:
            try: self.status_panel.append_line(f"Rename exception: {e}")
            except Exception: pass

    def _handle_burst_save(self, outdir: str, burst_rel: str, tokens: list, experiment: str, timeout_ms: int = 5000, poll_ms: int = 200, stable_s: float = 0.3, burst_index: int | None = None):
        """Create the burst folder and move/rename files matching tokens into it.

        Behavior:
        - Ensure outdir/burst_rel exists (create if necessary).
        - Create a new subfolder Burst_n where n = 0..max existing + 1.
        - Find files in outdir whose filenames contain any token (case-insensitive).
        - Sort matches by modification time (earliest first) and move them into Burst_n.
        - Rename moved files to {experiment}_Burst_{tokenlabel}_{j}{ext} where j increments per token starting at 0.
        """
        try:
            # Use a background worker to perform the burst save so the UI thread is not blocked.
            try:
                from utilities.file_renamer import BurstSaveWorker
            except Exception:
                BurstSaveWorker = None
            # If no worker available (PyQt missing), fall back to synchronous call
            if BurstSaveWorker is None:
                try:
                    from utilities.file_renamer import save_burst_files
                    moved, processed, burst_dir = save_burst_files(
                        outdir=outdir,
                        burst_rel=burst_rel,
                        tokens=tokens,
                        experiment=experiment,
                        timeout_ms=timeout_ms,
                        poll_ms=poll_ms,
                        stable_s=stable_s,
                        burst_index=burst_index,
                        processed_paths=getattr(self, '_processed_output_files', set()),
                        logger=getattr(self.status_panel, 'append_line', None)
                    )
                    try:
                        if hasattr(self, '_processed_output_files') and processed is not None:
                            self._processed_output_files.update(processed)
                    except Exception:
                        pass
                except Exception as e:
                    try: self.status_panel.append_line(f'Burst save failed (sync fallback): {e}')
                    except Exception: pass
                return

            # Create worker and thread
            try:
                worker = BurstSaveWorker(
                    outdir=outdir,
                    burst_rel=burst_rel,
                    tokens=tokens,
                    experiment=experiment,
                    timeout_ms=timeout_ms,
                    poll_ms=poll_ms,
                    stable_s=stable_s,
                    burst_index=burst_index,
                    # pass a shallow copy so the worker doesn't mutate the UI thread set concurrently
                    processed_paths=set(getattr(self, '_processed_output_files', set()) or set()),
                    logger=getattr(self.status_panel, 'append_line', None),
                )
            except Exception as e:
                try: self.status_panel.append_line(f'Burst save: failed to construct worker: {e}')
                except Exception: pass
                return

            t = QtCore.QThread(self)
            # ensure we keep references so GC doesn't collect them prematurely
            try:
                self._burst_worker_thread = t
                self._burst_worker = worker
            except Exception:
                pass

            worker.moveToThread(t)

            # Mark burst active and disable Fire button while worker runs
            try:
                self._burst_save_active = True
                self._set_fire_button_enabled(False)
            except Exception:
                pass

            # forward worker log messages to status panel in UI thread
            try:
                worker.log.connect(getattr(self.status_panel, 'append_line', lambda m: None))
            except Exception:
                pass

            # on finished, update processed set and dispatch info write similar to sync path
            def _on_burst_finished(moved, processed, burst_dir):
                try:
                    try:
                        if hasattr(self, '_processed_output_files') and processed is not None:
                            self._processed_output_files.update(processed)
                    except Exception:
                        pass

                    # compute shot_log_dir and payload for InfoWriter
                    try:
                        shot_log_dir = os.path.join(outdir, burst_rel) if burst_rel else outdir
                    except Exception:
                        shot_log_dir = outdir

                    payload = {
                        'outdir': burst_dir or outdir,
                        'experiment': experiment,
                        'shotnum': int(burst_index) if burst_index is not None else 0,
                        'renamed': moved or [],
                        'part_rows': [(getattr(r.info, 'short', ''), float(getattr(r.info, 'eng_value', 0.0) or 0.0)) for r in getattr(self.part1, 'rows', [])],
                        'cameras': getattr(self.device_tabs, '_cameras', []) or [],
                        'spectrometers': getattr(self.device_tabs, '_spectrometers', []) or [],
                        'event_ts': None,
                        'burst_shots': int(getattr(self.fire_panel, 'spin_shots', None).value()) if getattr(self.fire_panel, 'spin_shots', None) is not None else None,
                        'shot_log_dir': shot_log_dir,
                    }
                    try:
                        self._info_write_pending = True
                        self._pending_auto_addresses.clear()
                    except Exception:
                        pass

                    if getattr(self, '_info_writer', None) is not None and getattr(self._info_writer, 'write_info_and_shot_log', None) is not None:
                        try:
                            QtCore.QMetaObject.invokeMethod(self._info_writer, 'write_info_and_shot_log', QtCore.Qt.ConnectionType.QueuedConnection,
                                                            QtCore.Q_ARG(dict, payload))
                        except Exception:
                            try:
                                self._info_writer.write_info_and_shot_log(payload)
                            except Exception as e:
                                try: self.status_panel.append_line(f"Failed to schedule burst info write: {e}")
                                except Exception: pass
                    else:
                        try:
                            tmpw = InfoWriter()
                            tmpw.write_info_and_shot_log(payload)
                            try:
                                self._on_info_written(dict(payload or {}))
                            except Exception:
                                pass
                        except Exception as e:
                            try: self.status_panel.append_line(f"Failed to write burst info (fallback): {e}")
                            except Exception: pass
                except Exception as e:
                    try: self.status_panel.append_line(f"Burst finished handler exception: {e}")
                    except Exception: pass
                finally:
                    # clean up worker/thread
                    try:
                        worker.deleteLater()
                    except Exception:
                        pass
                    try:
                        t.quit()
                        t.wait(500)
                    except Exception:
                        pass

            def _on_burst_error(msg):
                try:
                    self.status_panel.append_line(f"Burst save worker error: {msg}")
                except Exception:
                    pass
                try:
                    worker.deleteLater()
                except Exception:
                    pass
                try:
                    t.quit()
                    t.wait(500)
                except Exception:
                    pass

            # connect signals
            try:
                worker.finished.connect(_on_burst_finished)
                worker.error.connect(_on_burst_error)
                t.started.connect(worker.run)
                t.start()
            except Exception as e:
                try: self.status_panel.append_line(f'Burst save: failed to start worker thread: {e}')
                except Exception: pass
                try:
                    worker.deleteLater()
                except Exception:
                    pass
                try:
                    t.quit()
                    t.wait(200)
                except Exception:
                    pass
            return
        except Exception:
            pass

    @QtCore.pyqtSlot(str, int)
    def _on_device_connect_requested(self, port: str, baud: int):
        """Handle connect requests from DeviceTabsPanel.
        This runs in the main/UI thread and will invoke methods on the Stage I/O via queued connections.
        Sequence:
          - request the worker to close current conn
          - update port/baud in worker (queued)
          - request open (which triggers discover)
        After discovery, _on_discovered will run; if no devices were found we'll show a MessageBox.
        """
        try:
            self.status_panel.append_line(f"Connecting to {port} @ {baud}...")
            # ask worker to close current connection (queued)
            try:
                QtCore.QMetaObject.invokeMethod(self.stage, 'close', QtCore.Qt.ConnectionType.QueuedConnection)
            except Exception:
                pass
            # set port/baud on the worker thread (queued)
            try:
                QtCore.QMetaObject.invokeMethod(self.stage, 'set_port_baud', QtCore.Qt.ConnectionType.QueuedConnection,
                                                QtCore.Q_ARG(str, port), QtCore.Q_ARG(int, int(baud)))
            except Exception:
                # fallback: call attribute directly (best-effort)
                try:
                    self.stage.set_port_baud(port, int(baud))
                except Exception:
                    pass
            # request open (which will emit opened -> discover)
            try:
                QtCore.QMetaObject.invokeMethod(self.stage, 'open', QtCore.Qt.ConnectionType.QueuedConnection)
            except Exception:
                pass
            # We'll check in _on_discovered whether devices were found. If none, show a dialog.
            # To ensure the user sees a message if discovery finds nothing, connect a one-shot
            # slot to the discovered signal that will display a popup when devices empty.
            def _show_if_empty(devs: list):
                try:
                    if not devs:
                        QtWidgets.QMessageBox.warning(self, 'Connect failed', f'No Zaber stages found on {port} at {baud} baud.')
                except Exception:
                    pass
                try:
                    self.stage.discovered.disconnect(_show_if_empty)
                except Exception:
                    pass

            try:
                self.stage.discovered.connect(_show_if_empty)
            except Exception:
                pass
        except Exception as e:
            try:
                self.status_panel.append_line(f"Connect request failed: {e}")
            except Exception:
                pass

    @QtCore.pyqtSlot(int, bool)
    def _on_moving(self, address: int, is_moving: bool):
        if 1 <= address <= len(self.part1.rows):
            row = self.part1.rows[address - 1]
            row.light_green.set_on(is_moving)
        # If this address corresponds to the PG or HeNe configured addresses, set their lights to moving (yellow)
        try:
            if is_moving:
                # check PG mapping
                if int(address) in getattr(self, '_alignment_pg_onpos', {}):
                    try:
                        if getattr(self, 'overall_controls', None) is not None:
                            self.overall_controls.set_alignment_pg_moving()
                    except Exception:
                        pass
                # check HeNe mapping
                if int(address) in getattr(self, '_alignment_hene_onpos', {}):
                    try:
                        if getattr(self, 'overall_controls', None) is not None:
                            self.overall_controls.set_alignment_hene_moving()
                    except Exception:
                        pass
        except Exception:
            pass
        # If this address corresponds to any PM SD row, disable its bypass button while moving
        try:
            if hasattr(self, 'pm_panel') and self.pm_panel is not None:
                try:
                    # disable when moving, enable when not
                    self.pm_panel.set_bypass_enabled_for_address(address, not bool(is_moving))
                except Exception:
                    pass
        except Exception:
            pass

    @QtCore.pyqtSlot(dict)
    def _on_info_written(self, payload: dict):
        """Called when Info + SHOT_LOG have been written for a shot.
        If any PM mirror group has Auto checked, move its Y stage by Dist in the
        selected direction (Pos/Neg). This is performed as a relative move (req_jog).
        """
        try:
            # Diagnostic log: record that the info write completed and payload keys
            try:
                sn = payload.get('shotnum', None) if isinstance(payload, dict) else None
                self.status_panel.append_line(f"InfoWriter completed for shot {sn}")
            except Exception:
                pass
            # Clear pending info-write state so UI can re-enable Fire when appropriate.
            try:
                self._info_write_pending = False
            except Exception:
                pass

            # Only perform PM Auto moves when in a per-shot sequence (single-shot mode).
            # Otherwise, skip PM Auto but still proceed to finish sequence and persist state.
            single_mode_ui = False
            try:
                single_mode_ui = bool(getattr(self, 'fire_panel', None) and getattr(self.fire_panel, 'rb_single', None) and self.fire_panel.rb_single.isChecked())
            except Exception:
                single_mode_ui = False

            if getattr(self, '_per_shot_active', False) or single_mode_ui:
                # Compute PM Auto moves using PMAutoManager and emit jogs
                try:
                    moves = []
                    if getattr(self, '_pm_auto', None) is not None:
                        try:
                            moves = self._pm_auto.generate_moves()
                        except Exception:
                            moves = []
                    auto_addresses = set()
                    for m in moves:
                        try:
                            addr = int(m.get('address'))
                            delta = float(m.get('delta', 0.0))
                            unit = str(m.get('unit', ''))
                            log = str(m.get('log', ''))
                            try:
                                if log:
                                    self.status_panel.append_line(log)
                            except Exception:
                                pass
                            auto_addresses.add(addr)
                            QtCore.QTimer.singleShot(0, lambda a=addr, d=delta, u=unit: self.req_jog.emit(a, float(d), u))
                        except Exception:
                            continue
                    try:
                        self._pending_auto_addresses.update(auto_addresses)
                    except Exception:
                        pass
                except Exception:
                    pass

            # After info write completes, attempt to finish the overall sequence (may start queued run)
            try:
                self._try_finish_sequence()
            except Exception:
                pass
            # After info write completes, persist shot counter
            try:
                if getattr(self, '_save_shot_counter', None) is not None:
                    try:
                        self._save_shot_counter()
                    except Exception:
                        pass
            except Exception:
                pass
            # If this info write was for a burst, clear burst-active and increment shot counter
            if isinstance(payload, dict) and payload.get('burst_shots', None) is not None:
                try:
                    # clear active flag
                    self._burst_save_active = False
                except Exception:
                    pass
                try:
                    # increment displayed shot counter once for the completed burst
                    if hasattr(self, 'fire_panel') and getattr(self.fire_panel, 'disp_counter', None) is not None:
                        self.fire_panel.disp_counter.setValue(int(self.fire_panel.disp_counter.value()) + 1)
                        try:
                            if getattr(self, '_save_shot_counter', None) is not None:
                                self._save_shot_counter()
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    # re-enable the fire button unless other post-processing prevents it
                    if not getattr(self, '_info_write_pending', False) and not getattr(self, '_pending_auto_addresses', set()):
                        try:
                            self._set_fire_button_enabled(True)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    @QtCore.pyqtSlot(int, float)
    def _on_moved(self, address: int, final_pos: float):
        # Protect the handler so any unexpected errors don't prevent saved-move continuation.
        try:
            row = self.part1.rows[address - 1]
            unit = row.info.unit
            prec = 2 if unit == "deg" else 6
            self.status_panel.append_line(
                f"Move complete on Address {address}: {final_pos:.{prec}f} {unit} (reading back...)"
            )
            # Request a fresh read for this address
            try:
                self.req_read.emit(address, unit)
            except Exception:
                pass

            # Update PM panel Act. indicator only when a move completes
            try:
                if hasattr(self, 'pm_panel') and self.pm_panel is not None:
                    try:
                        self.pm_panel.set_act_indicator_by_address(address, final_pos)
                    except Exception:
                        pass
            except Exception:
                pass

            # if this address was a pending bypass move, flip the bypass button visual for that PM
            try:
                pm_index = self._pending_bypass_moves.pop(int(address), None)
                if pm_index is not None:
                    try:
                        mg = [self.pm_panel.pm1, self.pm_panel.pm2, self.pm_panel.pm3][pm_index - 1]
                        # toggle the visual engaged state
                        new_state = not mg.bypass.is_engaged()
                        mg.bypass.set_engaged(new_state)
                        self.status_panel.append_line(f"PM{pm_index} bypass visual updated after move → {'ENGAGE' if new_state else 'BYPASS'}")
                    except Exception:
                        pass
            except Exception:
                pass

            # if this address was a pending auto move, clear and possibly re-enable Fire
            try:
                if int(address) in getattr(self, '_pending_auto_addresses', set()):
                    try:
                        self._pending_auto_addresses.discard(int(address))
                    except Exception:
                        pass
                    try:
                        # After a moved event, attempt to finish the overall sequence (may start queued run)
                        self._try_finish_sequence()
                    except Exception:
                        pass
            except Exception:
                pass
            # If this address is configured for alignment quick toggles, update its indicator light
            try:
                # check PG mapping first
                pg_on = None
                try:
                    pg_on = self._alignment_pg_onpos.get(int(address), None)
                except Exception:
                    pg_on = None
                if pg_on is not None:
                    try:
                        if abs(float(final_pos) - float(pg_on)) <= 1e-4:
                            try:
                                if getattr(self, 'overall_controls', None) and getattr(self.overall_controls, 'set_alignment_pg_light_state', None):
                                    self.overall_controls.set_alignment_pg_light_state(True)
                            except Exception:
                                pass
                        else:
                            try:
                                if getattr(self, 'overall_controls', None) and getattr(self.overall_controls, 'set_alignment_pg_light_state', None):
                                    self.overall_controls.set_alignment_pg_light_state(False)
                            except Exception:
                                pass
                    except Exception:
                        pass
                # check HeNe mapping
                hene_on = None
                try:
                    hene_on = self._alignment_hene_onpos.get(int(address), None)
                except Exception:
                    hene_on = None
                if hene_on is not None:
                    try:
                        if abs(float(final_pos) - float(hene_on)) <= 1e-4:
                            try:
                                if getattr(self, 'overall_controls', None) and getattr(self.overall_controls, 'set_alignment_hene_light_state', None):
                                    self.overall_controls.set_alignment_hene_light_state(True)
                            except Exception:
                                pass
                        else:
                            try:
                                if getattr(self, 'overall_controls', None) and getattr(self.overall_controls, 'set_alignment_hene_light_state', None):
                                    self.overall_controls.set_alignment_hene_light_state(False)
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception as e:
            # Log unexpected handler exceptions but keep going — important so sequences don't stall
            try:
                self.status_panel.append_line(f"_on_moved handler exception: {e}")
            except Exception:
                pass
        # Regardless of handler success, if a Move-to-Saved sequence is active, continue to the next queued move now
        try:
            if getattr(self, '_saved_move_active', False):
                # schedule a small delay so the readback and UI update can occur first
                try:
                    QtCore.QTimer.singleShot(50, self._dequeue_and_move_next)
                except Exception:
                    try:
                        self._dequeue_and_move_next()
                    except Exception:
                        pass
        except Exception:
            pass

    def _set_fire_button_enabled(self, enabled: bool) -> None:
        """Helper to enable/disable the GUI Fire button on the FireControlsPanel.
        Respects the FireControlsPanel internal mode rules (button disabled in continuous mode).
        """
        try:
            # Fire button should only be enabled if panel mode permits it (single/burst)
            if not getattr(self, 'fire_panel', None):
                return
            # Use the panel's _update_fire_button_state logic but override enabled state
            try:
                # If the panel mode doesn't allow firing, keep it disabled regardless
                mode = getattr(self.fire_panel, '_current_mode', 'continuous')
                allowed = (mode in ('single', 'burst'))
                self.fire_panel.btn_fire.setEnabled(bool(enabled) and allowed)
                # reflect faded or active appearance
                if bool(enabled) and allowed:
                        # hide sequence UI when re-enabling Fire (sequence finished)
                        try:
                            if getattr(self, 'fire_panel', None):
                                self.fire_panel.set_sequence_active(False)
                        except Exception:
                            pass
                        self.fire_panel.btn_fire.setStyleSheet("background:#D30000; color:white; font-weight:700;")
                else:
                    self.fire_panel.btn_fire.setStyleSheet("background:#444444; color:#9a9a9a; font-weight:600;")
            except Exception:
                pass
        except Exception:
            pass

    def _try_finish_sequence(self):
        """Check whether the per-shot sequence and post-processing are fully finished.
        If so, re-enable the Fire button and start any queued run.
        This centralizes the logic so it can be safely called from any completion handler.
        """
        try:
            if getattr(self, '_pending_auto_addresses', None) is None:
                self._pending_auto_addresses = set()
            # If we are waiting to start the next shot only after autos/info-writes, handle that first
            try:
                if getattr(self, '_next_shot_when_ready', False):
                    # If no info write and no pending autos, queue the next one-shot after a short buffer
                    if not getattr(self, '_info_write_pending', False) and not self._pending_auto_addresses:
                        try:
                            self._next_shot_when_ready = False
                            # wait post-auto buffer after moves complete before starting the next shot
                            try:
                                buffer_ms = int(getattr(self, 'fire_panel', None).spin_post_auto.value()) if getattr(self, 'fire_panel', None) and getattr(self.fire_panel, 'spin_post_auto', None) else 500
                            except Exception:
                                buffer_ms = 500
                            QtCore.QTimer.singleShot(buffer_ms, lambda: QtCore.QMetaObject.invokeMethod(self.fire_io, 'fire_one_shot', QtCore.Qt.ConnectionType.QueuedConnection))
                            self.status_panel.append_line(f'Queued next one-shot after PM Auto completion ({buffer_ms} ms buffer)')
                            return
                        except Exception:
                            pass
            except Exception:
                pass

            # If sequence fully finished (no per-shot active) and no pending post-processing, re-enable Fire
            if not self._pending_auto_addresses and not getattr(self, '_info_write_pending', False) and not getattr(self, '_per_shot_active', False):
                try:
                    self._set_fire_button_enabled(True)
                except Exception:
                    pass
                # if a queued run exists, start it and clear the queued flag
                try:
                    if getattr(self, '_queued_fire_request', False):
                        self._queued_fire_request = False
                        try:
                            buffer_ms = int(getattr(self, 'fire_panel', None).spin_post_auto.value()) if getattr(self, 'fire_panel', None) and getattr(self.fire_panel, 'spin_post_auto', None) else 50
                        except Exception:
                            buffer_ms = 50
                        # schedule start of queued run after the Post-Auto buffer
                        QtCore.QTimer.singleShot(buffer_ms, lambda: self._on_fire_clicked())
                        try:
                            self.status_panel.append_line(f'Queued run will start after Post-Auto buffer ({buffer_ms} ms)')
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    def _any_pm_auto_enabled(self) -> bool:
        """Return True if any PM mirror group's Auto checkbox is checked."""
        try:
            for mg in (getattr(self, 'pm_panel', None) and getattr(self.pm_panel, 'pm1', None), getattr(self, 'pm_panel', None) and getattr(self.pm_panel, 'pm2', None), getattr(self, 'pm_panel', None) and getattr(self.pm_panel, 'pm3', None)):
                try:
                    if mg and getattr(mg, 'auto', None) and mg.auto.isChecked():
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def _check_and_start_queued_run(self):
        """Watchdog called periodically while a queued run exists. If finish conditions
        are met, start the queued run and stop the timer."""
        try:
            # If there's no queued run, stop the timer
            if not getattr(self, '_queued_fire_request', False):
                try:
                    if getattr(self, '_queued_check_timer', None) is not None:
                        self._queued_check_timer.stop()
                        self._queued_check_timer = None
                except Exception:
                    pass
                return

            # If the sequence and post-processing are finished, start queued run
            if not getattr(self, '_per_shot_active', False) and not getattr(self, '_info_write_pending', False) and (not getattr(self, '_pending_auto_addresses', set())):
                try:
                    # clear timer first
                    if getattr(self, '_queued_check_timer', None) is not None:
                        self._queued_check_timer.stop()
                        self._queued_check_timer = None
                except Exception:
                    pass
                try:
                    self._queued_fire_request = False
                    try:
                        buffer_ms = int(getattr(self, 'fire_panel', None).spin_post_auto.value()) if getattr(self, 'fire_panel', None) and getattr(self.fire_panel, 'spin_post_auto', None) else 50
                    except Exception:
                        buffer_ms = 50
                    QtCore.QTimer.singleShot(buffer_ms, lambda: self._on_fire_clicked())
                    try:
                        self.status_panel.append_line(f'Queued run will start after Post-Auto buffer ({buffer_ms} ms)')
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass

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
        # After homing, the hardware will report a position; schedule a short delayed
        # check to update the PM panel Act. indicator using the newly read position
        # (the read_position_speed above will trigger _on_position which updates
        # row.info.eng_value; wait a bit then read that value to drive the Act. light).
        try:
            QtCore.QTimer.singleShot(250, lambda a=address: (
                None if not (hasattr(self, 'pm_panel') and hasattr(self, 'part1')) else self.pm_panel.set_act_indicator_by_address(a, float(self.part1.rows[a - 1].info.eng_value))
            ))
        except Exception:
            pass
        # If a Move-to-Saved sequence is active, continue to the next queued move now
        try:
            if getattr(self, '_saved_move_active', False):
                try:
                    QtCore.QTimer.singleShot(50, self._dequeue_and_move_next)
                except Exception:
                    try:
                        self._dequeue_and_move_next()
                    except Exception:
                        pass
        except Exception:
            pass

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
    
    @QtCore.pyqtSlot(str)
    def _on_request_move_to_saved(self, preset_name: str):
        """
        Read Saved_positions.json, find the block by name, and queue moves in its 'order'.
        Moves run one-by-one using the existing StageIO.move_absolute (blocking in I/O thread).
        """
        base_dir = os.path.dirname(os.path.abspath(__file__))
        filename= os.path.join(base_dir, "parameters/Saved_positions.json")
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.status_panel.append_line(f"Move-to-saved failed: cannot read {filename}: {e}")
            return

        if preset_name not in data:
            self.status_panel.append_line(f'Move-to-saved: preset "{preset_name}" not found.')
            return

        payload = data[preset_name]
        stages = payload.get("stages", [])
        if not stages:
            self.status_panel.append_line(f'Move-to-saved: preset "{preset_name}" has no stages.')
            return

        # Build an ordered queue. Support optional per-stage 'pre_moves' which are
        # executed before the visible final position. Queue entries are dicts:
        #   { 'address': int, 'target': float|None, 'home': bool, 'hidden': bool }
        try:
            ordered = sorted(stages, key=lambda s: s.get("order", 10**9))
        except Exception:
            ordered = stages

        pre_queue = []
        final_queue = []
        for st in ordered:
            name = str(st.get("name", "")).strip()
            pos  = st.get("position", None)
            if name == "" or pos is None:
                continue
            # find matching row by short name
            row = next((r for r in self.part1.rows if r.info.short == name), None)
            if row is None:
                self.status_panel.append_line(f'  ↳ Skipping "{name}" (no matching stage in Part 1).')
                continue
            address = getattr(row, "index", None)
            if not isinstance(address, int):
                self.status_panel.append_line(f'  ↳ Skipping "{name}" (invalid address mapping).')
                continue
            try:
                target_mm = float(pos)
            except Exception:
                self.status_panel.append_line(f'  ↳ Skipping "{name}" (position not numeric).')
                continue

            # Expand optional pre_moves (executed before any final targets)
            pre_moves = st.get('pre_moves', []) or []
            for pm in pre_moves:
                try:
                    pm_addr = None
                    pm_home = False
                    pm_target = None
                    pm_hidden = True
                    if isinstance(pm, dict):
                        if 'address' in pm:
                            try:
                                pm_addr = int(pm.get('address'))
                            except Exception:
                                pm_addr = None
                        if pm_addr is None and 'name' in pm:
                            pname = str(pm.get('name', '')).strip()
                            prow = next((r for r in self.part1.rows if r.info.short == pname), None)
                            if prow is not None:
                                pm_addr = getattr(prow, 'index', None)
                        pm_home = bool(pm.get('home', False))
                        if 'position' in pm:
                            try:
                                pm_target = float(pm.get('position'))
                            except Exception:
                                pm_target = None
                        pm_hidden = bool(pm.get('hidden', True))
                    else:
                        # simple string entry = name
                        pname = str(pm).strip()
                        prow = next((r for r in self.part1.rows if r.info.short == pname), None)
                        if prow is not None:
                            pm_addr = getattr(prow, 'index', None)
                    if pm_addr is None:
                        continue
                    pre_queue.append({'address': int(pm_addr), 'target': pm_target, 'home': pm_home, 'hidden': pm_hidden})
                except Exception:
                    continue

            # Collect the visible final target to run after all pre-moves
            final_queue.append({'address': int(address), 'target': float(target_mm), 'home': False, 'hidden': False})

        # If there are no pre-moves and no final moves, nothing to do
        if not pre_queue and not final_queue:
            self.status_panel.append_line(f'Move-to-saved: nothing to do for "{preset_name}".')
            return

        # Build combined queue for execution (pre_moves first)
        combined_queue = pre_queue + final_queue

        # --- Confirmation dialog: show current and target positions for all moves ---
        try:
            from PyQt6.QtWidgets import QMessageBox
            # Build lines describing each move in order
            lines = []
            idx = 1
            for ent in combined_queue:
                try:
                    addr = int(ent.get('address'))
                    # obtain row and current position
                    row = None
                    try:
                        if 1 <= addr <= len(self.part1.rows):
                            row = self.part1.rows[addr - 1]
                    except Exception:
                        row = None
                    label = getattr(row.info, 'short', f'Addr{addr}') if row is not None else f'Addr{addr}'
                    unit = getattr(row.info, 'unit', 'mm') if row is not None else 'mm'
                    cur = None
                    try:
                        cur = float(getattr(row.info, 'eng_value', 0.0))
                    except Exception:
                        cur = None
                    if ent.get('home', False) or (ent.get('target', None) is None and ent.get('home', False)):
                        target_str = 'HOME'
                    else:
                        t = ent.get('target', None)
                        try:
                            target_str = f"{float(t):.6f} {unit}"
                        except Exception:
                            target_str = str(t)
                    if cur is None:
                        cur_str = 'unknown'
                    else:
                        # choose precision based on unit
                        prec = 2 if unit == 'deg' else 3
                        cur_str = f"{cur:.{prec}f} {unit}"
                    hidden_tag = ' (pre-move)' if ent.get('hidden', False) else ''
                    lines.append(f"{idx}. {label} (Addr {addr}): {cur_str} → {target_str}{hidden_tag}")
                    idx += 1
                except Exception:
                    continue

            msg = "About to perform the following moves (in order):\n\n" + "\n".join(lines)
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Icon.Warning)
            mb.setWindowTitle('Confirm Move-to-Saved')
            mb.setText('Move-to-Saved: confirmation')
            mb.setInformativeText(msg)
            mb.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok)
            mb.setDefaultButton(QMessageBox.StandardButton.Ok)
            resp = mb.exec()
            if resp == QMessageBox.StandardButton.Cancel:
                try:
                    self.status_panel.append_line('Move-to-saved cancelled by user')
                except Exception:
                    pass
                return
        except Exception:
            # If dialog fails for any reason, continue without confirmation
            pass

        # Start queued execution: perform all pre_moves first, then all final targets
        queue = combined_queue
        self._saved_move_queue = queue
        self._saved_move_active = True
        try:
            visible_count = sum(1 for q in final_queue if not q.get('hidden', False))
        except Exception:
            visible_count = len(final_queue)
        total_count = len(queue)
        self.status_panel.append_line(f'Move-to-saved "{preset_name}": queued {visible_count} visible move(s) ({total_count} total incl. pre-moves).')
        self._dequeue_and_move_next()

    def _dequeue_and_move_next(self):
        """Kick off the next move in the queue, or finish if empty."""
        if not self._saved_move_active:
            return
        if not self._saved_move_queue:
            self._saved_move_active = False
            self.status_panel.append_line("Move-to-saved: sequence complete.")
            return
        entry = self._saved_move_queue.pop(0)
        # support both legacy tuple entries and new dict entries
        if isinstance(entry, dict):
            address = int(entry.get('address'))
            target_pos = entry.get('target', None)
            is_home = bool(entry.get('home', False))
            hidden = bool(entry.get('hidden', False))
        else:
            try:
                address, target_pos = entry
            except Exception:
                self.status_panel.append_line(f"Move-to-saved: invalid queue entry {entry}; skipping")
                QtCore.QTimer.singleShot(0, self._dequeue_and_move_next)
                return
            is_home = (float(target_pos) == 0.0)
            hidden = False

        unit = self.part1.rows[address - 1].info.unit
        try:
            if is_home or (target_pos is not None and float(target_pos) == 0.0):
                # Queue a home request on the Stage I/O thread
                if not hidden:
                    self.status_panel.append_line(f" → Queuing HOME for Address {address} (0.0)")
                try:
                    self.req_home.emit(address)
                except Exception:
                    # fallback: try invoking on the worker (best-effort non-blocking)
                    try:
                        QtCore.QMetaObject.invokeMethod(self.stage, 'home', QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(int, address))
                    except Exception:
                        pass
            else:
                # Queue an absolute move on the Stage I/O thread
                if not hidden:
                    self.status_panel.append_line(f" → Queuing move Address {address} to {float(target_pos):.6f} {unit}")
                try:
                    self.req_abs.emit(address, float(target_pos), unit)
                except Exception:
                    # fallback: invoke via queued connection to avoid blocking UI
                    try:
                        QtCore.QMetaObject.invokeMethod(self.stage, 'move_absolute', QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(int, address), QtCore.Q_ARG(float, float(target_pos)), QtCore.Q_ARG(str, unit))
                    except Exception:
                        pass
        except Exception as e:
            self.status_panel.append_line(f"Move error on Address {address}: {e}")
        # Do NOT advance the queue here; wait for moved/homed events to continue

    @QtCore.pyqtSlot(int, bool)
    def _on_pm_bypass_clicked(self, pm_index: int, engaged: bool):
        """Handle PM bypass toggles. When BYPASS (False) clicked, move SD to its min.
        When ENGAGE (True) clicked, move SD to its max. pm_index is 1..3.
        """
        try:
            # find the mirror group and its SD row
            mg = [self.pm_panel.pm1, self.pm_panel.pm2, self.pm_panel.pm3][pm_index - 1]
            sd_row = mg.row_sd
            # use row.sd min/max values and row.stage_num for address
            addr = int(sd_row.stage_num.value())
            if addr <= 0:
                self.status_panel.append_line(f"PM{pm_index} SD has invalid stage number ({addr}); cannot move.")
                return
            # The 'engaged' parameter is the new checked state after the click.
            # The requirement is: when the button was showing 'BYPASS' and is clicked -> move to MIN,
            # and when it was showing 'ENGAGE' and is clicked -> move to MAX. The previous state is
            # therefore the inverse of the new state.
            prev_was_bypass = bool(not engaged)
            # New behavior: when the button showed 'BYPASS' (prev_was_bypass=True) move to MIN;
            # when it showed 'ENGAGE' move to MAX.
            if prev_was_bypass:
                target = sd_row.min.value()
            else:
                target = sd_row.max.value()
            unit = 'mm'  # SD axes use mm in MotorInfo mapping; this should match part1 rows' unit if needed
            self.status_panel.append_line(f"PM{pm_index} bypass click (was {'BYPASS' if prev_was_bypass else 'ENGAGE'}) → moving SD (addr {addr}) to {target:.6f} {unit}")
            # schedule a move via req_abs (thread-safe queued signal)
            # record as pending so we flip the bypass visual only after the move completes
            try:
                self._pending_bypass_moves[int(addr)] = int(pm_index)
            except Exception:
                pass
            self.req_abs.emit(addr, float(target), unit)
        except Exception as e:
            try: self.status_panel.append_line(f"Failed to handle PM bypass click: {e}")
            except Exception: pass

    @QtCore.pyqtSlot(int, float, bool)
    def _on_alignment_switch_requested(self, address: int, target: float, on: bool):
        # Generic wrapper kept for compatibility; schedule the move only
        try:
            try:
                unit = self.part1.rows[address - 1].info.unit
            except Exception:
                unit = 'mm'
            try:
                self.status_panel.append_line(f"Alignment Quick {'ON' if on else 'OFF'} → Addr {address}, Target {float(target):.6f} {unit}")
            except Exception:
                pass
            try:
                self.req_abs.emit(int(address), float(target), unit)
            except Exception:
                try:
                    QtCore.QMetaObject.invokeMethod(self.stage, 'move_absolute', QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(int, int(address)), QtCore.Q_ARG(float, float(target)), QtCore.Q_ARG(str, unit))
                except Exception:
                    pass
        except Exception:
            pass

    @QtCore.pyqtSlot(int, float, bool)
    def _on_alignment_pg_switch_requested(self, address: int, target: float, on: bool):
        try:
            if on:
                self._alignment_pg_onpos[int(address)] = float(target)
            else:
                try:
                    if int(address) in self._alignment_pg_onpos:
                        del self._alignment_pg_onpos[int(address)]
                except Exception:
                    pass
        except Exception:
            pass
        # reuse generic scheduling
        try:
            unit = self.part1.rows[address - 1].info.unit
        except Exception:
            unit = 'mm'
        try:
            self.status_panel.append_line(f"PG Alignment Quick {'ON' if on else 'OFF'} → Addr {address}, Target {float(target):.6f} {unit}")
        except Exception:
            pass
        try:
            self.req_abs.emit(int(address), float(target), unit)
        except Exception:
            try:
                QtCore.QMetaObject.invokeMethod(self.stage, 'move_absolute', QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(int, int(address)), QtCore.Q_ARG(float, float(target)), QtCore.Q_ARG(str, unit))
            except Exception:
                pass

    @QtCore.pyqtSlot(int, float, bool)
    def _on_alignment_hene_switch_requested(self, address: int, target: float, on: bool):
        try:
            if on:
                self._alignment_hene_onpos[int(address)] = float(target)
            else:
                try:
                    if int(address) in self._alignment_hene_onpos:
                        del self._alignment_hene_onpos[int(address)]
                except Exception:
                    pass
        except Exception:
            pass
        # reuse generic scheduling
        try:
            unit = self.part1.rows[address - 1].info.unit
        except Exception:
            unit = 'mm'
        try:
            self.status_panel.append_line(f"HeNe Alignment Quick {'ON' if on else 'OFF'} → Addr {address}, Target {float(target):.6f} {unit}")
        except Exception:
            pass
        try:
            self.req_abs.emit(int(address), float(target), unit)
        except Exception:
            try:
                QtCore.QMetaObject.invokeMethod(self.stage, 'move_absolute', QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(int, int(address)), QtCore.Q_ARG(float, float(target)), QtCore.Q_ARG(str, unit))
            except Exception:
                pass

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
        # Shutdown info writer thread if present
        try:
            if getattr(self, '_info_writer', None) is not None:
                try:
                    QtCore.QMetaObject.invokeMethod(self._info_writer, 'close', QtCore.Qt.ConnectionType.QueuedConnection)
                except Exception:
                    try: self._info_writer.close()
                    except Exception: pass
        except Exception:
            pass
        try:
            if getattr(self, '_info_thread', None) is not None:
                try:
                    self._info_thread.quit()
                    self._info_thread.wait(500)
                except Exception:
                    pass
        except Exception:
            pass
        # --- Graceful shutdown for Picomotor I/O thread ---
        try:
            if getattr(self, 'pico_io', None) is not None:
                try:
                    # ask pico worker to close (queued)
                    QtCore.QMetaObject.invokeMethod(self.pico_io, 'close', QtCore.Qt.ConnectionType.QueuedConnection)
                except Exception:
                    try:
                        self.pico_io.close()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if getattr(self, 'pico_thread', None) is not None:
                try:
                    self.pico_thread.quit()
                    # wait up to 1000 ms for thread to finish
                    self.pico_thread.wait(1000)
                except Exception:
                    pass
        except Exception:
            pass
        super().closeEvent(a0)
        # Save PM panel settings on exit (best-effort)
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            pm_file = os.path.join(base_dir, "parameters/pm_settings.json")
            try:
                self.pm_panel.save_to_file(pm_file, logger=self.status_panel.append_line)
            except Exception:
                # fallback: attempt without logger
                try: self.pm_panel.save_to_file(pm_file)
                except Exception: pass
        except Exception:
            pass

        # InfoWriter was initialized in __init__; nothing to do here.

    @QtCore.pyqtSlot()
    def _on_request_stop_all(self):
        """Handle Stop All: cancel any queued Move-to-Saved sequence and send stop to all stages."""
        try:
            # Cancel saved-move queue immediately so no further queued moves will run
            try:
                self._saved_move_queue = []
                self._saved_move_active = False
            except Exception:
                pass
            # Emit stop for every configured stage (part1.rows are 0-indexed, addresses start at 1)
            try:
                for addr, row in enumerate(getattr(self.part1, 'rows', []) , start=1):
                    try:
                        unit = getattr(row.info, 'unit', 'mm') or 'mm'
                        # schedule stop on I/O thread via queued signal
                        QtCore.QTimer.singleShot(0, lambda a=addr, u=unit: self.req_stop.emit(a, u))
                    except Exception:
                        pass
                try:
                    self.status_panel.append_line('Stop All: issued stop to all stages and cleared queued moves')
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass

    # ---- Shot counter persistence helpers ----
    def _on_shot_config_saved(self, val: int):
        """Handler called when the Fire panel Configure button saves a new value."""
        try:
            try:
                if hasattr(self, 'fire_panel') and getattr(self.fire_panel, 'disp_counter', None) is not None:
                    self.fire_panel.disp_counter.setValue(int(val))
            except Exception:
                pass
            try:
                self._save_shot_counter()
            except Exception:
                pass
        except Exception:
            pass

    def _load_shot_counter(self):
        """Load shot counter from parameters/shot_counter.json (best-effort)."""
        try:
            f = getattr(self, '_shot_counter_file', None)
            if not f:
                return
            if not os.path.exists(f):
                return
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    j = json.load(fh)
                    v = int(j.get('shot_counter', 0)) if isinstance(j, dict) else 0
            except Exception:
                v = 0
            try:
                if hasattr(self, 'fire_panel') and getattr(self.fire_panel, 'disp_counter', None) is not None:
                    self.fire_panel.disp_counter.setValue(int(v))
            except Exception:
                pass
        except Exception:
            pass

    def _save_shot_counter(self):
        """Persist the current displayed shot counter to parameters/shot_counter.json."""
        try:
            f = getattr(self, '_shot_counter_file', None)
            if not f:
                return
            # ensure directory exists
            try:
                os.makedirs(os.path.dirname(f), exist_ok=True)
            except Exception:
                pass
            try:
                v = int(self.fire_panel.disp_counter.value()) if getattr(self, 'fire_panel', None) and getattr(self.fire_panel, 'disp_counter', None) else 0
            except Exception:
                v = 0
            # write atomically: write to temp then replace
            try:
                tmp = f + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as fh:
                    json.dump({'shot_counter': int(v)}, fh)
                try:
                    os.replace(tmp, f)
                except Exception:
                    # fallback to non-atomic write
                    with open(f, 'w', encoding='utf-8') as fh:
                        json.dump({'shot_counter': int(v)}, fh)
            except Exception:
                pass
        except Exception:
            pass

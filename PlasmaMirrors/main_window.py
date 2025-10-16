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
from panels.overall_control_panel import SavingPanel
import os
import json
import time
from datetime import datetime
from utilities.file_info_writer import InfoWriter
import utilities.file_renamer as file_renamer

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
                self._info_thread.started.connect(lambda: None)
                self._info_thread.start()
            else:
                self._info_thread = None
                self._info_writer = None
        except Exception:
            self._info_thread = None
            self._info_writer = None
        
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

            # Single-mode: start a per-shot loop. The displayed counter is a cumulative tally
            # that is never auto-reset; it increments only after each shot's rename completes.
            if mode == 'single':
                # don't allow overlapping sequences
                if getattr(self, '_per_shot_active', False):
                    try: self.status_panel.append_line('Per-shot sequence already running; ignoring Fire')
                    except Exception: pass
                    return

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

                # queue first one-shot in the worker
                try:
                    QtCore.QMetaObject.invokeMethod(self.fire_io, 'fire_one_shot', QtCore.Qt.ConnectionType.QueuedConnection)
                    try: self.status_panel.append_line(f"Per-shot start: current={self._per_shot_current}, total={self._per_shot_total}, target={getattr(self,'_per_shot_target',None)}")
                    except Exception: pass
                    try: self.status_panel.append_line("Queued first one-shot")
                    except Exception: pass
                except Exception:
                    try: self.status_panel.append_line('Failed to queue first one-shot')
                    except Exception: pass
                    self._per_shot_active = False
                return

            #Burst: forward to worker fire() which arms burst behavior
            if mode == 'burst':
                try:
                    QtCore.QMetaObject.invokeMethod(self.fire_io, 'fire', QtCore.Qt.ConnectionType.QueuedConnection)
                except Exception:
                    try: self.status_panel.append_line('Failed to queue burst fire()')
                    except Exception: pass
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
            # update display
            try: self.fire_panel.disp_counter.setValue(self._per_shot_current)
            except Exception: pass

            # continue until displayed counter reaches absolute target
            target = getattr(self, '_per_shot_target', None)
            if target is not None and self._per_shot_current < target:
                # schedule the next shot after the configured Interval (ms) regardless of rename/save success
                try:
                    interval_ms = int(getattr(self, '_rename_max_wait_ms', 1000))
                    def _queue_next():
                        try:
                            QtCore.QMetaObject.invokeMethod(self.fire_io, 'fire_one_shot', QtCore.Qt.ConnectionType.QueuedConnection)
                        except Exception:
                            try: self.status_panel.append_line("Failed to queue next one-shot")
                            except Exception: pass
                    # use QTimer.singleShot to wait interval_ms before firing next shot
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
                    except Exception as e:
                        try: self.status_panel.append_line(f"Failed to write shot info (fallback): {e}")
                        except Exception: pass
            except Exception as e:
                try: self.status_panel.append_line(f"Failed to dispatch shot info: {e}")
                except Exception: pass
        except Exception as e:
            try: self.status_panel.append_line(f"Rename exception: {e}")
            except Exception: pass

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

    @QtCore.pyqtSlot(int, float)
    def _on_moved(self, address: int, final_pos: float):
        row = self.part1.rows[address - 1]
        unit = row.info.unit
        prec = 2 if unit == "deg" else 6
        self.status_panel.append_line(
            f"Move complete on Address {address}: {final_pos:.{prec}f} {unit} (reading back...)"
        )
        self.req_read.emit(address, unit)
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

        # Build an ordered queue: [(address, target_mm), ...]
        # Map stage 'name' to our Part1 rows by row.info.short and take row.index as address.
        try:
            # keep defined order field; default to large if missing
            ordered = sorted(stages, key=lambda s: s.get("order", 10**9))
        except Exception:
            ordered = stages

        queue = []
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
            queue.append((address, target_mm))

        if not queue:
            self.status_panel.append_line(f'Move-to-saved: nothing to do for "{preset_name}".')
            return

        # Start queued execution
        self._saved_move_queue = queue
        self._saved_move_active = True
        self.status_panel.append_line(f'Move-to-saved "{preset_name}": queued {len(queue)} move(s).')
        self._dequeue_and_move_next()

    def _dequeue_and_move_next(self):
        """Kick off the next move in the queue, or finish if empty."""
        if not self._saved_move_active:
            return
        if not self._saved_move_queue:
            self._saved_move_active = False
            self.status_panel.append_line("Move-to-saved: sequence complete.")
            return
        address, target_pos = self._saved_move_queue.pop(0)
        unit = self.part1.rows[address - 1].info.unit
        self.status_panel.append_line(f" → Moving Address {address} to {target_pos:.6f} {unit}")
        try:
            self.stage.move_absolute(address, target_pos, unit)  # runs in StageIO thread, emits 'moved' + 'position'
        except Exception as e:
            self.status_panel.append_line(f"Move error on Address {address}: {e}")
        # attempt to keep going
        QtCore.QTimer.singleShot(0, self._dequeue_and_move_next)

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

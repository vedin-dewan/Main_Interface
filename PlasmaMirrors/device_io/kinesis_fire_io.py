# device_io/kinesis_fire_io.py
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Optional

from PyQt6 import QtCore
from collections import deque
import json

# -------- Optional: point this to your Kinesis install if needed --------
KINESIS_DLL_DIR: Optional[str] = r"C:\Program Files\Thorlabs\Kinesis"  # or None

# -------------------- NI-DAQ --------------------
try:
    import nidaqmx
    from nidaqmx.constants import LineGrouping
    _HAVE_DAQ = True
except Exception:
    _HAVE_DAQ = False

# -------------------- Kinesis (pythonnet/.NET) --------------------
try:
    if KINESIS_DLL_DIR:
        sys.path.append(KINESIS_DLL_DIR)
    import clr  # pythonnet
    clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
    clr.AddReference("Thorlabs.MotionControl.KCube.SolenoidCLI")
    from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
    from Thorlabs.MotionControl.KCube.SolenoidCLI import KCubeSolenoid, SolenoidStatus
    _HAVE_KINESIS = True
except Exception:
    _HAVE_KINESIS = False


@dataclass
class FireConfig:
    serial: Optional[str] = None                  # e.g. "68000239" or None to auto-pick
    out_pin_shutter: str = "Dev1/port0/line0"
    out_pin_cam: str = "Dev1/port0/line2"
    out_pin_spec: str = "Dev1/port0/line3"
    input_trigger: str = "Dev1/PFI0"
    poll_period_s: float = 0.02                   # ~20 ms
    start_enabled: bool = False                   # start with shutter enabled?
    # Single-shot train timing (applies ONLY to Single mode, N in succession)
    pulse_ms: int = 200                           # high time per shot
    gap_ms: int = 200                             # low time between shots
    single_waits_for_edge: bool = True            # if True: start train at next falling edge


class KinesisFireIO(QtCore.QObject):
    """
    GUI-agnostic controller for a Thorlabs KSC101 shutter + NI-DAQ digital I/O.

    Modes:
      - continuous: shutter held open; camera/spec follow inverted external trigger
      - single:     when Fire() pressed, emit N pulses in succession (N = set_num_shots).
                    If cfg.single_waits_for_edge=True, the train starts on the next
                    falling edge of the trigger; otherwise it starts immediately.
      - burst:      when Fire() pressed, count N falling edges and then disarm; while armed,
                    camera/spec follow inverted trigger and shutter is held enabled.

    Runs in its own thread; nothing blocks the GUI thread.
    """
    # ---- Signals to the UI / logger ----
    log = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    connected = QtCore.pyqtSignal(str)           # serial string
    status = QtCore.pyqtSignal(str)              # human-readable status line
    shots_progress = QtCore.pyqtSignal(int, int) # (current, total)
    # Emitted when a single externally-requested shot completes (one pulse finished)
    # The signal carries a float timestamp (seconds since epoch) obtained when the DAQ write/read
    # completed and the shot is considered executed.
    single_shot_done = QtCore.pyqtSignal(float)

    # ---------- lifecycle ----------
    def __init__(self, cfg: FireConfig):
        super().__init__()
        self.cfg = cfg
        self.dev = None
        self.out_task = None
        self.in_task = None
        self.serial: Optional[str] = None
        # runtime state
        # Start in a safe manual state (manual operating mode, shutter off)
        # instead of auto-starting in single-shot mode with shutter open.
        # Use internal mode 'manual' so the poll loop will keep the device
        # in manual/off state until an explicit set_mode() is called.
        self._mode: str = "manual"         # internal: 'manual' | public: 'continuous' | 'single' | 'burst'
        self._num_shots: int = 1
        self._fire_requested: bool = False
        self._burst_count: int = 0
        self._last_trig: Optional[int] = None

        # single-train state machine
        self._in_single_sequence: bool = False
        self._single_remaining: int = 0
        # one-shot state
        self._one_shot_active = False
        # one-shot state complete

        # --- Diagnostics (lightweight) ---
        # Use a small in-memory ring buffer to record recent events for debugging.
        # Disabled by default to avoid overhead; enable via enable_diagnostics(True).
        self._diag_enabled = False
        self._diag_capacity = 4096
        self._diag_buf = deque(maxlen=self._diag_capacity)

    # ---- Slots callable from UI thread (queued to our worker thread) ----
    @QtCore.pyqtSlot()
    def open(self):
        """Initialize Kinesis + NI-DAQ and start the poll timer."""
        # Kinesis
        if not _HAVE_KINESIS:
            self.error.emit("Kinesis/pythonnet not available. Install 'pythonnet' and Kinesis DLLs.")
            return
        try:
            DeviceManagerCLI.BuildDeviceList()
            self._diag_event('open_step', {'step': 'BuildDeviceList'})
            serials = self._discover_serials()
            self._diag_event('open_step', {'step': 'discover_serials', 'serials': serials})
            if self.cfg.serial and self.cfg.serial not in serials:
                self.serial = self.cfg.serial
            else:
                self.serial = self.cfg.serial or (serials[0] if serials else None)
            if not self.serial:
                raise RuntimeError("No KSC101 detected. Close Kinesis GUI, replug USB, check drivers.")

            self.dev = KCubeSolenoid.CreateKCubeSolenoid(self.serial)
            self.dev.Connect(self.serial)
            self._diag_event('kinesis_connected', {'serial': self.serial})
            if not self.dev.IsSettingsInitialized():
                self.dev.WaitForSettingsInitialized(10000)
            self.dev.StartPolling(int(self.cfg.poll_period_s * 1000 / 2) or 5)
            time.sleep(0.2)
            self.dev.EnableDevice()
            time.sleep(0.1)
            # Default safe state: place the KSC101 in manual mode and ensure
            # the shutter is closed/off. This avoids leaving the solenoid
            # energized or in single-shot mode on application start.
            self._set_mode_internal("manual")
            self._set_shutter_off()
            self._diag_event('kinesis_safe_state_set', {'mode': 'manual', 'shutter': 'off'})
            # Seed last trigger value so edge detection works immediately.
            try:
                val = self._read_trigger()
                self._last_trig = val
            except Exception:
                self._last_trig = None
            self.connected.emit(self.serial)
            self.log.emit(f"KSC101 connected (serial {self.serial}).")
        except Exception as e:
            self._diag_event('open_error', {'error': str(e)})
            self.error.emit(f"Kinesis open failed: {e}")
            self.dev = None

        # NI-DAQ
        if not _HAVE_DAQ:
            self.error.emit("NI-DAQ not available. Install 'nidaqmx' and NI drivers.")
            self.out_task = None
            self.in_task = None
        else:
            try:
                self.out_task = nidaqmx.Task()
                self.out_task.do_channels.add_do_chan(
                    f"{self.cfg.out_pin_shutter}, {self.cfg.out_pin_cam}, {self.cfg.out_pin_spec}",
                    line_grouping=LineGrouping.CHAN_PER_LINE
                )
                self.in_task = nidaqmx.Task()
                self.in_task.di_channels.add_di_chan(self.cfg.input_trigger)
                self._write_outputs(0, 0, 0)
                self._diag_event('daq_out_init', {})
            except Exception as e:
                self._diag_event('daq_open_error', {'error': str(e)})
                self.error.emit(f"NI-DAQ open failed: {e}")
                self.out_task = None
                self.in_task = None

        # no diagnostic logging here

        # Poll timer (runs in this worker thread)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(int(self.cfg.poll_period_s * 1000))
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._diag_event('timer_started', {'interval_ms': int(self.cfg.poll_period_s * 1000)})
        self.status.emit(f"Ready (mode: {self._mode}, serial: {self.serial or 'n/a'})")

    @QtCore.pyqtSlot()
    def close(self):
        """Stop timer and release hardware."""
        try:
            if getattr(self, "timer", None):
                self.timer.stop()
        except Exception:
            pass
        self._abort_single_sequence()
        try:
            self._write_outputs(0, 0, 0)
        except Exception:
            pass
        for t in ("in_task", "out_task"):
            task = getattr(self, t, None)
            if task is not None:
                try: task.stop()
                except Exception: pass
                try: task.close()
                except Exception: pass
                setattr(self, t, None)
        try:
            if getattr(self, "dev", None) is not None:
                self.dev.DisableDevice()
                self.dev.StopPolling()
                self.dev.Disconnect(True)
                self.dev = None
        except Exception:
            pass
        self.status.emit("Fire I/O stopped.")

    @QtCore.pyqtSlot(str)
    def set_mode(self, mode: str):
        mode = mode.strip().lower()
        if mode not in ("continuous", "single", "burst"):
            self.error.emit(f"Unknown mode: {mode}")
            return
        # (debug logging removed)
        # leaving a single sequence mid-stream? abort it safely
        if self._in_single_sequence and mode != "single":
            self._abort_single_sequence()
        self._mode = mode
        # pre-configure device state; tick does the rest
        if mode == "continuous":
            self._set_mode_internal("manual")
            self._set_shutter_on()
        else:
            self._set_mode_internal("triggered")
            self._set_shutter_on()
        # Reset transient arm state so toggling modes doesn't inherit stale requests
        try:
            self._fire_requested = False
            self._burst_count = 0
            # clear any lingering one-shot active flag so tick isn't blocked when switching modes
            try:
                self._one_shot_active = False
            except Exception:
                pass
            # initialize last trigger state to the current input so falling-edge detection is consistent
            try:
                val = self._read_trigger()
                self._last_trig = val
            except Exception:
                self._last_trig = None
            # ensure outputs are in known state (no accidental arming)
            try:
                self._write_outputs(0, 0, 0)
            except Exception:
                pass
        except Exception:
            pass
        self.status.emit(f"Mode set to {mode}")

    @QtCore.pyqtSlot(int)
    def set_num_shots(self, n: int):
        """Unified shot count for BOTH Single (N pulses) and Burst (N edges)."""
        self._num_shots = max(1, int(n))
        self.shots_progress.emit(0, self._num_shots)
        self.log.emit(f"# Shots set to {self._num_shots}")

    # Back-compat with any caller still sending only-burst
    @QtCore.pyqtSlot(int)
    def set_burst_count(self, n: int):
        self.set_num_shots(n)

    @QtCore.pyqtSlot()
    def fire(self):
        """Arm single/burst or no-op in continuous."""
        # (debug logging removed)
        if self._mode == "continuous":
            self.log.emit("Fire (continuous): device follows external trigger; nothing to arm.")
            return
        # If single doesn't wait for edge and we're idle, start immediately.
        if self._mode == "single" and not self.cfg.single_waits_for_edge:
            self._start_single_sequence(self._num_shots)
            return
        # Otherwise, arm and let _tick handle edge detection / burst counting.
        self._fire_requested = True
        self._burst_count = 0
        self.shots_progress.emit(0, self._num_shots)
        try:
            self._diag_event('fire_armed', {'mode': self._mode, 'num_shots': self._num_shots})
        except Exception:
            pass
        # Arm state: ensure the Kinesis device is in triggered mode and the
        # shutter is enabled immediately so the first shot or burst isn't missed
        # while waiting for the periodic poll.
        try:
            # put device into triggered mode and enable shutter
            try:
                self._set_mode_internal("triggered")
            except Exception:
                pass
            try:
                self._set_shutter_on()
            except Exception:
                pass
        except Exception:
            pass
        # Ensure DAQ outputs reflect the armed condition immediately as well.
        try:
            val = self._read_trigger()
            if val is None:
                # safe default: enable shutter, leave cameras/spec lines low
                try: self._write_outputs(1, 0, 0)
                except Exception: pass
            else:
                try: self._write_outputs(1, 1 - val, 1 - val)
                except Exception: pass
        except Exception:
            pass
        self.status.emit(f"Armed ({self._mode})")
        try:
            self._diag_event('fire_arm_complete', {'val': val if 'val' in locals() else None})
        except Exception:
            pass

    # ---------- internals ----------
    def _discover_serials(self) -> list[str]:
        ser = set()
        try:
            if hasattr(KCubeSolenoid, "GetDeviceList"):
                ser |= set(list(KCubeSolenoid.GetDeviceList()))
        except Exception:
            pass
        try:
            ser |= set(list(DeviceManagerCLI.GetDeviceList(KCubeSolenoid.DevicePrefix)))
        except Exception:
            pass
        try:
            all_list = list(DeviceManagerCLI.GetDeviceList())
            prefix = str(getattr(KCubeSolenoid, "DevicePrefix", "68"))
            ser |= {s for s in all_list if str(s).startswith(prefix)}
        except Exception:
            pass
        return sorted(ser)

    def _set_mode_internal(self, mode_key: str):
        if self.dev is None:
            return
        try:
            if mode_key == "manual":
                self.dev.SetOperatingMode(SolenoidStatus.OperatingModes.Manual)
            else:
                self.dev.SetOperatingMode(SolenoidStatus.OperatingModes.Triggered)
            # Let the device apply its operating mode before changing state.
            try:
                time.sleep(0.02)
            except Exception:
                pass
            try:
                self._diag_event('kinesis_set_mode', {'mode_key': mode_key})
            except Exception:
                pass
        except Exception as e:
            try:
                self._diag_event('kinesis_set_mode_error', {'error': str(e)})
            except Exception:
                pass
            self.error.emit(f"Kinesis SetOperatingMode failed: {e}")

    def _set_shutter_on(self):
        if self.dev is None:
            return
        try:
            self.dev.SetOperatingState(SolenoidStatus.OperatingStates.Active)
            # Small pause to ensure the hardware reflects the new state
            try:
                time.sleep(0.02)
            except Exception:
                pass
            try:
                self._diag_event('kinesis_set_state', {'state': 'active'})
            except Exception:
                pass
        except Exception as e:
            try:
                self._diag_event('kinesis_set_state_error', {'error': str(e)})
            except Exception:
                pass
            self.error.emit(f"Kinesis SetOperatingState(Active) failed: {e}")

    def _set_shutter_off(self):
        if self.dev is None:
            return
        try:
            self.dev.SetOperatingState(SolenoidStatus.OperatingStates.Inactive)
            # Small pause to ensure the hardware reflects the new state
            try:
                time.sleep(0.02)
            except Exception:
                pass
            try:
                self._diag_event('kinesis_set_state', {'state': 'inactive'})
            except Exception:
                pass
        except Exception as e:
            try:
                self._diag_event('kinesis_set_state_error', {'error': str(e)})
            except Exception:
                pass
            self.error.emit(f"Kinesis SetOperatingState(Inactive) failed: {e}")

    def _write_outputs(self, shutter: int, cam: int, spec: int):
        try:
            vals = [bool(shutter), bool(cam), bool(spec)]
        except Exception:
            vals = [False, False, False]

        if self.out_task is None:
            return
        try:
            self.out_task.write(vals)
            try:
                self._diag_event('daq_write', {'vals': [int(bool(v)) for v in vals]})
            except Exception:
                pass
        except Exception as e:
            try:
                self._diag_event('daq_write_error', {'error': str(e)})
            except Exception:
                pass
            self.error.emit(f"NI-DAQ write failed: {e}")

    def _read_trigger(self) -> Optional[int]:
        if self.in_task is None:
            return None
        try:
            val = int(bool(self.in_task.read()))
            try:
                self._diag_event('daq_read', {'val': val})
            except Exception:
                pass
            return val
        except Exception as e:
            try:
                self._diag_event('daq_read_error', {'error': str(e)})
            except Exception:
                pass
            self.error.emit(f"NI-DAQ read failed (will retry): {e}")
            try:
                self.in_task.close()
            except Exception:
                pass
            try:
                self.in_task = nidaqmx.Task()
                self.in_task.di_channels.add_di_chan(self.cfg.input_trigger)
            except Exception:
                self.in_task = None
            return None

    # ---- Diagnostics API ----
    def _diag_event(self, ev_type: str, payload: dict | None = None) -> None:
        """Record a small timestamped event in the ring buffer when diagnostics enabled."""
        try:
            if not getattr(self, '_diag_enabled', False):
                return
            entry = {'ts': time.time(), 'ev': str(ev_type), 'payload': payload or {}}
            try:
                self._diag_buf.append(entry)
            except Exception:
                # buffer append must not raise
                pass
        except Exception:
            pass

    @QtCore.pyqtSlot(bool)
    def enable_diagnostics(self, ena: bool) -> None:
        try:
            self._diag_enabled = bool(ena)
            if self._diag_enabled:
                try:
                    self._diag_buf.clear()
                except Exception:
                    pass
            try:
                self.log.emit(f"Diagnostics {'enabled' if self._diag_enabled else 'disabled'}")
            except Exception:
                pass
        except Exception:
            pass

    def get_diagnostics(self) -> list:
        """Return a shallow copy of current diagnostic events (fast)."""
        try:
            return list(self._diag_buf)
        except Exception:
            return []

    @QtCore.pyqtSlot(str)
    def dump_diagnostics(self, path: str) -> None:
        """Persist current diagnostic buffer to JSON file (best-effort)."""
        try:
            data = self.get_diagnostics()
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                try:
                    self.status.emit(f"Diagnostics dumped to {path}")
                except Exception:
                    pass
            except Exception as e:
                try:
                    self.error.emit(f"Failed to dump diagnostics: {e}")
                except Exception:
                    pass
        except Exception:
            pass

    # -------- single-sequence state machine (non-blocking) --------
    def _start_single_sequence(self, n: int):
        """Begin N pulses in succession using QTimer callbacks (no sleeps)."""
        if n <= 0:
            return
        # If already running, reset it
        self._abort_single_sequence()
        self._in_single_sequence = True
        self._single_remaining = int(n)
        try:
            self._diag_event('single_start', {'n': n})
        except Exception:
            pass
        self.shots_progress.emit(0, n)
        self.status.emit(f"Single: firing {n} shot(s)")
        self._single__pulse_on()

    def _single__pulse_on(self):
        if not self._in_single_sequence:
            return
        # high: set Kinesis shutter ON and outputs high
        try:
            try:
                self._set_shutter_on()
            except Exception:
                pass
            self._write_outputs(1, 1, 1)
            try:
                self._diag_event('single_pulse_on', {'remaining': self._single_remaining})
            except Exception:
                pass
        except Exception:
            pass
        QtCore.QTimer.singleShot(self.cfg.pulse_ms, self._single__pulse_off)

    def _single__pulse_off(self):
        if not self._in_single_sequence:
            return
        # low: set Kinesis shutter OFF and outputs low
        try:
            try:
                self._set_shutter_off()
            except Exception:
                pass
            self._write_outputs(0, 0, 0)
            try:
                self._diag_event('single_pulse_off', {'remaining_after': self._single_remaining})
            except Exception:
                pass
        except Exception:
            pass
        # progress update for the shot we just completed
        done = (self._num_shots - max(0, self._single_remaining - 1))
        self.shots_progress.emit(done, self._num_shots)
        self._single_remaining -= 1
        if self._single_remaining > 0:
            QtCore.QTimer.singleShot(self.cfg.gap_ms, self._single__pulse_on)
        else:
            self._in_single_sequence = False
            self.status.emit("Single sequence complete")
            # emit final shots_progress for whole sequence (already emitted in loop)

    def _abort_single_sequence(self):
        if self._in_single_sequence:
            self._in_single_sequence = False
            self._single_remaining = 0
            self._write_outputs(0, 0, 0)
            self.status.emit("Single sequence aborted")

    @QtCore.pyqtSlot()
    def fire_one_shot(self):
        """Perform a single pulse (pulse_ms high, then low) and emit single_shot_done when finished.
        This runs in the fire IO thread; callers should invoke it via a queued connection.
        """
        if self._one_shot_active:
            # already running a one-shot; ignore
            try:
                self.log.emit("fire_one_shot ignored: already active")
            except Exception:
                pass
            return
        try:
            self._one_shot_active = True
            # set outputs high for a pulse, then low and signal completion
            try:
                # Also toggle the Kinesis shutter device to reproduce the audible click
                try:
                    self._set_shutter_on()
                except Exception:
                    pass
                self._write_outputs(1, 1, 1)
                try:
                    self._diag_event('one_shot_on', {})
                except Exception:
                    pass
            except Exception:
                pass
            # schedule turning outputs low and emitting done
            def _finish():
                try:
                    # Turn Kinesis shutter off to close solenoid
                    try:
                        self._set_shutter_off()
                    except Exception:
                        pass
                    self._write_outputs(0, 0, 0)
                    try:
                        self._diag_event('one_shot_off', {})
                    except Exception:
                        pass
                    # emit a per-shot completion signal so the UI can react (rename etc)
                    try:
                        # emit DAQ timestamp so UI and renamer can use a common timestamp
                        self.single_shot_done.emit(time.time())
                    except Exception:
                        pass
                    # also emit a small shots_progress increment (1,1) so UIs listening see activity
                    try:
                        self.shots_progress.emit(1, 1)
                    except Exception:
                        pass
                finally:
                    self._one_shot_active = False

            QtCore.QTimer.singleShot(self.cfg.pulse_ms, _finish)
        except Exception:
            try:
                self._one_shot_active = False
            except Exception:
                pass

    # -------- periodic poll --------
    @QtCore.pyqtSlot()
    def _tick(self):
        # If a single sequence or a one-shot is running, let that owner own the outputs.
        # This prevents the periodic poll from immediately clearing outputs set by a
        # one-shot pulse.
        # (diagnostic logging removed)
        if self._in_single_sequence or getattr(self, '_one_shot_active', False):
            try:
                self._diag_event('tick_skipped', {'in_single': bool(self._in_single_sequence), 'one_shot_active': bool(getattr(self, '_one_shot_active', False))})
            except Exception:
                pass
            return

        val = self._read_trigger()
        try:
            self._diag_event('tick', {'val': val, 'last': self._last_trig})
        except Exception:
            pass
        last = self._last_trig
        falling = (last == 1 and val == 0)

        if self._mode == "continuous":
            self._set_mode_internal("manual")
            self._set_shutter_on()
            if val is None:
                self._write_outputs(1, 0, 0)  # safe default
            else:
                self._write_outputs(1, 1 - val, 1 - val)

        elif self._mode == "single":
            self._set_mode_internal("triggered")
            self._set_shutter_on()
            # Start the N-shot train
            if self._fire_requested and (falling if self.cfg.single_waits_for_edge else True):
                self._fire_requested = False
                self._start_single_sequence(self._num_shots)
            else:
                self._write_outputs(0, 0, 0)

        elif self._mode == "burst":
            self._set_mode_internal("triggered")
            self._set_shutter_on()
            if self._fire_requested:
                # follow inverted trigger while armed
                if val is None:
                    self._write_outputs(1, 0, 0)
                else:
                    self._write_outputs(1, 1 - val, 1 - val)
                if falling:
                    self._burst_count += 1
                    self.shots_progress.emit(self._burst_count, self._num_shots)
                    if self._burst_count >= self._num_shots:
                        self._fire_requested = False
                        self._burst_count = 0
                        self._write_outputs(0, 0, 0)
                        self.status.emit("Burst complete")
            else:
                self._write_outputs(0, 0, 0)

        else:
            self._set_mode_internal("manual")
            self._set_shutter_off()
            self._write_outputs(0, 0, 0)

        self._last_trig = val


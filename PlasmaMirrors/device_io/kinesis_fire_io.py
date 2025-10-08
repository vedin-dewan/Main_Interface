# device_io/kinesis_fire_io.py
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Optional

from PyQt6 import QtCore

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


class KinesisFireIO(QtCore.QObject):
    """
    GUI-agnostic controller for a Thorlabs KSC101 shutter + NI-DAQ digital I/O.

    Runs in its own thread. Uses a QTimer to poll the external trigger and drive:
      - Continuous mode: shutter held open; camera/spec are inverted-trigger
      - Single mode: one shot on next falling edge after Fire()
      - Burst mode: N shots on falling edges after Fire(); then disarm

    Signals are kept high-level for easy wiring in your main window.
    """
    # ---- Signals to the UI / logger ----
    log = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    connected = QtCore.pyqtSignal(str)           # serial string
    status = QtCore.pyqtSignal(str)              # human-readable status line
    shots_progress = QtCore.pyqtSignal(int, int) # (current, total) during burst

    # ---- Slots callable from UI thread (QueuedConnection) ----
    @QtCore.pyqtSlot()
    def open(self):
        """Initialize Kinesis + NI-DAQ and start the poll timer."""
        # Kinesis
        if not _HAVE_KINESIS:
            self.error.emit("Kinesis/pythonnet not available. Install 'pythonnet' and Kinesis DLLs.")
            return
        try:
            DeviceManagerCLI.BuildDeviceList()
            serials = self._discover_serials()
            if self.cfg.serial and self.cfg.serial not in serials:
                # Still try to connect to the requested serial once (in case list missed it)
                self.serial = self.cfg.serial
            else:
                self.serial = self.cfg.serial or (serials[0] if serials else None)
            if not self.serial:
                raise RuntimeError("No KSC101 detected. Close Kinesis GUI, replug USB, check drivers.")

            self.dev = KCubeSolenoid.CreateKCubeSolenoid(self.serial)
            self.dev.Connect(self.serial)
            if not self.dev.IsSettingsInitialized():
                self.dev.WaitForSettingsInitialized(10000)
            # Start device's own fast poller
            self.dev.StartPolling(int(self.cfg.poll_period_s * 1000 / 2) or 5)
            time.sleep(0.2)
            self.dev.EnableDevice()
            time.sleep(0.1)
            # Default safe state
            self._set_mode_internal("single")
            if self.cfg.start_enabled:
                self._set_shutter_on()
            else:
                self._set_shutter_off()
            self.connected.emit(self.serial)
            self.log.emit(f"KSC101 connected (serial {self.serial}).")
        except Exception as e:
            self.error.emit(f"Kinesis open failed: {e}")
            self.dev = None

        # NI-DAQ
        if not _HAVE_DAQ:
            self.error.emit("NI-DAQ not available. Install 'nidaqmx' and ensure NI drivers are present.")
            self.out_task = None
            self.in_task = None
        else:
            try:
                # Persistent DO task with 3 lines
                self.out_task = nidaqmx.Task()
                self.out_task.do_channels.add_do_chan(
                    f"{self.cfg.out_pin_shutter}, {self.cfg.out_pin_cam}, {self.cfg.out_pin_spec}",
                    line_grouping=LineGrouping.CHAN_PER_LINE
                )
                # Persistent DI task for trigger
                self.in_task = nidaqmx.Task()
                self.in_task.di_channels.add_di_chan(self.cfg.input_trigger)
                self._write_outputs(0, 0, 0)
            except Exception as e:
                self.error.emit(f"NI-DAQ open failed: {e}")
                self.out_task = None
                self.in_task = None

        # Timer
        self._last_trig: Optional[int] = None
        self._mode: str = "single"      # continuous | single | burst
        self._fire_requested: bool = False
        self._burst_target: int = 10
        self._burst_count: int = 0

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(int(self.cfg.poll_period_s * 1000))
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self.status.emit(f"Ready (mode: {self._mode}, serial: {self.serial or 'n/a'})")

    @QtCore.pyqtSlot()
    def close(self):
        """Stop timer and release hardware."""
        try:
            if getattr(self, "timer", None):
                self.timer.stop()
        except Exception:
            pass
        try:
            self._write_outputs(0, 0, 0)
        except Exception:
            pass
        for t in ("in_task", "out_task"):
            task = getattr(self, t, None)
            if task is not None:
                try:
                    task.stop()
                except Exception:
                    pass
                try:
                    task.close()
                except Exception:
                    pass
                setattr(self, t, None)
        try:
            if getattr(self, "dev", None) is not None:
                # leave enabled/connected if you prefer—this fully releases it:
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
        self._mode = mode
        # Put device in a sane state immediately; trigger logic will refine on tick
        if mode == "continuous":
            self._set_mode_internal("manual")
            self._set_shutter_on()
        else:
            self._set_mode_internal("triggered")
            self._set_shutter_on()  # required for triggered operation
        self.status.emit(f"Mode set to {mode}")

    @QtCore.pyqtSlot(int)
    def set_burst_count(self, n: int):
        self._burst_target = max(1, int(n))
        self.shots_progress.emit(0, self._burst_target)
        self.log.emit(f"Burst count set to {self._burst_target}")

    @QtCore.pyqtSlot()
    def fire(self):
        """Arm single/burst or no-op in continuous."""
        if self._mode == "continuous":
            self.log.emit("Fire pressed (continuous): no action; device follows external trigger.")
            return
        self._fire_requested = True
        self._burst_count = 0
        self.shots_progress.emit(0, self._burst_target)
        self.status.emit(f"Armed ({self._mode})")

    # ---------- internals ----------
    def __init__(self, cfg: FireConfig):
        super().__init__()
        self.cfg = cfg
        self.dev = None
        self.out_task = None
        self.in_task = None
        self.serial: Optional[str] = None

    def _discover_serials(self) -> list[str]:
        ser = set()
        try:
            # 1) Dedicated list (not always present on older assemblies)
            if hasattr(KCubeSolenoid, "GetDeviceList"):
                ser |= set(list(KCubeSolenoid.GetDeviceList()))
        except Exception:
            pass
        try:
            # 2) Using device prefix (usually "68")
            ser |= set(list(DeviceManagerCLI.GetDeviceList(KCubeSolenoid.DevicePrefix)))
        except Exception:
            pass
        try:
            # 3) Generic list filtered by prefix
            all_list = list(DeviceManagerCLI.GetDeviceList())
            prefix = str(getattr(KCubeSolenoid, "DevicePrefix", "68"))
            ser |= {s for s in all_list if str(s).startswith(prefix)}
        except Exception:
            pass
        return sorted(ser)

    def _set_mode_internal(self, mode_key: str):
        """Direct device mode set (manual/triggered)."""
        if self.dev is None:
            return
        try:
            if mode_key == "manual":
                self.dev.SetOperatingMode(SolenoidStatus.OperatingModes.Manual)
            else:
                self.dev.SetOperatingMode(SolenoidStatus.OperatingModes.Triggered)
        except Exception as e:
            self.error.emit(f"Kinesis SetOperatingMode failed: {e}")

    def _set_shutter_on(self):
        if self.dev is None:
            return
        try:
            self.dev.SetOperatingState(SolenoidStatus.OperatingStates.Active)
        except Exception as e:
            self.error.emit(f"Kinesis SetOperatingState(Active) failed: {e}")

    def _set_shutter_off(self):
        if self.dev is None:
            return
        try:
            self.dev.SetOperatingState(SolenoidStatus.OperatingStates.Inactive)
        except Exception as e:
            self.error.emit(f"Kinesis SetOperatingState(Inactive) failed: {e}")

    def _write_outputs(self, shutter: int, cam: int, spec: int):
        if self.out_task is None:
            return
        try:
            self.out_task.write([bool(shutter), bool(cam), bool(spec)])
        except Exception as e:
            self.error.emit(f"NI-DAQ write failed: {e}")

    def _read_trigger(self) -> Optional[int]:
        if self.in_task is None:
            return None
        try:
            return int(bool(self.in_task.read()))
        except Exception as e:
            # Try to re-open the DI task once if it died
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

    @QtCore.pyqtSlot()
    def _tick(self):
        # read trigger (None on error → hold safe)
        val = self._read_trigger()
        last = getattr(self, "_last_trig", None)
        falling = (last == 1 and val == 0)

        if self._mode == "continuous":
            # Manual ON; camera/spec mirror inverted trigger
            self._set_mode_internal("manual")
            self._set_shutter_on()
            if val is None:
                self._write_outputs(1, 0, 0)  # safe with shutter open? adjust if you prefer closed
            else:
                self._write_outputs(1, 1 - val, 1 - val)

        elif self._mode == "single":
            self._set_mode_internal("triggered")
            self._set_shutter_on()
            if self._fire_requested and falling:
                # one short pulse
                self._write_outputs(1, 1, 1)
                QtCore.QTimer.singleShot(200, lambda: self._write_outputs(0, 0, 0))
                self._fire_requested = False
                self.status.emit("Single shot fired")
            else:
                self._write_outputs(0, 0, 0)

        elif self._mode == "burst":
            self._set_mode_internal("triggered")
            self._set_shutter_on()
            if self._fire_requested:
                # follow inverted trigger while armed; count falling edges
                if val is None:
                    self._write_outputs(1, 0, 0)
                else:
                    self._write_outputs(1, 1 - val, 1 - val)
                if falling:
                    self._burst_count += 1
                    self.shots_progress.emit(self._burst_count, self._burst_target)
                    if self._burst_count >= self._burst_target:
                        self._fire_requested = False
                        self._burst_count = 0
                        self._write_outputs(0, 0, 0)
                        self.status.emit("Burst complete")
            else:
                self._write_outputs(0, 0, 0)

        else:
            # idle/safe
            self._set_mode_internal("manual")
            self._set_shutter_off()
            self._write_outputs(0, 0, 0)

        self._last_trig = val

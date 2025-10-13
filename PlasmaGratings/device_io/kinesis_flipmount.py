#  SPDX-License-Identifier: Princeton 
#  Github user: @ard-srp

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Optional

from PyQt6 import QtCore

# -------- Optional: point this to your Kinesis install if needed --------
KINESIS_DLL_DIR: Optional[str] = r"C:\Program Files\Thorlabs\Kinesis"  # or None

# -------------------- Kinesis (pythonnet/.NET) --------------------
try:
    if KINESIS_DLL_DIR:
        sys.path.append(KINESIS_DLL_DIR)
    import clr  # pythonnet
    clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
    clr.AddReference("Thorlabs.MotionControl.KCube.SolenoidCLI")
    from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
    from Thorlabs.MotionControl.KCube.SolenoidCLI import KCubeDCServo, ServoStatus
    _HAVE_KINESIS = True
except Exception:
    _HAVE_KINESIS = False

@dataclass
class FlipShutterConfig:
    serial: Optional[str] = None                  # e.g. "68000239" or None to auto-pick
    shutter_probe_chan: str = "37004276"  # serial number of shutter
    shutter_pump_A_chan: str = "37004216"  # serial number of shutter
    shutter_pump_B_chan: str = "37004214"  # serial number of shutter
    shutter_pump_C_chan: str = "37004212"  # serial number of shutter
    enabled: bool = False                   # start with shutter disabled
    gap_ms: int = 200                             # low time between shots
    single_waits_for_edge: bool = True            # if True: start train at next falling edge


class KinesisFlipShutter(QtCore.QObject):
    """
    Controls a Thorlabs Kinesis Flip Mount as a fast shutter.
    Uses the Solenoid KCube, with 3 channels for pump A/B/C and 1 channel for probe.
    All the channels are triggered by software commands to open/close the shutter.

    Note: This is not a "true" flip mount, but rather a solenoid with 4 channels.
    The "flip" terminology is used here for consistency with other devices.

    Requires Thorlabs Kinesis installed, and pythonnet (pip install pythonnet).
    """
    status_changed = QtCore.pyqtSignal(str)  # emits status string when changed
    error = QtCore.pyqtSignal(str)           # emits error message if something goes wrong

    def __init__(self, config: FlipShutterConfig):
        super().__init__()
        if not _HAVE_KINESIS:
            raise RuntimeError("KinesisFlipShutter requires Thorlabs Kinesis and pythonnet.")
        self.config = config
        self.shutter: Optional[KCubeDCServo] = None
        self._is_open = False
        self._is_enabled = False
        self._last_action_time = 0.0  # time of last open/close action

        DeviceManagerCLI.BuildDeviceList()  # scan for devices
        time.sleep(0.5)  # wait a bit for the device list to populate

        # Auto-pick device if serial not specified
        if self.config.serial is None:
            devices = DeviceManagerCLI.GetDeviceList()
            dc_servo_serials = [d.SerialNumber for d in devices if "KCube Solenoid" in d.Name]
            if not dc_servo_serials:
                raise RuntimeError("No Kinesis Solenoid (KCube) devices found.")
            self.config.serial = dc_servo_serials[0]  # pick the first one

        try:
            self.shutter = KCubeDCServo.CreateKCubeDCServo(self.config.serial)
            self.shutter.Connect(self.config.serial)
            time.sleep(0.5)  # wait for connection
            if not self.shutter.IsConnected:
                raise RuntimeError(f"Failed to connect to Kinesis device {self.config.serial}.")
            self.shutter.StartPolling(250)  # poll every 250 ms
            time.sleep(0.5)  # wait for polling to start
            self.shutter.EnableDevice()
            time.sleep(0.5)  # wait for device to enable
            if not self.shutter.IsEnabled:
                raise RuntimeError(f"Kinesis device {self.config.serial} failed to enable.")
            self._is_enabled = True
        
        except Exception as e:
            raise RuntimeError(f"Error initializing Kinesis Flip Shutter: {e}")
        
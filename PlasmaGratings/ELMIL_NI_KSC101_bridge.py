import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# ---------------- Kinesis (KSC101) (Single shot shutter) setup ----------------
# Requires: pythonnet (`pip install pythonnet`) and Thorlabs Kinesis
sys.path.append(r"C:\Program Files\Thorlabs\Kinesis")
import clr
clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
clr.AddReference("Thorlabs.MotionControl.KCube.SolenoidCLI")
from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
from Thorlabs.MotionControl.KCube.SolenoidCLI import KCubeSolenoid, SolenoidStatus

# ---------------- NI-DAQ setup ----------------
import nidaqmx
from nidaqmx.constants import LineGrouping

# ================== CONFIG For NI-DAQ ===================
SERIAL = None  # e.g. "68000239". If None, will auto-pick first KSC101 seen.
OUT_PIN_SHUTTER = "Dev1/port0/line0"
OUT_PIN_CAM     = "Dev1/port0/line2"
OUT_PIN_SPEC    = "Dev1/port0/line3"
INPUT_TRIGGER   = "Dev1/PFI0"        # external TTL in
POLL_PERIOD_S   = 0.02              # ~20 ms polling (software)
# =============================================


class KSC101:
    """Minimal wrapper around Kinesis KCube Solenoid (no polling; stays connected)."""
    def __init__(self, serial=None):
        self.serial = serial
        self.dev = None

    @staticmethod
    def discover(max_retries: int = 3, delay_s: float = 0.4) -> list[str]:
        """
        Return serials for KSC101 visible to the DLLs.
        Tries multiple enumeration paths because some builds omit one or another.
        """
        serials = set()
        for _ in range(max_retries + 1):
            DeviceManagerCLI.BuildDeviceList()

            # 1) Class helper (some builds omit it)
            try:
                if hasattr(KCubeSolenoid, "GetDeviceList"):
                    serials |= set(list(KCubeSolenoid.GetDeviceList()))
            except Exception:
                pass

            # 2) By device prefix (usually '68' for KSC101)
            try:
                serials |= set(list(DeviceManagerCLI.GetDeviceList(KCubeSolenoid.DevicePrefix)))
            except Exception:
                pass

            # 3) Generic list filtered by prefix (works even if (2) is missing)
            try:
                all_list = list(DeviceManagerCLI.GetDeviceList())
                prefix = str(getattr(KCubeSolenoid, "DevicePrefix", "68"))
                serials |= {s for s in all_list if str(s).startswith(prefix)}
            except Exception:
                pass

            if serials:
                break
            time.sleep(delay_s)

        return sorted(serials)

    def connect(self):
        """
        Connect to the device. If a serial is provided but not discovered, we still
        attempt Connect(serial) once—then surface a helpful error if it fails.
        """
        visibles = self.discover()

        # Auto-pick if none provided
        if not self.serial:
            if not visibles:
                raise RuntimeError(
                    "No KSC101 found by Kinesis. Close the Kinesis GUI, replug the USB cable, "
                    "and ensure you're running 64-bit Python with Kinesis DLLs in "
                    r"C:\Program Files\Thorlabs\Kinesis."
                )
            self.serial = visibles[0]

        # Create and try to connect
        self.dev = KCubeSolenoid.CreateKCubeSolenoid(self.serial)
        try:
            self.dev.Connect(self.serial)
        except Exception as e:
            # Most common cause: Kinesis GUI has the device open (exclusive lock)
            raise RuntimeError(
                f"Could not connect to KSC101 {self.serial}. "
                "Close the Kinesis GUI (it holds the device), then try again. "
                "If it still fails, unplug/replug the cube and rerun."
            ) from e

        if not self.dev.IsSettingsInitialized():
            self.dev.WaitForSettingsInitialized(10000)

        self.dev.StartPolling(int(POLL_PERIOD_S*1000/2))
        time.sleep(0.25)
        self.dev.EnableDevice()
        time.sleep(0.25)  # Wait for device to enable
        # Keep enum types handy (pythonnet 3.x)
        self.ModeEnum  = type(self.dev.GetOperatingMode())
        self.StateEnum = type(self.dev.GetOperatingState())

        info = self.dev.GetDeviceInfo()
        print(f"[KSC101] Connected: {info.Description} (Serial {self.serial})")

    def set_mode_manual(self):
        self.dev.SetOperatingMode(SolenoidStatus.OperatingModes.Manual)

    def set_mode_triggered(self):
        self.dev.SetOperatingMode(SolenoidStatus.OperatingModes.Triggered)

    def set_on(self):
        self.dev.SetOperatingState(SolenoidStatus.OperatingStates.Active)

    def set_off(self):
        self.dev.SetOperatingState(SolenoidStatus.OperatingStates.Inactive)

    def get_mode_state(self):
        m = self.dev.GetOperatingMode()
        s = self.dev.GetOperatingState()
        mode_map = {
            int(SolenoidStatus.OperatingModes.Manual): "manual",
            int(SolenoidStatus.OperatingModes.Triggered): "triggered",
        }
        state_map = {
            int(SolenoidStatus.OperatingStates.Inactive): "off",
            int(SolenoidStatus.OperatingStates.Active): "on",
        }
        return mode_map.get(int(m), str(int(m))), state_map.get(int(s), str(int(s)))



class Controller(threading.Thread):
    """
    Background worker:
      - Reads external trigger (software polled)
      - Sets KSC101 mode/state as required
      - Writes NI-DAQ outputs for shutter/camera/spec
    """
    def __init__(self, gui):
        super().__init__(daemon=True)
        self.gui = gui
        self.stop_flag = threading.Event()

        # State variables
        self.mode = "single"         # "continuous" | "single" | "burst"
        self.fire_requested = False  # for single/burst
        self.num_burst = 10
        self.shot_counter = 0

        # NI tasks
        self.out_task = nidaqmx.Task()
        self.out_task.do_channels.add_do_chan(
            f"{OUT_PIN_SHUTTER}, {OUT_PIN_CAM}, {OUT_PIN_SPEC}",
            line_grouping=LineGrouping.CHAN_PER_LINE
        )

        # KSC101
        self.ksc = KSC101(SERIAL)
        self.ksc.connect()
        # default safe state
        self.ksc.set_mode_manual()
        self.ksc.set_off()
        self.write_outputs(0, 0, 0)

    def shutdown(self):
        self.stop_flag.set()
        try:
            self.write_outputs(0, 0, 0)
            self.out_task.stop()
        except Exception:
            pass
        try:
            self.out_task.close()
        except Exception:
            pass
        # Intentionally keep the KSC101 connected (per your preference).
        # To release explicitly, uncomment:
        # self.ksc.dev.DisableDevice()
        # self.ksc.dev.Disconnect(True)

    def write_outputs(self, shutter: int, cam: int, spec: int):
        self.out_task.write([bool(shutter), bool(cam), bool(spec)])

    def _read_trigger_once(self):
        # Fresh task each read (simple & robust); for performance, you can keep it open.
        with nidaqmx.Task() as in_task:
            in_task.di_channels.add_di_chan(INPUT_TRIGGER)
            return int(bool(in_task.read()))  # 0 or 1

    def set_mode(self, new_mode: str):
        self.mode = new_mode

    def set_num_burst(self, n: int):
        self.num_burst = max(1, int(n))

    def fire(self):
        # Used by GUI button. Behavior depends on mode:
        if self.mode == "single":
            self.fire_requested = True  # arm; will fire on next falling edge
        elif self.mode == "burst":
            self.fire_requested = True
            self.shot_counter = 0
        else:
            # Continuous: nothing to do (external trigger drives it)
            pass

    def _handle_trigger(self, val: int, last_val: int | None):
        """
        val: current trigger (0/1)
        last_val: previous trigger (0/1 or None)
        Edge detect: falling edge is (last_val == 1 and val == 0).
        """
        falling = (last_val == 1 and val == 0)

        if self.mode == "continuous":
            # Manual + ON, shutter open; cam/spec follow inverted trigger
            self.ksc.set_off()
            self.ksc.set_mode_manual()
            self.ksc.set_on()
            self.write_outputs(1, 1-val, 1-val)

        elif self.mode == "burst":
            # Only start bursting after Fire is pressed.
            self.ksc.set_mode_triggered()
            self.ksc.set_on()

            if self.fire_requested:
                # While armed, let the external trigger drive cam/spec (inverted).
                # Keep shutter enabled.
                self.write_outputs(1, 1-val, 1-val)

                # Count falling edges only while armed
                if falling:
                    self.shot_counter += 1
                    if self.shot_counter >= self.num_burst:
                        # Done: disarm and go safe
                        self.fire_requested = False
                        self.shot_counter = 0
                        self.write_outputs(0, 0, 0)
                        # self.ksc.set_mode_manual()
            else:
                # Not armed yet: ignore external trigger completely.
                # Keep shutter closed and outputs low until Fire is pressed.
                self.write_outputs(0, 0, 0)

        elif self.mode == "single":
            # Triggered; on the first falling edge *after* Fire is pressed, emit one shot
            self.ksc.set_mode_triggered()
            self.ksc.set_on()

            if self.fire_requested and falling:
                # One-shot pulse on all 3 lines, then clear
                self.write_outputs(1, 1, 1)
                # short hold to be visible if your devices need a minimum width
                time.sleep(0.2)
                self.write_outputs(0, 0, 0)
                self.fire_requested = False
            else:
                # keep outputs low while waiting
                self.write_outputs(0, 0, 0)

        else:  # idle (not exposed in GUI, but here for completeness)
            self.ksc.set_mode_manual()
            self.ksc.set_off()
            self.write_outputs(0, 0, 0)

    def run(self):
        print("[Worker] Running (Ctrl+C in console won’t stop GUI). Close window to quit.")
        last_val = None
        try:
            while not self.stop_flag.is_set():
                try:
                    val = self._read_trigger_once()  # 0/1
                except Exception as e:
                    # If trigger read fails, keep outputs safe and retry
                    val = last_val
                    self.write_outputs(0, 0, 0)

                self._handle_trigger(val, last_val)
                last_val = val
                time.sleep(POLL_PERIOD_S)
        finally:
            print("[Worker] Stopping...")
            # Ensure outputs are low
            try:
                self.write_outputs(0, 0, 0)
            except Exception:
                pass


class InterfaceGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Trigger Controller")
        self.geometry("360x300")
        self.resizable(False, False)

        # --- Mode selection ---
        mode_frame = ttk.LabelFrame(self, text="Trigger Mode")
        mode_frame.pack(padx=10, pady=10, fill="x")

        self.mode_var = tk.StringVar(value="Continuous")
        for m in ["Continuous", "Single Shot", "Burst"]:
            ttk.Radiobutton(
                mode_frame, text=m, variable=self.mode_var, value=m,
                command=self.on_mode_change
            ).pack(anchor="w", padx=10, pady=2)

        # --- Burst shots ---
        burst_frame = ttk.Frame(self)
        burst_frame.pack(padx=10, pady=5, fill="x")
        ttk.Label(burst_frame, text="# Shots (Burst):").pack(side="left", padx=(0, 6))
        self.burst_spin = ttk.Spinbox(burst_frame, from_=1, to=999, width=6)
        self.burst_spin.set("10")
        self.burst_spin.pack(side="left")
        ttk.Label(burst_frame, text="(press Fire to start)").pack(side="left", padx=6)

        # --- Fire button ---
        fire_btn = tk.Button(self, text="Fire", bg="#D30000", fg="white",
                             font=("Segoe UI", 12, "bold"), width=18, height=2,
                             command=self.on_fire)
        fire_btn.pack(pady=15)

        # --- Status ---
        self.status = tk.StringVar(value="Status: initializing…")
        ttk.Label(self, textvariable=self.status).pack(pady=4)

        # Start controller thread
        try:
            self.controller = Controller(self)
            self.controller.set_mode(self._gui_mode_to_internal(self.mode_var.get()))
            self.controller.set_num_burst(int(self.burst_spin.get()))
            self.controller.start()

            # Show KSC101 mode/state once
            mode, state = self.controller.ksc.get_mode_state()
            self.status.set(f"Connected KSC101 {self.controller.ksc.serial} | Mode: {mode} | State: {state}")
        except Exception as e:
            messagebox.showerror("Initialization error", str(e))
            self.destroy()

        # Update burst setting when spin changes
        self.burst_spin.bind("<FocusOut>", lambda e: self._update_burst_from_spin())
        self.burst_spin.bind("<Return>",  lambda e: self._update_burst_from_spin())

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _update_burst_from_spin(self):
        try:
            self.controller.set_num_burst(int(self.burst_spin.get()))
        except Exception:
            pass

    def _gui_mode_to_internal(self, s: str) -> str:
        s = s.lower()
        if "continuous" in s:
            return "continuous"
        if "single" in s:
            return "single"
        if "burst" in s:
            return "burst"
        return "single"

    def on_mode_change(self):
        mode_internal = self._gui_mode_to_internal(self.mode_var.get())
        self.controller.set_mode(mode_internal)
        self._update_burst_from_spin()
        self.status.set(f"Mode set to: {self.mode_var.get()}")

    def on_fire(self):
        self._update_burst_from_spin()
        self.controller.fire()
        self.status.set(f"Fired ({self.mode_var.get()})")

    def on_close(self):
        try:
            self.controller.shutdown()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = InterfaceGUI()
    app.mainloop()

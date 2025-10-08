# ascii_stage_io.py
from PyQt6 import QtCore
from zaber_motion import Units
from zaber_motion.ascii import Connection  # <-- ASCII API

class ZaberStageIO(QtCore.QObject):
    # Signals identical to your Binary version
    log        = QtCore.pyqtSignal(str)
    error      = QtCore.pyqtSignal(str)
    opened     = QtCore.pyqtSignal()
    discovered = QtCore.pyqtSignal(list)        # [{"address":int, "label":str}]
    position   = QtCore.pyqtSignal(int, float, float)   # addr, steps(native not used here), pos(eng)
    moved      = QtCore.pyqtSignal(int, float)  # addr, final pos
    homed      = QtCore.pyqtSignal(int)         # addr
    speed      = QtCore.pyqtSignal(int, float)  # addr, target speed (best effort)
    moving     = QtCore.pyqtSignal(int, bool)   # addr, is_moving

    def __init__(self, port: str, baud: int):
        super().__init__()
        self.port = port
        self.baud = baud
        self.conn: Connection | None = None
        self._pollers: dict[int, QtCore.QTimer] = {}

    # ---------- lifecycle ----------
    @QtCore.pyqtSlot()
    def open(self):
        try:
            self.conn = Connection.open_serial_port(self.port, baud_rate=self.baud)
            self.log.emit(f"I/O opened {self.port} (ASCII, {self.baud} baud)")
            self.opened.emit()
        except Exception as e:
            self.error.emit(f"Open failed: {e}")

    @QtCore.pyqtSlot()
    def close(self):
        try:
            if self.conn:
                self.conn.close()
                self.log.emit("I/O closed")
        except Exception as e:
            self.error.emit(f"Close error: {e}")
        finally:
            self.conn = None

    # ---------- discovery ----------
    @QtCore.pyqtSlot()
    def discover(self):
        try:
            if self.conn is None:
                self.open()
                if self.conn is None:
                    return
            devs = self.conn.detect_devices()
            found = []
            for dev in devs:
                addr = dev.device_address
                label = getattr(dev, "name", None)
                try:
                    dev.identify()
                    label = label or getattr(dev, "name", None)
                except Exception:
                    pass
                self.log.emit(f"- Address {addr}: {label or 'Unknown'}")
                found.append({"address": addr, "label": label or "Unknown"})
            self.discovered.emit(found)
        except Exception as e:
            self.error.emit(f"Discover failed: {e}")

    # ---------- helpers ----------
    def _axis(self, address: int):
        # simple helper: assume axis 1 on each device
        dev = self.conn.get_device(int(address))
        return dev.get_axis(1)

    def _emit_position_once(self, address: int, unit: str):
        ax = self._axis(address)
        # ASCII doesn’t expose "steps" directly for all devices; pass 0 for compatibility
        pos = ax.get_position(Units.LENGTH_MILLIMETRES if unit == "mm" else Units.ANGLE_DEGREES)
        self.position.emit(int(address), 0.0, float(pos))

    def _start_poll(self, address: int, unit: str, interval_ms: int = 50):
        if address in self._pollers:
            return
        timer = QtCore.QTimer(self)
        timer.setInterval(interval_ms)
        timer.timeout.connect(lambda a=address, u=unit: self._poll_once(a, u))
        timer.start()
        self._pollers[address] = timer

    def _stop_poll(self, address: int):
        t = self._pollers.pop(address, None)
        if t:
            t.stop()
            t.deleteLater()

    def _poll_once(self, address: int, unit: str):
        try:
            ax = self._axis(address)
            # live UI update
            self._emit_position_once(address, unit)
            # ASCII gives us non-blocking busy checks
            busy = ax.is_busy()
            if not busy:
                # finalize
                pos = ax.get_position(Units.LENGTH_MILLIMETRES if unit == "mm" else Units.ANGLE_DEGREES)
                self.moved.emit(int(address), float(pos))
                self._stop_poll(address)
                self.moving.emit(int(address), False)
        except Exception as e:
            self.error.emit(f"Poll failed (addr {address}): {e}")
            self._stop_poll(address)
            self.moving.emit(int(address), False)

    # ---------- public slots (non-blocking) ----------
    @QtCore.pyqtSlot(int, str)
    def read_position_speed(self, address: int, unit: str):
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            ax = self._axis(address)
            pos = ax.get_position(Units.LENGTH_MILLIMETRES if unit == "mm" else Units.ANGLE_DEGREES)
            self.position.emit(int(address), 0.0, float(pos))
            # Best-effort readback of speed (varies by device; ASCII setting names differ across series)
            try:
                # Common setting name is 'maxspeed' or 'velocity'. Try both.
                spd = None
                try:
                    spd = ax.settings.get("maxspeed", Units.VELOCITY_MILLIMETRES_PER_SECOND
                                          if unit == "mm" else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
                except Exception:
                    spd = ax.settings.get("velocity", Units.VELOCITY_MILLIMETRES_PER_SECOND
                                          if unit == "mm" else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
                if spd is not None:
                    self.speed.emit(int(address), float(spd))
            except Exception:
                pass
            self.log.emit(f"Address {address}: {pos:.6f} {unit}")
        except Exception as e:
            self.error.emit(f"Read position failed: {e}")

    @QtCore.pyqtSlot(int, float, str)
    def move_absolute(self, address: int, target_pos: float, unit: str):
        """ASCII: returns immediately (wait_until_idle=False)."""
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            ax = self._axis(address)
            ax.move_absolute(float(target_pos),
                             Units.LENGTH_MILLIMETRES if unit == "mm" else Units.ANGLE_DEGREES,
                             wait_until_idle=False)
            self.moving.emit(int(address), True)
            self._start_poll(address, unit)
        except Exception as e:
            self.error.emit(f"Move failed: {e}")
            self.moving.emit(int(address), False)

    @QtCore.pyqtSlot(int, float, str)
    def move_delta(self, address: int, delta_pos: float, unit: str):
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            ax = self._axis(address)
            ax.move_relative(float(delta_pos),
                             Units.LENGTH_MILLIMETRES if unit == "mm" else Units.ANGLE_DEGREES,
                             wait_until_idle=False)
            self.moving.emit(int(address), True)
            self._start_poll(address, unit)
        except Exception as e:
            self.error.emit(f"Move delta failed: {e}")
            self.moving.emit(int(address), False)

    @QtCore.pyqtSlot(int)
    def home(self, address: int):
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            ax = self._axis(address)
            ax.home(wait_until_idle=False)  # non-blocking
            self.moving.emit(int(address), True)
            # You can decide unit by your address map; or pass from UI
            self._start_poll(address, "mm")  # or "deg" if that axis is rotary
        except Exception as e:
            self.error.emit(f"Home failed: {e}")
            self.moving.emit(int(address), False)

    @QtCore.pyqtSlot(int, str)
    def stop(self, address: int, unit: str):
        """ASCII stop is non-blocking if wait_until_idle=False; poller will finish it."""
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            ax = self._axis(address)
            ax.stop(wait_until_idle=False)  # returns immediately; axis decelerates
            self.log.emit(f"Address {address} STOP requested")
            # Keep polling; when ax.is_busy() becomes False, _poll_once will emit final position.
        except Exception as e:
            self.error.emit(f"Stop failed: {e}")
        # do NOT mark moving False here; poller will do it at the true end

    @QtCore.pyqtSlot(int, float)
    def set_target_speed(self, address: int, new_spd: float, unit: str):
        """Best-effort: setting names vary by hardware; try common ones."""
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            ax = self._axis(address)
            # try common setting keys:
            try:
                ax.settings.set("maxspeed", float(new_spd),
                                Units.VELOCITY_MILLIMETRES_PER_SECOND if unit == "mm"
                                else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
            except Exception:
                ax.settings.set("velocity", float(new_spd),
                                Units.VELOCITY_MILLIMETRES_PER_SECOND if unit == "mm"
                                else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
            # readback (best effort)
            try:
                rb = ax.settings.get("maxspeed", Units.VELOCITY_MILLIMETRES_PER_SECOND if unit == "mm"
                                     else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
            except Exception:
                rb = ax.settings.get("velocity", Units.VELOCITY_MILLIMETRES_PER_SECOND if unit == "mm"
                                     else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
            if rb is not None:
                self.speed.emit(int(address), float(rb))
                self.log.emit(f"Address {address} target speed set to: {rb:.3f} {unit}/s")
        except Exception as e:
            self.error.emit(f"Set target speed failed: {e}")

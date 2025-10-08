# ascii_stage_io.py
from PyQt6 import QtCore
from zaber_motion import Units
from zaber_motion.ascii import Connection  # <-- ASCII API

class ZaberStageIO(QtCore.QObject):
    # same signals as your Binary version
    log        = QtCore.pyqtSignal(str)
    error      = QtCore.pyqtSignal(str)
    opened     = QtCore.pyqtSignal()
    discovered = QtCore.pyqtSignal(list)
    position   = QtCore.pyqtSignal(int, float, float)  # address, steps(dummy 0), pos
    moved      = QtCore.pyqtSignal(int, float)
    homed      = QtCore.pyqtSignal(int)
    speed      = QtCore.pyqtSignal(int, float)
    moving     = QtCore.pyqtSignal(int, bool)

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
            self.conn = None

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
            if not devs:
                self.error.emit("ASCII discover: 0 devices. (Are the stages still in Binary mode?)")
                return
            found = []
            for dev in devs:
                try:
                    dev.identify()
                except Exception:
                    pass
                label = getattr(dev, "name", None) or "Unknown"
                addr  = int(dev.device_address)
                self.log.emit(f"- Address {addr}: {label}")
                found.append({"address": addr, "label": label})
            self.discovered.emit(found)
        except Exception as e:
            self.error.emit(f"Discover failed: {e}")

    # ---------- helpers ----------
    def _axis(self, address: int):
        dev = self.conn.get_device(int(address))
        return dev.get_axis(1)  # adjust if you use non-axis-1 hardware

    def _emit_position_once(self, address: int, unit: str):
        ax = self._axis(address)
        pos = float(ax.get_position(Units.LENGTH_MILLIMETRES if unit == "mm" else Units.ANGLE_DEGREES))
        self.position.emit(int(address), 0.0, pos)
        return pos

    def _start_poll(self, address: int, unit: str, interval_ms: int = 50):
        if address in self._pollers:
            return
        t = QtCore.QTimer(self)
        t.setInterval(interval_ms)
        t.timeout.connect(lambda a=address, u=unit: self._poll_once(a, u))
        t.start()
        self._pollers[address] = t

    def _stop_poll(self, address: int):
        t = self._pollers.pop(address, None)
        if t:
            t.stop()
            t.deleteLater()

    def _poll_once(self, address: int, unit: str):
        try:
            ax = self._axis(address)
            self._emit_position_once(address, unit)   # live update
            if not ax.is_busy():
                pos = self._emit_position_once(address, unit)
                self.moved.emit(int(address), float(pos))
                self._stop_poll(address)
                self.moving.emit(int(address), False)
        except Exception as e:
            self.error.emit(f"Poll failed (addr {address}): {e}")
            self._stop_poll(address)
            self.moving.emit(int(address), False)

    # ---------- public slots (all non-blocking) ----------
    @QtCore.pyqtSlot(int, str)
    def read_position_speed(self, address: int, unit: str):
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            ax = self._axis(address)
            pos = float(ax.get_position(Units.LENGTH_MILLIMETRES if unit == "mm" else Units.ANGLE_DEGREES))
            self.position.emit(int(address), 0.0, pos)

            # best-effort speed readback (setting key varies by series)
            sp = None
            try:
                sp = ax.settings.get("maxspeed",
                                     Units.VELOCITY_MILLIMETRES_PER_SECOND if unit == "mm"
                                     else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
            except Exception:
                try:
                    sp = ax.settings.get("velocity",
                                         Units.VELOCITY_MILLIMETRES_PER_SECOND if unit == "mm"
                                         else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
                except Exception:
                    pass
            if sp is not None:
                self.speed.emit(int(address), float(sp))
            self.log.emit(f"Address {address}: {pos:.6f} {unit}")
        except Exception as e:
            self.error.emit(f"Read position failed: {e}")

    @QtCore.pyqtSlot(int, float, str)
    def move_absolute(self, address: int, target_pos: float, unit: str):
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            ax = self._axis(address)
            ax.move_absolute(float(target_pos),
                             Units.LENGTH_MILLIMETRES if unit == "mm" else Units.ANGLE_DEGREES,
                             wait_until_idle=False)  # immediate return
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
            ax.home(wait_until_idle=False)
            self.moving.emit(int(address), True)
            # if you know this axis is rotary, pass "deg" instead
            self._start_poll(address, "mm")
        except Exception as e:
            self.error.emit(f"Home failed: {e}")
            self.moving.emit(int(address), False)

    @QtCore.pyqtSlot(int, str)
    def stop(self, address: int, unit: str):
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            ax = self._axis(address)
            ax.stop(wait_until_idle=False)   # returns immediately; poller will finish
            self.log.emit(f"Address {address} STOP requested")
        except Exception as e:
            self.error.emit(f"Stop failed: {e}")
        # don't mark moving False here; _poll_once() will when the axis is actually idle

    @QtCore.pyqtSlot(int, float, str)
    def set_target_speed(self, address: int, new_spd: float, unit: str):
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            ax = self._axis(address)
            # Setting key differs across product families; try common ones:
            try:
                ax.settings.set("maxspeed", float(new_spd),
                                Units.VELOCITY_MILLIMETRES_PER_SECOND if unit == "mm"
                                else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
            except Exception:
                ax.settings.set("velocity", float(new_spd),
                                Units.VELOCITY_MILLIMETRES_PER_SECOND if unit == "mm"
                                else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)

            # readback
            try:
                rb = ax.settings.get("maxspeed",
                                     Units.VELOCITY_MILLIMETRES_PER_SECOND if unit == "mm"
                                     else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
            except Exception:
                rb = ax.settings.get("velocity",
                                     Units.VELOCITY_MILLIMETRES_PER_SECOND if unit == "mm"
                                     else Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
            if rb is not None:
                self.speed.emit(int(address), float(rb))
                self.log.emit(f"Address {address} target speed set to: {rb:.3f} {unit}/s")
        except Exception as e:
            self.error.emit(f"Set target speed failed: {e}")

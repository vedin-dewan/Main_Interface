from PyQt6 import QtCore
from zaber_motion import Units
from zaber_motion.binary import Connection, BinarySettings

class ZaberStageIO(QtCore.QObject):
    # ---- Signals (same shape as your previous worker) ----
    log        = QtCore.pyqtSignal(str)
    error      = QtCore.pyqtSignal(str)
    opened     = QtCore.pyqtSignal()
    discovered = QtCore.pyqtSignal(list)               # [{"address": int, "label": str}]
    position   = QtCore.pyqtSignal(int, float, float)  # address, steps, pos(eng units)
    moved      = QtCore.pyqtSignal(int, float)         # address, final pos(eng)
    homed      = QtCore.pyqtSignal(int)                # address
    speed      = QtCore.pyqtSignal(int, float)         # address, target speed (mm/s or deg/s)
    moving     = QtCore.pyqtSignal(int, bool)          # address, is_moving

    def __init__(self, port: str, baud: int):
        super().__init__()
        self.port = port
        self.baud = baud
        self.conn: Connection | None = None
        self._pollers: dict[int, QtCore.QTimer] = {}
        self._last_pos: dict[int, float] = {}
        self._stable: dict[int, int] = {}  # consecutive stable-ticks counter

        # Heuristic idle detection:
        self._eps_mm   = 1e-9     # position change threshold for mm axes
        self._eps_deg  = 1e-9     # for deg axes
        self._need_stable_ticks = 2   # require N stable ticks to declare idle

    # ---------- lifecycle ----------
    @QtCore.pyqtSlot()
    def open(self):
        try:
            self.conn = Connection.open_serial_port(self.port, baud_rate=self.baud)
            self.log.emit(f"I/O opened {self.port} (Binary, {self.baud} baud)")
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
            devices = self.conn.detect_devices(identify_devices=True)
            found = []
            self.log.emit(f"Found {len(devices)} device(s) on {self.port}:")
            for d in devices:
                label = None
                try:
                    ident = d.identify()
                    label = getattr(ident, "name", None) or getattr(d, "name", None)
                except Exception:
                    label = getattr(d, "name", None) or "Unknown"
                addr = int(d.device_address)
                self.log.emit(f"- Address {addr}: {label}")
                found.append({"address": addr, "label": label})
            self.discovered.emit(found)
        except Exception as e:
            self.error.emit(f"Discover failed: {e}")

    # ---------- helpers ----------
    def _emit_position_once(self, address: int, unit: str):
        dev = self.conn.get_device(int(address))
        steps = float(dev.get_position())
        if unit == "mm":
            pos = float(dev.get_position(Units.LENGTH_MILLIMETRES))
        else:
            pos = float(dev.get_position(Units.ANGLE_DEGREES))
        self.position.emit(int(address), steps, pos)
        return pos

    def _start_poll(self, address: int, unit: str, interval_ms: int = 50):
        if address in self._pollers:
            return
        t = QtCore.QTimer(self)
        t.setInterval(interval_ms)
        t.timeout.connect(lambda a=address, u=unit: self._poll_once(a, u))
        t.start()
        self._pollers[address] = t
        self._last_pos[address] = None
        self._stable[address] = 0

    def _stop_poll(self, address: int):
        t = self._pollers.pop(address, None)
        if t:
            t.stop()
            t.deleteLater()
        self._last_pos.pop(address, None)
        self._stable.pop(address, None)

    def _is_busy_binary(self, dev) -> bool:
        """
        Try library-level busy; if not available, we return True and rely on the
        position-stability heuristic to terminate motion.
        """
        try:
            return bool(dev.is_busy())
        except Exception:
            return True  # fall back to heuristic

    def _poll_once(self, address: int, unit: str):
        try:
            dev = self.conn.get_device(int(address))
            # live UI update
            pos = self._emit_position_once(address, unit)

            # try direct busy flag
            busy = self._is_busy_binary(dev)

            # heuristic fallback / corroboration: if position stops changing for N ticks, consider idle
            prev = self._last_pos.get(address, None)
            self._last_pos[address] = pos
            eps = self._eps_mm if unit == "mm" else self._eps_deg
            if prev is not None and abs(pos - prev) < eps:
                self._stable[address] = self._stable.get(address, 0) + 1
            else:
                self._stable[address] = 0

            if (not busy) or (self._stable[address] >= self._need_stable_ticks):
                # finalize
                pos_final = self._emit_position_once(address, unit)
                self.moved.emit(int(address), float(pos_final))
                self._stop_poll(address)
                self.moving.emit(int(address), False)
        except Exception as e:
            self.error.emit(f"Poll failed (addr {address}): {e}")
            self._stop_poll(address)
            self.moving.emit(int(address), False)

    # ---------- public slots ----------
    @QtCore.pyqtSlot(int, str)
    def read_position_speed(self, address: int, unit: str):
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            dev = self.conn.get_device(int(address))
            # position
            self._emit_position_once(address, unit)
            # speed (target)
            try:
                if unit == "mm":
                    spd = dev.settings.get(BinarySettings.TARGET_SPEED,
                                           Units.VELOCITY_MILLIMETRES_PER_SECOND)
                else:
                    spd = dev.settings.get(BinarySettings.TARGET_SPEED,
                                           Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
                if spd is not None:
                    self.speed.emit(int(address), float(spd))
            except Exception:
                pass
        except Exception as e:
            self.error.emit(f"Read position failed: {e}")

    @QtCore.pyqtSlot(int, float, str)
    def move_absolute(self, address: int, target_pos: float, unit: str):
        """
        Fire-and-poll move (no waiting here). If your firmware makes this call blocking,
        see the note at the bottom.
        """
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            dev = self.conn.get_device(int(address))
            if unit == "mm":
                dev.move_absolute(float(target_pos), Units.LENGTH_MILLIMETRES)
            else:
                dev.move_absolute(float(target_pos), Units.ANGLE_DEGREES)
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
            dev = self.conn.get_device(int(address))
            if unit == "mm":
                cur = float(dev.get_position(Units.LENGTH_MILLIMETRES))
                dev.move_absolute(cur + float(delta_pos), Units.LENGTH_MILLIMETRES)
            else:
                cur = float(dev.get_position(Units.ANGLE_DEGREES))
                dev.move_absolute(cur + float(delta_pos), Units.ANGLE_DEGREES)
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
            dev = self.conn.get_device(int(address))
            dev.home()
            # Choose appropriate unit per your address map (or pass from GUI)
            unit = "mm"   # or "deg"
            self.moving.emit(int(address), True)
            self._start_poll(address, unit)
        except Exception as e:
            self.error.emit(f"Home failed: {e}")
            self.moving.emit(int(address), False)

    @QtCore.pyqtSlot(int, str)
    def stop(self, address: int, unit: str):
        """
        Binary STOP returns after the axis is halted. Because we never block the
        StageIO thread elsewhere, this runs immediately when you click the red button.
        """
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            dev = self.conn.get_device(int(address))
            if unit == "mm":
                pos = float(dev.stop(Units.LENGTH_MILLIMETRES))
            elif unit == "deg":
                pos = float(dev.stop(Units.ANGLE_DEGREES))
            else:
                pos = float(dev.stop(Units.NATIVE))
            steps = float(dev.get_position())
            self.position.emit(int(address), steps, pos)
            self.moved.emit(int(address), pos)   # treat as motion end
            self.log.emit(f"Address {address} STOP → {pos:.6f} {unit}" if unit=="mm" else
                          f"Address {address} STOP → {pos:.2f} {unit}")
        except Exception as e:
            self.error.emit(f"Stop failed: {e}")
        finally:
            self._stop_poll(address)
            self.moving.emit(int(address), False)

    @QtCore.pyqtSlot(int, float, str)
    def set_target_speed(self, address: int, new_spd: float, unit: str):
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            dev = self.conn.get_device(int(address))
            if unit == "mm":
                dev.settings.set(BinarySettings.TARGET_SPEED, float(new_spd),
                                 Units.VELOCITY_MILLIMETRES_PER_SECOND)
                rb = dev.settings.get(BinarySettings.TARGET_SPEED,
                                      Units.VELOCITY_MILLIMETRES_PER_SECOND)
            else:
                dev.settings.set(BinarySettings.TARGET_SPEED, float(new_spd),
                                 Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
                rb = dev.settings.get(BinarySettings.TARGET_SPEED,
                                      Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
            if rb is not None:
                self.speed.emit(int(address), float(rb))
                self.log.emit(f"Address {address} target speed set to: {rb:.3f} {unit}/s")
        except Exception as e:
            self.error.emit(f"Set target speed failed: {e}")

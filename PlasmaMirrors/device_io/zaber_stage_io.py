from PyQt6 import QtCore
import threading
from zaber_motion import Library, Units
from zaber_motion.binary import Connection, CommandCode, BinarySettings

class ZaberStageIO(QtCore.QObject):
    log = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    opened = QtCore.pyqtSignal()
    discovered = QtCore.pyqtSignal(list)
    position = QtCore.pyqtSignal(int, float, float)
    moved = QtCore.pyqtSignal(int, float)
    homed = QtCore.pyqtSignal(int)
    speed = QtCore.pyqtSignal(int, float)
    moving  = QtCore.pyqtSignal(int, bool)

    def __init__(self, port: str, baud: int):
        super().__init__()
        self.port = port
        self.baud = baud
        self.conn = None

    @QtCore.pyqtSlot()
    def open(self):
        try:
            Library.enable_device_db_store()
            self.conn = Connection.open_serial_port(self.port, baud_rate=self.baud)
            self.log.emit(f"I/O opened {self.port} (Binary, {self.baud} baud)")
            self.opened.emit()
        except Exception as e:
            self.error.emit(f"Open failed: {e}")

    @QtCore.pyqtSlot()
    def close(self):
        try:
            if self.conn is not None:
                self.conn.close()
                self.log.emit("I/O closed")
        except Exception as e:
            self.error.emit(f"Close error: {e}")
        finally:
            self.conn = None

    @QtCore.pyqtSlot()
    def discover(self):
        try:
            if self.conn is None:
                self.open()
                if self.conn is None:
                    return
            devices = self.conn.detect_devices(identify_devices=True)
            self.log.emit(f"Found {len(devices)} device(s) on {self.port}:")
            found = []
            for dev in devices:
                addr = dev.device_address
                label = getattr(dev, "name", None)
                try:
                    ident = dev.identify()
                    label = label or getattr(ident, "name", None)
                except Exception:
                    pass
                self.log.emit(f"- Address {addr}: {label or 'Unknown'}")
                found.append({"address": addr, "label": label or "Unknown"})
            self.discovered.emit(found)
        except Exception as e:
            self.error.emit(f"Discover failed: {e}")

    @QtCore.pyqtSlot(int, str)
    def read_position_speed(self, address: int, unit: str):
        try:
            if self.conn is None:
                self.error.emit("Not connected")
                return
            dev = self.conn.get_device(int(address))
            try:
                dev.identify()
            except Exception:
                pass
            steps = dev.get_position()
            if unit == "mm":
                pos = dev.get_position(Units.LENGTH_MILLIMETRES)
                spd = dev.settings.get(BinarySettings.TARGET_SPEED, Units.VELOCITY_MILLIMETRES_PER_SECOND)
                self.position.emit(int(address), float(steps), float(pos))
                self.speed.emit(int(address), float(spd))
                self.log.emit(f"Address {address}: {steps:.0f} steps, {pos:.6f} mm, {spd:.2f} mm/s")
            else:
                pos = dev.get_position(Units.ANGLE_DEGREES)
                spd = dev.settings.get(BinarySettings.TARGET_SPEED, Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
                self.position.emit(int(address), float(steps), float(pos))
                self.speed.emit(int(address), float(spd))
                self.log.emit(f"Address {address}: {steps:.0f} steps, {pos:.2f} deg, {spd:.2f} deg/s")
        except Exception as e:
            self.error.emit(f"Read position failed: {e}")

    def _start_waiter(self, address: int, unit: str, homed: bool = False):
        """Spawn a small worker that waits for the device to go idle, then emits final signals."""
        def _wait_and_finalize():
            try:
                dev = self.conn.get_device(int(address))
                dev.wait_until_idle()  # this blocks, but in a worker thread now
                steps = dev.get_position()
                if unit == "mm": 
                    pos = dev.get_position(Units.LENGTH_MILLIMETRES)
                else:
                    pos = dev.get_position(Units.ANGLE_DEGREES)
                # push final state
                self.position.emit(int(address), float(steps), float(pos))
                if homed:
                    self.homed.emit(int(address))
                else:
                    self.moved.emit(int(address), float(pos))
            except Exception as e:
                self.error.emit(f"Wait/finalize failed (addr {address}): {e}")
            finally:
                self.moving.emit(int(address), False)
        threading.Thread(target=_wait_and_finalize, daemon=True).start()

    @QtCore.pyqtSlot(int, float, str)
    def move_absolute(self, address: int, target_pos: float, unit: str):
        """Send move and return immediately; do not block the StageIO thread."""
        self.moving.emit(int(address), True)
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            dev = self.conn.get_device(int(address))
            if unit == "mm":
                import time
                t0 = time.monotonic()
                self.log.emit(f"move_absolute ENTER {t0:.3f}")
                dev.move_absolute(float(target_pos), Units.LENGTH_MILLIMETRES)
                t1 = time.monotonic()
                self.log.emit(f"move_absolute AFTER CALL {t1:.3f}  (Δ={t1 - t0:.3f}s)")
            else:
                dev.move_absolute(float(target_pos), Units.ANGLE_DEGREES)
            self._start_waiter(address, unit)
        except Exception as e:
            self.error.emit(f"Move failed: {e}")
            self.moving.emit(int(address), False)

    # @QtCore.pyqtSlot(int, float, str)
    # def move_absolute(self, address: int, target_pos: float, unit: str):
    #     self.moving.emit(int(address), True)
    #     try:
    #         if self.conn is None:
    #             self.error.emit("Not connected")
    #             return
    #         dev = self.conn.get_device(int(address))
    #         try:
    #             dev.identify()
    #         except Exception:
    #             pass
    #         if unit == "mm":
    #             dev.move_absolute(float(target_pos), Units.LENGTH_MILLIMETRES)
    #             dev.wait_until_idle()
    #             steps = dev.get_position()
    #             pos = dev.get_position(Units.LENGTH_MILLIMETRES)
    #         else:
    #             dev.move_absolute(float(target_pos), Units.ANGLE_DEGREES)
    #             dev.wait_until_idle()
    #             steps = dev.get_position()
    #             pos = dev.get_position(Units.ANGLE_DEGREES)
    #         self.position.emit(int(address), float(steps), float(pos))
    #         self.moved.emit(int(address), float(pos))
    #     except Exception as e:
    #         self.error.emit(f"Move failed: {e}")
    #     finally:
    #         self.moving.emit(int(address), False)

    @QtCore.pyqtSlot(int)
    def home(self, address: int):
        self.moving.emit(int(address), True)
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            dev = self.conn.get_device(int(address))
            dev.home()
            self._start_waiter(address, "mm",homed=True)  # unit here is only for formatting; you can map by address
        except Exception as e:
            self.error.emit(f"Home failed: {e}")
            self.moving.emit(int(address), False)

    # @QtCore.pyqtSlot(int)
    # def home(self, address: int):
    #     self.moving.emit(int(address), True)
    #     try:
    #         if self.conn is None:
    #             self.error.emit("Not connected"); return
    #         dev = self.conn.get_device(int(address))
    #         dev.home()
    #         dev.wait_until_idle()
    #         self.homed.emit(int(address))
    #     except Exception as e:
    #         self.error.emit(f"Home failed: {e}")
    #     finally:
    #         self.moving.emit(int(address), False)

    @QtCore.pyqtSlot(int, float, str)
    def move_delta(self, address: int, delta_pos: float, unit: str):
        self.moving.emit(int(address), True)
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
            self._start_waiter(address, unit)
        except Exception as e:
            self.error.emit(f"Move delta failed: {e}")
            self.moving.emit(int(address), False)

    # @QtCore.pyqtSlot(int, float, str)
    # def move_delta(self, address: int, delta_pos: float, unit: str):
    #     self.moving.emit(int(address), True)
    #     try:
    #         if self.conn is None:
    #             self.error.emit("Not connected"); return
    #         dev = self.conn.get_device(int(address))
    #         try:
    #             dev.identify()
    #         except Exception:
    #             pass
    #         if unit == "mm":
    #             cur = float(dev.get_position(Units.LENGTH_MILLIMETRES))
    #             target = cur + float(delta_pos)
    #             dev.move_absolute(target, Units.LENGTH_MILLIMETRES)
    #             dev.wait_until_idle()
    #             steps = dev.get_position()
    #             pos = dev.get_position(Units.LENGTH_MILLIMETRES)
    #             self.log.emit(f"Address {address} jog {delta_pos:+.6f} mm → {pos:.6f} mm")
    #         else:
    #             cur = float(dev.get_position(Units.ANGLE_DEGREES))
    #             target = cur + float(delta_pos)
    #             dev.move_absolute(target, Units.ANGLE_DEGREES)
    #             dev.wait_until_idle()
    #             steps = dev.get_position()
    #             pos = dev.get_position(Units.ANGLE_DEGREES)
    #             self.log.emit(f"Address {address} jog {delta_pos:+.2f} deg → {pos:.2f} deg")
    #         self.position.emit(int(address), float(steps), float(pos))
    #         self.moved.emit(int(address), float(pos))
    #     except Exception as e:
    #         self.error.emit(f"Move delta failed: {e}")
    #     finally:
    #         self.moving.emit(int(address), False)

    @QtCore.pyqtSlot(int, str)
    def stop(self, address: int, unit: str):
        """
        Decelerate to a halt immediately. Safe to call while a move is in progress.
        """
        try:
            if self.conn is None:
                self.error.emit("Not connected"); return
            dev = self.conn.get_device(int(address))

            # High-level stop; returns current pos in requested units.
            from zaber_motion import Units
            if unit == "mm":
                pos = dev.stop(Units.LENGTH_MILLIMETRES)
            elif unit == "deg":
                pos = dev.stop(Units.ANGLE_DEGREES)
            else:
                pos = dev.stop(Units.NATIVE)

            steps = dev.get_position()
            self.position.emit(int(address), float(steps), float(pos))
            self.moved.emit(int(address), float(pos))  # treat stop as a 'motion ended' event
            self.moving.emit(int(address), False)

            # nice log
            if unit == "deg":
                self.log.emit(f"Address {address} STOP → {pos:.2f} deg")
            elif unit == "mm":
                self.log.emit(f"Address {address} STOP → {pos:.6f} mm")
            else:
                self.log.emit(f"Address {address} STOP")
        except Exception as e:
            self.error.emit(f"Stop failed: {e}")

    # @QtCore.pyqtSlot(int, str)
    # def stop(self, address: int, unit: str):
    #     try:
    #         if self.conn is None:
    #             self.error.emit("Not connected")
    #             return
    #         dev = self.conn.get_device(int(address))
    #         try:
    #             dev.identify()
    #         except Exception:
    #             pass
    #         dev.stop()
    #         dev.wait_until_idle()
    #         steps = dev.get_position()
    #         # set moving indicator to off
    #         self.moving.emit(int(address), False)
    #         if unit == "mm":
    #             pos = dev.get_position(Units.LENGTH_MILLIMETRES)
    #             self.position.emit(int(address), float(steps), float(pos))
    #             self.log.emit(f"Address {address} stopped at {steps:.0f} steps, {pos:.6f} mm")
    #         else:
    #             pos = dev.get_position(Units.ANGLE_DEGREES)
    #             self.position.emit(int(address), float(steps), float(pos))
    #             self.log.emit(f"Address {address} stopped at {steps:.0f} steps, {pos:.2f} deg")
    #     except Exception as e:
    #         self.error.emit(f"Stop failed: {e}")


    @QtCore.pyqtSlot(int, float)
    def set_target_speed(self, address: int, new_spd: float, unit):
        try:
            if self.conn is None:
                self.error.emit("Not connected")
                return
            dev = self.conn.get_device(int(address))
            try:
                dev.identify()
            except Exception:
                pass

            if unit == "mm/s":
                try:
                    dev.settings.set(BinarySettings.TARGET_SPEED, float(new_spd),
                                    Units.VELOCITY_MILLIMETRES_PER_SECOND)
                except Exception as e:
                    self.error.emit(f"Set speed failed: {e}")
                    return
                ts = dev.settings.get(BinarySettings.TARGET_SPEED,
                                    Units.VELOCITY_MILLIMETRES_PER_SECOND)
                if ts is not None:
                    self.speed.emit(int(address), float(ts))
                    self.log.emit(f"Address {address} target speed set to: {ts:.6f} mm/s")
                else:
                    self.log.emit("Target Speed set; read-back unavailable")

            elif unit == "deg/s":
                try:
                    dev.settings.set(BinarySettings.TARGET_SPEED, float(new_spd),
                                    Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
                except Exception as e:
                    self.error.emit(f"Set speed failed: {e}")
                    return
                ts = dev.settings.get(BinarySettings.TARGET_SPEED,
                                    Units.ANGULAR_VELOCITY_DEGREES_PER_SECOND)
                if ts is not None:
                    self.speed.emit(int(address), float(ts))
                    self.log.emit(f"Address {address} target speed set to: {ts:.2f} deg/s")
                else:
                    self.log.emit("Target Speed set; read-back unavailable")
        except Exception as e:
            self.error.emit(f"Set target speed failed: {e}")

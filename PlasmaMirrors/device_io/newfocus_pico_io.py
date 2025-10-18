from PyQt6 import QtCore
import os
import sys


class NewFocusPicoIO(QtCore.QObject):
    """Minimal pythonnet-backed wrapper for Newport/New Focus Picomotor 8742.

    Responsibilities:
    - Load DeviceIOLib.dll and CmdLib8742.dll using pythonnet (if available).
    - Discover adapters and slave addresses.
    - Read model/serial for adapter and slaves.
    - Perform RelativeMove on an axis for any address.
    - Stop motion (per-address and StopAll).
    - Close/shutdown cleanly.

    This class is intended to be moved to a QThread and have its slots invoked
    via queued connections from the UI thread.
    """

    log = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    opened = QtCore.pyqtSignal()
    discovered = QtCore.pyqtSignal(list)  # list of dicts: { 'adapter_key', 'address', 'model_serial' }
    moved = QtCore.pyqtSignal(str, int, int)  # adapter_key, address, axis
    moving = QtCore.pyqtSignal(str, int, bool)

    def __init__(self, dll_dir: str | None = None, usb_pid: int = 0x4000):
        super().__init__()
        self.dll_dir = dll_dir
        self.usb_pid = int(usb_pid)
        self.deviceIO = None
        self.cmd = None
        self._open = False

    @QtCore.pyqtSlot()
    def open(self):
        """Load assemblies and discover devices."""
        try:
            if self.dll_dir and os.path.isdir(self.dll_dir) and sys.platform == 'win32':
                try:
                    os.add_dll_directory(self.dll_dir)
                    self.log.emit(f'Added DLL directory: {self.dll_dir}')
                except Exception:
                    os.environ['PATH'] = self.dll_dir + os.pathsep + os.environ.get('PATH', '')
                    self.log.emit(f'Prepended DLL dir to PATH: {self.dll_dir}')

            try:
                import clr
            except Exception as e:
                self.error.emit('pythonnet (clr) not available: ' + str(e))
                return

            # add references
            try:
                if self.dll_dir:
                    clr.AddReference(os.path.join(self.dll_dir, 'DeviceIOLib.dll'))
                    clr.AddReference(os.path.join(self.dll_dir, 'CmdLib8742.dll'))
                else:
                    clr.AddReference('DeviceIOLib')
                    clr.AddReference('CmdLib8742')
            except Exception as e:
                # best-effort: still try to import types
                self.log.emit('Warning: AddReference failed: ' + str(e))

            from Newport.DeviceIOLib import DeviceIOLib
            from NewFocus.PicomotorApp import CmdLib8742

            self.deviceIO = DeviceIOLib(True)
            self.cmd = CmdLib8742(self.deviceIO)

            try:
                self.deviceIO.SetUSBProductID(int(self.usb_pid))
            except Exception:
                pass

            # Discover devices (5 attempts, 5000 ms wait)
            try:
                self.deviceIO.DiscoverDevices(5, 5000)
            except Exception as e:
                self.log.emit('DiscoverDevices raised: ' + str(e))

            # get adapter keys
            try:
                keys = list(self.deviceIO.GetDeviceKeys() or [])
            except Exception:
                keys = []

            adapters = []
            for k in keys:
                try:
                    # attempt to open adapter if not already
                    try:
                        ok = self.deviceIO.Open(k)
                    except Exception:
                        ok = False

                    # Query slave addresses once and compute the max address.
                    # The adapter (primary) is conventionally address 1. Some
                    # controllers return only slave addresses (e.g., [2]) so we
                    # must include 1 in the range.
                    addrs = []
                    try:
                        a = self.cmd.GetDeviceAddresses(k)
                        if a is not None:
                            addrs = list(a)
                    except Exception:
                        addrs = []

                    # Determine maximum address (include primary address 1)
                    max_addr = 1
                    try:
                        if addrs:
                            max_addr = max([int(x) for x in addrs] + [1])
                    except Exception:
                        max_addr = 1

                    # Query model/serial for each address from 1..max_addr
                    for addr in range(1, int(max_addr) + 1):
                        try:
                            ms = None
                            try:
                                ms = self.cmd.GetModelSerial(k, int(addr))
                            except Exception:
                                # fallback to DeviceIOLib if available
                                try:
                                    if addr == 1:
                                        ms = self.deviceIO.GetModelSerial(k)
                                except Exception:
                                    ms = None
                            adapters.append({'adapter_key': str(k), 'address': int(addr), 'model_serial': str(ms) if ms is not None else ''})
                        except Exception:
                            adapters.append({'adapter_key': str(k), 'address': int(addr), 'model_serial': ''})
                except Exception:
                    continue

            self._open = True
            self.opened.emit()
            self.discovered.emit(adapters)
            self.log.emit(f'Picomotor I/O opened; adapters: {len(keys)}')
        except Exception as e:
            self.error.emit('Open failed: ' + str(e))

    @QtCore.pyqtSlot(str, int, int, int)
    def relative_move(self, adapter_key: str, address: int, axis: int, steps: int):
        """Perform a relative move on the given adapter/address/axis (steps).

        This method will try likely overload orders for RelativeMove depending on
        the CmdLib8742 signature on the loaded assembly.
        """
        try:
            if not self.cmd:
                self.error.emit('CmdLib not loaded')
                return
            self.moving.emit(adapter_key, int(address), True)
            # Try common overloads. Many vendor assemblies expose both orderings.
            tried = []
            # 4-arg: (key, address, axis, steps)
            try:
                res = self.cmd.RelativeMove(adapter_key, int(address), int(axis), int(steps))
                tried.append(('key,addr,axis,steps', res))
            except Exception:
                try:
                    # alternate 4-arg: (key, axis, address, steps)
                    res = self.cmd.RelativeMove(adapter_key, int(axis), int(address), int(steps))
                    tried.append(('key,axis,addr,steps', res))
                except Exception:
                    try:
                        # 3-arg: (key, axis, steps)
                        res = self.cmd.RelativeMove(adapter_key, int(axis), int(steps))
                        tried.append(('key,axis,steps', res))
                    except Exception as e:
                        self.error.emit('RelativeMove: all overload attempts failed: ' + str(e))
                        self.moving.emit(adapter_key, int(address), False)
                        return

            # Poll motion done
            done = False
            for _ in range(200):
                try:
                    b = False
                    try:
                        # two-arg overloads may expect (key, axis, addr, outBool)
                        out = self.cmd.GetMotionDone(adapter_key, int(axis), int(address))
                        # If GetMotionDone returns a tuple-like, coerce
                        if isinstance(out, tuple) and len(out) >= 1:
                            b = bool(out[0])
                        else:
                            b = bool(out)
                    except Exception:
                        try:
                            out = self.cmd.GetMotionDone(adapter_key, int(axis))
                            if isinstance(out, tuple) and len(out) >= 1:
                                b = bool(out[0])
                            else:
                                b = bool(out)
                        except Exception:
                            b = True
                    if b:
                        done = True
                        break
                except Exception:
                    pass
                QtCore.QThread.msleep(20)

            self.moved.emit(adapter_key, int(address), int(axis))
            self.moving.emit(adapter_key, int(address), False)
            if not done:
                self.log.emit('RelativeMove: move issued (motion-done poll timed out)')
            else:
                self.log.emit('RelativeMove: complete')
        except Exception as e:
            self.error.emit('RelativeMove failed: ' + str(e))
            try:
                self.moving.emit(adapter_key, int(address), False)
            except Exception:
                pass

    @QtCore.pyqtSlot(str, int)
    def stop_motion(self, adapter_key: str, address: int):
        try:
            if not self.cmd:
                self.error.emit('CmdLib not loaded')
                return
            try:
                self.cmd.StopMotion(adapter_key, int(address))
                self.log.emit(f'StopMotion requested for {adapter_key} addr={address}')
            except Exception:
                try:
                    self.cmd.AbortMotion(adapter_key, int(address))
                    self.log.emit(f'AbortMotion requested for {adapter_key} addr={address}')
                except Exception as e:
                    self.error.emit('Stop failed: ' + str(e))
        except Exception as e:
            self.error.emit('StopMotion wrapper failed: ' + str(e))

    @QtCore.pyqtSlot()
    def stop_all(self):
        try:
            if not self.cmd:
                self.error.emit('CmdLib not loaded')
                return
            # attempt abort on adapter-level and per-address
            try:
                keys = list(self.deviceIO.GetDeviceKeys() or [])
            except Exception:
                keys = []
            for k in keys:
                try:
                    # try adapter-level abort
                    try:
                        self.cmd.AbortMotion(k)
                    except Exception:
                        pass
                    # try to stop each known address
                    addrs = []
                    try:
                        a = self.cmd.GetDeviceAddresses(k)
                        if a is not None:
                            addrs = list(a)
                    except Exception:
                        addrs = []
                    for addr in addrs:
                        try:
                            self.cmd.StopMotion(k, int(addr))
                        except Exception:
                            try:
                                self.cmd.AbortMotion(k, int(addr))
                            except Exception:
                                pass
                except Exception:
                    continue
            self.log.emit('Stop All: issued stop/abort to all adapters/addresses')
        except Exception as e:
            self.error.emit('Stop All failed: ' + str(e))

    @QtCore.pyqtSlot()
    def close(self, adapter_key: str | None = None):
        try:
            if adapter_key and self.deviceIO:
                try:
                    self.deviceIO.Close(adapter_key)
                except Exception:
                    pass
            else:
                # close all
                try:
                    keys = list(self.deviceIO.GetDeviceKeys() or [])
                except Exception:
                    keys = []
                for k in keys:
                    try:
                        self.deviceIO.Close(k)
                    except Exception:
                        pass
            try:
                if getattr(self, 'cmd', None) is not None:
                    try: self.cmd.Shutdown()
                    except Exception: pass
            except Exception:
                pass
            try:
                if getattr(self, 'deviceIO', None) is not None:
                    try: self.deviceIO.Shutdown()
                    except Exception: pass
            except Exception:
                pass
            self._open = False
            self.log.emit('Picomotor I/O closed')
        except Exception as e:
            self.error.emit('Close failed: ' + str(e))

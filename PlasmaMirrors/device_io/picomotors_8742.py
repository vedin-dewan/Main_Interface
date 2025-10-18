"""
Wrapper for Newport Picomotor 8742 using pylablib.devices.Newport.Picomotor8742.

This module provides a higher-level `Picomotors8742Manager` class and a simple
CLI to discover devices (USB/Ethernet), open controllers (including daisy-chained
RS-485 devices), query axes, and perform simple moves.

Requirements:
  pip install pylablib

Notes:
- The implementation uses pylablib when available; if pylablib is not installed
  the CLI will print an informative error and exit.
- The manager supports multiaddr (daisy-chained RS-485) operation via
  `multiaddr=True` when opening the device.

Example usage:
  python device_io/picomotors_8742.py --list-usb
  python device_io/picomotors_8742.py --open-usb 0 --scan
  python device_io/picomotors_8742.py --open-usb 0 --move-by 1 100

This file is intended as a test harness you can later integrate into the GUI
by wrapping the manager into a QObject moved to a QThread and exposing signals.
"""
from __future__ import annotations

import sys
import time
from typing import Optional, List

try:
    from pylablib.devices import Newport_pocomotors as Newport
except Exception:
    Newport = None


class Picomotors8742Manager:
    def __init__(self, identifier: Optional[int | str] = None, multiaddr: bool = True, scan: bool = True, logger=print):
        if Newport is None:
            raise RuntimeError("pylablib is required (pip install pylablib).")
        self.identifier = identifier
        self.multiaddr = bool(multiaddr)
        self.scan = bool(scan)
        self._dev = None
        self.logger = logger

    @staticmethod
    def list_usb_count() -> int:
        return Newport.get_usb_devices_number_picomotor()

    def open(self) -> None:
        # identifier can be None, int(index), or host string
        if isinstance(self.identifier, str) and self.identifier.isdigit():
            ident = int(self.identifier)
        else:
            ident = self.identifier
        self._dev = Newport.Picomotor8742(ident, multiaddr=self.multiaddr, scan=self.scan)
        # After opening, you can read addr_map if multiaddr
        try:
            time.sleep(0.05)
            if self.multiaddr:
                # device object usually supports get_addr_map
                try:
                    self.addr_map = self._dev.get_addr_map()
                except Exception:
                    self.addr_map = None
        except Exception:
            self.addr_map = None
        self.logger(f"Opened Picomotor device (id={self.identifier}), multiaddr={self.multiaddr}, scan={self.scan}")

    def close(self) -> None:
        try:
            if self._dev is not None:
                try:
                    self._dev.close()
                except Exception:
                    pass
        finally:
            self._dev = None

    def get_all_axes(self) -> List[int]:
        if self._dev is None:
            raise RuntimeError("Device not open")
        return list(self._dev.get_all_axes())

    def autodetect_motors(self) -> None:
        if self._dev is None:
            raise RuntimeError("Device not open")
        self._dev.autodetect_motors()

    def save_parameters(self) -> None:
        if self._dev is None:
            raise RuntimeError("Device not open")
        self._dev.save_parameters()

    def get_addr_map(self):
        if self._dev is None:
            raise RuntimeError("Device not open")
        try:
            return self._dev.get_addr_map()
        except Exception:
            return None

    def get_position(self, axis: int, addr: Optional[int] = None) -> Optional[float]:
        if self._dev is None:
            raise RuntimeError("Device not open")
        try:
            return self._dev.get_position(int(axis), addr=addr)
        except Exception:
            return None

    def move_by(self, axis: int, steps: int, addr: Optional[int] = None, wait: bool = True) -> bool:
        if self._dev is None:
            raise RuntimeError("Device not open")
        try:
            self._dev.move_by(int(axis), int(steps), addr=addr)
            if wait:
                # naive wait: poll position until movement stops
                time.sleep(0.05)
                prev = None
                for _ in range(300):
                    pos = self.get_position(axis, addr=addr)
                    if prev is not None and pos == prev:
                        return True
                    prev = pos
                    time.sleep(0.05)
                return True
            return True
        except Exception:
            return False

    def move_to(self, axis: int, target: int, addr: Optional[int] = None, wait: bool = True) -> bool:
        if self._dev is None:
            raise RuntimeError("Device not open")
        try:
            self._dev.move_to(int(axis), int(target), addr=addr)
            if wait:
                # poll for completion with timeout
                prev = None
                for _ in range(600):
                    pos = self.get_position(axis, addr=addr)
                    if pos == int(target):
                        return True
                    time.sleep(0.05)
                return False
            return True
        except Exception:
            return False


# ----------------- CLI -----------------

def _main(argv: list[str]):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--list-usb", action="store_true", help="Print number of USB Picomotor devices")
    p.add_argument("--open-usb", type=int, help="Open USB device by index (0..N-1)")
    p.add_argument("--open-host", type=str, help="Open by host name / IP")
    p.add_argument("--multiaddr", action="store_true", help="Open with multiaddr=True (RS-485 daisy-chained)")
    p.add_argument("--scan", action="store_true", help="Scan network on open (default True)")
    p.add_argument("--get-axes", action="store_true", help="Print axes available on opened device")
    p.add_argument("--addr-map", action="store_true", help="Print address map (multiaddr)")
    p.add_argument("--get-pos", nargs=1, metavar=("AXIS",), help="Get position of AXIS")
    p.add_argument("--move-by", nargs=2, metavar=("AXIS","STEPS"), help="Move axis by STEPS")
    p.add_argument("--move-to", nargs=2, metavar=("AXIS","TARGET"), help="Move axis to TARGET")
    args = p.parse_args(argv)

    if args.list_usb:
        if Newport is None:
            print("pylablib not installed. pip install pylablib")
            return 2
        print(Picomotors8742Manager.list_usb_count())
        return 0

    ident = None
    if args.open_usb is not None:
        ident = int(args.open_usb)
    if args.open_host:
        ident = args.open_host

    if ident is None:
        print("Specify --open-usb N or --open-host NAME (or --list-usb first)")
        return 2

    mgr = Picomotors8742Manager(identifier=ident, multiaddr=args.multiaddr, scan=(True if args.scan else False), logger=print)
    try:
        mgr.open()
    except Exception as e:
        print(f"Failed to open device: {e}")
        return 3

    try:
        if args.get_axes:
            print(mgr.get_all_axes())
        if args.addr_map:
            print(mgr.get_addr_map())
        if args.get_pos:
            ax = int(args.get_pos[0]); print(mgr.get_position(ax))
        if args.move_by:
            ax = int(args.move_by[0]); steps = int(args.move_by[1]); print(mgr.move_by(ax, steps))
        if args.move_to:
            ax = int(args.move_to[0]); tgt = int(args.move_to[1]); print(mgr.move_to(ax, tgt))
    finally:
        mgr.close()
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))

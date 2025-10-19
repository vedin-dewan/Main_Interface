"""
scan_and_control_8742.py

Minimal scanner for Newport Picomotor 8742 daisy chains using pythonnet.

Usage: (run in the conda env where pythonnet is installed)
  python scan_and_control_8742.py [DLL_FOLDER]

If a DLL folder is provided the script will add it to the process DLL search
path so the vendor assemblies can be loaded. The script then discovers the
first adapter, opens it, and prints the addresses of daisy-chained controllers
behind that adapter using CmdLib8742.GetDeviceAddresses(adapter_key).

There is a single example RelativeMove call commented out near the end —
uncomment it if you want to perform a quick relative move after confirming
addresses and axis numbers.
"""

import os
import sys
import time

# Optional: first CLI arg is the folder containing DeviceIOLib.dll and CmdLib8742.dll
dll_dir = r"C:\Program Files\New Focus\New Focus Picomotor Application\Bin"#sys.argv[1] if len(sys.argv) > 1 else None

if dll_dir and os.path.isdir(dll_dir) and sys.platform == 'win32':
    # Ensure the process can find vendor DLLs (Python 3.8+)
    try:
        os.add_dll_directory(dll_dir)
        print('Added DLL directory to process search path:', dll_dir)
    except Exception:
        # fallback: prepend to PATH
        os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')
        print('Prepended DLL directory to PATH:', dll_dir)

try:
    import clr
except Exception:
    print('pythonnet is required (clr). Install into this env: conda install -c conda-forge pythonnet')
    raise

# Add references - use full path if dll_dir provided, otherwise rely on assembly name
if dll_dir:
    clr.AddReference(os.path.join(dll_dir, 'DeviceIOLib.dll'))
    clr.AddReference(os.path.join(dll_dir, 'CmdLib8742.dll'))
else:
    clr.AddReference('DeviceIOLib')
    clr.AddReference('CmdLib8742')

from Newport.DeviceIOLib import DeviceIOLib
from NewFocus.PicomotorApp import CmdLib8742

# Create objects
deviceIO = DeviceIOLib(True)
cmd = CmdLib8742(deviceIO)

# Optional: filter USB by product ID (0x4000 shown in vendor sample)
deviceIO.SetUSBProductID(0x4000)

# Discover adapters (USB + Ethernet) and wait 5 seconds
deviceIO.DiscoverDevices(5, 5000)

# Get discovered adapter keys
keys = deviceIO.GetDeviceKeys()
n = deviceIO.GetDeviceCount()
print('Adapters found:', n)
if n == 0:
    print('No adapters discovered; check cables/driver and DLL paths')
    sys.exit(0)

# Use the first adapter key
adapter_key = keys[0]
print('Using adapter key:', adapter_key)

# Open the adapter
if not deviceIO.Open(adapter_key):
    print('Failed to open adapter:', adapter_key)
    sys.exit(1)

# Get addresses of daisy-chained controllers behind this adapter
addresses = cmd.GetDeviceAddresses(adapter_key)
if addresses is None:
    print('No addresses returned by GetDeviceAddresses (try running Scan or check wiring)')
else:
    addresses = list(addresses)
    print('Discovered addresses behind adapter:', addresses)
print("Primary Model and Serial number (address 1):", cmd.GetModelSerial(adapter_key,1))
print("Slave model ad serial number (address 2):", cmd.GetModelSerial(adapter_key,2))
# ----------------- example move (comment/uncomment to enable) -----------------
# WARNING: only enable after you confirm addresses and axis numbers. This example
# moves axis 1 on address addresses[0] by +10 steps. Uncomment the next line to run.
addr = 1
motor_axes = 2
steps = +100
move = cmd.RelativeMove(adapter_key, addr, motor_axes,steps)
time.sleep(5)  # wait for move to complete 

moved = cmd.GetMotionDone(adapter_key,addr,motor_axes,True)
print(f'motion done: {moved}')
pos = cmd.GetPosition(adapter_key, addr, motor_axes)
print(f'Moved address {addr} axis {motor_axes} by {steps} steps to position {pos}')
# Close and shutdown
deviceIO.Close(adapter_key)
cmd.Shutdown()
deviceIO.Shutdown()

print('Done')


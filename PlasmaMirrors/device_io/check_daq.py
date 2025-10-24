# save as check_daq.py and run in the same Python environment you use for the app
import nidaqmx
from nidaqmx.system import System

s = System.local()
print("Detected system:", s)
dev_names = [d.name for d in s.devices]
print("Devices:", dev_names)
for name in dev_names:
    dev = s.devices[name]
    print(f"--- Device: {name} ---")
    print("  Product Type:", getattr(dev, 'product_type', None))
    print("  AI chans:", [c.name for c in dev.ai_physical_chans])
    print("  AO chans:", [c.name for c in getattr(dev, 'ao_physical_chans', [])])
    print("  DO lines:", [l.name for l in getattr(dev, 'do_lines', [])])
    # counters: many low-end USB devices do not have ctr channels
    try:
        print("  CI chans:", [c.name for c in getattr(dev, 'ci_physical_chans', [])])
        print("  CO chans:", [c.name for c in getattr(dev, 'co_physical_chans', [])])
    except Exception as e:
        print("  Counters not listed / not available:", e)
    # list PFI/terminals (routing candidates)
    try:
        print("  Terminals:", dev.terminals)
    except Exception:
        pass
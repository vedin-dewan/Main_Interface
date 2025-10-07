"""Convenience module that imports subpackages for easy interactive
development. This file can be imported either as a package-relative
module (when the project is used as a package) or as a top-level module
when running individual panels/scripts. The code below attempts the
package-relative imports first and falls back to importing the same
modules from the project root.
"""

try:
	# Preferred: package-relative import (works when the project is used as a package)
	from .panels import *
	from .device_io import *
	from .widgets import *
except Exception:
	# Fallback: import using the project root on sys.path (works when running files directly)
	import os
	import sys

	ROOT = os.path.dirname(__file__)
	if ROOT not in sys.path:
		sys.path.insert(0, ROOT)

	# import the subpackages as top-level modules and expose their symbols
	try:
		import panels as _panels
		import device_io as _device_io
		import widgets as _widgets
		from panels import *
		from device_io import *
		from widgets import *
	except Exception:
		# If even this fails, re-raise the original error for visibility
		raise
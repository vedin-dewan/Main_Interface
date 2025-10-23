from PyQt6 import QtWidgets, QtCore, QtGui


class DeviceStatusPanel(QtWidgets.QWidget):
    """Panel listing connected devices with PWR/STS/Description columns.

    Layout mirrors the screenshot: a tree with groups: Zaber Stages, Cameras, Spectrometers.
    Methods are provided so MainWindow can populate and update device states.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('device_status')
    # no timers: rely on moving/moved signals to indicate state

        title = QtWidgets.QLabel('Devices')
        title.setStyleSheet('font-weight:700; font-size:14px;')

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(['Devices', 'PWR', 'STS', 'Description'])
        self.tree.header().setStretchLastSection(False)
        # fixed column widths
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.tree.header().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.tree.header().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.tree.setColumnWidth(0, 180)   # Devices
        self.tree.setColumnWidth(1, 48)    # PWR
        self.tree.setColumnWidth(2, 48)    # STS
        self.tree.setColumnWidth(3, 380)   # Description
        self.tree.setRootIsDecorated(True)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(title)
        lay.addWidget(self.tree)

        # group items
        self.group_stages = QtWidgets.QTreeWidgetItem(self.tree, ['Zaber Stages'])
        self.group_cameras = QtWidgets.QTreeWidgetItem(self.tree, ['Cameras'])
        self.group_specs = QtWidgets.QTreeWidgetItem(self.tree, ['Spectrometers'])
        self.tree.addTopLevelItem(self.group_stages)
        self.tree.addTopLevelItem(self.group_cameras)
        self.tree.addTopLevelItem(self.group_specs)

        # maps for quick lookup
        self._stage_items = {}    # addr -> QTreeWidgetItem
        self._camera_items = {}   # camera name token -> item
        self._spec_items = {}     # spec filename token -> item

    # ---------- population ----------
    def populate(self, device_tabs, part1_rows=None):
        """Populate lists from `device_tabs` (DeviceTabsPanel) and optional part1_rows for mapping.
        device_tabs.get_stages() should return the stages list; device_tabs._cameras and _spectrometers are used.
        """
        try:
            # Clear existing children
            self.group_stages.takeChildren()
            self.group_cameras.takeChildren()
            self.group_specs.takeChildren()
            self._stage_items.clear()
            self._camera_items.clear()
            self._spec_items.clear()

            stages = []
            try:
                stages = device_tabs.get_stages() or []
            except Exception:
                stages = []

            # Add stage children keyed by configured stage number ('num') where available
            for i, s in enumerate(stages, start=1):
                # prefer explicit 'num' in stage definition, fallback to enumerated index
                try:
                    addr = int(s.get('num', i))
                except Exception:
                    addr = int(i)
                name = s.get('name') or s.get('Abr') or f'Addr{addr}'
                desc = s.get('description', '') or s.get('desc', '') or ''
                it = QtWidgets.QTreeWidgetItem(self.group_stages, [f"{addr}. {name}", '', '', desc])
                it.setData(0, QtCore.Qt.ItemDataRole.UserRole, {'address': addr})
                self.group_stages.addChild(it)
                self._stage_items[int(addr)] = it

            # Cameras
            cams = getattr(device_tabs, '_cameras', []) or []
            for c in cams:
                name = str(c.get('Name', '')).strip() or 'Camera'
                purpose = str(c.get('Purpose', '')).strip()
                it = QtWidgets.QTreeWidgetItem(self.group_cameras, [name, '', '', purpose])
                self.group_cameras.addChild(it)
                self._camera_items[name] = it

            # Spectrometers: use filename token as name; description fixed to Vis/XUV
            specs = getattr(device_tabs, '_spectrometers', []) or []
            for idx, s in enumerate(specs):
                filename = str(s.get('filename', '')).strip() or f'Spec{idx}'
                label = 'Vis. Spectrometer' if idx == 0 else 'XUV spectrometer' if idx == 1 else 'Spectrometer'
                it = QtWidgets.QTreeWidgetItem(self.group_specs, [filename, '', '', label])
                self.group_specs.addChild(it)
                self._spec_items[filename] = it

            # expand groups
            self.tree.expandItem(self.group_stages)
            self.tree.expandItem(self.group_cameras)
            self.tree.expandItem(self.group_specs)
        except Exception:
            pass

    # ---------- stage updates ----------
    def on_zaber_discovered(self, devices: list):
        """Mark PWR ON for discovered addresses, OFF otherwise."""
        try:
            found = set()
            for d in devices or []:
                try:
                    a = int(d.get('address'))
                    found.add(a)
                except Exception:
                    continue
            # update each known stage
            for addr, item in list(self._stage_items.items()):
                if addr in found:
                    self._set_cell(item, 1, 'ON', '#27a227')
                else:
                    self._set_cell(item, 1, 'OFF', '#d12b2b')
        except Exception:
            pass

    def on_stage_moving(self, address: int, is_moving: bool):
        try:
            addr = int(address)
            item = self._stage_items.get(addr)
            # fallback: if no direct match, try by enumerated index (1-based)
            if item is None:
                try:
                    if 1 <= int(addr) <= len(self._stage_items):
                        item = list(self._stage_items.values())[int(addr) - 1]
                except Exception:
                    item = None
            if is_moving:
                # set moving indicator (yellow); wait for moved signal to mark OK
                if item is not None:
                    self._set_cell(item, 2, 'MOV', '#e6a400')
            else:
                # when not moving, do not assume failure — on_stage_moved will set OK when move completes
                # leave the current STS until moved event arrives
                pass
        except Exception:
            pass

    def on_stage_moved(self, address: int, final_pos: float = None):
        try:
            addr = int(address)
            item = self._stage_items.get(addr)
            # fallback: if no direct match, try by enumerated index (1-based)
            if item is None:
                try:
                    if 1 <= int(addr) <= len(self._stage_items):
                        item = list(self._stage_items.values())[int(addr) - 1]
                except Exception:
                    item = None
            if item is not None:
                self._set_cell(item, 2, 'OK', '#27a227')
            else:
                # If we couldn't find an item, write a debug line to the global status panel if available
                try:
                    win = self.window()
                    if win is not None and hasattr(win, 'status_panel') and getattr(win, 'status_panel') is not None:
                        try:
                            win.status_panel.append_line(f"DeviceStatusPanel: moved event for Addr {addr} but no matching UI row found")
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    def on_stage_homed(self, address: int):
        """Called when a homing operation completes for an address — treat as OK."""
        try:
            addr = int(address)
            item = self._stage_items.get(addr)
            if item is None:
                try:
                    if 1 <= int(addr) <= len(self._stage_items):
                        item = list(self._stage_items.values())[int(addr) - 1]
                except Exception:
                    item = None
            if item is not None:
                self._set_cell(item, 2, 'OK', '#27a227')
        except Exception:
            pass

    # ---------- cameras / spectrometers updates ----------
    def on_fire_started(self):
        """Called when Fire is clicked: mark camera/spec STS as checking (yellow) until rename completes."""
        try:
            for it in self._camera_items.values():
                self._set_cell(it, 2, 'CHK', '#e6a400')
            for it in self._spec_items.values():
                self._set_cell(it, 2, 'CHK', '#e6a400')
        except Exception:
            pass

    def update_camera_spec_status(self, renamed_map: dict):
        """renamed_map: mapping token -> newpath for files renamed. Tokens are camera names and spec filenames."""
        try:
            # Cameras
            for name, it in self._camera_items.items():
                if name and name in (renamed_map or {}):
                    self._set_cell(it, 2, 'OK', '#27a227')
                else:
                    self._set_cell(it, 2, 'F', '#d12b2b')
            # Spectrometers
            for fname, it in self._spec_items.items():
                if fname and fname in (renamed_map or {}):
                    self._set_cell(it, 2, 'OK', '#27a227')
                else:
                    self._set_cell(it, 2, 'F', '#d12b2b')
        except Exception:
            pass

    # ---------- helpers ----------
    def _set_cell(self, item: QtWidgets.QTreeWidgetItem, col: int, text: str, bgcolor: str = None):
        try:
            item.setText(col, str(text))
            if bgcolor:
                brush = QtGui.QBrush(QtGui.QColor(bgcolor))
                item.setBackground(col, brush)
                # ensure foreground is readable
                item.setForeground(col, QtGui.QBrush(QtGui.QColor('#ffffff' if bgcolor != '#e6a400' else '#000000')))
            else:
                item.setBackground(col, QtGui.QBrush())
                item.setForeground(col, QtGui.QBrush())
        except Exception:
            pass

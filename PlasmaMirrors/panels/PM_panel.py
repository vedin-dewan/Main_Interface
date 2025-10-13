from PyQt6 import QtCore, QtWidgets
from widgets.motor_row import MotorRow
from widgets.round_light import RoundLight
import json
import os
from typing import Callable, Optional

class ToggleBypassButton(QtWidgets.QPushButton):
    """Right-bottom BYPASS/ENGAGE toggle button."""
    def __init__(self, parent=None):
        super().__init__("BYPASS", parent)
        self.setCheckable(True)
        self._apply_style(False)
        self.toggled.connect(self._apply_style)
        self.setFixedHeight(26)

    def _apply_style(self, engaged: bool):
        if engaged:
            # ENGAGE = red
            self.setText("ENGAGE")
            self.setStyleSheet(
                "background:#7a2f2e; color:#fff; border:1px solid #a24946; font-weight:700; border-radius:6px;"
            )
        else:
            # BYPASS = green
            self.setText("BYPASS")
            self.setStyleSheet(
                "background:#2f7a4a; color:#fff; border:1px solid #4ea36b; font-weight:700; border-radius:6px;"
            )

class PMStageRow(QtWidgets.QWidget):
    """One row: RX / Y / Z / SD with Min, Max, Zero Pos, MO Pos, Current, Direction.
       Direction dropdown is optional (for RX and Y only in your layout)."""
    def __init__(self, label: str, parent=None, direction_enabled: bool = True):
        super().__init__(parent)
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0,0,0,0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        # Left stage label
        lab = QtWidgets.QLabel(label)
        lab.setMinimumWidth(18)
        grid.addWidget(lab, 0, 0)
        # Stage number (small int)
        self.stage_num = QtWidgets.QSpinBox(); self.stage_num.setRange(0, 999); self.stage_num.setFixedWidth(40)
        grid.addWidget(self.stage_num, 0, 1)
        # Min/Max
        self.min = QtWidgets.QDoubleSpinBox(); self.min.setDecimals(3); self.min.setRange(-9999, 9999); self.min.setFixedWidth(70)
        self.max = QtWidgets.QDoubleSpinBox(); self.max.setDecimals(3); self.max.setRange(-9999, 9999); self.max.setFixedWidth(70)
        grid.addWidget(self.min, 0, 2); grid.addWidget(self.max, 0, 3)
        # Zero Pos / MO Pos / Current (read-only labels)
        self.zero_label = QtWidgets.QLabel("0.000")
        self.zero_label.setFixedWidth(70)
        self.zero_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.zero_label.setStyleSheet("background:#2a2a2a; padding:2px; border-radius:4px;")

        self.mo_label = QtWidgets.QLabel("0.000")
        self.mo_label.setFixedWidth(70)
        self.mo_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.mo_label.setStyleSheet("background:#2a2a2a; padding:2px; border-radius:4px;")

        self.cur_label = QtWidgets.QLabel("0.000")
        self.cur_label.setFixedWidth(70)
        self.cur_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.cur_label.setStyleSheet("background:#2a2a2a; padding:2px; border-radius:4px;")

        grid.addWidget(self.zero_label, 0, 4); grid.addWidget(self.mo_label, 0, 5); grid.addWidget(self.cur_label, 0, 6)

        # Direction (only if enabled)
        if direction_enabled:
            self.dir = QtWidgets.QComboBox(); self.dir.addItems(["Pos", "Neg"]); self.dir.setFixedWidth(70)
            grid.addWidget(self.dir, 0, 7)
        else:
            self.dir = None
            spacer = QtWidgets.QLabel("")
            spacer.setFixedWidth(70)
            grid.addWidget(spacer, 0, 7)

    # helpers for label-backed fields
    def set_zero(self, value: float):
        try:
            self.zero_label.setText(f"{float(value):.3f}")
        except Exception:
            self.zero_label.setText("0.000")

    def get_zero(self) -> float:
        try:
            return float(self.zero_label.text())
        except Exception:
            return 0.0

    def set_mo(self, value: float):
        try:
            self.mo_label.setText(f"{float(value):.3f}")
        except Exception:
            self.mo_label.setText("0.000")

    def get_mo(self) -> float:
        try:
            return float(self.mo_label.text())
        except Exception:
            return 0.0

    def set_current(self, value: float):
        try:
            self.cur_label.setText(f"{float(value):.3f}")
        except Exception:
            self.cur_label.setText("0.000")

    def get_current(self) -> float:
        try:
            return float(self.cur_label.text())
        except Exception:
            return 0.0

class PMMirrorGroup(QtWidgets.QGroupBox):
    def __init__(self, title: str, parent=None):
        super().__init__("", parent)
        self.setStyleSheet("QGroupBox{font-weight:700;}")
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                           QtWidgets.QSizePolicy.Policy.Preferred)
        self.setFixedWidth(580)

        # --- Top header: labels row + widgets row (to match screenshot) ---
        top = QtWidgets.QGridLayout()
        top.setHorizontalSpacing(8)
        top.setVerticalSpacing(2)
        # Row 0: header labels
        headers = ["On", "Name", "Act.", "Auto", "Dist. (mm)", "Target Type"]
        for col, text in enumerate(headers):
            lab = QtWidgets.QLabel(text)
            lab.setStyleSheet("color:#cfcfcf;")
            top.addWidget(lab, 0, col)
        # Row 1: actual controls aligned under labels
        self.on_light = RoundLight(14, "#22cc66", "#2b2b2b"); self.on_light.set_on(True)
        top.addWidget(self.on_light, 1, 0)
        self.name = QtWidgets.QLineEdit(title); self.name.setFixedWidth(180)
        top.addWidget(self.name, 1, 1)
        self.act_light = RoundLight(14, "#22cc66", "#2b2b2b")
        top.addWidget(self.act_light, 1, 2)
        self.auto = QtWidgets.QCheckBox(); self.auto.setChecked(True)
        top.addWidget(self.auto, 1, 3)
        self.dist = QtWidgets.QDoubleSpinBox(); self.dist.setDecimals(3); self.dist.setRange(0, 9999); self.dist.setValue(0.5); self.dist.setFixedWidth(80)
        top.addWidget(self.dist, 1, 4)
        self.target_type = QtWidgets.QComboBox(); self.target_type.addItems(["Circular", "Rectangular"]); self.target_type.setFixedWidth(110)
        top.addWidget(self.target_type, 1, 5)

        # --- Stage table header ---
        hdr = QtWidgets.QGridLayout()
        hdr.setHorizontalSpacing(6)
        header_labels = ["Stage", "Min", "Max", "Zero Pos", "MO Pos", "Current", "Direction"]
        hdr.addWidget(QtWidgets.QLabel(""), 0, 0)  # empty for RX/Y/Z/SD label col
        # target fixed widths (match widget widths in PMStageRow)
        col_widths = {1: 40, 2: 70, 3: 70, 4: 70, 5: 70, 6: 70, 7: 70}
        for i, t in enumerate(header_labels, start=1):
            lab = QtWidgets.QLabel(t)
            lab.setStyleSheet("color:#cfcfcf;")
            # apply width hint if available so header aligns with columns
            w = col_widths.get(i)
            if w is not None:
                lab.setFixedWidth(w)
                lab.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            hdr.addWidget(lab, 0, i)

        # --- Four rows (Direction only for RX & Y) ---
        self.row_rx = PMStageRow("RX", direction_enabled=True)
        self.row_y  = PMStageRow("Y",  direction_enabled=True)
        self.row_z  = PMStageRow("Z",  direction_enabled=False)
        self.row_sd = PMStageRow("SD", direction_enabled=False)

        # --- Bottom info strip: plain text (no buttons) + BYPASS/ENGAGE toggle ---
        bottom = QtWidgets.QHBoxLayout()
        lab_off = QtWidgets.QLabel("SD Off")
        lab_on  = QtWidgets.QLabel("SD On")
        lab_off.setStyleSheet("color:#cfcfcf;")
        lab_on.setStyleSheet("color:#cfcfcf;")
        bottom.addWidget(lab_off)
        bottom.addSpacing(16)
        bottom.addWidget(lab_on)
        bottom.addStretch(1)
        self.bypass = ToggleBypassButton()
        bottom.addWidget(self.bypass)

        # Compose panel
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(8,8,8,8)
        v.setSpacing(2)
        v.addLayout(top)
        v.addLayout(hdr)
        v.addWidget(self.row_rx)
        v.addWidget(self.row_y)
        v.addWidget(self.row_z)
        v.addWidget(self.row_sd)
        v.addLayout(bottom)

class PMPanel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.pm1 = PMMirrorGroup("Plasma Mirror 1")
        self.pm2 = PMMirrorGroup("Plasma Mirror 2")
        self.pm3 = PMMirrorGroup("Plasma Mirror 3")

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(8,8,8,8)
        v.setSpacing(2)
        v.addWidget(self.pm1)
        v.addWidget(self.pm2)
        v.addWidget(self.pm3)
        v.addStretch(1)

        # Match app style
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(520)
        self.setMaximumWidth(700)
        # saved positions file path (parameters/Saved_positions.json)
        self._saved_values_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'parameters', 'Saved_positions.json'))
        self._watcher = QtCore.QFileSystemWatcher(self)
        try:
            # watch file or directory so creation/deletion is detected
            if os.path.exists(self._saved_values_path):
                self._watcher.addPath(self._saved_values_path)
            else:
                self._watcher.addPath(os.path.dirname(self._saved_values_path))
            self._watcher.fileChanged.connect(self._on_saved_values_changed)
            self._watcher.directoryChanged.connect(self._on_saved_values_changed)
        except Exception:
            pass
        # small delay to allow UI init, then load
        QtCore.QTimer.singleShot(100, self._load_saved_values)

    def _on_saved_values_changed(self, path: str) -> None:
        # Debounce multiple events
        QtCore.QTimer.singleShot(50, self._load_saved_values)

    def _load_saved_values(self) -> None:
        """Load zero / MO values from parameters/Saved_positions.json.
        Supported formats:
        1) Direct mapping:
           { "Zero PM1": {"RX":1.23, "Y":2.34, ...}, "Microscope PM1": {...} }
        2) Preset-with-stages (current Saved_positions.json style):
           { "Preset Name": { "stages": [ {"name":"PM1R","position":...}, ... ] }, ... }

        The loader will look for keys named 'Zero PMn' and 'Microscope PMn'.
        When a preset provides a 'stages' list, stage names like 'PM1R','PM1Y','PM1Z','PM1D'
        are mapped to labels RX, Y, Z, SD respectively (best-effort suffix mapping).
        """
        try:
            if not os.path.exists(self._saved_values_path):
                return
            with open(self._saved_values_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return

        def apply_direct_map(mg, mapping_source):
            # mapping_source expected to be a dict mapping labels to numeric values
            mapping = {'RX': mg.row_rx, 'Y': mg.row_y, 'Z': mg.row_z, 'SD': mg.row_sd}
            if not isinstance(mapping_source, dict):
                return
            for label, row in mapping.items():
                try:
                    if label in mapping_source:
                        row.set_zero(float(mapping_source[label]))
                except Exception:
                    pass

        def apply_preset_stages(mg, preset_obj):
            # preset_obj expected to be dict with 'stages' list of {name, position}
            if not isinstance(preset_obj, dict):
                return
            stages = preset_obj.get('stages', [])
            if not isinstance(stages, list):
                return
            # walk stages and map names to RX/Y/Z/SD via suffix heuristic
            for st in stages:
                try:
                    name = str(st.get('name', ''))
                    pos = st.get('position', None)
                    if pos is None:
                        continue
                    # normalize
                    nm = name.upper()
                    # heuristics: look for trailing character
                    if nm.startswith('PM') and len(nm) >= 4:
                        suffix = nm[3:]
                    else:
                        suffix = nm[-1:]
                    # choose mapping
                    if suffix.startswith('R'):
                        mg.row_rx.set_zero(float(pos))
                    elif 'Y' in suffix:
                        mg.row_y.set_zero(float(pos))
                    elif 'Z' in suffix:
                        mg.row_z.set_zero(float(pos))
                    elif 'D' in suffix or 'S' in suffix:
                        # treat D or S as SD/redirect
                        mg.row_sd.set_zero(float(pos))
                except Exception:
                    pass

        # Now try to apply keys for PM1/PM2/PM3
        try:
            for idx in range(3):
                mg = [self.pm1, self.pm2, self.pm3][idx]
                zero_key = f'Zero PM{idx+1}'
                mo_key = f'Microscope PM{idx+1}'

                # direct label mapping
                zero_val = data.get(zero_key)
                if zero_val is not None:
                    apply_direct_map(mg, zero_val)
                else:
                    # search for preset with this name and stages list
                    preset = data.get(zero_key)
                    if preset is not None and isinstance(preset, dict) and 'stages' in preset:
                        apply_preset_stages(mg, preset)
                    else:
                        # fallback: scan top-level presets for one whose stages mention PM{n}
                        for key, val in data.items():
                            if not isinstance(val, dict):
                                continue
                            stages = val.get('stages')
                            if not isinstance(stages, list):
                                continue
                            # if any stage name contains 'PM{n}', use this preset
                            if any(isinstance(s, dict) and isinstance(s.get('name'), str) and f'PM{idx+1}' in s.get('name', '') for s in stages):
                                apply_preset_stages(mg, val)
                                break

                # MO values
                mo_val = data.get(mo_key)
                if mo_val is not None:
                    # direct mapping
                    if isinstance(mo_val, dict):
                        for label, row in {'RX': mg.row_rx, 'Y': mg.row_y, 'Z': mg.row_z, 'SD': mg.row_sd}.items():
                            try:
                                if label in mo_val:
                                    row.set_mo(float(mo_val[label]))
                            except Exception:
                                pass
                    # preset form
                    elif isinstance(mo_val, dict) and 'stages' in mo_val:
                        # treat similar to preset
                        apply_preset_stages(mg, mo_val)
                else:
                    # fallback search
                    for key, val in data.items():
                        if not isinstance(val, dict):
                            continue
                        stages = val.get('stages')
                        if not isinstance(stages, list):
                            continue
                        if any(isinstance(s, dict) and isinstance(s.get('name'), str) and f'PM{idx+1}' in s.get('name', '') for s in stages):
                            # try to find microscope-prefixed keys
                            # we'll reuse apply_preset_stages to pull positions into MO fields
                            apply_preset_stages(mg, val)
                            break
        except Exception:
            pass

    def update_current_by_address(self, address: int, value: float) -> None:
        """Update the Current label for the row corresponding to a Zaber stage address.
        The mapping uses the stage_num configured in each PM mirror group rows.
        """
        try:
            # search across pm1/pm2/pm3 rows
            for mg in (self.pm1, self.pm2, self.pm3):
                for r in (mg.row_rx, mg.row_y, mg.row_z, mg.row_sd):
                    try:
                        if int(r.stage_num.value()) == int(address):
                            r.set_current(float(value))
                            return
                    except Exception:
                        continue
        except Exception:
            return

    # --- Persistence helpers -------------------------------------------------
    def _mirror_group_to_dict(self, mg: 'PMMirrorGroup') -> dict:
        """Serialize one PMMirrorGroup to a plain dict."""
        def row_to_dict(r: 'PMStageRow'):
            return {
                'stage_num': r.stage_num.value(),
                'min': r.min.value(),
                'max': r.max.value(),
                'zero': r.get_zero(),
                'mo': r.get_mo(),
                'cur': r.get_current(),
                'dir': (r.dir.currentIndex() if getattr(r, 'dir', None) is not None else None)
            }

        return {
            'name': mg.name.text(),
            'auto': bool(mg.auto.isChecked()),
            'dist': mg.dist.value(),
            'target_type': mg.target_type.currentIndex(),
            'bypass': bool(mg.bypass.isChecked()),
            'rows': {
                'rx': row_to_dict(mg.row_rx),
                'y': row_to_dict(mg.row_y),
                'z': row_to_dict(mg.row_z),
                'sd': row_to_dict(mg.row_sd),
            }
        }

    def _dict_to_mirror_group(self, mg: 'PMMirrorGroup', data: dict) -> None:
        """Apply a previously-saved dict to a PMMirrorGroup instance."""
        try:
            mg.name.setText(str(data.get('name', mg.name.text())))
            mg.auto.setChecked(bool(data.get('auto', mg.auto.isChecked())))
            mg.dist.setValue(float(data.get('dist', mg.dist.value())))
            mg.target_type.setCurrentIndex(int(data.get('target_type', mg.target_type.currentIndex())))
            mg.bypass.setChecked(bool(data.get('bypass', mg.bypass.isChecked())))

            rows = data.get('rows', {}) or {}
            def apply_row(r: 'PMStageRow', d: dict):
                if not isinstance(d, dict):
                    return
                try: r.stage_num.setValue(int(d.get('stage_num', r.stage_num.value())))
                except Exception: pass
                try: r.min.setValue(float(d.get('min', r.min.value())))
                except Exception: pass
                try: r.max.setValue(float(d.get('max', r.max.value())))
                except Exception: pass
                try: r.set_zero(float(d.get('zero', r.get_zero())))
                except Exception: pass
                try: r.set_mo(float(d.get('mo', r.get_mo())))
                except Exception: pass
                try: r.set_current(float(d.get('cur', r.get_current())))
                except Exception: pass
                if getattr(r, 'dir', None) is not None:
                    idx = d.get('dir', None)
                    if isinstance(idx, int):
                        try: r.dir.setCurrentIndex(idx)
                        except Exception: pass

            apply_row(mg.row_rx, rows.get('rx', {}))
            apply_row(mg.row_y,  rows.get('y',  {}))
            apply_row(mg.row_z,  rows.get('z',  {}))
            apply_row(mg.row_sd, rows.get('sd', {}))
        except Exception:
            # be defensive: don't let corrupted settings break the UI
            return

    def get_state(self) -> dict:
        """Return the full PM panel state as a JSON-serializable dict."""
        return {
            'pm1': self._mirror_group_to_dict(self.pm1),
            'pm2': self._mirror_group_to_dict(self.pm2),
            'pm3': self._mirror_group_to_dict(self.pm3),
            'saved_time': QtCore.QDateTime.currentDateTime().toString(QtCore.Qt.DateFormat.ISODate)
        }

    def set_state(self, data: dict) -> None:
        """Apply a state dict to the UI. Silently ignores missing/invalid fields."""
        if not isinstance(data, dict):
            return
        self._dict_to_mirror_group(self.pm1, data.get('pm1', {}))
        self._dict_to_mirror_group(self.pm2, data.get('pm2', {}))
        self._dict_to_mirror_group(self.pm3, data.get('pm3', {}))

    def save_to_file(self, filename: str, logger: Optional[Callable] = None) -> None:
        try:
            d = self.get_state()
            folder = os.path.dirname(filename)
            if folder and not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(d, f, indent=2)
            if logger:
                try: logger(f"PM settings saved → {filename}")
                except Exception: pass
        except Exception as e:
            if logger:
                try: logger(f"PM settings save failed: {e}")
                except Exception: pass

    def load_from_file(self, filename: str, logger: Optional[Callable] = None) -> None:
        try:
            if not os.path.exists(filename):
                if logger:
                    try: logger(f"PM settings not found (will use defaults): {filename}")
                    except Exception: pass
                return
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.set_state(data)
            if logger:
                try: logger(f"PM settings loaded ← {filename}")
                except Exception: pass
        except Exception as e:
            if logger:
                try: logger(f"PM settings load failed: {e}")
                except Exception: pass
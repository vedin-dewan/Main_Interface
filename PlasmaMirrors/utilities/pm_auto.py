import math
from typing import List, Dict, Callable, Any


class PMAutoManager:
    """Compute PM Auto move descriptors from a PMPanel and part1 rows.

    This class does not emit moves. It computes and validates move descriptors
    which the caller (MainWindow) can emit via the req_jog signal and track
    pending addresses.
    """
    def __init__(self, pm_panel: Any, part1_rows: List[Any], logger: Callable = None):
        self.pm_panel = pm_panel
        self.part1_rows = part1_rows
        self.logger = logger or (lambda *a, **k: None)

    def _log(self, *args, **kwargs):
        try:
            self.logger(" ".join(str(a) for a in args))
        except Exception:
            try:
                # fall back if logger expects a single string
                self.logger(args[0] if args else "")
            except Exception:
                pass

    def generate_moves(self) -> List[Dict[str, Any]]:
        """Return a list of move descriptors.

        Each descriptor is a dict: {
            'address': int,
            'delta': float,
            'unit': str,
            'log': str
        }
        """
        moves: List[Dict[str, Any]] = []
        if not hasattr(self, 'pm_panel') or self.pm_panel is None:
            return moves

        for mg in (self.pm_panel.pm1, self.pm_panel.pm2, self.pm_panel.pm3):
            try:
                if not getattr(mg, 'auto', None) or not mg.auto.isChecked():
                    # try:
                    #     self._log(f"PM Auto: group {getattr(mg,'name',None).text() if getattr(mg,'name',None) else 'unknown'} auto unchecked; skipping")
                    # except Exception:
                    #     pass
                    continue

                target_type = str(mg.target_type.currentText()).strip().lower() if getattr(mg, 'target_type', None) is not None else 'rectangular'
                dist = float(mg.dist.value())

                # read current Y from part1 rows if available, otherwise fallback to UI current
                current_y = None
                try:
                    y_addr = int(mg.row_y.stage_num.value())
                    if y_addr > 0 and hasattr(self, 'part1_rows') and len(self.part1_rows) >= y_addr:
                        try:
                            current_y = float(self.part1_rows[y_addr - 1].info.eng_value)
                        except Exception:
                            current_y = None
                except Exception:
                    current_y = None
                if current_y is None:
                    try:
                        current_y = float(mg.row_y.get_current())
                    except Exception:
                        current_y = 0.0

                def _toggle_dir_widget(dir_widget):
                    """Safely toggle a direction widget between Pos and Neg.

                    Supports QComboBox-like widgets (setCurrentText / setCurrentIndex)
                    and falls back to no-op if unsupported.
                    Returns the new direction text (e.g. 'Pos' or 'Neg').
                    """
                    try:
                        cur = str(dir_widget.currentText()).strip()
                    except Exception:
                        try:
                            # maybe it's a QRadioButton group? try text attr
                            cur = str(dir_widget.text()).strip()
                        except Exception:
                            return None
                    new = 'Neg' if cur.lower().startswith('p') else 'Pos'
                    try:
                        if hasattr(dir_widget, 'setCurrentText'):
                            dir_widget.setCurrentText(new)
                        elif hasattr(dir_widget, 'setCurrentIndex') and hasattr(dir_widget, 'count'):
                            # flip between 0 and 1 if possible
                            try:
                                idx = dir_widget.currentIndex()
                                count = dir_widget.count()
                                if count >= 2:
                                    dir_widget.setCurrentIndex(1 - idx)
                                else:
                                    # fallback: try setting text via findText
                                    t_idx = dir_widget.findText(new)
                                    if t_idx >= 0:
                                        dir_widget.setCurrentIndex(t_idx)
                            except Exception:
                                pass
                        else:
                            # try to set text attribute if available
                            if hasattr(dir_widget, 'setText'):
                                try:
                                    dir_widget.setText(new)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    return new

                if target_type.startswith('c'):
                    # Circular: compute r using Zero Pos if present, otherwise fallback
                    try:
                        zero_pos = float(mg.row_y.get_zero())
                    except Exception:
                        zero_pos = None

                    if zero_pos is None:
                        try:
                            y_max = float(mg.row_y.max.value())
                        except Exception:
                            y_max = 0.0
                        r = (y_max - float(current_y) + 4.25)
                        self._log(f"PM Auto (Circular): Zero Pos missing, falling back to (Y.max - current_y + 4.25) => r={r:.3f}")
                    else:
                        r = (float(zero_pos) - float(current_y))

                    if abs(r) < 1e-4:
                        self._log(f"PM Auto: computed r is zero for Circular target (zero_pos={zero_pos}, current={current_y}); skipping")
                        continue

                    delta_angle = (180.0 * dist) / (math.pi * r)
                    rx_addr = 0
                    try:
                        rx_addr = int(mg.row_rx.stage_num.value())
                    except Exception:
                        rx_addr = 0
                    if rx_addr <= 0:
                        self._log(f"PM Auto: group has invalid RX stage_num {rx_addr}; skipping Circular auto")
                        continue
                    # use RX dir for sign
                    rx_dir = str(mg.row_rx.dir.currentText()) if getattr(mg.row_rx, 'dir', None) is not None else 'Pos'
                    delta = delta_angle if rx_dir.lower().startswith('p') else -abs(delta_angle)
                    unit = 'deg'
                    try:
                        unit = getattr(self.part1_rows[rx_addr - 1].info, 'unit', unit)
                    except Exception:
                        pass
                    # Before emitting RX move, ensure it won't push RX out of its bounds.
                    # Read current RX position and its min/max.
                    try:
                        rx_pos = None
                        if rx_addr > 0 and hasattr(self, 'part1_rows') and len(self.part1_rows) >= rx_addr:
                            try:
                                rx_pos = float(self.part1_rows[rx_addr - 1].info.eng_value)
                            except Exception:
                                rx_pos = None
                        if rx_pos is None:
                            try:
                                rx_pos = float(mg.row_rx.get_current())
                            except Exception:
                                rx_pos = None
                    except Exception:
                        rx_pos = None

                    rx_min = rx_max = None
                    try:
                        rx_min = float(mg.row_rx.min.value())
                    except Exception:
                        rx_min = None
                    try:
                        rx_max = float(mg.row_rx.max.value())
                    except Exception:
                        rx_max = None

                    intended_rx = None if rx_pos is None else (rx_pos + delta)
                    out_of_bounds_rx = False
                    tol = 1e-4
                    if intended_rx is not None:
                        if rx_min is not None and intended_rx < rx_min - tol:
                            out_of_bounds_rx = True
                        if rx_max is not None and intended_rx > rx_max + tol:
                            out_of_bounds_rx = True

                    if out_of_bounds_rx:
                        # Swap: move Y by +/-dist (mm) instead, and reverse RX direction
                        # determine Y address
                        try:
                            y_addr = int(mg.row_y.stage_num.value())
                        except Exception:
                            y_addr = 0
                        if y_addr <= 0:
                            self._log(f"PM Auto (Circular): RX out-of-bounds but Y stage invalid for swap; skipping")
                            continue
                        # Use Y.dir for sign
                        y_dir = str(mg.row_y.dir.currentText()) if getattr(mg.row_y, 'dir', None) is not None else 'Pos'
                        y_delta = dist if y_dir.lower().startswith('p') else -abs(dist)
                        unit_y = 'mm'
                        try:
                            unit_y = getattr(self.part1_rows[y_addr - 1].info, 'unit', unit_y)
                        except Exception:
                            pass
                        log = (f"PM Auto (Circular swap): RX intended {intended_rx:.6f} {unit} out-of-bounds; "
                               f"moving Y stage {y_addr} by {y_delta:.6f} {unit_y} instead and reversing RX direction")
                        # reverse RX direction in the UI
                        try:
                            _toggle_dir_widget(mg.row_rx.dir)
                        except Exception:
                            pass
                        moves.append({'address': y_addr, 'delta': float(y_delta), 'unit': unit_y, 'log': log})
                    else:
                        log = f"PM Auto (Circular): moving RX stage {rx_addr} by {delta:.6f} {unit} (r={r:.3f}, zero_pos={zero_pos}, current_y={current_y:.3f}, dist={dist:.3f})"
                        moves.append({'address': rx_addr, 'delta': float(delta), 'unit': unit, 'log': log})
                else:
                    # Linear/Rectangular: move Y by dist using Y.dir
                    try:
                        y_addr = int(mg.row_y.stage_num.value())
                    except Exception:
                        y_addr = 0
                    if y_addr <= 0:
                        self._log(f"PM Auto: group has invalid Y stage_num {y_addr}; skipping")
                        continue
                    dir_choice = str(mg.row_y.dir.currentText()) if getattr(mg.row_y, 'dir', None) is not None else 'Pos'
                    y_delta = dist if dir_choice.lower().startswith('p') else -abs(dist)
                    unit = 'mm'
                    try:
                        unit = getattr(self.part1_rows[y_addr - 1].info, 'unit', unit)
                    except Exception:
                        pass

                    # Check whether the intended Y move would violate Y bounds. If so,
                    # swap to moving RX by +/-dist (mm) and reverse Y direction.
                    try:
                        y_pos = None
                        if y_addr > 0 and hasattr(self, 'part1_rows') and len(self.part1_rows) >= y_addr:
                            try:
                                y_pos = float(self.part1_rows[y_addr - 1].info.eng_value)
                            except Exception:
                                y_pos = None
                        if y_pos is None:
                            try:
                                y_pos = float(mg.row_y.get_current())
                            except Exception:
                                y_pos = None
                    except Exception:
                        y_pos = None

                    y_min = y_max = None
                    try:
                        y_min = float(mg.row_y.min.value())
                    except Exception:
                        y_min = None
                    try:
                        y_max = float(mg.row_y.max.value())
                    except Exception:
                        y_max = None

                    intended_y = None if y_pos is None else (y_pos + y_delta)
                    out_of_bounds_y = False
                    tol = 1e-4
                    if intended_y is not None:
                        if y_min is not None and intended_y < y_min - tol:
                            out_of_bounds_y = True
                        if y_max is not None and intended_y > y_max + tol:
                            out_of_bounds_y = True

                    if out_of_bounds_y:
                        # Swap: move RX by +/-dist (mm) instead, and reverse Y direction
                        try:
                            rx_addr = int(mg.row_rx.stage_num.value())
                        except Exception:
                            rx_addr = 0
                        if rx_addr <= 0:
                            self._log(f"PM Auto (Linear): Y out-of-bounds but RX stage invalid for swap; skipping")
                            continue
                        rx_dir = str(mg.row_rx.dir.currentText()) if getattr(mg.row_rx, 'dir', None) is not None else 'Pos'
                        rx_delta = dist if rx_dir.lower().startswith('p') else -abs(dist)
                        unit_rx = 'mm'
                        try:
                            unit_rx = getattr(self.part1_rows[rx_addr - 1].info, 'unit', unit_rx)
                        except Exception:
                            pass
                        log = (f"PM Auto (Linear swap): Y intended {intended_y:.6f} {unit} out-of-bounds; "
                               f"moving RX stage {rx_addr} by {rx_delta:.6f} {unit_rx} instead and reversing Y direction")
                        # reverse Y direction in the UI
                        try:
                            _toggle_dir_widget(mg.row_y.dir)
                        except Exception:
                            pass
                        moves.append({'address': rx_addr, 'delta': float(rx_delta), 'unit': unit_rx, 'log': log})
                    else:
                        #log = f"PM Auto: moving stage {y_addr} by {y_delta:.6f} {unit}"
                        moves.append({'address': y_addr, 'delta': float(y_delta), 'unit': unit, 'log': log})
            except Exception:
                continue

        return moves

    def check_bounds(self) -> List[Dict[str, Any]]:
        """Check stages for PM groups with Auto checked.

                Returns a list of violation dicts with keys:
                    - pm_name
                    - row_label (RX/Y/Z)
                    - address
                    - position
                    - min
                    - max
                    - relation ('below' or 'above')
        """
        violations: List[Dict[str, Any]] = []
        if not hasattr(self, 'pm_panel') or self.pm_panel is None:
            return violations

        for mg in (self.pm_panel.pm1, self.pm_panel.pm2, self.pm_panel.pm3):
            try:
                if not getattr(mg, 'auto', None) or not mg.auto.isChecked():
                    continue
                pm_name = getattr(mg, 'name', None).text() if getattr(mg, 'name', None) else 'PM'
                # Only check the primary motion axes for PM auto: RX, Y and Z.
                # Do not treat SD as a blocking axis for auto moves.
                for row_label, row in (('RX', mg.row_rx), ('Y', mg.row_y), ('Z', mg.row_z)):
                    try:
                        addr = int(row.stage_num.value())
                    except Exception:
                        addr = 0
                    if addr <= 0:
                        continue
                    # read current position preferred from part1 rows
                    pos = None
                    try:
                        if addr > 0 and hasattr(self, 'part1_rows') and len(self.part1_rows) >= addr:
                            pos = float(self.part1_rows[addr - 1].info.eng_value)
                    except Exception:
                        pos = None
                    if pos is None:
                        try:
                            pos = float(row.get_current())
                        except Exception:
                            pos = None
                    if pos is None:
                        continue
                    try:
                        min_v = float(row.min.value())
                    except Exception:
                        min_v = None
                    try:
                        max_v = float(row.max.value())
                    except Exception:
                        max_v = None
                    tol = 1e-4
                    if min_v is not None and pos < min_v - tol:
                        violations.append({'pm_name': pm_name, 'row_label': row_label, 'address': addr, 'position': pos, 'min': min_v, 'max': max_v, 'relation': 'below'})
                    elif max_v is not None and pos > max_v + tol:
                        violations.append({'pm_name': pm_name, 'row_label': row_label, 'address': addr, 'position': pos, 'min': min_v, 'max': max_v, 'relation': 'above'})
            except Exception:
                continue
        return violations

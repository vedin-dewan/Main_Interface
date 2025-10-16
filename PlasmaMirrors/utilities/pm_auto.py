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
                    try:
                        self._log(f"PM Auto: group {getattr(mg,'name',None).text() if getattr(mg,'name',None) else 'unknown'} auto unchecked; skipping")
                    except Exception:
                        pass
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

                    if abs(r) < 1e-6:
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
                    delta = dist if dir_choice.lower().startswith('p') else -abs(dist)
                    unit = 'mm'
                    try:
                        unit = getattr(self.part1_rows[y_addr - 1].info, 'unit', unit)
                    except Exception:
                        pass
                    log = f"PM Auto: moving stage {y_addr} by {delta:.6f} {unit}"
                    moves.append({'address': y_addr, 'delta': float(delta), 'unit': unit, 'log': log})
            except Exception:
                continue

        return moves

    def check_bounds(self) -> List[Dict[str, Any]]:
        """Check stages for PM groups with Auto checked.

        Returns a list of violation dicts with keys:
          - pm_name
          - row_label (RX/Y/Z/SD)
          - address
          - position
          - min
          - max
          - relation ('below' or 'above_or_equal')
        """
        violations: List[Dict[str, Any]] = []
        if not hasattr(self, 'pm_panel') or self.pm_panel is None:
            return violations

        for mg in (self.pm_panel.pm1, self.pm_panel.pm2, self.pm_panel.pm3):
            try:
                if not getattr(mg, 'auto', None) or not mg.auto.isChecked():
                    continue
                pm_name = getattr(mg, 'name', None).text() if getattr(mg, 'name', None) else 'PM'
                for row_label, row in (('RX', mg.row_rx), ('Y', mg.row_y), ('Z', mg.row_z), ('SD', mg.row_sd)):
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
                    if min_v is not None and pos < min_v:
                        violations.append({'pm_name': pm_name, 'row_label': row_label, 'address': addr, 'position': pos, 'min': min_v, 'max': max_v, 'relation': 'below'})
                    elif max_v is not None and pos >= max_v:
                        violations.append({'pm_name': pm_name, 'row_label': row_label, 'address': addr, 'position': pos, 'min': min_v, 'max': max_v, 'relation': 'above_or_equal'})
            except Exception:
                continue
        return violations

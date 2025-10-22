"""Helper for loading and checking forbidden stage fire positions.

Provides ForbiddenPositionStore which mirrors the behavior previously in MainWindow:
- load(file_path=None): loads JSON file (defaults to parameters/ForbiddenStageFirePositions.json next to project)
- check(pm_panel, part1_rows): returns list of matching entries (label+description) for PM groups

This module is safe to call from the UI thread; it only reads UI-accessible values.
"""
import os
import json

class ForbiddenPositionStore:
    def __init__(self, file_path: str = None):
        self.file_path = file_path
        self.entries = []

    def load(self, file_path: str = None):
        """Load file (sets self.entries)."""
        path = file_path or self.file_path
        if path is None:
            base = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base, '..', 'parameters', 'ForbiddenStageFirePositions.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                self.entries = data
            else:
                self.entries = []
        except FileNotFoundError:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump([], f, indent=2)
            except Exception:
                pass
            self.entries = []
        except Exception:
            self.entries = []
        return self.entries

    def check(self, pm_panel, part1_rows):
        """Check current positions against entries and return list of matches.

        pm_panel: PMPanel instance (provides pm1/pm2/pm3 mirror groups with row_* attributes)
        part1_rows: list of MotorRow objects (with info.eng_value and info.short)
        """
        matches = []
        try:
            # gather auto-enabled groups
            auto_enabled_groups = []
            try:
                for idx, mg in enumerate((pm_panel.pm1, pm_panel.pm2, pm_panel.pm3), start=1):
                    try:
                        if getattr(mg, 'auto', None) is not None and mg.auto.isChecked():
                            auto_enabled_groups.append((idx, mg))
                    except Exception:
                        continue
            except Exception:
                auto_enabled_groups = []

            if not auto_enabled_groups:
                return []

            pos_map = {}
            addr_to_ids = {}
            for mg_i, mg in auto_enabled_groups:
                try:
                    if getattr(mg, 'row_rx', None) is not None:
                        val = float(mg.row_rx.get_current())
                        pos_map[f'PM{mg_i}R'] = val
                        pos_map[f'PM{mg_i}X'] = val
                        try:
                            addr = int(mg.row_rx.stage_num.value())
                            if addr > 0:
                                addr_to_ids.setdefault(addr, []).extend([f'PM{mg_i}R', f'PM{mg_i}X'])
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if getattr(mg, 'row_y', None) is not None:
                        val = float(mg.row_y.get_current())
                        pos_map[f'PM{mg_i}Y'] = val
                        try:
                            addr = int(mg.row_y.stage_num.value())
                            if addr > 0:
                                addr_to_ids.setdefault(addr, []).append(f'PM{mg_i}Y')
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if getattr(mg, 'row_z', None) is not None:
                        val = float(mg.row_z.get_current())
                        pos_map[f'PM{mg_i}Z'] = val
                        try:
                            addr = int(mg.row_z.stage_num.value())
                            if addr > 0:
                                addr_to_ids.setdefault(addr, []).append(f'PM{mg_i}Z')
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if getattr(mg, 'row_sd', None) is not None:
                        val = float(mg.row_sd.get_current())
                        pos_map[f'PM{mg_i}SD'] = val
                        pos_map[f'PM{mg_i}D'] = val
                        try:
                            addr = int(mg.row_sd.stage_num.value())
                            if addr > 0:
                                addr_to_ids.setdefault(addr, []).extend([f'PM{mg_i}SD', f'PM{mg_i}D'])
                        except Exception:
                            pass
                except Exception:
                    pass

            # fallback: use only addresses that map to auto-enabled groups
            try:
                for addr, ids in addr_to_ids.items():
                    try:
                        if addr <= 0 or addr > len(part1_rows):
                            continue
                        row = part1_rows[addr - 1]
                        eng = float(getattr(row.info, 'eng_value', 0.0))
                        for idn in ids:
                            if idn not in pos_map:
                                pos_map[str(idn)] = eng
                        try:
                            key = getattr(row.info, 'short', None)
                            if key and key not in pos_map:
                                pos_map[str(key)] = eng
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                pass

            # Evaluate entries (require all ranges to match)
            for ent in getattr(self, 'entries', []) or []:
                try:
                    label = str(ent.get('label', 'Unnamed'))
                    desc = str(ent.get('description', ''))
                    ranges = ent.get('ranges', [])
                    if not ranges:
                        continue
                    all_match = True
                    for rng in ranges:
                        try:
                            stage_id = str(rng.get('stage', '')).strip()
                            if not stage_id or stage_id not in pos_map:
                                all_match = False
                                break
                            cur = float(pos_map.get(stage_id, 0.0))
                            minv = rng.get('min', None)
                            maxv = rng.get('max', None)
                            tol = 1e-4
                            low_ok = True if minv is None else (cur > float(minv) + tol)
                            high_ok = True if maxv is None else (cur < float(maxv) - tol)
                            if not (low_ok and high_ok):
                                all_match = False
                                break
                        except Exception:
                            all_match = False
                            break
                    if all_match:
                        matches.append({'label': label, 'description': desc})
                except Exception:
                    continue
        except Exception:
            pass
        return matches

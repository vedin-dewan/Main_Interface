from __future__ import annotations

import os
from PyQt6 import QtCore


class InfoWriter(QtCore.QObject):
    """Background writer that writes Info text files without blocking the UI.

    Use the MainWindow's signal to pass a dict payload with keys:
      - outdir: str
      - info_name: str
      - info_lines: List[str]
    """
    log = QtCore.pyqtSignal(str)
    # emitted when write_info_and_shot_log finishes; payload is the dict passed in
    write_complete = QtCore.pyqtSignal(dict)

    @QtCore.pyqtSlot(dict)
    def write_info(self, payload: dict):
        try:
            outdir = str(payload.get('outdir', '') or '').strip()
            info_name = str(payload.get('info_name', '') or '').strip()
            info_lines = payload.get('info_lines', []) or []
            if not outdir or not info_name:
                self.log.emit('InfoWriter: missing outdir or info_name; skipping write')
                return
            try:
                os.makedirs(outdir, exist_ok=True)
            except Exception:
                pass
            info_full = os.path.join(outdir, info_name)
            try:
                with open(info_full, 'w', encoding='utf-8') as fh:
                    for ln in info_lines:
                        fh.write(ln + '\n')
                self.log.emit(f"Wrote shot info file: {info_name}")
            except Exception as e:
                self.log.emit(f"InfoWriter: failed to write {info_name}: {e}")
        except Exception as e:
            try:
                self.log.emit(f"InfoWriter internal error: {e}")
            except Exception:
                pass

    @QtCore.pyqtSlot()
    def close(self):
        # nothing special to do; placeholder for graceful shutdown if needed
        return

    @QtCore.pyqtSlot(dict)
    def append_shot_log(self, payload: dict):
        """Append a single line to SHOT_LOG.txt in the outdir.

        payload keys:
          - outdir: str
          - info_name: str
          - second_line: str  (the already-joined second-line to append)
        """
        try:
            outdir = str(payload.get('outdir', '') or '').strip()
            info_name = str(payload.get('info_name', '') or '').strip()
            second_line = payload.get('second_line', '') or ''
            if not outdir or not info_name or not second_line:
                self.log.emit('InfoWriter.append_shot_log: missing fields; skipping')
                return
            try:
                os.makedirs(outdir, exist_ok=True)
            except Exception:
                pass
            shot_log_path = os.path.join(outdir, 'SHOT_LOG.txt')
            line = second_line + '\t' + os.path.join(outdir, info_name)
            try:
                with open(shot_log_path, 'a', encoding='utf-8') as shf:
                    shf.write(line + '\n')
                self.log.emit(f"Updated SHOT_LOG: {os.path.basename(shot_log_path)}")
            except Exception as e:
                self.log.emit(f"InfoWriter: failed to append SHOT_LOG: {e}")
        except Exception as e:
            try:
                self.log.emit(f"InfoWriter.append_shot_log internal error: {e}")
            except Exception:
                pass

    @QtCore.pyqtSlot(dict)
    def write_info_and_shot_log(self, payload: dict):
        """Compose and write the Info file and append SHOT_LOG entry.

        Expected payload keys (all keys optional but missing fields will be handled):
          - outdir: str
          - experiment: str
          - shotnum: int
          - renamed: list of (old_path, new_path) tuples
          - part_rows: list of (abr, eng_value) tuples
          - cameras: list of camera dicts (each may contain 'Name','Purpose','Filters')
          - spectrometers: list of spectrometer dicts (each may contain 'filename','name')
          - event_ts: float timestamp (seconds since epoch) optional
        """
        try:
            outdir = str(payload.get('outdir', '') or '').strip()
            exp = str(payload.get('experiment', '') or 'Experiment').strip()
            shotnum = int(payload.get('shotnum', 0) or 0)
            renamed = payload.get('renamed', []) or []
            part_rows = payload.get('part_rows', []) or []
            cameras = payload.get('cameras', []) or []
            spectrometers = payload.get('spectrometers', []) or []
            event_ts = payload.get('event_ts', None)

            # derive date/time parts from first renamed file if possible
            date_s = None
            time_s = None
            if renamed:
                try:
                    first_new = os.path.basename(renamed[0][1])
                    parts = first_new.split('_')
                    shot_index = next((i for i, p in enumerate(parts) if p.startswith('Shot')), None)
                    if shot_index is not None and len(parts) > shot_index + 2:
                        date_s = parts[shot_index + 1]
                        time_s = parts[shot_index + 2]
                except Exception:
                    date_s = None
                    time_s = None

            if date_s is None or time_s is None:
                if event_ts is not None:
                    try:
                        from datetime import datetime
                        ets = datetime.fromtimestamp(float(event_ts))
                        ts = ets
                    except Exception:
                        from datetime import datetime
                        ts = datetime.now()
                else:
                    from datetime import datetime
                    ts = datetime.now()
                date_s = ts.strftime('%Y%m%d')
                ms = int(ts.microsecond / 1000)
                time_s = ts.strftime('%H%M%S') + f"{ms:03d}"

            # human-readable date/time
            try:
                hr_date = f"{int(date_s[4:6])}/{int(date_s[6:8])}/{int(date_s[0:4])}"
            except Exception:
                from datetime import datetime
                hr_date = datetime.now().strftime('%m/%d/%Y')
            try:
                hh = int(time_s[0:2]); mm = int(time_s[2:4]); ss = int(time_s[4:6])
                ampm = 'AM'
                display_h = hh
                if hh == 0:
                    display_h = 12
                    ampm = 'AM'
                elif hh == 12:
                    display_h = 12
                    ampm = 'PM'
                elif hh > 12:
                    display_h = hh - 12
                    ampm = 'PM'
                time_display = f"{display_h}:{mm:02d}:{ss:02d} {ampm}"
            except Exception:
                from datetime import datetime
                time_display = datetime.now().strftime('%I:%M:%S %p')

            # Build info lines
            info_lines = []
            info_lines.append("ShotInfoWriter: VERSION_2.0.0")
            second = ["Shot", str(shotnum), hr_date, time_display]
            try:
                for abr, val in part_rows:
                    second.append(f"{abr}-{float(val):.3f}")
            except Exception:
                pass
            info_lines.append('\t'.join(second))
            # third line: numeric positions
            try:
                third_vals = [f"{float(v):.3f}" for (_abr, v) in part_rows]
            except Exception:
                third_vals = []
            info_lines.append('\t'.join(third_vals))

            # camera lines
            try:
                cam_by_name = {str(c.get('Name','')).strip(): c for c in cameras if c.get('Name')}
                for name, newfull in sorted(((n, p) for n, p in ((
                    (os.path.basename(nm).split('_')[0], p) if p else (None, None)
                ) for nm, p in renamed) if n in cam_by_name), key=lambda x: x[0]):
                    c = cam_by_name.get(name, {})
                    purpose = str(c.get('Purpose','')).strip()
                    filters = str(c.get('Filters','')).strip()
                    info_lines.append(f"{name} $\t{purpose} $\t{filters} $\t\t{newfull}")
            except Exception:
                # fallback: attempt to match renamed by camera token (if provided separately)
                try:
                    cam_by_name = {str(c.get('Name','')).strip(): c for c in cameras if c.get('Name')}
                    for (oldf, newf) in renamed:
                        nb = os.path.basename(newf)
                        for name in cam_by_name:
                            if name and name.lower() in nb.lower():
                                c = cam_by_name.get(name, {})
                                purpose = str(c.get('Purpose','')).strip()
                                filters = str(c.get('Filters','')).strip()
                                info_lines.append(f"{name} $\t{purpose} $\t{filters} $\t\t{newf}")
                                break
                except Exception:
                    pass

            # spectrometer lines
            try:
                spec_by_token = {str(s.get('filename','')).strip(): s for s in spectrometers if s.get('filename')}
                for token, newfull in sorted(((t, p) for t, p in ((
                    (os.path.basename(nm).split('_')[0], p) if p else (None, None)
                ) for nm, p in renamed) if t in spec_by_token), key=lambda x: x[0]):
                    s = spec_by_token.get(token, {})
                    name = str(s.get('name','')).strip()
                    label = f"{name}Spec" if name else f"{token}Spec"
                    info_lines.append(f"{token} $\t{label} $\t\t{newfull}")
            except Exception:
                # fallback: match by token substring
                try:
                    spec_by_token = {str(s.get('filename','')).strip(): s for s in spectrometers if s.get('filename')}
                    for (oldf, newf) in renamed:
                        nb = os.path.basename(newf)
                        for token in spec_by_token:
                            if token and token.lower() in nb.lower():
                                s = spec_by_token.get(token, {})
                                name = str(s.get('name','')).strip()
                                label = f"{name}Spec" if name else f"{token}Spec"
                                info_lines.append(f"{token} $\t{label} $\t\t{newf}")
                                break
                except Exception:
                    pass

            # ensure outdir exists
            try:
                if not outdir:
                    self.log.emit('InfoWriter: write_info_and_shot_log missing outdir; skipping')
                    return
                os.makedirs(outdir, exist_ok=True)
            except Exception:
                pass

            # write info file
            try:
                info_name = f"{exp}_Shot{shotnum:05d}_{date_s}_{time_s}_Info.txt"
                info_full = os.path.join(outdir, info_name)
                with open(info_full, 'w', encoding='utf-8') as fh:
                    for ln in info_lines:
                        fh.write(ln + '\n')
                self.log.emit(f"Wrote shot info file: {info_name}")
            except Exception as e:
                self.log.emit(f"InfoWriter: failed to write info file: {e}")

            # append SHOT_LOG
            try:
                shot_log_path = os.path.join(outdir, 'SHOT_LOG.txt')
                shot_log_line = '\t'.join(second) + '\t' + os.path.join(outdir, info_name)
                with open(shot_log_path, 'a', encoding='utf-8') as shf:
                    shf.write(shot_log_line + '\n')
                self.log.emit(f"Updated SHOT_LOG: {os.path.basename(shot_log_path)}")
                # Notify listeners that the Info + SHOT_LOG write has completed
                try:
                    payload_out = dict(payload) if isinstance(payload, dict) else {}
                    # include derived info_name/outdir/shotnum to help listeners
                    payload_out.setdefault('outdir', outdir)
                    payload_out.setdefault('info_name', info_name)
                    payload_out.setdefault('shotnum', shotnum)
                    payload_out.setdefault('event_ts', event_ts)
                    self.write_complete.emit(payload_out)
                except Exception:
                    pass
            except Exception as e:
                self.log.emit(f"InfoWriter: failed to update SHOT_LOG: {e}")

        except Exception as e:
            try:
                self.log.emit(f"InfoWriter.write_info_and_shot_log internal error: {e}")
            except Exception:
                pass

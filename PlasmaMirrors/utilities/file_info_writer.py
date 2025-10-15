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

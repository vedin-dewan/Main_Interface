from __future__ import annotations
from PyQt6 import QtCore, QtWidgets

class FireControlsPanel(QtWidgets.QWidget):
    # GUI -> backend
    request_mode  = QtCore.pyqtSignal(str)   # "continuous" | "single" | "burst"
    request_shots = QtCore.pyqtSignal(int)   # applies to both Single and Burst
    request_reset = QtCore.pyqtSignal()      # reset shot counter on request
    request_fire  = QtCore.pyqtSignal()      # start action
    # Emitted when the user configures and saves a new shot counter value
    shot_config_saved = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        grp = QtWidgets.QGroupBox("Trigger Mode")
        grp.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                          QtWidgets.QSizePolicy.Policy.Fixed)
        g = QtWidgets.QGridLayout(grp)
        g.setContentsMargins(30, 30, 30, 30)
        g.setHorizontalSpacing(20)
        g.setVerticalSpacing(16)

        # Radios in a clean vertical column
        self.rb_cont   = QtWidgets.QRadioButton("Continuous")
        self.rb_single = QtWidgets.QRadioButton("Single Shot")
        self.rb_burst  = QtWidgets.QRadioButton("Burst")
        self.rb_cont.setChecked(True)

        col_modes = QtWidgets.QVBoxLayout()
        col_modes.addWidget(self.rb_cont)
        col_modes.addWidget(self.rb_single)
        col_modes.addWidget(self.rb_burst)
        col_modes.addStretch(1)
        # span the modes column down a few rows so it vertically aligns with the
        # other rows we add (shots, buffers, counter, fire button)
        g.addLayout(col_modes, 0, 0, 5, 1)

        # Shots row (shared for Single & Burst)
        lab_shots = QtWidgets.QLabel("# Shots:")
        self.spin_shots = QtWidgets.QSpinBox()
        self.spin_shots.setRange(1, 9999)
        self.spin_shots.setValue(1) # default 1 shot
        self.spin_shots.setFixedWidth(100)
        self.spin_shots.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        shots_row = QtWidgets.QHBoxLayout()
        shots_row.addWidget(lab_shots)
        shots_row.addWidget(self.spin_shots)
        shots_row.addStretch(1)
        g.addLayout(shots_row, 0, 1, 1, 2)

        # ----- Interval (ms) -----
        lab_interval = QtWidgets.QLabel("Camera Buffer (ms):")
        self.spin_interval = QtWidgets.QSpinBox()
        self.spin_interval.setRange(1, 1_000_000)  # 1 ms to 1000 s
        self.spin_interval.setValue(2000)           # default 2000 ms
        self.spin_interval.setFixedWidth(100)
        self.spin_interval.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        interval_row = QtWidgets.QHBoxLayout()
        interval_row.addWidget(lab_interval)
        interval_row.addWidget(self.spin_interval)
        interval_row.addStretch(1)
        # place Camera Buffer in row 1, spanning the two right-hand columns
        g.addLayout(interval_row, 1, 1, 1, 2)

        # ----- Post-Auto buffer (ms) -----
        lab_post_auto = QtWidgets.QLabel("Post-Auto buffer (ms):")
        self.spin_post_auto = QtWidgets.QSpinBox()
        self.spin_post_auto.setRange(0, 10_000)
        self.spin_post_auto.setValue(500)  # default 500 ms
        self.spin_post_auto.setFixedWidth(100)
        self.spin_post_auto.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        post_auto_row = QtWidgets.QHBoxLayout()
        post_auto_row.addWidget(lab_post_auto)
        post_auto_row.addWidget(self.spin_post_auto)
        post_auto_row.addStretch(1)
        # place Post-Auto buffer on its own row (row 2) to avoid overlap
        g.addLayout(post_auto_row, 2, 1, 1, 2)

        # ----- Shot Counter (read-only display) -----
        lab_counter = QtWidgets.QLabel("Shot Counter:")
        self.disp_counter = QtWidgets.QSpinBox()
        self.disp_counter.setRange(0, 9_999_999)
        self.disp_counter.setValue(0)
        self.disp_counter.setReadOnly(True)
        self.disp_counter.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.disp_counter.setFixedWidth(100)
        self.disp_counter.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        counter_row = QtWidgets.QHBoxLayout()
        counter_row.addWidget(lab_counter)
        counter_row.addWidget(self.disp_counter)
        # Configure button to edit and save the shot counter
        self.btn_configure = QtWidgets.QPushButton("Configure")
        self.btn_configure.setFixedWidth(90)
        counter_row.addWidget(self.btn_configure)
        counter_row.addStretch(1)
        # move counter to row 3 because we added the post-auto row
        g.addLayout(counter_row, 3, 1, 1, 2)

        # Big Fire button spanning the width
        self.btn_fire = QtWidgets.QPushButton("Fire")
        self.btn_fire.setMinimumHeight(44)
        self.btn_fire.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                    QtWidgets.QSizePolicy.Policy.Fixed)
        self.btn_fire.setStyleSheet("background:#D30000; color:white; font-weight:700;")
        # Fire button now on row 4
        g.addWidget(self.btn_fire, 4, 1, 1, 2)

        # Sequence progress bar (hidden until a sequence starts)
        self.seq_progress = QtWidgets.QProgressBar()
        self.seq_progress.setMinimum(0)
        self.seq_progress.setMaximum(100)
        self.seq_progress.setValue(0)
        self.seq_progress.setTextVisible(True)
        self.seq_progress.setVisible(False)
        # Sequence progress now on row 5
        g.addWidget(self.seq_progress, 5, 1, 1, 2)

        # Status line
        self.lab_status = QtWidgets.QLabel("Ready")
        # status aligned with the progress bar on the left
        g.addWidget(self.lab_status, 5, 0, 1, 1)

        # column stretch so the button gets space
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 2)
        g.setColumnStretch(2, 3)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(grp)

        # wire signals
        self.rb_cont.toggled.connect(lambda on: on and self._emit_mode("continuous"))
        self.rb_single.toggled.connect(lambda on: on and self._emit_mode("single"))
        self.rb_burst.toggled.connect(lambda on: on and self._emit_mode("burst"))
        self.spin_shots.editingFinished.connect(self._emit_shots)
        self.btn_fire.clicked.connect(self.request_fire)
        self.btn_configure.clicked.connect(self._on_configure_clicked)

        # ensure initial visual state for the fire button (continuous by default)
        try:
            self._current_mode = 'continuous'
            self._update_fire_button_state()
        except Exception:
            pass

    # ----- slots for backend to update UI -----
    @QtCore.pyqtSlot(str)
    def set_status(self, text: str):
        self.lab_status.setText(text)

    # ----- internals -----
    def _emit_mode(self, m: str):
        # remember current mode and update UI
        try:
            self._current_mode = m
            self._update_fire_button_state()
        except Exception:
            pass
        self.request_mode.emit(m)

    def _update_fire_button_state(self):
        """Enable the Fire button only in 'single' or 'burst' modes. In continuous mode disable and grey it out."""
        try:
            mode = getattr(self, '_current_mode', 'continuous')
            enabled = (mode in ('single', 'burst'))
            self.btn_fire.setEnabled(enabled)
            if enabled:
                # active red button
                self.btn_fire.setStyleSheet("background:#D30000; color:white; font-weight:700;")
            else:
                # faded/disabled appearance
                self.btn_fire.setStyleSheet("background:#444444; color:#9a9a9a; font-weight:600;")
        except Exception:
            pass

    # helpers for sequence progress control
    def set_sequence_active(self, active: bool, total_shots: int = 0):
        try:
            if active:
                self.seq_progress.setVisible(True)
                self.seq_progress.setMaximum(max(1, int(total_shots)))
                self.seq_progress.setValue(0)
                # visually fade the Fire button when active
                self.btn_fire.setStyleSheet("background:#444444; color:#9a9a9a; font-weight:600;")
                # keep the button enabled so the user can click to queue another sequence;
                # MainWindow enforces that queued requests only start once the current sequence and post-processing complete.
                self.btn_fire.setEnabled(True)
            else:
                self.seq_progress.setVisible(False)
                self.seq_progress.setValue(0)
                # restore Fire button state per mode rules
                self._update_fire_button_state()
        except Exception:
            pass

    def set_sequence_progress(self, value: int):
        try:
            if self.seq_progress.isVisible():
                self.seq_progress.setValue(int(value))
        except Exception:
            pass

    def _emit_shots(self):
        self.request_shots.emit(int(self.spin_shots.value()))

    def _on_configure_clicked(self):
        """Open a simple dialog to set the shot counter and emit the saved value."""
        try:
            current = int(self.disp_counter.value()) if getattr(self, 'disp_counter', None) is not None else 0
            val, ok = QtWidgets.QInputDialog.getInt(self, 'Configure Shot Counter', 'Shot number:', value=current, min=0, max=9999999)
            if ok:
                try:
                    # update displayed counter immediately
                    self.disp_counter.setValue(int(val))
                except Exception:
                    pass
                # notify main window to persist this value
                try:
                    self.shot_config_saved.emit(int(val))
                except Exception:
                    pass
        except Exception:
            pass

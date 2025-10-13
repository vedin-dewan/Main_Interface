from __future__ import annotations
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import QFileDialog, QStyle


class SavingPanel(QtWidgets.QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Saving", parent)

        layout = QtWidgets.QGridLayout(self)
        self.setFixedHeight(180)

        # --- 1. Output Directory ---
        self.dir_label = QtWidgets.QLabel("Output Directory")
        self.dir_edit = QtWidgets.QLineEdit()
        self.dir_button = QtWidgets.QToolButton()
        self.dir_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.dir_button.clicked.connect(self._choose_folder)

        layout.addWidget(self.dir_label, 0, 0)
        layout.addWidget(self.dir_edit, 0, 1)
        layout.addWidget(self.dir_button, 0, 2)

        # --- 2. Experiment Name ---
        self.exp_label = QtWidgets.QLabel("Experiment Name")
        self.exp_edit = QtWidgets.QLineEdit()
        layout.addWidget(self.exp_label, 1, 0)
        layout.addWidget(self.exp_edit, 1, 1, 1, 2)

        # --- 3. Burst Save Folder (Relative) ---
        self.burst_label = QtWidgets.QLabel("Burst Save Folder (Relative)")
        self.burst_edit = QtWidgets.QLineEdit()
        layout.addWidget(self.burst_label, 2, 0)
        layout.addWidget(self.burst_edit, 2, 1, 1, 2)
        layout.setVerticalSpacing(2)     # reduce space between rows (default ~6–10)
        layout.setContentsMargins(2, 2, 2, 2)  # shrink the outer padding

        self.setLayout(layout)

    def _choose_folder(self):
        start_dir = self.dir_edit.text().strip() or QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.DocumentsLocation
        )
        dirname = QFileDialog.getExistingDirectory(self, "Select Output Directory", start_dir)
        if dirname:
            self.dir_edit.setText(dirname)

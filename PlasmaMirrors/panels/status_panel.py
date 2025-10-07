from PyQt6 import QtCore, QtGui, QtWidgets

class StatusPanel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(420)
        self.setMaximumWidth(600)
        grp = QtWidgets.QGroupBox("Status")
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        fm = self.log.fontMetrics()
        row_h = fm.lineSpacing()
        self.log.setMinimumHeight(int(row_h * 35 + 12))
        btn_clear = QtWidgets.QPushButton("Clear"); btn_clear.clicked.connect(self.log.clear)
        btn_copy = QtWidgets.QPushButton("Copy All"); btn_copy.clicked.connect(self._copy_all)
        top = QtWidgets.QHBoxLayout(); top.addStretch(1); top.addWidget(btn_copy); top.addWidget(btn_clear)
        v = QtWidgets.QVBoxLayout(); v.addLayout(top); v.addWidget(self.log)
        grp.setLayout(v)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(grp)
        layout.addStretch(1)
        grp.setStyleSheet("QGroupBox { font-weight: 600; }")

    @QtCore.pyqtSlot(str)
    def append_line(self, text: str):
        self.log.appendPlainText(text)
        self.log.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _copy_all(self):
        self.log.selectAll()
        self.log.copy()

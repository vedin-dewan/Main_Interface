"""Main Interface for the Plasma Mirrors Experiment at the ETOILES laboratory.
   Authors: Vedin Dewan, Xuyang Xu, Arunava Das
"""


import sys
from PyQt6 import QtWidgets
from main_window import MainWindow

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
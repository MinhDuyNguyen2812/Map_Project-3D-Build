"""
Entry point for Digital Twin Finland.
Run:
    python main.py
"""

import sys
from PyQt5.QtWidgets import QApplication

from ui.splash_screen import SplashScreen
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    splash   = SplashScreen()
    main_win = None

    def open_main():
        nonlocal main_win
        main_win = MainWindow()
        main_win.show()

    splash.launch_main.connect(open_main)
    splash.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
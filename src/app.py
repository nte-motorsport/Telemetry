"""NTE Telemetry: car telemetry for Neverness to Everness, decoded from the game's own network traffic.

Entry point: python src/app.py (also the PyInstaller script)."""
import sys

from PySide6.QtWidgets import QApplication

import windows
from ui import theme
from ui.main_window import MainWindow


def main():
    windows.set_app_id()
    app = QApplication(sys.argv)
    app.setFont(theme.load_fonts())
    app.setStyleSheet(theme.STYLE)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

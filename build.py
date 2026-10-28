"""Build dist/NTE Telemetry.exe: one file, asks for admin rights on start (raw-socket capture needs them).
Run with the project venv:  .venv\\Scripts\\python build.py"""
import os

import PyInstaller.__main__

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")

# Qt parts the app never touches; leaving them out keeps the exe much smaller.
EXCLUDE = ["tkinter", "matplotlib", "scipy", "PyQt5", "PyQt6", "PySide2",
           "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
           "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore",
           "PySide6.QtMultimedia", "PySide6.QtNetwork", "PySide6.QtSql", "PySide6.QtPdf",
           "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth",
           "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtDesigner"]

PyInstaller.__main__.run([
    os.path.join(SRC, "app.py"),
    "--name", "NTE Telemetry",
    "--onefile", "--windowed", "--uac-admin", "--noconfirm", "--clean",
    "--paths", SRC,
    "--icon", os.path.join(SRC, "assets", "app.ico"),
    # next to the modules, where ui/theme.py looks for them
    "--add-data", f"{os.path.join(SRC, 'assets')}{os.pathsep}assets",
    "--distpath", os.path.join(HERE, "dist"),
    "--workpath", os.path.join(HERE, "build"),
    "--specpath", os.path.join(HERE, "build"),
    *[a for m in EXCLUDE for a in ("--exclude-module", m)],
])

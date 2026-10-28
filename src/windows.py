"""Windows specifics: the taskbar identity and restarting with administrator rights."""
import ctypes
import os
import sys

APP_ID = "NTEMotorsport.Telemetry"


def set_app_id():
    """Own taskbar icon and grouping instead of python.exe's."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass


def relaunch_as_admin():
    """Start this app again elevated (UAC prompt). True if the new instance was launched."""
    if getattr(sys, "frozen", False):
        exe, args = sys.executable, sys.argv[1:]
    else:
        exe, args = sys.executable, [os.path.abspath(sys.argv[0])] + sys.argv[1:]
    params = " ".join(f'"{a}"' for a in args)
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, os.getcwd(), 1) > 32

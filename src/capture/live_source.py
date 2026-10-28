"""Live telemetry: the game's traffic captured on one interface, decoded on a worker thread."""
import time

from PySide6.QtCore import QThread, Signal

from capture.protocol import decode
from capture.raw_socket import RawCapture
from capture.tracker import Tracker


class LiveSource(QThread):
    """Raw-socket capture on one interface. Once the game's ports are known, other traffic is skipped
    so voice chat and the like don't cost decoding time."""
    sample = Signal(dict)       # one tracker output, same fields as tracker.FIELDS
    failed = Signal(str, str)   # kind ("admin" | "error"), message

    def __init__(self, ip):
        super().__init__()
        self.ip = ip
        self._stop = False
        self.tracker = Tracker()

    def stop(self):
        self._stop = True
        self.wait(2000)

    def feed(self, payload):
        """Decode one packet; True if it carried this car's movement."""
        cands = list(decode(payload))
        if not cands:
            return False
        r = self.tracker.pick(cands)
        d = self.tracker.update(*r) if r else None
        if d:
            self.sample.emit(d)
        return r is not None

    def run(self):
        try:
            cap = RawCapture(self.ip)
        except PermissionError:
            self.failed.emit("admin", "Capturing traffic requires administrator rights.")
            return
        except OSError as e:
            self.failed.emit("error", f"Could not start capture on {self.ip}: {e}")
            return
        game, seen = None, 0.0
        try:
            for sport, dport, payload in cap.packets(lambda: self._stop):
                if game and time.monotonic() - seen < 5 and not ({sport, dport} & game):
                    continue
                if self.feed(payload):
                    game, seen = {sport, dport}, time.monotonic()
        except OSError as e:
            self.failed.emit("error", f"Capture stopped: {e}")
        finally:
            cap.close()

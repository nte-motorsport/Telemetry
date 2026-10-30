"""Live telemetry: the game's traffic captured on one interface, decoded on a worker thread."""
import math
import time

from PySide6.QtCore import QThread, Signal

from capture import opponents
from capture.protocol import decode
from capture.raw_socket import RawCapture
from capture.tracker import Tracker


class LiveSource(QThread):
    """Raw-socket capture on one interface. Once the game's ports are known, other traffic is skipped
    so voice chat and the like don't cost decoding time."""
    sample = Signal(dict)       # one tracker output, same fields as tracker.FIELDS
    rivals = Signal(object)     # other racers after a server update, see opponents.Opponents.update
    failed = Signal(str, str)   # kind ("admin" | "error"), message

    def __init__(self, ip):
        super().__init__()
        self.ip = ip
        self._stop = False
        self.tracker = Tracker()
        self.opponents = opponents.Opponents()

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
            if d["jump"]:  # teleported: whoever was around is not any more
                self.opponents = opponents.Opponents()
            self.sample.emit(d)
        return r is not None

    def feed_server(self, payload, t=None):
        """Take the other racers' positions from one packet the game server sent."""
        me = self.tracker.prev
        if not me:
            return
        recs = [r for r in opponents.decode(payload) if math.dist(r[2], me[1:4]) < opponents.NEAR]
        if recs:
            self.rivals.emit(self.opponents.update(time.monotonic() if t is None else t, recs, me[1:4]))

    def run(self):
        try:
            cap = RawCapture(self.ip)
        except PermissionError:
            self.failed.emit("admin", "Capturing traffic requires administrator rights.")
            return
        except OSError as e:
            self.failed.emit("error", f"Could not start capture on {self.ip}: {e}")
            return
        game, server, seen = None, None, 0.0
        try:
            for sport, dport, payload in cap.packets(lambda: self._stop):
                if game and time.monotonic() - seen < 5 and not ({sport, dport} & game):
                    continue
                if self.feed(payload):
                    # the client's own movement goes to the game server, so its port is the destination
                    game, server, seen = {sport, dport}, dport, time.monotonic()
                elif sport == server:
                    self.feed_server(payload)
        except OSError as e:
            self.failed.emit("error", f"Capture stopped: {e}")
        finally:
            cap.close()

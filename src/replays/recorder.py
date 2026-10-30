"""Automatic recording of online races: from the first rival data to the end of the race."""
import datetime
import time

from PySide6.QtCore import QObject, Signal


class RaceRecorder(QObject):
    """A race starts when rivals' positions start coming in and ends when they have stopped for END_AFTER
    seconds, when the player is teleported (a new race or a test drive) or when the app closes."""
    saved = Signal(str)        # the file of a replay just written
    recording = Signal(bool)   # a race recording started / stopped
    END_AFTER = 20.0  # s without rival data that end a race
    MIN_LENGTH = 30.0  # s: shorter recordings (a glimpse of someone in free roam) are not kept

    def __init__(self, store, enabled=True):
        super().__init__()
        self.store = store
        self.enabled = enabled
        self.active = False

    def set_enabled(self, on):
        self.enabled = on
        if not on:
            self.finish()

    def start(self, now):
        self.active = True
        self.t0 = now
        self.started = datetime.datetime.now().replace(microsecond=0).isoformat()
        self.me, self.rivals, self.last_t = [], {}, {}
        self.last_rival = now
        self.recording.emit(True)

    def on_own(self, d):
        if self.active:
            self.me.append([round(d["w"] - self.t0, 3), d["x"], d["y"], d["z"], d["speed_kmh"]])

    def on_rivals(self, cars):
        if not self.enabled or not cars:
            return
        now = time.monotonic()
        if not self.active:
            self.start(now)
        for num, c in cars.items():
            if self.last_t.get(num) == c["t"]:  # not moved since the last packet
                continue
            self.last_t[num] = c["t"]
            v = c["speed_kmh"]
            self.rivals.setdefault(str(num), []).append(
                [round(c["t"] - self.t0, 3), round(c["x"], 2), round(c["y"], 2), round(c["z"], 2),
                 None if v is None else round(v, 1)])
            self.last_rival = now

    def tick(self):
        if self.active and time.monotonic() - self.last_rival > self.END_AFTER:
            self.finish()

    def finish(self):
        if not self.active:
            return
        self.active = False
        self.recording.emit(False)
        times = [r[0] for r in self.me] + [r[0] for rows in self.rivals.values() for r in rows]
        if not self.me or not times:
            return
        t_lo = min(times)
        duration = max(times) - t_lo
        if duration < self.MIN_LENGTH:
            return
        shift = lambda rows: [[round(r[0] - t_lo, 3), *r[1:]] for r in rows]  # start the replay at 0
        path = self.store.save(dict(version=1, started=self.started, duration=round(duration, 3),
                                    me=shift(self.me), rivals={k: shift(v) for k, v in self.rivals.items()}))
        self.saved.emit(path)

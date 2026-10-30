"""The Multiplayer page: in an online race, everyone on one map and everyone's speed over the last minute."""
import math
import time
from collections import deque

import numpy as np
from PySide6.QtWidgets import QHBoxLayout, QWidget

from ui import charts, theme
from ui.widgets import card, legend_dot

WINDOW = 60  # seconds of tracks and speed shown
RIVAL_COLORS = ["#3d8eff", "#3ad164", "#b388ff", "#ff8c42", "#4cc9f0", "#f72585"]


def rival_color(num):
    return RIVAL_COLORS[(num - 1) % len(RIVAL_COLORS)]


class MultiplayerPage(QWidget):
    def __init__(self):
        super().__init__()
        self.me = deque()  # (t, x, y, speed km/h)
        self.rivals = {}   # number -> deque of (t, x, y, speed km/h or NaN)
        self.left = set()  # numbers no longer sent: their last minute stays until the next race
        self.dirty = True

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(theme.GAP)
        self.c_map = charts.MapChart()
        self.c_speed = charts.LineChart(lambda s: f"{s:.0f} s", zero=True)
        self.map_card = card("Map", self.c_map, " ")
        self.speed_card = card("Speed, last 60 s", self.c_speed, " ")
        h.addWidget(self.map_card, 1)
        h.addWidget(self.speed_card, 1)

    # ----- data -----

    def on_own(self, d):
        self.me.append((d["w"], d["x"], d["y"], d["speed_kmh"]))
        self.trim(self.me, d["w"])
        self.dirty = True

    def on_rivals(self, cars):
        for num, c in cars.items():
            hist = self.rivals.setdefault(num, deque())
            if not hist or hist[-1][0] != c["t"]:  # cars the packet didn't move come back unchanged
                v = c["speed_kmh"]
                hist.append((c["t"], c["x"], c["y"], math.nan if v is None else v))
                self.trim(hist, c["t"])
        self.left = {n for n in self.rivals if n not in cars}
        self.dirty = True

    @staticmethod
    def trim(hist, now):
        while hist and now - hist[0][0] > WINDOW:
            hist.popleft()

    def clear(self):
        self.me.clear()
        self.rivals.clear()
        self.left.clear()
        self.dirty = True

    # ----- rendering -----

    def render(self):
        if not self.dirty:
            return
        self.dirty = False
        now = time.monotonic()
        cars = [("You", theme.ACCENT, self.me)]
        cars += [(f"Rival {n}" + (" (left)" if n in self.left else ""), rival_color(n), h)
                 for n, h in sorted(self.rivals.items())]
        tracks, markers, series = [], [], []
        for name, color, h in cars:
            if not h:
                continue
            a = np.array(h, float)
            tracks.append(dict(x=a[:, 1], y=a[:, 2], color=color, width=3.5 if h is self.me else 2.5))
            markers.append((a[-1, 1], a[-1, 2], color))
            series.append((a[:, 0] - now, a[:, 3], color, 2.2 if h is self.me else 1.8))
        self.c_map.set_tracks(tracks, markers)
        self.c_speed.set_series(series, (-WINDOW, 0))
        parts = [f"{legend_dot(color)} {name}" for name, color, h in cars if h]
        if len(cars) == 1:
            parts.append("rivals show up during an online race")
        for c in (self.map_card, self.speed_card):
            c.legend.setText(" &nbsp; ".join(parts))

    def tick(self):
        self.dirty = True  # the time axis moves even without new data

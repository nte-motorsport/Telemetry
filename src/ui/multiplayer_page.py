"""The Multiplayer page: in an online race, everyone on one map and everyone's speed over the last minute, and who
is where in the race."""
import math
import time
from collections import deque

import numpy as np
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ui import charts, standings, theme, units
from ui.world_map import MapPicker, all_maps
from ui.widgets import RacersPanel, card

WINDOW = 60  # seconds of tracks and speed shown
MAP_EVERY = 2.0  # s between looks at which game map the tracks are on (while the world isn't known)
RIVAL_COLORS = ["#3d8eff", "#3ad164", "#b388ff", "#ff8c42", "#4cc9f0", "#f72585"]


def rival_color(num):
    return RIVAL_COLORS[(num - 1) % len(RIVAL_COLORS)]


def segments(a, gap=2.0, jump=100.0):
    """Split rows of [t, x, y, ...] where the car went unseen for a while or the server moved it, so the map
    doesn't draw a straight line across the track there."""
    if len(a) < 2:
        return [a]
    cut = np.flatnonzero((np.diff(a[:, 0]) > gap) | (np.hypot(np.diff(a[:, 1]), np.diff(a[:, 2])) > jump)) + 1
    return [s for s in np.split(a, cut) if len(s) >= 2]


class MultiplayerPage(QWidget):
    def __init__(self):
        super().__init__()
        self.me = deque()  # (t, x, y, speed km/h)
        self.rivals = {}   # number -> deque of (t, x, y, speed km/h or NaN)
        self.left = set()  # numbers no longer sent: their last minute stays until the next race
        self.names = {}  # rival number -> entrant's name, as the capture matched them
        self.snapshot = None  # how far along everyone is, as last sent (capture/progress.py), or None
        self.trails = True  # each car's last minute drawn behind its marker on the map (Settings)
        self.dirty = True

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(theme.GAP)
        h = QHBoxLayout()
        h.setSpacing(theme.GAP)
        v.addLayout(h, 1)
        self.racers = RacersPanel()  # who races, from the race server (capture/roster.py)
        self.racers.set_entrants([])
        v.addWidget(self.racers)
        self.c_map = charts.MapChart()
        self.maps = MapPicker(all_maps())  # the game map under the tracks: the world's, see set_world
        self.map_at = -1e9  # when the map was last looked at
        self.c_speed = charts.LineChart(lambda s: f"{s:.0f} s", zero=True)
        self.map_card = card("Map", self.c_map)
        self.speed_card = card("Speed", self.c_speed)
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

    def set_field(self, entrants):
        """The race's entrants, from the capture."""
        self.racers.set_entrants(entrants)
        self.show_standings()

    def set_names(self, names):
        """{rival number: name}, from the capture: each entrant in their car's colour."""
        self.names = dict(names)
        self.racers.set_colors({name: rival_color(num) for num, name in names.items()})
        self.show_standings()

    def set_me(self, name):
        self.racers.set_me(name)
        self.show_standings()

    def set_standings(self, snapshot):
        """How far along everyone is (progress.Standings.snapshot), from the capture; None out of a race."""
        self.snapshot = snapshot
        self.show_standings()

    def show_standings(self):
        """Each entrant's place, gap and what's left, in their box (again when the unit changes)."""
        s = self.snapshot
        if not s:
            self.racers.set_standings({})
            return
        named = standings.by_name(s["racers"], self.names, self.racers.me, self.racers.entrants)
        mine = named.get("")
        self.racers.set_standings({n: (r["place"], *standings.lines(r, mine, s["length"])) for n, r in named.items()})

    def set_trails(self, on):
        """Draw each car's last minute behind its marker on the map, or the markers alone."""
        self.trails = on
        self.dirty = True

    def set_world(self, level):
        """The game world (UE level path, "" while not known), from the capture."""
        self.maps.set_level(level)
        self.map_at = -1e9
        self.dirty = True

    def clear(self):
        self.me.clear()
        self.rivals.clear()
        self.left.clear()
        self.maps.reset()  # another place
        self.c_map.set_backdrop(None)
        self.dirty = True

    # ----- rendering -----

    def render(self):
        if not self.dirty:
            return
        self.dirty = False
        now = time.monotonic()
        cars = [(theme.ACCENT, self.me)] + [(rival_color(n), h) for n, h in sorted(self.rivals.items())]
        tracks, markers, series = [], [], []
        area = ([], [])  # where the cars have been: the view is fitted to it when the trails aren't drawn
        for color, h in cars:
            if not h:
                continue
            a = np.array(h, float)
            if self.trails:
                tracks += [dict(x=s[:, 1], y=s[:, 2], color=color, width=3.5 if h is self.me else 2.5)
                           for s in segments(a)]
            else:
                area[0].extend(a[:, 1])
                area[1].extend(a[:, 2])
            markers.append((a[-1, 1], a[-1, 2], color))
            series.append((a[:, 0] - now, units.speed(a[:, 3]), color, 2.2 if h is self.me else 1.8))
        if now - self.map_at >= MAP_EVERY:
            self.map_at = now
            own = np.array(self.me, float).reshape(-1, 4)  # (t, x, y, km/h), the last minute
            self.c_map.set_backdrop(self.maps.update(own[:, 1], own[:, 2]))
        self.c_map.set_tracks(tracks, markers, None if self.trails else area)
        self.c_speed.set_series(series, (-WINDOW, 0))

    def tick(self):
        self.dirty = True  # the time axis moves even without new data

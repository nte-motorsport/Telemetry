"""The Multiplayer page: in an online race, everyone on one map and everyone's speed over the last minute, and who
is where in the race."""
import math
import time
from collections import deque

import numpy as np
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ui import charts, standings, theme, units
from ui.world_map import MapPicker, all_maps
from ui import ranks
from ui.vehicles import car_name
from ui.widgets import DriversPanel, TimingPanel, card

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
        # on the left: who is where in the race, and who they are (from the race server, capture/roster.py)
        self.racers = TimingPanel()
        self.racers.set_entrants([])
        self.drivers = DriversPanel()
        self.lobby = {}  # name -> rank points before the race, of the players the race was matched with
        self.own_rank = None  # the player's own (rank row, points), as the server names them
        self.plates = {}  # entrant's name -> their car's number plate
        left = QVBoxLayout()
        left.setSpacing(theme.GAP)
        left.addWidget(self.racers)
        left.addWidget(self.drivers)
        left.addStretch()
        h.addLayout(left)
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

    def set_plates(self, plates):
        """{entrant's name: number plate}, from the capture."""
        self.plates = dict(plates)
        self.show_drivers()

    def set_lobby(self, lobby):
        """The players the latest race was matched with, from the capture (capture/ranking.py)."""
        self.lobby = {e["name"]: e["points"] for e in lobby}
        self.show_drivers()

    def set_rank(self, rank, points):
        """The player's own rank and points, from the capture."""
        self.own_rank = (rank, points)
        self.show_drivers()

    def show_drivers(self):
        """Each entrant in detail: the players, then the bots, each in alphabetical order (they stay put as places
        change)."""
        out = []
        for e in sorted(self.racers.entrants, key=lambda e: (bool(e.get("bot")), e["name"].casefold())):
            me = bool(self.racers.me) and e["name"] == self.racers.me
            bot = bool(e.get("bot"))
            points = None if bot else self.lobby.get(e["name"])
            if me and self.own_rank:
                rank, points = self.own_rank
            else:
                rank = ranks.from_points(points) if points is not None else None
            car = car_name(e["car"]) if e.get("car") else ""
            if e["name"] in self.plates:
                car = f"{car} ({self.plates[e['name']]})" if car else f"({self.plates[e['name']]})"
            out.append(dict(name=e["name"], bot=bot, car=car,
                            color=theme.ACCENT if me else self.racers.colors.get(e["name"]), rank=rank, points=points))
        self.drivers.set_racers(out)

    def set_standings(self, snapshot):
        """How far along everyone is (progress.Standings.snapshot), from the capture; None out of a race."""
        self.snapshot = snapshot
        self.show_standings()

    def show_standings(self):
        """Each entrant's place and how far behind the racer ahead, in their row."""
        s = self.snapshot
        if not s:
            self.racers.set_standings({})
            self.show_drivers()
            return
        named = standings.by_name(s["racers"], self.names, self.racers.me, self.racers.entrants)
        self.racers.set_standings({n: (r["place"], r["interval"], r["finish"] is not None) for n, r in named.items()})
        self.show_drivers()

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

"""The Live page: telemetry tiles and the last minute on charts."""
import time

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import windows
from capture.live_source import LiveSource
from capture.pcap import RawTap
from capture.raw_socket import default_ip, local_ips
from ui import charts, theme
from ui.world_map import MapPicker, all_maps
from ui.widgets import Button, ChartGrid, Tile, card, label, legend_dot

LIVE_KEEP = 120  # seconds of live history kept in memory
LIVE_WINDOW = 60  # seconds shown on the live charts
LAT_COLOR, Z_COLOR, YAW_COLOR = "#3d8eff", "#3ad164", "#ff8c42"
# the game map under the trajectory is the one the drive is on, see world_map.MapPicker
MAP_WINDOW = 60  # s of the drive the map is told from, while the world isn't known
MAP_EVERY = 2.0  # s between looks at which map it is


def signed(v):
    return f"{v:+.2f}"


class History:
    """The live samples as numpy columns, appended in place; the oldest are dropped by moving the start, so a
    frame takes slices instead of rebuilding lists from every sample's dict. Times ("w") only grow."""
    KEYS = ("w", "x", "y", "z", "speed_kmh", "g_long", "g_lat", "yaw_rate")

    def __init__(self, size=4096):
        self.col = {k: i for i, k in enumerate(self.KEYS)}
        self.a = np.empty((len(self.KEYS), size))
        self.lo = self.hi = 0  # the samples kept are a[:, lo:hi]

    def __len__(self):
        return self.hi - self.lo

    def __getitem__(self, key):
        return self.a[self.col[key], self.lo:self.hi]

    def append(self, d):
        if self.hi == self.a.shape[1]:
            n = len(self)
            # always a new array: the charts may still hold slices of the old one until they repaint
            a = np.empty((len(self.KEYS), max(self.a.shape[1], 2 * n)))
            a[:, :n] = self.a[:, self.lo:self.hi]
            self.a, self.lo, self.hi = a, 0, n
        self.a[:, self.hi] = [d[k] for k in self.KEYS]
        self.hi += 1

    def since(self, now, span):
        """Index (from the oldest kept) of the first sample at most span seconds before now. Times only grow,
        so the older ones are the ones before it."""
        return int(np.count_nonzero(now - self["w"] > span))

    def drop_older(self, now, span):
        """Forget the samples more than span seconds before now."""
        self.lo += self.since(now, span)

    def clear(self):
        self.lo = self.hi = 0


class LivePage(QWidget):
    driving = Signal(dict)   # each own sample while in a car, as the charts take it
    rivals = Signal(object)  # the other racers, passed on from the capture
    jumped = Signal()        # teleported: what came before is another place
    world = Signal(str)      # the game world (UE level path), "" while not known
    field = Signal(object)   # the race's entrants, passed on from the capture (capture/roster.py)
    CHARTS = [("speed", "Speed"), ("g", "G-forces"), ("map", "Trajectory"), ("gg", "G-G diagram"),
              ("z", "Altitude"), ("yaw", "Yaw rate")]

    def __init__(self):
        super().__init__()
        self.live = History()
        self.last = None  # the latest sample, for the tiles
        self.live_max = 0.0
        self.shown = {k for k, _ in self.CHARTS}  # charts on the page; the others are not drawn
        self.source = None
        self.source_desc = ""
        self.ip = ""  # the network chosen in Settings
        self.error = None
        self.last_msg = -1e9
        self.in_car = False
        self.dirty = True

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(theme.GAP)
        self.statusbar = self.build_statusbar()  # placed by the main window, below every page

        tiles = QWidget()
        g = QGridLayout(tiles)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(theme.GAP)
        self.tiles = {}
        spec = [("speed", "Speed", "km/h", True), ("gl", "Longitudinal G", "g", False),
                ("ga", "Lateral G", "g", False), ("yaw", "Yaw rate", "°/s", False), ("slope", "Slope", "°", False),
                ("z", "Altitude", "m", False), ("hdg", "Heading", "°", False), ("odo", "Odometer", "km", False),
                ("max", "Top speed", "km/h", False)]
        for i, (k, name, unit, big) in enumerate(spec):
            self.tiles[k] = Tile(name, unit, big)
            g.addWidget(self.tiles[k], 0, i)
            g.setColumnStretch(i, 1)

        xfmt = lambda s: f"{s:.0f} s"
        self.c_speed = charts.LineChart(xfmt, zero=True)
        self.c_g = charts.LineChart(xfmt, sym=1)
        self.c_map = charts.MapChart()
        self.maps = MapPicker(all_maps())
        self.map_at = -1e9  # when the map was last looked at
        self.level = ""  # the game world, as the server names it
        self.raw = None  # a pcap.RawTap the capture gives every packet to while raw traffic is wanted, see set_raw
        self.c_gg = charts.GGChart()
        self.c_z = charts.LineChart(xfmt)
        self.c_yaw = charts.LineChart(xfmt, sym=10)
        t = dict(self.CHARTS)
        self.grid = ChartGrid({
            "speed": card(t["speed"], self.c_speed),
            "g": card(t["g"], self.c_g, f"{legend_dot(theme.ACCENT)} longitudinal &nbsp; {legend_dot(LAT_COLOR)} lateral"),
            "map": card(t["map"], self.c_map),
            "gg": card(t["gg"], self.c_gg),
            "z": card(t["z"], self.c_z),
            "yaw": card(t["yaw"], self.c_yaw),
        })
        v.addWidget(tiles)
        v.addWidget(self.grid, 1)

    def build_statusbar(self):
        """The bar along the bottom of the window: whether data is coming in and how fast, whether a race is
        being recorded."""
        bar = QFrame()
        bar.setObjectName("statusBar")
        bar.setFixedHeight(theme.CONTROL_HEIGHT + theme.GAP)
        h = QHBoxLayout(bar)
        h.setContentsMargins(theme.GAP, 0, theme.GAP, 0)
        h.setSpacing(theme.GAP)
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        h.addWidget(self.dot)
        self.status = label("", "muted")
        h.addWidget(self.status, 1)
        self.admin_btn = Button("Relaunch as administrator", "shield-lock")
        self.admin_btn.set_flag("primary", True)
        self.admin_btn.clicked.connect(lambda: windows.relaunch_as_admin() and QApplication.quit())
        self.admin_btn.hide()
        h.addWidget(self.admin_btn)
        self.rec = label(f'<span style="color:{theme.DANGER}">●</span> Recording race', "muted")
        self.rec.setTextFormat(Qt.RichText)
        self.rec.setToolTip("An online race is being recorded; it will be on the Replays page once it ends")
        self.rec.hide()
        h.addWidget(self.rec)
        self.rate = label("", "muted")
        h.addWidget(self.rate)
        return bar

    # ----- capture -----

    def start(self, ip=None):
        """Capture on ip (a local address), or on the one chosen before; one that no longer exists, or none
        chosen, means the interface that holds the default route."""
        if ip is not None:
            self.ip = ip
        ip = self.ip if self.ip in local_ips() else default_ip()
        self.stop()
        self.error = None
        self.admin_btn.hide()
        self.source, self.source_desc = LiveSource(ip), ip
        self.source.sample.connect(self.on_sample)
        self.source.rivals.connect(self.rivals)
        self.source.failed.connect(self.on_failed)
        self.source.level.connect(self.on_level)
        self.source.field.connect(self.field)
        self.source.tap = self.raw
        self.source.start()
        self.tick()

    def stop(self):
        if self.source:
            self.source.sample.disconnect()
            self.source.rivals.disconnect()
            self.source.level.disconnect()
            self.source.field.disconnect()
            self.on_level("")
            self.field.emit([])
            self.source.stop()
            self.source = None

    def on_failed(self, kind, msg):
        self.error = msg
        self.admin_btn.setVisible(kind == "admin")
        self.tick()

    def on_sample(self, d, wall=None):
        self.last_msg = time.monotonic()
        if d.get("jump"):  # teleported (e.g. into a test drive): start over, so two places aren't joined
            self.clear()
            self.jumped.emit()
        self.in_car = d.get("in_car", True)
        if not self.in_car:  # running and jumping are not telemetry: keep them off the charts
            return
        d["w"] = time.monotonic() if wall is None else wall
        self.live.append(d)
        self.live.drop_older(d["w"], LIVE_KEEP)
        self.last = d
        self.live_max = max(self.live_max, d["speed_kmh"])
        self.dirty = True
        self.driving.emit(d)

    def set_raw(self, on):
        """Keep the last RawTap.SPAN s of raw traffic in memory, for a race's recording to start with, or not
        (and forget what was kept). A capture started again (another network chosen) carries on with it."""
        if on and self.raw is None:
            self.raw = RawTap()
        elif not on:
            self.raw = None
        if self.source:
            self.source.tap = self.raw

    def set_tap(self, writer):
        """Write the raw traffic into writer (a pcap.PcapWriter), the kept seconds first; None: stop."""
        if writer is not None:
            self.set_raw(True)
            self.raw.attach(writer)
        elif self.raw is not None:
            self.raw.detach()

    def on_level(self, level):
        self.level = level
        self.maps.set_level(level)
        self.map_at = -1e9  # look at the map again at the next frame
        self.dirty = True
        self.world.emit(level)
        self.tick()

    def set_recording(self, on):
        self.rec.setVisible(on)

    def set_charts(self, keys):
        self.grid.set_order(keys)
        self.shown = set(keys)
        self.dirty = True

    def clear(self):
        self.live.clear()
        self.last = None
        self.live_max = 0.0
        self.maps.reset()  # another place: its map is told again
        self.c_map.set_backdrop(None)
        self.dirty = True

    def tick(self):
        ok = time.monotonic() - self.last_msg < 3
        color = (theme.ACCENT if not self.in_car else "#3ad164") if ok else theme.DANGER
        self.dot.setStyleSheet(f"background:{color}; border-radius:5px;")
        where = self.source_desc + (f", {self.level.rsplit('/', 1)[-1]}" if self.level else "")
        if ok and not self.in_car:
            text = f"On foot: paused until you get in a car ({where})"
        elif ok:
            text = f"In a car, receiving data ({where})"
        elif self.error:
            text = self.error
        else:
            text = f"No data: not in a car or no game traffic ({self.source_desc})"
        self.status.setText(text)
        now = time.monotonic()
        n = len(self.live) - self.live.since(now, 1) if ok and self.in_car else 0
        self.rate.setText(f"{n} samples/s" if ok and self.in_car else "")
        self.dirty = True  # the charts' time axis moves even without new data

    # ----- rendering -----

    def render(self):
        if not self.dirty:
            return
        self.dirty = False
        d = self.last
        T = self.tiles
        if d:
            T["speed"].set(f"{d['speed_kmh']:.0f}")
            T["gl"].set(signed(d["g_long"]))
            T["ga"].set(signed(d["g_lat"]))
            T["yaw"].set(f"{d['yaw_rate']:.1f}")
            T["slope"].set(f"{d['slope_deg']:.1f}")
            T["z"].set(f"{d['z']:.1f}")
            T["hdg"].set(f"{d['heading']:.0f}")
            T["odo"].set(f"{d['odo_km']:.2f}")
            T["max"].set(f"{self.live_max:.0f}")
        else:
            for t in T.values():
                t.set("–")
        now = time.monotonic()
        L = self.live
        i = L.since(now, LIVE_WINDOW)
        col = lambda k: L[k][i:]
        tx = col("w") - now
        xr = (-LIVE_WINDOW, 0)
        shown = self.shown
        if "speed" in shown:
            self.c_speed.set_series([(tx, col("speed_kmh"), theme.ACCENT, 2.2)], xr)
        if "g" in shown:
            self.c_g.set_series([(tx, col("g_long"), theme.ACCENT, 1.8), (tx, col("g_lat"), LAT_COLOR, 1.8)], xr)
        if "z" in shown:
            self.c_z.set_series([(tx, col("z"), Z_COLOR, 1.8)], xr)
        if "yaw" in shown:
            self.c_yaw.set_series([(tx, col("yaw_rate"), YAW_COLOR, 1.8)], xr)
        if "map" in shown:
            if now - self.map_at >= MAP_EVERY:
                self.map_at = now
                j = L.since(now, MAP_WINDOW)
                self.c_map.set_backdrop(self.maps.update(L["x"][j:], L["y"][j:]))
            self.c_map.set_tracks([dict(x=L["x"], y=L["y"], speeds=L["speed_kmh"])],
                                  [(d["x"], d["y"], theme.TEXT)] if d else [])
        if "gg" in shown:
            tail = max(i, len(L) - 150)
            self.c_gg.set_sets([dict(ga=L["g_lat"][tail:], gl=L["g_long"][tail:], color=theme.ACCENT, fade=True)])

"""The Live page: telemetry tiles and the last minute on charts."""
import time
from collections import deque

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import windows
from capture.live_source import LiveSource
from capture.raw_socket import default_ip, local_ips
from ui import charts, theme
from ui.widgets import Button, ChartGrid, Tile, card, label, legend_dot

LIVE_KEEP = 120  # seconds of live history kept in memory
LIVE_WINDOW = 60  # seconds shown on the live charts
LAT_COLOR, Z_COLOR, YAW_COLOR = "#3d8eff", "#3ad164", "#ff8c42"


def signed(v):
    return f"{v:+.2f}"


class LivePage(QWidget):
    driving = Signal(dict)   # each own sample while in a car, as the charts take it
    rivals = Signal(object)  # the other racers, passed on from the capture
    jumped = Signal()        # teleported: what came before is another place
    CHARTS = [("speed", "Speed"), ("g", "G-forces"), ("map", "Trajectory"), ("gg", "G-G diagram"),
              ("z", "Altitude"), ("yaw", "Yaw rate")]

    def __init__(self):
        super().__init__()
        self.live = deque()
        self.live_max = 0.0
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
        """The bar along the bottom of the window: whether data is coming in and how fast, and the
        Clear."""
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
        self.rate = label("", "muted")
        h.addWidget(self.rate)
        clr = Button("Clear", "eraser")
        clr.setToolTip("Clear the live charts")
        clr.clicked.connect(self.clear)
        h.addWidget(clr)
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
        self.source.start()
        self.tick()

    def stop(self):
        if self.source:
            self.source.sample.disconnect()
            self.source.rivals.disconnect()
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
        while self.live and d["w"] - self.live[0]["w"] > LIVE_KEEP:
            self.live.popleft()
        self.live_max = max(self.live_max, d["speed_kmh"])
        self.dirty = True
        self.driving.emit(d)

    def set_charts(self, keys):
        self.grid.set_order(keys)
        self.dirty = True

    def clear(self):
        self.live.clear()
        self.live_max = 0.0
        self.dirty = True

    def tick(self):
        ok = time.monotonic() - self.last_msg < 3
        color = (theme.ACCENT if not self.in_car else "#3ad164") if ok else theme.DANGER
        self.dot.setStyleSheet(f"background:{color}; border-radius:5px;")
        if ok and not self.in_car:
            text = f"On foot: paused until you get in a car ({self.source_desc})"
        elif ok:
            text = f"In a car, receiving data ({self.source_desc})"
        elif self.error:
            text = self.error
        else:
            text = f"No data: not in a car or no game traffic ({self.source_desc})"
        self.status.setText(text)
        now = time.monotonic()
        n = sum(1 for p in reversed(self.live) if now - p["w"] <= 1) if ok and self.in_car else 0
        self.rate.setText(f"{n} samples/s" if ok and self.in_car else "")
        self.dirty = True  # the charts' time axis moves even without new data

    # ----- rendering -----

    def render(self):
        if not self.dirty:
            return
        self.dirty = False
        d = self.live[-1] if self.live else None
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
        win = [p for p in self.live if now - p["w"] <= LIVE_WINDOW]
        col = lambda k: np.array([p[k] for p in win], float)
        tx = col("w") - now
        xr = (-LIVE_WINDOW, 0)
        self.c_speed.set_series([(tx, col("speed_kmh"), theme.ACCENT, 2.2)], xr)
        self.c_g.set_series([(tx, col("g_long"), theme.ACCENT, 1.8), (tx, col("g_lat"), LAT_COLOR, 1.8)], xr)
        self.c_z.set_series([(tx, col("z"), Z_COLOR, 1.8)], xr)
        self.c_yaw.set_series([(tx, col("yaw_rate"), YAW_COLOR, 1.8)], xr)
        allp = list(self.live)
        self.c_map.set_tracks(
            [dict(x=[p["x"] for p in allp], y=[p["y"] for p in allp], speeds=[p["speed_kmh"] for p in allp],
                  fade=0.3, fade_max=300)],
            [(d["x"], d["y"], theme.TEXT)] if d else [])
        tail = win[-150:]
        self.c_gg.set_sets([dict(ga=[p["g_lat"] for p in tail], gl=[p["g_long"] for p in tail],
                                 color=theme.ACCENT, fade=True)])

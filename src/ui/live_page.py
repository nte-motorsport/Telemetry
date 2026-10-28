"""The Live page: capture status, telemetry tiles and the last minute on charts."""
import time
from collections import deque

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QComboBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import windows
from capture.live_source import LiveSource
from capture.raw_socket import default_ip, local_ips
from ui import charts, theme
from ui.widgets import Button, Tile, card, chart_grid, label, legend_dot, panel, scroll

LIVE_KEEP = 120  # seconds of live history kept in memory
LIVE_WINDOW = 60  # seconds shown on the live charts
LAT_COLOR, Z_COLOR, YAW_COLOR = "#3d8eff", "#3ad164", "#ff8c42"


def signed(v):
    return f"{v:+.2f}"


class LivePage(QWidget):
    received = Signal(dict)  # every tracker sample, after the page has taken it in

    def __init__(self):
        super().__init__()
        self.live = deque()
        self.live_max = 0.0
        self.source = None
        self.source_desc = ""
        self.error = None
        self.last_msg = -1e9
        self.dirty = True

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(theme.GAP)
        v.addWidget(self.build_toolbar())

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
        grid = chart_grid([
            card("Speed, last 60 s", self.c_speed),
            card("G-forces", self.c_g, f"{legend_dot(theme.ACCENT)} longitudinal &nbsp; {legend_dot(LAT_COLOR)} lateral"),
            card("Trajectory", self.c_map, "colour = speed"),
            card("G-G diagram", self.c_gg, "↑ accel ↓ braking, ← → cornering"),
            card("Altitude, last 60 s", self.c_z),
            card("Yaw rate", self.c_yaw),
        ])
        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(theme.GAP)
        bv.addWidget(tiles)
        bv.addWidget(grid)
        bv.addStretch()
        v.addWidget(scroll(body), 1)

    def build_toolbar(self):
        tb, h = panel(QHBoxLayout)
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
        h.addWidget(label("Network", "muted"))
        self.iface = QComboBox()
        self.iface.setMinimumWidth(180)
        for ip in local_ips():
            self.iface.addItem(ip, ip)
        self.iface.setToolTip("Network interface that carries the game's traffic")
        self.iface.activated.connect(lambda _: self.start())
        h.addWidget(self.iface)
        clr = Button("Clear", "eraser")
        clr.clicked.connect(self.clear)
        h.addWidget(clr)
        return tb

    # ----- capture -----

    def start(self):
        ip = self.iface.currentData() or default_ip()
        self.stop()
        self.error = None
        self.admin_btn.hide()
        self.source, self.source_desc = LiveSource(ip), ip
        self.source.sample.connect(self.on_sample)
        self.source.failed.connect(self.on_failed)
        self.source.start()
        self.tick()

    def stop(self):
        if self.source:
            self.source.sample.disconnect()
            self.source.stop()
            self.source = None

    def on_failed(self, kind, msg):
        self.error = msg
        self.admin_btn.setVisible(kind == "admin")
        self.tick()

    def on_sample(self, d, wall=None):
        d["w"] = time.monotonic() if wall is None else wall
        self.last_msg = time.monotonic()
        self.live.append(d)
        while self.live and d["w"] - self.live[0]["w"] > LIVE_KEEP:
            self.live.popleft()
        self.live_max = max(self.live_max, d["speed_kmh"])
        self.dirty = True
        self.received.emit(d)

    def clear(self):
        self.live.clear()
        self.live_max = 0.0
        self.dirty = True

    def tick(self):
        ok = time.monotonic() - self.last_msg < 3
        color = "#3ad164" if ok else theme.DANGER
        self.dot.setStyleSheet(f"background:{color}; border-radius:5px;")
        if ok:
            text = f"Receiving data ({self.source_desc})"
        elif self.error:
            text = self.error
        else:
            text = f"No data: not in a car or no game traffic ({self.source_desc})"
        self.status.setText(text)
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
            [dict(x=[p["x"] for p in allp], y=[p["y"] for p in allp], speeds=[p["speed_kmh"] for p in allp])],
            [(d["x"], d["y"], theme.TEXT)] if d else [])
        tail = win[-150:]
        self.c_gg.set_sets([dict(ga=[p["g_lat"] for p in tail], gl=[p["g_long"] for p in tail],
                                 color=theme.ACCENT, fade=True)])

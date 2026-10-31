"""The Replays page: recorded online races, each on a map and a speed chart with a timeline to scrub."""
import datetime
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QSlider, QVBoxLayout, QWidget

from ui import charts, theme
from ui.multiplayer_page import WINDOW, rival_color, segments
from ui.widgets import Button, card, label, legend_dot, panel

STEPS = 10  # timeline positions per second


def clock(s):
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}"


class ReplaysPage(QWidget):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.cars = []  # (name, colour, array of [t, x, y, z, km/h]) of the open replay
        self.area = None  # (xs, ys) of every track of the open replay, the map is fitted to
        self.opened = False  # its file; None once drawn with no replay open, False before anything is drawn
        self.duration = 0.0
        self.pos = 0.0
        self.dirty = True
        self.playing = QTimer(self)
        self.playing.timeout.connect(self.step)

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(theme.GAP)

        lp, ll = panel()
        lp.setFixedWidth(300)
        ll.addWidget(label("Races", "sectionTitle"))
        self.empty = label("", "muted", wrap=True)
        ll.addWidget(self.empty)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.open_row)
        ll.addWidget(self.list, 1)
        self.del_btn = Button("Delete", "trash")
        self.del_btn.set_flag("danger", True)
        self.del_btn.clicked.connect(self.delete)
        ll.addWidget(self.del_btn)
        h.addWidget(lp)

        right = QVBoxLayout()
        right.setSpacing(theme.GAP)
        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.c_map = charts.MapChart()
        self.c_speed = charts.LineChart(clock, zero=True)
        self.cursor = pg.InfiniteLine(angle=90, pen=pg.mkPen(theme.TEXT, width=1, style=Qt.DashLine))
        self.cursor.setOpacity(0.6)
        self.c_speed.addItem(self.cursor, ignoreBounds=True)
        self.map_card = card("Map", self.c_map, " ")
        self.speed_card = card("Speed", self.c_speed, " ")
        row.addWidget(self.map_card, 1)
        row.addWidget(self.speed_card, 1)
        right.addLayout(row, 1)

        tp, tl = panel(QHBoxLayout)
        self.play_btn = Button("Play", "player-play", icon_only=True)
        self.play_btn.clicked.connect(self.toggle_play)
        tl.addWidget(self.play_btn)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(lambda v: self.seek(v / STEPS, from_slider=True))
        tl.addWidget(self.slider, 1)
        self.time = label("0:00 / 0:00", "muted")
        self.time.setMinimumWidth(90)
        self.time.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tl.addWidget(self.time)
        right.addWidget(tp)
        h.addLayout(right, 1)
        self.refresh()

    # ----- the list -----

    def refresh(self, select=None):
        """Reload the list; select is a replay file to open (default: keep the current one)."""
        keep = select or (self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None)
        self.list.blockSignals(True)
        self.list.clear()
        for path, m in self.store.list():
            when = datetime.datetime.fromisoformat(m["started"]).strftime("%d %b %H:%M")
            rivals = f'{m["rivals"]} rival' + ("" if m["rivals"] == 1 else "s")
            it = QListWidgetItem(f"{when}   ·   {clock(m['duration'])}   ·   {rivals}")
            it.setData(Qt.UserRole, path)
            self.list.addItem(it)
        self.list.blockSignals(False)
        n = self.list.count()
        self.empty.setText("" if n else "No races yet. Online races are recorded automatically "
                                        "(Settings → Recording).")
        self.empty.setVisible(not n)
        self.del_btn.setEnabled(bool(n))
        paths = [self.list.item(i).data(Qt.UserRole) for i in range(n)]
        row = paths.index(keep) if keep in paths else (0 if n else -1)
        self.list.blockSignals(True)
        self.list.setCurrentRow(row)
        self.list.blockSignals(False)
        if (paths[row] if row >= 0 else None) != self.opened:  # a new replay saved: leave the open one be
            self.open_row(row)

    def open_row(self, row):
        self.stop()
        it = self.list.item(row) if row >= 0 else None
        self.cars = []
        self.duration = 0.0
        self.opened = it.data(Qt.UserRole) if it else None
        if it:
            try:
                r = self.store.load(it.data(Qt.UserRole))
            except (OSError, ValueError, EOFError):
                r = None
            if r:
                self.duration = r["duration"]
                if r["me"]:
                    self.cars.append(("You", theme.ACCENT, np.array(r["me"], float)))
                for num, rows in sorted(r["rivals"].items(), key=lambda kv: int(kv[0])):
                    if rows:
                        a = np.array([[np.nan if v is None else v for v in row] for row in rows], float)
                        self.cars.append((f"Rival {num}", rival_color(int(num)), a))
        self.draw()

    def delete(self):
        it = self.list.currentItem()
        if it and QMessageBox.question(self, "Delete replay", f"Delete the race of {it.text().split('   ')[0]}?") \
                == QMessageBox.Yes:
            self.store.delete(it.data(Qt.UserRole))
            self.refresh()

    # ----- the replay -----

    def draw(self):
        """Everything that doesn't move with the timeline: the whole race's speeds and the map's view."""
        # the map is fitted to the whole race once; the tracks are drawn as the timeline moves (see seek)
        self.area = (np.concatenate([a[:, 1] for _, _, a in self.cars]),
                     np.concatenate([a[:, 2] for _, _, a in self.cars])) if self.cars else None
        # nothing open: a minute, so the axis doesn't read 0:00 four times
        self.c_speed.set_series([(a[:, 0], a[:, 4], c, 2.0 if n == "You" else 1.6) for n, c, a in self.cars],
                                (0, self.duration if self.cars and self.duration > 0 else 60.0))
        legend = " &nbsp; ".join(f"{legend_dot(c)} {n}" for n, c, _ in self.cars)
        for c in (self.map_card, self.speed_card):
            c.legend.setText(legend)
        self.slider.blockSignals(True)
        self.slider.setRange(0, int(self.duration * STEPS))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.slider.setEnabled(bool(self.cars))
        self.play_btn.setEnabled(bool(self.cars))
        self.seek(0.0)

    def seek(self, t, from_slider=False):
        self.pos = min(max(t, 0.0), self.duration)
        if not from_slider:
            self.slider.blockSignals(True)
            self.slider.setValue(int(self.pos * STEPS))
            self.slider.blockSignals(False)
        # as on the Multiplayer page: each car trails its last minute, fading out towards the oldest end
        tracks, markers = [], []
        for n, c, a in self.cars:
            i, j = np.searchsorted(a[:, 0], (self.pos - WINDOW, self.pos), "right")
            trail = a[i:j]
            if a[0, 0] <= self.pos <= a[-1, 0]:  # a car that hasn't joined yet or has left shows no dot
                now = np.array([[self.pos] + [np.interp(self.pos, a[:, 0], a[:, k]) for k in range(1, a.shape[1])]])
                trail = np.vstack([trail, now])
                markers.append((now[0, 1], now[0, 2], c))
            tracks += [dict(x=s[:, 1], y=s[:, 2], color=c, width=3 if n == "You" else 2, fade=0.6 if k == 0 else None)
                       for k, s in enumerate(segments(trail))]
        self.c_map.set_tracks(tracks, markers, self.area)
        self.cursor.setPos(self.pos)
        self.cursor.setVisible(bool(self.cars))
        self.time.setText(f"{clock(self.pos)} / {clock(self.duration)}")

    def toggle_play(self):
        if self.playing.isActive():
            self.stop()
            return
        if self.pos >= self.duration:
            self.seek(0.0)
        self.last = time.monotonic()
        self.playing.start(40)
        self.play_btn.set_icon("player-pause")
        self.play_btn.setToolTip("Pause")

    def stop(self):
        self.playing.stop()
        self.play_btn.set_icon("player-play")
        self.play_btn.setToolTip("Play")

    def step(self):
        now = time.monotonic()
        self.seek(self.pos + now - self.last)
        self.last = now
        if self.pos >= self.duration:
            self.stop()

    def render(self):
        pass

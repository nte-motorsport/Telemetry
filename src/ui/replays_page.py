"""The Replays page: recorded online races, each on a map and a speed chart with a timeline to scrub, and
everyone's speed at the timeline's position, where each car can be hidden."""
import datetime
import os
import subprocess
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QSizePolicy, QSlider,
                               QVBoxLayout, QWidget)

from ui import charts, theme
from ui.multiplayer_page import WINDOW, rival_color, segments
from ui.widgets import Button, card, label, panel

STEPS = 10  # timeline positions per second


def clock(s):
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}"


def row_height():
    """A list row: the date and the details line under it, race_row's margins, and the list item's padding and
    border (8 and 2 px) and the GAP under it (from the style sheet), which the row widget is placed inside."""
    return (QFontMetrics(theme.font(theme.FS_LG)).height() + QFontMetrics(theme.font(theme.FS_MD)).height() + 2
            + 2 * 4 + 2 * (8 + 2) + theme.GAP)


def race_row(when, details):
    """A row of the list: the date in the site font, the length and the field under it. Drawn over the list
    item, which keeps the hover and selection look; its labels turn dark on the selected (yellow) one."""
    w = QWidget()
    w.setProperty("role", "raceRow")
    w.setAttribute(Qt.WA_TransparentForMouseEvents)
    v = QVBoxLayout(w)
    v.setContentsMargins(6, 4, 6, 4)
    v.setSpacing(2)
    v.addWidget(label(when, "listTitle"))
    v.addWidget(label(details, "muted"))
    return w


class CarChip(QFrame):
    """One car under the charts: its colour and name, its speed at the timeline's position, and a button
    that hides it from the map and the speed chart."""

    def __init__(self, on_toggle):
        super().__init__()
        self.setProperty("role", "panel")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)  # side by side from the left, not spread out
        self.name = ""
        self.hidden = False
        h = QHBoxLayout(self)
        h.setContentsMargins(theme.GAP, theme.GAP, theme.GAP + 4, theme.GAP)
        h.setSpacing(theme.GAP)
        self.btn = Button("Hide", "eye", icon_only=True)
        self.btn.clicked.connect(lambda: on_toggle(self))
        h.addWidget(self.btn, 0, Qt.AlignVCenter)
        v = QVBoxLayout()
        v.setSpacing(0)
        self.title = label("", "muted")
        self.title.setTextFormat(Qt.RichText)
        v.addWidget(self.title)
        # one rich-text label, so the unit sits on the number's baseline
        self.value = label("", "chipValue")
        self.value.setTextFormat(Qt.RichText)
        v.addWidget(self.value)
        h.addLayout(v, 1)

    def set_car(self, name, color):
        """Show this car (chips are kept and given the next replay's cars, so switching replays doesn't
        rebuild the row and make it jump)."""
        self.name = name
        self.btn.set_tint(color)
        self.set_hidden(False)

    def set_hidden(self, on):
        self.hidden = on
        self.title.setText(self.name)
        self.btn.set_icon("eye-off" if on else "eye")
        self.btn.setToolTip(f"Show {self.name}" if on else f"Hide {self.name}")
        self.setProperty("off", on)
        for w in (self, self.value):
            w.style().unpolish(w)
            w.style().polish(w)

    def set_speed(self, v):
        num = "–" if v is None or not np.isfinite(v) else f"{v:.0f}"
        self.value.setText(f'{num}<span style="font-size:{theme.FS_MD}px; color:{theme.MUTED}">&nbsp;km/h</span>')

    def showEvent(self, ev):
        # room for three digits, in the font the style sheet gave it, so the chips don't jiggle
        unit = theme.font(theme.FS_MD)
        self.value.setMinimumWidth(self.value.fontMetrics().horizontalAdvance("888")
                                   + QFontMetrics(unit).horizontalAdvance(" km/h") + 4)
        super().showEvent(ev)


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
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.currentRowChanged.connect(self.mark_selected)
        self.list.currentRowChanged.connect(self.open_row)
        ll.addWidget(self.list, 1)
        btns = QHBoxLayout()
        btns.setSpacing(theme.GAP)
        folder_btn = Button("Open folder", "folder")
        folder_btn.setToolTip("Show the replay files in Explorer")
        folder_btn.clicked.connect(self.open_folder)
        btns.addWidget(folder_btn, 1)
        self.del_btn = Button("Delete", "trash")
        self.del_btn.set_flag("danger", True)
        self.del_btn.clicked.connect(self.delete)
        btns.addWidget(self.del_btn, 1)
        ll.addLayout(btns)
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
        self.map_card = card("Map", self.c_map)
        self.speed_card = card("Speed", self.c_speed)
        row.addWidget(self.map_card, 1)
        row.addWidget(self.speed_card, 1)
        right.addLayout(row, 1)

        self.pool = []   # every CarChip made so far, in the row's order
        self.chips = []  # those in use: one per car of the open replay, in the order of self.cars
        self.hidden = set()  # names of the cars hidden from the map and the chart
        # the cars' blocks stand on the page like panels, a GAP apart
        self.chip_row = QHBoxLayout()
        self.chip_row.setSpacing(theme.GAP)
        self.no_cars, nl = panel()
        nl.addWidget(label("Open a race to see everyone's speed here.", "muted"))
        self.chip_row.addWidget(self.no_cars, 1)
        self.chip_row.addStretch()
        right.addLayout(self.chip_row)

        tp, tl = panel(QHBoxLayout)
        self.play_btn = Button("Play", "player-play", icon_only=True)
        self.play_btn.clicked.connect(self.toggle_play)
        tl.addWidget(self.play_btn)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(lambda v: self.seek(v / STEPS, from_slider=True))
        tl.addWidget(self.slider, 1)
        self.time = label("0:00 / 0:00", "muted")
        self.time.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
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
            when = datetime.datetime.fromisoformat(m["started"]).strftime("%d %b %Y, %H:%M")
            rivals = f'{m["rivals"]} rival' + ("" if m["rivals"] == 1 else "s")
            it = QListWidgetItem()
            it.setData(Qt.UserRole, path)
            it.setData(Qt.UserRole + 1, when)
            w = race_row(when, f"{clock(m['duration'])}   ·   {rivals}")
            it.setSizeHint(QSize(0, row_height()))
            self.list.addItem(it)
            self.list.setItemWidget(it, w)
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
        self.mark_selected()
        if (paths[row] if row >= 0 else None) != self.opened:  # a new replay saved: leave the open one be
            self.open_row(row)

    def mark_selected(self, row=None):
        """Dark text on the selected row, whose background is the accent."""
        for i in range(self.list.count()):
            w = self.list.itemWidget(self.list.item(i))
            w.setProperty("sel", i == self.list.currentRow())
            for x in [w] + w.findChildren(QWidget):
                x.style().unpolish(x)
                x.style().polish(x)

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

    def open_folder(self):
        """Explorer at the replays, with the open one selected."""
        it = self.list.currentItem()
        path = it.data(Qt.UserRole) if it else None
        if path and os.path.exists(path):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        else:
            os.startfile(self.store.dir)

    def delete(self):
        it = self.list.currentItem()
        if it and QMessageBox.question(self, "Delete replay", f"Delete the race of {it.data(Qt.UserRole + 1)}?") \
                == QMessageBox.Yes:
            self.store.delete(it.data(Qt.UserRole))
            self.refresh()

    # ----- the replay -----

    def draw(self):
        """Everything that doesn't move with the timeline: the whole race's speeds and the map's view."""
        # the map is fitted to the whole race once; the tracks are drawn as the timeline moves (see seek)
        # (hiding a car leaves that view as it is)
        self.area = (np.concatenate([a[:, 1] for _, _, a in self.cars]),
                     np.concatenate([a[:, 2] for _, _, a in self.cars])) if self.cars else None
        self.hidden.clear()
        while len(self.pool) < len(self.cars):
            chip = CarChip(self.toggle_car)
            self.chip_row.insertWidget(len(self.pool), chip)
            self.pool.append(chip)
        self.chips = self.pool[:len(self.cars)]
        for chip, (n, c, _) in zip(self.chips, self.cars):
            chip.set_car(n, c)
        for i, chip in enumerate(self.pool):
            chip.setVisible(i < len(self.cars))
        self.no_cars.setVisible(not self.chips)
        self.plot()
        self.slider.blockSignals(True)
        self.slider.setRange(0, int(self.duration * STEPS))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.slider.setEnabled(bool(self.cars))
        # as wide as the longest time it will show, so the slider doesn't move as the text changes
        longest = f"{clock(self.duration)} / {clock(self.duration)}".replace("1", "8")
        self.time.setFixedWidth(self.time.fontMetrics().horizontalAdvance(longest))
        self.play_btn.setEnabled(bool(self.cars))
        self.seek(0.0)

    def plot(self):
        """The speed chart, of the cars not hidden."""
        shown = [(n, c, a) for n, c, a in self.cars if n not in self.hidden]
        # nothing open: a minute, so the axis doesn't read 0:00 four times
        self.c_speed.set_series([(a[:, 0], a[:, 4], c, 2.0 if n == "You" else 1.6) for n, c, a in shown],
                                (0, self.duration if self.cars and self.duration > 0 else 60.0))

    def toggle_car(self, chip):
        self.hidden ^= {chip.name}
        chip.set_hidden(chip.name in self.hidden)
        self.plot()
        self.seek(self.pos)

    def seek(self, t, from_slider=False):
        self.pos = min(max(t, 0.0), self.duration)
        if not from_slider:
            self.slider.blockSignals(True)
            self.slider.setValue(int(self.pos * STEPS))
            self.slider.blockSignals(False)
        # as on the Multiplayer page: each car trails its last minute, fading out towards the oldest end
        tracks, markers = [], []
        for (n, c, a), chip in zip(self.cars, self.chips):
            here = a[0, 0] <= self.pos <= a[-1, 0]  # a car that hasn't joined yet or has left shows no dot
            now = np.array([[self.pos] + [np.interp(self.pos, a[:, 0], a[:, k]) for k in range(1, a.shape[1])]])
            chip.set_speed(now[0, 4] if here else None)
            if n in self.hidden:
                continue
            i, j = np.searchsorted(a[:, 0], (self.pos - WINDOW, self.pos), "right")
            trail = a[i:j]
            if here:
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

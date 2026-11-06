"""The Replays page: recorded online races, each on a map and a speed chart with a timeline to scrub, and
everyone's name, car and speed at the timeline's position, where each car can be hidden."""
import datetime
import html
import os
import subprocess
import time

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMessageBox, QSizePolicy, QSlider, QVBoxLayout, QWidget

from ui import charts, theme
from ui.multiplayer_page import WINDOW, rival_color, segments
from ui.vehicles import car_name
from ui.widgets import Button, RowList, card, label, panel, shown_name
from ui.world_map import MapPicker, all_maps

STEPS = 10  # timeline positions per second
NUDGE = 0.1  # s the arrow keys step the timeline by


def clock(s):
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}"


class CarChip(QFrame):
    """One car under the charts: its colour, its driver's name and the car (when the replay has the race's
    entrants), its speed at the timeline's position, and a button that hides it from the map and the speed
    chart."""

    def __init__(self, on_toggle):
        super().__init__()
        self.setProperty("role", "panel")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)  # side by side from the left, not spread out
        self.name = ""
        self.shown = ""  # the name as written: a bot's between colons (widgets.shown_name)
        self.about = ""  # what is written after the name: the car
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

    def set_car(self, name, color, about="", shown=None):
        """Show this car (chips are kept and given the next replay's cars, so switching replays doesn't
        rebuild the row and make it jump). name: the key it is hidden under; shown: as written, if not name."""
        self.name = name
        self.shown = shown or name
        self.about = about
        self.btn.set_tint(color)
        self.set_hidden(False)

    def set_hidden(self, on):
        self.hidden = on
        sep = "&nbsp;&nbsp;·&nbsp;&nbsp;"
        about = sep + sep.join(html.escape(part) for part in self.about.split(" · ")) if self.about else ""
        self.title.setText(f'<span style="color:{theme.MUTED if on else theme.TEXT}">{html.escape(self.shown)}</span>'
                           f'{about}')
        self.btn.set_icon("eye-off" if on else "eye")
        self.btn.setToolTip(f"Show {self.shown}" if on else f"Hide {self.shown}")
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
        self.held = False  # playing, but held while the slider is dragged

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(theme.GAP)

        lp, ll = panel()
        lp.setFixedWidth(300)
        ll.addWidget(label("Races", "sectionTitle"))
        self.empty = label("", "muted", wrap=True)
        ll.addWidget(self.empty)
        self.list = RowList()
        self.list.currentRowChanged.connect(self.open_row)
        ll.addWidget(self.list, 1)
        btns = QHBoxLayout()
        btns.setSpacing(theme.GAP)
        folder_btn = Button("Folder", "folder")
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
        self.c_map = charts.MapChart(interactive=True)
        self.maps = MapPicker(all_maps())  # the game map under the tracks, see draw
        self.level = ""  # the open replay's world, if it was recorded
        self.c_speed = charts.LineChart(clock, zero=True, xzoom=5.0, hover=lambda v: f"{v:.0f} km/h")
        self.c_speed.clicked.connect(lambda t: self.cars and self.seek(t))  # a click on the chart moves the timeline
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
        self.me = ""  # the player's name, written over their own marker
        self.field = []  # the open replay's entrants, when it has them (recorded since 2026-11-04)
        self.bots = set()  # names (as in self.cars) of the open replay's cars that bots drive

        tp, tl = panel(QHBoxLayout)
        self.play_btn = Button("Play", "player-play", icon_only=True)
        self.play_btn.setToolTip("Play (Space)")
        self.play_btn.clicked.connect(self.toggle_play)
        tl.addWidget(self.play_btn)
        # keys for the replay, whatever has the focus on this page (shortcuts of a hidden page don't fire)
        for key, act in ((Qt.Key_Space, self.toggle_play), (Qt.Key_Left, lambda: self.nudge(-NUDGE)),
                         (Qt.Key_Right, lambda: self.nudge(NUDGE))):
            QShortcut(QKeySequence(key), self, act)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(lambda v: self.seek(v / STEPS, from_slider=True))
        # playing holds while the slider is dragged and goes on from where it is let go
        self.slider.sliderPressed.connect(self.hold)
        self.slider.sliderReleased.connect(self.resume)
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
            raw = "   ·   raw traffic" if m.get("raw") else ""
            it = self.list.add_row(when, f"{clock(m['duration'])}   ·   {rivals}{raw}", path)
            it.setData(Qt.UserRole + 1, when)
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
        self.list.mark_selected()
        if (paths[row] if row >= 0 else None) != self.opened:  # a new replay saved: leave the open one be
            self.open_row(row)

    def open_row(self, row):
        self.stop()
        it = self.list.item(row) if row >= 0 else None
        self.cars = []
        self.bots = set()
        self.duration = 0.0
        self.level = ""
        self.field = []
        self.opened = it.data(Qt.UserRole) if it else None
        if it:
            try:
                r = self.store.load(it.data(Qt.UserRole))
            except (OSError, ValueError, EOFError):
                r = None
            if r:
                self.duration = r["duration"]
                self.level = r.get("level") or ""
                self.field = r.get("field") or []
                bots = set(r.get("bots") or [])
                names = r.get("names") or {}
                field_bots = {e["name"] for e in self.field if e.get("bot")}
                if r["me"]:
                    self.cars.append(("You", theme.ACCENT, np.array(r["me"], float)))
                for num, rows in sorted(r["rivals"].items(), key=lambda kv: int(kv[0])):
                    if rows:
                        a = np.array([[np.nan if v is None else v for v in row] for row in rows], float)
                        who = names.get(num) or f"Rival {num}"
                        if num in bots or who in field_bots:
                            self.bots.add(who)
                        self.cars.append((who, rival_color(int(num)), a))
        self.draw()

    def set_me(self, name):
        self.me = name or ""
        if self.cars:
            for chip, (n, c, _) in zip(self.chips, self.cars):
                chip.set_car(n, c, self.about(n), "You" if n == "You" else self.label(n))
                chip.set_hidden(n in self.hidden)
            self.seek(self.pos)

    def about(self, name):
        """What the open replay's entrants say of the car under name: its model."""
        who = self.me if name == "You" else name
        e = next((e for e in self.field if e["name"] == who), None)
        return car_name(e["car"]) if e else ""

    def label(self, name):
        """The name of the car under name as written on its chip and over its marker on the map."""
        return (self.me or "You") if name == "You" else shown_name(name, name in self.bots)

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
        self.c_map.user_view = False  # a new race: fitted to it, whatever the last one was zoomed to
        self.pick_map()
        self.c_speed.user_x = None
        while len(self.pool) < len(self.cars):
            chip = CarChip(self.toggle_car)
            self.chip_row.insertWidget(len(self.pool), chip)
            self.pool.append(chip)
        self.chips = self.pool[:len(self.cars)]
        for chip, (n, c, _) in zip(self.chips, self.cars):
            chip.set_car(n, c, self.about(n), "You" if n == "You" else self.label(n))
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

    def pick_map(self):
        """The open replay's game map: the recorded world's; for a replay from before worlds were recorded,
        the one whose roads the player's own drive lies on. Again when the map packs change."""
        self.maps.set_level(self.level)
        own = next((a for n, _, a in self.cars if n == "You"), None)
        if own is not None:
            self.maps.update(own[:, 1], own[:, 2])
        self.c_map.set_backdrop(self.maps.current)
        self.seek(self.pos)  # draw it


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
        # as on the Multiplayer page: each car trails its last minute
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
                markers.append((now[0, 1], now[0, 2], c, self.label(n)))
            tracks += [dict(x=s[:, 1], y=s[:, 2], color=c, width=3 if n == "You" else 2)
                       for s in segments(trail)]
        self.c_map.set_tracks(tracks, markers, self.area)
        self.cursor.setPos(self.pos)
        self.cursor.setVisible(bool(self.cars))
        self.time.setText(f"{clock(self.pos)} / {clock(self.duration)}")

    def nudge(self, dt):
        """Step the timeline by dt seconds (the arrow keys), playing or not."""
        if self.cars:
            self.seek(self.pos + dt)
            self.c_speed.follow(self.pos)  # a zoomed chart keeps the position in view

    def toggle_play(self):
        if not self.cars:  # Space with no replay open
            return
        if self.playing.isActive():
            self.stop()
            return
        if self.pos >= self.duration:
            self.seek(0.0)
        self.last = time.monotonic()
        self.playing.start(40)
        self.play_btn.set_icon("player-pause")
        self.play_btn.setToolTip("Pause (Space)")

    def hold(self):
        if self.playing.isActive():
            self.playing.stop()  # the button still reads Pause: it is still playing, only held
            self.held = True

    def resume(self):
        if not self.held:
            return
        self.held = False
        if self.pos >= self.duration:  # let go at the end
            self.stop()
            return
        self.last = time.monotonic()
        self.playing.start(40)

    def stop(self):
        self.playing.stop()
        self.held = False
        self.play_btn.set_icon("player-play")
        self.play_btn.setToolTip("Play (Space)")

    def step(self):
        now = time.monotonic()
        self.seek(self.pos + now - self.last)
        self.c_speed.follow(self.pos)
        self.last = now
        if self.pos >= self.duration:
            self.stop()

    def render(self):
        pass

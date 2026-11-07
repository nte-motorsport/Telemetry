"""The main window: the site-style navbar, the Live / Multiplayer / Replays / Settings pages and race recording."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QVBoxLayout

from replays.recorder import RaceRecorder
from replays.store import ReplayStore
from ui import theme, units
from ui.live_page import LivePage
from ui.multiplayer_page import MultiplayerPage
from ui.prefs import Prefs
from ui.replays_page import ReplaysPage
from ui.settings_page import SettingsPage
from ui.tracks import tracks
from ui.vehicles import vehicles
from ui.widgets import Backdrop, Button

LIVE, MULTIPLAYER, REPLAYS, SETTINGS = 0, 1, 2, 3


class MainWindow(QMainWindow):
    def __init__(self, autostart=True, prefs=None, replays=None):
        super().__init__()
        self.setWindowTitle("NTE Telemetry")
        self.setWindowIcon(QIcon(theme.asset("app.ico")))
        self.resize(1440, 920)
        self.setMinimumSize(1100, 700)

        root = Backdrop()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(theme.GAP)
        v.addWidget(self.build_navbar())

        self.live = LivePage()
        self.multiplayer = MultiplayerPage()
        self.live.driving.connect(self.multiplayer.on_own)
        self.live.rivals.connect(self.multiplayer.on_rivals)
        self.live.jumped.connect(self.multiplayer.clear)
        self.live.world.connect(self.multiplayer.set_world)
        self.live.field.connect(self.multiplayer.set_field)
        self.live.names.connect(self.multiplayer.set_names)
        self.live.player.connect(self.on_player)
        self.prefs = prefs or Prefs({"live": [k for k, _ in LivePage.CHARTS]})
        self.live.set_charts(self.prefs.shown("live"))
        units.set_speed_unit(self.prefs.option("speed_unit"))
        self.live.set_units()
        self.prefs.changed.connect(self.on_prefs)

        store = replays or ReplayStore()
        self.recorder = RaceRecorder(store, self.prefs.option("auto_record"), self.prefs.option("raw_traffic"))
        self.recorder.tap.connect(self.live.set_tap)
        self.live.set_raw(self.raw_wanted())
        self.live.driving.connect(self.recorder.on_own)
        self.live.rivals.connect(self.recorder.on_rivals)
        self.live.jumped.connect(self.recorder.finish)  # a new race or a test drive
        self.live.world.connect(self.recorder.set_world)
        self.live.field.connect(self.recorder.set_field)
        self.live.track.connect(self.recorder.set_track)
        self.live.names.connect(self.recorder.set_names)
        self.recorder.recording.connect(self.live.set_recording)
        self.replays = ReplaysPage(store)
        self.recorder.saved.connect(lambda path: self.replays.refresh())

        self.settings = SettingsPage(self.prefs, [("live", "Live", LivePage.CHARTS)], store)
        self.set_me()
        self.settings.maps_changed.connect(self.replays.pick_map)  # Live and Multiplayer look every few seconds
        # car names from the NTE Motorsport database, fetched anew at each start (ui/vehicles.py)
        vehicles().changed.connect(lambda: self.replays.set_me(self.replays.me))
        vehicles().changed.connect(lambda: self.multiplayer.racers.set_entrants(self.multiplayer.racers.entrants))
        vehicles().refresh()
        tracks().changed.connect(lambda: self.replays.refresh())  # track names, the same way (ui/tracks.py)
        tracks().refresh()
        self.pages = QStackedWidget()
        for p in (self.live, self.multiplayer, self.replays, self.settings):
            self.pages.addWidget(p)
        content = QVBoxLayout()
        content.setContentsMargins(theme.GAP, 0, theme.GAP, 0)
        content.addWidget(self.pages)
        v.addLayout(content, 1)
        v.addWidget(self.live.statusbar)
        self.switch(LIVE)

        t = QTimer(self)
        # at most 20 frames a second: the game sends a car's position 10-15 times a second, so more would only
        # redraw the same data shifted along the time axis; nothing is drawn while the window is minimized
        t.timeout.connect(lambda: self.isMinimized() or self.pages.currentWidget().render())
        t.start(50)
        t2 = QTimer(self)
        t2.timeout.connect(self.live.tick)
        t2.timeout.connect(self.multiplayer.tick)
        t2.timeout.connect(self.recorder.tick)
        t2.start(250)

        # full screen: F11 or Alt+Enter toggle it, Esc leaves it
        for keys in ("F11", "Alt+Return", "Alt+Enter"):
            QShortcut(QKeySequence(keys), self, self.toggle_full_screen)
        QShortcut(QKeySequence("Esc"), self, lambda: self.isFullScreen() and self.toggle_full_screen())
        self.was_maximized = False

        self.live.ip = self.prefs.option("network")
        if autostart:
            self.live.start()

    def build_navbar(self):
        bar = QFrame()
        bar.setObjectName("navbar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, theme.GAP, 0)
        h.setSpacing(theme.GAP)
        logo = QLabel()
        pm = QPixmap(theme.asset("logo.png"))
        dpr = self.devicePixelRatioF()
        pm = pm.scaled(int(86 * dpr), int(86 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        logo.setPixmap(pm)
        logo.setFixedSize(86, 86)
        h.addWidget(logo)
        title = QVBoxLayout()
        title.setSpacing(0)
        title.addStretch()
        t = QLabel("NTE Motorsport")
        t.setObjectName("siteTitle")
        e = QLabel("Telemetry")
        e.setObjectName("eyebrow")
        title.addWidget(t)
        title.addWidget(e)
        title.addStretch()
        h.addLayout(title)
        h.addStretch()

        self.tab_live = Button("Live", "chart-line", checkable=True)
        self.tab_mp = Button("Multiplayer", "users", checkable=True)
        self.tab_rep = Button("Replays", "history", checkable=True)
        self.tab_set = Button("Settings", "settings", checkable=True)
        self.tabs = (self.tab_live, self.tab_mp, self.tab_rep, self.tab_set)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for i, b in enumerate(self.tabs):
            group.addButton(b, i)
            h.addWidget(b)
        group.idClicked.connect(self.switch)
        return bar

    def switch(self, i):
        self.pages.setCurrentIndex(i)
        self.tabs[i].setChecked(True)
        self.pages.currentWidget().dirty = True

    def toggle_full_screen(self):
        if self.isFullScreen():
            self.showMaximized() if self.was_maximized else self.showNormal()
        else:
            self.was_maximized = self.isMaximized()  # come back to the same state
            self.showFullScreen()

    def on_prefs(self, key):
        if key == "options":
            self.recorder.set_enabled(self.prefs.option("auto_record"))
            self.recorder.set_raw(self.prefs.option("raw_traffic"))
            self.live.set_raw(self.raw_wanted())
            self.set_me()
            self.set_units()
            if self.prefs.option("network") != self.live.ip:
                self.live.start(self.prefs.option("network"))
        else:
            self.live.set_charts(self.prefs.shown(key))

    def on_player(self, name, account):
        """The game named the player: kept, so it is known from the start next time (a race joined before the
        server sends it)."""
        if (name, account) != (self.prefs.option("my_name"), self.prefs.option("my_id")):
            self.prefs.options["my_name"] = name  # one change, one save, one "options" signal
            self.prefs.set_option("my_id", account)

    def set_units(self):
        """Speeds in the unit chosen in Settings, if it changed."""
        if units.set_speed_unit(self.prefs.option("speed_unit")):
            self.live.set_units()
            self.multiplayer.dirty = True
            self.replays.set_units()

    def set_me(self):
        """The player's name, to mark them among the entrants."""
        for page in (self.live, self.multiplayer, self.replays):
            page.set_me(self.prefs.option("my_name"))

    def raw_wanted(self):
        """Raw traffic is kept for races to be recorded with: only while both are on."""
        return self.prefs.option("auto_record") and self.prefs.option("raw_traffic")

    def closeEvent(self, ev):
        self.live.stop()
        self.recorder.finish()  # keep a race that is still going
        super().closeEvent(ev)

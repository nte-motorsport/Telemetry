"""The main window: the site-style navbar and the Live / Multiplayer / Settings pages."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QVBoxLayout

from ui import theme
from ui.chart_layout import ChartLayout
from ui.live_page import LivePage
from ui.multiplayer_page import MultiplayerPage
from ui.settings_page import SettingsPage
from ui.widgets import Backdrop, Button

LIVE, MULTIPLAYER, SETTINGS = 0, 1, 2


class MainWindow(QMainWindow):
    def __init__(self, autostart=True, prefs=None):
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
        self.prefs = prefs or ChartLayout({"live": [k for k, _ in LivePage.CHARTS]})
        self.live.set_charts(self.prefs.shown("live"))
        self.prefs.changed.connect(lambda key: self.live.set_charts(self.prefs.shown(key)))
        self.settings = SettingsPage(self.prefs, [("live", "Live", LivePage.CHARTS)])
        self.pages = QStackedWidget()
        for p in (self.live, self.multiplayer, self.settings):
            self.pages.addWidget(p)
        content = QVBoxLayout()
        content.setContentsMargins(theme.GAP, 0, theme.GAP, 0)
        content.addWidget(self.pages)
        v.addLayout(content, 1)
        v.addWidget(self.live.statusbar)
        self.switch(LIVE)

        t = QTimer(self)
        t.timeout.connect(lambda: self.pages.currentWidget().render())
        t.start(33)
        t2 = QTimer(self)
        t2.timeout.connect(self.live.tick)
        t2.timeout.connect(self.multiplayer.tick)
        t2.start(250)

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
        self.tab_set = Button("Settings", "settings", checkable=True)
        self.tabs = (self.tab_live, self.tab_mp, self.tab_set)
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

    def closeEvent(self, ev):
        self.live.stop()
        super().closeEvent(ev)

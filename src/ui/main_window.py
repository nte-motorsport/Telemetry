"""The main window: the site-style navbar, the Live / Compare pages and run recording."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QVBoxLayout

from runs.model import Recorder
from runs.store import RunStore
from ui import theme
from ui.compare_page import ComparePage
from ui.live_page import LivePage
from ui.widgets import Backdrop, Button

LIVE, COMPARE = 0, 1


class MainWindow(QMainWindow):
    def __init__(self, store=None, autostart=True):
        super().__init__()
        self.setWindowTitle("NTE Telemetry")
        self.setWindowIcon(QIcon(theme.asset("app.ico")))
        self.resize(1440, 920)
        self.setMinimumSize(1100, 700)
        self.recorder = None

        root = Backdrop()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(theme.GAP)
        v.addWidget(self.build_navbar())

        self.live = LivePage()
        self.live.received.connect(self.on_sample)
        self.compare = ComparePage(store or RunStore(theme.COLORS))
        self.compare.runs_changed.connect(self.on_runs_changed)
        self.on_runs_changed(len(self.compare.store.runs))
        self.pages = QStackedWidget()
        self.pages.addWidget(self.live)
        self.pages.addWidget(self.compare)
        content = QVBoxLayout()
        content.setContentsMargins(theme.GAP, 0, theme.GAP, theme.GAP)
        content.addWidget(self.pages)
        v.addLayout(content, 1)
        self.switch(LIVE)

        t = QTimer(self)
        t.timeout.connect(lambda: self.pages.currentWidget().render())
        t.start(33)
        t2 = QTimer(self)
        t2.timeout.connect(self.live.tick)
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
        self.tab_cmp = Button("Compare", "arrows-diff", checkable=True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for i, b in enumerate((self.tab_live, self.tab_cmp)):
            group.addButton(b, i)
            h.addWidget(b)
        group.idClicked.connect(self.switch)

        self.rec_btn = Button("Record run", "player-record")
        self.rec_btn.clicked.connect(self.toggle_record)
        h.addWidget(self.rec_btn)
        imp = Button("Import CSV", "file-import")
        imp.clicked.connect(lambda: self.compare.import_csv() and self.switch(COMPARE))
        h.addWidget(imp)
        return bar

    def switch(self, i):
        self.pages.setCurrentIndex(i)
        (self.tab_live if i == LIVE else self.tab_cmp).setChecked(True)
        self.pages.currentWidget().dirty = True

    def on_runs_changed(self, n):
        self.tab_cmp.setText(f"Compare ({n})" if n else "Compare")

    # ----- recording -----

    def on_sample(self, d):
        if self.recorder:
            self.recorder.add(d)
            self.rec_btn.setText(f"Stop · {self.recorder.time:.1f} s · {self.recorder.dist / 1000:.2f} km")

    def toggle_record(self):
        if self.recorder is None:
            self.recorder = Recorder()
            self.rec_btn.set_flag("danger", True)
            self.rec_btn.set_icon("player-stop")
            self.rec_btn.setText("Stop")
        else:
            if len(self.recorder.pts) > 5:
                self.compare.add_run(f"Run {len(self.compare.store.runs) + 1}", self.recorder.pts)
            self.recorder = None
            self.rec_btn.set_flag("danger", False)
            self.rec_btn.set_icon("player-record")
            self.rec_btn.setText("Record run")

    def closeEvent(self, ev):
        self.live.stop()
        super().closeEvent(ev)

"""The Settings page: the network to capture on, race recording, the map packs, and which charts the Live
page shows in what order."""
import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from capture.raw_socket import local_ips
from ui import theme, world_map
from ui.widgets import Button, label, panel, scroll


class SettingsPage(QWidget):
    maps_changed = Signal()  # a map pack was installed, or the maps folder looked at again

    def __init__(self, prefs, sections):
        """sections: [(page key, title, [(chart key, chart title)])]"""
        super().__init__()
        self.prefs = prefs
        self.dirty = True
        self.lists = {}
        self.titles = {}

        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(theme.GAP)
        cap, cl = panel()
        cl.addWidget(label("Capture", "sectionTitle"))
        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        row.addWidget(label("Network", "muted"))
        self.network = QComboBox()
        self.network.setMinimumWidth(220)
        ips = local_ips()  # the default-route one first
        saved = prefs.option("network")
        for ip in ips + ([saved] if saved and saved not in ips else []):
            self.network.addItem(ip if ip in ips else f"{ip} (not connected)", ip)
        self.network.setCurrentIndex(max(self.network.findData(saved), 0) if saved else 0)
        self.network.activated.connect(lambda _: self.prefs.set_option("network", self.network.currentData()))
        row.addWidget(self.network)
        row.addStretch()
        cl.addLayout(row)
        cl.addWidget(label("The network interface that carries the game's traffic. The one with the internet "
                           "connection is first, and it is the right one unless a VPN or a second network card "
                           "is in use.", "muted", wrap=True))
        v.addWidget(cap)
        rec, rl = panel()
        rl.addWidget(label("Recording", "sectionTitle"))
        self.auto_record = QCheckBox("Record online races automatically")
        self.auto_record.setChecked(prefs.option("auto_record"))
        self.auto_record.toggled.connect(lambda on: self.prefs.set_option("auto_record", on))
        rl.addWidget(self.auto_record)
        rl.addWidget(label("A race is recorded from when the other racers' data starts coming in until it stops, "
                           "and can then be watched on the Replays page.", "muted", wrap=True))
        v.addWidget(rec)
        v.addWidget(self.build_maps())
        hint, hl = panel()
        hl.addWidget(label("Choose which charts the Live page shows and in what order. They fill the "
                           "window left to right, top to bottom: up to 3 in a row, up to 8 in two rows.", "muted",
                           wrap=True))
        v.addWidget(hint)

        cols = QHBoxLayout()
        cols.setSpacing(theme.GAP)
        for page, title, charts in sections:
            self.titles[page] = dict(charts)
            p, pl = panel()
            head = QHBoxLayout()
            head.addWidget(label(title, "sectionTitle"))
            head.addStretch()
            rst = Button("Reset", "restore")
            rst.clicked.connect(lambda _=False, page=page: self.prefs.reset(page))
            head.addWidget(rst)
            pl.addLayout(head)
            rows = QVBoxLayout()
            rows.setSpacing(theme.GAP)
            pl.addLayout(rows)
            pl.addStretch()
            self.lists[page] = rows
            cols.addWidget(p, 1)
            self.fill(page)
        v.addLayout(cols)
        v.addStretch()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll(body))
        prefs.changed.connect(self.fill)

    # ----- map packs -----

    def build_maps(self):
        p, pl = panel()
        head = QHBoxLayout()
        head.setSpacing(theme.GAP)
        head.addWidget(label("Maps", "sectionTitle"))
        head.addStretch()
        add = Button("Install map pack", "folder")
        add.setToolTip("Copy a .ntemap file into the maps folder")
        add.clicked.connect(self.install_map)
        head.addWidget(add)
        folder = Button("Open folder", "folder")
        folder.setToolTip("Show the maps folder in Explorer")
        folder.clicked.connect(lambda: os.startfile(world_map.maps_dir()))
        head.addWidget(folder)
        again = Button("Rescan", "restore")
        again.setToolTip("Look at the maps folder again, after adding or removing packs by hand")
        again.clicked.connect(self.rescan_maps)
        head.addWidget(again)
        pl.addLayout(head)
        self.map_rows = QVBoxLayout()
        self.map_rows.setSpacing(4)
        pl.addLayout(self.map_rows)
        pl.addWidget(label("Map packs (.ntemap) put the game's map under the tracks. Each says which game world "
                           "it is the map of, and the one of the world you are in is shown. They are kept in "
                           f"{world_map.maps_dir()}.", "muted", wrap=True))
        self.fill_maps()
        return p

    def fill_maps(self):
        while self.map_rows.count():
            self.map_rows.takeAt(0).widget().deleteLater()
        maps = world_map.all_maps()
        if not maps:
            self.map_rows.addWidget(label("No map packs installed.", "muted"))
        for m in maps:
            world = m.level.rsplit("/", 1)[-1] if m.level else "no world given: told by its roads"
            size = os.path.getsize(m.pack.path) / 1e6 if os.path.isfile(m.pack.path) else None
            self.map_rows.addWidget(label(f"{m.name}  ·  {world}" + (f"  ·  {size:.0f} MB" if size else ""), "muted"))

    def install_map(self):
        path, _ = QFileDialog.getOpenFileName(self, "Install map pack", "", f"Map packs (*{world_map.EXT})")
        if not path:
            return
        try:
            m = world_map.install(path)
        except OSError as e:
            QMessageBox.warning(self, "Install map pack", f"Could not copy the map pack: {e}")
            m = False
        if m is None:
            QMessageBox.warning(self, "Install map pack", f"{os.path.basename(path)} is not a map pack.")
        self.fill_maps()
        self.maps_changed.emit()

    def rescan_maps(self):
        world_map.rescan()
        self.fill_maps()
        self.maps_changed.emit()

    def fill(self, page):
        if page not in self.lists:  # an option, not a page's charts
            return
        lay = self.lists[page]
        while lay.count():
            lay.takeAt(0).widget().deleteLater()
        rows = self.prefs.rows(page)
        for i, (key, on) in enumerate(rows):
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(theme.GAP)
            cb = QCheckBox(self.titles[page][key])
            cb.setChecked(on)
            cb.toggled.connect(lambda on, key=key: self.prefs.set_visible(page, key, on))
            h.addWidget(cb, 1)
            up = Button("Move up", "chevron-up", icon_only=True)
            up.setEnabled(i > 0)
            up.clicked.connect(lambda _=False, i=i: self.prefs.move(page, i, -1))
            dn = Button("Move down", "chevron-down", icon_only=True)
            dn.setEnabled(i < len(rows) - 1)
            dn.clicked.connect(lambda _=False, i=i: self.prefs.move(page, i, 1))
            h.addWidget(up)
            h.addWidget(dn)
            lay.addWidget(w)

    def render(self):
        pass

"""The Settings page: a list of sections on the left, as the Replays page's races, and the chosen one beside it.
Display: which charts the Live page shows and in what order. Network: the interface to capture on. Recording:
online races. Plugins: the map packs."""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QMessageBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from capture.raw_socket import local_ips
from ui import theme, world_map
from ui.widgets import Button, RowList, label, panel, scroll


def section_page(title, *intro):
    """A section's page: its title, the lines under it, and room for the rest (the layout returned)."""
    body = QWidget()
    v = QVBoxLayout(body)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(theme.GAP)
    p, pl = panel()
    pl.addWidget(label(title, "sectionTitle"))
    for text in intro:
        pl.addWidget(label(text, "muted", wrap=True))
    v.addWidget(p)
    return body, v, pl


class SettingsPage(QWidget):
    maps_changed = Signal()  # a map pack was installed, or the maps folder looked at again

    def __init__(self, prefs, sections):
        """sections: [(page key, title, [(chart key, chart title)])], the pages whose charts Display sets"""
        super().__init__()
        self.prefs = prefs
        self.dirty = True
        self.lists = {}
        self.titles = {}

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(theme.GAP)
        lp, ll = panel()
        lp.setFixedWidth(300)
        ll.addWidget(label("Settings", "sectionTitle"))
        self.nav = RowList()
        ll.addWidget(self.nav, 1)
        h.addWidget(lp)
        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)

        pages = [("Display", "The charts on the Live page", self.build_display(sections)),
                 ("Network", "Where the game's traffic is read", self.build_network()),
                 ("Recording", "Online races", self.build_recording()),
                 ("Plugins", "", self.build_plugins())]
        for title, details, page in pages:
            self.nav.add_row(title, details)
            self.stack.addWidget(scroll(page))
        self.plugins_row = len(pages) - 1
        self.update_plugins_row()
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        prefs.changed.connect(self.fill)

    # ----- Display -----

    def build_display(self, sections):
        body, v, _ = section_page("Display", "Choose which charts each page shows and in what order. They fill the "
                                             "window left to right, top to bottom: up to 3 in a row, up to 8 in two "
                                             "rows.")
        for page, title, charts in sections:
            self.titles[page] = dict(charts)
            p, pl = panel()
            head = QHBoxLayout()
            head.addWidget(label(title, "sectionTitle"))
            head.addStretch()
            rst = Button("Reset", "restore")
            rst.setToolTip("Every chart shown, in the first order")
            rst.clicked.connect(lambda _=False, page=page: self.prefs.reset(page))
            head.addWidget(rst)
            pl.addLayout(head)
            rows = QVBoxLayout()
            rows.setSpacing(theme.GAP)
            pl.addLayout(rows)
            self.lists[page] = rows
            v.addWidget(p)
            self.fill(page)
        v.addStretch()
        return body

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

    # ----- Network -----

    def build_network(self):
        body, v, pl = section_page("Network", "The network interface that carries the game's traffic. The one with "
                                              "the internet connection is first, and it is the right one unless a "
                                              "VPN or a second network card is in use.")
        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        row.addWidget(label("Interface", "muted"))
        self.network = QComboBox()
        self.network.setMinimumWidth(220)
        ips = local_ips()  # the default-route one first
        saved = self.prefs.option("network")
        for ip in ips + ([saved] if saved and saved not in ips else []):
            self.network.addItem(ip if ip in ips else f"{ip} (not connected)", ip)
        self.network.setCurrentIndex(max(self.network.findData(saved), 0) if saved else 0)
        self.network.activated.connect(lambda _: self.prefs.set_option("network", self.network.currentData()))
        row.addWidget(self.network)
        row.addStretch()
        pl.addLayout(row)
        v.addStretch()
        return body

    # ----- Recording -----

    def build_recording(self):
        body, v, pl = section_page("Recording", "A race is recorded from when the other racers' data starts coming "
                                                "in until it stops, and can then be watched on the Replays page.")
        self.auto_record = QCheckBox("Record online races automatically")
        self.auto_record.setChecked(self.prefs.option("auto_record"))
        self.auto_record.toggled.connect(lambda on: self.prefs.set_option("auto_record", on))
        pl.addWidget(self.auto_record)

        p, rl = panel()
        rl.addWidget(label("Raw traffic", "sectionTitle"))
        self.raw_traffic = QCheckBox("Also save the raw network traffic of each recorded race")
        self.raw_traffic.setChecked(self.prefs.option("raw_traffic"))
        self.raw_traffic.toggled.connect(lambda on: self.prefs.set_option("raw_traffic", on))
        rl.addWidget(self.raw_traffic)
        rl.addWidget(label("Every packet the capture sees while a race is recorded, and in the 30 seconds before "
                           "it (kept in memory only, until a race starts), is saved next to its replay, as a "
                           ".pcap.gz file that Wireshark opens, for working out more of what the game sends. "
                           "Replays that have it say \"raw traffic\" in the list; deleting a replay deletes it too.",
                           "muted", wrap=True))
        warn = label(f'<span style="color:{theme.DANGER}">Be careful with these files.</span> They are not just '
                     "the game's traffic but everything this computer's network connection carried during the "
                     "race: other apps, the browser, chats, downloads. Whatever of it went unencrypted is in "
                     "there as it was, and that can be private: addresses, names, messages, logins. Don't share "
                     "these files, or replay folders that hold them, with anyone you wouldn't show that to.",
                     "muted", wrap=True)
        warn.setTextFormat(Qt.RichText)
        rl.addWidget(warn)
        v.addWidget(p)
        # only races that are recorded get their traffic saved
        self.raw_traffic.setEnabled(self.auto_record.isChecked())
        self.auto_record.toggled.connect(self.raw_traffic.setEnabled)
        v.addStretch()
        return body

    # ----- Plugins: map packs -----

    def build_plugins(self):
        body, v, pl = section_page("Plugins", "Map packs (.ntemap) put the game's map under the tracks on the Live, "
                                              "Multiplayer and Replays pages. Each says which game world it is the "
                                              "map of, and the one of the world you are in is shown.",
                                   f"They are kept in {world_map.maps_dir()}.")
        btns = QHBoxLayout()
        btns.setSpacing(theme.GAP)
        add = Button("Install map pack", "folder")
        add.setToolTip("Copy a .ntemap file into the maps folder")
        add.clicked.connect(self.install_map)
        btns.addWidget(add)
        folder = Button("Open folder", "folder")
        folder.setToolTip("Show the maps folder in Explorer")
        folder.clicked.connect(lambda: os.startfile(world_map.maps_dir()))
        btns.addWidget(folder)
        again = Button("Rescan", "restore")
        again.setToolTip("Look at the maps folder again, after adding or removing packs by hand")
        again.clicked.connect(self.rescan_maps)
        btns.addWidget(again)
        btns.addStretch()
        pl.addLayout(btns)
        self.map_rows = QVBoxLayout()
        self.map_rows.setSpacing(theme.GAP)
        v.addLayout(self.map_rows)
        v.addStretch()
        self.fill_maps()
        return body

    def fill_maps(self):
        while self.map_rows.count():
            self.map_rows.takeAt(0).widget().deleteLater()
        maps = world_map.all_maps()
        if not maps:
            p, pl = panel()
            pl.addWidget(label("No map packs installed.", "muted"))
            self.map_rows.addWidget(p)
        for m in maps:
            p, pl = panel()
            pl.setSpacing(2)
            pl.addWidget(label(m.name, "listTitle"))
            world = m.level.rsplit("/", 1)[-1] if m.level else "none given: told by its roads"
            size = os.path.getsize(m.pack.path) / 1e6 if os.path.isfile(m.pack.path) else None
            details = f"World: {world}   ·   {m.file}" + (f"   ·   {size:.0f} MB" if size else "")
            pl.addWidget(label(details, "muted"))
            self.map_rows.addWidget(p)

    def update_plugins_row(self):
        n = len(world_map.all_maps())
        self.nav.set_details(self.plugins_row, f"{n} map pack" + ("" if n == 1 else "s") if n else "No map packs")

    def maps_updated(self):
        self.fill_maps()
        self.update_plugins_row()
        self.maps_changed.emit()

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
        self.maps_updated()

    def rescan_maps(self):
        world_map.rescan()
        self.maps_updated()

    def render(self):
        pass

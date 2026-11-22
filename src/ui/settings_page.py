"""The Settings page: a list of sections on the left, as the Replays page's races, and the chosen one beside it.
Display: which charts the Live page shows and in what order, how the Multiplayer and Replays pages are laid out, the
unit of speed and how racers are named on the map. Network: the interface to capture on. Recording: online races.
Plugins: the map packs. Account: the player's name and account ID, as the game sends them.

Every section is laid out the same way: a panel with its title and what it is about, then groups (a panel each:
a title, maybe a line on it and buttons on its right), made of settings one under another, between thin lines -
each one's name and what it does on the left, its control on the right, all controls of one width."""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout,
                               QWidget)

from capture.raw_socket import local_ips
from ui import theme, units, world_map
from ui.widgets import MAP_NAMES, Button, RowList, Select, label, notice, panel, scroll

FIELD_WIDTH = 260  # every drop-down list and text field


def section_page(title, intro):
    """A section's page: its title and the line under it, and room for its groups (the layout returned)."""
    body = QWidget()
    v = QVBoxLayout(body)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(theme.GAP)
    p, pl = panel()
    pl.addWidget(label(title, "sectionTitle"))
    pl.addWidget(label(intro, "muted", wrap=True))
    v.addWidget(p)
    return body, v


def group(v, title, text=None, buttons=()):
    """A group of settings, added to page layout v: its title with the buttons on its right, the text under it;
    the layout its settings go in."""
    p, pl = panel()
    head = QHBoxLayout()
    head.setSpacing(theme.GAP)
    head.addWidget(label(title, "sectionTitle"))
    head.addStretch()
    for b in buttons:
        head.addWidget(b)
    pl.addLayout(head)
    if text:
        pl.addWidget(label(text, "muted", wrap=True))
    rows = QVBoxLayout()
    rows.setContentsMargins(0, 0, 0, 0)
    rows.setSpacing(theme.GAP)
    pl.addLayout(rows)
    v.addWidget(p)
    return rows


def divider():
    line = QFrame()
    line.setProperty("role", "divider")
    line.setFixedHeight(1)
    return line


def setting(rows, name, text, *controls):
    """One setting at the bottom of a group's rows, under a line if it isn't the first: its name and text on the
    left, the controls on the right. The left column is returned, for more lines under the text."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(theme.GAP * 2)
    left = QVBoxLayout()
    left.setSpacing(4)
    left.addWidget(label(name))
    if text:
        left.addWidget(label(text, "muted", wrap=True))
    h.addLayout(left, 1)
    for c in controls:
        h.addWidget(c, 0, Qt.AlignVCenter)
    if rows.count():
        rows.addWidget(divider())
    rows.addWidget(w)
    return left


def select(items, current, on_change):
    """A drop-down list of the (key, name) items, current chosen; on_change(key) when another is."""
    s = Select()
    s.setFixedWidth(FIELD_WIDTH)
    for key, name in items:
        s.addItem(name, key)
    s.setCurrentIndex(max(s.findData(current), 0))
    s.activated.connect(lambda _: on_change(s.currentData()))
    return s


def value_label():
    """A value shown where a setting's control would be, that can't be changed: as wide as the controls, on their
    right."""
    w = QLabel()
    w.setFixedWidth(FIELD_WIDTH)
    w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    w.setTextInteractionFlags(Qt.TextSelectableByMouse)  # to copy
    w.setProperty("role", "listTitle")
    return w


def moved(keys, i, step):
    """keys with the one at i moved step places along."""
    keys = list(keys)
    keys[i], keys[i + step] = keys[i + step], keys[i]
    return keys


def switch(on, on_change):
    """A checkbox standing for a setting's name to its left."""
    cb = QCheckBox()
    cb.setCursor(Qt.PointingHandCursor)
    cb.setChecked(on)
    cb.toggled.connect(on_change)
    return cb


class SettingsPage(QWidget):
    maps_changed = Signal()  # a map pack was installed, or the maps folder looked at again

    def __init__(self, prefs, sections, layouts=()):
        """sections: [(page key, title, [(chart key, chart title)])], the pages whose charts Display sets;
        layouts: [(page key, title, [(panel key, its
        name)], {side: its name})], the pages whose layout Display sets (prefs.LAYOUTS)"""
        super().__init__()
        self.prefs = prefs
        self.dirty = True
        self.lists = {}
        self.layout_specs = layouts
        self.titles = {}
        self.layouts = {}  # page key -> (side select, charts select, layout of the panels' rows, {panel key: name})
        self.layout_shown = {}  # page key -> its panels in the order their rows are in

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

        pages = [("Display", "Charts, layouts and units", self.build_display(sections)),
                 ("Network", "Where the game's traffic is read", self.build_network()),
                 ("Recording", "Online races", self.build_recording()),
                 ("Plugins", "", self.build_plugins()),
                 ("Account", "", self.build_account())]
        for title, details, page in pages:
            self.nav.add_row(title, details)
            self.stack.addWidget(scroll(page))
        self.plugins_row = len(pages) - 2
        self.account_row = len(pages) - 1
        self.update_plugins_row()
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        prefs.changed.connect(self.fill)
        self.update_account()
        prefs.changed.connect(lambda key: key == "options" and self.update_account())  # the game named you
        prefs.changed.connect(lambda key: key == "options" and self.fill_layouts())

    # ----- Display -----

    def build_display(self, sections):
        body, v = section_page("Display", "What the pages show, and how: their charts and panels, the unit of "
                                          "speed and the map.")
        for page, title, charts in sections:
            self.titles[page] = dict(charts)
            rst = Button("Reset", "restore")
            rst.setToolTip("Every chart shown, in the first order")
            rst.clicked.connect(lambda _=False, page=page: self.prefs.reset(page))
            self.lists[page] = group(v, f"{title} charts", "The charts shown and their order. They fill the window "
                                     "left to right, top to bottom: up to 3 in a row, up to 8 in two rows.", [rst])
            self.fill(page)
        for page, title, panels, sides in self.layout_specs:
            self.build_layout(v, page, title, panels, sides)
        self.fill_layouts()
        self.build_units(v)
        self.build_map(v)
        v.addStretch()
        return body

    def build_layout(self, v, page, title, panels, sides):
        """Where a page's column of panels is, which are on and their order in it, and the order of its charts
        (prefs.LAYOUTS)."""
        rst = Button("Reset", "restore")
        rst.setToolTip("As the page first was")
        rst.clicked.connect(lambda: self.prefs.set_layout(page))
        rows = group(v, f"{title} layout", None, [rst])
        side = select(sides.items(), None, lambda key: self.prefs.set_layout(page, side=key))
        setting(rows, "Panels' column", "The side of the page the panels are on.", side)
        chart_order = select([(False, "Map, then speed"), (True, "Speed, then map")], None,
                             lambda key: self.prefs.set_layout(page, speed_first=key))
        setting(rows, "Charts", "The two charts, left to right.", chart_order)
        setting(rows, "Panels", "Those shown, top to bottom in the column.")
        box = QWidget()
        order = QVBoxLayout(box)
        order.setContentsMargins(0, 0, 0, 0)
        order.setSpacing(theme.GAP)
        rows.addWidget(box)
        self.layouts[page] = (side, chart_order, order, dict(panels))

    def fill_layouts(self):
        """The layout groups as the layouts are now: the lists' choices, and the panels' rows in their order."""
        for page, (side, chart_order, order, names) in self.layouts.items():
            lay = self.prefs.layout(page)
            side.setCurrentIndex(max(side.findData(lay["side"]), 0))
            chart_order.setCurrentIndex(max(chart_order.findData(lay["speed_first"]), 0))
            if self.layout_shown.get(page) == (lay["panels"], lay["off"]):
                continue
            self.layout_shown[page] = (lay["panels"], lay["off"])
            while order.count():
                order.takeAt(0).widget().deleteLater()
            keys = lay["panels"]
            for i, key in enumerate(keys):
                w = QWidget()
                h = QHBoxLayout(w)
                h.setContentsMargins(0, 0, 0, 0)
                h.setSpacing(theme.GAP)
                cb = QCheckBox(names[key])
                cb.setCursor(Qt.PointingHandCursor)
                cb.setChecked(key not in lay["off"])
                cb.toggled.connect(lambda on, page=page, key=key: self.prefs.set_layout(
                    page, off=[k for k in self.prefs.layout(page)["off"] if k != key] + ([] if on else [key])))
                h.addWidget(cb, 1)
                for step, name, icon in ((-1, "Move up", "chevron-up"), (1, "Move down", "chevron-down")):
                    b = Button(name, icon, icon_only=True)
                    b.setEnabled(0 <= i + step < len(keys))
                    b.clicked.connect(lambda _=False, page=page, keys=keys, i=i, step=step:
                                      self.prefs.set_layout(page, panels=moved(keys, i, step)))
                    h.addWidget(b)
                order.addWidget(w)

    def build_units(self, v):
        """The unit speeds are shown in, on every page (ui/units.py)."""
        rows = group(v, "Units")
        self.speed_unit = select(units.NAMES.items(), self.prefs.option("speed_unit"),
                                 lambda key: self.prefs.set_option("speed_unit", key))
        setting(rows, "Speed", "Distances follow it: metres and kilometres with km/h and m/s, feet and miles with "
                               "mph, feet and nautical miles with knots and Mach. Mach is to the speed of sound at "
                               "sea level, 1225 km/h.", self.speed_unit)

    def build_map(self, v):
        """How racers are named over their markers on the map (widgets.map_name), and whether their trails are
        drawn."""
        rows = group(v, "Map")
        self.map_names = select(MAP_NAMES.items(), self.prefs.option("map_names"),
                                lambda key: self.prefs.set_option("map_names", key))
        setting(rows, "Racers' names", "Over each car's marker on the map of a replay. Three letters: the first "
                                       "three of the name in capitals, as the game shows them in a race.",
                self.map_names)
        self.map_trails = switch(self.prefs.option("map_trails"), lambda on: self.prefs.set_option("map_trails", on))
        setting(rows, "Trails behind the cars", "Each car's last minute, drawn behind its marker on the Multiplayer "
                                                "and Replays maps. Off, the maps show the markers alone.",
                self.map_trails)

    # ----- Account -----

    def build_account(self):
        """The player as the game knows them: the race server lists every entrant by name, and this is how the
        Multiplayer and Replays pages tell which one is the player. Not set by hand: the game sends both, with the
        account ID, when it connects (capture/roster.py), and the main window keeps them (on_player)."""
        body, v = section_page("Account", "Who you are in the game. The app reads it from the game's own traffic "
                                          "when the game connects to its server: there is nothing to set.")
        rows = group(v, "In the game")
        self.my_name = value_label()
        setting(rows, "Name", "It marks you as YOU among a race's racers on the Multiplayer and Replays pages, and "
                              "tells your own car from the others'.", self.my_name)
        self.my_id = value_label()
        setting(rows, "Account ID", "", self.my_id)
        self.account_note = label("Not found yet: start the game, or join a race, with the app capturing.", "muted",
                                  wrap=True)
        rows.addWidget(self.account_note)
        v.addStretch()
        return body

    def update_account(self):
        name, acc = self.prefs.option("my_name"), self.prefs.option("my_id")
        self.my_name.setText(name or "—")
        self.my_id.setText(acc or "—")
        self.account_note.setVisible(not name)
        self.nav.set_details(self.account_row, name or "Not found yet")

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
            cb.setCursor(Qt.PointingHandCursor)
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
            if i:
                lay.addWidget(divider())
            lay.addWidget(w)

    # ----- Network -----

    def build_network(self):
        body, v = section_page("Network", "Where the app reads the game's traffic from.")
        rows = group(v, "Capture")
        ips = local_ips()  # the default-route one first
        saved = self.prefs.option("network")
        items = [(ip, ip if ip in ips else f"{ip} (not connected)") for ip in ips + ([saved] if saved and saved not in ips else [])]
        self.network = select(items, saved or (ips[0] if ips else None),
                              lambda ip: self.prefs.set_option("network", ip))
        setting(rows, "Network interface", "The one that carries the game's traffic. The one with the internet "
                                           "connection is first, and it is the right one unless a VPN or a second "
                                           "network card is in use.", self.network)
        v.addStretch()
        return body

    # ----- Recording -----

    def build_recording(self):
        body, v = section_page("Recording", "A race is recorded from when the other racers' data starts coming in "
                                            "until it stops, and can then be watched on the Replays page. A replay "
                                            "keeps each racer's car and in-game name, as the race server sends them.")
        rows = group(v, "Replays")
        self.auto_record = switch(self.prefs.option("auto_record"),
                                  lambda on: self.prefs.set_option("auto_record", on))
        setting(rows, "Record online races automatically", "Off, no replays are made.", self.auto_record)

        rows = group(v, "Raw traffic")
        self.raw_traffic = switch(self.prefs.option("raw_traffic"),
                                  lambda on: self.prefs.set_option("raw_traffic", on))
        left = setting(rows, "Save the raw network traffic of each recorded race",
                       "Every packet the capture sees while a race is recorded, and in the 30 seconds before it "
                       "(kept in memory only, until a race starts), is saved next to its replay, as a .pcap.gz file "
                       "that Wireshark opens, for working out more of what the game sends. Replays that have it say "
                       "\"raw traffic\" in the list; deleting a replay deletes it too.", self.raw_traffic)
        warn = label(f'<span style="color:{theme.DANGER}">Be careful with these files.</span> They are not just '
                     "the game's traffic but everything this computer's network connection carried during the "
                     "race: other apps, the browser, chats, downloads. Whatever of it went unencrypted is in "
                     "there as it was, and that can be private: addresses, names, messages, logins. Don't share "
                     "these files, or replay folders that hold them, with anyone you wouldn't show that to.",
                     "muted", wrap=True)
        warn.setTextFormat(Qt.RichText)
        left.addWidget(warn)
        # only races that are recorded get their traffic saved
        self.raw_traffic.setEnabled(self.auto_record.isChecked())
        self.auto_record.toggled.connect(self.raw_traffic.setEnabled)
        v.addStretch()
        return body

    # ----- Plugins: map packs -----

    def build_plugins(self):
        body, v = section_page("Plugins", "Map packs (.ntemap) put the game's map under the tracks on the Live, "
                                          "Multiplayer and Replays pages. Each says which game world it is the map "
                                          "of, and the one of the world you are in is shown.")
        add = Button("Install", "folder")
        add.setToolTip("Copy a .ntemap file into the maps folder")
        add.clicked.connect(self.install_map)
        folder = Button("Open folder", "folder")
        folder.setToolTip("Show the maps folder in Explorer")
        folder.clicked.connect(lambda: os.startfile(world_map.maps_dir()))
        again = Button("Rescan", "restore")
        again.setToolTip("Look at the maps folder again, after adding or removing packs by hand")
        again.clicked.connect(self.rescan_maps)
        self.map_rows = group(v, "Map packs", f"Kept in {world_map.maps_dir()}.", [add, folder, again])
        v.addStretch()
        self.fill_maps()
        return body

    def fill_maps(self):
        while self.map_rows.count():
            self.map_rows.takeAt(0).widget().deleteLater()
        maps = world_map.all_maps()
        if not maps:
            self.map_rows.addWidget(label("No map packs installed.", "muted"))
        for m in maps:
            world = ", ".join(w.rsplit("/", 1)[-1] for w in m.worlds) or "none given: told by its roads"
            size = os.path.getsize(m.pack.path) / 1e6 if os.path.isfile(m.pack.path) else None
            setting(self.map_rows, m.name, f"World: {world}   ·   {m.file}" + (f"   ·   {size:.0f} MB" if size else ""))

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
            notice(self, "Install map pack", f"Could not copy the map pack: {e}")
            m = False
        if m is None:
            notice(self, "Install map pack", f"{os.path.basename(path)} is not a map pack.")
        self.maps_updated()

    def rescan_maps(self):
        world_map.rescan()
        self.maps_updated()

    def render(self):
        pass

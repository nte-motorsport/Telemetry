"""Small building blocks in the NTE Motorsport site style: panels, buttons, tiles, chart cards, the backdrop."""
import html
import itertools
import math

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QSizePolicy, QHBoxLayout, QLabel, QListView,
                               QListWidget, QListWidgetItem, QPushButton, QScrollArea, QStyledItemDelegate,
                               QVBoxLayout, QWidget)

from ui import theme


class SteadyLabel(QLabel):
    """A label as tall whatever its text. The app's font (Momo Trust Display) has neither Cyrillic nor the racers'
    colour dot (U+25CF): those come from Segoe UI glyph by glyph, whose line is a pixel taller at 12 px (17 against
    16), so a row of names would grow and shrink as names, dots and dashes come and go. This one is always as tall
    as the taller of the two."""

    def tall(self, size):
        fallback = QFont(self.font())
        fallback.setFamilies(["Segoe UI"])
        extra = max(QFontMetrics(fallback).height() - QFontMetrics(self.font()).height(), 0)
        plain = QLabel(self)  # the height the label's own font gives, with its margins: a text with no fallback
        plain.setFont(self.font())
        plain.setText("M")
        size.setHeight(max(size.height(), plain.sizeHint().height() + extra))
        plain.deleteLater()
        return size

    def sizeHint(self):
        return self.tall(super().sizeHint())

    def minimumSizeHint(self):
        return self.tall(super().minimumSizeHint())


def label(text="", role=None, wrap=False, steady=False):
    """steady: as tall whatever the text (SteadyLabel), for the rows of racers' names."""
    w = SteadyLabel(text) if steady else QLabel(text)
    if role:
        w.setProperty("role", role)
    w.setWordWrap(wrap)
    return w


def set_text(w, text):
    """Write text in label w only when it says something else: writing it anew lays it out and draws it again."""
    if w.text() != text:
        w.setText(text)


def panel(layout_cls=QVBoxLayout, margins=theme.GAP, spacing=theme.GAP):
    f = QFrame()
    f.setProperty("role", "panel")
    lay = layout_cls(f)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    return f, lay


def legend_dot(color):
    return f'<span style="color:{color}">●</span>'


class Button(QPushButton):
    """A site button: label, then a Tabler icon on the right; black icon when filled (checked/primary)."""

    def __init__(self, text, icon_name=None, checkable=False, icon_only=False):
        super().__init__("" if icon_only else text)
        self.icon_name = icon_name
        self.tint = None  # colour of the border and icon instead of the accent
        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setIconSize(QSize(20, 20))
        if icon_only:
            self.setProperty("iconOnly", True)
            self.setToolTip(text)
        self.toggled.connect(lambda _: self.refresh())
        self.refresh()

    def set_flag(self, name, on):
        self.setProperty(name, on)
        self.style().unpolish(self)
        self.style().polish(self)
        self.refresh()

    def set_tint(self, color):
        """Border and icon in this colour, and its dark shade on hover (as ACCENT_DARK is the accent's)."""
        self.tint = color
        c = QColor(color)
        dark = QColor(int(c.red() * 0.17), int(c.green() * 0.17), int(c.blue() * 0.17)).name()
        self.setStyleSheet(f"QPushButton {{ border-color: {color}; }} QPushButton:hover {{ background: {dark}; }}")
        self.refresh()

    def set_icon(self, name):
        self.icon_name = name
        self.refresh()

    def refresh(self):
        if not self.icon_name:
            return
        filled = self.isChecked() or self.property("primary")
        color = ("#000000" if filled else theme.DANGER if self.property("danger") else self.tint or theme.ACCENT)
        self.setIcon(theme.icon(self.icon_name, color))


class Tile(QFrame):
    def __init__(self, name, unit, big=False):
        super().__init__()
        self.setProperty("role", "panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(theme.GAP, theme.GAP, theme.GAP, theme.GAP)
        lay.setSpacing(2)
        lay.addWidget(label(name, "muted"))
        row = QHBoxLayout()
        row.setSpacing(4)
        self.value = label("–", "tileValueBig" if big else "tileValue")
        row.addWidget(self.value)
        # a bare degree sign sits up by the digits, like 312°; other units go on the baseline
        self.unit = label(unit, "muted")
        row.addWidget(self.unit, 0, Qt.AlignTop if unit == "°" else Qt.AlignBottom)
        row.addStretch()
        lay.addLayout(row)

    def set(self, text):
        self.value.setText(text)

    def set_unit(self, unit):
        self.unit.setText(unit)


def card(title, chart, legend=""):
    f, lay = panel()
    head = QHBoxLayout()
    head.setSpacing(theme.GAP)
    head.addWidget(label(title, "sectionTitle"))
    f.legend = None  # the legend label, for pages that change it
    if legend:
        f.legend = lg = label(legend, "muted")
        lg.setTextFormat(Qt.RichText)
        head.addWidget(lg)
    head.addStretch()
    lay.addLayout(head)
    lay.addWidget(chart, 1)
    return f


class ChartGrid(QWidget):
    """Chart cards sharing the room left on the page; set_order() shows the given keys in that order,
    left to right, top to bottom, and hides the rest. Up to 3 charts sit in one row, up to 8 in two,
    more in three; every cell gets the same size."""

    def __init__(self, cards):
        super().__init__()
        self.cards = cards  # {key: card}
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(theme.GAP)
        for c in cards.values():
            c.setParent(self)
            # sized by the grid alone, not by what is inside, so all cells come out equal
            c.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            c.setMinimumSize(220, 150)
            c.hide()

    def set_order(self, keys):
        for c in self.cards.values():
            self.grid.removeWidget(c)
            c.hide()
        n = len(keys)
        rows = 0 if not n else 1 if n <= 3 else 2 if n <= 8 else 3
        cols = math.ceil(n / rows) if n else 0
        for i in range(len(self.cards)):
            self.grid.setRowStretch(i, 1 if i < rows else 0)
            self.grid.setColumnStretch(i, 1 if i < cols else 0)
        for i, k in enumerate(keys):
            self.grid.addWidget(self.cards[k], i // cols, i % cols)
            self.cards[k].show()


def row_height():
    """A list row: the title and the details line under it, list_row's margins, and the list item's padding and
    border (8 and 2 px) and the GAP under it (from the style sheet), which the row widget is placed inside."""
    return (QFontMetrics(theme.font(theme.FS_LG)).height() + QFontMetrics(theme.font(theme.FS_MD)).height() + 2
            + 2 * 4 + 2 * (8 + 2) + theme.GAP)


def list_row(title, details):
    """A row of a RowList: the title in the site font, a muted line under it. Drawn over the list item, which
    keeps the hover and selection look; its labels turn dark on the selected (yellow) one."""
    w = QWidget()
    w.setProperty("role", "raceRow")
    w.setAttribute(Qt.WA_TransparentForMouseEvents)
    v = QVBoxLayout(w)
    v.setContentsMargins(6, 4, 6, 4)
    v.setSpacing(2)
    v.addWidget(label(title, "listTitle"))
    v.addWidget(label(details, "muted"))
    return w


class RowList(QListWidget):
    """A list of list_row rows in the site style (the Replays races, the Settings sections); the selected one is
    the accent, with dark text."""

    def __init__(self):
        super().__init__()
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.currentRowChanged.connect(self.mark_selected)

    def add_row(self, title, details, data=None):
        it = QListWidgetItem()
        it.setData(Qt.UserRole, data)
        it.setSizeHint(QSize(0, row_height()))
        self.addItem(it)
        self.setItemWidget(it, list_row(title, details))
        return it

    def set_details(self, row, details):
        """Change the muted line of a row."""
        w = self.itemWidget(self.item(row))
        w.findChildren(QLabel)[1].setText(details)

    def mark_selected(self, row=None):
        """Dark text on the selected row, whose background is the accent."""
        for i in range(self.count()):
            w = self.itemWidget(self.item(i))
            w.setProperty("sel", i == self.currentRow())
            for x in [w] + w.findChildren(QWidget):
                x.style().unpolish(x)
                x.style().polish(x)


class TimingPanel(QFrame):
    """A race's entrants in a list, in race order during a race: each one's place, name (in the colour of their car on
    the map and the charts, once the capture has matched them: capture/identity.py) and how many seconds after the
    racer ahead they got where they are (capture/progress.py)."""
    WIDTH = 300
    PLACEHOLDERS = 4  # rows in all at least: dashes for those not known yet (the race server names them as the race loads)

    def __init__(self, title="Timing"):
        super().__init__()
        self.setProperty("role", "panel")
        self.setFixedWidth(self.WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)  # as tall as it needs
        v = QVBoxLayout(self)
        v.setContentsMargins(theme.GAP, theme.GAP, theme.GAP, theme.GAP)
        v.setSpacing(theme.GAP)
        v.addWidget(label(title, "sectionTitle"))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(theme.GAP)
        self.grid.setVerticalSpacing(4)
        self.grid.setColumnStretch(1, 1)
        v.addLayout(self.grid)
        self.rows = []  # (place, name, interval) labels, one row per entrant
        self.me = ""
        self.entrants = []
        self.colors = {}  # name -> colour of their car on the map and the charts
        self.standings = {}  # name ("" for the player) -> (place, interval in s or None, finished)

    def set_colors(self, colors):
        if colors != self.colors:
            self.colors = dict(colors)
            self.refresh()

    def set_me(self, name):
        self.me = name or ""
        self.refresh()

    def set_standings(self, standings):
        """{name, or "" for the player: (place, seconds after the racer ahead or None, whether finished, seconds after
        the leader or None)}; {} for
        none. The interval of two finishers is the race server's, to the millisecond; one on the way is good to a
        tenth or two, so written to the tenth."""
        self.standings = dict(standings)
        self.refresh()

    def standing(self, name):
        return self.standings.get("" if self.me and name == self.me else name)

    def set_entrants(self, entrants):
        """entrants: [dict(car, name, bot)] (capture/roster.py)"""
        self.entrants = list(entrants)
        while len(self.rows) < max(len(self.entrants), self.PLACEHOLDERS):
            row = len(self.rows)
            cells = (label("", "muted", steady=True), label(steady=True), label("", "muted", steady=True),
                     label("", "muted", steady=True))
            cells[1].setTextFormat(Qt.RichText)
            cells[1].setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # a long name is cut, not the times
            cells[2].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cells[3].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for col, w in enumerate(cells):
                self.grid.addWidget(w, row, col)
            self.rows.append(cells)
        self.refresh()

    def order(self):
        """The entrants in race order while there is one (those not placed after, as they were)."""
        return sorted(self.entrants, key=lambda e: self.standing(e["name"])[0] if self.standing(e["name"]) else 99)

    def refresh(self):
        """The rows written anew, in race order; rows of dashes after them up to PLACEHOLDERS, at the places left."""
        placed = self.order()
        taken = {st[0] for st in map(self.standing, (e["name"] for e in placed)) if st}
        free = (p for p in itertools.count(1) if p not in taken)
        dashes = [next(free) for _ in range(self.PLACEHOLDERS - len(placed))]
        # by place, those without one (not placed yet) last; before the race, the entrants first and the dashes after
        place_of = lambda item: item if isinstance(item, int) else (self.standing(item["name"]) or (99,))[0]
        placed = sorted(placed + dashes, key=place_of) if taken else placed + dashes
        for k, cells in enumerate(self.rows):
            shown = k < len(placed)
            for w in cells:
                w.setVisible(shown)
            if not shown:
                continue
            if isinstance(placed[k], int):
                place = placed[k]
                # before the race, among entrants not placed yet, a dash's place is no more known than theirs
                known = taken or not self.entrants
                set_text(cells[0], f"P{place}" if known else "—")
                set_text(cells[1], f'<span style="color:{theme.MUTED}">—</span>')
                set_text(cells[2], "Interval" if known and place == 1 else "—")
                set_text(cells[3], "Leader" if known and place == 1 else "—")
                continue
            e = placed[k]
            st = self.standing(e["name"])
            mine = self.me and e["name"] == self.me
            color = theme.ACCENT if mine else self.colors.get(e["name"])
            dot = f'<span style="color:{color}">&#9679;</span>&nbsp;' if color else ""
            set_text(cells[0], f"P{st[0]}" if st else "—")
            set_text(cells[1], dot + html.escape(shown_name(e["name"], e.get("bot"))))
            set_text(cells[2], "" if not st else "Interval" if st[0] == 1
                             else f"+{st[1]:.{3 if st[2] else 1}f}" if st[1] is not None else "")
            gap = st[3] if st and len(st) > 3 else None
            set_text(cells[3], "" if not st else "Leader" if st[0] == 1
                             else f"+{gap:.{3 if st[2] else 1}f}" if gap is not None else "")


class DriversPanel(QFrame):
    """A race's entrants in detail, in the order they are given: each one's name (in the colour of their car on the
    map and the charts), car, and rank with points, the rank's logo on the left: the player's own as the server names
    it, another player's from their points in the race's lobby (ui/ranks.py); a bot's, or one not known yet, the first
    rank's faded."""
    PLACEHOLDERS = 4  # entries in all at least: dashes for those not known yet
    LOGO = 44  # px: a rank logo's side, about the three lines of an entry
    UNKNOWN_OPACITY = 0.25  # the first rank's logo, as shown for a bot or a rank not known yet

    def __init__(self, title="Racers"):
        super().__init__()
        self.setProperty("role", "panel")
        self.setFixedWidth(TimingPanel.WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
        v = QVBoxLayout(self)
        v.setContentsMargins(theme.GAP, theme.GAP, theme.GAP, theme.GAP)
        v.setSpacing(theme.GAP)
        v.addWidget(label(title, "sectionTitle"))
        self.list = QVBoxLayout()
        self.list.setSpacing(theme.GAP)
        v.addLayout(self.list)
        self.shown = None  # what the entries say, to write them anew only when it changes
        self.logos = {}  # (logo file, opacity) -> its pixmap, scaled
        self.rows = []  # [box, icon, [head, car, rank labels], its logo's pixmap] made so far: kept and written over, not made anew,
                        # so a change doesn't blink the panel
        self.set_racers([])

    def add_row(self):
        box = QFrame()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.GAP)
        icon = QLabel()  # empty only while no logo is there at all: the names stay in line
        icon.setFixedSize(self.LOGO, self.LOGO)
        icon.setAlignment(Qt.AlignCenter)
        row.addWidget(icon)
        b = QVBoxLayout()
        b.setContentsMargins(0, 0, 0, 0)
        b.setSpacing(2)
        row.addLayout(b, 1)
        texts = []
        for role in ("listTitle", "muted", "muted"):
            w = label("", role, steady=True)
            w.setTextFormat(Qt.RichText)
            b.addWidget(w)
            texts.append(w)
        self.list.addWidget(box)
        self.rows.append([box, icon, texts, None])

    def set_racers(self, racers):
        """racers: [dict(name, bot, color or None, car: its name, rank: dict(name, logo: its file or None) or None,
        points or None)], in order; [] for placeholders."""
        if racers == self.shown:
            return
        self.shown = racers
        entries = racers + [None] * (self.PLACEHOLDERS - len(racers))  # dashes for those not known yet
        while len(self.rows) < len(entries):
            self.add_row()
        for k, (box, icon, texts, had) in enumerate(self.rows):
            box.setVisible(k < len(entries))
            if k >= len(entries):
                continue
            r = entries[k]
            if r and r["rank"] and r["rank"]["logo"]:
                pix = self.logo(r["rank"]["logo"])
            else:  # a bot's, or a rank not known yet: the first rank's, faded
                from ui import ranks
                first = ranks.first_logo()
                pix = self.logo(first, self.UNKNOWN_OPACITY) if first else None
            if pix is not had:  # (the pixmaps are kept: the same one is the same logo)
                self.rows[k][3] = pix
                if pix:
                    icon.setPixmap(pix)
                else:
                    icon.clear()
            if r is None:
                head, car, rank = "—", "—", "—"
            else:
                dot = f'<span style="color:{r["color"]}">&#9679;</span>&nbsp;' if r["color"] else ""
                head = dot + html.escape(shown_name(r["name"], r["bot"]))
                car = html.escape(r["car"]) if r["car"] else "—"
                if r["bot"]:
                    rank = "Bot"
                else:
                    rank = " · ".join(([html.escape(r["rank"]["name"])] if r["rank"] else [])
                                      + ([f"{r['points']} pts"] if r["points"] is not None else [])) or "—"
            for w, text in zip(texts, (head, car, rank)):
                set_text(w, text)

    def logo(self, path, opacity=1.0):
        """The pixmap of a logo file, scaled to fit and at opacity, or None if it won't load."""
        if (path, opacity) not in self.logos:
            pix = QPixmap(path)
            if not pix.isNull():
                ratio = self.devicePixelRatioF()
                pix = pix.scaled(QSize(self.LOGO, self.LOGO) * ratio, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                if opacity < 1:
                    faded = QPixmap(pix.size())
                    faded.fill(Qt.transparent)
                    p = QPainter(faded)
                    p.setOpacity(opacity)
                    p.drawPixmap(0, 0, pix)
                    p.end()
                    pix = faded
                pix.setDevicePixelRatio(ratio)
            self.logos[(path, opacity)] = None if pix.isNull() else pix
        return self.logos[(path, opacity)]


class MiniStrip(QWidget):
    """A lap's mini-sectors in a row of bars, each in the colour of its time (ui/sectors.py), dim while not driven."""
    HEIGHT = 4

    def __init__(self):
        super().__init__()
        self.setFixedHeight(self.HEIGHT)
        self.colors = []

    def set_colors(self, colors):
        if colors != self.colors:
            self.colors = list(colors)
            self.update()

    def paintEvent(self, ev):
        n = len(self.colors)
        if not n:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        gap = 2
        w = (self.width() - gap * (n - 1)) / n
        for i, c in enumerate(self.colors):
            p.setBrush(QColor(c or theme.GRID))
            p.drawRoundedRect(QRectF(i * (w + gap), 0, w, self.HEIGHT), 1.5, 1.5)
        p.end()


class SectorsPanel(QFrame):
    """Each racer's latest time in each of the lap's three sectors, coloured as in real racing (purple the best of
    anyone's, green their own best, yellow slower than their own best), and their current lap's mini-sectors in a
    strip below in the same colours (ui/sectors.py). Each racer named by three letters, as in races (map_name), on
    the line of their times."""
    PLACEHOLDERS = 4
    PLACEHOLDER_MINIS = 3  # grey mini-sectors to a sector in a row not known yet

    def __init__(self, title="Sectors"):
        super().__init__()
        self.setProperty("role", "panel")
        self.setFixedWidth(TimingPanel.WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
        v = QVBoxLayout(self)
        v.setContentsMargins(theme.GAP, theme.GAP, theme.GAP, theme.GAP)
        v.setSpacing(theme.GAP)
        v.addWidget(label(title, "sectionTitle"))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(theme.GAP)
        self.grid.setVerticalSpacing(3)
        for col, text in enumerate(("S1", "S2", "S3"), 1):  # after the name's column
            self.grid.setColumnStretch(col, 1)
            h = label(text, "muted")
            h.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.grid.addWidget(h, 0, col)
        v.addLayout(self.grid)
        v.addStretch()  # the rows at the top of a panel made taller than they are
        self.rows = []  # (name, [3 sector labels], strip)
        self.shown = None
        self.set_rows([])

    def set_rows(self, rows):
        """rows: [dict(name, bot, color or None, sectors: [(seconds, colour) or None] * 3,
        minis: [colour or None])], in order; [] for placeholders."""
        if rows == self.shown:
            return
        self.shown = rows
        rows = list(rows) + [None] * (self.PLACEHOLDERS - len(rows))
        while len(self.rows) < len(rows):
            k = len(self.rows)
            name = label(steady=True)
            name.setTextFormat(Qt.RichText)
            secs = [label(steady=True) for _ in range(3)]
            for w in secs:
                w.setTextFormat(Qt.RichText)
                w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            strip = MiniStrip()
            # each racer in two rows: name and the sectors' times; the mini-sectors below
            top = 1 + 2 * k
            self.grid.addWidget(name, top, 0)
            for col, w in enumerate(secs, 1):
                self.grid.addWidget(w, top, col)
            self.grid.addWidget(strip, top + 1, 0, 1, 4)
            if k:
                self.grid.setRowMinimumHeight(top, QFontMetrics(name.font()).height() + 6)  # a gap before the next
            self.rows.append((name, secs, strip))
        for k, (name, secs, strip) in enumerate(self.rows):
            r = rows[k] if k < len(rows) else None
            visible = k < len(rows)
            for w in (name, strip, *secs):
                w.setVisible(visible)
            if r is None:
                set_text(name, "—")
                for w in secs:
                    set_text(w, f'<span style="color:{theme.MUTED}">—</span>')
                strip.set_colors([None] * (3 * self.PLACEHOLDER_MINIS))
                continue
            dot = f'<span style="color:{r["color"]}">&#9679;</span>&nbsp;' if r["color"] else ""
            set_text(name, dot + html.escape(map_name(r["name"], r["bot"], "short")))
            for w, sec in zip(secs, r["sectors"]):
                set_text(w, f'<span style="color:{sec[1]}">{sec[0]:.3f}</span>' if sec
                          else f'<span style="color:{theme.MUTED}">—</span>')
            strip.set_colors(r["minis"])


def shown_name(name, bot):
    """A racer's name as the app writes it: a bot's between colons, ":Ethan27:"."""
    return f":{name}:" if bot else name


# how racers are named over their markers on the map (Settings > Display)
MAP_NAMES = {"full": "Full names", "short": "Three letters, as in races", "off": "Hidden"}


def map_name(name, bot, mode):
    """A racer's name as written on the map in mode (a key of MAP_NAMES): in full (a bot's between colons), or as
    its first three letters or digits in capitals, bots' too, as the game shows them ("Racer42" -> "RAC",
    "я Ваня" -> "ЯВА"); "" for none."""
    if mode == "off" or not name:
        return ""
    if mode == "short":
        return "".join(ch for ch in name if ch.isalnum())[:3].upper() or name[:3]
    return shown_name(name, bot)


def scroll(widget):
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QFrame.NoFrame)
    s.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    s.setWidget(widget)
    widget.setAttribute(Qt.WA_TranslucentBackground)
    return s


class Backdrop(QWidget):
    """The sites' page background: the carbon texture, cover-scaled and darkened by half."""

    def __init__(self):
        super().__init__()
        self.src = QPixmap(theme.asset("background.png"))
        self.cache = None

    def resizeEvent(self, ev):
        self.cache = None
        super().resizeEvent(ev)

    def paintEvent(self, ev):
        p = QPainter(self)
        if self.cache is None or self.cache.size() != self.size():
            pm = self.src.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x, y = (pm.width() - self.width()) // 2, (pm.height() - self.height()) // 2
            self.cache = pm.copy(x, y, self.width(), self.height())
        p.drawPixmap(0, 0, self.cache)
        p.fillRect(self.rect(), QColor(0, 0, 0, 128))


class ChosenDelegate(QStyledItemDelegate):
    """A Select's options, the chosen one in the accent colour, under the pointer too."""

    def __init__(self, select):
        super().__init__(select)
        self.select = select

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.row() == self.select.currentIndex():
            for role in (QPalette.Text, QPalette.HighlightedText):
                option.palette.setColor(role, QColor(theme.ACCENT))


class Select(QComboBox):
    """A drop-down list as the NTE Motorsport sites have them (Rivals' SelectField): opened, the field and its
    list are one shape, the same border and background, the field's corners squared off where the list goes on
    (below, or above when there is no room below); the chevron turns over, and the chosen option is in the
    accent colour, with no tick. The looks are in theme.STYLE, keyed on the "open" property ("down" / "up")."""
    MAX_ITEMS = 8  # options shown before the list scrolls

    def __init__(self):
        super().__init__()
        self.setView(QListView())
        self.setItemDelegate(ChosenDelegate(self))  # the style sheet's ::item rules, not the menu look
        # the app's font, set here: a font-size in the style sheet would make the list's font anew from Windows' own
        # for lists (Segoe UI), and the fallback list of theme.font with it
        self.view().setFont(theme.font(theme.FS_MD))
        self.setMaxVisibleItems(self.MAX_ITEMS)
        self.setCursor(Qt.PointingHandCursor)
        self.view().setCursor(Qt.PointingHandCursor)
        pop = self.view().window()  # the list's own window: frameless and see-through, so its corners can round
        pop.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        pop.setAttribute(Qt.WA_TranslucentBackground)

    def showPopup(self):
        super().showPopup()
        pop = self.view().window()
        top = self.mapToGlobal(QPoint(0, 0))
        screen = (self.screen() or pop.screen()).availableGeometry()
        h = pop.height()
        below = top.y() + self.height() + h <= screen.bottom()
        pop.setGeometry(top.x(), top.y() + self.height() if below else top.y() - h, self.width(), h)
        self.set_open("down" if below else "up")

    def hidePopup(self):
        super().hidePopup()
        self.set_open("")

    def set_open(self, how):
        for w in (self, self.view()):
            w.setProperty("open", how)
            w.style().unpolish(w)
            w.style().polish(w)


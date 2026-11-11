"""Small building blocks in the NTE Motorsport site style: panels, buttons, tiles, chart cards, the backdrop."""
import html
import itertools
import math

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QSizePolicy, QHBoxLayout, QLabel, QListView,
                               QListWidget, QListWidgetItem, QPushButton, QScrollArea, QStyledItemDelegate,
                               QVBoxLayout, QWidget)

from ui import theme


def label(text="", role=None, wrap=False):
    w = QLabel(text)
    if role:
        w.setProperty("role", role)
    w.setWordWrap(wrap)
    return w


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
        """{name, or "" for the player: (place, seconds after the racer ahead or None, whether finished)}; {} for
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
            cells = (label("", "muted"), label(), label("", "muted"))
            cells[1].setTextFormat(Qt.RichText)
            cells[2].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
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
                cells[0].setText(f"P{place}" if known else "—")
                cells[1].setText(f'<span style="color:{theme.MUTED}">—</span>')
                cells[2].setText("Interval" if known and place == 1 else "—")
                continue
            e = placed[k]
            st = self.standing(e["name"])
            mine = self.me and e["name"] == self.me
            color = theme.ACCENT if mine else self.colors.get(e["name"])
            dot = f'<span style="color:{color}">&#9679;</span>&nbsp;' if color else ""
            cells[0].setText(f"P{st[0]}" if st else "—")
            cells[1].setText(dot + html.escape(shown_name(e["name"], e.get("bot"))))
            cells[2].setText("" if not st else "Interval" if st[0] == 1
                             else f"+{st[1]:.{3 if st[2] else 1}f}" if st[1] is not None else "")


class DriversPanel(QFrame):
    """A race's entrants in detail, in the order they are given: each one's name (in the colour of their car on the
    map and the charts), car, and rank with points: the player's own as the server names it, another player's from
    their points in the race's lobby (ui/ranks.py), a bot's none."""
    PLACEHOLDERS = 4  # entries in all at least: dashes for those not known yet

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
        self.set_racers([])

    def set_racers(self, racers):
        """racers: [dict(name, bot, color or None, car: its name, rank: a rank row or None, points or None)], in
        order; [] for placeholders."""
        from ui import ranks
        if racers == self.shown:
            return
        self.shown = racers
        while self.list.count():
            w = self.list.takeAt(0).widget()
            if w:  # gone at once: deleteLater alone leaves it drawn where it was until the event loop runs
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for r in racers + [None] * (self.PLACEHOLDERS - len(racers)):  # dashes for those not known yet
            box = QFrame()
            b = QVBoxLayout(box)
            b.setContentsMargins(0, 0, 0, 0)
            b.setSpacing(2)
            if r is None:
                head, car, rank = "—", "—", "—"
            else:
                dot = f'<span style="color:{r["color"]}">&#9679;</span>&nbsp;' if r["color"] else ""
                head = dot + html.escape(shown_name(r["name"], r["bot"]))
                car = html.escape(r["car"]) if r["car"] else "—"
                if r["bot"]:
                    rank = "Bot"
                elif r["rank"]:
                    rank = (f'<span style="color:{ranks.color(r["rank"])}">{html.escape(ranks.name(r["rank"]))}</span>'
                            + (f" · {r['points']} pts" if r["points"] is not None else ""))
                else:
                    rank = "—"
            for text, role in ((head, "listTitle"), (car, "muted"), (rank, "muted")):
                w = label(text, role)
                w.setTextFormat(Qt.RichText)
                b.addWidget(w)
            self.list.addWidget(box)


def shown_name(name, bot):
    """A racer's name as the app writes it: a bot's between colons, ":Ethan27:"."""
    return f":{name}:" if bot else name


# how racers are named over their markers on the map (Settings > Display)
MAP_NAMES = {"full": "Full names", "short": "Three letters, as in races", "off": "Hidden"}


def map_name(name, bot, mode):
    """A racer's name as written on the map in mode (a key of MAP_NAMES): in full (a bot's between colons), or as
    its first three letters or digits in capitals, bots' too, as the game shows them ("liubquanti" -> "LIU",
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


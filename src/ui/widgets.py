"""Small building blocks in the NTE Motorsport site style: panels, buttons, tiles, chart cards, the backdrop."""
import html
import math

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import (QFrame, QGridLayout, QSizePolicy, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

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


class RacersPanel(QFrame):
    """A race's entrants side by side: each one's name, car and whether it is the player or a bot, and the colour
    of their car on the map and the charts once the capture has matched them (capture/identity.py)."""

    def __init__(self, title="Racers"):
        super().__init__()
        self.setProperty("role", "panel")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)  # as tall as it needs, the charts the rest
        v = QVBoxLayout(self)
        v.setContentsMargins(theme.GAP, theme.GAP, theme.GAP, theme.GAP)
        v.setSpacing(theme.GAP)
        v.addWidget(label(title, "sectionTitle"))
        self.row = QHBoxLayout()
        self.row.setSpacing(theme.GAP)
        v.addLayout(self.row)
        self.me = ""
        self.entrants = []
        self.colors = {}  # name -> colour of their car on the map and the charts

    def set_colors(self, colors):
        if colors != self.colors:
            self.colors = dict(colors)
            self.set_entrants(self.entrants)

    def set_me(self, name):
        self.me = name or ""
        self.set_entrants(self.entrants)

    def set_entrants(self, entrants):
        """entrants: [dict(car, name, bot)] (capture/roster.py)"""
        from ui.vehicles import car_name
        self.entrants = list(entrants)
        while self.row.count():
            w = self.row.takeAt(0).widget()
            if w:  # gone at once: deleteLater alone leaves it drawn where it was until the event loop runs
                w.hide()
                w.setParent(None)
                w.deleteLater()
        if not self.entrants:
            self.row.addWidget(label("Not known yet: the race server names its entrants as the race loads.",
                                     "muted"))
        for e in self.entrants:
            box = QFrame()
            box.setProperty("role", "panel")
            b = QVBoxLayout(box)
            b.setContentsMargins(theme.GAP, theme.GAP // 2, theme.GAP, theme.GAP // 2)
            b.setSpacing(2)
            tags = []
            if self.me and e["name"] == self.me:
                tags.append(f'<span style="color:{theme.ACCENT}">YOU</span>')
            color = theme.ACCENT if self.me and e["name"] == self.me else self.colors.get(e["name"])
            dot = f'<span style="color:{color}">&#9679;</span>&nbsp;' if color else ""
            head = label(dot + html.escape(shown_name(e["name"], e.get("bot")))
                         + ("&nbsp;&nbsp;" + " ".join(tags) if tags else ""),
                         "listTitle")
            head.setTextFormat(Qt.RichText)
            b.addWidget(head)
            b.addWidget(label(car_name(e["car"]), "muted"))
            self.row.addWidget(box)
        self.row.addStretch()


def shown_name(name, bot):
    """A racer's name as the app writes it: a bot's between colons, ":Ethan27:"."""
    return f":{name}:" if bot else name


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

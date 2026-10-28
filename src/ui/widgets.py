"""Small building blocks in the NTE Motorsport site style: panels, buttons, tiles, chart cards, the backdrop."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

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

    def set_icon(self, name):
        self.icon_name = name
        self.refresh()

    def refresh(self):
        if not self.icon_name:
            return
        filled = self.isChecked() or self.property("primary")
        color = "#000000" if filled else theme.DANGER if self.property("danger") else theme.ACCENT
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
        row.addWidget(label(unit, "muted"), 0, Qt.AlignTop if unit == "°" else Qt.AlignBottom)
        row.addStretch()
        lay.addLayout(row)

    def set(self, text):
        self.value.setText(text)


def card(title, chart, legend=""):
    f, lay = panel()
    head = QHBoxLayout()
    head.setSpacing(theme.GAP)
    head.addWidget(label(title, "sectionTitle"))
    if legend:
        lg = label(legend, "muted")
        lg.setTextFormat(Qt.RichText)
        head.addWidget(lg)
    head.addStretch()
    lay.addLayout(head)
    lay.addWidget(chart, 1)
    return f


def chart_grid(cards):
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setSpacing(theme.GAP)
    for i, c in enumerate(cards):
        g.addWidget(c, i // 2, i % 2)
    g.setColumnStretch(0, 1)
    g.setColumnStretch(1, 1)
    return w


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

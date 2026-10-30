"""The Settings page: turn each page's charts on and off and change their order."""
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QVBoxLayout, QWidget

from ui import theme
from ui.widgets import Button, label, panel, scroll


class SettingsPage(QWidget):
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

    def fill(self, page):
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

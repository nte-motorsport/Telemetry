"""Which charts each page shows and in what order, kept in %APPDATA%\\NTE Telemetry\\settings.json."""
import json
import os

from PySide6.QtCore import QObject, Signal


def settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "NTE Telemetry")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")


class ChartLayout(QObject):
    changed = Signal(str)  # page key, after any change to that page's charts

    def __init__(self, defaults, path=None):
        """defaults: {page: [chart key, ...]} in the order the page lists them; everything starts shown."""
        super().__init__()
        self.defaults = defaults
        self.path = path or settings_path()
        try:
            saved = json.load(open(self.path, encoding="utf-8"))["charts"]
        except (OSError, ValueError, KeyError, TypeError):
            saved = {}
        self.pages = {}
        for page, keys in defaults.items():
            rows = []
            try:
                rows = [[k, bool(on)] for k, on in saved.get(page, []) if k in keys]
            except (TypeError, ValueError, AttributeError):
                pass
            # charts added in a later version go at the end, shown; ones that no longer exist are dropped
            have = {k for k, _ in rows}
            self.pages[page] = rows + [[k, True] for k in keys if k not in have]

    def rows(self, page):
        return self.pages[page]

    def shown(self, page):
        return [k for k, on in self.pages[page] if on]

    def set_visible(self, page, key, on):
        for row in self.pages[page]:
            if row[0] == key:
                row[1] = on
        self.commit(page)

    def move(self, page, i, step):
        rows = self.pages[page]
        j = i + step
        if 0 <= j < len(rows):
            rows[i], rows[j] = rows[j], rows[i]
            self.commit(page)

    def reset(self, page):
        self.pages[page] = [[k, True] for k in self.defaults[page]]
        self.commit(page)

    def commit(self, page):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(charts=self.pages), f)
        os.replace(tmp, self.path)
        self.changed.emit(page)

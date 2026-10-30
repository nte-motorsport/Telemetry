"""The app's settings, kept in %APPDATA%\\NTE Telemetry\\settings.json: which charts each page shows and in
what order, and on/off options."""
import json
import os

from PySide6.QtCore import QObject, Signal

OPTIONS = {"auto_record": True}  # option -> default


def data_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "NTE Telemetry")
    os.makedirs(d, exist_ok=True)
    return d


class Prefs(QObject):
    changed = Signal(str)  # a page key after a change to its charts, or "options"

    def __init__(self, defaults, path=None):
        """defaults: {page: [chart key, ...]} in the order the page lists them; everything starts shown."""
        super().__init__()
        self.defaults = defaults
        self.path = path or os.path.join(data_dir(), "settings.json")
        try:
            data = json.load(open(self.path, encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        saved = data.get("charts") if isinstance(data.get("charts"), dict) else {}
        opts = data.get("options") if isinstance(data.get("options"), dict) else {}
        self.options = {k: opts[k] if isinstance(opts.get(k), bool) else v for k, v in OPTIONS.items()}
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

    def option(self, name):
        return self.options[name]

    def set_option(self, name, value):
        self.options[name] = value
        self.commit("options")

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

    def commit(self, key):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(charts=self.pages, options=self.options), f)
        os.replace(tmp, self.path)
        self.changed.emit(key)

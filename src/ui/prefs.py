"""The app's settings, kept in %APPDATA%\\NTE Telemetry\\settings.json: which charts each page shows and in
what order, and on/off options."""
import json
import os

from PySide6.QtCore import QObject, Signal

# option -> default; network "" = the default-route one; raw_traffic: save each race's raw network traffic too;
# my_name: the player's name in the game, to mark them among a race's entrants ("" = not known), and my_id their
# account id ("" = not known): both found in the game's traffic (capture/roster.py, ROLE), or the name set by hand;
# speed_unit: the unit speeds are shown in, a key of ui/units.SPEEDS; map_names: how racers are named on the map,
# a key of widgets.MAP_NAMES; map_trails: each car's last minute drawn behind its marker on the Multiplayer and Replays
# maps (off: the markers alone); layout_<page>: how the Multiplayer ("multiplayer") and Replays ("replays") pages
# are laid out, see LAYOUTS
OPTIONS = {"auto_record": True, "network": "", "raw_traffic": False, "my_name": "", "my_id": "", "speed_unit": "kmh",
           "map_names": "full", "map_trails": True, "layout_multiplayer": {}, "layout_replays": {}}

# page -> its layout as it first is: side, the side of the page its column of panels is on ("left" / "right"; on
# Replays the list of races goes on the other); panels, the column's panels top to bottom (the pages' PANELS keys);
# off, those of them turned off; speed_first, the speed chart left of the map
LAYOUTS = {"multiplayer": dict(side="left", panels=["racers", "timing", "sectors"], off=[], speed_first=False),
           "replays": dict(side="right", panels=["result", "sectors", "racers"], off=[], speed_first=False)}


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
        self.options = {k: opts[k] if isinstance(opts.get(k), type(v)) else v for k, v in OPTIONS.items()}
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

    def layout(self, page):
        """A page's layout (LAYOUTS), as saved: what is missing or makes no sense as it first is, panels added in a
        later version at the end of the column."""
        first = LAYOUTS[page]
        saved = self.options["layout_" + page]
        side = saved.get("side") if saved.get("side") in ("left", "right") else first["side"]
        panels = saved.get("panels") if isinstance(saved.get("panels"), list) else []
        panels = list(dict.fromkeys(k for k in panels if k in first["panels"]))
        panels += [k for k in first["panels"] if k not in panels]
        off = saved.get("off") if isinstance(saved.get("off"), list) else []
        off = [k for k in panels if k in off]
        speed_first = saved.get("speed_first") if isinstance(saved.get("speed_first"), bool) else first["speed_first"]
        return dict(side=side, panels=panels, off=off, speed_first=speed_first)

    def set_layout(self, page, **changes):
        """Change some of a page's layout; none: back to as it first is."""
        self.set_option("layout_" + page, dict(self.layout(page), **changes) if changes else {})

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

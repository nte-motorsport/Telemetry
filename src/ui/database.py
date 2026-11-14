"""Names from the NTE Motorsport database (github.com/nte-motorsport/Database, data/*.json), by the game's own ids.

Each kind (ui/vehicles.py, ui/tracks.py) is fetched in the background when the app starts and kept in a file of
%APPDATA%\\NTE Telemetry, so the names are there at once next time, and offline."""
import json
import os
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

from ui.prefs import data_dir

URL = "https://raw.githubusercontent.com/nte-motorsport/Database/main/data/{}.json"
TIMEOUT = 15  # s for each file


def plain(value):
    """A name as kept: text, or a dict of what an entry says (ui/ranks.py)."""
    return value if isinstance(value, dict) else str(value)


def key(game_id):
    """A game id as looked up: the game writes some in more ways than one ("Vehicle026", "vehicle_026")."""
    return str(game_id).lower().replace("_", "")


class Names(QObject):
    changed = Signal()  # the names were fetched anew and differ: labels that show them should be redone

    def __init__(self, files, cache, entry, path=None):
        """files: the database's data files to read; cache: the file name they are kept under; entry: a function
        of one database entry to [(game id, name)] (none for an entry without them)."""
        super().__init__()
        self.files = files
        self.entry = entry
        self.path = path or os.path.join(data_dir(), cache)
        self.names = {}  # key(game id) -> name (or a dict: plain)
        try:
            with open(self.path, encoding="utf-8") as f:
                cached = json.load(f)
            if isinstance(cached, dict):
                self.names = {str(k): plain(v) for k, v in cached.items()}
        except (OSError, ValueError):
            pass
        self.fetching = False

    def get(self, game_id):
        """The name of game_id, or None if the database doesn't have it."""
        return self.names.get(key(game_id))

    def refresh(self):
        """Fetch the database in the background; changed is emitted (in the UI thread) if the names differ."""
        if self.fetching:
            return
        self.fetching = True
        threading.Thread(target=self.fetch, daemon=True).start()

    def fetch(self):
        try:
            names = {}
            for f in self.files:
                req = urllib.request.Request(URL.format(f), headers={"User-Agent": "NTE-Telemetry"})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    for e in json.load(r):
                        if isinstance(e, dict):
                            names.update((key(g), plain(n)) for g, n in self.entry(e))
        except (OSError, ValueError):
            return  # offline, or the database is broken for now: the cached names stay
        finally:
            self.fetching = False
        if names and names != self.names:
            self.names = names
            try:
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(names, f, ensure_ascii=False, indent=1, sort_keys=True)
                os.replace(tmp, self.path)
            except OSError:
                pass
            self.changed.emit()  # a queued connection: the receivers run in the UI thread

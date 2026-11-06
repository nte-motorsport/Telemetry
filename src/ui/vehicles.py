"""The game's car names, by the id the race server sends (capture/roster.py, "Vehicle026"): the model alone, without
the brand ("918 Spyder"), from the NTE Motorsport database (github.com/nte-motorsport/Database: data/cars.json,
bikes.json, other.json, each entry's "game_id" and "model").

The database is fetched in the background when the app starts and kept in %APPDATA%\\NTE Telemetry\\vehicles.json,
so the names are there at once next time, and offline. A car the database doesn't have shows by its id."""
import json
import os
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

from ui.prefs import data_dir

URL = "https://raw.githubusercontent.com/nte-motorsport/Database/main/data/{}.json"
FILES = ("cars", "bikes", "other")
TIMEOUT = 15  # s for each file


class Vehicles(QObject):
    changed = Signal()  # the names were fetched anew and differ: labels that show them should be redone

    def __init__(self, path=None):
        super().__init__()
        self.path = path or os.path.join(data_dir(), "vehicles.json")
        self.names = {}  # game id ("vehicle026") -> model
        try:
            with open(self.path, encoding="utf-8") as f:
                cached = json.load(f)
            if isinstance(cached, dict):
                self.names = {str(k): str(v) for k, v in cached.items()}
        except (OSError, ValueError):
            pass
        self.fetching = False

    def name(self, car):
        """The model of the car with game id car ("Vehicle026", "vehicle004"), or car itself if not known."""
        return self.names.get(key(car)) or car

    def refresh(self):
        """Fetch the database in the background; changed is emitted (in the UI thread) if the names differ."""
        if self.fetching:
            return
        self.fetching = True
        threading.Thread(target=self.fetch, daemon=True).start()

    def fetch(self):
        try:
            names = {}
            for f in FILES:
                req = urllib.request.Request(URL.format(f), headers={"User-Agent": "NTE-Telemetry"})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    for e in json.load(r):
                        if isinstance(e, dict) and e.get("game_id") and e.get("model"):
                            names[key(e["game_id"])] = str(e["model"])
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


def key(car):
    return str(car).lower().replace("_", "")


_vehicles = None


def vehicles():
    """The one Vehicles of the app."""
    global _vehicles
    if _vehicles is None:
        _vehicles = Vehicles()
    return _vehicles


def car_name(car):
    return vehicles().name(car)

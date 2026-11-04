"""The game's car names, by the id the race server sends (capture/roster.py): assets/vehicles.json, made from the
game's DT_VehicleData table and the ST_VehicleData texts. A car not in it shows by its id."""
import json
import os

from ui import theme

_names = None


def car_name(car):
    global _names
    if _names is None:
        try:
            with open(os.path.join(theme.ASSETS, "vehicles.json"), encoding="utf-8") as f:
                _names = json.load(f)
        except (OSError, ValueError):
            _names = {}
    key = car.lower().replace("_", "")
    return _names.get(key) or car

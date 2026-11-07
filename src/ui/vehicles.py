"""The game's car names, by the id the race server sends (capture/roster.py, "Vehicle026"): the model alone, without
the brand ("918 Spyder"), from the NTE Motorsport database (ui/database.py: data/cars.json, bikes.json, other.json,
each entry's "game_id" and "model"), kept in %APPDATA%\\NTE Telemetry\\vehicles.json. A car the database doesn't
have shows by its id."""
from ui.database import Names


def entry(e):
    return [(e["game_id"], e["model"])] if e.get("game_id") and e.get("model") else []


_vehicles = None


def vehicles():
    """The one Names of the app's cars."""
    global _vehicles
    if _vehicles is None:
        _vehicles = Names(("cars", "bikes", "other"), "vehicles.json", entry)
    return _vehicles


def car_name(car):
    """The model of the car with game id car ("Vehicle026", "vehicle004"), or car itself if not known."""
    return vehicles().get(car) or car

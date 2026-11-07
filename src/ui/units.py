"""The unit speeds are shown in (Settings > Display). Speeds are km/h everywhere inside the app: the capture, the
replays, the map's colours; they are turned into the chosen unit only where they are written or charted."""

# key -> (as written, what one km/h is in it, decimals shown)
SPEEDS = {
    "kmh": ("km/h", 1.0, 0),
    "ms": ("m/s", 1 / 3.6, 0),
    "mph": ("mph", 1 / 1.609344, 0),
    "kn": ("kn", 1 / 1.852, 0),
    "mach": ("Mach", 1 / 1225.044, 2),  # the speed of sound at sea level, 15 °C (343 m/s)
}
NAMES = {"kmh": "Kilometres per hour (km/h)", "ms": "Metres per second (m/s)", "mph": "Miles per hour (mph)",
         "kn": "Knots (kn)", "mach": "Mach"}
DEFAULT = "kmh"

_speed = DEFAULT


def set_speed_unit(key):
    """Show speeds in the unit key (an unknown one: km/h); True if that is a change."""
    global _speed
    old, _speed = _speed, key if key in SPEEDS else DEFAULT
    return _speed != old


def speed_unit():
    """The chosen unit as written: "km/h"."""
    return SPEEDS[_speed][0]


def speed(kmh):
    """A speed (a number or an array) in km/h, in the chosen unit."""
    return kmh * SPEEDS[_speed][1]


def speed_text(kmh):
    """A speed in km/h as written in the chosen unit, without the unit: "212", "0.17"."""
    return shown_text(speed(kmh))


def shown_text(v):
    """A speed already in the chosen unit (a chart's value) as written, without the unit."""
    return f"{v:.{SPEEDS[_speed][2]}f}"

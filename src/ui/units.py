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
# the units of distance that go with each unit of speed: (short, metres in one), (long, metres in one). Knots and Mach
# are the sea's and the air's: feet and nautical miles
SYSTEMS = {
    "metric": (("m", 1.0), ("km", 1000.0)),
    "imperial": (("ft", 0.3048), ("mi", 1609.344)),
    "nautical": (("ft", 0.3048), ("nmi", 1852.0)),
}
SYSTEM = {"kmh": "metric", "ms": "metric", "mph": "imperial", "kn": "nautical", "mach": "nautical"}

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


def _system():
    return SYSTEMS[SYSTEM[_speed]]


def height_unit():
    """The unit heights (altitude) are shown in: "m" or "ft"."""
    return _system()[0][0]


def height(m):
    """A height (a number or an array) in metres, in the unit of the chosen system."""
    return m / _system()[0][1]


def distance_unit():
    """The unit distances driven are shown in: "km", "mi" or "nmi"."""
    return _system()[1][0]


def distance(m):
    """A distance in metres, in the long unit of the chosen system."""
    return m / _system()[1][1]


def scale(span_m, nice):
    """A map scale bar for a view span_m metres across: (its length in metres, as written). nice(span) is a round
    length under span; the bar is round in feet or metres while it is shorter than a mile or kilometre, else in
    the long unit."""
    (short, fs), (long, fl) = _system()
    size = nice(span_m / fs)
    if size * fs < fl:
        return size * fs, f"{size:g} {short}"
    size = nice(span_m / fl)
    return size * fl, f"{size:g} {long}"


def length_text(m):
    """A distance in metres as written in the chosen system: in metres or feet under a kilometre, else in its long
    unit to a tenth ("152 m", "2.8 km", "0.6 mi")."""
    (short, fs), (long, fl) = _system()
    if abs(m) < 1000:
        return f"{abs(m) / fs:.0f} {short}"
    return f"{abs(m) / fl:.1f} {long}"

"""The racing ranks, from the NTE Motorsport database (ui/database.py: data/ranks.json, each entry's "id", "name",
"points" and "logo"), kept in %APPDATA%\\NTE Telemetry\\ranks.json, their logos in its folder ranks.

The ranks go in the order of their points, the first at 0. The server names a rank by its row in the game's
DT_RacingTier table, "RacingRank_<tier>_<step>": four steps to a tier (RacingRank_1_1 the first rank, RacingRank_1_4
the fourth, RacingRank_2_1 the fifth...), so a row is the rank at its place in that order. A player who drops below
a rank's points keeps it for some 32-125 more (the table's DowngradeBufferScore), so a rank told from points alone may
be one too low for a player just under a step: the player's own is the one the server names (capture/ranking.py)."""
import os
import threading
import urllib.request

from ui.database import TIMEOUT, Names
from ui.prefs import data_dir

STEPS = 4  # ranks to a tier


def entry(e):
    try:
        rank = dict(name=str(e["name"]), points=int(e["points"]), logo=str(e.get("logo") or ""))
    except (KeyError, TypeError, ValueError):
        return []
    return [(e["id"], rank)] if e.get("id") else []


class Ranks(Names):
    """The ranks, and their logos fetched along with them."""

    def __init__(self):
        super().__init__(("ranks",), "ranks.json", entry)
        self.logos = os.path.join(data_dir(), "ranks")

    def fetch(self):
        super().fetch()
        got = False
        for r in list(self.names.values()):
            path = self.logo_path(r)
            if not path or os.path.exists(path):
                continue
            try:
                os.makedirs(self.logos, exist_ok=True)
                req = urllib.request.Request(r["logo"], headers={"User-Agent": "NTE-Telemetry"})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as f:
                    data = f.read()
                tmp = path + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, path)
                got = True
            except OSError:
                continue  # offline: next start
        if got:
            self.changed.emit()

    def logo_path(self, rank):
        """Where rank's logo is kept (whether there yet or not), or None if it has none."""
        name = os.path.basename(rank.get("logo", "").split("?")[0])
        return os.path.join(self.logos, name) if name else None

    def ordered(self):
        return sorted((r for r in self.names.values() if isinstance(r, dict)), key=lambda r: r["points"])


_ranks = None


def ranks():
    """The one Ranks of the app."""
    global _ranks
    if _ranks is None:
        _ranks = Ranks()
    return _ranks


def from_points(points):
    """The rank a player with points is at, as dict(name, points, logo), or None while the ranks aren't known."""
    return next((r for r in reversed(ranks().ordered()) if r["points"] <= points), None)


def from_row(row):
    """The rank the server names by its row ("RacingRank_3_2"), or None (not known)."""
    try:
        _, tier, step = row.split("_")
        k = (int(tier) - 1) * STEPS + int(step) - 1
    except (AttributeError, ValueError):
        return None
    order = ranks().ordered()
    return order[k] if 0 <= k < len(order) else None


def logo(rank):
    """The file of rank's logo, or None while it isn't there."""
    path = ranks().logo_path(rank) if rank else None
    return path if path and os.path.exists(path) else None

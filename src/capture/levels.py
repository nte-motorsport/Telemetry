"""Which game world (UE level) a server sends, from the level's path in its packets.

The server names its level in plain text, as UE strings:
  - right after the client connects (the 5th packet or so, 0.2-0.3 s in), with the game mode after it:
        /Game/Maps/<folders>/<level>
  - again and again while driving, as world partition cells stream in (every 3-8 s at most):
        /Game/Maps/<folders>/<level>/_Generated_/<cell id>
Found in a capture going test drive -> main world -> test drive (2026-11-03): each world its own level, the
same one for both test drives. Which map goes with which level, the map packs say (ui/world_map.py).
"""
import re

MARK = b"/Game/Maps/"
PATH = re.compile(rb"/Game/Maps/[A-Za-z0-9_/]+")
CELLS = "/_Generated_/"


def find_level(payload):
    """The level a packet names, or None. Cheap for the packets that don't (nearly all): one substring search."""
    if MARK not in payload:
        return None
    m = PATH.search(payload)
    if not m:
        return None
    path = m.group().decode("ascii")
    return path.split(CELLS)[0].rstrip("/") or None

"""Which game world (UE level) a server sends, from the level's path in its packets.

The server names its level in plain text, as UE strings:
  - right after the client connects (the 5th packet or so, 0.2-0.3 s in), with the game mode after it:
        /Game/Maps/<folders>/<level>\\0 <length> /Game/Blueprints/GameMode/...
  - again and again while driving, as world partition cells stream in (every 3-8 s at most):
        /Game/Maps/<folders>/<level>/_Generated_/<cell id>
Found in a capture going test drive -> main world -> test drive (2026-11-03): each world its own level, the
same one for both test drives. Which map goes with which level, the map packs say (ui/world_map.py).

The main world holds levels of its own too, buildings put in it as level instances (2026-11-09: a race on the
main world was saved as DLC_Detached_House_InDoor): the server names them as well, as
/Temp/Game/Maps/<folders>/<level>_LevelInstance_<hash>, and their cells as above, with no game mode after them.
So only the path the game mode follows is the world for sure; a cell's is a guess (see the counting in
capture/live_source.py), for when the capture began after the client connected.
"""
import re

MARK = b"/Game/Maps/"
PATH = re.compile(rb"/Game/Maps/[A-Za-z0-9_/]+")
CELLS = "/_Generated_/"
TEMP = b"/Temp"  # before /Game/Maps/: a level instance, a level inside the world
GAME_MODE = re.compile(rb"\x00[\x00-\xff]{4}/Game/Blueprints/GameMode/")  # the string after the world's path


def find_level(payload):
    """(the level a packet names, True if it's the world for sure: the game mode follows it), or None.
    Cheap for the packets that don't name one (nearly all): one substring search."""
    if MARK not in payload:
        return None
    for m in PATH.finditer(payload):
        if payload[max(0, m.start() - len(TEMP)):m.start()] == TEMP:
            continue
        path = m.group().decode("ascii").split(CELLS)[0].rstrip("/")
        if path:
            return path, bool(GAME_MODE.match(payload, m.end()))
    return None

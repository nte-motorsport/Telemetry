"""A race's checkpoints: which of the game's sets of them the race is run through, from the race server naming them.

The checkpoints are actors of the race's level, "BP_RaceCheckPointActor_C" (a box a car must pass through, its
CheckpointIndex its place in the lap, bIsFinishCheckPoint the finish line), found in the game's files
(assets/checkpoints.json: each set's level, the race track it was matched to and its laps, and every checkpoint's
name, index, middle x, y in m as the capture's own positions are, yaw and box half extents in m). A level may hold
more than one set (DLC_RT_C1: one each way round; the open world: one each race track), and nothing in the race's
data says which; but the race server names the race's checkpoint actors as it streams them to the player, the first
as the race starts ("BP_RaceCheckPointActor_C_UAID_08BFB8415EBAF1CF02_1570868598", a UE string at any bit; 2026-11-14,
10 races on 5 tracks: each named its own set's, by the full name), and no two sets share a name. So the first one
named tells the set. They come with no position: those are only in the game's files."""
import json
import os

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
MARK = b"BP_RaceCheckPointActor_C_UAID_"


def _shifted(marker):
    """The bytes marker leaves in a packet whichever bit it starts at: for each of the 8, the bytes it fills whole."""
    v = int.from_bytes(marker, "little")
    return [marker] + [(v << k).to_bytes(len(marker) + 1, "little")[1:len(marker)] for k in range(1, 8)]


MARKS = _shifted(MARK)
_sets = None  # set id -> dict(level, track, laps, checkpoints)
_by_name = None  # checkpoint actor name -> set id


def sets():
    global _sets, _by_name
    if _sets is None:
        try:
            with open(os.path.join(ASSETS, "checkpoints.json"), encoding="utf-8") as f:
                _sets = json.load(f)
        except (OSError, ValueError):
            _sets = {}
        _by_name = {c["name"]: sid for sid, s in _sets.items() for c in s["checkpoints"]}
    return _sets


def names(payload):
    """The checkpoint actors' names in one server packet."""
    if not any(m in payload for m in MARKS):
        return []
    n = int.from_bytes(payload, "little")
    out = []
    for k in range(8):
        data = (n >> k).to_bytes(len(payload), "little")
        i = data.find(MARK)
        while i >= 0:
            end = data.find(b"\x00", i)
            if end > i:
                out.append(data[i:end].decode("ascii", "replace"))
            i = data.find(MARK, i + 1)
    return out


def find(payload):
    """dict(id, level, track, laps, checkpoints) of the set a checkpoint the packet names is of, or None."""
    sets()
    for name in names(payload):
        sid = _by_name.get(name)
        if sid:
            return dict(sets()[sid], id=sid)
    return None

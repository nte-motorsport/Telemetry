"""The game's track names, by the row of its track table the race server names (capture/roster.py TRACK,
"Track003_02_pvp") or the race track's level ("DLC_RT_C2"), from the NTE Motorsport database (ui/database.py:
data/tracks.json, each entry's "game_id", a list of every row of that track, and "name"), kept in
%APPDATA%\\NTE Telemetry\\tracks.json. A track the database doesn't have shows by its id."""
from ui.database import Names


def entry(e):
    ids = e.get("game_id")
    if isinstance(ids, str):
        ids = [ids]
    return [(i, e["name"]) for i in ids or [] if i and e.get("name")]


_tracks = None


def tracks():
    """The one Names of the app's tracks."""
    global _tracks
    if _tracks is None:
        _tracks = Names(("tracks",), "tracks.json", entry)
    return _tracks


def track_name(track):
    """The name of the track with game id track ("Track003_02_pvp" -> "Hethereau Track 2"), track itself if not
    known, None for no track."""
    return (tracks().get(track) or track) if track else None

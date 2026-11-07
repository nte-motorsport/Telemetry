"""Recorded online races, one gzipped JSON file each in %APPDATA%\\NTE Telemetry\\replays.

A replay: {"version": 1, "started": "2026-10-30T18:05:12", "duration": s,
           "me": [[t, x, y, z, km/h], ...], "rivals": {"1": [[t, x, y, z, km/h or null], ...], ...},
           "level": "/Game/Maps/..." (the game world, when it was known; replays before 2026-11-03 have none),
           "field": [{"car": "Vehicle026", "name": "...", "bot": false}, ...] (the race's entrants, when they
           were known: replays from 2026-11-04 on),
           "bots": ["2", ...] (the rivals the game drives, from 2026-11-05 on; left out when there were none),
           "names": {"2": "...", ...} (the rivals' names, those the capture could match: from 2026-11-06 on),
           "track": "Track003_02_pvp" (the track, a row of the game's DT_RaceTrack table, when it was known: from
           2026-11-07 on; ui/tracks.py names it)}
with t in seconds from the start of the recording.

Next to a replay, with the same name, may be its raw traffic: <name>.pcap.gz, every packet the capture saw while
the race was recorded (Settings > Recording)."""
import gzip
import json
import os

from ui.prefs import data_dir


class ReplayStore:
    def __init__(self, path=None):
        self.dir = path or os.path.join(data_dir(), "replays")
        os.makedirs(self.dir, exist_ok=True)
        self.meta = {}  # path -> (mtime, summary), so the list doesn't reread every file
        for name in os.listdir(self.dir):  # raw traffic of a race the app didn't get to finish (it was closed hard)
            if name.endswith(".pcap.gz.tmp"):
                try:
                    os.remove(os.path.join(self.dir, name))
                except OSError:
                    pass

    def name(self, started):
        """A replay's file name, without .json.gz: when the race started."""
        return started.replace(":", "-").replace("T", "_")

    @staticmethod
    def raw_path(path):
        """Where the raw traffic of the replay at path is."""
        return path[:-len(".json.gz")] + ".pcap.gz"

    def raw_tmp(self, started):
        """Where the raw traffic of a race being recorded goes until the race is kept."""
        return os.path.join(self.dir, self.name(started) + ".pcap.gz.tmp")

    def save(self, replay, raw=None):
        """Write a replay; raw: the raw_tmp() file of its traffic, if it was recorded, moved next to it."""
        path = os.path.join(self.dir, self.name(replay["started"]) + ".json.gz")
        tmp = path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(replay, f, separators=(",", ":"))
        os.replace(tmp, path)
        if raw:
            os.replace(raw, self.raw_path(path))
        return path

    def load(self, path):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)

    def delete(self, path):
        os.remove(path)
        if os.path.exists(self.raw_path(path)):
            os.remove(self.raw_path(path))
        self.meta.pop(path, None)

    def list(self):
        """[(path, dict(started, duration, track, raw))], newest first; unreadable files are left out. track: the
        game's id of the track, or None; raw: the raw traffic was recorded too."""
        out = []
        for name in sorted(os.listdir(self.dir), reverse=True):
            if not name.endswith(".json.gz"):
                continue
            path = os.path.join(self.dir, name)
            mtime = os.path.getmtime(path)
            cached = self.meta.get(path)
            if not cached or cached[0] != mtime:
                try:
                    r = self.load(path)
                    cached = (mtime, dict(started=r["started"], duration=r["duration"],
                                          track=r.get("track") or own_track(r.get("level"))))
                except (OSError, ValueError, KeyError, TypeError, EOFError):
                    continue
                self.meta[path] = cached
            out.append((path, dict(cached[1], raw=os.path.exists(self.raw_path(path)))))
        return out


def own_track(level):
    """The track of a level that is a race track and nothing else ("/Game/Maps/Map_DLC/DLC_RaceTrack/DLC_RT_C2"):
    its name, as the game's track table has it too; None for any other level."""
    name = (level or "").rsplit("/", 1)[-1]
    return name if name.startswith("DLC_RT_") else None

"""Recorded online races, one gzipped JSON file each in %APPDATA%\\NTE Telemetry\\replays.

A replay: {"version": 1, "started": "2026-10-30T18:05:12", "duration": s,
           "me": [[t, x, y, z, km/h], ...], "rivals": {"1": [[t, x, y, z, km/h or null], ...], ...}}
with t in seconds from the start of the recording."""
import gzip
import json
import os

from ui.prefs import data_dir


class ReplayStore:
    def __init__(self, path=None):
        self.dir = path or os.path.join(data_dir(), "replays")
        os.makedirs(self.dir, exist_ok=True)
        self.meta = {}  # path -> (mtime, summary), so the list doesn't reread every file

    def save(self, replay):
        name = replay["started"].replace(":", "-").replace("T", "_") + ".json.gz"
        path = os.path.join(self.dir, name)
        tmp = path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(replay, f, separators=(",", ":"))
        os.replace(tmp, path)
        return path

    def load(self, path):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)

    def delete(self, path):
        os.remove(path)
        self.meta.pop(path, None)

    def list(self):
        """[(path, dict(started, duration, rivals))], newest first; unreadable files are left out."""
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
                    cached = (mtime, dict(started=r["started"], duration=r["duration"], rivals=len(r["rivals"])))
                except (OSError, ValueError, KeyError, TypeError, EOFError):
                    continue
                self.meta[path] = cached
            out.append((path, cached[1]))
        return out

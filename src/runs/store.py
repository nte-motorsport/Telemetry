"""Saved runs and the reference run, kept in %APPDATA%\\NTE Telemetry\\runs.json."""
import json
import os

from runs.model import Run


def store_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "NTE Telemetry")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "runs.json")


class RunStore:
    def __init__(self, palette, path=None):
        self.palette = palette  # colours handed out to new runs, first unused one wins
        self.path = path or store_path()
        self.runs, self.ref_id = [], None
        try:
            s = json.load(open(self.path, encoding="utf-8"))
            self.runs = [Run(r["name"], r["color"], r["pts"], r["id"], r.get("visible", True)) for r in s["runs"]]
            self.ref_id = s.get("ref_id")
        except (OSError, ValueError, KeyError):
            pass

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(runs=[r.to_json() for r in self.runs], ref_id=self.ref_id), f, ensure_ascii=False)
        os.replace(tmp, self.path)

    @property
    def ref(self):
        return next((r for r in self.runs if r.id == self.ref_id), None)

    def add(self, name, pts):
        used = {r.color for r in self.runs}
        color = next((c for c in self.palette if c not in used), self.palette[len(self.runs) % len(self.palette)])
        r = Run(name, color, pts)
        self.runs.append(r)
        if self.ref is None:
            self.ref_id = r.id
        self.save()
        return r

    def remove(self, run):
        self.runs.remove(run)
        if self.ref_id == run.id:
            self.ref_id = self.runs[0].id if self.runs else None
        self.save()

"""A recorded run: points along the drive, its stats and comparison with another run by distance."""
import time

import numpy as np

KEYS = ("time", "dist", "x", "y", "z", "v", "gl", "ga", "yaw", "t", "hdg", "slope")


def point(time_s, dist, d):
    """One run point from a tracker sample, with the run's own time and distance."""
    return dict(time=round(time_s, 3), dist=round(dist, 2), x=d["x"], y=d["y"], z=d["z"], v=d["speed_kmh"],
                gl=d["g_long"], ga=d["g_lat"], yaw=d["yaw_rate"], t=d["t"], hdg=d.get("heading", 0.0),
                slope=d.get("slope_deg", 0.0))


class Recorder:
    """Turns live samples into run points: time from the client clock, distance from the odometer."""

    def __init__(self):
        self.pts, self.odo0, self.last_t = [], None, None

    def add(self, d):
        if self.odo0 is None:
            self.odo0 = d["odo_km"]
        if self.pts:
            dt = d["t"] - self.last_t
            time_s = self.pts[-1]["time"] + (dt if 0 < dt < 3 else 0.1)
        else:
            time_s = 0.0
        self.last_t = d["t"]
        self.pts.append(point(time_s, (d["odo_km"] - self.odo0) * 1000, d))

    @property
    def time(self):
        return self.pts[-1]["time"] if self.pts else 0.0

    @property
    def dist(self):
        return self.pts[-1]["dist"] if self.pts else 0.0


class Run:
    def __init__(self, name, color, pts, rid=None, visible=True):
        self.id = rid or f"{time.time():.6f}"
        self.name, self.color, self.visible, self.pts = name, color, visible, pts
        self.a = {k: np.array([p.get(k, 0.0) for p in pts], dtype=float) for k in KEYS}

    def at(self, dist, key):
        """Value of key at a distance along the run (NaN outside it)."""
        d = self.a["dist"]
        if not len(d) or dist < d[0] or dist > d[-1]:
            return float("nan")
        return float(np.interp(dist, d, self.a[key]))

    def stats(self):
        a = self.a
        dist, t = a["dist"][-1], a["time"][-1]
        return dict(dist=dist / 1000, time=t, vmax=a["v"].max(), vavg=dist / t * 3.6 if t > 0 else 0.0,
                    ga=np.abs(a["ga"]).max(), brake=min(0.0, a["gl"].min()), acc=max(0.0, a["gl"].max()))

    def delta_to(self, ref):
        """Time gained or lost against the reference run at each of this run's points."""
        d = self.a["dist"]
        if ref is self:
            return d, np.zeros_like(d)
        # the reference's time at each distance it first reaches (standing still repeats a distance)
        rd, first = np.unique(ref.a["dist"], return_index=True)
        dt = self.a["time"] - np.interp(d, rd, ref.a["time"][first])
        dt[(d < rd[0]) | (d > rd[-1])] = np.nan
        return d, dt

    def to_json(self):
        return dict(id=self.id, name=self.name, color=self.color, visible=self.visible, pts=self.pts)

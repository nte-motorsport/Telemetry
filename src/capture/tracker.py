"""Turning a stream of position fixes into car telemetry.

Inputs (throttle/brake/steering/gear/rpm) are not sent over the network, so everything
(speed, g-forces, yaw rate, slope, odometer) is derived from position.
"""
import math

FIELDS = ("t", "x", "y", "z", "speed_kmh", "heading", "vz", "slope_deg", "g_long", "g_lat",
          "yaw_rate", "slip_deg", "cam_yaw", "odo_km")


def wrap180(a):
    return (a + 180) % 360 - 180


class Tracker:
    def __init__(self, alpha=0.35):
        self.prev = None
        self.alpha = alpha
        self.v = [0.0, 0.0, 0.0]  # smoothed velocity, m/s
        self.acc = [0.0, 0.0]     # smoothed (long, lat) accel, m/s^2
        self.heading = 0.0
        self.yaw_rate = 0.0
        self.odo = 0.0

    @staticmethod
    def consistent(a, b):
        """b plausibly follows a: 0 < dt < 3 s and under 200 m/s."""
        dt = b[0] - a[0]
        return 0 < dt < 3 and math.dist(a[1:4], b[1:4]) < 200 * dt + 1

    def pick(self, cands):
        if self.prev:
            ok = [c for c in cands if self.consistent(self.prev, c)]
            if ok:
                self.misses = 0
                return min(ok, key=lambda c: c[0])
            self.misses = getattr(self, "misses", 0) + 1
            if self.misses < 20:
                return None
        # (re)seed: accept a fix only once two packets in a row agree (reconnect / teleport)
        seed = getattr(self, "seed", None)
        for c in cands:
            if seed and self.consistent(seed, c):
                self.prev, self.seed, self.misses = seed[:4], None, 0
                return c
        self.seed = cands[-1]
        return None

    def update(self, ts, x, y, z, cam_yaw):
        out = None
        if self.prev:
            pts, px, py, pz = self.prev
            dt = ts - pts
            if dt <= 0:
                return None
            if dt < 2:
                k = self.alpha
                nv = [(x - px) / dt, (y - py) / dt, (z - pz) / dt]
                ov = self.v
                self.v = [o + k * (n - o) for o, n in zip(ov, nv)]
                self.odo += math.dist((x, y, z), (px, py, pz))
                vxy = math.hypot(self.v[0], self.v[1])
                if vxy > 1.0:
                    hd = math.degrees(math.atan2(self.v[1], self.v[0]))
                    self.yaw_rate += k * (wrap180(hd - self.heading) / dt - self.yaw_rate)
                    self.heading = hd % 360
                    hx, hy = self.v[0] / vxy, self.v[1] / vxy
                    ax, ay = (self.v[0] - ov[0]) / dt, (self.v[1] - ov[1]) / dt
                    lon, lat = ax * hx + ay * hy, -ax * hy + ay * hx
                    self.acc = [a + k * (n - a) for a, n in zip(self.acc, (lon, lat))]
                else:
                    self.yaw_rate *= 1 - k
                    self.acc = [a * (1 - k) for a in self.acc]
                speed = math.sqrt(sum(c * c for c in self.v))
                out = dict(t=round(ts, 3), x=round(x, 2), y=round(y, 2), z=round(z, 2),
                           speed_kmh=round(speed * 3.6, 1), heading=round(self.heading, 1),
                           vz=round(self.v[2], 2),
                           slope_deg=round(math.degrees(math.atan2(self.v[2], vxy)) if vxy > 1 else 0.0, 1),
                           g_long=round(self.acc[0] / 9.81, 2), g_lat=round(self.acc[1] / 9.81, 2),
                           yaw_rate=round(self.yaw_rate, 1),
                           slip_deg=round(wrap180(cam_yaw - self.heading), 1) if vxy > 1 else 0.0,
                           cam_yaw=round(cam_yaw, 1), odo_km=round(self.odo / 1000, 3))
        self.prev = (ts, x, y, z)
        return out

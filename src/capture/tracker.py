"""Turning a stream of position fixes into car telemetry.

Inputs (throttle/brake/steering/gear/rpm) are not sent over the network, so everything
(speed, g-forces, yaw rate, slope, odometer) is derived from position.
"""
import math
from collections import deque

FIELDS = ("t", "x", "y", "z", "speed_kmh", "heading", "vz", "slope_deg", "g_long", "g_lat",
          "yaw_rate", "slip_deg", "cam_yaw", "odo_km", "in_car", "jump")


class CarDetector:
    """In a car or on foot, from how often the client sends its position (a capture of running, driving
    and standing, and an online race): on foot it sends every frame, ~17 ms apart; in a car every
    67-100 ms, with a few extra fixes in between. On foot it also sends at 100 ms for a moment after
    stopping, so the decision looks at the share of time over the last SPAN seconds, with a gap between
    the on and off levels."""
    SPAN = 1.5          # seconds of client time looked at
    ON, OFF = 0.7, 0.3  # share of that time in car-like intervals to switch to car / back to foot
    GAP = 0.3           # longer intervals are pauses in sending (loading, menus), not a send rate
    CAR_LO, CAR_HI = 0.045, 0.16  # car-like intervals: ~100 ms when free roaming, ~67 ms in an online race

    def __init__(self):
        self.win = deque()  # (client ts, interval before it)
        self.prev = None
        self.in_car = False

    def update(self, ts):
        if self.prev is not None:
            dt = ts - self.prev
            if dt < 0:  # a new session: the client clock started over
                self.win.clear()
            elif dt < self.GAP:
                self.win.append((ts, dt))
        self.prev = ts
        while self.win and ts - self.win[0][0] > self.SPAN:
            self.win.popleft()
        total = sum(dt for _, dt in self.win)
        car = sum(dt for _, dt in self.win if self.CAR_LO <= dt < self.CAR_HI) / total if total else 0.0
        if not self.in_car and total >= self.SPAN * 0.8 and car >= self.ON:
            self.in_car = True
        elif self.in_car and car <= self.OFF:
            self.in_car = False
        return self.in_car


def wrap180(a):
    return (a + 180) % 360 - 180


class Tracker:
    # Velocity comes from the move over this long, not from one step: client timestamps are whole frames
    # and the position isn't taken exactly then, so a single 67 ms step reads as 120, then 212 km/h.
    VEL_SPAN = 0.4

    def __init__(self, alpha=0.35):
        self.prev = None
        self.recent = deque()  # (ts, x, y, z) over the last VEL_SPAN
        self.alpha = alpha
        self.v = [0.0, 0.0, 0.0]  # smoothed velocity, m/s
        self.acc = [0.0, 0.0]     # smoothed (long, lat) accel, m/s^2
        self.heading = None  # unknown until the car first moves; then no yaw rate is made up from 0°
        self.moving = False  # heading is fresh; after a stop the direction may have changed unseen
        self.yaw_rate = 0.0
        self.odo = 0.0
        self.car = CarDetector()
        self.jumped = False  # the next sample is the first one after a teleport

    def reset_motion(self):
        """Forget the smoothed motion: after a teleport (a test drive moves you to another world and
        restarts the client clock) it belongs to the old place and would read as huge speed, g and yaw."""
        self.v = [0.0, 0.0, 0.0]
        self.acc = [0.0, 0.0]
        self.recent.clear()
        self.heading = None
        self.yaw_rate = 0.0
        self.car = CarDetector()
        self.jumped = True

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
                if self.prev:  # tracking was lost and found somewhere else: a teleport or a reconnect
                    self.reset_motion()
                self.prev, self.seed, self.misses = seed[:4], None, 0
                return c
        self.seed = cands[-1]
        return None

    def update(self, ts, x, y, z, cam_yaw):
        out = None
        in_car = self.car.update(ts)
        if self.prev:
            pts, px, py, pz = self.prev
            dt = ts - pts
            if dt <= 0:
                return None
            if in_car and dt < 0.05:
                # a car sends every 67-100 ms plus the odd fix a frame later; over such a short
                # interval position noise reads as a jump in speed (tens of g), so skip that fix
                return None
            if dt >= 2:  # a pause in sending: the move across it says nothing about speed
                self.recent.clear()
            else:
                k = self.alpha
                if not self.recent:
                    self.recent.append(self.prev)
                self.recent.append((ts, x, y, z))
                while len(self.recent) > 2 and ts - self.recent[1][0] >= self.VEL_SPAN:
                    self.recent.popleft()
                bt, bx, by, bz = self.recent[0]
                nv = [(x - bx) / (ts - bt), (y - by) / (ts - bt), (z - bz) / (ts - bt)]
                ov = self.v
                self.v = [o + k * (n - o) for o, n in zip(ov, nv)]
                if in_car:  # the odometer counts driving only
                    self.odo += math.dist((x, y, z), (px, py, pz))
                vxy = math.hypot(self.v[0], self.v[1])
                if vxy > 1.0:
                    hd = math.degrees(math.atan2(self.v[1], self.v[0]))
                    if self.heading is not None and self.moving:
                        self.yaw_rate += k * (wrap180(hd - self.heading) / dt - self.yaw_rate)
                    self.heading = hd % 360
                    self.moving = True
                    hx, hy = self.v[0] / vxy, self.v[1] / vxy
                    ax, ay = (self.v[0] - ov[0]) / dt, (self.v[1] - ov[1]) / dt
                    lon, lat = ax * hx + ay * hy, -ax * hy + ay * hx
                    self.acc = [a + k * (n - a) for a, n in zip(self.acc, (lon, lat))]
                else:
                    self.moving = False
                    self.yaw_rate *= 1 - k
                    self.acc = [a * (1 - k) for a in self.acc]
                speed = math.sqrt(sum(c * c for c in self.v))
                out = dict(t=round(ts, 3), x=round(x, 2), y=round(y, 2), z=round(z, 2),
                           speed_kmh=round(speed * 3.6, 1), heading=round(self.heading or 0.0, 1),
                           vz=round(self.v[2], 2),
                           slope_deg=round(math.degrees(math.atan2(self.v[2], vxy)) if vxy > 1 else 0.0, 1),
                           g_long=round(self.acc[0] / 9.81, 2), g_lat=round(self.acc[1] / 9.81, 2),
                           yaw_rate=round(self.yaw_rate, 1),
                           slip_deg=round(wrap180(cam_yaw - self.heading), 1) if vxy > 1 else 0.0,
                           cam_yaw=round(cam_yaw, 1), odo_km=round(self.odo / 1000, 3), in_car=in_car,
                           jump=self.jumped)
                self.jumped = False
        self.prev = (ts, x, y, z)
        return out

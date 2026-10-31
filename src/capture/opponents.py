"""Other racers in an online race. The server sends every player the others' state in records found in
many of its packets (a few per packet, at offsets that depend on the packet). Each record has a fixed
signature, an id that stays with one car, the server's clock and the car's position:

  pos-200 .. pos-188  13 bits, one of SIGS      pos-187 .. pos-176  car id (12 bits)
  pos-72  .. pos-41   server time, ms (32 bits)  pos .. pos+95       x, y, z, float32 in centimetres

Found by matching two online race captures (3 rivals each) against their tracks. The id is clean in
every record, whereas telling cars apart by distance mixes them up once they spread out. 13 bits of
signature still match by chance now and then, the server sends empty (0, 0, 0) records and some things
that never move, and in some races the player's own car too; Opponents sorts those out."""
import math
import statistics
import struct
from collections import deque

from capture import bits

# 2074 in every race; 2096 and 2091 in three of four captured races (2026-10-30/31), carrying the same ids
# and positions that agree with the 2074 records' tracks, as often again as 2074 in all. They fill in
# between 2074 records; the server's own long silences about a car (a minute and more) they do not.
SIGS = (2074, 2091, 2096)
NEAR = 3000.0  # m: a position this far from the player is not a car in the same race


def decode(payload):
    """[(car id, server time in s, (x, y, z) in metres)] for every record in one server packet that may be
    a car."""
    n = int.from_bytes(payload, "little")
    out = []
    for o in (s + 200 for s in bits.find(payload, SIGS, 13, 0, len(payload) * 8 - 296)):
        p = tuple(struct.unpack("<f", struct.pack("<I", (n >> (o + 32 * i)) & 0xFFFFFFFF))[0] / 100
                  for i in range(3))
        if all(math.isfinite(c) and abs(c) < 1e5 for c in p) and any(abs(c) > 0.01 for c in p):
            out.append(((n >> (o - 187)) & 0xFFF, ((n >> (o - 72)) & 0xFFFFFFFF) / 1000, p))
    return out


class Opponents:
    """Each racer's latest positions, under a number (1, 2, 3...) given in the order they show up. A car keeps
    its number if it drops out for a while (the server updates far-away cars rarely) and a number is never
    given to another car, so someone who joins after another left doesn't carry on that one's lines."""
    SPEED_SPAN = 1.0  # s of positions the speed is measured over
    TIMEOUT = 5.0     # s without an update before a car is dropped
    MAX_SPEED = 120   # m/s: a longer step is either the server moving the car (it does, by 60-80 m) or a
                      # bad record; it counts once the next position agrees with it
    CONFIRM = 10      # records in a row that follow on from each other before an id counts as a car
    RECONFIRM = 2     # the same, for an id already shown that dropped out for a while
    SELF_DIST = 4.0   # m: an id whose median distance to the player is under this is the player's own
                      # car, which the server echoes about 1 m off (a median of 2.7 m at most, at
                      # 200-250 km/h, in two races); rivals were 6+ m away when first shown, on the grid
                      # or right after the start, and a rival once shown stays shown, however close it
                      # gets in a duel (the old rule, "within 15 m most of the time", hid one for 30 s)
    SELF_SPAN = 20    # latest distances that median is taken over
    MOVED = 20.0      # m from where an id was first seen before it counts as a car: some things in the
                      # race send the same records but never move (they show up mid-race, though) ...
    GRID = 30.0       # m: ... a car standing this close to the player while the player stands too (the
                      # starting grid) counts at once
    STILL = 1.0       # m: standing means keeping within this over the last CONFIRM records
    CLOCK_STEP = 2.0  # s: a record this much older than its car's clock says, arriving now and carrying on
                      # its track, means the car's clock stepped back. Each car's time is its own: before
                      # the start some run 3-4 s ahead and fall in with the rest at the start, so one
                      # offset for all (as before) let such a car make every other look 4 s stale and be
                      # dropped at once (a rival missing for 20 s after the start); resent records are
                      # at most ~1 s old

    def __init__(self):
        # car id -> dict(num (None until confirmed), hist=deque of (server t, x, y, z), pending,
        # good=records that followed on, dists=the latest of those records' distances to the player,
        # start=first position, moved=has got MOVED away from it, still=the latest (position, player's
        # position) of the records that followed on, off=local time minus this car's time at the
        # quickest delivery seen, at=arrival of its latest record)
        self.cars = {}
        self.nums = {}  # car id -> number, for as long as this object lives (one server)

    def fits(self, a, t, p):
        """p at server time t plausibly follows a; a chance match carries a made-up time, so the gap is
        kept short too."""
        dt = t - a[0]
        return 0 < dt < 3 and math.dist(a[1:], p) <= self.MAX_SPEED * max(dt, 0.05) + 5

    def on_grid(self, still):
        """The car and the player have both stood still, close together, over the last CONFIRM records."""
        if len(still) < self.CONFIRM:
            return False
        p0, me0 = still[0]
        return (math.dist(p0, me0) < self.GRID
                and all(math.dist(p, p0) < self.STILL and math.dist(me, me0) < self.STILL for p, me in still))

    def update(self, t, records, me=None):
        """Take one packet's [(car id, server time, (x, y, z))], its arrival time t and the player's own
        (x, y, z). Returns every confirmed rival as {number: dict(t, x, y, z, speed_kmh)}, t being when
        that car's position was sent, on the local clock."""
        for cid, st, p in records:
            car = self.cars.get(cid)
            if car is None:
                self.cars[cid] = dict(num=None, hist=deque([(st, *p)]), pending=None, good=0,
                                      dists=deque(maxlen=self.SELF_SPAN), start=p, moved=False,
                                      still=deque(maxlen=self.CONFIRM), off=t - st, at=t)
                continue
            h = car["hist"]
            lag = t - st
            if st <= h[-1][0]:  # a record sent again, overtaken by a newer one, or the car's clock stepped back
                if (lag > car["off"] + self.CLOCK_STEP
                        and math.dist(h[-1][1:], p) <= self.MAX_SPEED * (t - car["at"]) + 5):
                    h.clear()
                    h.append((st, *p))
                    car["off"], car["at"], car["pending"] = lag, t, None
                continue
            if self.fits(h[-1], st, p):
                # the clock is only trusted from records that carry on a track: chance matches hold noise
                car["off"] = min(car["off"], lag)
                car["at"] = t
                h.append((st, *p))
                car["pending"] = None
                car["good"] += 1
                if me is not None:
                    car["dists"].append(math.dist(me, p))
                    car["still"].append((p, me))
                car["moved"] = (car["moved"] or math.dist(car["start"], p) > self.MOVED
                                or self.on_grid(car["still"]))
            elif car["pending"] and self.fits(car["pending"], st, p):
                h.clear()  # moved (or its clock stepped ahead), and the next record agrees: carry on from here
                h.extend((car["pending"], (st, *p)))
                car["pending"] = None
                car["off"], car["at"] = lag, t
            else:
                car["pending"] = (st, *p)
                if car["num"] is None:  # a chance match, not a car: start counting again
                    car["good"] = 0
                    car["dists"].clear()
                    car["still"].clear()
        out = {}
        for cid, car in list(self.cars.items()):
            h = car["hist"]
            local = h[-1][0] + car["off"]
            if t - local > self.TIMEOUT:
                del self.cars[cid]
                continue
            if car["num"] is None:
                if cid in self.nums:  # shown before: a rival that was out of range for a while
                    if car["good"] < self.RECONFIRM:
                        continue
                elif (car["good"] < self.CONFIRM or not car["moved"] or not car["dists"]
                      or statistics.median(car["dists"]) < self.SELF_DIST):
                    continue  # not shown (yet): unconfirmed, never moved, or the player's own car
                car["num"] = self.nums.setdefault(cid, len(self.nums) + 1)
            while len(h) > 2 and h[-1][0] - h[1][0] >= self.SPEED_SPAN:
                h.popleft()
            span = h[-1][0] - h[0][0]
            speed = math.dist(h[0][1:], h[-1][1:]) / span * 3.6 if span > 0.3 else None
            out[car["num"]] = dict(t=local, x=h[-1][1], y=h[-1][2], z=h[-1][3], speed_kmh=speed)
        return out

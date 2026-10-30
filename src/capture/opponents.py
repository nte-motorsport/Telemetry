"""Other racers in an online race. The server sends every player the others' state in records found in
many of its packets (a few per packet, at offsets that depend on the packet). Each record has a fixed
signature, an id that stays with one car, the server's clock and the car's position:

  pos-200 .. pos-188  13 bits, always SIG       pos-187 .. pos-176  car id (12 bits)
  pos-72  .. pos-41   server time, ms (32 bits)  pos .. pos+95       x, y, z, float32 in centimetres

Found by matching two online race captures (3 rivals each) against their tracks. The id is clean in
every record, whereas telling cars apart by distance mixes them up once they spread out. 13 bits of
signature still match by chance now and then, the server sends empty (0, 0, 0) records and some things
that never move, and in some races the player's own car too; Opponents sorts those out."""
import math
import struct
from collections import deque

SIG = 2074
NEAR = 3000.0  # m: a position this far from the player is not a car in the same race


def decode(payload):
    """[(car id, server time in s, (x, y, z) in metres)] for every record in one server packet that may be
    a car."""
    n = int.from_bytes(payload, "little")
    out = []
    for o in range(200, len(payload) * 8 - 96):
        if (n >> (o - 200)) & 0x1FFF != SIG:
            continue
        p = tuple(struct.unpack("<f", struct.pack("<I", (n >> (o + 32 * i)) & 0xFFFFFFFF))[0] / 100
                  for i in range(3))
        if all(math.isfinite(c) and abs(c) < 1e5 for c in p) and any(abs(c) > 0.01 for c in p):
            out.append(((n >> (o - 187)) & 0xFFF, ((n >> (o - 72)) & 0xFFFFFFFF) / 1000, p))
    return out


class Opponents:
    """Each racer's latest positions, under a number (1, 2, 3...) given in the order they show up. A number
    is never given again, so someone who joins after another left doesn't carry on that one's lines."""
    SPEED_SPAN = 1.0  # s of positions the speed is measured over
    TIMEOUT = 5.0     # s without an update before a car is dropped
    MAX_SPEED = 120   # m/s: a longer step is either the server moving the car (it does, by 60-80 m) or a
                      # bad record; it counts once the next position agrees with it
    CONFIRM = 10      # records in a row that follow on from each other before an id counts as a car
    SELF_DIST = 15.0  # m: an id that keeps this close to the player is the player's own car
    MOVED = 20.0      # m from where an id was first seen before it counts as a car: some things in the
                      # race send the same records but never move

    def __init__(self):
        # car id -> dict(num (None until confirmed), hist=deque of (server t, x, y, z), pending,
        # good=records that followed on, near=of those, how many were right by the player,
        # start=first position, moved=has got MOVED away from it)
        self.cars = {}
        self.offset = None  # local time minus server time, at the quickest delivery seen
        self.next_num = 1

    def fits(self, a, t, p):
        """p at server time t plausibly follows a; a chance match carries a made-up time, so the gap is
        kept short too."""
        dt = t - a[0]
        return 0 < dt < 3 and math.dist(a[1:], p) <= self.MAX_SPEED * max(dt, 0.05) + 5

    def update(self, t, records, me=None):
        """Take one packet's [(car id, server time, (x, y, z))], its arrival time t and the player's own
        (x, y, z). Returns every confirmed rival as {number: dict(t, x, y, z, speed_kmh)}, t being when
        that car's position was sent, on the local clock."""
        for cid, st, p in records:
            car = self.cars.get(cid)
            if car is None:
                self.cars[cid] = dict(num=None, hist=deque([(st, *p)]), pending=None, good=0, near=0,
                                      start=p, moved=False)
                continue
            h = car["hist"]
            if st <= h[-1][0]:  # a record sent again, or overtaken by a newer one
                continue
            if self.fits(h[-1], st, p):
                # the clock is only trusted from records that carry on a track: chance matches hold noise
                lag = t - st
                if self.offset is None or lag < self.offset:
                    self.offset = lag
                elif lag > self.offset + 60:  # another server, or its clock was reset
                    self.offset = lag
                    for other in self.cars.values():
                        other["hist"] = deque([other["hist"][-1]])
                h.append((st, *p))
                car["pending"] = None
                car["good"] += 1
                car["near"] += me is not None and math.dist(me, p) < self.SELF_DIST
                car["moved"] = car["moved"] or math.dist(car["start"], p) > self.MOVED
            elif car["pending"] and self.fits(car["pending"], st, p):
                h.clear()  # moved, and the next record agrees: measure speed from here on
                h.extend((car["pending"], (st, *p)))
                car["pending"] = None
            else:
                car["pending"] = (st, *p)
                if car["num"] is None:  # a chance match, not a car: start counting again
                    car["good"] = car["near"] = 0
        out = {}
        if self.offset is None:
            return out
        for cid, car in list(self.cars.items()):
            h = car["hist"]
            local = h[-1][0] + self.offset
            if t - local > self.TIMEOUT:
                del self.cars[cid]
                continue
            if car["good"] < self.CONFIRM or not car["moved"] or car["near"] > 0.8 * car["good"]:
                continue  # not shown (yet): unconfirmed, never moved, or the player's own car
            if car["num"] is None:
                car["num"], self.next_num = self.next_num, self.next_num + 1
            while len(h) > 2 and h[-1][0] - h[1][0] >= self.SPEED_SPAN:
                h.popleft()
            span = h[-1][0] - h[0][0]
            speed = math.dist(h[0][1:], h[-1][1:]) / span * 3.6 if span > 0.3 else None
            out[car["num"]] = dict(t=local, x=h[-1][1], y=h[-1][2], z=h[-1][3], speed_kmh=speed)
        return out

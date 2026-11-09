"""Other racers in an online race. The server sends every player the others' state in records found in
many of its packets (a few per packet, at offsets that depend on the packet). Each record has a fixed
signature, an id that stays with one car, the server's clock and the car's position:

  pos-200 .. pos-188  13 bits, one of SIGS      pos-187 .. pos-176  car id (12 bits)
  pos-72  .. pos-41   server time, ms (32 bits)  pos-40  .. pos-9    HEADER (32 bits, the same in every record)
  pos-8   .. pos-1    flags: bit 2 (pos-6) set for cars the game drives (AI)
  pos .. pos+95       x, y, z, float32 in centimetres

The AI flag and the header were found by comparing a free roam session of two players (2026-11-05, each
one's capture) with races against bots: the bots, the free roam's NPCs (people and traffic, 20-30 of them
around the player) and things that never move all have it; the two players never did, in either capture.

Found by matching two online race captures (3 rivals each) against their tracks. The id is clean in
every record, whereas telling cars apart by distance mixes them up once they spread out. 13 bits of
signature match by chance now and then, which the header sorts out; the server also sends empty
(0, 0, 0) records and some things that never move, and in some races the player's own car too; Opponents
sorts those out."""
import math
import statistics
import struct
from collections import deque

import numpy as np

from capture import bits

# 2074 in every race; 2096 and 2091 in three of four captured races (2026-10-30/31), carrying the same ids
# and positions that agree with the 2074 records' tracks, as often again as 2074 in all. They fill in
# between 2074 records; the server's own long silences about a car (a minute and more) they do not.
SIGS = (2074, 2091, 2096)
NEAR = 3000.0  # m: a position this far from the player is not a car in the same race
HEADER = 0x3A24  # pos-40 .. pos-9 of every real record (in all 15 captures of 2026-11-04/05); chance matches of
                 # the signature carry noise there
AI = 1 << 2      # in the flags byte


def decode(payload):
    """[(car id, server time in s, (x, y, z) in metres, driven by the game)] for every record in one server
    packet that may be a car."""
    n = int.from_bytes(payload, "little")
    out = []
    for o in (s + 200 for s in bits.find(payload, SIGS, 13, 0, len(payload) * 8 - 296)):
        if (n >> (o - 40)) & 0xFFFFFFFF != HEADER:
            continue
        p = tuple(struct.unpack("<f", struct.pack("<I", (n >> (o + 32 * i)) & 0xFFFFFFFF))[0] / 100
                  for i in range(3))
        if all(math.isfinite(c) and abs(c) < 1e5 for c in p) and any(abs(c) > 0.01 for c in p):
            out.append(((n >> (o - 187)) & 0xFFF, ((n >> (o - 72)) & 0xFFFFFFFF) / 1000, p,
                        bool((n >> (o - 8)) & AI)))
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
    # A car held back by that rule for long is the player's own for good: at the finish the game drives the car
    # on and the player's own position stops matching it, and the echo, held back the whole race, was shown for
    # the last 3-30 s (three races of 2026-11-06)
    SELF_HOLD = 80    # updates (some 2 s of them)
    # The rule above misses the echo at speed: the player's own position is the latest one sent, every
    # 67-100 ms, so at 200+ km/h the echo reads 1-6 m away and its median crosses SELF_DIST (a friend's own
    # car shown as a rival for the second half of two races, 2026-11-05). Compared with where the player was
    # when the record was sent instead, the echo stays 0.4-0.9 m off; a rival comes within 1.5 m of that for
    # a 2 s stretch now and then (touching, in 1-2% of them), never for several in a row.
    SELF_NEAR = 1.2   # m: median distance from the player's own track, at the best of LAGS, over ...
    SELF_RECENT = 60  # ... a car's latest this many records (about 2 s)
    SELF_EVERY = 1.0  # s between looks, for a car already shown ...
    SELF_TIMES = 3    # ... and this many looks in a row that find it there make it the player's own car
    # The player has one car, so while an echo already found keeps coming no other car is it: a rival bumper to
    # bumper with the player (within 1 m of the player's own track for 3 s, 2026-11-09) was taken for a second
    # echo and hidden for the rest of the race, while the real one was still being sent
    LAGS = np.arange(-0.1, 0.31, 0.02)  # s the echo may be behind the player's own fix on the local clock
    OWN_SPAN = 5.0    # s of the player's own positions kept for that
    MOVED = 20.0      # m from where an id was first seen before it counts as a car: some things in the
                      # race send the same records but never move (they show up mid-race, though) ...
    GRID = 30.0       # m: ... a car standing this close to the player while the player stands too (the
                      # starting grid) counts at once
    STILL = 1.0       # m: standing means keeping within this over the last CONFIRM records
    AI_VOTES = 20     # a car is the game's while more of its records have the AI flag than not: a tally of
                      # +1 for each that has it and -1 for each that hasn't, held within +-AI_VOTES
    CLOCK_STEP = 2.0  # s: a record this much older than its car's clock says, arriving now and carrying on
                      # its track, means the car's clock stepped back. Each car's time is its own: before
                      # the start some run 3-4 s ahead and fall in with the rest at the start, so one
                      # offset for all (as before) let such a car make every other look 4 s stale and be
                      # dropped at once (a rival missing for 20 s after the start); resent records are
                      # at most ~1 s old

    def __init__(self):
        # car id -> dict(num (None until confirmed), hist=deque of (server t, x, y, z), pending,
        # good=records that followed on, dists=the latest of those records' distances to the player,
        # start=first position, moved=has got MOVED away from it, grid=has stood on the grid, still=the
        # latest (position, player's position) of the records that followed on, off=local time minus this
        # car's time at the quickest delivery seen, at=arrival of its latest record, recent=(local t, x, y)
        # of the latest records that followed on, ai=the game drives it, ais=the tally that says so, near=looks
        # in a row that found it on the player's own track, look=when it was last looked at, held=updates it
        # was held back for being where the player is)
        self.cars = {}
        self.nums = {}  # car id -> number, for as long as this object lives (one server)
        self.own_ids = set()  # car ids found to be the player's own car
        self.own_at = -math.inf  # when a record of one of them last arrived
        self.ai = {}  # car id -> the game drives it, for every car shown, as when first shown
        self.track = deque()  # (local t, x, y) of the player's own positions, the last OWN_SPAN s
        self.allow_ai = True  # cars the game drives count: race bots. Not in free roam, where they are NPCs

    def own(self, t, x, y):
        """The player's own position, sent at local time t."""
        if self.track and t <= self.track[-1][0]:
            return
        self.track.append((t, x, y))
        while t - self.track[0][0] > self.OWN_SPAN:
            self.track.popleft()

    def on_own_track(self, car):
        """The car's latest records lie on the player's own track, where the player was when they were sent
        (give or take LAGS): it is the player's own car."""
        if len(car["recent"]) < self.CONFIRM or len(self.track) < 2:
            return False
        r = np.array(car["recent"])
        own = np.array(self.track)
        best = math.inf
        for k in self.LAGS:
            t = r[:, 0] - k
            ok = (t >= own[0, 0]) & (t <= own[-1, 0])
            if ok.sum() < self.CONFIRM:
                continue
            d = np.hypot(r[ok, 1] - np.interp(t[ok], own[:, 0], own[:, 1]),
                         r[ok, 2] - np.interp(t[ok], own[:, 0], own[:, 2]))
            best = min(best, float(np.median(d)))
        return best < self.SELF_NEAR

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
        """Take one packet's [(car id, server time, (x, y, z), ai)], its arrival time t and the player's own
        (x, y, z). Returns every confirmed rival as {number: dict(t, x, y, z, speed_kmh, bot)}, t being when
        that car's position was sent, on the local clock, bot whether the game drives it."""
        for cid, st, p, ai in records:
            if cid in self.own_ids:
                self.own_at = t
                continue
            car = self.cars.get(cid)
            if car is None:
                self.cars[cid] = dict(num=None, hist=deque([(st, *p)]), pending=None, good=0,
                                      dists=deque(maxlen=self.SELF_SPAN), start=p, moved=False, grid=False,
                                      still=deque(maxlen=self.CONFIRM), off=t - st, at=t,
                                      recent=deque(maxlen=self.SELF_RECENT), ai=ai, ais=1 if ai else -1, held=0,
                                      near=0, look=t)
                continue
            # the flag is set now and then on a player's car too (in 1-2% of its records): by the majority
            car["ais"] = min(max(car["ais"] + (1 if ai else -1), -self.AI_VOTES), self.AI_VOTES)
            car["ai"] = car["ais"] > 0
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
                car["recent"].append((st + car["off"], p[0], p[1]))
                if me is not None:
                    car["dists"].append(math.dist(me, p))
                    car["still"].append((p, me))
                car["moved"] = car["moved"] or math.dist(car["start"], p) > self.MOVED
                car["grid"] = car["grid"] or self.on_grid(car["still"])
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
                    car["recent"].clear()
        echo = t - self.own_at <= self.TIMEOUT  # the player's own car is known and still sent
        out = {}
        for cid, car in list(self.cars.items()):
            h = car["hist"]
            local = h[-1][0] + car["off"]
            if t - local > self.TIMEOUT:
                del self.cars[cid]
                continue
            if car["ai"] and not self.allow_ai:
                continue  # an NPC
            if car["num"] is None:
                if cid in self.nums:  # shown before: a rival that was out of range for a while
                    if car["good"] < self.RECONFIRM:
                        continue
                elif car["good"] < self.CONFIRM or not (car["moved"] or car["grid"]) or not car["dists"]:
                    continue  # not shown (yet): unconfirmed or never moved
                elif not echo and statistics.median(car["dists"]) < self.SELF_DIST:
                    car["held"] += 1  # the player's own car, by the look of it
                    if car["held"] >= self.SELF_HOLD:
                        self.own_ids.add(cid)
                        del self.cars[cid]
                    continue
                elif not echo and self.on_own_track(car):
                    self.own_ids.add(cid)
                    del self.cars[cid]
                    continue
                car["num"] = self.nums.setdefault(cid, len(self.nums) + 1)
            elif not echo and t - car["look"] >= self.SELF_EVERY:  # shown: the echo, missed at first?
                car["look"] = t
                car["near"] = car["near"] + 1 if self.on_own_track(car) else 0
                if car["near"] >= self.SELF_TIMES:
                    self.own_ids.add(cid)
                    self.ai.pop(cid, None)
                    del self.cars[cid]
                    continue
            # as when first shown: after the finish the game drives a player's car on, with the AI flag
            self.ai.setdefault(cid, car["ai"])
            while len(h) > 2 and h[-1][0] - h[1][0] >= self.SPEED_SPAN:
                h.popleft()
            span = h[-1][0] - h[0][0]
            speed = math.dist(h[0][1:], h[-1][1:]) / span * 3.6 if span > 0.3 else None
            out[car["num"]] = dict(t=local, x=h[-1][1], y=h[-1][2], z=h[-1][3], speed_kmh=speed,
                                   bot=car["ai"])
        return out

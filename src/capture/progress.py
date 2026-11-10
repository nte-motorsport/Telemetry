"""How far along the track every racer is. The race server keeps a list of the racers in race order (the leader
first) with how far each has got, and sends it to every player several times a second, whoever is how far away:
unlike the cars' positions (capture/opponents.py), which it stops sending for a car some 550 m off in the open world
(2026-11-09: a rival unseen from 565 m until he came back to 520 m, and for good from 680 m).

The list comes as numbered fields, each an 8-bit number followed by its value (the numbers of a list element i):

  34 + 52 i   the racer's time at the finish, float32 in seconds (sent once, as the racer finishes)
  36 + 52 i   one bit, sent with it now and then
  38 + 52 i   a float32 of the racer's car (243.47 for every Vehicle026 the player drove, 267.26 for a Vehicle038)
  42 + 52 i   metres along the track, float32 in centimetres
  44 + 52 i   the share of the race done, float32 (0 .. 1)

with the numbers rising, and a 0 after the last field sent. Only changed elements may be sent, and other fields of an
element may come in between. Found in the traffic of 13 races of 2026-11-07/09 on five tracks (three and four
racers): the share times the track's length (6873 m on Track003_02_pvp, 6641 m on DLC_RT_C2) is the metres, the
player's own entry follows the distance they drove to a few metres, and each rival's the place on the player's own
drive where that rival was. On some tracks the metres start over a few seconds into the race, at a line past the grid
(Track001_03_pvp, 2026-11-08: 180 m less from then on, everyone's); the share doesn't, so the share times the length
(the metres gained over the share gained) is how far along a racer is. The 8-bit numbers leave room for four racers,
as many as a race has (2026-11). The list may hold one more than the race's entrants: a car the game drives that is
not one of them (DLC_RT_C1, 2026-11-09).

The list is the race's results too (the race server's FRacingPlayerRankInfo, the same struct it sends in full, names
and all, at the end of some races): as a racer finishes, its element's update carries its time, 34 ... 38, 42, 44 in a
row. In 16 races of 2026-11-07/09 every finish time was the one the full results gave, to the millisecond, and the
element's place the racer's place at the finish (the times rise with it), the finisher's share 1 or nearly (0.9989).

The list says nothing of who is who. Standings follows each racer from one update to the next (they don't jump),
tells the player by their own distance driven, and each rival by where its car was: on the player's own drive, the
point the rival's entry says it was at.
"""
import itertools
import math
import struct
from collections import deque

import numpy as np

from capture import bits

RACERS = 4
SHARE = tuple(44 + 52 * i for i in range(RACERS))  # the number of each element's share of the race


def _f32(n, o):
    return struct.unpack("<f", struct.pack("<I", (n >> o) & 0xFFFFFFFF))[0]


FINISHED = 0.95  # share of the race done at least of a racer whose finish time is taken


def finish_time(n, metres_at, i):
    """The finish time (s) sent right before element i's metres, whose number is at bit metres_at, or None."""
    b = 52 * i
    p = metres_at - 40 if (n >> (metres_at - 40)) & 0xFF == 40 + b else metres_at  # a field 40 may come between
    p -= 40
    if p < 0 or (n >> p) & 0xFF != 38 + b:
        return None
    p -= 49 if p >= 9 and (n >> (p - 9)) & 0xFF == 36 + b else 40  # the one-bit field 36, when it is sent
    if p < 0 or (n >> p) & 0xFF != 34 + b:
        return None
    t = _f32(n, p + 8)
    return t if math.isfinite(t) and 10 < t < 3600 else None


def decode(payload):
    """[(place, metres along the track, share of the race done, finish time in s or None)] of the list's elements in
    one server packet, place being 1 for the leader."""
    n = int.from_bytes(payload, "little")
    out = []
    for a in bits.find(payload, SHARE, 8, 40, len(payload) * 8 - 32):
        i = (((n >> a) & 0xFF) - 44) // 52
        q = a - 32  # the metres, and their number before them
        if (n >> (q - 8)) & 0xFF != 42 + 52 * i:
            continue
        m, share = _f32(n, q) / 100, _f32(n, a + 8)
        after = (n >> (a + 40)) & 0xFF  # the next field's number, or the 0 that ends them
        # the metres are at most the share of the track's length (under 50 km): chance matches seldom are
        if (math.isfinite(m) and math.isfinite(share) and 0 <= share <= 1.01 and 0 <= m <= share * 50000 + 50
                and (after == 0 or 44 + 52 * i < after < 42 + 52 * RACERS)):
            done = finish_time(n, q - 8, i) if share >= FINISHED else None
            out.append((i + 1, m, share, done))
    return out


class Standings:
    """Each racer's distance along the track over time, and who they are: the player ("me") or a rival's number
    (capture/opponents.py)."""
    KEEP = 120.0      # s of each racer's distances, and of the cars' positions, kept
    MAX_SPEED = 120   # m/s: a longer step of the player's own position is the game moving the car, not driving
    GUESS_LENGTH = 6000.0  # m: a track's length while the race's own isn't known yet
    GOING = 0.01      # share of the race the leader has done when it counts as under way
    LENGTH_SPAN = 0.02  # share of the race a racer must gain before its metres gained over it are a length
    OWN_SPAN = 10.0   # s over which the player's own distance driven is compared with each racer's
    OWN_SPREAD = 20.0  # m: the player is the racer whose distance keeps this close to the distance driven, plus a
                       # fixed amount (where on the track the player started), and half as close as anyone else's.
                       # Not closer: the list comes 0.1-0.3 s late, 5-15 m at speed (the player's own entry in a
                       # race of 2026-11-09 kept within 15 m, the next closest 45-100 m)
    OWN_DRIVEN = 150.0  # m driven over OWN_SPAN before that is looked at: standing on the grid, everyone fits
    OWN_TIMES = 3     # looks in a row that find another racer to be the player before it is taken to be
    LOOK = 1.0        # s between looks at who is who
    SAMPLES = 60      # positions of each car looked at, at most (one a second over the last minute)
    NEAR = 25.0       # m: a racer whose entry puts it within this of where a car was (median) may be that car
    VOTES = 3         # positions of a car that must be on the player's drive before it is told

    def __init__(self):
        self.racers = []  # each: dict(hist=deque of (t, share), mark=(share, metres) a length is measured from)
        self.length = None  # the track's length, m
        self.lengths = deque(maxlen=200)  # its measurements
        self.path = deque()  # the player's own (t, x, y, distance driven)
        self.cars = {}  # rival number -> deque of (t, x, y)
        self.me = None  # the player's index in racers
        self.me_next = (None, 0)  # another racer the latest looks took for the player, and how many in a row
        self.offset = 0.0  # the player's distance along the track minus their distance driven
        self.who = {}  # racer index -> rival number
        self.look = -math.inf

    # ----- input -----

    def own(self, t, x, y):
        """The player's own position at local time t."""
        if self.path and t <= self.path[-1][0]:
            return
        d = self.path[-1][3] + math.hypot(x - self.path[-1][1], y - self.path[-1][2]) if self.path else 0.0
        if self.path and d - self.path[-1][3] > self.MAX_SPEED * max(t - self.path[-1][0], 0.1):
            d = self.path[-1][3]  # moved by the game, not driven
        self.path.append((t, x, y, d))
        while t - self.path[0][0] > self.KEEP:
            self.path.popleft()

    def rivals(self, t, cars):
        """The rivals' positions, as opponents.Opponents.update gives them."""
        for num, c in cars.items():
            h = self.cars.setdefault(num, deque())
            if not h or c["t"] > h[-1][0]:
                h.append((c["t"], c["x"], c["y"]))
            while h and t - h[0][0] > self.KEEP:
                h.popleft()

    def update(self, t, places):
        """One packet's list elements (decode) at local time t."""
        # (a packet may carry an element twice: the latest is the one sent last). Once the race is under way an
        # element of nought is no racer's: one now and then for a moment mid-race, and every one left at the finish
        # (2026-11-08/09), and not always quite nought
        going = any(r["hist"] and r["hist"][-1][1] > self.GOING for r in self.racers)
        places = list({place: (place, m, share, done) for place, m, share, done in places
                       if place <= RACERS and not (going and share < 1e-3)}.values())
        if not places:
            return
        # as many racers as the list has places
        while len(self.racers) < min(max(place for place, _, _, _ in places), RACERS):
            self.racers.append(dict(hist=deque(), mark=None, finish=None))
        # each element to the racer it carries on from: the way that moves them least from where they were heading
        # in all. Not each to the closest: a racer off the track may stand still in the list and then leap ahead
        # 240 m at once (DLC_RT_C2, 2026-11-08), right past another
        # Racers that have finished all stand at the end, as alike as can be: one is told by the place it finished in,
        # which its element keeps (and a finish just sent goes to a racer that hasn't one)
        guesses = [self.guess(r, t) for r in self.racers]
        best = None
        for to in itertools.permutations(range(len(self.racers)), len(places)):
            cost = sum((abs(share - guesses[i]) if guesses[i] is not None else 0.01)
                       + (1.0 if self.racers[i]["finish"] and (done is not None or self.racers[i]["finish"][1] != place)
                          else 0.0)
                       for (place, _, share, done), i in zip(places, to))
            if best is None or cost < best[0]:
                best = (cost, to)
        for (place, m, share, done), i in zip(places, best[1]):
            r = self.racers[i]
            if done is not None:
                r["finish"] = (done, place)
            h = r["hist"]
            if not h or t > h[-1][0]:
                h.append((t, share))
            while len(h) > 1 and t - h[1][0] > self.KEEP:  # the one before those kept says where it was since
                h.popleft()
            # the track's length: metres gained over share gained (the metres may have started over in between:
            # a length out of line with the rest, which the median leaves out)
            if r["mark"] is None or m < r["mark"][1] or share < r["mark"][0]:
                r["mark"] = (share, m)
            elif share - r["mark"][0] >= self.LENGTH_SPAN:
                self.lengths.append((m - r["mark"][1]) / (share - r["mark"][0]))
                self.length = float(np.median(self.lengths))
                r["mark"] = (share, m)
        if t - self.look >= self.LOOK:
            self.look = t
            self.find_me()
            self.find_rivals()

    def guess(self, r, t):
        """The share of the race racer r is likely to have done at t, from its latest updates; None for a racer not
        heard of yet."""
        h = r["hist"]
        if not h:
            return None
        t1, m1 = h[-1]
        for t0, m0 in reversed(h):
            if t1 - t0 >= 1.0:
                rate = (m1 - m0) / (t1 - t0)  # a step in the list (see update) makes it out of reach: left out
                return m1 + rate * (t - t1) if 0 <= rate * (self.length or self.GUESS_LENGTH) <= self.MAX_SPEED else m1
        return m1

    # ----- who is who -----

    def at(self, i, ts):
        """Racer i's distance along the track at the times ts (NaN before it was first heard of). An element is sent
        when it changes, so a racer standing still is where it was last said to be."""
        h = np.array(self.racers[i]["hist"]).reshape(-1, 2)
        if not len(h):
            return np.full(len(ts), np.nan)
        out = np.interp(ts, h[:, 0], h[:, 1]) * self.length
        out[ts < h[0, 0]] = np.nan
        return out

    def find_me(self):
        """The player is the racer whose distance along the track goes with the distance they drove."""
        if len(self.path) < 2 or not self.length:
            return
        p = np.array(self.path)
        p = p[p[:, 0] >= p[-1, 0] - self.OWN_SPAN]
        if len(p) < 10 or p[-1, 3] - p[0, 3] < self.OWN_DRIVEN:
            return
        fits = []
        for i in range(len(self.racers)):
            d = self.at(i, p[:, 0]) - p[:, 3]
            d = d[np.isfinite(d)]
            if len(d) >= 10:
                fits.append((float(np.percentile(d, 90) - np.percentile(d, 10)), i, float(np.median(d))))
        fits.sort()
        if not (fits and fits[0][0] < self.OWN_SPREAD and (len(fits) == 1 or fits[0][0] < fits[1][0] / 2)):
            return
        _, i, offset = fits[0]
        if i != self.me and self.me is not None:  # another: only once several looks in a row say so
            n = self.me_next[1] + 1 if self.me_next[0] == i else 1
            self.me_next = (i, n)
            if n < self.OWN_TIMES:
                return
        self.me, self.offset, self.me_next = i, offset, (None, 0)
        self.who.pop(i, None)

    def find_rivals(self):
        """A rival is the racer whose entry, at the times its car was seen, puts it where the car was: the point of
        the player's own drive that far along the track (where the player has been since)."""
        if self.me is None or len(self.path) < 2:
            return
        p = np.array(self.path)
        drive = p[:, 3] + self.offset  # the player's drive by distance along the track
        if np.any(np.diff(drive) < 0):
            return
        scores = []
        for num, h in self.cars.items():
            c = np.array(h)
            c = c[c[:, 0] >= c[-1, 0] - 60.0]
            if len(c) > self.SAMPLES:
                c = c[np.linspace(0, len(c) - 1, self.SAMPLES).astype(int)]
            for i in range(len(self.racers)):
                if i == self.me:
                    continue
                m = self.at(i, c[:, 0])
                ok = np.isfinite(m) & (m >= drive[0]) & (m <= drive[-1])
                if ok.sum() < self.VOTES:
                    continue
                x = np.interp(m[ok], drive, p[:, 1])
                y = np.interp(m[ok], drive, p[:, 2])
                miss = float(np.median(np.hypot(x - c[ok, 1], y - c[ok, 2])))
                if miss < self.NEAR:
                    scores.append((miss, num, i))
        taken, used = set(), set()
        who = {}
        for _, num, i in sorted(scores):
            if num in taken or i in used:
                continue
            taken.add(num)
            used.add(i)
            who[i] = num
        # what wasn't looked at again (cars not seen lately) stays as it was
        for i, num in self.who.items():
            if i not in used and num not in taken and i != self.me:
                who[i] = num
        self.who = who

    # ----- output -----

    def snapshot(self):
        """dict(length=the track's length in m or None, racers=[dict(id, place, share, metres, who, t)]) in race
        order, id staying with one racer, share the share of the race done, metres how far along the track (None
        while the length isn't known), who "me", a rival's number or None while not known, t the local time the
        racer's share was last sent, finish the racer's time at the finish (s) and finish_place its place there, both
        None until it has finished."""
        rows = []
        for i, r in enumerate(self.racers):
            if not r["hist"]:
                continue
            t, share = r["hist"][-1]
            done, at = r["finish"] or (None, None)
            rows.append(dict(id=i, share=share, metres=share * self.length if self.length else None,
                             who="me" if i == self.me else self.who.get(i), t=t, finish=done, finish_place=at))
        rows.sort(key=lambda r: -r["share"])
        for k, r in enumerate(rows):
            r["place"] = k + 1
        return dict(length=self.length, racers=rows)

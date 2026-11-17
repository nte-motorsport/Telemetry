"""Sector times, as in real racing: each stretch of a lap between two checkpoints (capture/checkpoints.py) is a
mini-sector, and the mini-sectors are put in three groups of about a third of the lap each, the sectors.

A racer passes a checkpoint when it comes nearest to its middle, within reach of its box: on the straight line
between two of its positions, the time in proportion along it. (Not when it crosses a line across the way it drives:
a checkpoint may stand where the track turns, 2026-11-11 on DLC_RT_C1, and a car passing it some metres to one side
turns as it does, so the line turns with it and may never be crossed.) The checkpoints are passed in their order (CheckpointIndex), the last (the finish) ending a
lap; one a racer is not seen passing (a rival's position not sent: the open world sends none of a car some 550 m
off, see capture/progress.py) is skipped, and the times on either side of it are not known. A lap's first
mini-sector starts at the line it ended the lap before over, the race's first at the start.

The start is when the player's car got under way (the cars are held on the grid until then), until a racer
finishes: then it is when the race server's times at the finish say it was, from the moments the racers crossed the
line (the median of theirs). In 6 races of 2026-11-11/14 the rivals' agreed to 0.1 s, the player's own 0.5-1.7 s
later (its position comes with another delay): only the race's first mini-sector, timed from the start, has it.

Each time is coloured as in real racing: purple the best of anyone's in the race, green the racer's own best
(another lap's was no better), yellow slower than the racer's own best."""
import math
import statistics

PURPLE, GREEN, YELLOW = "#b45cff", "#3ad164", "#f2c230"
SECTORS = 3
JUMP = 100.0   # m between two positions of a car more than which it was moved, not driven
REACH = 1.25   # times the checkpoint box's larger half extent a pass may be off its middle
AWAY = 10.0    # m further from a checkpoint than it came nearest at which a car has passed it
STILL = 0.5    # m/s under which the player's car stands on the grid


def groups(cps, n=SECTORS):
    """[[mini-sector index]] of the n sectors: cuts at the checkpoints nearest to each n-th of the lap's length (the
    straight line from each checkpoint to the next, the finish to the first), each sector one mini-sector at least."""
    k = len(cps)
    if k < n:
        return [list(range(k))]
    lengths = [math.dist((cps[i - 1]["x"], cps[i - 1]["y"]), (cps[i]["x"], cps[i]["y"])) for i in range(k)]
    total = sum(lengths)
    ends, run = [], 0.0
    cum = []
    for v in lengths:
        run += v
        cum.append(run)
    for j in range(1, n):
        lo = (ends[-1] + 1) if ends else 0
        hi = k - (n - j)  # room for one mini-sector in each sector after
        best = min(range(lo, hi), key=lambda i: abs(cum[i] - total * j / n))
        ends.append(best)
    ends.append(k - 1)
    out, lo = [], 0
    for e in ends:
        out.append(list(range(lo, e + 1)))
        lo = e + 1
    return out


def nearest(a, b, cp):
    """(distance, time) where the straight line between racer positions a, b ((t, x, y)) comes nearest to checkpoint
    cp's middle."""
    dx, dy = b[1] - a[1], b[2] - a[2]
    dd = dx * dx + dy * dy
    f = 0.0 if dd < 1e-9 else min(1.0, max(0.0, ((cp["x"] - a[1]) * dx + (cp["y"] - a[2]) * dy) / dd))
    return math.hypot(a[1] + dx * f - cp["x"], a[2] + dy * f - cp["y"]), a[0] + (b[0] - a[0]) * f


class Timer:
    """The checkpoints each racer passed in one race, and its mini-sector and sector times."""
    SKIP = 2  # checkpoints a racer may be missed passing before the next it is seen passing

    def __init__(self, cps, laps=None):
        """cps: the race's checkpoints in their order (dict(x, y, half: [m, m], ...)); laps: how many the race has,
        or None if not known (a racer's laps end when it finishes, see finished)."""
        self.cps = cps
        self.laps = laps
        self.groups = groups(cps)
        self.start = None      # the race's start (local time), see set_start
        self.measured = False  # the start is the one the race server's times at the finish say
        self.starts = []       # the start each finisher's time says: their median is taken (the player's own car is
                               # seen with another delay than the rivals', its start some 0.5-1.7 s off theirs)
        self.racers = {}       # key -> dict(prev=(t, x, y), lap, next: checkpoint index, cross: {(lap, i): t}, done)

    def feed(self, key, t, x, y):
        """Racer key's position at local time t."""
        r = self.racers.setdefault(key, dict(prev=None, lap=1, next=0, cross={}, done=False, near={}))
        p = (t, x, y)
        a, r["prev"] = r["prev"], p
        # before the start the cars may drive anywhere (to the grid, past checkpoints on the way)
        if a is None or r["done"] or t <= a[0] or self.start is None or a[0] < self.start:
            return
        if math.dist(a[1:], p[1:]) > JUMP:  # moved by the game: wherever it came nearest, it didn't drive there
            r["near"] = {}
            return
        n = len(self.cps)
        for skip in range(self.SKIP + 1):
            step = r["next"] + skip
            j, lap = step % n, r["lap"] + step // n
            if self.laps and lap > self.laps:
                break
            cp = self.cps[j]
            d, at = nearest(a, p, cp)
            if d <= REACH * max(cp["half"]) and d < r["near"].get(step, (math.inf,))[0]:
                r["near"][step] = (d, at)
            got = r["near"].get(step)
            # a car that has finished may stop right past the line: passed as soon as it goes away from it at all
            away = 0.5 if r.get("finish") is not None else AWAY
            if got and math.hypot(x - cp["x"], y - cp["y"]) > got[0] + away:  # gone past it
                self.passed(r, step, got[1])
                break

    def passed(self, r, step, at):
        """Racer r passed the checkpoint step on from the one it was to pass next, at local time at."""
        n = len(self.cps)
        j, lap = step % n, r["lap"] + step // n
        r["cross"][(lap, j)] = at
        r["near"] = {k - step - 1: v for k, v in r["near"].items() if k > step}
        r["lap"], r["next"] = lap, j + 1
        if r["next"] == n:  # the finish: a lap done
            r["next"] = 0
            r["lap"] += 1
            if self.laps and r["lap"] > self.laps:
                r["done"] = True
                r["done_at"] = at
            self.settle(r)

    def crossed(self, key, lap, j, at):
        """Racer key passed checkpoint j of lap at time at, as a recorded race says (see record): no positions
        looked at."""
        r = self.racers.setdefault(key, dict(prev=None, lap=1, next=0, cross={}, done=False, near={}))
        r["cross"][(lap, j)] = at
        r["lap"], r["next"] = lap, j + 1
        if r["next"] == len(self.cps):
            r["lap"], r["next"] = lap + 1, 0

    def record(self, shift=0.0):
        """What the race's sectors were timed on, to be kept with its replay: the start and every racer's checkpoint
        passes (lap, checkpoint index, time) and when it was done, the times less shift; {key: ...} by racer."""
        out = {}
        for k, r in self.racers.items():
            e = dict(cross=[[lap, j, round(t - shift, 6)] for (lap, j), t in sorted(r["cross"].items(),
                                                                                  key=lambda kv: kv[1])])
            if r["done"] and r.get("done_at") is not None:
                e["done"] = round(r["done_at"] - shift, 6)
            out[str(k)] = e
        return dict(start=None if self.start is None else round(self.start - shift, 6), groups=self.groups,
                    racers=out)

    def finished(self, key, finish):
        """Racer key finished the race, finish s after its start (the race server's time, sent as it crosses the line,
        a moment before its car is seen there): its laps end at its next pass of the line (or the one just passed),
        and the start is measured from it (see the module's doc)."""
        r = self.racers.get(key)
        if not r or r.get("finish") is not None:
            return
        r["finish"] = finish
        self.settle(r)

    def settle(self, r):
        """Racer r is done once it has passed the line after its finish was sent (or just before it was: its pass
        of the line within a few seconds of the finish time)."""
        if r.get("finish") is None or r["next"] != 0 or r["lap"] < 2:
            return
        crossed = r["cross"].get((r["lap"] - 1, len(self.cps) - 1))
        if crossed is None:
            return
        start = crossed - r["finish"]
        if self.start is not None and abs(start - self.start) > 5.0:
            return  # an earlier lap's line: the race's finish is still to come
        r["done"] = True
        r["done_at"] = crossed
        self.starts.append(start)
        self.start = statistics.median(self.starts)
        self.measured = True

    def set_start(self, t):
        """The start as the capture tells it (when not measured from a finish): the crossings before it are not
        the race's."""
        if not self.measured:
            self.start = t

    def minis(self, key):
        """{(lap, mini-sector index): seconds} of racer key's known mini-sectors."""
        r = self.racers.get(key)
        if not r:
            return {}
        last = len(self.cps) - 1
        out = {}
        for (lap, i), t in r["cross"].items():
            if i:
                before = r["cross"].get((lap, i - 1))
            elif lap == 1:
                before = self.start
            else:
                before = r["cross"].get((lap - 1, last))
            if before is not None and t > before:
                out[(lap, i)] = t - before
        return out

    def sectors(self, key):
        """{(lap, sector index): seconds} of racer key's sectors whose mini-sectors are all known."""
        m = self.minis(key)
        laps = {lap for lap, _ in m}
        out = {}
        for lap in laps:
            for s, g in enumerate(self.groups):
                v = [m.get((lap, i)) for i in g]
                if None not in v:
                    out[(lap, s)] = sum(v)
        return out

    def lap(self, key):
        """The lap racer key is on (the last it drove once it is done)."""
        r = self.racers.get(key)
        if not r:
            return 1
        return r["lap"] - 1 if r["done"] and r["next"] == 0 and r["lap"] > 1 else r["lap"]

    def table(self):
        """{key: dict(lap, sectors: [(seconds, colour) or None] * SECTORS, minis: [colour or None] * mini-sectors)}:
        each racer's latest time in each sector and its colour, and its current lap's mini-sectors' colours."""
        minis = {k: self.minis(k) for k in self.racers}
        secs = {k: self.sectors(k) for k in self.racers}
        best_mini = best(minis)
        best_sec = best(secs)
        out = {}
        for k in self.racers:
            lap = self.lap(k)
            own_mini, own_sec = best({k: minis[k]}), best({k: secs[k]})
            row = []
            for s in range(len(self.groups)):
                latest = max((l for l, j in secs[k] if j == s), default=None)
                if latest is None:
                    row.append(None)
                else:
                    v = secs[k][(latest, s)]
                    row.append((v, colour(v, best_sec[s], own_sec[s])))
            strip = []
            for i in range(len(self.cps)):
                v = minis[k].get((lap, i))
                strip.append(colour(v, best_mini[i], own_mini[i]) if v is not None else None)
            out[k] = dict(lap=lap, sectors=row, minis=strip)
        return out


class RaceTiming:
    """A race's Timer, kept from what the capture sends as it comes: the race's checkpoints, its standings and
    everyone's positions. A new one once a race with known checkpoints gets under way, given the finishes the race
    server sends; none once the race's data stops coming (the standings gone). The Multiplayer page shows its
    table; the recorder keeps its record with the race's replay (replays/recorder.py), so both time it alike."""
    KEEP = 60.0  # s of the player's own speeds kept, to tell when its car got under way (launch)

    def __init__(self):
        self.course = None   # the race's checkpoints (capture/checkpoints.py), or None while not known
        self.timer = None    # Timer of the race while its data comes, or None
        self.timer_for = None  # (checkpoint set id, start) the timer is of
        self.own = []        # (t, km/h) of the player's car over the last KEEP s

    def set_course(self, course, snapshot):
        self.course = course
        self.update(snapshot)

    def on_own(self, t, x, y, kmh):
        self.own.append((t, kmh))
        while self.own and t - self.own[0][0] > self.KEEP:
            self.own.pop(0)
        if self.timer:
            self.timer.feed("me", t, x, y)

    def on_rival(self, key, t, x, y):
        if self.timer:
            self.timer.feed(key, t, x, y)

    def update(self, s):
        """The standings (progress.Standings.snapshot) as last sent, or None out of a race."""
        if not s or not self.course:
            self.timer = self.timer_for = None
        if self.course and s and s.get("start") is not None:
            key = (self.course["id"], s["start"])
            if key != self.timer_for:
                self.timer_for = key
                self.timer = Timer(self.course["checkpoints"], self.course.get("laps"))
                self.timer.set_start(launch(self.own, s["start"]))
        if self.timer and s:
            for r in s["racers"]:
                if r["finish"] is not None and r["who"] is not None:
                    self.timer.finished(r["who"], r["finish"])


def launch(own, under_way):
    """When the player's car got under way from the grid: right after the last of its samples (t, speed in km/h)
    standing still before under_way (when the race's leader had got going); under_way if none stood still."""
    still = [t for t, v in own if t <= under_way and v < STILL * 3.6]
    if not still:
        return under_way
    after = [t for t, _ in own if still[-1] < t <= under_way]
    return after[0] if after else still[-1]


def best(times):
    """{slot: the least of the times} over {key: {(lap, slot): seconds}}."""
    out = {}
    for m in times.values():
        for (_, slot), v in m.items():
            out[slot] = min(v, out.get(slot, math.inf))
    return out


def colour(v, best_all, best_own):
    if v <= best_all + 1e-6:
        return PURPLE
    if v <= best_own + 1e-6:
        return GREEN
    return YELLOW

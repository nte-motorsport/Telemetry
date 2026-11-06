"""Live telemetry: the game's traffic captured on one interface, decoded on a worker thread."""
import math
import time
from collections import deque

from PySide6.QtCore import QThread, Signal

from capture import opponents
from capture.identity import Identity
from capture.levels import find_level
from capture.roster import Roster
from capture.protocol import decode
from capture.raw_socket import RawCapture
from capture.tracker import Tracker


class Probe:
    """A flow (pair of ports) that may be the game's, watched until its fixes prove it: random data (a video
    stream in Discord, say) now and then decodes as two fixes that agree, but only the game's client clock
    runs at the rate of real time."""
    FIXES = 5     # fixes in a row that keep time ...
    SPAN = 0.4    # ... over at least this long (a car standing still sends only a few)
    DRIFT = 0.25  # share by which the client clock may run off real time
    STEP = 0.25   # s by which one step's client time may differ from real time
    MIN_TS = 0.05  # s: random data decodes mostly as tiny times, which a game connected that briefly
                   # hasn't sent anything at yet

    def __init__(self):
        self.tracker = Tracker()
        self.times = deque()  # (arrival, client time) of the fixes in a row

    def take(self, cands, now):
        """True once the flow is the game's."""
        cands = [c for c in cands if c[0] >= self.MIN_TS]
        r = self.tracker.pick(cands) if cands else None
        if not r:
            return False
        self.tracker.update(*r)
        if self.times:
            t0, c0 = self.times[-1]
            if abs((r[0] - c0) - (now - t0)) > self.STEP:  # this one didn't keep time: count again from it
                self.times.clear()
        self.times.append((now, r[0]))
        while len(self.times) > self.FIXES * 4:
            self.times.popleft()
        (t0, c0), (t1, c1) = self.times[0], self.times[-1]
        return (len(self.times) >= self.FIXES and t1 - t0 >= self.SPAN
                and abs((c1 - c0) - (t1 - t0)) <= self.DRIFT * (t1 - t0))


class LiveSource(QThread):
    """Raw-socket capture on one interface. Movement is taken from one flow only, the one proven to be the
    game's (see Probe); while it is alive other traffic is skipped, so a voice chat or a stream doesn't
    cost decoding time or get mistaken for the game."""
    sample = Signal(dict)       # one tracker output, same fields as tracker.FIELDS
    rivals = Signal(object)     # other racers after a server update, see opponents.Opponents.update
    failed = Signal(str, str)   # kind ("admin" | "error"), message
    level = Signal(str)         # the game world (UE level path) the game's server is on, "" while not known
    field = Signal(object)      # the race's entrants, see roster.Roster.field: [] while there are none
    names = Signal(object)      # {rival number: entrant's name} of the rivals known by name (capture/identity.py)
    player = Signal(str, str)   # the player's own name and account id (as text: it doesn't fit a C int), see
                                # roster.ROLE: as soon as a server sends them
    ALIVE = 5.0   # s: the game's flow counts as alive this long after its last fix
    PROBES = 64   # flows watched at most at once
    BUSY = 300    # packets a second: the game sends up to ~120, so a flow this busy (a video stream) is
                  # something else and not worth decoding while looking for the game

    def __init__(self, ip):
        super().__init__()
        self.ip = ip
        self._stop = False
        self.tracker = Tracker()
        self.opponents = opponents.Opponents()
        self.flow = None    # (client port, server port) of the game
        self.seen = -math.inf  # when it last carried a fix
        self.probes = {}    # flow -> Probe
        self.rate_at = -math.inf
        self.rates, self.last_rates = {}, {}  # flow -> packets this second / the one before
        # (source port, destination port) -> the level packets of that flow named: the server names it right
        # after connecting, before the flow is known to be the game's, so every flow is looked at
        self.levels = {}
        self.world = ""  # as last emitted
        # (source port, destination port) -> the entrants its packets named; looked for only in flows that named a
        # level (the game's servers), as the race server sends them before the flow is known to be the game's
        self.rosters = {}
        self.identities = {}  # the same flows -> Identity: the cars their servers made
        self.entrants = []  # as last emitted
        self.named = {}     # as last emitted
        self.me = ""        # the player's name, see Identity.match: from the game (player), else as set
        self.role = None    # the player's own (account id, name), as last emitted
        self.tap = None  # a pcap.PcapWriter that gets every captured packet (a race's raw traffic), or None

    def stop(self):
        self._stop = True
        self.wait(2000)

    def busy(self, flow, now):
        """Count one packet of flow; True if it sends too often to be the game."""
        if now - self.rate_at >= 1.0:
            self.rate_at, self.last_rates, self.rates = now, self.rates, {}
        n = self.rates[flow] = self.rates.get(flow, 0) + 1
        return max(n, self.last_rates.get(flow, 0)) > self.BUSY

    def feed(self, payload, flow=None, now=None):
        """Decode one packet; True if it carried this car's movement. flow: (source port, destination
        port), None to take every packet as the game's (replaying a capture of the game alone)."""
        cands = list(decode(payload))
        if not cands:
            return False
        now = time.monotonic() if now is None else now
        if flow is not None and flow != self.flow:
            probe = self.probes.get(flow)
            if probe is None:
                if len(self.probes) >= self.PROBES:
                    self.probes.clear()
                probe = self.probes[flow] = Probe()
            if not probe.take(cands, now):
                return False
            # the game, on a new flow (it connected to another server): carry on from what the probe has
            had = self.flow is not None
            self.tracker, self.flow, self.probes = probe.tracker, flow, {}
            if had:
                self.tracker.reset_motion()  # flags a jump: clears the charts and the rivals
            self.seen = now
            return True
        r = self.tracker.pick(cands)
        if r:
            self.opponents.own(now, r[1], r[2])  # to tell the server's echo of this car from the rivals
        d = self.tracker.update(*r) if r else None
        if d:
            if d["jump"]:  # teleported: whoever was around is not any more
                self.opponents = opponents.Opponents()
            self.sample.emit(d)
        if r is not None:
            self.seen = now
        return r is not None

    def feed_server(self, payload, t=None):
        """Take the other racers' positions from one packet the game server sent."""
        me = self.tracker.prev
        if not me:
            return
        recs = [r for r in opponents.decode(payload) if math.dist(r[2], me[1:4]) < opponents.NEAR]
        if recs:
            self.rivals.emit(self.opponents.update(time.monotonic() if t is None else t, recs, me[1:4]))

    def handle(self, sport, dport, payload, now):
        """One UDP datagram of the capture: (source port, destination port), payload, arrival time."""
        lv = find_level(payload)
        if lv:
            if len(self.levels) >= self.PROBES and (sport, dport) not in self.levels:
                self.levels.clear()
            self.levels[(sport, dport)] = lv
        if (sport, dport) in self.levels:
            r = self.rosters.get((sport, dport))
            if r is None:
                if len(self.rosters) >= self.PROBES:
                    self.rosters.clear()
                r = self.rosters[(sport, dport)] = Roster()
            r.update(payload)
            if r.role and r.role != self.role:
                self.role = r.role
                self.me = r.role[1]
                self.player.emit(r.role[1], str(r.role[0]))
            ident = self.identities.get((sport, dport))
            if ident is None:
                if len(self.identities) >= self.PROBES:
                    self.identities.clear()
                ident = self.identities[(sport, dport)] = Identity()
            ident.feed(payload)
        # the client's own movement goes to the game server, so the server's port is the destination
        server = self.flow[1] if self.flow else None
        flow = (sport, dport)
        if flow == self.flow or (now - self.seen > self.ALIVE and not self.busy(flow, now)):
            self.feed(payload, flow, now)
        elif sport == server and dport == self.flow[0]:
            self.feed_server(payload, now)
        # the game's server -> client direction is the reverse of its flow
        world = self.levels.get((self.flow[1], self.flow[0]), "") if self.flow else ""
        if world != self.world:
            self.world = world
            self.level.emit(world)
        r = self.rosters.get((self.flow[1], self.flow[0])) if self.flow else None
        entrants = r.field() if r else []
        if entrants != self.entrants:
            self.entrants = entrants
            self.field.emit(entrants)
        # cars the game drives are a race's bots when the server named a field to race; in free roam (a world
        # shared with friends) they are its people and traffic, 20-30 of them, which aren't rivals
        self.opponents.allow_ai = len(entrants) >= 2
        named = self.match_names(r, self.identities.get((self.flow[1], self.flow[0])) if self.flow else None)
        if named != self.named:
            self.named = named
            self.names.emit(named)

    def match_names(self, roster, ident):
        """{rival number: name} for the rivals the field can be matched to."""
        if not roster or not ident or not roster.entrants:
            return {}
        opp = self.opponents
        own = next(iter(opp.own_ids)) if len(opp.own_ids) == 1 else None
        humans = [cid for cid, ai in opp.ai.items() if not ai]
        bots = [cid for cid, ai in opp.ai.items() if ai]
        by_car = ident.match(roster.order(), roster.bots, humans, bots, own, self.me)
        return {opp.nums[cid]: name for cid, name in by_car.items() if cid in opp.nums}

    def run(self):
        try:
            cap = RawCapture(self.ip)
        except PermissionError:
            self.failed.emit("admin", "Capturing traffic requires administrator rights.")
            return
        except OSError as e:
            self.failed.emit("error", f"Could not start capture on {self.ip}: {e}")
            return
        try:
            for sport, dport, payload in cap.packets(lambda: self._stop, lambda: self.tap):
                self.handle(sport, dport, payload, time.monotonic())
        except OSError as e:
            self.failed.emit("error", f"Capture stopped: {e}")
        finally:
            cap.close()

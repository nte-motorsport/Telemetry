"""Automatic recording of online races: from the first rival data to the end of the race."""
import datetime
import os
import time

from PySide6.QtCore import QObject, Signal

from capture.pcap import PcapWriter
from replays.store import own_track


class RaceRecorder(QObject):
    """A race starts when rivals' positions start coming in and ends when they have stopped for END_AFTER
    seconds, when the player is teleported (a new race or a test drive) or when the app closes."""
    saved = Signal(str)        # the file of a replay just written
    recording = Signal(bool)   # a race recording started / stopped
    tap = Signal(object)       # a PcapWriter to give every captured packet to while a race is recorded, or None
    END_AFTER = 20.0  # s without rival data that end a race
    MIN_LENGTH = 30.0  # s: shorter recordings (a glimpse of someone in free roam) are not kept

    def __init__(self, store, enabled=True, raw=False):
        """raw: also save the raw network traffic of each race, next to its replay."""
        super().__init__()
        self.store = store
        self.enabled = enabled
        self.raw = raw
        self.writer = None  # the raw traffic of the race being recorded
        self.active = False
        self.world = ""  # the game world (UE level path) as last known
        self.entrants = []  # the race's entrants as last known (capture/roster.py): they come before the race
        self.race_track = ""  # the race's track as last known (capture/roster.py): it too comes before
        # the player's own (name, account id) as last known: the account a race is driven on, which may not be the
        # one driven on later
        self.player = ("", "")
        self.rank_now = None  # the player's (rank, points) as last named (capture/ranking.py)
        self.lobby_now = []  # the latest lobby's players as last known: they come some 10 s before the race server

    def set_enabled(self, on):
        self.enabled = on
        if not on:
            self.finish()

    def set_raw(self, on):
        """Turned off, the raw traffic of a race being recorded is stopped and thrown away at once: it may be
        what someone didn't want kept. Turned on, it is recorded from the next race."""
        self.raw = on
        if not on:
            self.end_raw(keep=False)

    def end_raw(self, keep):
        """Stop the raw traffic; its file, if kept (to go next to the replay), or None."""
        w, self.writer = self.writer, None
        if w is None:
            return None
        self.tap.emit(None)
        w.close()
        if keep:
            return w.path
        try:
            os.remove(w.path)
        except OSError:
            pass
        return None

    def set_field(self, entrants):
        self.entrants = list(entrants)
        if self.active and entrants:
            self.field = self.entrants  # the latest the race server named while the race went on

    def set_track(self, track):
        self.race_track = track
        if self.active and track and not self.track:
            self.track = track

    def set_player(self, name, account):
        self.player = (name or "", account or "")
        if self.active and name:
            self.racer = self.player  # the race server names the player as it connects: the latest is this race's

    def set_names(self, names):
        if self.active:
            self.names.update(names)  # a name once matched stays: the capture forgets them at the finish

    def on_standings(self, snapshot):
        """How far along everyone is (progress.Standings.snapshot): each racer's share of the race done whenever it
        changes, and who they turned out to be."""
        if not self.active or not snapshot:
            return
        if snapshot["length"]:
            self.length = snapshot["length"]
        for r in snapshot["racers"]:
            racer = self.racers.setdefault(r["id"], dict(who=None, rows=[]))
            if r["who"] is not None:
                racer["who"] = "me" if r["who"] == "me" else str(r["who"])
            if r.get("finish") is not None:
                racer["finish"], racer["place"] = round(r["finish"], 3), r["finish_place"]
            t = round(r["t"] - self.t0, 3)
            if not racer["rows"] or t > racer["rows"][-1][0]:
                racer["rows"].append([t, round(r["share"], 6)])

    def set_rank(self, rank, points):
        self.rank_now = (rank, points)
        if self.active:
            if self.rank_before is None:  # not known when the race began: the first named is the one before it
                self.rank_before = self.rank_now
            elif self.rank_now != self.rank_before:
                self.rank_after = self.rank_now  # the finish names the points before the race, then after it

    def set_lobby(self, lobby):
        self.lobby_now = list(lobby)
        if self.active and lobby:
            self.lobby = self.lobby_now

    def set_world(self, level):
        self.world = level
        if self.active and level and not self.level:
            # the race's world: the first one known while it goes on. Not a later one: the next world is named
            # a moment before the teleport into it ends the race
            self.level = level

    def start(self, now):
        self.active = True
        self.t0 = now
        self.started = datetime.datetime.now().replace(microsecond=0).isoformat()
        self.me, self.rivals, self.last_t = [], {}, {}
        self.bots = {}  # rival number -> tally of its updates with the AI flag (+1) and without (-1)
        self.names = {}  # rival number -> entrant's name, as the capture matched them
        self.racers = {}  # racer id (capture/progress.py) -> dict(who, rows=[[t, share of the race done], ...])
        self.length = None  # the track's length, m, as the capture measured it
        self.racer = self.player
        self.level = self.world
        self.field = self.entrants
        self.track = self.race_track
        self.rank_before, self.rank_after = self.rank_now, None
        self.lobby = self.lobby_now
        self.last_rival = now
        if self.raw:
            try:
                self.writer = PcapWriter(self.store.raw_tmp(self.started))
                self.tap.emit(self.writer)
            except OSError:
                self.writer = None
        self.recording.emit(True)

    def on_own(self, d):
        if self.active:
            self.me.append([round(d["w"] - self.t0, 3), d["x"], d["y"], d["z"], d["speed_kmh"]])

    def on_rivals(self, cars):
        if not self.enabled or not cars:
            return
        now = time.monotonic()
        if not self.active:
            self.start(now)
        for num, c in cars.items():
            if self.last_t.get(num) == c["t"]:  # not moved since the last packet
                continue
            self.last_t[num] = c["t"]
            v = c["speed_kmh"]
            self.bots[num] = self.bots.get(num, 0) + (1 if c.get("bot") else -1)
            self.rivals.setdefault(str(num), []).append(
                [round(c["t"] - self.t0, 3), round(c["x"], 2), round(c["y"], 2), round(c["z"], 2),
                 None if v is None else round(v, 1)])
            self.last_rival = now

    def tick(self):
        if self.active and time.monotonic() - self.last_rival > self.END_AFTER:
            self.finish()

    def finish(self):
        if not self.active:
            return
        self.active = False
        self.recording.emit(False)
        times = [r[0] for r in self.me] + [r[0] for rows in self.rivals.values() for r in rows]
        if not self.me or not times or max(times) - min(times) < self.MIN_LENGTH:
            self.end_raw(keep=False)  # not kept, nor its traffic
            return
        t_lo = min(times)
        duration = max(times) - t_lo
        shift = lambda rows: [[round(r[0] - t_lo, 3), *r[1:]] for r in rows]  # start the replay at 0
        replay = dict(version=1, started=self.started, duration=round(duration, 3),
                      me=shift(self.me), rivals={k: shift(v) for k, v in self.rivals.items()})
        if self.level:
            replay["level"] = self.level
        track = self.track or own_track(self.level)
        if track:
            replay["track"] = track
        if self.field:
            replay["field"] = self.field
        if self.names:
            replay["names"] = {str(n): name for n, name in sorted(self.names.items())}
        if self.racer[0]:
            replay["player"] = dict(name=self.racer[0], id=self.racer[1])
        if self.racers:
            racers = []
            for _, r in sorted(self.racers.items()):
                if r["rows"]:
                    racer = dict(who=r["who"], rows=shift(r["rows"]))
                    if r.get("finish") is not None:
                        racer["finish"], racer["place"] = r["finish"], r["place"]
                    racers.append(racer)
            replay["progress"] = dict(length=self.length and round(self.length, 1), racers=racers)
        if self.rank_before:
            replay["rank"] = dict(before=list(self.rank_before))
            if self.rank_after:
                replay["rank"]["after"] = list(self.rank_after)
        # the lobby the race was matched in: not one of an earlier race (a race in the main world may be matched before
        # the capture began), so only when its players are the race's
        names = {e["name"] for e in self.field}
        lobby = [dict(e) for e in self.lobby if e["name"] in names]
        if len(lobby) >= 2 and len(lobby) * 2 > len(self.lobby):
            replay["lobby"] = lobby
        bots = [str(n) for n, votes in sorted(self.bots.items()) if votes > 0]
        if bots:
            replay["bots"] = bots
        path = self.store.save(replay, raw=self.end_raw(keep=True))
        self.saved.emit(path)

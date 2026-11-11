"""The racers' ranked standing: the player's own rank and points, and every player's points in the race's lobby, from
the game's servers. Found in the traffic of 16 online races of 2026-11-07/09.

The player's rank and points come as UE property data, in plain text UE strings (capture/roster.py) at any bit:

    "RacingSeason_4" "RacingRank_3_1" int32 points

once in the account's save data, which a server sends as the client connects to it, and twice at the finish (in
FRacingPlayerSeasonData, a few seconds before the race server's results): the points before the race, then after it
("RacingRank_3_1" 8863, then "RacingRank_3_2" 9038: 175 won, and the next rank). The points the save data gives on
connecting to a race are the ones the finish names first, race after race, so the latest named is the player's
standing.

The lobby: some 10 s before the race server connects, the server of the world the player waits in sends every
matched player's record (FRacingPlayerMatchExtraData):

    int64 account id  "name"  10 bits  "outfit"  33 bits  "frame"  33 bits  "card"  ...
    "FRacingPlayerMatchExtraData"  64 bits  int32 points  "Vehicle026"

the points the same as the player's own standing (the player's own record held the points of the save data each
time). The name of the account and its id are found back from the marker, as the first string with a player's id
(12 digits, 2142...) right before it and three more strings after it at those gaps: of 14 races, every record was
told right so (an "outfit" string has a 17 digit number before it now and then). Races in the main world are
matched while the player already is on its server, and those records may come before the capture began.
"""
import re

from capture.roster import ue_string

RANK = re.compile(rb"(RacingRank_\d{1,2}_\d{1,2})\x00")
RANK_MARK = b"RacingRank_"
LOBBY = b"FRacingPlayerMatchExtraData\x00"
CAR = re.compile(r"[Vv]ehicle_?\d{3}")
ID_LO, ID_HI = 10 ** 11, 10 ** 14  # a player's account id: 12 digits (2142..., 2182...)
BACK = 2000   # bits before the marker the record's name is looked for in
GAPS = (10, 33, 33)  # bits after the name, the outfit, the frame
MAX_POINTS = 10 ** 6


def size(s):
    """Bits a UE string of text s takes, its length included."""
    return 32 + (8 if s.isascii() else 16) * (len(s) + 1)


def record_name(n, nbits, end):
    """(account id, name) of the lobby record whose marker's length is at bit end, or None."""
    for bit in range(end - 1, max(64, end - BACK), -1):
        acc = (n >> (bit - 64)) & ((1 << 64) - 1)
        if not ID_LO <= acc < ID_HI:
            continue
        name = ue_string(n, bit, nbits)
        if not name:
            continue
        q = bit + size(name)
        for gap in GAPS:
            s = ue_string(n, q + gap, nbits)
            if s is None:
                break
            q += gap + size(s)
        else:
            return acc, name
    return None


def _shifted(marker):
    """The bytes marker leaves in a packet whichever bit it starts at: for each of the 8, the bytes it fills whole."""
    v = int.from_bytes(marker, "little")
    return [marker] + [(v << k).to_bytes(len(marker) + 1, "little")[1:len(marker)] for k in range(1, 8)]


MARKS = _shifted(RANK_MARK) + _shifted(LOBBY)


def named(payload):
    """True if the packet may hold a rank or a lobby record: a quick look for their markers at any bit, so that
    decode (slow) is run on few packets of all those captured."""
    return any(m in payload for m in MARKS)


def decode(payload):
    """([(rank, points)] in the order the packet names them, [dict(id, name, points, car)] of the lobby records in
    it) of one server packet."""
    if len(payload) < 64:
        return [], []
    n = int.from_bytes(payload, "little")
    nbits = len(payload) * 8
    ranks, lobby = {}, {}
    for k in range(8):  # the strings are at any bit: look at the packet shifted by each
        data = (n >> k).to_bytes(len(payload), "little") if k else payload
        if RANK_MARK in data:
            for m in RANK.finditer(data):
                text = m.group(1).decode("ascii")
                start = 8 * (m.start() - 4) + k
                end = start + size(text)
                if ue_string(n, start, nbits) == text and end + 32 <= nbits:
                    points = (n >> end) & 0xFFFFFFFF
                    if points < MAX_POINTS:
                        ranks[start] = (text, points)
        i = data.find(LOBBY)
        while i >= 0:
            start = 8 * (i - 4) + k
            end = start + 32 + 8 * len(LOBBY)
            car = ue_string(n, end + 96, nbits)
            if car and CAR.fullmatch(car) and ue_string(n, start, nbits) == LOBBY[:-1].decode():
                who = record_name(n, nbits, start)
                points = (n >> (end + 64)) & 0xFFFFFFFF
                if who and points < MAX_POINTS:
                    lobby[start] = dict(id=str(who[0]), name=who[1], points=points, car=car)
            i = data.find(LOBBY, i + 1)
    return [ranks[b] for b in sorted(ranks)], [lobby[b] for b in sorted(lobby)]


class Ranking:
    """The player's standing and the latest lobby, as the game's servers name them."""
    LOBBY_GAP = 10.0  # s: a lobby's records come all at once (in one packet or a few); later ones are another's

    def __init__(self):
        self.rank = None  # (rank, points) as last named
        self.lobby = []   # the latest lobby's records, dict(id, name, points, car), in the order they came
        self.lobby_at = None  # when its records last came

    def update(self, payload, now):
        """Take one server packet at time now (s); (the standing changed, the lobby changed)."""
        ranks, lobby = decode(payload)
        rank_changed = bool(ranks) and ranks[-1] != self.rank
        if ranks:
            self.rank = ranks[-1]
        if not lobby:
            return rank_changed, False
        if self.lobby_at is None or now - self.lobby_at > self.LOBBY_GAP:
            self.lobby = []  # the player's own record is in every lobby: a lobby is told by when it comes
        self.lobby_at = now
        before = list(self.lobby)
        for r in lobby:
            k = next((j for j, e in enumerate(self.lobby) if e["id"] == r["id"]), None)
            if k is None:
                self.lobby.append(r)
            else:
                self.lobby[k] = r
        return rank_changed, self.lobby != before

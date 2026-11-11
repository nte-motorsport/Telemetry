"""Whose car is whose: the race's entrants (capture/roster.py) matched to the cars on the map (capture/opponents.py).

Neither the entrants' records nor the cars' say who drives which car, so it is pieced together from how the race
server makes the cars, found in 16 online races with recorded traffic (2026-11-04/06):

- A car's id in the position records is part of the network id (UE NetGUID) of its DataReplicationManager. The
  server makes a car by sending that component's name with its id before it (an "export"):

      packed NetGUID  8-bit flags (7)  packed NetGUID of the car  "DataReplicationManager"

  the ids packed in 7 bits a byte with a "more" bit; the car id of the position records is the 12 bits from 2 bits
  into the component's id. The server numbers what it makes in order, so a car made later has a larger id.
- The players' cars are made in the order the players joined the race, which is the order of the slots their
  first entrant records give them (524, 576, 628, 680; the records are shuffled later). So the players' car ids in
  rising order are the players' names in that order: right for every player in 8 races where it could be checked
  (the player's own car among them; in one race the first records were missed and it went wrong).
- A bot's car is made with its "AIRacer_Vehicle018_09" name after it, followed by its parts ("V018_FrontKit_01");
  the bot's entrant record holds the same "AIRacer_..." name and the bot's own. Two bots may have one such name
  (two bots in Vehicle018, both "AIRacer_Vehicle018", 2026-11-11): then their cars go to them in the order of
  their slots, as the players' do. In 4 races of 2026-11-11 (8 bots) every bot's car was made in the order of the
  bots' slots, the players' cars in between.
"""
import re

from capture.roster import ue_string

DRM = b"DataReplicationManager"
AI_TAG = b"AIRacer_"
PART = re.compile(r"V\d{3}_")  # a car part: what follows a bot's name when the server makes its car


def unpack(n, bit):
    """A UE packed int at bit: (value, bit after it, bytes)."""
    v, shift, nbytes = 0, 0, 0
    while nbytes < 5:
        b = (n >> bit) & 0xFF
        v |= (b >> 1) << shift
        shift += 7
        bit += 8
        nbytes += 1
        if not b & 1:
            break
    return v, bit, nbytes


def next_string(n, bit, nbits, span=400):
    """The first UE string of 4+ characters within span bits after bit (a car's parts come ~180 bits after the
    bot's name), or None."""
    for b in range(bit, min(bit + span, nbits - 32)):
        s = ue_string(n, b, nbits)
        if s and len(s) >= 4:
            return s
    return None


class Identity:
    """The bots' cars, from the server making them; and the matching, given the field and the cars."""

    def __init__(self):
        self.tags = {}       # car id -> the bot's "AIRacer_..." name
        self.untagged = None  # the car made last, while no "AIRacer_..." name has followed it

    def feed(self, payload):
        """Take one packet of the race server."""
        if len(payload) < 40:
            return
        n = int.from_bytes(payload, "little")
        nbits = len(payload) * 8
        events = []
        for k in range(8):  # strings sit at any bit
            data = (n >> k).to_bytes(len(payload), "little") if k else payload
            for key in (DRM, AI_TAG):
                i = data.find(key)
                while i >= 0:
                    events.append((8 * (i - 4) + k, key))  # where its length is
                    i = data.find(key, i + 1)
        for bit, key in sorted(events):
            if key == DRM:
                if ue_string(n, bit, nbits) != DRM.decode():
                    continue
                # 2-byte ids only: the position records' car id has 12 bits
                own, after, nb1 = unpack(n, bit - 48)
                outer, end, nb2 = unpack(n, after + 8)
                if nb1 == 2 and nb2 == 2 and end + 8 == bit and (n >> after) & 0xFF == 7:
                    self.untagged = (n >> (bit - 46)) & 0xFFF
            else:
                tag = ue_string(n, bit, nbits)
                if not tag or not tag.startswith("AIRacer_") or self.untagged is None:
                    continue
                nxt = next_string(n, bit + 32 + 8 * (len(tag) + 1), nbits)
                if nxt and PART.match(nxt):  # not the bot's entrant record, which has "Robot0045" next
                    self.tags[self.untagged] = tag
                    self.untagged = None

    def match(self, order, bot_tags, humans, bots, own=None, me=""):
        """{car id: name}. order: the entrants' names in the order they joined (roster.Roster.order); bot_tags:
        {bot's name: the "AIRacer_..." names its records gave it}; humans, bots: the car ids of the other players and of the bots; own:
        the player's own car id, if the server sends it (in some races it doesn't, or it isn't known yet); me:
        the player's name. Players are only named once every one's car is known.

        The player and their own car are left out of the order whenever they are known: the order goes wrong
        now and then (a car's id comes from a part the server may send late: in one race of 22 the player's car
        had a larger id than the next player's), and then it would give the player's name to a rival."""
        names = set(bot_tags)
        people = [name for name in order if name not in names]
        cars = sorted(set(humans) - {own})
        if me not in people and own is not None and len(cars) + 1 == len(people):
            me = people[sorted(cars + [own]).index(own)]  # the player's name not set: the order's guess
        if me in people:
            people.remove(me)
        out = dict(zip(cars, people)) if len(cars) == len(people) else {}
        # each bot's car by its "AIRacer_..." name; the cars of one such name to its bots in the order of their slots,
        # when as many of each are known
        for tag in set(self.tags.values()):
            made = sorted(car for car, t in self.tags.items() if t == tag)
            whose = [name for name in order if tag in bot_tags.get(name, ())]
            if len(made) == len(whose):
                out.update((car, name) for car, name in zip(made, whose) if car in bots)
        return out

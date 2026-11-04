"""Who races: each entrant's car and name, and whether it is a bot, from the race server's packets.

Right after the race server connects (some 20-30 s before the start), it sends a record for every entrant, in
plain text UE strings (an int32 length, NUL included, then the text) but packed at any bit, not just at bytes:

  "Vehicle026"  int32 0  int16 slot  int16 0  int16 0xFF00  int16 1  int16 0  "<driver's name>"

the slot one of a few fixed values a race (its place in the field), the car a row of the game's vehicle table
(see ui/vehicles.py). A bot also has a record that starts with "AIRacer_Vehicle..." and holds its name a little
further on. The records do not say which of the cars on the map (capture/opponents.py) is whose: they list the
field. Found in seven online races with recorded traffic (2026-11-04).
"""
import re

CAR = re.compile(rb"((?:AIRacer_)?[Vv]ehicle_?\d{3})\x00")
GAP = [0, 0xFF00, 1, 0]  # the int16s between the slot and the name
BOT = "AIRacer_"


def ue_string(n, bit, nbits):
    """The UE string at bit of the packet n (an int, LSB-first bits), or None."""
    if bit < 0 or bit + 32 > nbits:
        return None
    ln = (n >> bit) & 0xFFFFFFFF
    if not 2 <= ln <= 64 or bit + 32 + 8 * ln > nbits:
        return None
    raw = ((n >> (bit + 32)) & ((1 << (8 * ln)) - 1)).to_bytes(ln, "little")
    if raw[-1] != 0 or not re.fullmatch(rb"[ -~]+", raw[:-1]):
        return None
    return raw[:-1].decode("ascii")


def decode(payload):
    """([(slot, car id, name)], {bot names}) for the entrant records in one server packet."""
    if b"ehicle" not in payload and len(payload) < 64:
        return [], set()
    n = int.from_bytes(payload, "little")
    nbits = len(payload) * 8
    entrants, bots = [], set()
    for k in range(8):  # the strings are at any bit: look at the packet shifted by each
        data = (n >> k).to_bytes(len(payload), "little") if k else payload
        if b"ehicle" not in data:
            continue
        for m in CAR.finditer(data):
            text = m.group(1).decode("ascii")
            start = 8 * (m.start() - 4) + k  # where its length is
            if ue_string(n, start, nbits) != text:
                continue
            end = start + 32 + 8 * (len(text) + 1)
            if text.startswith(BOT):
                # a bot's record: its name is one of the strings that follow
                bit, found = end, 0
                while bit < min(end + 600, nbits - 32) and found < 3:
                    s = ue_string(n, bit, nbits)
                    if s:
                        if not s.lower().startswith("vehicle"):
                            bots.add(s)
                        found += 1
                        bit += 32 + 8 * (len(s) + 1)
                    else:
                        bit += 1
                continue
            if (n >> end) & 0xFFFFFFFF:
                continue
            slot = (n >> (end + 32)) & 0xFFFF
            if [(n >> (end + 48 + 16 * i)) & 0xFFFF for i in range(4)] != GAP:
                continue  # some other record with a car in it (the player's garage, a part)
            name = ue_string(n, end + 112, nbits)
            if name:
                entrants.append((slot, text, name))
    return entrants, bots


class Roster:
    """The field of one race server, as its records come in."""

    def __init__(self):
        self.entrants = {}  # slot -> (car id, name)
        self.bots = set()   # names of the bots

    def update(self, payload):
        """Take one server packet; True if the field changed."""
        entrants, bots = decode(payload)
        changed = False
        for slot, car, name in entrants:
            if self.entrants.get(slot) != (car, name):
                self.entrants[slot] = (car, name)
                changed = True
        if bots - self.bots:
            self.bots |= bots
            changed = True
        return changed

    def field(self):
        """[dict(car, name, bot)] in slot order."""
        return [dict(car=car, name=name, bot=name in self.bots)
                for _, (car, name) in sorted(self.entrants.items())]

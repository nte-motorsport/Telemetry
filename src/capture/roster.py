"""Who races: each entrant's car and name, and whether it is a bot, from the race server's packets.

Right after the race server connects (some 20-30 s before the start), it sends a record for every entrant, in
plain text UE strings (an int32 length, NUL included, then the text) but packed at any bit, not just at bytes:

  "Vehicle026"  int32 0  int16 slot  int16 0  int16 0xFF00  int16 1  int16 0  "<driver's name>"

the slot one of a few fixed values a race (524, 576, 628, 680 for four), the car a row of the game's vehicle table
(see ui/vehicles.py). The slots are not the entrants' own: the server sends the records again, shuffled, as the
race loads (2-3 times in 10 s), so an entrant is known by name. A name of other than ASCII is sent as UTF-16 (its
length negative, in characters): "я Ваня" was missing from five races of 2026-11-05 and whoever had their slot
before was listed twice instead. A bot also has a record that starts with "AIRacer_Vehicle..." and holds its
name a little further on (not every bot's: in two races of three bots one was named so). The records do not say
which of the cars on the map (capture/opponents.py) is whose: they list the field; capture/identity.py matches
them up, from the order of the slots the entrants were first given and the bots' "AIRacer_..." names. Found in
seven online races with recorded traffic (2026-11-04).
"""
import re

# a bot's car may have a number after it, "AIRacer_Vehicle018_09": with it, two bots of three went unnamed in
# two races (2026-11-05)
CAR = re.compile(rb"((?:AIRacer_)?[Vv]ehicle_?\d{3}(?:_\d+)?)\x00")
NOT_NAME = re.compile(r"(?i)(robot\d|vehicle|airacer_|v\d{3}_)")  # the other strings near a bot's name
ROBOT = re.compile(r"Robot\d+")  # the string before a bot's name
GAP = [0, 0xFF00, 1, 0]  # the int16s between the slot and the name
# The player's own account, as each of the game's servers sends it on connecting (and again now and then), in UE
# property tags: "RoleId" "Int64Property" ... id ... "RoleName" "StrProperty" ... name. The fields between are
# of fixed size, so the id and the name are at fixed bits from the start of "RoleId" (its length): the same in
# all 22 captures of 2026-11-04/06, which held no one else's. Account ids of players have 12 digits (2142...,
# 2182...); bots' have 17.
ROLE = b"RoleId\0"
ROLE_ID, ROLE_NAME = 304, 672  # bits from the length of "RoleId"
BOT = "AIRacer_"


def ue_string(n, bit, nbits):
    """The UE string at bit of the packet n (an int, LSB-first bits), or None."""
    if bit < 0 or bit + 32 > nbits:
        return None
    ln = (n >> bit) & 0xFFFFFFFF
    if ln >= 1 << 31:  # UTF-16: -ln characters
        chars = (1 << 32) - ln
        if not 2 <= chars <= 64 or bit + 32 + 16 * chars > nbits:
            return None
        raw = ((n >> (bit + 32)) & ((1 << (16 * chars)) - 1)).to_bytes(2 * chars, "little")
        if raw[-2:] != b"\0\0":
            return None
        try:
            text = raw[:-2].decode("utf-16-le")
        except UnicodeDecodeError:
            return None
        return text if text.isprintable() else None
    if not 2 <= ln <= 64 or bit + 32 + 8 * ln > nbits:
        return None
    raw = ((n >> (bit + 32)) & ((1 << (8 * ln)) - 1)).to_bytes(ln, "little")
    if raw[-1] != 0 or not re.fullmatch(rb"[ -~]+", raw[:-1]):
        return None
    return raw[:-1].decode("ascii")


def decode_role(n, nbits, bit):
    """(account id, name) of the "RoleId" record whose string's length is at bit, or None."""
    if (ue_string(n, bit, nbits) != "RoleId" or ue_string(n, bit + 88, nbits) != "Int64Property"
            or ue_string(n, bit + 368, nbits) != "RoleName" or bit + ROLE_NAME + 32 > nbits):
        return None
    name = ue_string(n, bit + ROLE_NAME, nbits)
    acc = (n >> (bit + ROLE_ID)) & ((1 << 64) - 1)
    return (acc, name) if name and 0 < acc < 10 ** 15 else None


def decode(payload):
    """([(slot, car id, name)], {bot's "AIRacer_..." name: its name}, the player's own (account id, name) or None)
    for the records in one server packet."""
    if b"ehicle" not in payload and len(payload) < 64:
        return [], {}, None
    n = int.from_bytes(payload, "little")
    nbits = len(payload) * 8
    entrants, bots, role = [], {}, None
    for k in range(8):  # the strings are at any bit: look at the packet shifted by each
        data = (n >> k).to_bytes(len(payload), "little") if k else payload
        i = data.find(ROLE)
        if i >= 0 and role is None:
            role = decode_role(n, nbits, 8 * (i - 4) + k)
        if b"ehicle" not in data:
            continue
        for m in CAR.finditer(data):
            text = m.group(1).decode("ascii")
            start = 8 * (m.start() - 4) + k  # where its length is
            if ue_string(n, start, nbits) != text:
                continue
            end = start + 32 + 8 * (len(text) + 1)
            if text.startswith(BOT):
                # a bot's record: "AIRacer_Vehicle018_09", "Robot0045", "Vehicle018" (not always), its name. Some
                # are cut short, the next bot's "Robot0108" right after: the name is the string after this record's
                # own "Robot" one (else "@%", noise after the next's, was taken once)
                bit, robot = end, False
                while bit < min(end + 600, nbits - 32):
                    s = ue_string(n, bit, nbits)
                    if s and s.startswith(BOT):
                        break  # the next bot's record: this one was cut short ("Robot0108" was the next's)
                    if s and (robot or ROBOT.fullmatch(s)):
                        if robot and not NOT_NAME.match(s):
                            bots[text] = s
                            break
                        robot = True
                        bit += 32 + (8 if s.isascii() else 16) * (len(s) + 1)
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
    return entrants, bots, role


class Roster:
    """The field of one race server, as its records come in."""

    def __init__(self):
        self.entrants = {}  # name -> car id, from the latest record of each
        # name -> (slot, how many came before): the slot of an entrant's first record. The slots are given in the
        # order the entrants joined, and that is the order the server makes their cars in (capture/identity.py)
        self.first = {}
        self.bots = {}      # bot's "AIRacer_..." name -> its name
        self.role = None    # the player's own (account id, name), once the server has sent it

    def update(self, payload):
        """Take one server packet; True if the field changed."""
        entrants, bots, role = decode(payload)
        if role:
            self.role = role
        changed = False
        for slot, car, name in entrants:
            if name not in self.first:
                self.first[name] = (slot, len(self.first))
                changed = True
            if self.entrants.get(name) != car:
                self.entrants[name] = car
                changed = True
        for tag, name in bots.items():
            if self.bots.get(tag) != name:
                self.bots[tag] = name
                changed = True
        return changed

    def order(self):
        """The entrants' names in the order they joined."""
        return sorted(self.entrants, key=lambda name: self.first[name])

    def field(self):
        """[dict(car, name, bot)] in the order they joined."""
        bots = set(self.bots.values())
        return [dict(car=self.entrants[name], name=name, bot=name in bots) for name in self.order()]

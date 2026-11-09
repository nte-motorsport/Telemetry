"""How far along the track each racer is, as the Multiplayer and Replays pages write it: their place, how far ahead of
or behind the player, how much of the race done and how much is left (capture/progress.py)."""
from ui import units

FINISHED = 0.9995  # share of the race done at the finish line (1, give or take a float's rounding)


def by_name(racers, names, me, entrants):
    """{entrant's name, or "" for the player: racer} of racers (dict(place, share, metres, who), see
    progress.Standings.snapshot) told apart: the player's by who "me", a rival's by its number's name in names. A
    racer not told apart yet goes to the one entrant left without one, when only one is left."""
    out = {}
    for r in racers:
        if r["who"] == "me":
            out[""] = r
        elif r["who"] is not None and names.get(r["who"]):
            out[names[r["who"]]] = r
    left = [r for r in racers if r not in out.values()]
    unnamed = [e["name"] for e in entrants if e["name"] != me and e["name"] not in out]
    if len(left) == 1 and len(unnamed) == 1:
        out[unnamed[0]] = left[0]
    return out


def lines(r, mine, length):
    """(the place and gap, the share done and what is left) of racer r as written; mine: the player's own racer,
    or None."""
    head = f"P{r['place']}"
    if mine is not None and r is not mine and r["metres"] is not None and mine["metres"] is not None:
        gap = r["metres"] - mine["metres"]
        head += f"  ·  {units.length_text(gap)} {'ahead' if gap >= 0 else 'behind'}"
    if r["share"] >= FINISHED:
        return head, "Finished"
    detail = f"{r['share'] * 100:.0f}% done"
    if length:
        detail += f"  ·  {units.length_text(length * (1 - r['share']))} to go"
    return head, detail

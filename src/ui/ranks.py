"""The racing ranks, from the game's DT_RacingTier table (2026-11-11): a rank's name and colour, and the rank points
put a player in.

A row "RacingRank_<tier>_<step>" holds UpgradeScore, the points that take a player on to the next row: 1000 for
RacingRank_1_1, 1000 more for each row after, up to 16000 for RacingRank_4_4; RacingRank_5_1 is the last (-1). So a
rank is how many thousands of points a player has, the four steps of a tier written IV (the first) to I. The table
also has DowngradeBufferScore (32-125 points): a player who drops below a rank's points keeps it for that many, so
a rank told from points alone may be one too low for a player just under a step (the player's own rank is the one
the server names, capture/ranking.py). The names are the table's Chinese text (新人车手, 业余车手, 职业车手, 传奇车手,
超凡车手) put into English; the game's English text isn't in its files."""

TIERS = {  # tier -> (name, colour: the table's TierColor)
    1: ("Rookie", "#C0AE8B"),
    2: ("Amateur", "#1DC795"),
    3: ("Pro", "#22A2E3"),
    4: ("Legend", "#AF4ED8"),
    5: ("Transcendent", "#E7B52A"),
}
STEP = 1000  # points between ranks
NUMERALS = ("IV", "III", "II", "I")  # a tier's steps as the game writes them: RacingRank_3_1 is Pro IV


def from_points(points):
    """The rank row ("RacingRank_3_2") a player with points is at."""
    k = max(0, int(points) // STEP)
    if k >= 16:
        return "RacingRank_5_1"
    return f"RacingRank_{k // 4 + 1}_{k % 4 + 1}"


def parts(rank):
    """(tier, step) of a rank row, or None."""
    try:
        _, tier, step = rank.split("_")
        return int(tier), int(step)
    except ValueError:
        return None


def name(rank):
    """A rank row as written: "RacingRank_3_2" -> "Pro III"."""
    p = parts(rank)
    if not p or p[0] not in TIERS:
        return rank
    tier, step = p
    return TIERS[tier][0] if tier == 5 else f"{TIERS[tier][0]} {NUMERALS[min(max(step, 1), 4) - 1]}"


def color(rank):
    p = parts(rank)
    return TIERS[p[0]][1] if p and p[0] in TIERS else None

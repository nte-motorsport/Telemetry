"""Make the website's race simulation from a recorded replay: one lap of every car, looped, and the game map
under it. Run with the app's venv, from the Telemetry folder:

    .venv\\Scripts\\python website\\tools\\make_lap.py "%APPDATA%\\NTE Telemetry\\replays\\<replay>.json.gz" [lap] [--spread s]
        [--you <replay>]

The replay needs its sectors (recorded since 2026-11-17) and a lap every car drove in full (lap 2 by default: a
flying lap, so the loop has no standing start). Each car's lap is stretched to one shared period, so the loop
closes without the cars drifting apart, and the cars start it as far apart as they crossed the line, the rivals
then each SPREAD s (--spread) further back than the one before them, so they don't run in one bunch. The map is
drawn from the installed map pack of the replay's world (as the Replays page draws it).

--you takes the player's lap from another replay of the same track instead: the fastest lap driven in full there
(line to line, the line being the course's finish checkpoint), e.g. a cleaner one than in the race the rivals come
from. It starts the loop where the player's own lap of this race does.

Writes website/src/lap.json and website/public/assets/ui/lap-map.webp. Rivals are named as the app names bots
(the game's bot names); the player is "You", so no player's name ends up on the site."""
import gzip
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WEBSITE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(WEBSITE), "src"))

from PySide6.QtGui import QColor, QImage, QPainter, QTransform  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui import theme  # noqa: E402
from ui.multiplayer_page import RIVAL_COLORS  # noqa: E402
from ui.world_map import MapImage, all_maps  # noqa: E402

RATE = 10  # samples per second in the output
# The map's view, in px: the size the site's chart is drawn at (its aspect), and the image is twice that, for
# screens with two pixels per px.
VIEW_W, VIEW_H = 600, 420
SCALE = 2
MARGIN = 1.08  # the view around the lap, as the app fits the map to a race
SPREAD = 10.0  # s: each rival starts the loop this much further back than the one that crossed the line before it


def load(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def rows(data):
    """[t, x, y, z, km/h] as an array; missing speeds filled in between the known ones."""
    a = np.array([[np.nan if v is None else v for v in row] for row in data], float)
    ok = np.isfinite(a[:, 4])
    a[:, 4] = np.interp(a[:, 0], a[ok, 0], a[ok, 4])
    return a


def lap_of(a, t0, t1, period):
    """The car's lap from t0 to t1 at RATE over the shared period: (x, y, km/h) arrays. The few metres (and km/h)
    the lap's end is off its start are spread over the lap, so the loop closes."""
    n = int(round(period * RATE))
    phase = np.arange(n) / n
    t = t0 + phase * (t1 - t0)
    out = []
    for k in (1, 2, 4):
        v = np.interp(t, a[:, 0], a[:, k])
        end = np.interp(t1, a[:, 0], a[:, k])
        out.append(v - (end - v[0]) * phase)
    return out


def passes(a, point, near=25.0):
    """The times the drive a ([t, x, y, ...]) crosses the line through point, square to the way it goes: one for
    each time it comes within `near` m of it, found between the samples either side of the line."""
    d = np.hypot(a[:, 1] - point[0], a[:, 2] - point[1])
    out = []
    i = 0
    while i < len(a):
        if d[i] >= near:
            i += 1
            continue
        j = i
        while j < len(a) and d[j] < near:
            j += 1
        k = min(max(i + int(np.argmin(d[i:j])), 1), len(a) - 2)
        way = a[k + 1, 1:3] - a[k - 1, 1:3]
        along = (a[k - 1:k + 2, 1:3] - point) @ way  # before the line < 0 < after it
        m = 0 if along[1] >= 0 else 1
        lo, hi = along[m], along[m + 1]
        f = -lo / (hi - lo) if hi != lo else 0.0
        out.append(a[k - 1 + m, 0] + f * (a[k + m, 0] - a[k - 1 + m, 0]))
        i = j
    return out


def fastest_lap(a, point, shortest=30.0):
    """(t0, t1) of the quickest lap from the line to the line in drive a, or None."""
    t = passes(a, point)
    laps = [(t0, t1) for t0, t1 in zip(t, t[1:]) if t1 - t0 >= shortest]
    return min(laps, key=lambda lap: lap[1] - lap[0]) if laps else None


def nice(span, n):
    raw = span / n
    p = 10 ** math.floor(math.log10(raw))
    f = raw / p
    return (1 if f < 1.5 else 2 if f < 3 else 5 if f < 7 else 10) * p


def main():
    args = sys.argv[1:]
    spread = SPREAD
    if "--spread" in args:
        i = args.index("--spread")
        spread = float(args[i + 1])
        del args[i:i + 2]
    you = None
    if "--you" in args:
        i = args.index("--you")
        you = args[i + 1]
        del args[i:i + 2]
    path = args[0]
    lap = int(args[1]) if len(args) > 1 else 2
    r = load(path)
    sec = r["sectors"]
    finish = len(sec["course"]["checkpoints"]) - 1  # the last checkpoint is the line
    bots = set(r.get("bots") or [])
    names = r.get("names") or {}

    cars = []  # (key, name, colour, rows, lap start, lap end, when it starts the loop)
    for key in ["me"] + sorted(r["rivals"], key=int):
        cross = {(c[0], c[1]): c[2] for c in sec["racers"].get(key, {}).get("cross", [])}
        t0, t1 = cross.get((lap - 1, finish)), cross.get((lap, finish))
        if t0 is None or t1 is None:
            print(f"{key}: no full lap {lap}, left out")
            continue
        if key == "me":
            name, color = "You", theme.ACCENT
        else:
            name = names.get(key, f"Racer {key}")
            if key in bots:
                name = f":{name}:"  # as the app writes a bot's name
            color = RIVAL_COLORS[(int(key) - 1) % len(RIVAL_COLORS)]
        a = rows(r["me"] if key == "me" else r["rivals"][key])
        start = t0
        if key == "me" and you:
            cp = sec["course"]["checkpoints"][finish]
            a = rows(load(you)["me"])
            lap_there = fastest_lap(a, np.array([cp["x"], cp["y"]]))
            if lap_there is None:
                sys.exit(f"no full lap of the player in {you}")
            t0, t1 = lap_there
            print(f"You: the {t1 - t0:.1f} s lap of {os.path.basename(you)}")
        cars.append((key, name, color, a, t0, t1, start))
    if not cars:
        sys.exit("no car drove that lap in full")

    period = float(np.mean([c[5] - c[4] for c in cars]))
    first = min(c[6] for c in cars)
    # the rivals pulled apart: the k-th of them over the line starts k * spread s later still
    rivals = sorted((c for c in cars if c[0] != "me"), key=lambda c: c[6])
    extra = {c[0]: k * spread for k, c in enumerate(rivals)}
    laps = [(name, color, (start - first + extra.get(key, 0.0)) % period, lap_of(a, t0, t1, period))
            for key, name, color, a, t0, t1, start in cars]

    # the view: screen x is the game's y, screen y its x (up), as on the app's map
    sx = np.concatenate([y for *_, (x, y, v) in laps])
    sy = np.concatenate([x for *_, (x, y, v) in laps])
    cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2
    m_per_px = max((sx.max() - sx.min()) / VIEW_W, (sy.max() - sy.min()) / VIEW_H) * MARGIN
    x0, y1 = cx - VIEW_W / 2 * m_per_px, cy + VIEW_H / 2 * m_per_px  # the view's left and top, in metres

    app = QApplication.instance() or QApplication([])
    world = r.get("level") or ""
    world_map = next((m for m in all_maps() if world in m.worlds), None)
    img = QImage(VIEW_W * SCALE, VIEW_H * SCALE, QImage.Format_RGB32)
    img.fill(QColor(0, 0, 0))
    if world_map is None:
        print(f"no map pack of {world} installed: the map is left black")
    else:
        p = QPainter(img)
        k = SCALE / m_per_px
        p.setTransform(QTransform(k, 0, 0, -k, -x0 * k, y1 * k))  # metres -> image px, y up
        MapImage(world_map).paint(p)
        p.end()
    out_img = os.path.join(WEBSITE, "public", "assets", "ui", "lap-map.webp")
    if not img.save(out_img, "WEBP", 82):
        sys.exit("couldn't write " + out_img)

    def px(v, lo, sign):
        return [round(float(n), 1) for n in (v - lo) / m_per_px * sign]

    data = {
        "track": r.get("track"),
        "period": round(period, 3),
        "rate": RATE,
        "view": [VIEW_W, VIEW_H],
        "metresPerPx": round(m_per_px, 4),
        "cars": [
            {
                "name": name,
                "color": color,
                "offset": round(offset, 3),
                "x": px(y, x0, 1),  # px from the view's left
                "y": px(x, y1, -1),  # px from its top
                "speed": [round(float(n), 1) for n in v],
            }
            for name, color, offset, (x, y, v) in laps
        ],
    }
    with open(os.path.join(WEBSITE, "src", "lap.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"{len(laps)} cars, a {period:.1f} s lap, {m_per_px:.2f} m/px:", ", ".join(n for n, *_ in laps))


if __name__ == "__main__":
    main()

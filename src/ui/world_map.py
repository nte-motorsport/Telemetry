"""Game map images under the tracks, from map packs: plug-ins kept outside the app, in
%APPDATA%\\NTE Telemetry\\maps. The app knows no map or world by name: a pack says which game world it is the map
of, and the world the server names (capture/levels.py) picks the pack.

A pack is a .ntemap file (a zip, its entries stored as they are) or, for making one, a folder with the same in
it; tools/build_map.py makes packs from the game's map tiles:

  map.json                  {"level": the game world (UE level path), as the server names it,
                             "title": a name to show (the file's name if left out),
                             "grid": [columns, rows], "tile": tile size in px,
                             "pixel_to_world": [[a, b, c], [d, e, f]],   world x = a*u + b*v + c,
                                                                         world y = d*u + e*v + f, (u, v) a pixel
                             "levels": tile levels, "roads_level": the level of roads.png}
  tiles/<k>/<row>_<col>.png level k: each tile covers 2^k x 2^k tiles of level 0, the full-size one
  roads.png                 where the roads are, at roads_level, as a grey mask: tells a drive's map while the
                            world isn't known (see MapPicker)
"""
import json
import math
import os
import zipfile
from collections import OrderedDict

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap, QTransform

import pyqtgraph as pg

from ui.prefs import data_dir

EXT = ".ntemap"


def maps_dir():
    d = os.path.join(data_dir(), "maps")
    os.makedirs(d, exist_ok=True)
    return d


class Pack:
    """The files of a pack, read by name: from a .ntemap file or a folder."""

    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if os.path.isfile(path) else None

    def read(self, name):
        """The bytes of a file in the pack, or None."""
        try:
            if self.zip is not None:
                return self.zip.read(name)
            with open(os.path.join(self.path, *name.split("/")), "rb") as f:
                return f.read()
        except (KeyError, OSError):
            return None

    def close(self):
        if self.zip is not None:
            self.zip.close()
            self.zip = None


class WorldMap:
    """One map: its tiles at every level, read as they are needed, where it lies, and its roads."""
    CACHE = 192  # tiles kept in memory

    def __init__(self, pack, meta):
        self.pack = pack
        self.file = os.path.basename(pack.path)
        self.name = meta.get("title") or os.path.splitext(self.file)[0]
        self.level = meta.get("level")
        self.cols, self.rows = meta["grid"]
        self.tile = meta["tile"]
        self.levels = meta.get("levels", 1)
        (a, b, c), (d, e, f) = meta["pixel_to_world"]
        self.to_world = np.array([[a, b], [d, e]], float), np.array([c, f], float)
        self.to_pixel = np.linalg.inv(self.to_world[0])
        # pixel (u, v) -> the map chart's coordinates, which are (world y, world x)
        self.transform = QTransform(d, a, e, b, f, c)
        self.size = (self.cols * self.tile, self.rows * self.tile)
        self.pixmaps = OrderedDict()  # (level, row, col) -> QPixmap or None, the latest used last
        self.roads = None
        self.roads_level = meta.get("roads_level")

    @classmethod
    def load(cls, path):
        """The map pack at path (a .ntemap file or a folder), or None if it isn't one."""
        pack = None
        try:
            pack = Pack(path)
            meta = json.loads(pack.read("map.json") or b"")
            return cls(pack, meta)
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, np.linalg.LinAlgError):
            if pack is not None:
                pack.close()
            return None

    def grid(self, level):
        """Columns and rows of tiles at a level."""
        return -(-self.cols // 2 ** level), -(-self.rows // 2 ** level)

    def pixmap(self, level, row, col):
        key = (level, row, col)
        if key in self.pixmaps:
            self.pixmaps.move_to_end(key)
            return self.pixmaps[key]
        data = self.pack.read(f"tiles/{level}/{row}_{col}.png")
        pm = None
        if data:
            pm = QPixmap()
            if not pm.loadFromData(data):
                pm = None
        self.pixmaps[key] = pm
        while len(self.pixmaps) > self.CACHE:
            self.pixmaps.popitem(last=False)
        return pm

    def on_road(self, x, y):
        """Share of the world points (x, y arrays) that lie on this map's roads (0 outside it)."""
        if self.roads is None:
            data = self.pack.read("roads.png") if self.roads_level is not None else None
            img = QImage.fromData(data).convertToFormat(QImage.Format_Grayscale8) if data else QImage()
            if img.isNull():
                self.roads_level = None
                return 0.0
            a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width()]
            road = a > 127
            # a pixel either way still counts: the drive's line and the drawn road are both a little off
            grown = road.copy()
            grown[1:] |= road[:-1]
            grown[:-1] |= road[1:]
            grown[:, 1:] |= road[:, :-1]
            grown[:, :-1] |= road[:, 1:]
            self.roads = grown
        if not len(x):
            return 0.0
        t = self.to_world[1]
        p = (self.to_pixel @ (np.c_[x, y] - t).T) / 2 ** self.roads_level
        u, v = np.floor(p).astype(int)
        h, w = self.roads.shape
        inside = (u >= 0) & (u < w) & (v >= 0) & (v < h)
        hit = np.zeros(len(u), bool)
        hit[inside] = self.roads[v[inside], u[inside]]
        return float(hit.mean())


_maps = []
_scanned = False


def all_maps():
    """Every map pack in the maps folder, loaded once: the pages share them, and with them their tiles in
    memory and their roads. The same list object throughout: rescan() changes it in place."""
    global _scanned
    if not _scanned:
        rescan()
    return _maps


def rescan():
    """Look at the maps folder again (a pack was added or removed)."""
    global _scanned
    _scanned = True
    for m in _maps:
        m.pack.close()
    d = maps_dir()
    found = []
    for name in sorted(os.listdir(d)):
        path = os.path.join(d, name)
        if (os.path.isfile(path) and name.lower().endswith(EXT)) or os.path.isfile(os.path.join(path, "map.json")):
            m = WorldMap.load(path)
            if m is not None:
                found.append(m)
    _maps[:] = found


def install(path):
    """Copy a map pack (a .ntemap file) into the maps folder and load it; the WorldMap, or None if it isn't a
    map pack."""
    import shutil
    probe = WorldMap.load(path) if os.path.isfile(path) else None
    if probe is None:
        return None
    probe.pack.close()
    for m in _maps:  # a pack of the same name is replaced: let go of its file first
        m.pack.close()
    shutil.copyfile(path, os.path.join(maps_dir(), os.path.basename(path)))
    rescan()
    return next((m for m in _maps if m.file == os.path.basename(path)), None)


class MapImage(pg.GraphicsObject):
    """A WorldMap drawn under the tracks: of the level whose pixels are the nearest to the screen's (not
    smaller), only the tiles in view."""

    def __init__(self, world_map):
        super().__init__()
        self.map = world_map
        self.setZValue(-10)  # under the tracks and the markers

    def boundingRect(self):
        return self.map.transform.mapRect(QRectF(0, 0, *self.map.size))

    def paint(self, p, *_):
        m = self.map
        to_device = m.transform * p.transform()  # full-size image pixel -> screen pixel
        inverted, ok = to_device.inverted()
        if not ok:
            return
        on_screen = math.sqrt(abs(to_device.determinant()))  # screen px per image px
        k = 0
        while k + 1 < m.levels and on_screen * 2 ** (k + 1) <= 1:
            k += 1  # the next level, half as fine, still has a pixel per screen pixel
        span = m.tile * 2 ** k  # full-size px one tile of level k covers
        view = inverted.mapRect(QRectF(p.viewport()))
        cols, rows = m.grid(k)
        c0, c1 = max(int(view.left() // span), 0), min(int(view.right() // span), cols - 1)
        r0, r1 = max(int(view.top() // span), 0), min(int(view.bottom() // span), rows - 1)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setTransform(m.transform, True)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                pm = m.pixmap(k, r, c)
                if pm is not None:
                    p.drawPixmap(QRectF(c * span, r * span, span, span), pm, QRectF(pm.rect()))


class MapPicker:
    """Which of several maps a drive is on. Maps can share the world's coordinates (a race track lies where a
    part of the city is), so where the drive is says nothing by itself.

    Once the world is known (set_level: the server names it) its map is the one, or none if there is no map
    of it. Until then the roads tell: a map is taken once most of the drive lies on its roads and clearly
    more than on any other's; till then (a stretch that fits two maps alike, a track there is no map of) the
    one taken before stays. On the replays recorded so far, minute-long stretches never picked a wrong map
    this way, but in the hills of the main world only a third of a drive lay on the roads it could see."""
    MIN = 0.5      # share of the drive on the map's roads
    MARGIN = 0.2   # by which that share beats every other map's
    MIN_POINTS = 100

    def __init__(self, maps):
        self.maps = maps  # all_maps(): kept as it is, so a pack installed later is seen
        self.current = None
        self.level = ""  # the world, "" while not known

    def of_level(self, level):
        """The map of a world, or None."""
        return next((m for m in self.maps if m.level and (level == m.level or level.startswith(m.level + "/"))),
                    None)

    def set_level(self, level):
        """The world the game is in ("" when not known): its map, if there is one, is the one from now on."""
        self.level = level or ""
        self.current = self.of_level(self.level) if self.level else None

    def reset(self):
        """Another place (a teleport): no map until the drive tells again. A known world stays known: a new
        one is told by set_level."""
        if not self.level:
            self.current = None

    def update(self, x, y):
        """Take the drive (world x, y arrays, the latest stretch of it) and return the map it is on, or None."""
        if self.level:
            self.current = self.of_level(self.level)  # (again: the packs may have changed)
            return self.current
        if self.current is not None and self.current not in self.maps:
            self.current = None  # its pack was replaced or removed
        if len(x) >= self.MIN_POINTS and self.maps:
            shares = sorted(((m.on_road(x, y), i) for i, m in enumerate(self.maps)), reverse=True)
            best, i = shares[0]
            second = shares[1][0] if len(shares) > 1 else 0.0
            if best >= self.MIN and best - second >= self.MARGIN:
                self.current = self.maps[i]
        return self.current

r"""Align a recorded drive with a game map's tiles by hand, and save where the map lies in the world: the
"pixel_to_world" of the source folder's map.json, which tools/build_map.py then makes a map pack of.

    python tools/align_map.py <source folder with the tiles> <replay .json.gz> [columns]

Replays are in %APPDATA%\NTE Telemetry\replays; one in the map's world, over many of its roads, is best.

Mouse:  left drag - move the map view          wheel - zoom the view
        right drag - move the drive             Ctrl + wheel - scale the drive (about the pointer)
        Shift + wheel - rotate the drive (0.25 deg a notch, Alt for 0.02)
Keys:   arrows - nudge the drive 1 screen px    M - mirror the drive     S - save map.json
        F - view the drive                         A - view the whole map
"""
import gzip
import json
import math
import os
import re
import sys
from collections import OrderedDict

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (QApplication, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
                               QLabel, QMainWindow, QStatusBar)

TILE = 512
MID = 128     # px per tile of the middle copy, cached on disk
PREVIEW = 32  # px per tile of the whole-map preview
CACHE_TILES = 400


def tiles_of(folder):
    files = sorted((f for f in os.listdir(folder) if f.lower().endswith(".png")),
                   key=lambda f: int(re.findall(r"\d+", f)[-1]))
    return [os.path.join(folder, f) for f in files]


def build_cache(files, cols, cache):
    """The whole map at PREVIEW px a tile, and each tile at MID px: decoding the full tiles takes a while,
    so it is done once."""
    os.makedirs(os.path.join(cache, "mid"), exist_ok=True)
    rows = math.ceil(len(files) / cols)
    preview = QImage(cols * PREVIEW, rows * PREVIEW, QImage.Format_ARGB32)
    preview.fill(Qt.black)
    p = QPainter(preview)
    for i, f in enumerate(files):
        img = QImage(f)
        img.scaled(MID, MID, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(os.path.join(cache, "mid", f"{i}.png"))
        p.drawImage(QRectF((i % cols) * PREVIEW, (i // cols) * PREVIEW, PREVIEW, PREVIEW), img)
        if i % 200 == 0:
            print(f"building the map cache: {i}/{len(files)}", flush=True)
    p.end()
    preview.save(os.path.join(cache, "preview.png"))


class MapView(QGraphicsView):
    def __init__(self, folder, drive, cols, status):
        super().__init__()
        self.folder, self.cols, self.status = folder, cols, status
        self.files = tiles_of(folder)
        self.rows = math.ceil(len(self.files) / cols)
        local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        self.cache = os.path.join(local, "NTE Telemetry", "align_cache", os.path.basename(os.path.normpath(folder)))
        if not os.path.exists(os.path.join(self.cache, "preview.png")):
            build_cache(self.files, cols, self.cache)
        self.items = OrderedDict()  # (level, index) -> map tile item, the most recently used last
        self.scene_ = QGraphicsScene(0, 0, cols * TILE, self.rows * TILE)
        self.setScene(self.scene_)
        self.setBackgroundBrush(QColor(0, 0, 0))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        pv = QGraphicsPixmapItem(QPixmap(os.path.join(self.cache, "preview.png")))
        pv.setScale(TILE / PREVIEW)
        pv.setTransformationMode(Qt.SmoothTransformation)
        self.scene_.addItem(pv)

        # the drive, in world metres, as a path; placed on the map by its transform
        self.c = drive.mean(0)  # its centre (world)
        path = QPainterPath()
        for seg in drive_segments(drive):
            path.moveTo(*seg[0])
            for q in seg[1:]:
                path.lineTo(*q)
        self.path = QGraphicsPathItem(path)
        pen = QPen(QColor(255, 50, 50, 230))
        pen.setWidthF(2.5)
        pen.setCosmetic(True)
        self.path.setPen(pen)
        self.path.setZValue(10)
        self.scene_.addItem(self.path)
        self.s, self.theta, self.mirror = 0.4, 0.0, False  # m per map px, deg, flipped
        self.p0 = QPointF(self.scene_.width() / 2, self.scene_.height() / 2)  # where the drive's centre is
        self.load()
        self.place()
        self.moving = None

    # ----- the drive's placement: map px p = p0 + R(theta) F (w - c) / s -----

    def matrix(self):
        th = math.radians(self.theta)
        R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
        F = np.diag([1.0, -1.0 if self.mirror else 1.0])
        return R @ F / self.s

    def place(self):
        M = self.matrix()
        d = np.array([self.p0.x(), self.p0.y()]) - M @ self.c
        self.path.setTransform(QTransform(M[0, 0], M[1, 0], M[0, 1], M[1, 1], d[0], d[1]))
        self.status.setText(f"scale {self.s:.5f} m/px   rotation {self.theta:+.2f} deg   mirror {'on' if self.mirror else 'off'}"
                            f"   |   right drag move, Ctrl+wheel scale, Shift+wheel rotate, M mirror, S save")

    def json_path(self):
        return os.path.join(self.folder, "map.json")

    def save(self):
        A = np.linalg.inv(self.matrix())  # map px -> world
        t = self.c - A @ np.array([self.p0.x(), self.p0.y()])
        try:  # keep what else map.json says (level, title, road_min)
            with open(self.json_path(), encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = {}
        meta.update(grid=[self.cols, self.rows], tile=TILE,
                    pixel_to_world=[[round(A[0, 0], 7), round(A[0, 1], 7), round(t[0], 4)],
                                    [round(A[1, 0], 7), round(A[1, 1], 7), round(t[1], 4)]])
        with open(self.json_path(), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1)
        self.status.setText(f"saved {self.json_path()}")

    def load(self):
        """Carry on from a map.json saved before."""
        try:
            with open(self.json_path(), encoding="utf-8") as f:
                m = json.load(f)["pixel_to_world"]
        except (OSError, ValueError, KeyError):
            return
        A = np.array([[m[0][0], m[0][1]], [m[1][0], m[1][1]]])
        t = np.array([m[0][2], m[1][2]])
        M = np.linalg.inv(A)
        self.s = math.sqrt(abs(np.linalg.det(A)))
        self.mirror = np.linalg.det(A) < 0
        RF = M * self.s
        R = RF @ np.diag([1.0, -1.0 if self.mirror else 1.0])
        self.theta = math.degrees(math.atan2(R[1, 0], R[0, 0]))
        p = M @ (self.c - t)
        self.p0 = QPointF(p[0], p[1])

    # ----- map tiles, at the detail the zoom needs -----

    def refresh_tiles(self):
        scale = self.transform().m11()  # screen px per map px
        level = TILE if scale >= 0.3 else MID if scale >= 1.5 / (TILE / PREVIEW) else None
        r = self.mapToScene(self.viewport().rect()).boundingRect()
        want = set()
        if level:
            c0, c1 = max(int(r.left() // TILE), 0), min(int(r.right() // TILE), self.cols - 1)
            r0, r1 = max(int(r.top() // TILE), 0), min(int(r.bottom() // TILE), self.rows - 1)
            for row in range(r0, r1 + 1):
                for col in range(c0, c1 + 1):
                    i = row * self.cols + col
                    if i < len(self.files):
                        want.add((level, i))
        for key, it in self.items.items():
            it.setVisible(key in want)
        for key in sorted(want):
            if key in self.items:
                self.items.move_to_end(key)
                continue
            lv, i = key
            src = self.files[i] if lv == TILE else os.path.join(self.cache, "mid", f"{i}.png")
            it = QGraphicsPixmapItem(QPixmap(src))
            it.setTransformationMode(Qt.SmoothTransformation)
            it.setScale(TILE / lv)
            it.setPos((i % self.cols) * TILE, (i // self.cols) * TILE)
            it.setZValue(1 if lv == MID else 2)
            self.scene_.addItem(it)
            self.items[key] = it
        while len(self.items) > CACHE_TILES:
            key, it = next(iter(self.items.items()))
            if key in want:
                break
            self.scene_.removeItem(it)
            del self.items[key]

    def fit_map(self):
        self.fitInView(self.scene_.sceneRect(), Qt.KeepAspectRatio)
        self.refresh_tiles()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self.refresh_tiles()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.refresh_tiles()

    def fit(self):
        self.fitInView(self.path.sceneBoundingRect().adjusted(-2000, -2000, 2000, 2000), Qt.KeepAspectRatio)
        self.refresh_tiles()

    # ----- input -----

    def wheelEvent(self, ev):
        notches = (ev.angleDelta().y() or ev.angleDelta().x()) / 120
        at = self.mapToScene(ev.position().toPoint())
        mods = ev.modifiers()
        if mods & Qt.ControlModifier:  # scale the drive about the pointer
            k = 1.02 ** notches
            self.p0 = at + (self.p0 - at) * k
            self.s /= k
            self.place()
        elif mods & Qt.ShiftModifier:  # rotate the drive about the pointer
            da = notches * (0.02 if mods & Qt.AltModifier else 0.25)
            th = math.radians(da)
            d = self.p0 - at
            self.p0 = at + QPointF(d.x() * math.cos(th) - d.y() * math.sin(th),
                                   d.x() * math.sin(th) + d.y() * math.cos(th))
            self.theta += da
            self.place()
        else:
            self.scale(1.25 ** notches, 1.25 ** notches)
            self.refresh_tiles()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.RightButton:
            self.moving = self.mapToScene(ev.position().toPoint())
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self.moving is not None:
            at = self.mapToScene(ev.position().toPoint())
            self.p0 += at - self.moving
            self.moving = at
            self.place()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.RightButton:
            self.moving = None
            return
        super().mouseReleaseEvent(ev)

    def keyPressEvent(self, ev):
        k = ev.key()
        step = 1 / self.transform().m11()  # one screen px, in map px
        moves = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0), Qt.Key_Up: (0, -step), Qt.Key_Down: (0, step)}
        if k in moves:
            self.p0 += QPointF(*moves[k])
            self.place()
        elif k == Qt.Key_M:
            self.mirror = not self.mirror
            self.place()
        elif k == Qt.Key_S:
            self.save()
        elif k == Qt.Key_F:
            self.fit()
        elif k == Qt.Key_A:
            self.fit_map()
        else:
            super().keyPressEvent(ev)


def drive_segments(w, jump=100.0):
    """The drive split where it jumped (the game moving the car), so no line is drawn across the map."""
    cut = np.flatnonzero(np.hypot(*np.diff(w, axis=0).T) > jump) + 1
    return [s for s in np.split(w, cut) if len(s) >= 2]


def main():
    # %APPDATA% (cmd) and $env:APPDATA (PowerShell) both work, whatever shell passes them on unexpanded
    expand = lambda a: os.path.expandvars(a.replace("$env:APPDATA", "%APPDATA%"))
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    folder, replay = expand(sys.argv[1]), expand(sys.argv[2])
    cols = int(sys.argv[3]) if len(sys.argv) > 3 else int(round(math.sqrt(len(tiles_of(folder)))))
    with gzip.open(replay, "rt", encoding="utf-8") as f:
        drive = np.array([(r[1], r[2]) for r in json.load(f)["me"]], float)
    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle(f"Align {os.path.basename(folder)} with {os.path.basename(replay)}")
    status = QLabel()
    bar = QStatusBar()
    bar.addWidget(status, 1)
    win.setStatusBar(bar)
    view = MapView(folder, drive, cols, status)
    win.setCentralWidget(view)
    win.resize(1400, 950)
    win.show()
    view.fit_map()
    view.setFocus()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

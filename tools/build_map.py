"""Make a map pack (.ntemap, see src/ui/world_map.py) from a game map's tiles.

    python tools/build_map.py <source folder> [<out .ntemap>]

The source folder holds the game's tiles (PNG, numbered left to right, top to bottom) and map.json:
  {"level": the game world (UE level path) the server names; the app's status bar shows its last part,
   "title": a name to show (optional),
   "grid": [columns, rows], "tile": tile size in px,
   "pixel_to_world": [[a, b, c], [d, e, f]] (tools/align_map.py places the map and writes this),
   "road_min": grey level from which a pixel counts as road (45 if left out)}
The pack gets the tiles as they are, each half size down to one tile, and the roads mask. Without <out> it goes
to the app's maps folder, %APPDATA%\\NTE Telemetry\\maps, named after the source folder.
"""
import json
import os
import re
import sys
import tempfile
import zipfile

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter

ROADS_PX = 3.0  # m per pixel the roads mask has at most


def png(img):
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def main(src, out=None):
    app = QGuiApplication([])  # noqa: F841 (images need it)
    with open(os.path.join(src, "map.json"), encoding="utf-8") as f:
        meta = json.load(f)
    if not meta.get("level"):
        print("note: map.json has no \"level\": the app can then tell the map only by its roads")
    cols, rows = meta["grid"]
    tile = meta["tile"]
    files = sorted((f for f in os.listdir(src) if f.lower().endswith(".png")),
                   key=lambda f: int(re.findall(r"\d+", f)[-1]))
    (a, b, _), (c, d, _) = meta["pixel_to_world"]
    m_per_px = abs(a * d - b * c) ** 0.5
    if out is None:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        os.makedirs(os.path.join(base, "NTE Telemetry", "maps"), exist_ok=True)
        out = os.path.join(base, "NTE Telemetry", "maps", os.path.basename(os.path.normpath(src)) + ".ntemap")

    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(out + ".tmp", "w", zipfile.ZIP_STORED) as z:
        def tile_path(k, r, col):
            return os.path.join(tmp, str(k), f"{r}_{col}.png")

        def source(k, r, col):
            if k == 0:
                i = r * cols + col
                return QImage(os.path.join(src, files[i])) if col < cols and r < rows and i < len(files) else None
            p = tile_path(k, r, col)
            return QImage(p) if os.path.exists(p) else None

        for r in range(rows):  # level 0: the game's tiles as they are
            for col in range(cols):
                i = r * cols + col
                if i < len(files):
                    z.write(os.path.join(src, files[i]), f"tiles/0/{r}_{col}.png")
        k, c_n, r_n = 0, cols, rows
        while c_n > 1 or r_n > 1:
            k += 1
            c_n, r_n = (c_n + 1) // 2, (r_n + 1) // 2
            os.makedirs(os.path.join(tmp, str(k)))
            for r in range(r_n):
                for col in range(c_n):
                    img = QImage(2 * tile, 2 * tile, QImage.Format_ARGB32_Premultiplied)
                    img.fill(Qt.transparent)
                    p = QPainter(img)
                    for dr in (0, 1):
                        for dc in (0, 1):
                            s = source(k - 1, 2 * r + dr, 2 * col + dc)
                            if s is not None:
                                p.drawImage(dc * tile, dr * tile, s)
                    p.end()
                    small = img.scaled(tile, tile, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    small.save(tile_path(k, r, col))
                    z.write(tile_path(k, r, col), f"tiles/{k}/{r}_{col}.png")
            print(f"level {k}: {c_n} x {r_n} tiles, {m_per_px * 2 ** k:.2f} m/px", flush=True)
        levels = k + 1

        # the roads, from the finest level that is still at most ROADS_PX m a pixel
        rl = 0
        while rl + 1 < levels and m_per_px * 2 ** (rl + 1) <= ROADS_PX:
            rl += 1
        c_n, r_n = -(-cols // 2 ** rl), -(-rows // 2 ** rl)
        whole = QImage(c_n * tile, r_n * tile, QImage.Format_ARGB32)
        whole.fill(Qt.black)
        p = QPainter(whole)
        for r in range(r_n):
            for col in range(c_n):
                s = source(rl, r, col)
                if s is not None:
                    p.drawImage(QRect(col * tile, r * tile, tile, tile), s)
        p.end()
        grey = whole.convertToFormat(QImage.Format_Grayscale8)
        g = np.frombuffer(grey.constBits(), np.uint8).reshape(grey.height(), grey.bytesPerLine())[:, :grey.width()]
        mask = np.ascontiguousarray(np.where(g >= meta.get("road_min", 45), 255, 0).astype(np.uint8))
        z.writestr("roads.png", png(QImage(mask.data, mask.shape[1], mask.shape[0], mask.shape[1],
                                           QImage.Format_Grayscale8)))
        pack = {k: v for k, v in meta.items() if k not in ("levels", "roads_level")}
        pack.update(levels=levels, roads_level=rl)
        z.writestr("map.json", json.dumps(pack, indent=1))
    os.replace(out + ".tmp", out)
    print(f"roads mask: level {rl} ({m_per_px * 2 ** rl:.2f} m/px)")
    print(f"map pack: {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)

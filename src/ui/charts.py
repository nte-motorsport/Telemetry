"""Charts on pyqtgraph: time/distance lines, the speed-coloured trajectory map and the G-G diagram."""
import math

import numpy as np
import pyqtgraph as pg
from pyqtgraph import functions as fn
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem

from ui import theme

pg.setConfigOptions(antialias=True, background=None, foreground=theme.MUTED)

NO_DATA = "no data"
MIN_HEIGHT = 110  # charts stretch to fill the window, but not below this
MAP_POINTS = 1200  # most points per track on the map; a long run is thinned to this
GG_POINTS = 2000   # most dots per run on the G-G diagram


def thin(n, limit):
    """Indices of at most ~limit of n points, evenly spread, always keeping the last one."""
    if n <= limit:
        return slice(None)
    return np.unique(np.r_[np.arange(0, n, math.ceil(n / limit)), n - 1])


_brushes = {}


def brush(color):
    """One shared brush per colour. pyqtgraph caches each dot's image by the brush object, so a fresh
    brush every frame keeps filling and rebuilding that cache."""
    c = QColor(color)
    return _brushes.setdefault(c.rgba(), pg.mkBrush(c))


def peak_thin(xs, ys, x0, x1, columns):
    """The part of a curve inside x0..x1 (plus one point either side), thinned to the lowest and the
    highest value per pixel column, so peaks survive. xs must be increasing."""
    if len(xs) > 2:
        i = max(int(np.searchsorted(xs, x0)) - 1, 0)
        j = min(int(np.searchsorted(xs, x1, "right")) + 1, len(xs))
        xs, ys = xs[i:j], ys[i:j]
    k = len(xs) // max(columns, 1)
    if k < 2:
        return xs, ys
    m = len(xs) // k * k
    yb = ys[:m].reshape(-1, k)
    out_y = np.empty(2 * len(yb))
    out_y[0::2] = np.fmin.reduce(yb, axis=1)  # fmin/fmax skip NaN; an all-NaN bucket stays a gap
    out_y[1::2] = np.fmax.reduce(yb, axis=1)
    return np.r_[np.repeat(xs[:m:k], 2), xs[m:]], np.r_[out_y, ys[m:]]


class FastCurve(pg.PlotCurveItem):
    """A curve drawn as short polylines. Qt strokes one long antialiased path that keeps crossing itself
    (noisy G data, a lap on the map) very slowly; short pieces draw many times faster and look the same."""
    CHUNK = 64

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # kept as an image until the data changes, so repainting around it costs nothing
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)

    def paint(self, p, *args):
        x, y = self.xData, self.yData
        if x is None or len(x) < 2:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, self.opts["antialias"])
        p.setPen(self.opts["pen"])
        if self.opts["connect"] == "pairs":
            n = len(x) // 2 * 2
            for i in range(0, n, 2 * self.CHUNK):
                p.drawLines(fn.arrayToQPolygonF(x[i:min(i + 2 * self.CHUNK, n)], y[i:min(i + 2 * self.CHUNK, n)]))
            return
        # unbroken runs of finite points; a NaN leaves a gap, as connect="finite" does
        idx = np.flatnonzero(np.isfinite(x) & np.isfinite(y))
        if not len(idx):
            return
        cut = np.flatnonzero(np.diff(idx) > 1)
        for a, b in zip(np.r_[idx[0], idx[cut + 1]], np.r_[idx[cut], idx[-1]] + 1):
            for i in range(a, b - 1, self.CHUNK):
                j = min(i + self.CHUNK + 1, b)
                p.drawPolyline(fn.arrayToQPolygonF(x[i:j], y[i:j]))


def nice_step(span, n):
    raw = span / n
    p = 10 ** math.floor(math.log10(raw))
    f = raw / p
    return (1 if f < 1.5 else 2 if f < 3 else 5 if f < 7 else 10) * p


def dist_fmt(v):
    return f"{v / 1000:.1f} km" if abs(v) >= 1000 else f"{v:.0f} m"


def speed_color(v):
    """The accent yellow (slow) to the danger red (fast), 0..250 km/h."""
    t = max(0.0, min(1.0, v / 250))
    a, b = QColor(theme.ACCENT), QColor(theme.DANGER)
    return QColor.fromRgbF(*(x + (y - x) * t for x, y in zip(a.getRgbF()[:3], b.getRgbF()[:3])))


class Axis(pg.AxisItem):
    def __init__(self, orientation, fmt=None):
        super().__init__(orientation)
        self.fmt = fmt
        self.setPen(pg.mkPen(theme.GRID))
        self.setTextPen(pg.mkPen(theme.MUTED))
        self.setStyle(tickFont=theme.font(11), tickTextOffset=6)
        # the axis also draws the grid, which is slow; keep it as an image until the range changes
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)

    def tickStrings(self, values, scale, spacing):
        if self.fmt:
            return [self.fmt(v) for v in values]
        return super().tickStrings(values, scale, spacing)


class BaseChart(pg.PlotWidget):
    def __init__(self, axes=True, xfmt=None, **kw):
        items = {"bottom": Axis("bottom", xfmt), "left": Axis("left")} if axes else {}
        super().__init__(axisItems=items, **kw)
        self.setBackground(None)
        self.setStyleSheet("background: transparent; border: none;")
        pi = self.getPlotItem()
        pi.setMenuEnabled(False)
        pi.hideButtons()
        pi.setMouseEnabled(False, False)
        pi.vb.setMouseEnabled(False, False)
        if axes:
            pi.showGrid(True, True, alpha=0.6)
        else:
            pi.hideAxis("left")
            pi.hideAxis("bottom")
        self.empty = pg.TextItem(NO_DATA, color=theme.MUTED, anchor=(0.5, 0.5))
        self.empty.setFont(theme.font(12))
        self.addItem(self.empty, ignoreBounds=True)

    def wheelEvent(self, ev):  # let the page scroll instead of zooming
        ev.ignore()

    def show_empty(self, on):
        self.empty.setVisible(bool(on))
        if on:
            (x0, x1), (y0, y1) = self.viewRange()
            self.empty.setPos((x0 + x1) / 2, (y0 + y1) / 2)


class LineChart(BaseChart):
    """Several series against a shared x; optional zero-including or symmetric y range."""

    def __init__(self, xfmt=None, zero=False, sym=None):
        super().__init__(xfmt=xfmt)
        self.zero, self.sym = zero, sym
        self.setMinimumHeight(MIN_HEIGHT)
        self.items = []
        self.last = None  # the last set_series() arguments, to thin again for a new width
        self.zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(theme.MUTED, width=1))
        self.zero_line.setOpacity(0.5)
        self.addItem(self.zero_line, ignoreBounds=True)

    def set_series(self, series, xrange=None):
        """series: [(xs, ys, color, width)]"""
        self.last = (series, xrange)
        while len(self.items) < len(series):
            it = FastCurve(connect="finite")
            self.addItem(it)
            self.items.append(it)
        while len(self.items) > len(series):
            self.removeItem(self.items.pop())
        lo, hi, xlo, xhi = math.inf, -math.inf, math.inf, -math.inf
        for xs, _, _, _ in series:
            if len(xs):
                xlo, xhi = min(xlo, xs[0]), max(xhi, xs[-1])
        x0, x1 = xrange if xrange else ((xlo, xhi) if math.isfinite(xlo) and xhi > xlo else (0, 1))
        columns = int(self.getPlotItem().vb.width()) or self.width()
        for it, (xs, ys, color, width) in zip(self.items, series):
            xs, ys = peak_thin(np.asarray(xs, float), np.asarray(ys, float), x0, x1, columns)
            it.setData(xs, ys, pen=pg.mkPen(color, width=width))
            fin = ys[np.isfinite(ys)]
            if len(fin):
                lo, hi = min(lo, fin.min()), max(hi, fin.max())
        empty = not math.isfinite(lo)
        if empty:
            lo, hi = -1.0, 1.0
        if self.zero:
            lo, hi = min(lo, 0.0), max(hi, 0.0)
        if self.sym is not None:
            m = max(abs(lo), abs(hi), self.sym)
            lo, hi = -m, m
        if hi - lo < 1e-6:
            lo, hi = lo - 1, hi + 1
        # round out to whole grid steps: the range (and the cached axis) then holds still while the
        # values move inside it, instead of changing with every new sample
        step = nice_step(hi - lo, 4)
        lo, hi = math.floor(lo / step + 1e-9) * step, math.ceil(hi / step - 1e-9) * step
        pad = (hi - lo) * 0.06
        self.setRange(xRange=(x0, x1), yRange=(lo - pad, hi + pad), padding=0)
        self.zero_line.setVisible(bool(lo < 0 < hi))
        self.show_empty(empty)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # Qt also resizes the view while it is being built and torn down, when there is nothing to redraw
        if getattr(self, "last", None) and self.getPlotItem() is not None:
            self.set_series(*self.last)


class MapChart(BaseChart):
    """Top-down trajectory: game +X up, +Y right. Tracks are coloured by run or by speed."""
    BINS = 24

    def __init__(self):
        super().__init__(axes=False)
        self.setMinimumHeight(MIN_HEIGHT)
        self.setAspectLocked(True)
        self.layers = []
        self.markers = pg.ScatterPlotItem(size=12, pen=pg.mkPen(theme.BG, width=2))
        self.starts = pg.ScatterPlotItem(size=7, pen=None, brush=brush(theme.TEXT))
        self.bar = pg.PlotDataItem(pen=pg.mkPen(theme.MUTED, width=2))
        self.bar_text = pg.TextItem(color=theme.MUTED, anchor=(0, 1))
        self.bar_text.setFont(theme.font(11))
        for it in (self.starts, self.markers, self.bar):
            self.addItem(it)
        self.addItem(self.bar_text, ignoreBounds=True)

    def _layer(self, i):
        while len(self.layers) <= i:
            it = FastCurve(connect="pairs")
            self.addItem(it)
            self.layers.append(it)
        return self.layers[i]

    def set_tracks(self, tracks, markers=()):
        """tracks: [dict(x, y, color=None | speeds=array, width)]; markers: [(x, y, color)]"""
        used = 0
        allx, ally, starts = [], [], []
        for tr in tracks:
            x, y = np.asarray(tr["x"], float), np.asarray(tr["y"], float)
            if len(x) < 2:
                continue
            keep = thin(len(x), MAP_POINTS)
            x, y = x[keep], y[keep]
            allx.append(x)
            ally.append(y)
            starts.append((y[0], x[0]))
            if tr.get("speeds") is not None:
                v = np.asarray(tr["speeds"], float)[keep][1:]
                b = np.clip((v / 250 * self.BINS).astype(int), 0, self.BINS - 1)
                for k in np.unique(b):
                    idx = np.nonzero(b == k)[0]
                    sx = np.empty(len(idx) * 2)
                    sy = np.empty(len(idx) * 2)
                    sx[0::2], sx[1::2] = y[idx], y[idx + 1]
                    sy[0::2], sy[1::2] = x[idx], x[idx + 1]
                    pen = pg.mkPen(speed_color((k + 0.5) * 250 / self.BINS), width=tr.get("width", 3))
                    pen.setCapStyle(Qt.RoundCap)
                    self._layer(used).setData(sx, sy, pen=pen)
                    used += 1
            else:
                sx = np.repeat(y, 2)[1:-1]
                sy = np.repeat(x, 2)[1:-1]
                pen = pg.mkPen(tr["color"], width=tr.get("width", 3))
                pen.setCapStyle(Qt.RoundCap)
                self._layer(used).setData(sx, sy, pen=pen)
                used += 1
        for it in self.layers[used:]:
            it.setData([], [])
        self.starts.setData([s[0] for s in starts], [s[1] for s in starts])
        self.set_markers(markers)
        if not allx:
            self.bar.setData([], [])
            self.bar_text.setText("")
            self.setRange(xRange=(-1, 1), yRange=(-1, 1), padding=0)
            self.show_empty(True)
            return
        self.show_empty(False)
        X, Y = np.concatenate(allx), np.concatenate(ally)
        span = max(X.max() - X.min(), Y.max() - Y.min(), 20)
        cx, cy = (Y.max() + Y.min()) / 2, (X.max() + X.min()) / 2
        h = span / 2 * 1.08
        self.setRange(xRange=(cx - h, cx + h), yRange=(cy - h, cy + h), padding=0)
        (x0, x1), (y0, y1) = self.viewRange()
        size = nice_step(span, 4)
        bx, by = x0 + (x1 - x0) * 0.03, y0 + (y1 - y0) * 0.04
        self.bar.setData([bx, bx + size], [by, by])
        self.bar_text.setText(dist_fmt(size))
        self.bar_text.setPos(bx, by + (y1 - y0) * 0.01)

    def set_markers(self, markers):
        """markers: [(x, y, color)], e.g. where each run is at the hover point."""
        self.markers.setData([m[1] for m in markers], [m[0] for m in markers],
                             brush=[brush(m[2]) for m in markers])


class GGChart(BaseChart):
    """As in sim overlays: acceleration up, braking down, and the dot moves to the outside of the
    turn (left in a right-hand turn), i.e. the force the driver feels."""

    def __init__(self):
        super().__init__(axes=False)
        self.setMinimumHeight(MIN_HEIGHT)
        self.setAspectLocked(True)
        self.deco = []
        self.scatters = []
        self.mx = None

    def _frame(self, mx):
        if mx == self.mx:
            return
        self.mx = mx
        for it in self.deco:
            self.removeItem(it)
        self.deco = []
        pen = QPen(QColor(theme.GRID))
        pen.setWidthF(1)
        pen.setCosmetic(True)
        step = 0.5 if mx <= 2 else 1.0
        k = step
        while k <= mx + 1e-9:
            e = QGraphicsEllipseItem(QRectF(-k, -k, 2 * k, 2 * k))
            e.setPen(pen)
            self.addItem(e)
            self.deco.append(e)
            t = pg.TextItem(f"{k:g}g", color=theme.MUTED, anchor=(0, 1))
            t.setFont(theme.font(11))
            t.setPos(k * 0.707, k * 0.707)
            self.addItem(t)
            self.deco.append(t)
            k += step
        for xs, ys in (([-mx, mx], [0, 0]), ([0, 0], [-mx, mx])):
            ln = pg.PlotDataItem(xs, ys, pen=pg.mkPen(theme.GRID, width=1))
            self.addItem(ln)
            self.deco.append(ln)
        for text, pos, anchor in (("accel", (0, mx), (0.5, 1)), ("braking", (0, -mx), (0.5, 0)),
                                  ("left", (-mx, 0), (0, 1)), ("right", (mx, 0), (1, 1))):
            t = pg.TextItem(text, color=theme.MUTED, anchor=anchor)
            t.setFont(theme.font(11))
            t.setPos(*pos)
            self.addItem(t)
            self.deco.append(t)
        m = mx * 1.25  # room for the accel / braking / left / right labels
        self.setRange(xRange=(-m, m), yRange=(-m, m), padding=0)

    def set_sets(self, sets):
        """sets: [dict(ga, gl, color, fade=False)]; lateral is mirrored so the dot shows the felt force."""
        # scale to the 99th percentile, not the max: a single position glitch reads as 5-8 g
        mags = [np.abs(np.asarray(s[k], float)) for s in sets for k in ("ga", "gl") if len(s[k])]
        mx = min(max(1.0, float(np.percentile(np.concatenate(mags), 99))), 4.0) if mags else 1.0
        self._frame(math.ceil(mx * 2) / 2)
        while len(self.scatters) < len(sets):
            sc = pg.ScatterPlotItem(pen=None)
            self.addItem(sc)
            self.scatters.append(sc)
        for sc in self.scatters[len(sets):]:
            sc.setData([], [])
        for sc, s in zip(self.scatters, sets):
            ga, gl = np.asarray(s["ga"], float), np.asarray(s["gl"], float)
            keep = thin(len(ga), GG_POINTS)
            ga, gl = ga[keep], gl[keep]
            n = len(ga)
            c = QColor(s["color"])
            if s.get("fade") and n:
                brushes, sizes = [], []
                for i in range(n):
                    cc = QColor(c)
                    # a few fixed steps, so pyqtgraph draws each dot style once and reuses it
                    cc.setAlphaF(round(0.15 + 0.85 * (i + 1) / n, 1))
                    brushes.append(brush(cc))
                    sizes.append(12 if i == n - 1 else 5)
                sc.setData(-ga, gl, brush=brushes, size=sizes)
            else:
                c.setAlphaF(0.55)
                sc.setData(-ga, gl, brush=brush(c), size=4)
        self.show_empty(not any(len(s["ga"]) for s in sets))
        self.empty.setPos(0, self.mx * 0.35)

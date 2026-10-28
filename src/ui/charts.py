"""Charts on pyqtgraph: time/distance lines, the speed-coloured trajectory map and the G-G diagram."""
import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem

from ui import theme

pg.setConfigOptions(antialias=True, background=None, foreground=theme.MUTED)

NO_DATA = "no data"


def nice_step(span, n):
    raw = span / n
    p = 10 ** math.floor(math.log10(raw))
    f = raw / p
    return (1 if f < 1.5 else 2 if f < 3 else 5 if f < 7 else 10) * p


def dist_fmt(v):
    return f"{v / 1000:.1f} km" if abs(v) >= 1000 else f"{v:.0f} m"


def speed_color(v):
    """Blue (slow) to red (fast), 0..250 km/h."""
    t = max(0.0, min(1.0, v / 250))
    return QColor.fromHslF((220 - 220 * t) / 360, 0.85, 0.58)


class Axis(pg.AxisItem):
    def __init__(self, orientation, fmt=None):
        super().__init__(orientation)
        self.fmt = fmt
        self.setPen(pg.mkPen(theme.GRID))
        self.setTextPen(pg.mkPen(theme.MUTED))
        self.setStyle(tickFont=theme.font(11), tickTextOffset=6)

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
    """Several series against a shared x; optional zero-including or symmetric y range and a hover cursor."""
    hovered = Signal(object)  # x under the mouse, or None

    def __init__(self, xfmt=None, zero=False, sym=None, height=240):
        super().__init__(xfmt=xfmt)
        self.zero, self.sym = zero, sym
        self.setFixedHeight(height)
        self.items = []
        self.cursor = pg.InfiniteLine(angle=90, pen=pg.mkPen(theme.TEXT, width=1, style=Qt.DashLine))
        self.cursor.setOpacity(0.5)
        self.cursor.hide()
        self.addItem(self.cursor, ignoreBounds=True)
        self.zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(theme.MUTED, width=1))
        self.zero_line.setOpacity(0.5)
        self.addItem(self.zero_line, ignoreBounds=True)
        self.scene().sigMouseMoved.connect(self._moved)

    def set_series(self, series, xrange=None):
        """series: [(xs, ys, color, width)]"""
        while len(self.items) < len(series):
            it = pg.PlotDataItem(connect="finite")
            self.addItem(it)
            self.items.append(it)
        while len(self.items) > len(series):
            self.removeItem(self.items.pop())
        lo, hi, xlo, xhi = math.inf, -math.inf, math.inf, -math.inf
        for it, (xs, ys, color, width) in zip(self.items, series):
            xs, ys = np.asarray(xs, float), np.asarray(ys, float)
            it.setData(xs, ys, pen=pg.mkPen(color, width=width))
            fin = ys[np.isfinite(ys)]
            if len(fin):
                lo, hi = min(lo, fin.min()), max(hi, fin.max())
            if len(xs):
                xlo, xhi = min(xlo, xs[0]), max(xhi, xs[-1])
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
        pad = (hi - lo) * 0.06
        x0, x1 = xrange if xrange else ((xlo, xhi) if math.isfinite(xlo) and xhi > xlo else (0, 1))
        self.setRange(xRange=(x0, x1), yRange=(lo - pad, hi + pad), padding=0)
        self.zero_line.setVisible(bool(lo < 0 < hi))
        self.show_empty(empty)

    def set_cursor(self, x):
        self.cursor.setVisible(x is not None)
        if x is not None:
            self.cursor.setPos(x)

    def _moved(self, pos):
        vb = self.getPlotItem().vb
        if vb.sceneBoundingRect().contains(pos):
            self.hovered.emit(vb.mapSceneToView(pos).x())
        else:
            self.hovered.emit(None)

    def leaveEvent(self, ev):
        self.hovered.emit(None)
        super().leaveEvent(ev)


class MapChart(BaseChart):
    """Top-down trajectory: game +X up, +Y right. Tracks are coloured by run or by speed."""
    BINS = 24

    def __init__(self, height=360):
        super().__init__(axes=False)
        self.setFixedHeight(height)
        self.setAspectLocked(True)
        self.layers = []
        self.markers = pg.ScatterPlotItem(size=12, pen=pg.mkPen(theme.BG, width=2))
        self.starts = pg.ScatterPlotItem(size=7, pen=None, brush=pg.mkBrush(theme.TEXT))
        self.bar = pg.PlotDataItem(pen=pg.mkPen(theme.MUTED, width=2))
        self.bar_text = pg.TextItem(color=theme.MUTED, anchor=(0, 1))
        self.bar_text.setFont(theme.font(11))
        for it in (self.starts, self.markers, self.bar):
            self.addItem(it)
        self.addItem(self.bar_text, ignoreBounds=True)

    def _layer(self, i):
        while len(self.layers) <= i:
            it = pg.PlotDataItem(connect="pairs")
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
            allx.append(x)
            ally.append(y)
            starts.append((y[0], x[0]))
            if tr.get("speeds") is not None:
                v = np.asarray(tr["speeds"], float)[1:]
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
        self.markers.setData([m[1] for m in markers], [m[0] for m in markers],
                             brush=[pg.mkBrush(m[2]) for m in markers])
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


class GGChart(BaseChart):
    """As in sim overlays: acceleration up, braking down, and the dot moves to the outside of the
    turn (left in a right-hand turn), i.e. the force the driver feels."""

    def __init__(self, height=360):
        super().__init__(axes=False)
        self.setFixedHeight(height)
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
        m = mx * 1.12
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
            n = len(ga)
            c = QColor(s["color"])
            if s.get("fade") and n:
                brushes, sizes = [], []
                for i in range(n):
                    cc = QColor(c)
                    cc.setAlphaF(0.15 + 0.85 * (i + 1) / n)
                    brushes.append(pg.mkBrush(cc))
                    sizes.append(12 if i == n - 1 else 5)
                sc.setData(-ga, gl, brush=brushes, size=sizes)
            else:
                c.setAlphaF(0.55)
                sc.setData(-ga, gl, brush=pg.mkBrush(c), size=4)
        self.show_empty(not any(len(s["ga"]) for s in sets))
        self.empty.setPos(0, self.mx * 0.35)

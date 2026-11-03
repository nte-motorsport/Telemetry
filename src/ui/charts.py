"""Charts on pyqtgraph: time/distance lines, the speed-coloured trajectory map and the G-G diagram."""
import math

import numpy as np
import pyqtgraph as pg
from pyqtgraph import functions as fn
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem

from ui import theme
from ui.world_map import MapImage

pg.setConfigOptions(antialias=True, background=None, foreground=theme.MUTED)

NO_DATA = "NO DATA"
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
    (noisy G data, a lap on the map) very slowly; short pieces draw many times faster and look the same.
    Not cached as an image: the live curves change with every frame, so a cache would only be redrawn."""
    CHUNK = 64

    def paint(self, p, *_):
        x, y = self.xData, self.yData
        if x is None or len(x) < 2:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, self.opts["antialias"])
        p.setPen(self.opts["pen"])
        # unbroken runs of finite points; a NaN leaves a gap, as connect="finite" does
        idx = np.flatnonzero(np.isfinite(x) & np.isfinite(y))
        if not len(idx):
            return
        cut = np.flatnonzero(np.diff(idx) > 1)
        for a, b in zip(np.r_[idx[0], idx[cut + 1]], np.r_[idx[cut], idx[-1]] + 1):
            for i in range(a, b - 1, self.CHUNK):
                j = min(i + self.CHUNK + 1, b)
                p.drawPolyline(fn.arrayToQPolygonF(x[i:j], y[i:j]))


_pens = {}


def pen(color, width, cap):
    """One shared pen per style: the map asks for the same few dozen every frame."""
    c = QColor(color)
    key = (c.rgba(), width, cap)
    p = _pens.get(key)
    if p is None:
        p = _pens[key] = pg.mkPen(c, width=width)
        p.setCapStyle(cap)
        p.setJoinStyle(Qt.RoundJoin)
    return p


class Tracks(pg.GraphicsObject):
    """The map's tracks as short polylines in many pens, all drawn by one item. A track comes in up to BINS
    pens (speed colours): one pyqtgraph item per pen costs more in bookkeeping each frame than the drawing
    itself, and drawing each segment on its own (with its own two round caps) costs several times what a
    polyline through the same points does."""
    CHUNK = 64  # segments per polyline at most, as FastCurve's short pieces

    def __init__(self):
        super().__init__()
        self.lines = []  # [(pen, QPolygonF)], drawn in this order
        self.rect = QRectF()  # of the data
        self.pad = 0.0  # px: half the widest pen
        self.bounds = None

    def set_lines(self, lines, rect, pad):
        self.prepareGeometryChange()
        self.lines, self.rect, self.pad, self.bounds = lines, rect, pad, None
        self.update()

    def viewTransformChanged(self):
        # the pens' widths are in pixels, so the bounds in data units change with the zoom
        super().viewTransformChanged()
        self.prepareGeometryChange()
        self.bounds = None

    def boundingRect(self):
        if self.bounds is None:
            if not self.lines:
                self.bounds = QRectF()
            else:
                vx, vy = self.pixelVectors()
                px = math.hypot(vx.x(), vx.y()) * self.pad if vx is not None else 0.0
                py = math.hypot(vy.x(), vy.y()) * self.pad if vy is not None else 0.0
                self.bounds = self.rect.adjusted(-px, -py, px, py)
        return self.bounds

    def paint(self, p, *_):
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for pn, poly in self.lines:
            p.setPen(pn)
            p.drawPolyline(poly)


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

    def generateDrawSpecs(self, p):
        specs = super().generateDrawSpecs(p)
        if specs is None:
            return None
        (_, p1, p2), *rest = specs
        # no line of its own: the chart's frame draws all four sides alike (the axis' line runs a pixel past
        # the plot area and doubles up with the frame)
        return ((QPen(Qt.NoPen), p1, p2), *rest)

    def tickStrings(self, values, scale, spacing):
        if self.fmt:
            return [self.fmt(v) for v in values]
        return super().tickStrings(values, scale, spacing)


class ScaleAxis(Axis):
    """Under a map, in place of an x axis: a scale bar and its length, in the axis' font and colour."""

    def __init__(self):
        super().__init__("bottom")
        self.setHeight(24)  # as tall as the line charts' time axis
        self.active = False

    def paint(self, p, *_):
        vb = self.linkedView()
        if not self.active or vb is None:
            return
        (x0, x1), _ = vb.viewRange()
        w = self.geometry().width()
        if x1 <= x0 or w <= 0:
            return
        size = nice_step((x1 - x0) * 0.8, 4)
        length = size / (x1 - x0) * w
        r = self.boundingRect()
        y = r.top() + 12
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(pg.mkPen(theme.MUTED, width=1))
        p.drawLine(QPointF(0, y), QPointF(length, y))
        for x in (0, length):  # end ticks, as on a ruler
            p.drawLine(QPointF(x, y - 4), QPointF(x, y + 4))
        p.setFont(self.style["tickFont"])
        p.drawText(QRectF(length + 8, r.top(), 200, r.height()), Qt.AlignLeft | Qt.AlignVCenter, dist_fmt(size))


class BaseChart(pg.PlotWidget):
    def __init__(self, axes=True, xfmt=None, frame=True, **kw):
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
        self.axes_below()
        if frame:  # all four sides of the plot area, the same as the axes' lines along two of them
            pi.vb.setBorder(pg.mkPen(theme.GRID, width=1))
        self.empty = pg.TextItem(NO_DATA, color=theme.MUTED, anchor=(0.5, 0.5))
        self.empty.setFont(theme.font(25))
        self.empty.setOpacity(0.2)
        self.addItem(self.empty, ignoreBounds=True)
        pi.vb.sigRangeChanged.connect(lambda *_: self.center_empty())

    def axes_below(self):
        """The axes draw the grid, and pyqtgraph puts them above the plot area; below it the grid lies under
        the lines. Their tick labels are outside the plot area, so nothing covers them."""
        for name in ("left", "bottom", "right", "top"):
            self.getPlotItem().getAxis(name).setZValue(-200)

    def wheelEvent(self, ev):  # let the page scroll instead of zooming
        ev.ignore()

    def show_empty(self, on):
        self.empty.setVisible(bool(on))
        self.center_empty()

    def center_empty(self):
        if self.empty.isVisible():
            (x0, x1), (y0, y1) = self.viewRange()
            self.empty.setPos((x0 + x1) / 2, (y0 + y1) / 2)


class LineChart(BaseChart):
    """Several series against a shared x; optional zero-including or symmetric y range.

    xzoom: the shortest x span the chart zooms to, None for a fixed x range. With it the wheel moves along x,
    Alt + wheel zooms x (about the pointer) and dragging moves along x too, all within the x range given to
    set_series; y fits what is shown. A view zoomed or moved so stays as it is until reset_view() or a double
    click.

    clicked(x) comes from a click on the plot that doesn't move the pointer (a drag moves the view).

    hover: a format for y values; with it, where the pointer is over the plot a faint line marks the x (and
    tells it, in xfmt), and every series has a dot and a tip with its value there."""
    clicked = Signal(float)
    CLICK_SLOP = 4  # px the pointer may move between press and release for it to be a click, not a drag
    HOVER_GAP = 2.0  # x: a series with samples further apart than this around the pointer has none there
    PAN_STEP = 0.1  # share of the shown span one wheel notch moves it by
    ZOOM_STEP = 0.75  # what one wheel notch with Alt scales the shown span by

    def __init__(self, xfmt=None, zero=False, sym=None, xzoom=None, hover=None):
        super().__init__(xfmt=xfmt)
        self.xfmt = xfmt or (lambda v: f"{v:g}")
        self.zero, self.sym = zero, sym
        self.xzoom = xzoom
        self.user_x = None  # the x range zoomed or moved to by hand
        self.limits = None  # the x limits last set on the view box
        self.setMinimumHeight(MIN_HEIGHT)
        self.items = []
        self.last = None  # the last set_series() arguments, to thin again for a new width
        self.zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(theme.MUTED, width=1))
        self.zero_line.setOpacity(0.5)
        self.addItem(self.zero_line, ignoreBounds=True)
        if xzoom:
            self.getPlotItem().setMouseEnabled(True, False)
            self.getPlotItem().vb.sigRangeChangedManually.connect(self.moved_by_hand)
        self.hover = hover
        self.hover_at = None  # scene position of the pointer, None when it is away
        if hover:
            self.hover_line = pg.InfiniteLine(angle=90, pen=pg.mkPen(theme.TEXT, width=1))
            self.hover_line.setOpacity(0.35)
            self.hover_dots = pg.ScatterPlotItem(size=8, pen=pg.mkPen(theme.BG, width=1.5))
            self.hover_time = self.tip(theme.GRID)
            self.hover_tips = []  # one per series, made as needed
            for z, it in enumerate((self.hover_line, self.hover_dots, self.hover_time), 20):
                it.setZValue(z)
                self.addItem(it, ignoreBounds=True)
            self.scene().sigMouseMoved.connect(self.on_hover)
            self.getPlotItem().vb.sigRangeChanged.connect(lambda *_: self.update_hover())
            self.update_hover()

    def tip(self, border):
        """A small label in a box, which keeps its size in pixels however the view is zoomed."""
        t = pg.TextItem(color=theme.TEXT, fill=pg.mkBrush(QColor(10, 11, 13, 230)), border=pg.mkPen(border, width=1.5))
        t.setFont(theme.font(11))
        t.textItem.document().setDocumentMargin(3)
        return t

    def on_hover(self, pos):
        self.hover_at = pos
        self.update_hover()

    def leaveEvent(self, ev):
        self.hover_at = None
        if self.hover:
            self.update_hover()
        super().leaveEvent(ev)

    def update_hover(self):
        """The line, the dots and the tips for where the pointer is now (the data or the view may have moved
        under it)."""
        if not self.hover:
            return
        vb = self.getPlotItem().vb
        area = vb.sceneBoundingRect()
        points = []  # (y, colour) of each series at the pointer's x
        if self.hover_at is not None and self.last and area.contains(self.hover_at):
            x = vb.mapSceneToView(self.hover_at).x()
            for xs, ys, color, _ in self.last[0]:
                xs, ys = np.asarray(xs, float), np.asarray(ys, float)
                if len(xs) < 2 or not xs[0] <= x <= xs[-1]:
                    continue
                i = min(max(int(np.searchsorted(xs, x)), 1), len(xs) - 1)  # xs[i - 1] <= x <= xs[i]
                dx = xs[i] - xs[i - 1]
                if dx > self.HOVER_GAP:
                    continue
                y = ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / dx if dx > 0 else ys[i]
                if np.isfinite(y):
                    points.append((float(y), color))
        while len(self.hover_tips) < len(points):
            t = self.tip(theme.TEXT)
            t.setZValue(23)
            self.addItem(t, ignoreBounds=True)
            self.hover_tips.append(t)
        for t in self.hover_tips[len(points):]:
            t.hide()
        shown = bool(points)
        for it in (self.hover_line, self.hover_dots, self.hover_time):
            it.setVisible(shown)
        if not shown:
            return
        self.hover_line.setPos(x)
        self.hover_dots.setData([x] * len(points), [y for y, _ in points], brush=[brush(c) for _, c in points])
        (_, _), (_, y1) = self.viewRange()
        self.hover_time.setText(self.xfmt(x))
        self.hover_time.setAnchor((0.5, 0))
        self.hover_time.setPos(x, y1)
        # tips beside the line at their values, pushed apart so they don't cover each other and kept inside
        # the plot; on the left of the line near the right edge
        sx = vb.mapViewToScene(QPointF(x, 0)).x()
        for (y, _), t in zip(points, self.hover_tips):
            t.setText(self.hover(y))  # first: the sizes below are of the text
        order = sorted(range(len(points)), key=lambda k: -points[k][0])  # top first
        h = self.hover_tips[0].boundingRect().height() + 2
        top = area.top() + h * 1.5  # below the time
        ys = [vb.mapViewToScene(QPointF(x, points[k][0])).y() for k in order]
        for j in range(len(ys)):
            ys[j] = max(ys[j], top if j == 0 else ys[j - 1] + h)
        ys[-1] = min(ys[-1], area.bottom() - h / 2)
        for j in range(len(ys) - 2, -1, -1):
            ys[j] = min(ys[j], ys[j + 1] - h)
        width = max((t.boundingRect().width() for t in self.hover_tips[:len(points)]), default=0)
        left = sx + 10 + width > area.right()
        for j, k in enumerate(order):
            y, color = points[k]
            t = self.hover_tips[k]
            t.border = pg.mkPen(color, width=1.5)
            t.setAnchor((1, 0.5) if left else (0, 0.5))
            p = vb.mapSceneToView(QPointF(sx - 10 if left else sx + 10, ys[j]))
            t.setPos(p.x(), p.y())
            t.show()
            t.update()

    def moved_by_hand(self, *_):
        self.user_x = tuple(self.viewRange()[0])
        if self.last:
            self.set_series(*self.last)  # thinned again for what is shown, and y fitted to it

    def reset_view(self):
        """Show the whole x range again."""
        self.user_x = None
        if self.last:
            self.set_series(*self.last)

    def wheelEvent(self, ev):
        if not self.xzoom:
            super().wheelEvent(ev)
            return
        ev.accept()
        # Alt turns the wheel sideways on some systems, so either direction counts
        notches = (ev.angleDelta().y() or ev.angleDelta().x()) / 120
        if not notches or not self.last:
            return
        x0, x1 = self.viewRange()[0]
        if ev.modifiers() & Qt.AltModifier:
            at = self.getPlotItem().vb.mapSceneToView(self.mapToScene(ev.position().toPoint())).x()
            span = x1 - x0
            # up zooms in; the span is held within the limits here, about the pointer, rather than by
            # set_series, which would keep the left end and so move the view at every notch past a limit
            new = min(max(span * self.ZOOM_STEP ** notches, self.limits[2]), self.limits[3])
            if abs(new - span) <= 1e-9 * span:  # already at the limit
                return
            k = new / span
            self.user_x = (at - (at - x0) * k, at + (x1 - at) * k)
        else:
            d = -notches * self.PAN_STEP * (x1 - x0)  # down moves on, to later
            self.user_x = (x0 + d, x1 + d)
        self.set_series(*self.last)  # keeps it inside the range, at least xzoom long

    def mouseDoubleClickEvent(self, ev):
        if self.xzoom:
            self.reset_view()
        super().mouseDoubleClickEvent(ev)

    def mousePressEvent(self, ev):
        self.dragging = True  # follow() leaves the view to the hand that moves it
        self.pressed_at = ev.position() if ev.button() == Qt.LeftButton else None
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        self.dragging = False
        at, self.pressed_at = getattr(self, "pressed_at", None), None
        super().mouseReleaseEvent(ev)
        if at is not None and ev.button() == Qt.LeftButton and (ev.position() - at).manhattanLength() <= self.CLICK_SLOP:
            vb = self.getPlotItem().vb
            scene = self.mapToScene(ev.position().toPoint())
            if vb.sceneBoundingRect().contains(scene):
                self.clicked.emit(vb.mapSceneToView(scene).x())

    FOLLOW = 0.9  # share of the shown span the followed x is kept within

    def follow(self, x):
        """Keep x (a replay's position, as it plays) in a zoomed view: once it gets FOLLOW of the way across,
        the view scrolls along with it; if it is out of view (started over, say), the view jumps to it."""
        if not self.xzoom or not self.user_x or not self.last or getattr(self, "dragging", False):
            return
        x0, x1 = self.viewRange()[0]
        span = x1 - x0
        if x0 <= x <= x0 + self.FOLLOW * span:
            return
        a = x - self.FOLLOW * span if x > x0 else x - (1 - self.FOLLOW) * span
        self.user_x = (a, a + span)
        self.set_series(*self.last)  # keeps it inside the range

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
        if self.xzoom:
            # the view box keeps a view zoomed or moved by hand inside the whole range
            limits = (x0, x1, min(self.xzoom, x1 - x0), x1 - x0)
            if limits != self.limits:
                self.limits = limits
                self.getPlotItem().vb.setLimits(xMin=x0, xMax=x1, minXRange=limits[2], maxXRange=limits[3])
            if self.user_x:
                span = min(max(self.user_x[1] - self.user_x[0], limits[2]), x1 - x0)
                a = min(max(self.user_x[0], x0), x1 - span)
                x0, x1 = a, a + span
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
        if self.hover:
            self.update_hover()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # Qt also resizes the view while it is being built and torn down, when there is nothing to redraw
        if getattr(self, "last", None) and self.getPlotItem() is not None:
            self.set_series(*self.last)


class MapChart(BaseChart):
    """Top-down trajectory: game +X up, +Y right. Tracks are coloured by run or by speed.

    interactive: the wheel zooms (about the pointer) and dragging moves the view; once the view is moved so,
    it stays as it is instead of being fitted to the tracks, until reset_view() or a double click."""
    BINS = 24   # speed colours
    ZOOM = (10.0, 50_000.0)  # m: the view zoomed by hand shows at least / at most this much across

    def __init__(self, interactive=False):
        super().__init__(axes=False)
        self.interactive = interactive
        self.fit = None  # (x range, y range) that shows every track, see set_tracks
        self.user_view = False  # the view was zoomed or moved by hand
        self.setMinimumHeight(MIN_HEIGHT)
        self.setAspectLocked(True)
        pi = self.getPlotItem()
        self.scale = ScaleAxis()
        pi.setAxisItems({"bottom": self.scale})
        pi.showAxis("bottom")
        self.axes_below()
        self.tracks = Tracks()
        self.addItem(self.tracks)
        self.markers = pg.ScatterPlotItem(size=12, pen=pg.mkPen(theme.BG, width=2))
        self.addItem(self.markers)
        self.markers.setZValue(10)  # above the tracks
        self.backdrop = None  # the game map under the tracks, see set_backdrop
        if interactive:
            pi.setMouseEnabled(True, True)
            lo, hi = self.ZOOM
            pi.vb.setLimits(minXRange=lo, maxXRange=hi, minYRange=lo, maxYRange=hi)
            pi.vb.sigRangeChangedManually.connect(self.moved_by_hand)

    def moved_by_hand(self, *_):
        self.user_view = True

    def set_backdrop(self, world_map):
        """Show a world_map.WorldMap under the tracks, or none (None)."""
        if (self.backdrop.map if self.backdrop is not None else None) is world_map:
            return
        if self.backdrop is not None:
            self.removeItem(self.backdrop)
            self.backdrop = None
        if world_map is not None:
            self.backdrop = MapImage(world_map)
            self.addItem(self.backdrop, ignoreBounds=True)

    def reset_view(self):
        """Fit the view to the tracks again, and keep doing so as they change."""
        self.user_view = False
        if self.fit:
            self.setRange(xRange=self.fit[0], yRange=self.fit[1], padding=0)

    def wheelEvent(self, ev):
        if self.interactive:
            # at a limit the view box no longer scales but still moves about the pointer at every step, so
            # turning on past it would carry the view off the tracks
            (x0, x1), (y0, y1) = self.viewRange()
            lo, hi = self.ZOOM
            d = ev.angleDelta().y() or ev.angleDelta().x()
            if (d > 0 and min(x1 - x0, y1 - y0) <= lo * 1.001) or (d < 0 and max(x1 - x0, y1 - y0) >= hi * 0.999):
                ev.accept()
                return
            pg.PlotWidget.wheelEvent(self, ev)  # the view box zooms
        else:
            super().wheelEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if self.interactive:
            self.reset_view()
        super().mouseDoubleClickEvent(ev)

    _speed_colors = None

    @classmethod
    def speed_colors(cls):
        """The colour of each speed bin, at its middle."""
        if cls._speed_colors is None:
            cls._speed_colors = [speed_color((b + 0.5) * 250 / cls.BINS) for b in range(cls.BINS)]
        return cls._speed_colors

    def set_tracks(self, tracks, markers=(), area=None):
        """tracks: [dict(x, y, color=None | speeds=array, width)]; markers: [(x, y, color)]; area: (xs, ys) the
        view is fitted to instead of the tracks, so it holds still while they grow (a replay)."""
        lines = []  # [(pen, QPolygonF)], in the order the tracks come
        allx, ally = [], []
        widest = 0.0
        for tr in tracks:
            x, y = np.asarray(tr["x"], float), np.asarray(tr["y"], float)
            if len(x) < 2:
                continue
            keep = thin(len(x), MAP_POINTS)
            x, y = x[keep], y[keep]
            allx.append(x)
            ally.append(y)
            width = tr.get("width", 3)
            widest = max(widest, width)
            if tr.get("speeds") is not None:
                v = np.nan_to_num(np.asarray(tr["speeds"], float)[keep][1:])
                key = np.clip((v / 250 * self.BINS).astype(int), 0, self.BINS - 1)
            else:
                key = np.zeros(len(x) - 1, int)
            # runs of consecutive segments in the same colour, each drawn as polylines
            cut = np.flatnonzero(np.diff(key)) + 1
            sx, sy = y, x  # screen order: game +Y right, +X up
            for a, z in zip(np.r_[0, cut], np.r_[cut, len(key)]):
                c = self.speed_colors()[key[a]] if tr.get("speeds") is not None else tr["color"]
                pn = pen(c, width, Qt.RoundCap)
                for i in range(a, z, Tracks.CHUNK):  # segments i..j-1 are points i..j
                    j = min(i + Tracks.CHUNK, z)
                    lines.append((pn, fn.arrayToQPolygonF(sx[i:j + 1], sy[i:j + 1])))
        if allx:
            X, Y = np.concatenate(allx), np.concatenate(ally)
            self.tracks.set_lines(lines, QRectF(Y.min(), X.min(), Y.max() - Y.min(), X.max() - X.min()),
                                  widest / 2 + 1)
        else:
            self.tracks.set_lines([], QRectF(), 0)
        self.set_markers(markers)
        if area is not None and len(area[0]):
            allx, ally = [np.asarray(area[0], float)], [np.asarray(area[1], float)]
        self.scale.active = bool(allx)
        self.scale.update()
        self.show_empty(not allx)
        if allx:
            X, Y = np.concatenate(allx), np.concatenate(ally)
            span = max(X.max() - X.min(), Y.max() - Y.min(), 20)
            cx, cy = (Y.max() + Y.min()) / 2, (X.max() + X.min()) / 2
            h = span / 2 * 1.08
            self.fit = ((cx - h, cx + h), (cy - h, cy + h))
        else:
            self.fit = ((-1, 1), (-1, 1))
        if not self.user_view:  # a view zoomed or moved by hand stays
            self.setRange(xRange=self.fit[0], yRange=self.fit[1], padding=0)

    def set_markers(self, markers):
        """markers: [(x, y, color)], e.g. where each run is at the hover point."""
        self.markers.setData([m[1] for m in markers], [m[0] for m in markers],
                             brush=[brush(m[2]) for m in markers])


class GGChart(BaseChart):
    """As in sim overlays: acceleration up, braking down, and the dot moves to the outside of the
    turn (left in a right-hand turn), i.e. the force the driver feels."""

    def __init__(self):
        super().__init__(axes=False, frame=False)
        self.setMinimumHeight(MIN_HEIGHT)
        self.setAspectLocked(True)
        self.deco = []
        self.scatters = []
        self.mx = None
        self.fade_styles = {}  # (colour, n) -> fade_style()

    def fade_style(self, color, n):
        """Brushes and sizes of n dots that fade in from the oldest, the newest one big. The same n comes
        every frame, so they are made once."""
        key = (color.rgba(), n)
        style = self.fade_styles.get(key)
        if style is None:
            brushes = []
            for i in range(n):
                cc = QColor(color)
                # a few fixed steps, so pyqtgraph draws each dot style once and reuses it
                cc.setAlphaF(round(0.15 + 0.85 * (i + 1) / n, 1))
                brushes.append(brush(cc))
            sizes = np.full(n, 5.0)
            sizes[-1] = 12
            style = self.fade_styles[key] = (brushes, sizes)
        return style

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
        gap = mx * 0.04  # between the ring and its labels
        for text, pos, anchor in (("accel", (0, mx + gap), (0.5, 1)), ("braking", (0, -mx - gap), (0.5, 0)),
                                  ("left", (-mx - gap, 0), (1, 0.5)), ("right", (mx + gap, 0), (0, 0.5))):
            t = pg.TextItem(text, color=theme.MUTED, anchor=anchor)
            t.setFont(theme.font(11))
            t.setPos(*pos)
            self.addItem(t)
            self.deco.append(t)
        m = mx * 1.25  # room for the accel / braking labels; the view is wider than tall, so left and right fit
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
                brushes, sizes = self.fade_style(c, n)
                sc.setData(-ga, gl, brush=brushes, size=sizes)
            else:
                c.setAlphaF(0.55)
                sc.setData(-ga, gl, brush=brush(c), size=4)
        self.show_empty(not any(len(s["ga"]) for s in sets))
        self.empty.setPos(0, 0)

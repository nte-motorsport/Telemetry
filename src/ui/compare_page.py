"""The Compare page: the runs table and every visible run on charts by distance from the start."""
import os

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QRadioButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from runs.csv_io import export_csv, import_csv
from ui import charts, theme
from ui.widgets import Button, card, chart_grid, label, legend_dot, panel, scroll

ROW_HEIGHT = 52


def fmt_time(s):
    m = int(s // 60)
    return f"{m}:{s - 60 * m:04.1f}" if m else f"{s:.1f}"


class ComparePage(QWidget):
    runs_changed = Signal(int)  # number of runs, after any add / delete

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.cursor_dist = None
        self.dirty = True

        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(theme.GAP)

        hint, hl = panel()
        hl.addWidget(label("Runs are compared by distance travelled from the start, so begin every recording at the same "
                           "spot and drive the same route. The reference run sets Δt: plus means the run is "
                           "behind the reference.", "muted", wrap=True))
        v.addWidget(hint)

        tp, tl = panel()
        tl.addWidget(label("Runs", "sectionTitle"))
        self.empty_runs = label("No runs yet. Press “Record run” or import a CSV exported from this app.",
                                "muted", wrap=True)
        tl.addWidget(self.empty_runs)
        self.table = QTableWidget()
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        tl.addWidget(self.table)
        v.addWidget(tp)

        rp, rl = panel()
        self.readout = label("", "muted", wrap=True)
        self.readout.setTextFormat(Qt.RichText)
        rl.addWidget(self.readout)
        v.addWidget(rp)

        self.k_speed = charts.LineChart(charts.dist_fmt, zero=True)
        self.k_delta = charts.LineChart(charts.dist_fmt, sym=0.5)
        self.k_map = charts.MapChart()
        self.k_gg = charts.GGChart()
        self.k_lat = charts.LineChart(charts.dist_fmt, sym=1)
        self.k_lon = charts.LineChart(charts.dist_fmt, sym=1)
        self.k_z = charts.LineChart(charts.dist_fmt)
        self.dist_charts = [self.k_speed, self.k_delta, self.k_lat, self.k_lon, self.k_z]
        for c in self.dist_charts:
            c.hovered.connect(self.set_cursor)
        v.addWidget(chart_grid([
            card("Speed by distance", self.k_speed),
            card("Δt to reference", self.k_delta, "+ slower, − faster"),
            card("Trajectories", self.k_map),
            card("G-G diagram", self.k_gg),
            card("Lateral G by distance", self.k_lat),
            card("Longitudinal G by distance", self.k_lon),
            card("Altitude by distance", self.k_z),
        ]))
        v.addStretch()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.scroll = scroll(body)
        lay.addWidget(self.scroll)
        self.render_table()

    # ----- runs -----

    def add_run(self, name, pts):
        self.store.add(name, pts)
        self.render_table()

    def import_csv(self):
        """Ask for CSV files and add each as a run; True if anything was added."""
        paths, _ = QFileDialog.getOpenFileNames(self, "Import runs", "", "CSV (*.csv)")
        added = 0
        for p in paths:
            try:
                pts = import_csv(p)
            except (OSError, ValueError, KeyError) as e:
                QMessageBox.warning(self, "Import CSV", f"Could not read {os.path.basename(p)}:\n{e}")
                continue
            if len(pts) > 5:
                self.store.add(os.path.splitext(os.path.basename(p))[0], pts)
                added += 1
        if added:
            self.render_table()
        return bool(added)

    def export_run(self, run):
        name = "".join(c if c.isalnum() or c in " -_" else "_" for c in run.name)
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", name + ".csv", "CSV (*.csv)")
        if path:
            export_csv(run, path)

    def delete_run(self, run):
        if QMessageBox.question(self, "Delete run", f"Delete “{run.name}”?") == QMessageBox.Yes:
            self.store.remove(run)
            self.render_table()

    def set_visible(self, run, on):
        run.visible = on
        self.store.save()
        self.dirty = True

    def rename(self, run, name):
        if name and name != run.name:
            run.name = name
            self.store.save()
            self.dirty = True

    def set_ref(self, run):
        self.store.ref_id = run.id
        self.store.save()
        self.dirty = True

    def set_cursor(self, x):
        if x is not None and x < 0:
            x = None
        if x != self.cursor_dist:
            self.cursor_dist = x
            self.dirty = True

    # ----- rendering -----

    def render_table(self):
        rs = self.store.runs
        self.empty_runs.setVisible(not rs)
        self.table.setVisible(bool(rs))
        cols = ["", "Run", "Reference", "Distance, km", "Time", "Max, km/h", "Average", "Max lateral g",
                "Max braking g", "Max accel g", ""]
        self.table.clear()
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setRowCount(len(rs))
        self.ref_group = QButtonGroup(self.table)
        for row, r in enumerate(rs):
            s = r.stats()
            vis = QWidget()
            vh = QHBoxLayout(vis)
            vh.setContentsMargins(0, 0, theme.GAP, 0)
            vh.setSpacing(8)
            cb = QCheckBox()
            cb.setChecked(r.visible)
            cb.toggled.connect(lambda on, r=r: self.set_visible(r, on))
            sw = QLabel()
            sw.setFixedSize(14, 14)
            sw.setStyleSheet(f"background:{r.color}; border-radius:4px;")
            vh.addWidget(cb)
            vh.addWidget(sw)
            self.table.setCellWidget(row, 0, vis)

            name = QLineEdit(r.name)
            name.editingFinished.connect(lambda r=r, w=name: self.rename(r, w.text()))
            self.table.setCellWidget(row, 1, name)

            rb_wrap = QWidget()
            rh = QHBoxLayout(rb_wrap)
            rh.setContentsMargins(theme.GAP, 0, 0, 0)
            rb = QRadioButton()
            rb.setChecked(r.id == self.store.ref_id)
            rb.toggled.connect(lambda on, r=r: on and self.set_ref(r))
            self.ref_group.addButton(rb)
            rh.addWidget(rb)
            self.table.setCellWidget(row, 2, rb_wrap)

            vals = [f"{s['dist']:.3f}", fmt_time(s["time"]), f"{s['vmax']:.1f}", f"{s['vavg']:.1f}",
                    f"{s['ga']:.2f}", f"{s['brake']:.2f}", f"{s['acc']:.2f}"]
            for i, val in enumerate(vals):
                it = QTableWidgetItem(val)
                it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.table.setItem(row, 3 + i, it)

            act = QWidget()
            ah = QHBoxLayout(act)
            ah.setContentsMargins(0, 0, 0, 0)
            ah.setSpacing(theme.GAP)
            dl = Button("Save CSV", "download", icon_only=True)
            dl.clicked.connect(lambda _=False, r=r: self.export_run(r))
            de = Button("Delete", "trash", icon_only=True)
            de.set_flag("danger", True)
            de.clicked.connect(lambda _=False, r=r: self.delete_run(r))
            ah.addWidget(dl)
            ah.addWidget(de)
            self.table.setCellWidget(row, 10, act)

        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(10, QHeaderView.Fixed)
        self.table.setColumnWidth(10, 2 * (theme.CONTROL_HEIGHT) + theme.GAP + 4)
        self.table.setFixedHeight(hh.sizeHint().height() + ROW_HEIGHT * len(rs) + 4)
        self.dirty = True
        self.runs_changed.emit(len(rs))

    def render(self):
        if not self.dirty:
            return
        self.dirty = False
        vis = [r for r in self.store.runs if r.visible]
        ref = self.store.ref
        w = lambda r: 2.6 if r is ref else 1.8
        xmax = max((r.a["dist"][-1] for r in vis), default=1.0)
        xr = (0, max(xmax, 1.0))

        def S(key):
            return [(r.a["dist"], r.a[key], r.color, w(r)) for r in vis]

        self.k_speed.set_series(S("v"), xr)
        self.k_delta.set_series([(*r.delta_to(ref), r.color, w(r)) for r in vis] if ref else [], xr)
        self.k_lat.set_series(S("ga"), xr)
        self.k_lon.set_series(S("gl"), xr)
        self.k_z.set_series(S("z"), xr)
        cd = self.cursor_dist
        for c in self.dist_charts:
            c.set_cursor(cd)
        markers = []
        if cd is not None:
            for r in vis:
                x, y = r.at(cd, "x"), r.at(cd, "y")
                if np.isfinite(x):
                    markers.append((x, y, r.color))
        self.k_map.set_tracks([dict(x=r.a["x"], y=r.a["y"], color=r.color, width=3.5 if r is ref else 2.5)
                               for r in vis], markers)
        self.k_gg.set_sets([dict(ga=r.a["ga"], gl=r.a["gl"], color=r.color) for r in vis])

        if not vis:
            self.readout.setText("")
        elif cd is None:
            self.readout.setText("Hover over a chart to see every run's values at one point on the track.")
        else:
            parts = [f'<b style="color:{theme.TEXT}">{charts.dist_fmt(cd)}</b>']
            for r in vis:
                v = r.at(cd, "v")
                if not np.isfinite(v):
                    continue
                s = f'{legend_dot(r.color)} <b style="color:{theme.TEXT}">{r.name}</b> {v:.0f} km/h'
                if ref and r is not ref:
                    dt = r.at(cd, "time") - ref.at(cd, "time")
                    if np.isfinite(dt):
                        s += f", Δt {dt:+.2f} s"
                s += f", lateral {r.at(cd, 'ga'):.2f} g"
                parts.append(s)
            self.readout.setText(" &nbsp;&nbsp; ".join(parts))

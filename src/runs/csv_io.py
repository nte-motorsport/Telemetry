"""Runs as CSV files, one row per point, for sharing and backups."""
import csv

from runs.model import point

CSV_COLS = ["t", "x", "y", "z", "speed_kmh", "heading", "vz", "slope_deg", "g_long", "g_lat",
            "yaw_rate", "slip_deg", "cam_yaw", "odo_km"]


def export_csv(run, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLS)
        for p in run.pts:
            w.writerow([p["t"], p["x"], p["y"], p["z"], p["v"], p.get("hdg", 0), 0, p.get("slope", 0),
                        p["gl"], p["ga"], p["yaw"], 0, 0, f"{p['dist'] / 1000:.4f}"])


def import_csv(path):
    """Points from a CSV written by export_csv."""
    pts, time_s, prev_t, odo0 = [], 0.0, None, None
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            d = {k: float(row.get(k) or 0) for k in CSV_COLS}
            if prev_t is not None:
                dt = d["t"] - prev_t
                time_s += dt if 0 < dt < 3 else 0.1
            prev_t = d["t"]
            if odo0 is None:
                odo0 = d["odo_km"]
            pts.append(point(time_s, (d["odo_km"] - odo0) * 1000, d))
    return pts

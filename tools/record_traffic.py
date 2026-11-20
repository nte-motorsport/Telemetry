"""Capture all the raw traffic of one interface to a gzipped .pcap, whatever the app makes of it: to look into
the game's packets when the app no longer reads them (a game update changed them).

    python tools/record_traffic.py [<seconds, 600 if left out>] [<out .pcap.gz>]

Run it from a terminal opened as administrator, then race; Ctrl+C stops it early. Without <out> the file goes to
the app's replays folder, %APPDATA%\\NTE Telemetry\\replays, named capture_<date>_<time>.pcap.gz (not a replay:
the Replays page leaves it be). The app may run at the same time.
"""
import datetime
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from capture.pcap import PcapWriter  # noqa: E402
from capture.raw_socket import RawCapture  # noqa: E402
from ui.prefs import data_dir  # noqa: E402


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 600.0
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        data_dir(), "replays", datetime.datetime.now().strftime("capture_%Y-%m-%d_%H-%M-%S.pcap.gz"))
    try:
        cap = RawCapture()
    except PermissionError:
        sys.exit("Needs administrator rights: run it from a terminal opened as administrator.")
    w = PcapWriter(out)
    print(f"Capturing on {cap.ip} for {seconds:.0f} s to {out} (Ctrl+C stops it)")
    end = time.monotonic() + seconds
    shown = 0.0
    try:
        for _ in cap.packets(lambda: time.monotonic() >= end, lambda: w):
            if time.monotonic() - shown >= 10:
                shown = time.monotonic()
                print(f"  {w.packets} packets, {end - shown:.0f} s left")
    except KeyboardInterrupt:
        pass
    finally:
        cap.close()
        w.close()
    print(f"Done: {w.packets} packets in {out}")


if __name__ == "__main__":
    main()

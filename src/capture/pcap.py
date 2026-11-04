"""Raw IPv4 packets to a gzipped .pcap file, which Wireshark opens as it is."""
import gzip
import struct
import threading
import time

LINKTYPE_IPV4 = 228  # each record is a bare IPv4 packet, as the raw socket gives them


class PcapWriter:
    """Written to from the capture thread, closed from the UI thread; a packet that comes after close() is
    dropped."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.f = gzip.open(path, "wb", compresslevel=3)  # light: it runs beside the game
        self.f.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, LINKTYPE_IPV4))
        self.packets = 0

    def write(self, pkt, t=None):
        t = time.time() if t is None else t
        with self.lock:
            if self.f is None:
                return
            self.f.write(struct.pack("<IIII", int(t), int(t % 1 * 1e6), len(pkt), len(pkt)) + pkt)
            self.packets += 1

    def close(self):
        with self.lock:
            if self.f is not None:
                self.f.close()
                self.f = None

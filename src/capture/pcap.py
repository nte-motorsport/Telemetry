"""Raw IPv4 packets to a gzipped .pcap file, which Wireshark opens as it is."""
import gzip
import struct
import threading
import time
from collections import deque

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


class RawTap:
    """What the capture gives every packet to while raw traffic is wanted. Until a writer is attached it keeps
    the last SPAN seconds of them in memory (never on disk), at most MAX_BYTES, so a race's raw traffic starts
    before the race did: the server names its world and the players well before the first rival shows up.
    attach() writes those out first; from then on packets go straight to the writer."""
    SPAN = 30.0                  # s of packets kept before a race
    MAX_BYTES = 64 * 1024 * 1024  # and at most this much of them (a download beside the game)

    def __init__(self):
        self.lock = threading.Lock()
        self.kept = deque()  # (arrival time, packet), the oldest first
        self.size = 0
        self.writer = None

    def write(self, pkt, t=None):
        t = time.time() if t is None else t
        with self.lock:
            if self.writer is not None:
                self.writer.write(pkt, t)
                return
            self.kept.append((t, pkt))
            self.size += len(pkt)
            while self.kept and (t - self.kept[0][0] > self.SPAN or self.size > self.MAX_BYTES):
                self.size -= len(self.kept.popleft()[1])

    def attach(self, writer):
        """From now on into writer, the kept packets first."""
        with self.lock:
            since = time.time() - self.SPAN  # (they are dropped as newer ones come: after a quiet spell, older)
            for t, pkt in self.kept:
                if t >= since:
                    writer.write(pkt, t)
            self.kept.clear()
            self.size = 0
            self.writer = writer

    def detach(self):
        """Back to keeping the last SPAN s in memory."""
        with self.lock:
            self.writer = None

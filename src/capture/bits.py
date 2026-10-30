"""Finding a fixed bit pattern in a packet read as an LSB-first bit stream."""
import numpy as np


def find(payload, value, width, lo=0, hi=None):
    """Every offset o in lo..hi-1 at which the width bits starting at bit o equal value.

    Done on arrays: testing each offset by shifting the packet as one big integer costs time in
    proportion to the packet's size at every offset, which a stream of large packets (a download running
    beside the game) turns into seconds per second of traffic."""
    bits = np.unpackbits(np.frombuffer(payload, np.uint8), bitorder="little")
    hi = len(bits) - width + 1 if hi is None else min(hi, len(bits) - width + 1)
    if hi <= lo:
        return []
    n = hi - lo
    v = np.zeros(n, np.uint32)
    for i in range(width):
        v |= bits[lo + i:lo + i + n].astype(np.uint32) << i
    return (np.flatnonzero(v == value) + lo).tolist()

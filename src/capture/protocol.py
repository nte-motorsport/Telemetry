"""Decoding the game's outgoing UE movement packets into raw position fixes.

Packet layout (bit offsets relative to MARKER, LSB-first UE bit stream):
  -32 .. -1  float32 client timestamp (seconds)
    0 .. 9   constant marker 0x041
   10 .. 16  quantized-vector header: 6-bit component width N | 0x40 (scaled flag)
   17 ..     X, Y, Z: N bits each, two's complement, units 1/100 cm (N grows with distance from origin)
   then      camera rotation (UE compressed shorts: [flag+16 bit] pitch, yaw, roll)
"""
import struct

from capture import bits

MARKER, SCALE = 0x041, 10000.0  # SCALE: raw units -> metres


def decode(payload: bytes):
    """Yield every (ts, x, y, z, cam_yaw) candidate; the tracker picks the plausible one."""
    n = int.from_bytes(payload, "little")
    nbits = len(payload) * 8
    for off in bits.find(payload, MARKER, 10, 32, nbits - 70):
        hdr = (n >> (off + 10)) & 0x7F
        w = hdr & 0x3F
        if not (hdr & 0x40) or not (12 <= w <= 32) or off + 17 + 3 * w + 3 > nbits:
            continue
        ts = struct.unpack("<f", struct.pack("<I", (n >> (off - 32)) & 0xFFFFFFFF))[0]
        if not (0 < ts < 1e7):
            continue
        # each component is a w-bit two's complement integer; w = bits needed for the largest |component|
        mask, sign = (1 << w) - 1, 1 << (w - 1)
        x, y, z = (((((n >> (off + 17 + i * w)) & mask) ^ sign) - sign) / SCALE for i in range(3))
        p = off + 17 + 3 * w
        cam = []
        for _ in range(3):
            if (n >> p) & 1:
                a = ((n >> (p + 1)) & 0xFFFF) * 360 / 65536
                cam.append(a - 360 if a > 180 else a)
                p += 17
            else:
                cam.append(0.0)
                p += 1
        yield ts, x, y, z, cam[1]

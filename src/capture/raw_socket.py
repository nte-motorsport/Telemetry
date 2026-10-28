"""Live UDP capture without Wireshark/Npcap: a Windows raw socket in SIO_RCVALL mode.

Needs administrator rights. Sees IPv4 traffic of one local interface in both directions;
yields (src_port, dst_port, payload) for UDP datagrams, skipping DNS and QUIC (53, 443),
as they are never game traffic.
"""
import socket
import struct

SKIP_PORTS = {53, 443}


def default_ip():
    """IPv4 address of the interface that holds the default route (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def local_ips():
    """All local IPv4 addresses, the default-route one first."""
    ips = [default_ip()]
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips


class RawCapture:
    def __init__(self, ip=None):
        self.ip = ip or default_ip()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
        self.sock.bind((self.ip, 0))
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
        self.sock.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
        self.sock.settimeout(0.5)

    def close(self):
        try:
            self.sock.ioctl(socket.SIO_RCVALL, socket.RCVALL_OFF)
        except OSError:
            pass
        self.sock.close()

    def packets(self, stop=lambda: False):
        """Yield (src_port, dst_port, payload) until stop() returns True."""
        while not stop():
            try:
                pkt = self.sock.recv(65535)
            except socket.timeout:
                continue
            except OSError:
                if stop():
                    return
                raise
            if len(pkt) < 28 or pkt[0] >> 4 != 4 or pkt[9] != 17:  # IPv4 + UDP only
                continue
            ihl = (pkt[0] & 0x0F) * 4
            if struct.unpack_from("!H", pkt, 6)[0] & 0x1FFF:  # skip non-first fragments
                continue
            sport, dport, ulen = struct.unpack_from("!HHH", pkt, ihl)
            if sport in SKIP_PORTS or dport in SKIP_PORTS:
                continue
            yield sport, dport, pkt[ihl + 8:ihl + max(ulen, 8)]

#!/usr/bin/env python3
"""Single-client DHCP for a direct YKV-02 Ethernet link.

Binds only to the lab NIC address (default 192.168.50.1:67) so home Wi-Fi
DHCP is never answered. Offers a single address (default 192.168.50.11).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import struct
import sys
import time

MAGIC = b"\x63\x82\x53\x63"
BOOTREQUEST = 1
BOOTREPLY = 2
DHCP_DISCOVER = 1
DHCP_OFFER = 2
DHCP_REQUEST = 3
DHCP_ACK = 5
DHCP_NAK = 6

OPT_MSG_TYPE = 53
OPT_REQ_IP = 50
OPT_SERVER_ID = 54
OPT_LEASE = 51
OPT_SUBNET = 1
OPT_ROUTER = 3
OPT_END = 255


def _ip(addr: str) -> bytes:
    return socket.inet_aton(addr)


def _parse_options(blob: bytes) -> dict[int, bytes]:
    out: dict[int, bytes] = {}
    i = 0
    while i < len(blob):
        tag = blob[i]
        if tag == 0:
            i += 1
            continue
        if tag == OPT_END:
            break
        if i + 1 >= len(blob):
            break
        length = blob[i + 1]
        start = i + 2
        end = start + length
        if end > len(blob):
            break
        out[tag] = blob[start:end]
        i = end
    return out


def _opt(tag: int, data: bytes) -> bytes:
    return bytes([tag, len(data)]) + data


def parse_dhcp(pkt: bytes) -> dict | None:
    if len(pkt) < 240 or pkt[236:240] != MAGIC:
        return None
    op, htype, hlen, _hops, xid, _secs, flags = struct.unpack_from("!BBBBLHH", pkt, 0)
    if op != BOOTREQUEST or htype != 1 or hlen != 6:
        return None
    ciaddr = pkt[12:16]
    chaddr = pkt[28 : 28 + 6]
    opts = _parse_options(pkt[240:])
    msg = opts.get(OPT_MSG_TYPE, b"\x00")
    return {
        "xid": xid,
        "flags": flags,
        "ciaddr": ciaddr,
        "chaddr": chaddr,
        "msg": msg[0] if msg else 0,
        "req_ip": opts.get(OPT_REQ_IP),
        "server_id": opts.get(OPT_SERVER_ID),
    }


def build_reply(
    req: dict,
    msg_type: int,
    server_ip: str,
    offer_ip: str,
    mask: str,
) -> bytes:
    yiaddr = b"\x00\x00\x00\x00" if msg_type == DHCP_NAK else _ip(offer_ip)
    header = struct.pack(
        "!BBBBLHH4s4s4s4s16s64s128s",
        BOOTREPLY,
        1,
        6,
        0,
        req["xid"],
        0,
        req["flags"],
        req["ciaddr"],
        yiaddr,
        _ip(server_ip),
        b"\x00\x00\x00\x00",
        req["chaddr"] + b"\x00" * 10,
        b"\x00" * 64,
        b"\x00" * 128,
    )
    options = MAGIC + b"".join(
        [
            _opt(OPT_MSG_TYPE, bytes([msg_type])),
            _opt(OPT_SERVER_ID, _ip(server_ip)),
            _opt(OPT_LEASE, struct.pack("!I", 3600)),
            _opt(OPT_SUBNET, _ip(mask)),
            _opt(OPT_ROUTER, _ip(server_ip)),
            bytes([OPT_END]),
        ]
    )
    pkt = header + options
    if len(pkt) < 300:
        pkt += b"\x00" * (300 - len(pkt))
    return pkt


def _mac(chaddr: bytes) -> str:
    return ":".join(f"{b:02x}" for b in chaddr[:6])


def serve(server_ip: str, offer_ip: str, mask: str, pid_file: str | None) -> None:
    log = logging.getLogger("ykv-dhcp")
    if server_ip in ("0.0.0.0", "::", "127.0.0.1"):
        raise SystemExit("Refusing to bind a wildcard/loopback DHCP socket")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.bind((server_ip, 67))
    except OSError as e:
        raise SystemExit(
            f"bind {server_ip}:67 failed ({e}). Run as root and bind only the lab NIC."
        ) from e
    sock.settimeout(1.0)

    if pid_file:
        with open(pid_file, "w", encoding="ascii") as fh:
            fh.write(str(os.getpid()))

    stop = False

    def _stop(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("DHCP on %s:67 offering %s (mask %s)", server_ip, offer_ip, mask)
    offer_aton = _ip(offer_ip)
    server_aton = _ip(server_ip)

    while not stop:
        try:
            data, addr = sock.recvfrom(2048)
        except (TimeoutError, socket.timeout):
            continue
        req = parse_dhcp(data)
        if req is None:
            continue
        msg = req["msg"]
        log.info("from %s mac=%s type=%s", addr, _mac(req["chaddr"]), msg)

        if msg == DHCP_DISCOVER:
            reply = build_reply(req, DHCP_OFFER, server_ip, offer_ip, mask)
        elif msg == DHCP_REQUEST:
            requested = req["req_ip"]
            sid = req["server_id"]
            ok_ip = requested in (None, offer_aton)
            ok_sid = sid in (None, server_aton)
            kind = DHCP_ACK if ok_ip and ok_sid else DHCP_NAK
            reply = build_reply(req, kind, server_ip, offer_ip, mask)
        else:
            continue

        dest = ("255.255.255.255", 68)
        if req["ciaddr"] != b"\x00\x00\x00\x00":
            dest = (socket.inet_ntoa(req["ciaddr"]), 68)
        try:
            sock.sendto(reply, dest)
        except OSError as e:
            log.warning("sendto %s failed: %s", dest, e)

    sock.close()
    if pid_file:
        try:
            os.remove(pid_file)
        except OSError:
            pass
    log.info("DHCP stopped")


def _bootp_request(
    msg_type: int,
    xid: int = 0x11223344,
    chaddr: bytes | None = None,
    req_ip: bytes | None = None,
    server_id: bytes | None = None,
    flags: int = 0x8000,
    ciaddr: bytes | None = None,
) -> bytes:
    mac = chaddr or bytes.fromhex("aabbccddeeff")
    ciaddr = ciaddr or b"\x00" * 4
    header = struct.pack(
        "!BBBBLHH4s4s4s4s16s64s128s",
        BOOTREQUEST,
        1,
        6,
        0,
        xid,
        0,
        flags,
        ciaddr,
        b"\x00" * 4,
        b"\x00" * 4,
        b"\x00" * 4,
        mac + b"\x00" * 10,
        b"\x00" * 64,
        b"\x00" * 128,
    )
    opts = [_opt(OPT_MSG_TYPE, bytes([msg_type]))]
    if req_ip is not None:
        opts.append(_opt(OPT_REQ_IP, req_ip))
    if server_id is not None:
        opts.append(_opt(OPT_SERVER_ID, server_id))
    opts.append(bytes([OPT_END]))
    return header + MAGIC + b"".join(opts)


def self_test() -> int:
    """Parse/build checks only — does not bind port 67."""
    assert parse_dhcp(b"short") is None
    assert parse_dhcp(b"\x00" * 240) is None
    disc = parse_dhcp(_bootp_request(DHCP_DISCOVER))
    assert disc is not None
    assert disc["msg"] == DHCP_DISCOVER
    assert disc["chaddr"] == bytes.fromhex("aabbccddeeff")
    offer = build_reply(disc, DHCP_OFFER, "192.168.50.1", "192.168.50.11", "255.255.255.0")
    assert len(offer) >= 300
    assert offer[0] == BOOTREPLY
    assert offer[16:20] == _ip("192.168.50.11")
    assert MAGIC in offer
    rq = parse_dhcp(
        _bootp_request(
            DHCP_REQUEST,
            req_ip=_ip("192.168.50.11"),
            server_id=_ip("192.168.50.1"),
        )
    )
    assert rq is not None
    ack = build_reply(rq, DHCP_ACK, "192.168.50.1", "192.168.50.11", "255.255.255.0")
    assert ack[16:20] == _ip("192.168.50.11")
    nak = build_reply(rq, DHCP_NAK, "192.168.50.1", "192.168.50.11", "255.255.255.0")
    assert nak[16:20] == b"\x00" * 4
    print("ykv_dhcp self-test OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Single-address DHCP for YKV-02")
    p.add_argument("--server-ip", default="192.168.50.1")
    p.add_argument("--offer-ip", default="192.168.50.11")
    p.add_argument("--mask", default="255.255.255.0")
    p.add_argument("--pid-file", default="/tmp/ykv-dhcp.pid")
    p.add_argument("--foreground", action="store_true")
    p.add_argument(
        "--self-test",
        action="store_true",
        help="Parse/build unit checks; do not bind UDP/67",
    )
    args = p.parse_args(argv)

    if args.self_test:
        return self_test()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    if args.server_ip in ("0.0.0.0", "::", "127.0.0.1"):
        print("Refusing to bind a wildcard/loopback DHCP socket", file=sys.stderr)
        return 2
    if os.geteuid() != 0:
        print("Run as root: sudo python3 tools/ykv_dhcp.py", file=sys.stderr)
        return 2

    if args.foreground:
        serve(args.server_ip, args.offer_ip, args.mask, args.pid_file)
        return 0

    pid = os.fork()
    if pid > 0:
        print(f"ykv_dhcp pid={pid} offering {args.offer_ip} via {args.server_ip}")
        return 0
    os.setsid()
    serve(args.server_ip, args.offer_ip, args.mask, args.pid_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

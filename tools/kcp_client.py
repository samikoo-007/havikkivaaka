#!/usr/bin/env python3
"""Minimal KCP TCP client for YKV-02 / KERN devices (port 23)."""

from __future__ import annotations

import argparse
import re
import socket
import sys
import time

DEFAULT_PORT = 23
WEIGHT_RE = re.compile(
    r"^(?P<echo>S|SI|SX)\s+(?P<status>[SDI+\-]|[A-Z0-9]+)\s+"
    r"(?P<value>[-\d. ]+)\s+(?P<unit>\S+)\s*$"
)


class KcpError(RuntimeError):
    pass


class KcpClient:
    def __init__(self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buf = b""

    def connect(self) -> None:
        self.close()
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        self._sock = sock
        self._buf = b""

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self) -> KcpClient:
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def send_raw(self, line: str) -> str:
        if self._sock is None:
            raise KcpError("not connected")
        payload = line.rstrip("\r\n") + "\r\n"
        self._sock.sendall(payload.encode("ascii", errors="strict"))
        return self._readline()

    def _readline(self) -> str:
        assert self._sock is not None
        deadline = time.monotonic() + self.timeout
        while b"\n" not in self._buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("KCP response timeout")
            self._sock.settimeout(remaining)
            chunk = self._sock.recv(4096)
            if not chunk:
                raise KcpError("connection closed by peer")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode("ascii", errors="replace").rstrip("\r")

    def cmd(self, command: str) -> str:
        return self.send_raw(command)

    def cancel(self) -> str:
        return self.cmd("@")

    def si(self) -> tuple[str, float | None, str | None]:
        line = self.cmd("SI")
        return self._parse_weight(line)

    def s(self) -> tuple[str, float | None, str | None]:
        line = self.cmd("S")
        return self._parse_weight(line)

    def tare(self) -> str:
        return self.cmd("T")

    def zero(self) -> str:
        return self.cmd("Z")

    @staticmethod
    def _parse_weight(line: str) -> tuple[str, float | None, str | None]:
        if line.strip() == "ES":
            raise KcpError("ES: unknown/syntax error")
        m = WEIGHT_RE.match(line.strip())
        if not m:
            # Non-weight status e.g. "S I", "S +"
            parts = line.split()
            if len(parts) >= 2:
                return parts[1], None, None
            raise KcpError(f"unparsed response: {line!r}")
        status = m.group("status")
        raw = m.group("value").strip()
        unit = m.group("unit")
        try:
            value = float(raw)
        except ValueError:
            return status, None, unit
        return status, value, unit


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="KERN KCP TCP smoke client")
    p.add_argument("--host", default="192.168.50.11")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument(
        "action",
        choices=["si", "s", "tare", "zero", "i1", "cancel", "raw"],
        help="KCP action",
    )
    p.add_argument("raw_cmd", nargs="?", help="Raw command when action=raw")
    args = p.parse_args(argv)

    try:
        with KcpClient(args.host, args.port, args.timeout) as c:
            if args.action == "si":
                st, val, unit = c.si()
                print(f"status={st} value={val} unit={unit}")
            elif args.action == "s":
                st, val, unit = c.s()
                print(f"status={st} value={val} unit={unit}")
            elif args.action == "tare":
                print(c.tare())
            elif args.action == "zero":
                print(c.zero())
            elif args.action == "i1":
                print(c.cmd("I1"))
            elif args.action == "cancel":
                print(c.cancel())
            elif args.action == "raw":
                if not args.raw_cmd:
                    p.error("raw requires raw_cmd")
                print(c.cmd(args.raw_cmd))
    except (OSError, KcpError, TimeoutError) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""KERN KCP TCP client (ASCII, CR LF, port 23)."""

from __future__ import annotations

import json
import re
import socket
import time
from pathlib import Path

WEIGHT_RE = re.compile(
    r"^(?P<echo>S|SI|SX)\s+(?P<status>[SDI+\-]|[A-Z0-9]+)\s+"
    r"(?P<value>[-\d. ]+)\s+(?P<unit>\S+)\s*$"
)


class KcpError(RuntimeError):
    pass


class KcpClient:
    def __init__(self, host: str, port: int = 23, timeout: float = 5.0):
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

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def send_raw(self, line: str) -> str:
        self.send_no_reply(line)
        return self.readline()

    def send_no_reply(self, line: str) -> None:
        if self._sock is None:
            raise KcpError("not connected")
        payload = line.rstrip("\r\n") + "\r\n"
        self._sock.sendall(payload.encode("ascii", errors="strict"))

    def readline(self, timeout: float | None = None) -> str:
        assert self._sock is not None
        wait = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + wait
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

    def _readline(self) -> str:
        return self.readline()

    def cmd(self, command: str) -> str:
        return self.send_raw(command)

    def cancel(self) -> str:
        return self.cmd("@")

    def si(self) -> tuple[str, float | None, str | None]:
        return self._parse_weight(self.cmd("SI"))

    def s(self) -> tuple[str, float | None, str | None]:
        return self._parse_weight(self.cmd("S"))

    def sad(self) -> int:
        """Raw A/D converter counts (KCP SAD). Independent of kg calibration."""
        line = self.cmd("SAD")
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "SAD" and parts[1] == "A":
            return int(parts[2])
        if len(parts) >= 2 and parts[0] == "SAD":
            return int(parts[1])
        raise KcpError(f"unparsed SAD response: {line!r}")

    def tare(self) -> str:
        return self.cmd("T")

    def zero(self) -> str:
        return self.cmd("Z")

    @staticmethod
    def to_grams(value: float, unit: str | None) -> float:
        """Normalize KCP weight to grams (app / kiosk always use g)."""
        u = (unit or "g").strip().lower()
        if u in ("kg", "kilogram", "kilograms"):
            return value * 1000.0
        if u in ("mg",):
            return value / 1000.0
        # g, gram, grams, or unknown → treat as grams
        return value

    @staticmethod
    def _parse_weight(line: str) -> tuple[str, float | None, str | None]:
        if line.strip() == "ES":
            raise KcpError("ES: unknown/syntax error")
        m = WEIGHT_RE.match(line.strip())
        if not m:
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
        return status, KcpClient.to_grams(value, unit), unit


def load_sad_cal(path: Path | None = None) -> dict[str, float] | None:
    """Load SAD→kg cal from data/ykv_sad_cal.json if present."""
    p = path or (Path(__file__).resolve().parents[1] / "data" / "ykv_sad_cal.json")
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return {
            "sad_empty": float(raw["sad_empty"]),
            "sad_at_ref": float(raw["sad_at_ref"]),
            "ref_kg": float(raw["ref_kg"]),
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def grams_from_sad(
    sad: int, cal: dict[str, float], *, tare_g: float = 0.0
) -> float:
    """Convert SAD AD counts to grams; optional software tare offset (SAD soft-tare)."""
    span = cal["sad_at_ref"] - cal["sad_empty"]
    if abs(span) < 1.0:
        raise KcpError("invalid SAD cal span")
    kg = (sad - cal["sad_empty"]) / span * cal["ref_kg"]
    return kg * 1000.0 - float(tare_g)


class MockScale:
    """In-process scale for dry-run without YKV / kcp_mock."""

    def __init__(self) -> None:
        self.weight_g = 0.0
        self.tare_g = 0.0

    @property
    def connected(self) -> bool:
        return True

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def si(self) -> tuple[str, float | None, str | None]:
        net = self.weight_g - self.tare_g
        return "S", net, "g"

    def tare(self) -> str:
        self.tare_g = self.weight_g
        return "T A"

    def zero(self) -> str:
        self.tare_g = 0.0
        self.weight_g = 0.0
        return "Z A"

    def cancel(self) -> str:
        return ""

    def add_grams(self, grams: float) -> None:
        self.weight_g += grams

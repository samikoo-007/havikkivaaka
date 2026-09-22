#!/usr/bin/env python3
"""YKV-02 USB signal-path diagnostic (read-mostly): identity, SI/SXI, SAD."""

from __future__ import annotations

import argparse
import glob
import os
import select
import statistics
import termios
import time
from typing import Any

BAUD = termios.B9600


def open_serial(path: str) -> int:
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[3] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[4] = BAUD
    attrs[5] = BAUD
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def xfer(fd: int, cmd: str, wait: float = 1.2) -> list[str]:
    os.write(fd, (cmd + "\r\n").encode("ascii"))
    end = time.monotonic() + wait
    buf = b""
    lines: list[str] = []
    while time.monotonic() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if not r:
            continue
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            chunk = b""
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            lines.append(line.decode("ascii", "replace").rstrip("\r"))
    return lines


def parse_weight(lines: list[str]) -> tuple[str | None, float | None, str | None]:
    for line in lines:
        parts = line.split()
        if len(parts) >= 3 and parts[0] in {"S", "SI", "SX", "SXI", "X"} and parts[1] in {
            "S",
            "D",
            "I",
            "+",
            "-",
        }:
            try:
                value = float(parts[2])
            except ValueError:
                continue
            unit = parts[3] if len(parts) > 3 else None
            return parts[1], value, unit
        if len(parts) == 2 and parts[0] in {"S", "SI", "X"} and parts[1] in {"I", "+", "-"}:
            return parts[1], None, None
    return None, None, None


def sample_weights(fd: int, cmd: str, n: int, gap: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(n):
        lines = xfer(fd, cmd, wait=1.0)
        status, value, unit = parse_weight(lines)
        out.append({"i": i, "raw": lines, "status": status, "value": value, "unit": unit})
        time.sleep(gap)
    return out


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    vals = [s["value"] for s in samples if isinstance(s.get("value"), float)]
    statuses = [s["status"] for s in samples if s.get("status")]
    summary: dict[str, Any] = {
        "n": len(samples),
        "n_numeric": len(vals),
        "statuses": sorted(set(statuses)),
        "values": vals,
    }
    if vals:
        summary["min"] = min(vals)
        summary["max"] = max(vals)
        summary["span"] = max(vals) - min(vals)
        summary["mean"] = statistics.fmean(vals)
        if len(vals) > 1:
            summary["stdev"] = statistics.pstdev(vals)
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="YKV USB signal diagnostic")
    p.add_argument("--label", default="unknown", help="physical state: empty|50kg|other")
    p.add_argument("--samples", type=int, default=8)
    p.add_argument("--port", default="")
    args = p.parse_args()

    ports = [args.port] if args.port else sorted(glob.glob("/dev/cu.usbserial*"))
    if not ports or not ports[0]:
        print("NO_USB_SERIAL")
        return 2
    port = ports[0]
    print(f"PORT={port} label={args.label}")

    fd = open_serial(port)
    try:
        identity: dict[str, Any] = {}
        for cmd, wait in [("@", 1.0), ("I1", 1.0), ("I2", 1.0), ("I3", 1.0), ("I4", 1.0)]:
            identity[cmd] = xfer(fd, cmd, wait)
        print("IDENTITY", identity)

        cfg: dict[str, Any] = {}
        for cmd in ("JDC", "JDD", "JDO", "JDA", "JDF"):
            cfg[cmd] = xfer(fd, cmd, 1.2)
        print("CONFIG", cfg)

        print("SI_SUMMARY", summarize(sample_weights(fd, "SI", args.samples, 0.15)))
        print("SXI_SUMMARY", summarize(sample_weights(fd, "SXI", args.samples, 0.15)))

        sad_vals: list[int] = []
        for _ in range(args.samples):
            for line in xfer(fd, "SAD", 1.0):
                parts = line.split()
                if len(parts) >= 3 and parts[0] == "SAD" and parts[1] == "A":
                    sad_vals.append(int(parts[2]))
                    break
            time.sleep(0.12)
        sad_sum: dict[str, Any] = {"n": len(sad_vals), "values": sad_vals}
        if sad_vals:
            sad_sum["min"] = min(sad_vals)
            sad_sum["max"] = max(sad_vals)
            sad_sum["span"] = max(sad_vals) - min(sad_vals)
            sad_sum["mean"] = statistics.fmean(sad_vals)
            if len(sad_vals) > 1:
                sad_sum["stdev"] = statistics.pstdev(sad_vals)
        print("SAD_SUMMARY", sad_sum)
    finally:
        os.close(fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

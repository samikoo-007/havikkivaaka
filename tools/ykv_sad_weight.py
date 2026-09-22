#!/usr/bin/env python3
"""Read / capture YKV weight via SAD + data/ykv_sad_cal.json (USB serial)."""

from __future__ import annotations

import argparse
import glob
import json
import os
import select
import sys
import termios
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAL = ROOT / "data" / "ykv_sad_cal.json"
BAUD = termios.B9600


def load_cal(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for k in ("sad_empty", "sad_at_ref", "ref_kg"):
        if k not in data:
            raise SystemExit(f"cal missing {k}: {path}")
    return data


def kg_from_sad(sad: int, cal: dict) -> float:
    span = float(cal["sad_at_ref"]) - float(cal["sad_empty"])
    if abs(span) < 1:
        raise SystemExit("invalid cal span")
    return (sad - float(cal["sad_empty"])) / span * float(cal["ref_kg"])


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


def xfer_serial(fd: int, cmd: str, wait: float = 1.2) -> list[str]:
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


def parse_sad(lines: list[str]) -> int | None:
    for line in lines:
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "SAD" and parts[1] == "A":
            return int(parts[2])
    return None


def mean_sad(fd: int, n: int) -> int:
    sads: list[int] = []
    for _ in range(n):
        ad = parse_sad(xfer_serial(fd, "SAD", 1.0))
        if ad is not None:
            sads.append(ad)
            print(f"SAD={ad}")
        time.sleep(0.15)
    if not sads:
        raise SystemExit("NO_SAD")
    return int(round(sum(sads) / len(sads)))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cal", type=Path, default=DEFAULT_CAL)
    p.add_argument("--samples", type=int, default=5)
    p.add_argument("--port", default="")
    p.add_argument(
        "--capture",
        choices=("empty", "ref"),
        help="write SAD into cal file: empty=platform unloaded; ref=known weight on pan",
    )
    p.add_argument("--ref-kg", type=float, default=50.0, help="with --capture ref")
    args = p.parse_args()

    ports = [args.port] if args.port else sorted(glob.glob("/dev/cu.usbserial*"))
    if not ports or not ports[0]:
        print("NO_USB_SERIAL", file=sys.stderr)
        return 2
    fd = open_serial(ports[0])
    try:
        if args.capture:
            mean_ad = mean_sad(fd, args.samples)
            cal: dict = {}
            if args.cal.is_file():
                try:
                    cal = json.loads(args.cal.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    cal = {}
            if args.capture == "empty":
                cal["sad_empty"] = mean_ad
                print(f"WROTE sad_empty={mean_ad} → {args.cal}")
            else:
                cal["sad_at_ref"] = mean_ad
                cal["ref_kg"] = float(args.ref_kg)
                print(f"WROTE sad_at_ref={mean_ad} ref_kg={args.ref_kg} → {args.cal}")
            if "sad_empty" not in cal or "sad_at_ref" not in cal or "ref_kg" not in cal:
                print("NOTE: cal incomplete until both --capture empty and --capture ref are done")
            args.cal.parent.mkdir(parents=True, exist_ok=True)
            args.cal.write_text(json.dumps(cal, indent=2) + "\n", encoding="utf-8")
            return 0

        cal = load_cal(args.cal)
        sads: list[int] = []
        for _ in range(args.samples):
            ad = parse_sad(xfer_serial(fd, "SAD", 1.0))
            if ad is not None:
                sads.append(ad)
                print(f"SAD={ad}  kg={kg_from_sad(ad, cal):.2f}")
            time.sleep(0.15)
        if not sads:
            print("NO_SAD")
            return 3
        mean_ad = sum(sads) / len(sads)
        print(f"MEAN_AD={mean_ad:.0f} MEAN_KG={kg_from_sad(int(mean_ad), cal):.2f}")
        return 0
    finally:
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())

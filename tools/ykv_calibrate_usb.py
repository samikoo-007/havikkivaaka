#!/usr/bin/env python3
"""One-shot YKV USB calibration: zero → wait for load → save → verify."""

from __future__ import annotations

import argparse
import glob
import os
import select
import termios
import time

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


def xfer(fd: int, cmd: str, wait: float = 1.5) -> list[str]:
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


def sad_once(fd: int) -> int | None:
    lines = xfer(fd, "SAD", 1.0)
    for line in lines:
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "SAD" and parts[1] == "A":
            try:
                return int(parts[2])
            except ValueError:
                return None
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adj-kg", type=float, default=50.0)
    p.add_argument("--wait-s", type=float, default=90.0)
    p.add_argument("--delta-min", type=int, default=400_000, help="min |SAD-SAD0| to detect load")
    p.add_argument(
        "--empty-max-ad",
        type=int,
        default=8_500_000,
        help="refuse zero if SAD empty is above this",
    )
    p.add_argument("--capacity-kg", type=float, default=50.0)
    p.add_argument(
        "--mode",
        choices=("jag", "jal"),
        default="jal",
        help="jag=JAGZ/JAGL; jal=JALZ/JALL",
    )
    p.add_argument("--stable-n", type=int, default=5)
    p.add_argument("--stable-band", type=int, default=500)
    args = p.parse_args()

    ports = sorted(glob.glob("/dev/cu.usbserial*"))
    if not ports:
        print("NO_USB_SERIAL")
        return 2
    port = ports[0]
    print(
        f"PORT={port} mode={args.mode} adj={args.adj_kg} kg capacity={args.capacity_kg} kg wait={args.wait_s}s",
        flush=True,
    )

    fd = open_serial(port)
    try:
        cap = args.capacity_kg
        overload = round(cap + 0.4, 1)
        for cmd, w in [
            ("@", 1.0),
            ("U kg", 1.2),
            (f"JDC {cap:.1f} kg", 1.2),
            ("JDD 0.2 kg", 1.2),
            (f"JDO {overload:.1f} kg", 1.2),
            (f"JDA {args.adj_kg:.1f} kg", 1.2),
            (f"JDL 0 {args.adj_kg:.1f} kg", 1.2),
            ("JDA", 1.0),
            ("JDC", 1.0),
            ("SI", 1.2),
        ]:
            print(f"{cmd:20} => {xfer(fd, cmd, w)}", flush=True)

        ad0 = sad_once(fd)
        print(f"SAD empty = {ad0}", flush=True)
        if ad0 is None:
            print("FAIL no SAD empty")
            return 3
        if ad0 > args.empty_max_ad:
            print(
                f"FAIL scale not empty enough: SAD={ad0} > empty_max_ad={args.empty_max_ad}",
                flush=True,
            )
            return 7

        zero_cmd = "JALZ" if args.mode == "jal" else "JAGZ"
        load_cmd = "JALL" if args.mode == "jal" else "JAGL"
        zero = xfer(fd, zero_cmd, 4.0)
        print(f"{zero_cmd} => {zero}", flush=True)
        if not any(f"{zero_cmd} A" in x for x in zero):
            print(f"FAIL {zero_cmd} not accepted")
            return 4

        print("", flush=True)
        print("=== NYT: laita KAIKKI säätöpainot alustalle ===", flush=True)
        print(f"=== Yhteensä {args.adj_kg:.0f} kg (esim. 10 + 20 + 20 kg) ===", flush=True)
        print("=== Älä poista painoja. Odota kunnes lukema rauhoittuu. ===", flush=True)
        print("", flush=True)

        print(
            f"WAITING up to {args.wait_s:.0f}s for STABLE load "
            f"(SAD delta >= {args.delta_min})...",
            flush=True,
        )
        loaded_ad: int | None = None
        recent: list[int] = []
        t_end = time.monotonic() + args.wait_s
        while time.monotonic() < t_end:
            ad = sad_once(fd)
            if ad is not None:
                delta = abs(ad - ad0)
                print(f"  SAD={ad} delta={delta}", flush=True)
                if delta >= args.delta_min:
                    recent.append(ad)
                    if len(recent) > args.stable_n:
                        recent = recent[-args.stable_n :]
                    if len(recent) >= args.stable_n and (max(recent) - min(recent)) <= args.stable_band:
                        loaded_ad = int(sum(recent) / len(recent))
                        break
                else:
                    recent = []
            time.sleep(0.35)

        if loaded_ad is None:
            print("FAIL timeout waiting for stable load")
            xfer(fd, "@", 1.0)
            return 5

        print(f"STABLE LOAD SAD≈{loaded_ad}", flush=True)
        load = xfer(fd, load_cmd, 4.0)
        print(f"{load_cmd} => {load}", flush=True)
        if args.mode == "jal" and any("JALL B" in x for x in load):
            print(
                "FAIL JALL requests another linearization weight "
                f"({load}) but we only have {args.adj_kg} kg. "
                "Re-run with --capacity-kg equal to adj weight.",
                flush=True,
            )
            xfer(fd, "@", 1.0)
            return 8

        jas = xfer(fd, "JAS", 4.0)
        print(f"JAS  => {jas}", flush=True)
        for cmd, w in [("SI", 2.0), ("S", 2.5), ("SAD", 1.2), ("JDA", 1.0), ("JDC", 1.0), ("I2", 1.0)]:
            print(f"{cmd:8} => {xfer(fd, cmd, w)}", flush=True)

        ok = any("JAS A" in x for x in jas)
        print("OK" if ok else "FAIL", flush=True)
        return 0 if ok else 6
    finally:
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())

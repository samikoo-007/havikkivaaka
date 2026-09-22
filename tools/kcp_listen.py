#!/usr/bin/env python3
"""Read-only KCP listen for YKV-02 (direct Ethernet or LAN).

Does not send T/Z. Default: try SIR stream, fall back to SI poll.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kcp import KcpClient, KcpError, WEIGHT_RE  # noqa: E402

DEFAULT_HOST = "192.168.50.11"
DEFAULT_PORT = 23


def _ts() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _parse(line: str) -> dict:
    raw = line.strip()
    rec: dict = {"ts": _ts(), "raw": raw, "status": None, "value": None, "unit": None}
    m = WEIGHT_RE.match(raw)
    if m:
        rec["status"] = m.group("status")
        rec["unit"] = m.group("unit")
        try:
            rec["value"] = float(m.group("value").strip())
        except ValueError:
            rec["value"] = None
        return rec
    parts = raw.split()
    if len(parts) >= 2:
        rec["status"] = parts[1]
    return rec


def _emit(rec: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(rec, ensure_ascii=True), flush=True)
        return
    extra = ""
    if rec["value"] is not None:
        extra = f"  status={rec['status']}  value={rec['value']}  unit={rec['unit']}"
    elif rec["status"]:
        extra = f"  status={rec['status']}"
    print(f"{rec['ts']}  {rec['raw']}{extra}", flush=True)


def _connect_with_retry(host: str, port: int, timeout: float, wait_s: float) -> KcpClient:
    deadline = time.monotonic() + wait_s
    last: Exception | None = None
    while time.monotonic() < deadline:
        client = KcpClient(host, port, timeout=timeout)
        try:
            client.connect()
            return client
        except OSError as e:
            last = e
            time.sleep(0.5)
    raise ConnectionError(last or "connect failed")


def _looks_like_reject(line: str) -> bool:
    s = line.strip().upper()
    if s == "ES":
        return True
    parts = s.split()
    return len(parts) >= 2 and parts[0] in {"SIR", "S"} and parts[1] in {"L", "I", "ES"}


def listen(args: argparse.Namespace) -> int:
    stop = False

    def _stop(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    print(
        f"KCP listen host={args.host}:{args.port} mode={args.mode} "
        f"(read-only, Ctrl+C to stop)",
        flush=True,
    )
    client = _connect_with_retry(args.host, args.port, args.timeout, args.wait_s)
    end = None if args.duration <= 0 else time.monotonic() + args.duration
    mode = args.mode

    try:
        if args.i1:
            try:
                info = client.cmd("I1")
                print(f"I1 {info}", flush=True)
            except (KcpError, TimeoutError, OSError) as e:
                print(f"I1 skipped: {e}", flush=True)

        if mode == "auto":
            client.send_no_reply("SIR")
            try:
                first = client.readline(timeout=max(args.timeout, 2.0))
            except TimeoutError:
                print("SIR produced no line — falling back to SI poll", flush=True)
                mode = "poll"
            else:
                if _looks_like_reject(first):
                    print(f"SIR rejected ({first!r}) — falling back to SI poll", flush=True)
                    mode = "poll"
                else:
                    mode = "sir"
                    _emit(_parse(first), args.json)

        if mode == "sir":
            idle = max(args.timeout, 3.0)
            while not stop and (end is None or time.monotonic() < end):
                try:
                    line = client.readline(timeout=idle)
                except TimeoutError:
                    print(f"{_ts()}  (no SIR line for {idle:.0f}s)", flush=True)
                    continue
                _emit(_parse(line), args.json)
        else:
            while not stop and (end is None or time.monotonic() < end):
                try:
                    line = client.cmd("SI")
                    _emit(_parse(line), args.json)
                except TimeoutError:
                    print(f"{_ts()}  SI timeout", flush=True)
                except KcpError as e:
                    print(f"{_ts()}  SI error: {e}", flush=True)
                    return 1
                if stop:
                    break
                time.sleep(args.interval)
        return 0
    finally:
        try:
            client.send_no_reply("@")
            time.sleep(0.1)
        except (KcpError, OSError, TimeoutError):
            pass
        client.close()
        print("KCP listen stopped", flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Read-only YKV-02 KCP listen")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--wait-s", type=float, default=20.0, help="TCP connect retry budget")
    p.add_argument("--interval", type=float, default=0.25, help="SI poll interval")
    p.add_argument("--duration", type=float, default=0, help="Stop after N seconds (0=until signal)")
    p.add_argument(
        "--mode",
        choices=["auto", "sir", "poll"],
        default="auto",
        help="auto=SIR then SI poll; sir=stream; poll=SI loop",
    )
    p.add_argument("--json", action="store_true")
    p.add_argument("--i1", action="store_true", help="Query I1 once after connect")
    p.add_argument("--once", action="store_true", help="Single SI then exit")
    args = p.parse_args(argv)

    if args.once:
        try:
            with KcpClient(args.host, args.port, args.timeout) as c:
                rec = _parse(c.cmd("SI"))
                _emit(rec, args.json)
            return 0
        except (OSError, KcpError, TimeoutError) as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1

    try:
        return listen(args)
    except (OSError, KcpError, TimeoutError, ConnectionError) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

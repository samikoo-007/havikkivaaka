#!/usr/bin/env python3
"""Tiny KCP TCP mock for offline tests without YKV hardware.

Default KCP port 2323 (port 23 needs root). Optional HTTP control port
lets you SET/ADD weight via curl while the mock is running.
"""

from __future__ import annotations

import argparse
import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

WEIGHT = 0.0
TARE = 0.0
LOCK = threading.Lock()


def fmt_weight(net: float) -> str:
    # Right-align-ish 10-char field as in KCP examples
    s = f"{net:.2f}"
    return f"{s:>10}"


def get_net() -> float:
    with LOCK:
        return WEIGHT - TARE


def set_weight(grams: float) -> float:
    global WEIGHT
    with LOCK:
        WEIGHT = float(grams)
        return WEIGHT


def add_weight(delta: float) -> float:
    global WEIGHT
    with LOCK:
        WEIGHT += float(delta)
        return WEIGHT


class KcpHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        global WEIGHT, TARE
        peer = self.client_address[0]
        print(f"connect {peer}", flush=True)
        while True:
            line = self.rfile.readline()
            if not line:
                break
            cmd = line.decode("ascii", errors="replace").strip()
            print(f"← {cmd!r}", flush=True)
            with LOCK:
                if cmd == "SI":
                    net = WEIGHT - TARE
                    st = "S"
                    resp = f"S {st} {fmt_weight(net)} g"
                elif cmd == "S":
                    net = WEIGHT - TARE
                    resp = f"S S {fmt_weight(net)} g"
                elif cmd == "T":
                    TARE = WEIGHT
                    resp = "T A"
                elif cmd == "Z":
                    TARE = 0.0
                    WEIGHT = 0.0
                    resp = "Z A"
                elif cmd == "@":
                    resp = ""
                elif cmd == "I1":
                    resp = 'I1 A "KCP-MOCK 1.0"'
                elif cmd.startswith("SIR"):
                    # one sample then stop (full stream not needed for smoke)
                    net = WEIGHT - TARE
                    resp = f"S D {fmt_weight(net)} g"
                else:
                    resp = "ES"
            if resp:
                out = resp + "\r\n"
                self.wfile.write(out.encode("ascii"))
                self.wfile.flush()
                print(f"→ {resp}", flush=True)


class ControlHandler(BaseHTTPRequestHandler):
    """HTTP control: GET /weight, POST /set, POST /add, POST /zero."""

    def log_message(self, fmt: str, *args) -> None:
        print(f"[control] {self.address_string()} {fmt % args}", flush=True)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_grams(self) -> float | None:
        """Parse grams from JSON body, form body, or ?grams= query."""
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b""
        ctype = (self.headers.get("Content-Type") or "").lower()
        qs = parse_qs(urlparse(self.path).query)

        if "grams" in qs and qs["grams"]:
            try:
                return float(qs["grams"][0])
            except ValueError:
                return None

        if not raw:
            return None

        text = raw.decode("utf-8", errors="replace").strip()
        if "json" in ctype or (text.startswith("{") and text.endswith("}")):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return None
            if "grams" in data:
                return float(data["grams"])
            if "add" in data:
                return float(data["add"])
            if "delta" in data:
                return float(data["delta"])
            return None

        # application/x-www-form-urlencoded or plain "1234" / "grams=1234"
        if "=" in text:
            form = parse_qs(text)
            for key in ("grams", "add", "delta", "weight"):
                if key in form and form[key]:
                    return float(form[key][0])
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/", "/weight", "/status"):
            with LOCK:
                gross = WEIGHT
                tare = TARE
            self._json(
                200,
                {
                    "weight_g": gross,
                    "tare_g": tare,
                    "net_g": gross - tare,
                },
            )
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/set", "/weight"):
            grams = self._read_grams()
            if grams is None:
                self._json(400, {"error": "missing grams (JSON, form, or query)"})
                return
            new = set_weight(grams)
            print(f"[control] SET weight={new:.2f} g", flush=True)
            self._json(200, {"ok": True, "weight_g": new, "net_g": get_net()})
            return
        if path == "/add":
            delta = self._read_grams()
            if delta is None:
                self._json(400, {"error": "missing grams/delta (JSON, form, or query)"})
                return
            new = add_weight(delta)
            print(f"[control] ADD {delta:+.2f} → weight={new:.2f} g", flush=True)
            self._json(200, {"ok": True, "weight_g": new, "net_g": get_net()})
            return
        if path == "/zero":
            with LOCK:
                global WEIGHT, TARE
                WEIGHT = 0.0
                TARE = 0.0
            print("[control] ZERO", flush=True)
            self._json(200, {"ok": True, "weight_g": 0.0, "net_g": 0.0})
            return
        self._json(404, {"error": "not found; use POST /set /add /zero"})


def start_control(host: str, port: int) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), ControlHandler)
    t = threading.Thread(target=httpd.serve_forever, name="kcp-control", daemon=True)
    t.start()
    return httpd


def main() -> int:
    global WEIGHT
    p = argparse.ArgumentParser(description="KERN KCP TCP mock scale")
    p.add_argument("--host", default="0.0.0.0", help="KCP bind address")
    p.add_argument("--port", type=int, default=2323, help="KCP TCP port (23 needs root)")
    p.add_argument(
        "--control-port",
        type=int,
        default=2324,
        help="HTTP control port (0=disable). SET/ADD weight via curl",
    )
    p.add_argument("--control-host", default=None, help="HTTP bind (default: same as --host)")
    p.add_argument("--weight", type=float, default=0.0, help="Initial platform weight (g)")
    args = p.parse_args()
    WEIGHT = args.weight

    control_host = args.control_host if args.control_host is not None else args.host

    try:
        socketserver.ThreadingTCPServer.allow_reuse_address = True
        server = socketserver.ThreadingTCPServer((args.host, args.port), KcpHandler)
    except PermissionError:
        print("Port privileged — try: python3 tools/kcp_mock.py --port 2323")
        return 1
    except OSError as e:
        print(f"KCP bind failed {args.host}:{args.port}: {e}")
        return 1

    control = None
    if args.control_port and args.control_port > 0:
        try:
            control = start_control(control_host, args.control_port)
        except OSError as e:
            print(f"Control bind failed {control_host}:{args.control_port}: {e}")
            server.server_close()
            return 1

    print(f"KCP mock on {args.host}:{args.port}  (Ctrl+C to stop)", flush=True)
    if control is not None:
        print(
            f"HTTP control on {control_host}:{args.control_port}  "
            f"(GET /weight, POST /set /add /zero)",
            flush=True,
        )
        print(
            f"  curl -s -X POST http://127.0.0.1:{args.control_port}/set "
            f'-H "Content-Type: application/json" -d \'{{"grams": 450}}\'',
            flush=True,
        )
    print(
        f"Test: python3 tools/kcp_client.py --host 127.0.0.1 --port {args.port} si",
        flush=True,
    )

    try:
        with server:
            server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping…", flush=True)
    finally:
        if control is not None:
            control.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

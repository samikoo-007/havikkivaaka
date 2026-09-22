"""HTTP kiosk backend + scale polling loop (stdlib only)."""

from __future__ import annotations

import argparse
import errno
import json
import logging
import os
import socket
import threading
import time
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.config import AppConfig, ConfigStore
from app.kcp import KcpClient, MockScale, grams_from_sad, load_sad_cal
from app.state_machine import StateMachine
from app.storage import Storage

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
STATIC = ROOT / "static"
EXPORTS = DATA / "exports"
LOG = logging.getLogger("havikkivaaka")

# Poll when connected vs exponential backoff while YKV is absent (lab UX).
POLL_OK_S = 0.25
POLL_FAIL_MIN_S = 1.0
POLL_FAIL_MAX_S = 15.0


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def friendly_scale_error(exc: BaseException) -> str:
    """User-facing Finnish message — never raw errno / OSError text in the kiosk."""
    if isinstance(exc, TimeoutError):
        return "YKV ei vastaa"
    if isinstance(exc, ConnectionRefusedError):
        return "Ei yhteyttä YKV:hen"
    if isinstance(exc, (socket.gaierror, ConnectionResetError, BrokenPipeError)):
        return "Ei yhteyttä YKV:hen"
    if isinstance(exc, OSError):
        en = getattr(exc, "errno", None)
        if en in (
            errno.EHOSTUNREACH,  # 113 No route to host
            errno.ENETUNREACH,
            errno.ECONNREFUSED,
            errno.ECONNRESET,
            errno.ENETDOWN,
            errno.EHOSTDOWN,
            errno.ETIMEDOUT,
        ):
            return "Ei yhteyttä YKV:hen"
        msg = str(exc).lower()
        if "no route to host" in msg or "network is unreachable" in msg:
            return "Ei yhteyttä YKV:hen"
        if "timed out" in msg or "timeout" in msg:
            return "YKV ei vastaa"
    return "Odottaa vaakaa"


class App:
    def __init__(self, mock: bool, host: str, port: int):
        self.mock = mock
        self.host = host
        self.port = port
        DATA.mkdir(parents=True, exist_ok=True)
        EXPORTS.mkdir(parents=True, exist_ok=True)
        self.config_store = ConfigStore(DATA / "config.json")
        self.cfg = self.config_store.get()
        self.storage = Storage(DATA / "events.sqlite3")
        self.scale: KcpClient | MockScale
        if mock:
            self.scale = MockScale()
        else:
            self.scale = KcpClient(host, port)
        self.machine = StateMachine(
            threshold_g=self._cfg_float("threshold_g", "HAVIKKI_THRESHOLD_G", 300),
            settle_s=self._cfg_float("settle_s", "HAVIKKI_SETTLE_S", 10),
            empty_g=self._cfg_float("empty_g", "HAVIKKI_EMPTY_G", 20),
            empty_away_s=self._cfg_float("empty_away_s", "HAVIKKI_EMPTY_AWAY_S", 20),
            start_delta_g=float(self.cfg.start_delta_g),
            feedback_show_s=float(self.cfg.feedback_show_s),
            quantize_g=float(getattr(self.cfg, "quantize_g", 2.0)),
            empty_bin_g=float(self.cfg.empty_bin_g),
            empty_bin_tolerance_g=float(self.cfg.empty_bin_tolerance_g),
            on_event=self._on_event,
            on_auto_tare=self._on_auto_tare,
        )
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._stats_day = date.today().isoformat()
        self._fail_delay_s = POLL_FAIL_MIN_S
        self._last_logged_error: str | None = None
        self._last_poll_ok_at: str | None = None
        self._sad_cal = None if mock else load_sad_cal()
        # SAD soft-tare: subtract from cal grams (KCP T does not affect SAD path).
        self._sad_tare_g = 0.0
        self._sad_raw_g = 0.0  # last grams before soft-tare (for Taara)
        if self._sad_cal:
            LOG.info(
                "weight source=SAD (SI cal broken on this YKV); empty=%s ref=%s@%skg",
                int(self._sad_cal["sad_empty"]),
                int(self._sad_cal["sad_at_ref"]),
                self._sad_cal["ref_kg"],
            )
        self._refresh_day()
        if self.cfg.prefill_waste_g > 0:
            self.machine.apply_baseline(self.cfg.prefill_waste_g)

    def _cfg_float(self, attr: str, env_name: str, default: float) -> float:
        """Env overrides file on first boot (lab CLI); file wins after admin save."""
        if env_name in os.environ and os.environ[env_name].strip():
            try:
                return float(os.environ[env_name])
            except ValueError:
                pass
        return float(getattr(self.cfg, attr, default))

    def apply_config(self, cfg: AppConfig) -> None:
        """Hot-reload machine params from saved config (lock held by caller)."""
        self.cfg = cfg
        self.machine.apply_runtime_config(
            threshold_g=cfg.threshold_g,
            settle_s=cfg.settle_s,
            empty_g=cfg.empty_g,
            empty_away_s=cfg.empty_away_s,
            start_delta_g=cfg.start_delta_g,
            feedback_show_s=cfg.feedback_show_s,
            quantize_g=cfg.quantize_g,
            empty_bin_g=cfg.empty_bin_g,
            empty_bin_tolerance_g=cfg.empty_bin_tolerance_g,
        )
        LOG.info(
            "config applied threshold=%.0f settle=%.1f quantize=%.0f theme=%s",
            cfg.threshold_g,
            cfg.settle_s,
            cfg.quantize_g,
            cfg.theme,
        )

    def update_config(self, patch: dict) -> AppConfig:
        with self._lock:
            cfg = self.config_store.update(patch)
            self.apply_config(cfg)
            return cfg

    def get_config(self) -> dict:
        with self._lock:
            return self.cfg.to_dict()

    def _refresh_day(self) -> None:
        stats = self.storage.day_stats()
        self.machine.state.day_count = stats.count
        self.machine.state.day_total_g = stats.total_g
        self.machine.state.day_avg_g = stats.avg_g
        self.machine.state.day_max_g = stats.max_g

    def _maybe_rollover_day(self) -> None:
        """When calendar day changes, reload stats (new day starts at zero)."""
        today = date.today().isoformat()
        if self._stats_day != today:
            LOG.info("day rollover %s → %s", self._stats_day, today)
            self._stats_day = today
            self._refresh_day()

    def _on_event(self, grams: float, feedback: str) -> None:
        self.storage.add_event(grams, feedback)
        self._refresh_day()
        LOG.info("event %.1fg %s", grams, feedback)

    def _apply_sad_soft_tare(self) -> None:
        """Zero current SAD reading in software (lock held). No-op if not SAD mode."""
        if not self._sad_cal:
            return
        self._sad_tare_g = float(self._sad_raw_g)
        LOG.info("SAD soft-tare offset=%.1fg", self._sad_tare_g)

    def _on_auto_tare(self) -> None:
        """Called from state machine (lock already held) when empty bin returns."""
        try:
            self._apply_sad_soft_tare()
            resp = self.scale.tare()
            LOG.info("auto-tare after emptying: %s", resp)
            self.machine.state.error = None
        except Exception as e:  # noqa: BLE001 — keep kiosk alive
            LOG.warning("auto-tare failed: %s", e)
            self.machine.state.error = friendly_scale_error(e)

    def snapshot(self) -> dict:
        with self._lock:
            self._maybe_rollover_day()
            cfg = self.cfg
            return self.machine.to_dict() | {
                "mode": "mock" if self.mock else "live",
                "theme": cfg.theme,
                "site_id": cfg.site_id,
                "config": {
                    "threshold_g": cfg.threshold_g,
                    "settle_s": cfg.settle_s,
                    "feedback_show_s": cfg.feedback_show_s,
                    "empty_g": cfg.empty_g,
                    "empty_away_s": cfg.empty_away_s,
                    "quantize_g": cfg.quantize_g,
                    "empty_bin_g": cfg.empty_bin_g,
                    "theme": cfg.theme,
                    "site_id": cfg.site_id,
                    "feedback_smile_text": cfg.feedback_smile_text,
                    "feedback_frown_text": cfg.feedback_frown_text,
                },
            }

    def health(self) -> dict:
        with self._lock:
            s = self.machine.state
            return {
                "ok": True,
                "mode": "mock" if self.mock else "live",
                "connected": s.connected,
                "error": s.error,
                "phase": s.phase.value,
                "last_poll_ok_at": self._last_poll_ok_at,
                "last_event_g": s.last_event_g,
                "site_id": self.cfg.site_id,
                "theme": self.cfg.theme,
            }

    def tare(self) -> str:
        """Tare current weight as empty bin (not waste); reset machine to idle zero."""
        with self._lock:
            self._apply_sad_soft_tare()
            resp = self.scale.tare()
            self.machine.apply_manual_tare_reset()
            return resp

    def zero(self) -> str:
        """Scale hardware zero/tare baseline (not day counters)."""
        with self._lock:
            # SAD: soft-tare is the real zero; Z still sent for SI/mock compatibility.
            self._apply_sad_soft_tare()
            resp = self.scale.zero()
            self.machine.apply_manual_tare_reset()
            return resp

    def set_baseline_current(self) -> dict:
        """Treat current scale reading as baseline (pre-filled bin); no waste event."""
        with self._lock:
            w = float(self.machine.state.weight_g)
            self.machine.apply_baseline(w)
            LOG.info("manual baseline set to %.1fg (no waste count)", w)
            return {"baseline_g": round(w, 1)}

    def export_day_files(self, day: str | None = None) -> dict:
        """Write CSV + JSON under data/exports/; return paths and summary."""
        day = day or date.today().isoformat()
        EXPORTS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = f"day-{day}-{stamp}"
        csv_path = EXPORTS / f"{base}.csv"
        json_path = EXPORTS / f"{base}.json"
        with self._lock:
            cfg = self.cfg
            csv_body = self.storage.export_day_csv(day)
            json_body = self.storage.export_day_json(
                day,
                site_id=cfg.site_id,
                co2_factor_kg_per_kg=cfg.co2_factor_kg_per_kg,
            )
            stats = self.storage.day_stats(day)
        csv_path.write_text(csv_body, encoding="utf-8")
        json_path.write_text(json_body, encoding="utf-8")
        LOG.info("exported day %s → %s , %s", day, csv_path.name, json_path.name)
        return {
            "day": day,
            "csv": str(csv_path),
            "json": str(json_path),
            "count": stats.count,
            "total_g": round(stats.total_g, 1),
        }

    def day_csv_text(self, day: str | None = None) -> str:
        return self.storage.export_day_csv(day)

    def day_json_text(self, day: str | None = None) -> str:
        with self._lock:
            cfg = self.cfg
        return self.storage.export_day_json(
            day,
            site_id=cfg.site_id,
            co2_factor_kg_per_kg=cfg.co2_factor_kg_per_kg,
        )

    def reset_day(self, *, export_first: bool | None = None) -> dict:
        """Clear today's events; optionally export CSV+JSON first."""
        with self._lock:
            do_export = (
                self.cfg.export_before_reset
                if export_first is None
                else bool(export_first)
            )
            day = date.today().isoformat()
            exported = None
        if do_export:
            exported = self.export_day_files(day)
        with self._lock:
            deleted = self.storage.clear_day()
            self._stats_day = date.today().isoformat()
            self._refresh_day()
            LOG.info("day stats reset (%s events deleted)", deleted)
            return {
                "deleted": deleted,
                "exported": exported,
                "day": {
                    "count": self.machine.state.day_count,
                    "total_g": self.machine.state.day_total_g,
                    "avg_g": self.machine.state.day_avg_g,
                    "max_g": self.machine.state.day_max_g,
                },
            }

    def demo_add(self, grams: float) -> None:
        if not isinstance(self.scale, MockScale):
            raise RuntimeError("demo add only in mock mode")
        with self._lock:
            self.scale.add_grams(grams)

    def demo_set(self, grams: float) -> None:
        if not isinstance(self.scale, MockScale):
            raise RuntimeError("demo set only in mock mode")
        with self._lock:
            self.scale.weight_g = grams

    def _switch_to_mock_fallback(self, reason: str) -> None:
        """Optional lab escape hatch — only when HAVIKKI_ALLOW_MOCK_FALLBACK=1."""
        if self.mock or not _env_truthy("HAVIKKI_ALLOW_MOCK_FALLBACK"):
            return
        LOG.warning("mock fallback enabled after scale failure: %s", reason)
        try:
            self.scale.close()
        except Exception:
            pass
        self.scale = MockScale()
        self.mock = True
        with self._lock:
            self.machine.state.connected = True
            self.machine.state.error = None

    def poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.scale.connected:
                    self.scale.connect()
                if self._sad_cal and isinstance(self.scale, KcpClient):
                    sad = self.scale.sad()
                    raw_g = grams_from_sad(sad, self._sad_cal)
                    status = "S"
                    with self._lock:
                        self._sad_raw_g = raw_g
                        value = raw_g - self._sad_tare_g
                        self.machine.state.connected = True
                        self.machine.state.error = None
                        stable = status == "S"
                        self.machine.update(value, stable=stable)
                        self._last_poll_ok_at = datetime.now(timezone.utc).isoformat()
                else:
                    status, value, _unit = self.scale.si()
                    with self._lock:
                        self.machine.state.connected = True
                        self.machine.state.error = None
                        if value is not None:
                            stable = status == "S"
                            self.machine.update(value, stable=stable)
                        self._last_poll_ok_at = datetime.now(timezone.utc).isoformat()
                self._fail_delay_s = POLL_FAIL_MIN_S
                self._last_logged_error = None
                time.sleep(POLL_OK_S)
            except Exception as e:  # noqa: BLE001 — keep kiosk alive
                friendly = friendly_scale_error(e)
                with self._lock:
                    self.machine.state.connected = False
                    self.machine.state.error = friendly
                # Log once per distinct OS error text to avoid journal spam.
                raw = str(e)
                if raw != self._last_logged_error:
                    LOG.warning("scale poll: %s → %s", raw, friendly)
                    self._last_logged_error = raw
                try:
                    self.scale.close()
                except Exception:
                    pass
                self._switch_to_mock_fallback(raw)
                if self.mock:
                    self._fail_delay_s = POLL_FAIL_MIN_S
                    continue
                delay = self._fail_delay_s
                self._fail_delay_s = min(POLL_FAIL_MAX_S, self._fail_delay_s * 2)
                time.sleep(delay)

    def stop(self) -> None:
        self._stop.set()
        try:
            self.scale.close()
        except Exception:
            pass


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            LOG.debug("%s - " + fmt, self.address_string(), *args)

        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _text(self, code: int, body: str, content_type: str, filename: str | None = None) -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if filename:
                self.send_header(
                    "Content-Disposition", f'attachment; filename="{filename}"'
                )
            self.end_headers()
            self.wfile.write(data)

        def _file(self, path: Path, content_type: str) -> None:
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json_body(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                data = {}
            return data if isinstance(data, dict) else {}

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)
            day = (qs.get("day") or [None])[0]

            if path in ("/", "/index.html"):
                self._file(STATIC / "index.html", "text/html; charset=utf-8")
            elif path in ("/admin", "/admin.html"):
                self._file(STATIC / "admin.html", "text/html; charset=utf-8")
            elif path == "/api/state":
                self._json(200, app.snapshot())
            elif path == "/api/config":
                self._json(200, {"ok": True, "config": app.get_config()})
            elif path == "/api/health":
                self._json(200, app.health())
            elif path == "/api/events":
                try:
                    limit = int((qs.get("limit") or ["100"])[0])
                    offset = int((qs.get("offset") or ["0"])[0])
                except ValueError:
                    limit, offset = 100, 0
                events = app.storage.list_events(day=day, limit=limit, offset=offset)
                stats = app.storage.day_stats(day)
                self._json(
                    200,
                    {
                        "ok": True,
                        "day": day or date.today().isoformat(),
                        "stats": {
                            "count": stats.count,
                            "total_g": round(stats.total_g, 1),
                            "avg_g": round(stats.avg_g, 1),
                            "max_g": round(stats.max_g, 1),
                            "smile_count": stats.smile_count,
                            "frown_count": stats.frown_count,
                        },
                        "events": events,
                    },
                )
            elif path == "/api/export/day.csv":
                d = day or date.today().isoformat()
                self._text(
                    200,
                    app.day_csv_text(d),
                    "text/csv; charset=utf-8",
                    filename=f"havikkivaaka-{d}.csv",
                )
            elif path == "/api/export/day.json":
                d = day or date.today().isoformat()
                self._text(
                    200,
                    app.day_json_text(d),
                    "application/json; charset=utf-8",
                    filename=f"havikkivaaka-{d}.json",
                )
            elif path.startswith("/static/"):
                rel = path[len("/static/") :]
                fp = STATIC / rel
                if fp.is_file():
                    ctype = "text/css" if fp.suffix == ".css" else "application/octet-stream"
                    if fp.suffix == ".html":
                        ctype = "text/html; charset=utf-8"
                    self._file(fp, ctype)
                else:
                    self.send_error(404)
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            data = self._read_json_body()

            try:
                if path == "/api/tare":
                    self._json(200, {"ok": True, "resp": app.tare()})
                elif path == "/api/zero":
                    # Scale hardware zero (kept for tools); UI Nollaa uses reset-day
                    self._json(200, {"ok": True, "resp": app.zero()})
                elif path == "/api/reset-day":
                    export_first = data.get("export_first")
                    if export_first is None:
                        export_first = None
                    else:
                        export_first = bool(export_first)
                    self._json(
                        200,
                        {"ok": True, **app.reset_day(export_first=export_first)},
                    )
                elif path == "/api/config":
                    cfg = app.update_config(data)
                    self._json(200, {"ok": True, "config": cfg.to_dict()})
                elif path == "/api/set-baseline":
                    self._json(200, {"ok": True, **app.set_baseline_current()})
                elif path == "/api/export/day":
                    # Save CSV+JSON to data/exports/ (admin "Vie raportti")
                    day = data.get("day")
                    result = app.export_day_files(day if isinstance(day, str) else None)
                    self._json(200, {"ok": True, **result})
                elif path == "/api/demo/add":
                    grams = float(data.get("grams", 100))
                    app.demo_add(grams)
                    self._json(200, {"ok": True})
                elif path == "/api/demo/set":
                    grams = float(data.get("grams", 0))
                    app.demo_set(grams)
                    self._json(200, {"ok": True})
                else:
                    self.send_error(404)
            except ValueError as e:
                self._json(400, {"ok": False, "error": str(e)})
            except Exception as e:  # noqa: BLE001
                self._json(400, {"ok": False, "error": str(e)})

    return Handler


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    p = argparse.ArgumentParser(description="Hävikkivaaka kiosk server")
    p.add_argument("--mock", action="store_true", help="In-process mock scale")
    p.add_argument("--host", default=os.environ.get("HAVIKKI_HOST", "192.168.50.11"))
    p.add_argument("--port", type=int, default=int(os.environ.get("HAVIKKI_PORT", "23")))
    p.add_argument("--http-host", default="0.0.0.0")
    p.add_argument("--http-port", type=int, default=8080)
    p.add_argument(
        "--settle-s",
        type=float,
        default=None,
        help="Override settle seconds (default 10; use 2 for quick demo)",
    )
    p.add_argument(
        "--empty-away-s",
        type=float,
        default=None,
        help="Seconds near-empty before tyhjennys/AWAY (default 20; use 3 for quick test)",
    )
    p.add_argument(
        "--empty-g",
        type=float,
        default=None,
        help="Absolute net ≤ this grams counts as off-scale / empty (default 20)",
    )
    args = p.parse_args(argv)

    use_mock = args.mock or _env_truthy("HAVIKKI_MOCK")
    if use_mock and not args.mock:
        LOG.info("HAVIKKI_MOCK set — starting in mock mode")
    app = App(mock=use_mock, host=args.host, port=args.port)
    if args.settle_s is not None:
        app.machine.settle_s = args.settle_s
    if args.empty_away_s is not None:
        app.machine.empty_away_s = args.empty_away_s
    if args.empty_g is not None:
        app.machine.empty_g = args.empty_g

    t = threading.Thread(target=app.poll_loop, name="scale-poll", daemon=True)
    t.start()

    handler = make_handler(app)
    httpd = ThreadingHTTPServer((args.http_host, args.http_port), handler)
    LOG.info(
        "Kiosk http://%s:%s  admin http://%s:%s/admin  mode=%s scale=%s:%s",
        args.http_host,
        args.http_port,
        args.http_host,
        args.http_port,
        "mock" if use_mock else "live",
        args.host,
        args.port,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOG.info("shutting down")
    finally:
        app.stop()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

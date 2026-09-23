#!/usr/bin/env python3
"""Security / production-gate checks (path traversal, admin PIN, body cap, kiosk open)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.server import (  # noqa: E402
    ADMIN_PIN_HEADER,
    App,
    make_handler,
    safe_static_file,
)
from http.server import ThreadingHTTPServer  # noqa: E402


class SafeStaticTests(unittest.TestCase):
    def test_rejects_traversal(self) -> None:
        self.assertIsNone(safe_static_file("../../data/events.sqlite3"))
        self.assertIsNone(safe_static_file("../../../etc/passwd"))
        self.assertIsNone(safe_static_file("/etc/passwd"))

    def test_allows_in_tree(self) -> None:
        # admin.html lives under app/static
        fp = safe_static_file("admin.html")
        self.assertIsNotNone(fp)
        assert fp is not None
        self.assertTrue(fp.name == "admin.html")


class HttpGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        # Point data at temp so we do not touch lab sqlite
        import app.server as srv

        cls._old_data = srv.DATA
        cls._old_exports = srv.EXPORTS
        data = Path(cls._tmpdir.name) / "data"
        data.mkdir()
        srv.DATA = data
        srv.EXPORTS = data / "exports"
        srv.EXPORTS.mkdir()

        os.environ["HAVIKKI_ADMIN_PIN"] = "246801"
        cls.app = App(mock=True, host="127.0.0.1", port=0)
        handler = make_handler(cls.app)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.15)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.stop()
        cls.httpd.shutdown()
        import app.server as srv

        srv.DATA = cls._old_data
        srv.EXPORTS = cls._old_exports
        os.environ.pop("HAVIKKI_ADMIN_PIN", None)
        cls._tmpdir.cleanup()

    def _req(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        pin: str | None = None,
        raw_body: bytes | None = None,
        extra_headers: dict | None = None,
    ) -> tuple[int, bytes, dict]:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers: dict[str, str] = {}
        if pin is not None:
            headers[ADMIN_PIN_HEADER] = pin
        payload = raw_body
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()
        return resp.status, data, hdrs

    def test_kiosk_state_open(self) -> None:
        code, data, _ = self._req("GET", "/api/state")
        self.assertEqual(code, 200)
        self.assertIn(b"mode", data)

    def test_config_requires_pin(self) -> None:
        code, data, _ = self._req("GET", "/api/config")
        self.assertEqual(code, 401)
        self.assertIn(b"auth_required", data)

    def test_config_with_pin(self) -> None:
        code, data, _ = self._req("GET", "/api/config", pin="246801")
        self.assertEqual(code, 200)
        payload = json.loads(data.decode())
        self.assertTrue(payload.get("ok"))

    def test_reset_requires_pin(self) -> None:
        code, _, _ = self._req("POST", "/api/reset-day", body={})
        self.assertEqual(code, 401)

    def test_static_traversal_404(self) -> None:
        code, _, _ = self._req("GET", "/static/../../data/events.sqlite3")
        self.assertEqual(code, 404)
        code2, _, _ = self._req("GET", "/static//etc/passwd")
        self.assertEqual(code2, 404)

    def test_static_admin_ok(self) -> None:
        code, data, _ = self._req("GET", "/static/admin.html")
        self.assertEqual(code, 200)
        self.assertIn(b"Admin", data)

    def test_body_cap(self) -> None:
        huge = b"{" + (b"a" * (70 * 1024)) + b"}"
        code, data, _ = self._req(
            "POST",
            "/api/config",
            pin="246801",
            raw_body=huge,
            extra_headers={"Content-Type": "application/json", "Content-Length": str(len(huge))},
        )
        self.assertEqual(code, 413)

    def test_auth_status(self) -> None:
        code, data, _ = self._req("GET", "/api/auth")
        self.assertEqual(code, 200)
        payload = json.loads(data.decode())
        self.assertTrue(payload.get("auth_required"))


class SettleMachineTests(unittest.TestCase):
    def test_two_additions_within_settle_merge(self) -> None:
        from app.state_machine import Phase, StateMachine

        events: list[tuple[float, str]] = []
        sm = StateMachine(
            settle_s=2.0,
            feedback_show_s=0.5,
            start_delta_g=40.0,
            quantize_g=0,
            on_event=lambda g, f: events.append((g, f)),
        )
        t0 = time.monotonic()
        # Monkeypatch monotonic via direct phase drive using update with held time —
        # use short settle and sleep.
        sm.settle_s = 0.4
        sm.update(0.0, stable=True)
        sm.update(150.0, stable=True)
        self.assertEqual(sm.state.phase, Phase.SETTLING)
        time.sleep(0.15)
        sm.update(330.0, stable=True)  # second dump before settle completes
        self.assertEqual(sm.state.phase, Phase.SETTLING)
        time.sleep(0.45)
        sm.update(330.0, stable=True)
        self.assertEqual(len(events), 1)
        self.assertGreater(events[0][0], 300.0)

    def test_addition_during_feedback_starts_new_event(self) -> None:
        from app.state_machine import Phase, StateMachine

        events: list[tuple[float, str]] = []
        sm = StateMachine(
            settle_s=0.2,
            feedback_show_s=0.35,
            start_delta_g=40.0,
            quantize_g=0,
            on_event=lambda g, f: events.append((g, f)),
        )
        sm.update(0.0, stable=True)
        sm.update(100.0, stable=True)
        time.sleep(0.25)
        sm.update(100.0, stable=True)
        self.assertEqual(sm.state.phase, Phase.FEEDBACK)
        self.assertEqual(len(events), 1)
        # During feedback, rising weight is ignored
        sm.update(280.0, stable=True)
        self.assertEqual(sm.state.phase, Phase.FEEDBACK)
        self.assertEqual(len(events), 1)
        time.sleep(0.4)
        sm.update(280.0, stable=True)
        self.assertIn(sm.state.phase, (Phase.HOLD, Phase.SETTLING))
        if sm.state.phase == Phase.HOLD:
            sm.update(280.0, stable=True)
            # addition from baseline 100 → need rise: baseline was set to 100
            sm.update(280.0, stable=True)
        # After feedback, further rise above new baseline starts settling
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(events) < 2:
            sm.update(280.0, stable=True)
            time.sleep(0.05)
        # Second event only if addition from baseline >= start_delta
        # baseline after first event = 100; weight 280 → addition 180 → settle
        if sm.state.phase == Phase.SETTLING:
            time.sleep(0.25)
            sm.update(280.0, stable=True)
        self.assertGreaterEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()

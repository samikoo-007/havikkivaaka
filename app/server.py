"""HTTP kiosk backend + scale polling loop (stdlib only)."""

from __future__ import annotations

import argparse
import errno
import hmac
import json
import logging
import os
import socket
import threading
import time
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from app.config import (
    AppConfig,
    ConfigStore,
    KITCHEN_SCALE_IDS,
    PLATE_SCALE_IDS,
    SCALE_LABELS,
    layout_diner_split,
    layout_kiosk_enabled,
)
from app.kcp import (
    KcpClient,
    MockScale,
    grams_from_sad,
    load_sad_cal_for_slot,
)
from app.state_machine import StateMachine
from app.storage import Storage

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
STATIC = ROOT / "static"
STATIC_ROOT = STATIC.resolve()
EXPORTS = DATA / "exports"
LOG = logging.getLogger("havikkivaaka")

# Poll when connected vs exponential backoff while YKV is absent (lab UX).
POLL_OK_S = 0.25
POLL_FAIL_MIN_S = 1.0
POLL_FAIL_MAX_S = 15.0
# Short KCP timeout so one dead scale does not freeze the others for 5s.
KCP_POLL_TIMEOUT_S = 0.4
SLOT_SKIP_AFTER_FAIL_S = 5.0
# Cap JSON POST bodies (admin config patches are tiny).
MAX_JSON_BODY_BYTES = 64 * 1024
ADMIN_PIN_HEADER = "X-Havikki-Pin"


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def admin_pin_configured() -> str | None:
    """Return configured admin PIN, or None if open (lab without PIN)."""
    pin = os.environ.get("HAVIKKI_ADMIN_PIN", "").strip()
    return pin or None


def pin_matches(provided: str, expected: str) -> bool:
    """Constant-time PIN compare (different lengths → False)."""
    a = provided.encode("utf-8")
    b = expected.encode("utf-8")
    if len(a) != len(b):
        hmac.compare_digest(a, a)
        return False
    return hmac.compare_digest(a, b)


def safe_static_file(rel: str) -> Path | None:
    """Resolve /static/<rel> only if the file stays under app/static."""
    if not rel or "\x00" in rel:
        return None
    try:
        candidate = (STATIC / rel).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not candidate.is_relative_to(STATIC_ROOT):
        return None
    if candidate.is_file():
        return candidate
    return None


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
        # CLI/env host for A bootstrap if config host empty
        if not self.cfg.scale_a_host:
            self.cfg = self.config_store.update(
                {"scale_a_host": host, "scale_a_port": port}
            )
        self.storage = Storage(DATA / "events.sqlite3")
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._stats_day = date.today().isoformat()
        self._fail_delay_s = POLL_FAIL_MIN_S
        self._last_logged_error: str | None = None
        self._last_poll_ok_at: str | None = None
        # Per-slot SAD cal (ykv_sad_cal_{a,b,c}.json or shared ykv_sad_cal.json).
        self._sad_cal_by_slot: dict[str, dict[str, float] | None] = {
            s: (None if mock else load_sad_cal_for_slot(s, DATA))
            for s in ("a", "b", "c")
        }
        self._sad_cal = next(
            (c for c in self._sad_cal_by_slot.values() if c is not None), None
        )
        # SAD soft-tare per scale (KCP T does not affect SAD path).
        self._sad_tare_g: dict[str, float] = {"a": 0.0, "b": 0.0, "c": 0.0}
        self._sad_raw_g: dict[str, float] = {"a": 0.0, "b": 0.0, "c": 0.0}
        # Skip a dead slot briefly so one failed KCP does not stall the others.
        self._slot_skip_until: dict[str, float] = {}

        self.scale_a: KcpClient | MockScale | None = None
        self.scale_b: KcpClient | MockScale | None = None
        self.scale_c: KcpClient | MockScale | None = None

        self.machine_a = self._make_machine("a", on_auto_tare=self._on_auto_tare_a)
        self.machine_b = self._make_machine("b", on_auto_tare=self._on_auto_tare_b)
        self.machine_c = self._make_machine(
            "c", on_auto_tare=self._on_auto_tare_c, data_only=True
        )
        self.machine = self.machine_a  # legacy alias (admin/tare)

        self._init_scales()
        self.scale = self.scale_a  # legacy

        if self._sad_cal:
            for slot, cal in self._sad_cal_by_slot.items():
                if not cal:
                    continue
                LOG.info(
                    "weight source=SAD slot=%s empty=%s ref=%s@%skg",
                    slot,
                    int(cal["sad_empty"]),
                    int(cal["sad_at_ref"]),
                    cal["ref_kg"],
                )
        elif not mock:
            LOG.info("weight source=SI (no data/ykv_sad_cal*.json)")
        pin = admin_pin_configured()
        if pin:
            LOG.info("admin PIN required (header %s)", ADMIN_PIN_HEADER)
        else:
            LOG.warning(
                "HAVIKKI_ADMIN_PIN unset — admin APIs open on bind address "
                "(ok only on an isolated lab switch)"
            )
        self._refresh_day()
        if self.cfg.prefill_waste_g > 0 and "a" in self.cfg.slots():
            self.machine_a.apply_baseline(self.cfg.prefill_waste_g)

    def _machines(self) -> dict[str, StateMachine]:
        return {"a": self.machine_a, "b": self.machine_b, "c": self.machine_c}

    def _scales(self) -> dict[str, KcpClient | MockScale | None]:
        return {"a": self.scale_a, "b": self.scale_b, "c": self.scale_c}

    def _set_scale(self, slot: str, client: KcpClient | MockScale | None) -> None:
        if slot == "a":
            self.scale_a = client
            self.scale = client
        elif slot == "b":
            self.scale_b = client
        elif slot == "c":
            self.scale_c = client

    def _init_scales(self) -> None:
        """Create clients for enabled slots from config (mock → MockScale)."""
        slots = self.cfg.slots()
        for slot in ("a", "b", "c"):
            old = self._scales()[slot]
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass
                self._set_scale(slot, None)
            if slot not in slots:
                continue
            if self.mock:
                self._set_scale(slot, MockScale())
                continue
            host = self.cfg.host_for(slot)
            port = self.cfg.port_for(slot)
            if not host:
                LOG.warning("scale %s enabled but host empty — skipped", slot)
                continue
            # CLI host wins for A on first boot when matching defaults
            if slot == "a" and self.host and host == "192.168.50.11":
                # Prefer explicit --host / HAVIKKI_HOST when provided at start
                host = self.host
                port = self.port
            self._set_scale(slot, KcpClient(host, port, timeout=KCP_POLL_TIMEOUT_S))
            LOG.info("scale %s → %s:%s (timeout=%.1fs)", slot, host, port, KCP_POLL_TIMEOUT_S)

    def _make_machine(
        self,
        scale_id: str,
        *,
        on_auto_tare: Callable[[], None] | None = None,
        data_only: bool = False,
    ) -> StateMachine:
        def _on_event(grams: float, feedback: str) -> None:
            self._on_event(grams, feedback, scale_id)

        return StateMachine(
            threshold_ok_g=self._cfg_float("threshold_ok_g", "HAVIKKI_THRESHOLD_OK_G", 200),
            threshold_g=self._cfg_float("threshold_g", "HAVIKKI_THRESHOLD_G", 300),
            settle_s=self._cfg_float("settle_s", "HAVIKKI_SETTLE_S", 10),
            empty_g=self._cfg_float("empty_g", "HAVIKKI_EMPTY_G", 20),
            empty_away_s=self._cfg_float("empty_away_s", "HAVIKKI_EMPTY_AWAY_S", 20),
            start_delta_g=float(self.cfg.start_delta_g),
            feedback_show_s=float(self.cfg.feedback_show_s),
            quantize_g=float(getattr(self.cfg, "quantize_g", 2.0)),
            empty_bin_g=float(self.cfg.empty_bin_g),
            empty_bin_tolerance_g=float(self.cfg.empty_bin_tolerance_g),
            data_only=data_only,
            on_event=_on_event,
            on_auto_tare=on_auto_tare,
        )

    def _cfg_float(self, attr: str, env_name: str, default: float) -> float:
        """Env overrides file on first boot (lab CLI); file wins after admin save."""
        if env_name in os.environ and os.environ[env_name].strip():
            try:
                return float(os.environ[env_name])
            except ValueError:
                pass
        return float(getattr(self.cfg, attr, default))

    def apply_config(self, cfg: AppConfig, *, rebuild_scales: bool = False) -> None:
        """Hot-reload machine params from saved config (lock held by caller)."""
        old = self.cfg
        self.cfg = cfg
        for slot, machine in self._machines().items():
            machine.apply_runtime_config(
                threshold_ok_g=cfg.threshold_ok_g,
                threshold_g=cfg.threshold_g,
                settle_s=cfg.settle_s,
                empty_g=cfg.empty_g,
                empty_away_s=cfg.empty_away_s,
                start_delta_g=cfg.start_delta_g,
                feedback_show_s=cfg.feedback_show_s,
                quantize_g=cfg.quantize_g,
                empty_bin_g=cfg.empty_bin_g,
                empty_bin_tolerance_g=cfg.empty_bin_tolerance_g,
                data_only=(slot == "c"),
            )
        need_rebuild = rebuild_scales or (
            old.scale_layout != cfg.scale_layout
            or old.scale_a_host != cfg.scale_a_host
            or old.scale_a_port != cfg.scale_a_port
            or old.scale_b_host != cfg.scale_b_host
            or old.scale_b_port != cfg.scale_b_port
            or old.scale_c_host != cfg.scale_c_host
            or old.scale_c_port != cfg.scale_c_port
        )
        if need_rebuild and not self.mock:
            self._init_scales()
        elif need_rebuild and self.mock:
            # Ensure mocks exist for newly enabled slots
            for slot in cfg.slots():
                if self._scales()[slot] is None:
                    self._set_scale(slot, MockScale())
            for slot in ("a", "b", "c"):
                if slot not in cfg.slots():
                    sc = self._scales()[slot]
                    if sc is not None:
                        try:
                            sc.close()
                        except Exception:
                            pass
                    self._set_scale(slot, None)
        LOG.info(
            "config applied layout=%s ok=%.0f frown=%.0f settle=%.1f theme=%s",
            cfg.scale_layout,
            cfg.threshold_ok_g,
            cfg.threshold_g,
            cfg.settle_s,
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

    def _stats_payload(self, stats) -> dict:
        return {
            "count": stats.count,
            "total_g": round(stats.total_g, 1),
            "avg_g": round(stats.avg_g, 1),
            "max_g": round(stats.max_g, 1),
            "min_g": round(stats.min_g, 1) if stats.min_g is not None else None,
            "smile_count": stats.smile_count,
            "ok_count": stats.ok_count,
            "frown_count": stats.frown_count,
        }

    def _refresh_day(self) -> None:
        plate = self.storage.day_stats(scale_ids=PLATE_SCALE_IDS)
        kitchen = self.storage.day_stats(scale_ids=KITCHEN_SCALE_IDS)
        for machine in (self.machine_a, self.machine_b):
            machine.state.day_count = plate.count
            machine.state.day_total_g = plate.total_g
            machine.state.day_avg_g = plate.avg_g
            machine.state.day_max_g = plate.max_g
            machine.state.day_min_g = plate.min_g
        self.machine_c.state.day_count = kitchen.count
        self.machine_c.state.day_total_g = kitchen.total_g
        self.machine_c.state.day_avg_g = kitchen.avg_g
        self.machine_c.state.day_max_g = kitchen.max_g
        self.machine_c.state.day_min_g = kitchen.min_g

    def _maybe_rollover_day(self) -> None:
        """When calendar day changes, reload stats (new day starts at zero)."""
        today = date.today().isoformat()
        if self._stats_day != today:
            LOG.info("day rollover %s → %s", self._stats_day, today)
            self._stats_day = today
            self._refresh_day()

    def _on_event(self, grams: float, feedback: str, scale_id: str = "a") -> None:
        self.storage.add_event(grams, feedback, scale_id=scale_id)
        self._refresh_day()
        LOG.info("event %s %.1fg %s", scale_id, grams, feedback)

    def _apply_sad_soft_tare(self, slot: str = "a") -> None:
        """Zero current SAD reading in software (lock held). No-op if not SAD mode."""
        if not self._sad_cal_by_slot.get(slot):
            return
        self._sad_tare_g[slot] = float(self._sad_raw_g.get(slot, 0.0))
        LOG.info("SAD soft-tare %s offset=%.1fg", slot, self._sad_tare_g[slot])

    def _on_auto_tare_a(self) -> None:
        self._auto_tare_slot("a")

    def _on_auto_tare_b(self) -> None:
        self._auto_tare_slot("b")

    def _on_auto_tare_c(self) -> None:
        self._auto_tare_slot("c")

    def _auto_tare_slot(self, slot: str) -> None:
        scale = self._scales()[slot]
        machine = self._machines()[slot]
        if scale is None:
            return
        try:
            self._apply_sad_soft_tare(slot)
            resp = scale.tare()
            LOG.info("auto-tare %s after emptying: %s", slot.upper(), resp)
            machine.state.error = None
        except Exception as e:  # noqa: BLE001 — keep kiosk alive
            LOG.warning("auto-tare %s failed: %s", slot, e)
            machine.state.error = friendly_scale_error(e)

    def _scale_snapshot(self, machine: StateMachine) -> dict:
        d = machine.to_dict()
        # Day totals live only at top-level (aggregated).
        d.pop("day", None)
        return d

    def _stub_scale(self) -> dict:
        return {
            "phase": "idle",
            "weight_g": 0.0,
            "live_addition_g": 0.0,
            "bin_weight_g": 0.0,
            "stable": True,
            "feedback": None,
            "last_event_g": None,
            "baseline_g": 0.0,
            "connected": False,
            "error": None,
            "threshold_ok_g": self.cfg.threshold_ok_g,
            "threshold_g": self.cfg.threshold_g,
            "settle_s": self.cfg.settle_s,
            "feedback_show_s": self.cfg.feedback_show_s,
            "empty_g": self.cfg.empty_g,
            "empty_away_s": self.cfg.empty_away_s,
            "quantize_g": self.cfg.quantize_g,
            "empty_bin_g": self.cfg.empty_bin_g,
            "empty_bin_tolerance_g": self.cfg.empty_bin_tolerance_g,
            "enabled": False,
        }

    def snapshot(self) -> dict:
        with self._lock:
            self._maybe_rollover_day()
            cfg = self.cfg
            slots = cfg.slots()
            plate = self.storage.day_stats(scale_ids=PLATE_SCALE_IDS)
            kitchen = self.storage.day_stats(scale_ids=KITCHEN_SCALE_IDS)
            day = {
                "count": plate.count,
                "total_g": self.machine_a._round_display(plate.total_g),
                "avg_g": self.machine_a._round_display(plate.avg_g),
                "max_g": self.machine_a._round_display(plate.max_g),
                "min_g": (
                    self.machine_a._round_display(plate.min_g)
                    if plate.min_g is not None
                    else None
                ),
            }
            day_kitchen = {
                "count": kitchen.count,
                "total_g": round(kitchen.total_g, 1),
                "avg_g": round(kitchen.avg_g, 1),
                "max_g": round(kitchen.max_g, 1),
                "min_g": round(kitchen.min_g, 1) if kitchen.min_g is not None else None,
            }
            scales_out: dict[str, dict] = {}
            for slot, machine in self._machines().items():
                if slot in slots and self._scales()[slot] is not None:
                    snap = self._scale_snapshot(machine)
                    snap["enabled"] = True
                    snap["label"] = SCALE_LABELS[slot]
                    scales_out[slot] = snap
                else:
                    stub = self._stub_scale()
                    stub["label"] = SCALE_LABELS[slot]
                    scales_out[slot] = stub
            flat_src = self.machine_a if "a" in slots else (
                self.machine_c if "c" in slots else self.machine_a
            )
            flat = flat_src.to_dict()
            return flat | {
                "mode": "mock" if self.mock else "live",
                "theme": cfg.theme,
                "site_id": cfg.site_id,
                "kiosk_title": cfg.kiosk_title,
                "kiosk_location": cfg.kiosk_location,
                "scale_layout": cfg.scale_layout,
                "kiosk_enabled": layout_kiosk_enabled(cfg.scale_layout),
                "diner_split": layout_diner_split(cfg.scale_layout),
                "day": day,
                "day_kitchen": day_kitchen,
                "scales": scales_out,
                "config": {
                    "threshold_ok_g": cfg.threshold_ok_g,
                    "threshold_g": cfg.threshold_g,
                    "settle_s": cfg.settle_s,
                    "feedback_show_s": cfg.feedback_show_s,
                    "empty_g": cfg.empty_g,
                    "empty_away_s": cfg.empty_away_s,
                    "quantize_g": cfg.quantize_g,
                    "empty_bin_g": cfg.empty_bin_g,
                    "theme": cfg.theme,
                    "site_id": cfg.site_id,
                    "kiosk_title": cfg.kiosk_title,
                    "kiosk_location": cfg.kiosk_location,
                    "scale_layout": cfg.scale_layout,
                    "kiosk_enabled": layout_kiosk_enabled(cfg.scale_layout),
                    "diner_split": layout_diner_split(cfg.scale_layout),
                    "feedback_smile_text": cfg.feedback_smile_text,
                    "feedback_ok_text": cfg.feedback_ok_text,
                    "feedback_frown_text": cfg.feedback_frown_text,
                },
            }

    def health(self) -> dict:
        with self._lock:
            cfg = self.cfg
            slots = cfg.slots()
            scales = []
            for slot in ("a", "b", "c"):
                machine = self._machines()[slot]
                enabled = slot in slots
                st = machine.state
                scales.append(
                    {
                        "scale_id": slot,
                        "label": SCALE_LABELS[slot],
                        "enabled": enabled,
                        "connected": bool(st.connected) if enabled else False,
                        "error": st.error if enabled else None,
                        "phase": st.phase.value if enabled else "idle",
                        "last_event_g": st.last_event_g if enabled else None,
                        "host": cfg.host_for(slot) if enabled else "",
                        "port": cfg.port_for(slot) if enabled else None,
                    }
                )
            any_conn = any(s["connected"] for s in scales if s["enabled"])
            primary = next((s for s in scales if s["enabled"]), None)
            return {
                "ok": True,
                "mode": "mock" if self.mock else "live",
                "connected": any_conn,
                "error": primary["error"] if primary else None,
                "phase": primary["phase"] if primary else "idle",
                "last_poll_ok_at": self._last_poll_ok_at,
                "last_event_g": primary["last_event_g"] if primary else None,
                "site_id": cfg.site_id,
                "theme": cfg.theme,
                "scale_layout": cfg.scale_layout,
                "kiosk_enabled": layout_kiosk_enabled(cfg.scale_layout),
                "scales": scales,
            }

    def tare(self, scale_id: str = "a") -> str:
        """Tare current weight as empty bin (not waste); reset machine to idle zero."""
        sid = (scale_id or "a").strip().lower()
        with self._lock:
            scale = self._scales().get(sid)
            machine = self._machines().get(sid)
            if scale is None or machine is None:
                raise RuntimeError(f"vaaka {sid} ei käytössä")
            self._apply_sad_soft_tare(sid)
            resp = scale.tare()
            machine.apply_manual_tare_reset()
            return resp

    def zero(self, scale_id: str = "a") -> str:
        """Scale hardware zero/tare baseline (not day counters)."""
        sid = (scale_id or "a").strip().lower()
        with self._lock:
            scale = self._scales().get(sid)
            machine = self._machines().get(sid)
            if scale is None or machine is None:
                raise RuntimeError(f"vaaka {sid} ei käytössä")
            self._apply_sad_soft_tare(sid)
            resp = scale.zero()
            machine.apply_manual_tare_reset()
            return resp

    def set_baseline_current(self, scale_id: str = "a") -> dict:
        """Treat current scale reading as baseline (pre-filled bin); no waste event."""
        sid = (scale_id or "a").strip().lower()
        with self._lock:
            machine = self._machines().get(sid)
            if machine is None or sid not in self.cfg.slots():
                raise RuntimeError(f"vaaka {sid} ei käytössä")
            w = float(machine.state.weight_g)
            machine.apply_baseline(w)
            LOG.info("manual baseline %s set to %.1fg (no waste count)", sid, w)
            return {"baseline_g": round(w, 1), "scale_id": sid}

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
            plate = self.storage.day_stats(day, scale_ids=PLATE_SCALE_IDS)
            kitchen = self.storage.day_stats(day, scale_ids=KITCHEN_SCALE_IDS)
            csv_body = self.storage.export_day_csv(day)
            json_body = self.storage.export_day_json(
                day,
                site_id=cfg.site_id,
                co2_factor_kg_per_kg=cfg.co2_factor_kg_per_kg,
                plate_stats=plate,
                kitchen_stats=kitchen,
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
        plate = self.storage.day_stats(day, scale_ids=PLATE_SCALE_IDS)
        kitchen = self.storage.day_stats(day, scale_ids=KITCHEN_SCALE_IDS)
        return self.storage.export_day_json(
            day,
            site_id=cfg.site_id,
            co2_factor_kg_per_kg=cfg.co2_factor_kg_per_kg,
            plate_stats=plate,
            kitchen_stats=kitchen,
        )

    def reset_day(
        self,
        *,
        export_first: bool | None = None,
        day: str | None = None,
    ) -> dict:
        """Clear events for a calendar day; optionally export CSV+JSON first.

        Default day = today. Clearing a past day does not refresh live kiosk
        counters unless that day is still \"today\".
        """
        target = day or date.today().isoformat()
        # Basic YYYY-MM-DD guard
        try:
            date.fromisoformat(target)
        except ValueError as e:
            raise ValueError(f"day: YYYY-MM-DD ({e})") from e
        with self._lock:
            do_export = (
                self.cfg.export_before_reset
                if export_first is None
                else bool(export_first)
            )
            exported = None
        if do_export:
            exported = self.export_day_files(target)
        with self._lock:
            deleted = self.storage.clear_day(target)
            today = date.today().isoformat()
            if target == today:
                self._stats_day = today
                self._refresh_day()
            LOG.info("day stats reset day=%s (%s events deleted)", target, deleted)
            return {
                "deleted": deleted,
                "exported": exported,
                "cleared_day": target,
                "day": {
                    "count": self.machine_a.state.day_count,
                    "total_g": self.machine_a.state.day_total_g,
                    "avg_g": self.machine_a.state.day_avg_g,
                    "max_g": self.machine_a.state.day_max_g,
                    "min_g": self.machine_a.state.day_min_g,
                },
                "day_kitchen": {
                    "count": self.machine_c.state.day_count,
                    "total_g": self.machine_c.state.day_total_g,
                },
            }

    def _demo_scale(self, scale_id: str) -> MockScale:
        sid = (scale_id or "a").strip().lower()
        scale = self._scales().get(sid)
        if not isinstance(scale, MockScale):
            raise RuntimeError(f"demo {sid.upper()} only in mock mode / enabled slot")
        return scale

    def demo_add(self, grams: float, scale_id: str = "a") -> None:
        with self._lock:
            self._demo_scale(scale_id).add_grams(grams)

    def demo_set(self, grams: float, scale_id: str = "a") -> None:
        with self._lock:
            self._demo_scale(scale_id).weight_g = grams

    def _switch_to_mock_fallback(self, reason: str) -> None:
        """Optional lab escape hatch — only when HAVIKKI_ALLOW_MOCK_FALLBACK=1."""
        if self.mock or not _env_truthy("HAVIKKI_ALLOW_MOCK_FALLBACK"):
            return
        LOG.warning("mock fallback enabled after scale failure: %s", reason)
        self.mock = True
        self._init_scales()
        with self._lock:
            for machine in self._machines().values():
                machine.state.connected = True
                machine.state.error = None

    def _poll_one(
        self,
        *,
        scale: KcpClient | MockScale,
        machine: StateMachine,
        use_sad: bool,
        label: str,
    ) -> None:
        cal = self._sad_cal_by_slot.get(label)
        if not scale.connected:
            scale.connect()
        if use_sad and isinstance(scale, KcpClient) and cal:
            sad = scale.sad()
            raw_g = grams_from_sad(sad, cal)
            with self._lock:
                self._sad_raw_g[label] = raw_g
                value = raw_g - self._sad_tare_g.get(label, 0.0)
                machine.state.connected = True
                machine.state.error = None
                machine.update(value, stable=True)
                self._last_poll_ok_at = datetime.now(timezone.utc).isoformat()
        else:
            status, value, _unit = scale.si()
            with self._lock:
                machine.state.connected = True
                machine.state.error = None
                if value is not None:
                    stable = status == "S"
                    machine.update(value, stable=stable)
                self._last_poll_ok_at = datetime.now(timezone.utc).isoformat()

    def poll_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                slots = list(self.cfg.slots())
                scales = {s: self._scales()[s] for s in slots}
                machines = {s: self._machines()[s] for s in slots}
            if not slots:
                time.sleep(POLL_FAIL_MIN_S)
                continue
            any_ok = False
            primary_err: BaseException | None = None
            now = time.monotonic()
            for label in slots:
                scale = scales.get(label)
                machine = machines.get(label)
                if scale is None or machine is None:
                    continue
                skip_until = self._slot_skip_until.get(label, 0.0)
                if now < skip_until:
                    continue
                try:
                    self._poll_one(
                        scale=scale,
                        machine=machine,
                        use_sad=bool(self._sad_cal_by_slot.get(label)),
                        label=label,
                    )
                    any_ok = True
                    self._slot_skip_until.pop(label, None)
                except Exception as e:  # noqa: BLE001
                    friendly = friendly_scale_error(e)
                    with self._lock:
                        machine.state.connected = False
                        machine.state.error = friendly
                    self._slot_skip_until[label] = time.monotonic() + SLOT_SKIP_AFTER_FAIL_S
                    raw = str(e)
                    if raw != self._last_logged_error:
                        LOG.warning("scale poll %s: %s → %s", label.upper(), raw, friendly)
                        self._last_logged_error = raw
                    try:
                        scale.close()
                    except Exception:
                        pass
                    if label == slots[0]:
                        primary_err = e
            if any_ok:
                self._fail_delay_s = POLL_FAIL_MIN_S
                self._last_logged_error = None
                time.sleep(POLL_OK_S)
                continue
            if primary_err is not None:
                self._switch_to_mock_fallback(str(primary_err))
                if self.mock:
                    self._fail_delay_s = POLL_FAIL_MIN_S
                    continue
            delay = self._fail_delay_s
            self._fail_delay_s = min(POLL_FAIL_MAX_S, self._fail_delay_s * 2)
            time.sleep(delay)

    def stop(self) -> None:
        self._stop.set()
        for sc in self._scales().values():
            if sc is None:
                continue
            try:
                sc.close()
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

        def _admin_authorized(self) -> bool:
            expected = admin_pin_configured()
            if expected is None:
                return True
            provided = self.headers.get(ADMIN_PIN_HEADER, "")
            return pin_matches(provided, expected)

        def _require_admin(self) -> bool:
            """Return True if allowed; else send 401 JSON and return False."""
            if self._admin_authorized():
                return True
            self._json(
                401,
                {
                    "ok": False,
                    "error": "Admin PIN vaaditaan",
                    "auth_required": True,
                },
            )
            return False

        def _read_json_body(self) -> dict:
            raw_len = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_len)
            except ValueError:
                length = 0
            if length < 0:
                length = 0
            if length > MAX_JSON_BODY_BYTES:
                raise ValueError(
                    f"pyyntö liian suuri (max {MAX_JSON_BODY_BYTES} tavua)"
                )
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
                # HTML shell is public so the PIN prompt can load; APIs stay gated.
                self._file(STATIC / "admin.html", "text/html; charset=utf-8")
            elif path == "/api/auth":
                self._json(
                    200,
                    {
                        "ok": True,
                        "auth_required": admin_pin_configured() is not None,
                        "pin_header": ADMIN_PIN_HEADER,
                    },
                )
            elif path == "/api/state":
                self._json(200, app.snapshot())
            elif path == "/api/health":
                # Open for day-close wait / kiosk ops; no day event dump.
                self._json(200, app.health())
            elif path == "/api/config":
                if not self._require_admin():
                    return
                self._json(200, {"ok": True, "config": app.get_config()})
            elif path == "/api/events":
                if not self._require_admin():
                    return
                try:
                    limit = int((qs.get("limit") or ["100"])[0])
                    offset = int((qs.get("offset") or ["0"])[0])
                except ValueError:
                    limit, offset = 100, 0
                scope = (qs.get("scope") or ["all"])[0].strip().lower()
                if scope == "plate":
                    scale_ids: frozenset[str] | None = PLATE_SCALE_IDS
                elif scope == "kitchen":
                    scale_ids = KITCHEN_SCALE_IDS
                else:
                    scale_ids = None
                events = app.storage.list_events(
                    day=day, limit=limit, offset=offset, scale_ids=scale_ids
                )
                stats = app.storage.day_stats(day, scale_ids=scale_ids)
                plate = app.storage.day_stats(day, scale_ids=PLATE_SCALE_IDS)
                kitchen = app.storage.day_stats(day, scale_ids=KITCHEN_SCALE_IDS)
                self._json(
                    200,
                    {
                        "ok": True,
                        "day": day or date.today().isoformat(),
                        "scope": scope,
                        "stats": app._stats_payload(stats),
                        "plate": app._stats_payload(plate),
                        "kitchen": app._stats_payload(kitchen),
                        "events": events,
                    },
                )
            elif path == "/api/export/day.csv":
                if not self._require_admin():
                    return
                d = day or date.today().isoformat()
                self._text(
                    200,
                    app.day_csv_text(d),
                    "text/csv; charset=utf-8",
                    filename=f"havikkivaaka-{d}.csv",
                )
            elif path == "/api/export/day.json":
                if not self._require_admin():
                    return
                d = day or date.today().isoformat()
                self._text(
                    200,
                    app.day_json_text(d),
                    "application/json; charset=utf-8",
                    filename=f"havikkivaaka-{d}.json",
                )
            elif path.startswith("/static/"):
                rel = path[len("/static/") :]
                fp = safe_static_file(rel)
                if fp is not None:
                    ctype = "text/css" if fp.suffix == ".css" else "application/octet-stream"
                    if fp.suffix == ".html":
                        ctype = "text/html; charset=utf-8"
                    elif fp.suffix == ".js":
                        ctype = "application/javascript; charset=utf-8"
                    self._file(fp, ctype)
                else:
                    self.send_error(404)
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                data = self._read_json_body()
            except ValueError as e:
                self._json(413, {"ok": False, "error": str(e)})
                return

            # All mutating / staff routes require PIN when configured.
            if not self._require_admin():
                return

            try:
                if path == "/api/tare":
                    sid = str(data.get("scale", data.get("scale_id", "a")))
                    self._json(200, {"ok": True, "resp": app.tare(sid)})
                elif path == "/api/zero":
                    # Scale hardware zero (kept for tools); UI Nollaa uses reset-day
                    sid = str(data.get("scale", data.get("scale_id", "a")))
                    self._json(200, {"ok": True, "resp": app.zero(sid)})
                elif path == "/api/reset-day":
                    export_first = data.get("export_first")
                    if export_first is None:
                        export_first = None
                    else:
                        export_first = bool(export_first)
                    day_arg = data.get("day")
                    if day_arg is not None and not isinstance(day_arg, str):
                        raise ValueError("day: YYYY-MM-DD merkkijono")
                    self._json(
                        200,
                        {
                            "ok": True,
                            **app.reset_day(
                                export_first=export_first,
                                day=day_arg if isinstance(day_arg, str) else None,
                            ),
                        },
                    )
                elif path == "/api/config":
                    cfg = app.update_config(data)
                    self._json(200, {"ok": True, "config": cfg.to_dict()})
                elif path == "/api/set-baseline":
                    sid = str(data.get("scale", data.get("scale_id", "a")))
                    self._json(200, {"ok": True, **app.set_baseline_current(sid)})
                elif path == "/api/export/day":
                    # Save CSV+JSON to data/exports/ (admin "Vie raportti")
                    day = data.get("day")
                    result = app.export_day_files(day if isinstance(day, str) else None)
                    self._json(200, {"ok": True, **result})
                elif path == "/api/demo/add":
                    grams = float(data.get("grams", 100))
                    scale = str(data.get("scale", "a"))
                    app.demo_add(grams, scale)
                    self._json(200, {"ok": True})
                elif path == "/api/demo/set":
                    grams = float(data.get("grams", 0))
                    scale = str(data.get("scale", "a"))
                    app.demo_set(grams, scale)
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
        for m in app._machines().values():
            m.settle_s = args.settle_s
    if args.empty_away_s is not None:
        for m in app._machines().values():
            m.empty_away_s = args.empty_away_s
    if args.empty_g is not None:
        for m in app._machines().values():
            m.empty_g = args.empty_g

    t = threading.Thread(target=app.poll_loop, name="scale-poll", daemon=True)
    t.start()

    handler = make_handler(app)
    httpd = ThreadingHTTPServer((args.http_host, args.http_port), handler)
    LOG.info(
        "Kiosk http://%s:%s  admin http://%s:%s/admin  mode=%s layout=%s",
        args.http_host,
        args.http_port,
        args.http_host,
        args.http_port,
        "mock" if use_mock else "live",
        app.cfg.scale_layout,
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

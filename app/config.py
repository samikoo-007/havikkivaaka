"""Persistent kiosk/admin settings (data/config.json) with validation."""

from __future__ import annotations

import json
import logging
import os
import threading
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

LOG = logging.getLogger("havikkivaaka.config")

# Fixed Admin labels (not free-text). Schema allows more slots later.
SCALE_LABELS: dict[str, str] = {
    "a": "Vasen lohko",
    "b": "Oikea lohko",
    "c": "Keittiön hävikki",
}

# Allowed v1 layouts (extensible later).
SCALE_LAYOUTS: frozenset[str] = frozenset({"a", "a_b", "a_c", "a_b_c", "c"})

LAYOUT_SLOTS: dict[str, frozenset[str]] = {
    "a": frozenset({"a"}),
    "a_b": frozenset({"a", "b"}),
    "a_c": frozenset({"a", "c"}),
    "a_b_c": frozenset({"a", "b", "c"}),
    "c": frozenset({"c"}),
}

PLATE_SCALE_IDS: frozenset[str] = frozenset({"a", "b"})
KITCHEN_SCALE_IDS: frozenset[str] = frozenset({"c"})


def layout_slots(layout: str) -> frozenset[str]:
    return LAYOUT_SLOTS.get(str(layout).strip().lower(), frozenset({"a"}))


def layout_kiosk_enabled(layout: str) -> bool:
    """Diner Chromium UI only when A is in the layout (not C-only)."""
    return "a" in layout_slots(layout)


def layout_diner_split(layout: str) -> bool:
    """True → A|B dual panels; False + kiosk → A full-width."""
    slots = layout_slots(layout)
    return "a" in slots and "b" in slots


def _default_host(slot: str) -> str:
    env_map = {
        "a": ("HAVIKKI_HOST", "192.168.50.11"),
        "b": ("HAVIKKI_HOST_B", ""),
        "c": ("HAVIKKI_HOST_C", ""),
    }
    env_name, fallback = env_map[slot]
    return os.environ.get(env_name, fallback).strip()


def _default_port(slot: str) -> int:
    env_map = {
        "a": ("HAVIKKI_PORT", "23"),
        "b": ("HAVIKKI_PORT_B", "23"),
        "c": ("HAVIKKI_PORT_C", "23"),
    }
    env_name, fallback = env_map[slot]
    raw = os.environ.get(env_name, fallback).strip()
    try:
        return int(raw)
    except ValueError:
        return 23


DEFAULTS: dict[str, Any] = {
    # 3-tier: smile < ok_g ≤ addition < threshold_g → ok; else frown
    "threshold_ok_g": 200.0,
    "threshold_g": 300.0,
    "settle_s": 10.0,
    "feedback_show_s": 3.2,
    "empty_g": 20.0,
    "empty_away_s": 20.0,
    "start_delta_g": 40.0,
    # Round + deadband for display/settle (SAD noise ~1–2 g). 0 = off.
    "quantize_g": 2.0,
    # Known empty-bin mass (g). 0 = disabled; when set, return-to-scale near this
    # weight ± empty_bin_tolerance_g completes auto-tare emptying.
    "empty_bin_g": 0.0,
    "empty_bin_tolerance_g": 50.0,
    # If bin already has waste when placed: set baseline to this (g) so it is
    # not counted as a new plate event. 0 = unused (use Taara / Aseta baseline).
    "prefill_waste_g": 0.0,
    "theme": "dark",  # dark | light — kiosk data-theme
    "export_before_reset": True,
    "co2_factor_kg_per_kg": 2.5,  # Agent1 Should: simple ESG multiplier
    "site_id": "lab-1",
    # Visible kiosk header title (brand), e.g. Hävikkivaaka
    "kiosk_title": "Hävikkivaaka",
    # Top-right place on kiosk (e.g. school or site name). Empty = hidden.
    "kiosk_location": "",
    "feedback_smile_text": "Hienoa — pieni hävikki tänään.",
    "feedback_ok_text": (
        "Ihan ok — seuraavalla kerralla voit ottaa vähän vähemmän."
    ),
    "feedback_frown_text": (
        "Kiitos palautuksesta — pienempi annos säästää ja maistuu usein paremmin."
    ),
    # Scale layout + transmitter hosts (Admin UI). Env used as bootstrap defaults.
    "scale_layout": "a",
    "scale_a_host": _default_host("a"),
    "scale_a_port": _default_port("a"),
    "scale_b_host": _default_host("b"),
    "scale_b_port": _default_port("b"),
    "scale_c_host": _default_host("c"),
    "scale_c_port": _default_port("c"),
}


@dataclass
class AppConfig:
    threshold_ok_g: float = 200.0
    threshold_g: float = 300.0
    settle_s: float = 10.0
    feedback_show_s: float = 3.2
    empty_g: float = 20.0
    empty_away_s: float = 20.0
    start_delta_g: float = 40.0
    quantize_g: float = 2.0
    empty_bin_g: float = 0.0
    empty_bin_tolerance_g: float = 50.0
    prefill_waste_g: float = 0.0
    theme: str = "dark"
    export_before_reset: bool = True
    co2_factor_kg_per_kg: float = 2.5
    site_id: str = "lab-1"
    kiosk_title: str = "Hävikkivaaka"
    kiosk_location: str = ""
    feedback_smile_text: str = "Hienoa — pieni hävikki tänään."
    feedback_ok_text: str = (
        "Ihan ok — seuraavalla kerralla voit ottaa vähän vähemmän."
    )
    feedback_frown_text: str = (
        "Kiitos palautuksesta — pienempi annos säästää ja maistuu usein paremmin."
    )
    scale_layout: str = "a"
    scale_a_host: str = "192.168.50.11"
    scale_a_port: int = 23
    scale_b_host: str = ""
    scale_b_port: int = 23
    scale_c_host: str = ""
    scale_c_port: int = 23

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["scale_labels"] = dict(SCALE_LABELS)
        d["kiosk_enabled"] = layout_kiosk_enabled(self.scale_layout)
        d["diner_split"] = layout_diner_split(self.scale_layout)
        d["enabled_scales"] = sorted(layout_slots(self.scale_layout))
        return d

    def slots(self) -> frozenset[str]:
        return layout_slots(self.scale_layout)

    def host_for(self, slot: str) -> str:
        return str(getattr(self, f"scale_{slot}_host", "") or "").strip()

    def port_for(self, slot: str) -> int:
        try:
            return int(getattr(self, f"scale_{slot}_port", 23))
        except (TypeError, ValueError):
            return 23


_TEXT_MAX: dict[str, int] = {
    "kiosk_title": 80,
    "kiosk_location": 80,
    "feedback_smile_text": 500,
    "feedback_ok_text": 500,
    "feedback_frown_text": 1000,
}

_HOST_KEYS = ("scale_a_host", "scale_b_host", "scale_c_host")
_PORT_KEYS = ("scale_a_port", "scale_b_port", "scale_c_port")


# (min, max) inclusive for numeric fields
_RANGES: dict[str, tuple[float, float]] = {
    "threshold_ok_g": (50.0, 5000.0),
    "threshold_g": (50.0, 5000.0),
    "settle_s": (0.5, 120.0),
    "feedback_show_s": (0.5, 30.0),
    "empty_g": (0.0, 500.0),
    "empty_away_s": (1.0, 300.0),
    "start_delta_g": (5.0, 500.0),
    "quantize_g": (0.0, 50.0),
    "empty_bin_g": (0.0, 50000.0),
    "empty_bin_tolerance_g": (1.0, 2000.0),
    "prefill_waste_g": (0.0, 50000.0),
    "co2_factor_kg_per_kg": (0.0, 50.0),
    "scale_a_port": (1.0, 65535.0),
    "scale_b_port": (1.0, 65535.0),
    "scale_c_port": (1.0, 65535.0),
}


class ConfigStore:
    """Thread-safe load/save of AppConfig from JSON."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cfg = AppConfig(**deepcopy(DEFAULTS))
        self.load()

    def load(self) -> AppConfig:
        with self._lock:
            if self.path.is_file():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        # Migrate legacy site_label → kiosk_location
                        if "kiosk_location" not in raw and "site_label" in raw:
                            raw = {**raw, "kiosk_location": raw.get("site_label") or ""}
                        merged = {**DEFAULTS, **{k: raw[k] for k in DEFAULTS if k in raw}}
                        self._cfg = _dict_to_config(merged)
                except (json.JSONDecodeError, OSError, TypeError, ValueError) as e:
                    LOG.warning("config load failed (%s) — using defaults", e)
            else:
                self._cfg = AppConfig(**deepcopy(DEFAULTS))
                self._write_unlocked(self._cfg)
            return deepcopy(self._cfg)

    def get(self) -> AppConfig:
        with self._lock:
            return deepcopy(self._cfg)

    def update(self, patch: dict[str, Any]) -> AppConfig:
        """Validate patch, merge, persist, return new config."""
        with self._lock:
            current = asdict(self._cfg)
            cleaned, errors = validate_patch(patch)
            if errors:
                raise ValueError("; ".join(errors))
            current.update(cleaned)
            # Hosts required for enabled slots
            trial = _dict_to_config(current)
            host_errors = _validate_layout_hosts(trial)
            if host_errors:
                raise ValueError("; ".join(host_errors))
            self._cfg = trial
            self._write_unlocked(self._cfg)
            return deepcopy(self._cfg)

    def _write_unlocked(self, cfg: AppConfig) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        # Persist only dataclass fields (not computed to_dict extras).
        tmp.write_text(
            json.dumps(asdict(cfg), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)


def _validate_layout_hosts(cfg: AppConfig) -> list[str]:
    errors: list[str] = []
    for slot in sorted(cfg.slots()):
        host = cfg.host_for(slot)
        if not host:
            errors.append(
                f"scale_{slot}_host vaaditaan kokoonpanossa {cfg.scale_layout}"
            )
    return errors


def _dict_to_config(d: dict[str, Any]) -> AppConfig:
    allowed = {f.name for f in fields(AppConfig)}
    kwargs = {k: d[k] for k in allowed if k in d}
    # Coerce types
    if "theme" in kwargs:
        theme = str(kwargs["theme"]).strip().lower()
        kwargs["theme"] = theme if theme in ("dark", "light") else "dark"
    if "export_before_reset" in kwargs:
        kwargs["export_before_reset"] = _as_bool(kwargs["export_before_reset"])
    if "site_id" in kwargs:
        kwargs["site_id"] = str(kwargs["site_id"]).strip()[:64] or "lab-1"
    if "kiosk_title" in kwargs:
        title = str(kwargs["kiosk_title"]).strip()[: _TEXT_MAX["kiosk_title"]]
        kwargs["kiosk_title"] = title or DEFAULTS["kiosk_title"]
    if "kiosk_location" in kwargs:
        kwargs["kiosk_location"] = str(kwargs["kiosk_location"]).strip()[
            : _TEXT_MAX["kiosk_location"]
        ]
    if "scale_layout" in kwargs:
        layout = str(kwargs["scale_layout"]).strip().lower().replace("+", "_").replace("-", "_")
        # Accept a+b / a+c aliases from UI
        aliases = {
            "ab": "a_b",
            "ac": "a_c",
            "abc": "a_b_c",
            "a_b_c": "a_b_c",
            "a_b": "a_b",
            "a_c": "a_c",
            "a": "a",
            "b": "a",  # not allowed alone → fall back
            "c": "c",
        }
        layout = aliases.get(layout, layout)
        kwargs["scale_layout"] = layout if layout in SCALE_LAYOUTS else "a"
    for key in _HOST_KEYS:
        if key in kwargs:
            kwargs[key] = str(kwargs[key]).strip()[:128]
    for key in _PORT_KEYS:
        if key in kwargs:
            try:
                kwargs[key] = int(float(kwargs[key]))
            except (TypeError, ValueError):
                kwargs[key] = 23
    for key, maxlen in _TEXT_MAX.items():
        if key in kwargs:
            if key in ("kiosk_title", "kiosk_location"):
                continue  # handled above
            text = str(kwargs[key]).strip()[:maxlen]
            kwargs[key] = text or DEFAULTS[key]
    for key in _RANGES:
        if key in kwargs and key not in _PORT_KEYS:
            kwargs[key] = float(kwargs[key])
    return AppConfig(**{**DEFAULTS, **kwargs})


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def validate_patch(patch: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return (cleaned subset, error messages)."""
    errors: list[str] = []
    cleaned: dict[str, Any] = {}
    allowed = {f.name for f in fields(AppConfig)}

    for key, val in patch.items():
        if key == "site_label":
            # Legacy alias → kiosk_location
            key = "kiosk_location"
        if key not in allowed:
            # Ignore computed extras clients may echo back
            if key in ("scale_labels", "kiosk_enabled", "diner_split", "enabled_scales"):
                continue
            errors.append(f"tuntematon asetus: {key}")
            continue
        if key == "theme":
            t = str(val).strip().lower()
            if t not in ("dark", "light"):
                errors.append("theme: dark tai light")
            else:
                cleaned[key] = t
            continue
        if key == "export_before_reset":
            cleaned[key] = _as_bool(val)
            continue
        if key == "site_id":
            s = str(val).strip()[:64]
            if not s:
                errors.append("site_id ei saa olla tyhjä")
            else:
                cleaned[key] = s
            continue
        if key == "scale_layout":
            layout = str(val).strip().lower().replace("+", "_").replace("-", "_")
            aliases = {
                "ab": "a_b",
                "ac": "a_c",
                "abc": "a_b_c",
            }
            layout = aliases.get(layout, layout)
            if layout not in SCALE_LAYOUTS:
                errors.append(
                    "scale_layout: a | a_b | a_c | a_b_c | c"
                )
            else:
                cleaned[key] = layout
            continue
        if key in _HOST_KEYS:
            cleaned[key] = str(val).strip()[:128]
            continue
        if key in _PORT_KEYS:
            try:
                port = int(float(val))
            except (TypeError, ValueError):
                errors.append(f"{key}: oltava porttinumero")
                continue
            if port < 1 or port > 65535:
                errors.append(f"{key}: oltava välillä 1–65535")
            else:
                cleaned[key] = port
            continue
        if key in _TEXT_MAX:
            text = str(val).strip()[: _TEXT_MAX[key]]
            if key == "kiosk_title":
                cleaned[key] = text or DEFAULTS["kiosk_title"]
                continue
            if key == "kiosk_location":
                cleaned[key] = text  # empty allowed → hidden on kiosk
                continue
            if not text:
                errors.append(f"{key} ei saa olla tyhjä")
            else:
                cleaned[key] = text
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            errors.append(f"{key}: oltava numero")
            continue
        lo, hi = _RANGES[key]
        if num < lo or num > hi:
            errors.append(f"{key}: oltava välillä {lo:g}–{hi:g}")
            continue
        cleaned[key] = num

    return cleaned, errors

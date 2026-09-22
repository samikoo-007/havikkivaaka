"""Persistent kiosk/admin settings (data/config.json) with validation."""

from __future__ import annotations

import json
import logging
import threading
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

LOG = logging.getLogger("havikkivaaka.config")

DEFAULTS: dict[str, Any] = {
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
    "feedback_smile_text": "Kiitos, olet ihana!",
    "feedback_frown_text": (
        "Ota seuraavalla kerralla vähemmän, voit aina ottaa lisää jos ruoka on hyvää!"
    ),
}


@dataclass
class AppConfig:
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
    feedback_smile_text: str = "Kiitos, olet ihana!"
    feedback_frown_text: str = (
        "Ota seuraavalla kerralla vähemmän, voit aina ottaa lisää jos ruoka on hyvää!"
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_TEXT_MAX: dict[str, int] = {
    "feedback_smile_text": 500,
    "feedback_frown_text": 1000,
}


# (min, max) inclusive for numeric fields
_RANGES: dict[str, tuple[float, float]] = {
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
            self._cfg = _dict_to_config(current)
            self._write_unlocked(self._cfg)
            return deepcopy(self._cfg)

    def _write_unlocked(self, cfg: AppConfig) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)


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
    for key, maxlen in _TEXT_MAX.items():
        if key in kwargs:
            text = str(kwargs[key]).strip()[:maxlen]
            kwargs[key] = text or DEFAULTS[key]
    for key in _RANGES:
        if key in kwargs:
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
        if key not in allowed:
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
        if key in _TEXT_MAX:
            text = str(val).strip()[: _TEXT_MAX[key]]
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

"""Bio-bin waste state machine: settle → smile/frown → keep baseline → empty/away → tare."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class Phase(str, Enum):
    IDLE = "idle"
    SETTLING = "settling"
    FEEDBACK = "feedback"
    HOLD = "hold"
    AWAY = "away"


@dataclass
class LiveState:
    phase: Phase = Phase.IDLE
    weight_g: float = 0.0
    stable: bool = True
    feedback: str | None = None  # smile | ok | frown
    settle_started: float | None = None
    feedback_until: float | None = None
    last_event_g: float | None = None  # addition size of last event
    baseline_g: float = 0.0  # weight after last event (0 when empty/idle)
    away_started: float | None = None
    away_floor_g: float | None = None  # lowest reading while away (return detect)
    connected: bool = False
    error: str | None = None
    day_count: int = 0
    day_total_g: float = 0.0
    day_avg_g: float = 0.0
    day_max_g: float = 0.0
    day_min_g: float | None = None


@dataclass
class StateMachine:
    threshold_ok_g: float = 200.0
    threshold_g: float = 300.0
    settle_s: float = 10.0
    empty_g: float = 20.0
    empty_away_s: float = 20.0
    start_delta_g: float = 40.0
    feedback_show_s: float = 3.2
    # Display/settle deadband (g). 0 = pass-through. Default 2 for SAD noise.
    quantize_g: float = 2.0
    # Held weight must stay put this long before settle may complete.
    stable_hold_s: float = 0.75
    # Known empty-bin mass (0 = off). When AWAY and reading ≈ this ± tolerance,
    # treat as empty bin returned and auto-tare.
    empty_bin_g: float = 0.0
    empty_bin_tolerance_g: float = 50.0
    # Kitchen / production scale: record grams, no smile/ok/frown UI.
    data_only: bool = False
    on_event: Callable[[float, str], None] | None = None
    on_auto_tare: Callable[[], None] | None = None
    state: LiveState = field(default_factory=LiveState)
    _held_g: float | None = field(default=None, repr=False)
    _held_since: float | None = field(default=None, repr=False)

    def classify_feedback(self, addition_g: float) -> str:
        """3-tier: smile | ok | frown."""
        ok_g = min(self.threshold_ok_g, self.threshold_g)
        if addition_g < ok_g:
            return "smile"
        if addition_g < self.threshold_g:
            return "ok"
        return "frown"

    def apply_runtime_config(
        self,
        *,
        threshold_ok_g: float | None = None,
        threshold_g: float | None = None,
        settle_s: float | None = None,
        empty_g: float | None = None,
        empty_away_s: float | None = None,
        start_delta_g: float | None = None,
        feedback_show_s: float | None = None,
        quantize_g: float | None = None,
        empty_bin_g: float | None = None,
        empty_bin_tolerance_g: float | None = None,
        data_only: bool | None = None,
    ) -> None:
        """Hot-apply admin settings without process restart."""
        if threshold_ok_g is not None:
            self.threshold_ok_g = float(threshold_ok_g)
        if threshold_g is not None:
            self.threshold_g = float(threshold_g)
        if settle_s is not None:
            self.settle_s = float(settle_s)
        if empty_g is not None:
            self.empty_g = float(empty_g)
        if empty_away_s is not None:
            self.empty_away_s = float(empty_away_s)
        if start_delta_g is not None:
            self.start_delta_g = float(start_delta_g)
        if feedback_show_s is not None:
            self.feedback_show_s = float(feedback_show_s)
        if quantize_g is not None:
            self.quantize_g = float(quantize_g)
            self._held_g = None
            self._held_since = None
        if empty_bin_g is not None:
            self.empty_bin_g = float(empty_bin_g)
        if empty_bin_tolerance_g is not None:
            self.empty_bin_tolerance_g = float(empty_bin_tolerance_g)
        if data_only is not None:
            self.data_only = bool(data_only)

    def _step_g(self, raw_g: float) -> float:
        qg = self.quantize_g
        if qg <= 0:
            return float(raw_g)
        return round(float(raw_g) / qg) * qg

    def _filter_weight(self, raw_g: float, now: float) -> tuple[float, bool]:
        """Deadband + step quantize; stable when held value unchanged for stable_hold_s."""
        qg = self.quantize_g
        if qg <= 0:
            return float(raw_g), True
        stepped = self._step_g(raw_g)
        if self._held_g is None:
            self._held_g = stepped
            self._held_since = now
        elif abs(float(raw_g) - self._held_g) >= qg:
            self._held_g = stepped
            self._held_since = now
        held_since = self._held_since if self._held_since is not None else now
        stable = (now - held_since) >= self.stable_hold_s
        return float(self._held_g), stable

    def _round_display(self, value_g: float) -> float:
        if self.quantize_g >= 1.0:
            return float(round(value_g))
        return round(value_g, 1)

    def apply_baseline(self, weight_g: float) -> None:
        """Set baseline to current weight without counting waste (pre-filled bin)."""
        s = self.state
        now = time.monotonic()
        held, _ = self._filter_weight(float(weight_g), now)
        s.baseline_g = held
        s.phase = Phase.HOLD if held > self.empty_g else Phase.IDLE
        s.away_started = None
        s.away_floor_g = None
        self._clear_settle_feedback()

    def _matches_empty_bin(self, weight_g: float) -> bool:
        if self.empty_bin_g <= 0:
            return False
        return abs(weight_g - self.empty_bin_g) <= self.empty_bin_tolerance_g

    def _addition(self, weight_g: float) -> float:
        return weight_g - self.state.baseline_g

    def live_addition_g(self) -> float:
        """Current plate addition for kiosk display (not cumulative bin weight).

        During FEEDBACK show the settled event size; after feedback (HOLD/IDLE)
        display is 0 until the next rise above baseline. During AWAY show 0.
        """
        s = self.state
        if s.phase == Phase.FEEDBACK:
            return float(s.last_event_g or 0.0)
        if s.phase == Phase.AWAY:
            return 0.0
        return max(0.0, self._addition(s.weight_g))

    def _enter_settling(self, now: float) -> None:
        s = self.state
        s.phase = Phase.SETTLING
        s.settle_started = now
        s.away_started = None

    def _clear_settle_feedback(self) -> None:
        s = self.state
        s.settle_started = None
        s.feedback = None
        s.feedback_until = None

    def _reset_idle_empty(self) -> None:
        """After tare / emptying: idle at net zero, ready for additions."""
        s = self.state
        s.phase = Phase.IDLE
        s.baseline_g = 0.0
        s.weight_g = 0.0
        s.away_started = None
        s.away_floor_g = None
        self._held_g = None
        self._held_since = None
        self._clear_settle_feedback()

    def _enter_away(self, weight_g: float) -> None:
        s = self.state
        s.phase = Phase.AWAY
        s.away_floor_g = weight_g
        self._clear_settle_feedback()

    def _complete_emptying(self) -> None:
        """Bin returned after emptying: auto-tare, baseline 0, no waste event."""
        if self.on_auto_tare:
            self.on_auto_tare()
        self._reset_idle_empty()

    def apply_manual_tare_reset(self) -> None:
        """UI/API tare or zero: treat current scale weight as empty bin, not waste."""
        self._reset_idle_empty()

    def update(self, weight_g: float, stable: bool = True) -> LiveState:
        now = time.monotonic()
        s = self.state
        filtered, hold_stable = self._filter_weight(float(weight_g), now)
        # Scale "S" (if any) AND deadband hold — SAD path always sent S before.
        if self.quantize_g > 0:
            stable = hold_stable
        s.weight_g = filtered
        s.stable = stable
        addition = self._addition(filtered)
        weight_g = filtered

        if s.phase == Phase.FEEDBACK:
            # Do not start away detection during feedback window
            if s.feedback_until and now >= s.feedback_until:
                s.phase = Phase.HOLD
                s.feedback = None
                s.feedback_until = None
            return s

        if s.phase == Phase.AWAY:
            if s.away_floor_g is None or weight_g < s.away_floor_g:
                s.away_floor_g = weight_g
            # Known empty-bin mass: reading near empty_bin_g completes emptying.
            if self._matches_empty_bin(weight_g):
                self._complete_emptying()
                return s
            # Bin returned: net rose enough from the away floor (covers ~0→bin
            # and large-negative platform → empty-bin ≈ 0 after prior tare).
            if s.away_floor_g is not None and (
                weight_g - s.away_floor_g
            ) >= self.start_delta_g:
                self._complete_emptying()
            return s

        if s.phase == Phase.SETTLING:
            s.away_started = None
            if addition < self.start_delta_g:
                # Dropped back — idle if empty baseline, else hold on prior contents
                if s.baseline_g <= self.empty_g:
                    s.phase = Phase.IDLE
                else:
                    s.phase = Phase.HOLD
                s.settle_started = None
                return s
            if (
                stable
                and s.settle_started
                and (now - s.settle_started) >= self.settle_s
            ):
                # Classify by this cycle's addition, not total bin weight
                fb = "none" if self.data_only else self.classify_feedback(addition)
                s.last_event_g = addition
                s.baseline_g = weight_g
                if self.on_event:
                    self.on_event(addition, fb)
                if self.data_only:
                    # Kitchen scale: no diner feedback window
                    s.feedback = None
                    s.feedback_until = None
                    s.phase = Phase.HOLD
                    s.settle_started = None
                else:
                    s.feedback = fb
                    s.phase = Phase.FEEDBACK
                    s.feedback_until = now + self.feedback_show_s
            return s

        # IDLE or HOLD — near-empty absolute may mean bin lifted (tyhjennys)
        if weight_g <= self.empty_g:
            had_content = s.baseline_g > self.empty_g or s.phase == Phase.HOLD
            if had_content:
                if s.away_started is None:
                    s.away_started = now
                elif (now - s.away_started) >= self.empty_away_s:
                    self._enter_away(weight_g)
                return s
            s.away_started = None
            return s

        # Weight back above empty threshold before away matured → cancel timer
        s.away_started = None

        if s.phase == Phase.IDLE:
            if addition >= self.start_delta_g:
                self._enter_settling(now)
            return s

        if s.phase == Phase.HOLD:
            if addition >= self.start_delta_g:
                self._enter_settling(now)
            return s

        return s

    def to_dict(self) -> dict:
        s = self.state
        live = self._round_display(self.live_addition_g())
        return {
            "phase": s.phase.value,
            # weight_g = live addition for UI; bin_weight_g = raw scale reading
            "weight_g": live,
            "live_addition_g": live,
            "bin_weight_g": self._round_display(s.weight_g),
            "stable": s.stable,
            "feedback": s.feedback,
            "last_event_g": (
                self._round_display(s.last_event_g)
                if s.last_event_g is not None
                else None
            ),
            "baseline_g": self._round_display(s.baseline_g),
            "connected": s.connected,
            "error": s.error,
            "threshold_ok_g": self.threshold_ok_g,
            "threshold_g": self.threshold_g,
            "settle_s": self.settle_s,
            "feedback_show_s": self.feedback_show_s,
            "empty_g": self.empty_g,
            "empty_away_s": self.empty_away_s,
            "quantize_g": self.quantize_g,
            "empty_bin_g": self.empty_bin_g,
            "empty_bin_tolerance_g": self.empty_bin_tolerance_g,
            "day": {
                "count": s.day_count,
                "total_g": self._round_display(s.day_total_g),
                "avg_g": self._round_display(s.day_avg_g),
                "max_g": self._round_display(s.day_max_g),
                "min_g": (
                    self._round_display(s.day_min_g)
                    if s.day_min_g is not None
                    else None
                ),
            },
        }

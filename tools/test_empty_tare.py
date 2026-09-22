#!/usr/bin/env python3
"""Quick empty-bin / auto-tare verification (mock scale, no HTTP).

Usage (from repo root):
  python3 tools/test_empty_tare.py
  python3 tools/test_empty_tare.py --empty-away-s 3   # slower, closer to production

With server + curl (optional):
  python3 -m app.server --mock --settle-s 0.2 --empty-away-s 3 --http-port 8080
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kcp import MockScale  # noqa: E402
from app.state_machine import Phase, StateMachine  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--empty-away-s", type=float, default=0.15, help="Away seconds (default 0.15)")
    p.add_argument("--settle-s", type=float, default=0.05, help="Settle seconds (default 0.05)")
    args = p.parse_args()

    scale = MockScale()
    events: list[tuple[float, str]] = []
    tares = {"n": 0}

    def on_event(g: float, fb: str) -> None:
        events.append((g, fb))

    def on_auto_tare() -> None:
        scale.tare()
        tares["n"] += 1

    sm = StateMachine(
        threshold_g=300.0,
        settle_s=args.settle_s,
        empty_g=20.0,
        empty_away_s=args.empty_away_s,
        feedback_show_s=0.02,
        start_delta_g=40.0,
        on_event=on_event,
        on_auto_tare=on_auto_tare,
    )

    def tick() -> None:
        _st, net, _u = scale.si()
        assert net is not None
        sm.update(net, stable=True)

    def wait_phase(phase: Phase, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            tick()
            if sm.state.phase == phase:
                return
            time.sleep(0.01)
        raise AssertionError(
            f"timeout waiting for {phase.value}, got {sm.state.phase.value} "
            f"w={sm.state.weight_g} base={sm.state.baseline_g}"
        )

    # 1) Start 0; add 150; add 100
    tick()
    assert sm.state.phase == Phase.IDLE and abs(sm.live_addition_g()) < 0.1

    scale.add_grams(150)
    wait_phase(Phase.SETTLING)
    wait_phase(Phase.FEEDBACK)
    wait_phase(Phase.HOLD)
    assert abs(events[-1][0] - 150) < 0.1

    scale.add_grams(100)
    wait_phase(Phase.SETTLING)
    wait_phase(Phase.FEEDBACK)
    wait_phase(Phase.HOLD)
    assert abs(events[-1][0] - 100) < 0.1
    day_before = sum(g for g, _ in events)
    assert abs(day_before - 250) < 0.1, day_before

    # 2) Lift: absolute weight ~0 for > empty_away_s
    scale.weight_g = 0.0
    wait_phase(Phase.AWAY, timeout=args.empty_away_s + 2.0)
    assert len(events) == 2, "AWAY must not create waste events"

    # 3) Empty bin back (500 g) → auto-tare, live 0, day unchanged
    scale.weight_g = 500.0
    wait_phase(Phase.IDLE, timeout=2.0)
    assert tares["n"] == 1, f"expected 1 auto-tare, got {tares['n']}"
    _st, net, _u = scale.si()
    assert net is not None and abs(net) < 0.1, f"net after tare should be 0, got {net}"
    tick()
    assert sm.state.phase == Phase.IDLE
    assert abs(sm.live_addition_g()) < 0.1
    assert abs(sm.state.baseline_g) < 0.1
    assert abs(sum(g for g, _ in events) - day_before) < 0.1

    # 4) Add 200; day increases by 200 only
    scale.add_grams(200)
    wait_phase(Phase.SETTLING)
    wait_phase(Phase.FEEDBACK)
    wait_phase(Phase.HOLD)
    assert abs(events[-1][0] - 200) < 0.1
    day_after = sum(g for g, _ in events)
    assert abs(day_after - (day_before + 200)) < 0.1, day_after

    print("OK empty-bin auto-tare")
    print(f"  events={[round(g, 1) for g, _ in events]} total={day_after:.1f}g")
    print(f"  auto_tares={tares['n']} empty_away_s={args.empty_away_s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Lightweight in-process metrics (plan §10). Swap for Prometheus/OTel in production.

Counts what matters operationally: turns by mode, grounded vs not, degraded (fallback) rate,
crisis routes, dropped (unfaithful/invalid) verses, provider usage, and retrieval source.
"""

from __future__ import annotations

from collections import defaultdict

from app.core.budget import latency_recorder


class Metrics:
    def __init__(self) -> None:
        self.counters: dict[str, int] = defaultdict(int)

    def incr(self, key: str, n: int = 1) -> None:
        self.counters[key] += n

    def record_turn(self, done: dict) -> None:
        self.incr("turns")
        self.incr(f"mode.{done.get('mode')}")
        if done.get("grounded"):
            self.incr("grounded")
        if done.get("degraded"):
            self.incr("degraded")
        if done.get("safety"):
            self.incr("crisis")
        if done.get("verified") is False:
            self.incr("verify_dropped")  # invalid id or failed faithfulness (§7.2)
        if done.get("provider"):
            self.incr(f"provider.{done['provider']}")

    def snapshot(self) -> dict:
        return {"counters": dict(self.counters), "latency": latency_recorder.snapshot()}


metrics = Metrics()

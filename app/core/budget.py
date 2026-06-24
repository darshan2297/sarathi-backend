"""Per-turn cost & latency budget (plan §10.1) — wired in from Phase 1, not Phase 7.

A cold turn may fan out to 5–6 LLM calls; we track tokens + wall-clock per turn and keep a
rolling p95 so we can SEE budget pressure early and pull the levers in §10.1.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


def estimate_tokens(text: str) -> int:
    """Cheap, provider-agnostic token estimate (~4 chars/token). Replaced by real usage in Phase 2."""
    return max(1, len(text) // 4)


@dataclass
class TurnBudget:
    """Tracks one conversation turn's spend against the configured budgets."""

    token_budget: int
    latency_budget_ms: int
    _start: float = field(default_factory=time.perf_counter)
    tokens_in: int = 0
    tokens_out: int = 0
    llm_calls: int = 0

    def add_call(self, prompt_text: str, output_text: str) -> None:
        self.llm_calls += 1
        self.tokens_in += estimate_tokens(prompt_text)
        self.tokens_out += estimate_tokens(output_text)

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000

    @property
    def over_tokens(self) -> bool:
        return self.total_tokens > self.token_budget

    @property
    def over_latency(self) -> bool:
        return self.elapsed_ms > self.latency_budget_ms

    def summary(self) -> dict:
        return {
            "llm_calls": self.llm_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_tokens": self.total_tokens,
            "token_budget": self.token_budget,
            "over_tokens": self.over_tokens,
            "latency_ms": round(self.elapsed_ms, 1),
            "latency_budget_ms": self.latency_budget_ms,
            "over_latency": self.over_latency,
        }


class LatencyRecorder:
    """In-memory rolling latency samples → p50/p95. Swapped for real metrics in Phase 7."""

    def __init__(self, maxlen: int = 500) -> None:
        self._samples: list[float] = []
        self._maxlen = maxlen

    def record(self, ms: float) -> None:
        self._samples.append(ms)
        if len(self._samples) > self._maxlen:
            self._samples.pop(0)

    def _pct(self, p: float) -> float:
        if not self._samples:
            return 0.0
        ordered = sorted(self._samples)
        k = max(0, min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1)))))
        return ordered[k]

    def snapshot(self) -> dict:
        return {
            "count": len(self._samples),
            "p50_ms": round(self._pct(50), 1),
            "p95_ms": round(self._pct(95), 1),
        }


latency_recorder = LatencyRecorder()

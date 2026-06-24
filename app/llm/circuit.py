"""Circuit breaker (plan §9) — stop hammering a provider that's down; recover automatically.

States:
  closed     → calls allowed; failures counted.
  open       → calls blocked until `reset_s` elapses, then one trial is allowed (half-open).
  half_open  → a single trial call is permitted; success closes the circuit, failure re-opens it.
"""

from __future__ import annotations

import time
from enum import Enum


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, fail_threshold: int = 3, reset_s: float = 20.0) -> None:
        self._fail_threshold = fail_threshold
        self._reset_s = reset_s
        self._failures = 0
        self._state = State.CLOSED
        self._opened_at = 0.0

    @property
    def state(self) -> State:
        return self._state

    def allow(self) -> bool:
        if self._state is State.CLOSED:
            return True
        if self._state is State.OPEN:
            if (time.monotonic() - self._opened_at) >= self._reset_s:
                self._state = State.HALF_OPEN  # let one trial through
                return True
            return False
        # HALF_OPEN: allow the single trial
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._state = State.CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        if self._state is State.HALF_OPEN or self._failures >= self._fail_threshold:
            self._state = State.OPEN
            self._opened_at = time.monotonic()

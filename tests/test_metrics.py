"""Phase 7 proof — metrics counters. (from backend/)"""

from __future__ import annotations

from app.core.metrics import Metrics


def test_record_turn_increments_expected_counters():
    m = Metrics()
    m.record_turn({"mode": "open", "grounded": True, "degraded": True,
                   "safety": False, "verified": True, "provider": "stub"})
    c = m.snapshot()["counters"]
    assert c["turns"] == 1
    assert c["mode.open"] == 1
    assert c["grounded"] == 1
    assert c["degraded"] == 1
    assert c["provider.stub"] == 1
    assert "crisis" not in c


def test_verify_dropped_and_crisis_counted():
    m = Metrics()
    m.record_turn({"mode": "safety", "safety": True, "verified": True})
    m.record_turn({"mode": "open", "grounded": False, "verified": False, "provider": "openrouter"})
    c = m.snapshot()["counters"]
    assert c["crisis"] == 1
    assert c["verify_dropped"] == 1
    assert c["turns"] == 2

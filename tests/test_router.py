"""Phase 2 proof — router failover, circuit breaker, JSON robustness, cache, degraded flag.

Uses fake in-process providers so we prove the resilience logic with zero network. (from backend/)
"""

from __future__ import annotations

import asyncio

from app.cache.response_cache import ResponseCache
from app.core.budget import TurnBudget
from app.llm.base import ComposeContext
from app.llm.providers.base import Provider, ProviderError
from app.llm.router import Router

VALID = '{"spoken_guidance_hi":"वत्स, यह क्रोध स्वाभाविक है। {{VERSE}}।","verse_id":"BG2.47","practical_step_hi":"एक कदम","mode":"open"}'
FENCED = "```json\n" + VALID + "\n```"
WRAPPED = "ज़रूर, यह रहा उत्तर:\n" + VALID + "\nधन्यवाद।"

CANDIDATES = [{"id": "BG2.47", "chapter_theme_hi": "कर्म योग",
               "translation_hi": "तेरा अधिकार केवल कर्म में है", "tags": ["क्रोध"]}]


class FakeProvider(Provider):
    def __init__(self, name, reply=None, error=None, configured=True):
        self.name = name
        self._reply = reply
        self._error = error
        self._configured = configured
        self.calls = 0

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def complete(self, messages, *, json_mode=True, timeout=30.0, model=None) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._reply


def ctx() -> ComposeContext:
    return ComposeContext(user_message="गुस्से से नींद नहीं आती", candidates=CANDIDATES, response_mode="open")


def run(router: Router):
    return asyncio.run(router.compose(ctx(), TurnBudget(4000, 6000)))


def test_primary_success_not_degraded():
    p = FakeProvider("primary", reply=VALID)
    s = FakeProvider("secondary", reply=VALID)
    r = run(Router(providers=[(p, True), (s, False)], cache=None, max_retries=0, retry_base_s=0))
    assert r.provider == "primary" and r.degraded is False
    assert r.verse_id == "BG2.47"
    assert s.calls == 0  # secondary never touched


def test_failover_marks_degraded():
    p = FakeProvider("primary", error=ProviderError("down"))
    s = FakeProvider("secondary", reply=VALID)
    r = run(Router(providers=[(p, True), (s, False)], cache=None, max_retries=0, retry_base_s=0))
    assert r.provider == "secondary" and r.degraded is True
    assert p.calls == 1 and s.calls == 1


def test_circuit_opens_after_threshold():
    # primary fails every call; after the breaker's threshold it should be skipped entirely.
    p = FakeProvider("primary", error=ProviderError("down"))
    s = FakeProvider("secondary", reply=VALID)
    router = Router(providers=[(p, True), (s, False)], cache=None, max_retries=0, retry_base_s=0)
    for _ in range(3):  # default circuit_fail_threshold = 3
        run(router)
    calls_before = p.calls
    run(router)  # 4th turn
    assert p.calls == calls_before  # primary skipped — circuit open
    assert s.calls == 4


def test_json_parsing_robustness():
    for reply in (FENCED, WRAPPED):
        p = FakeProvider("primary", reply=reply)
        r = run(Router(providers=[(p, True)], cache=None, max_retries=0, retry_base_s=0))
        assert "{{VERSE}}" in r.spoken_guidance_hi and r.verse_id == "BG2.47"


def test_verse_id_constrained_to_candidates():
    bogus = '{"spoken_guidance_hi":"वत्स।","verse_id":"BG99.99","practical_step_hi":null,"mode":"open"}'
    p = FakeProvider("primary", reply=bogus)
    r = run(Router(providers=[(p, True)], cache=None, max_retries=0, retry_base_s=0))
    assert r.verse_id is None  # hallucinated id dropped


def test_cache_hit_skips_provider():
    p = FakeProvider("primary", reply=VALID)
    cache = ResponseCache(maxsize=10)
    router = Router(providers=[(p, True)], cache=cache, max_retries=0, retry_base_s=0)
    run(router)
    run(router)  # identical input
    assert p.calls == 1  # second served from cache
    assert cache.stats()["hits"] == 1


def test_all_fail_uses_stub_fallback():
    p = FakeProvider("primary", error=ProviderError("down"))
    s = FakeProvider("secondary", error=ProviderError("down"))
    r = run(Router(providers=[(p, True), (s, False)], cache=None, max_retries=0, retry_base_s=0))
    assert r.provider == "stub" and r.degraded is True
    assert r.spoken_guidance_hi  # stub still produced guidance

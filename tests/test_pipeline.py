"""Phase 1 proof tests — especially the STRUCTURAL anti-hallucination guarantee (plan §7.1).

Run:  pytest -q   (from backend/)
"""

from __future__ import annotations

import asyncio

from app.core.budget import TurnBudget
from app.graph.pipeline import inject_verse, run_turn
from app.llm.base import VERSE_PLACEHOLDER, ComposeContext, ComposeResult
from app.retrieval.corpus import get_corpus


def collect(user_message: str, history=None) -> list[dict]:
    async def _run():
        return [ev async for ev in run_turn(
            user_message=user_message, history=history or [], turn_id="test", stream_delay_ms=0)]
    return asyncio.run(_run())


def streamed_text(events: list[dict]) -> str:
    return "".join(e["text"] for e in events if e["type"] == "token")


# --- the core guarantee --------------------------------------------------------------------

def test_model_never_emits_sanskrit_but_injection_adds_it():
    corpus = get_corpus()
    verse = corpus.get_verse("BG2.47")
    canonical = verse["sanskrit"].splitlines()[0].rstrip("।॥ ")

    # the stub's raw output must contain ONLY the placeholder, never the Sanskrit
    from app.llm.stub import StubLLM

    ctx = ComposeContext(
        user_message="गुस्से से नींद नहीं आती",
        candidates=[verse],
        response_mode="open",
    )
    raw = asyncio.run(StubLLM().compose(ctx, TurnBudget(4000, 6000)))
    assert VERSE_PLACEHOLDER in raw.spoken_guidance_hi
    assert canonical not in raw.spoken_guidance_hi  # model did NOT produce scripture

    # injection pulls the Sanskrit from the corpus
    rendered, card = inject_verse(raw.spoken_guidance_hi, raw.verse_id, corpus)
    assert canonical in rendered
    assert VERSE_PLACEHOLDER not in rendered
    assert card and card["id"] == "BG2.47" and card["sanskrit"] == verse["sanskrit"]


def test_invalid_verse_id_is_dropped_no_fabrication():
    corpus = get_corpus()
    text = f"एक सत्य — {VERSE_PLACEHOLDER}।"
    rendered, card = inject_verse(text, "BG99.99", corpus)  # not in corpus
    assert card is None
    assert VERSE_PLACEHOLDER not in rendered
    assert "«" not in rendered  # no fabricated verse rendered


# --- behaviour by path ---------------------------------------------------------------------

def test_open_turn_is_grounded_with_verse_card():
    events = collect("मेरे पिता का देहांत हो गया, स्वीकार नहीं कर पा रहा")
    done = next(e for e in events if e["type"] == "done")
    cards = [e for e in events if e["type"] == "verse_card"]
    assert done["grounded"] is True
    assert done["verse_id"] is not None
    assert len(cards) == 1
    assert cards[0]["sanskrit"]  # canonical text present


def test_close_mode_has_no_verse():
    events = collect("धन्यवाद, इससे मदद मिली", history=[{"role": "user", "text": "..."}])
    done = next(e for e in events if e["type"] == "done")
    assert done["mode"] == "close"
    assert done["verse_id"] is None
    assert not any(e["type"] == "verse_card" for e in events)


def test_budget_is_tracked_and_within_limits():
    events = collect("परिणाम की चिंता से नींद नहीं आती")
    done = next(e for e in events if e["type"] == "done")
    b = done["budget"]
    assert b["llm_calls"] >= 1
    assert b["total_tokens"] > 0
    assert b["over_tokens"] is False

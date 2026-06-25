"""Phase 3 proof — LangGraph multi-agent flow + understanding/retrieval behaviour. (from backend/)"""

from __future__ import annotations

import asyncio

from app.core.budget import TurnBudget
from app.graph.build import build_graph
from app.graph.nodes.retrieval import retrieval_node
from app.graph.nodes.understanding import understanding_node
from app.graph.pipeline import run_turn


def _budget():
    return TurnBudget(4000, 6000)


def collect(user_message: str, history=None) -> list[dict]:
    async def _run():
        return [ev async for ev in run_turn(
            user_message=user_message, history=history or [], turn_id="t", stream_delay_ms=0)]
    return asyncio.run(_run())


# --- graph wiring ---

def test_graph_compiles_with_all_nodes():
    g = build_graph()
    assert {"understanding", "retrieve", "compose", "verify", "output"} <= set(g.nodes)


def test_full_turn_open_is_grounded():
    events = collect("मेरे पिता का देहांत हो गया, मैं स्वीकार नहीं कर पा रहा")
    done = next(e for e in events if e["type"] == "done")
    metas = [e for e in events if e["type"] == "meta" and "mode" in e]
    statuses = [e["node"] for e in events if e["type"] == "status"]
    assert done["grounded"] is True and done["verse_id"] is not None
    assert any(e["type"] == "verse_card" for e in events)
    assert metas and metas[0]["mode"] == "open"
    assert "understanding" in statuses and "compose" in statuses  # node status emitted


# --- understanding heuristic (no LLM here → deterministic path) ---

def test_understanding_modes():
    def mode(msg, hist):
        return asyncio.run(understanding_node(
            {"user_message": msg, "thread_history": hist, "budget": _budget()}))["response_mode"]

    assert mode("मुझे बहुत गुस्सा आ रहा है", []) == "open"
    assert mode("धन्यवाद, इससे मदद मिली", [{"role": "user", "text": "x"}]) == "close"
    assert mode("गुस्सा कैसे छोड़ूँ", [{"role": "user", "text": "x"}]) == "deepen"
    assert mode("पर रोज़ उसका सामना करना पड़ता है", [{"role": "user", "text": "x"}]) == "continue"


def test_greeting_routes_to_greet_not_open():
    def out(msg, hist=None):
        return asyncio.run(understanding_node(
            {"user_message": msg, "thread_history": hist or [], "budget": _budget()}))

    for hello in ("Hello", "hi", "नमस्ते", "नमस्ते सारथी 🙏", "namaste guruji", "  Hey!  "):
        assert out(hello)["response_mode"] == "greet", hello
    # a greeting carrying a real concern is NOT a pure greeting → stays a substantive turn
    assert out("नमस्ते, मुझे रात को नींद नहीं आती")["response_mode"] == "open"


def test_greeting_turn_has_no_verse():
    events = collect("Hello")
    done = next(e for e in events if e["type"] == "done")
    metas = [e for e in events if e["type"] == "meta" and "mode" in e]
    assert metas and metas[0]["mode"] == "greet"
    assert done["verse_id"] is None and done["grounded"] is False
    assert not any(e["type"] == "verse_card" for e in events)  # no scripture on a hello


def test_understanding_reroutes_to_crisis_on_self_harm():
    # the 2nd safety layer (plan §8): understanding flags self-harm → reroute to crisis_response.
    # Under the test stub there's no LLM, so this exercises the keyword backstop in the node.
    out = asyncio.run(understanding_node(
        {"user_message": "life is pointless, I don't want to be here anymore",
         "thread_history": [], "budget": _budget()}))
    assert out.get("safety_flag") is True and out.get("route") == "crisis"
    assert out.get("crisis_phase") == "entry"


def test_understanding_detects_emotion():
    out = asyncio.run(understanding_node(
        {"user_message": "पार्टनर ने धोखा दिया, गुस्सा आता है", "thread_history": [], "budget": _budget()}))
    assert out["emotion"] == "क्रोध"


# --- retrieval ---

def test_retrieval_fallback_returns_candidates():
    out = asyncio.run(retrieval_node(
        {"response_mode": "open", "concern": "धोखे से गुस्सा", "user_message": "x", "budget": _budget()}))
    assert out["candidates"] and all("id" in c for c in out["candidates"])


def test_retrieval_skipped_on_continue():
    out = asyncio.run(retrieval_node(
        {"response_mode": "continue", "concern": "गुस्सा", "user_message": "x", "budget": _budget()}))
    assert out["candidates"] == []


def test_retrieval_skipped_on_offtopic():
    # cloud QA #3 — an off-topic question must NOT get a forced verse
    out = asyncio.run(retrieval_node(
        {"response_mode": "open", "intent": "off-topic",
         "concern": "delhi weather", "user_message": "delhi ka mausam", "budget": _budget()}))
    assert out["candidates"] == []


# --- render: citation injection (cloud QA #4 — no duplicate citation) ---

def test_injected_citation_not_duplicated():
    from app.graph.render import inject_verse
    from app.retrieval.corpus import get_corpus
    corpus = get_corpus()
    # the model wrongly typed its OWN citation right before the placeholder
    text = "गहराई में देखो — श्रीमद्भगवद्गीता (२.२०) — {{VERSE}} यही सार है।"
    rendered, card = inject_verse(text, "BG2.20", corpus)
    assert rendered.count("श्रीमद्भगवद्गीता") == 1, rendered   # exactly one citation, not two
    assert "{{VERSE}}" not in rendered and card["id"] == "BG2.20"


def test_extra_placeholders_are_dropped():
    from app.graph.render import inject_verse
    from app.retrieval.corpus import get_corpus
    rendered, _ = inject_verse("{{VERSE}} ... और {{VERSE}}", "BG2.20", get_corpus())
    assert "{{VERSE}}" not in rendered
    assert rendered.count("«") == 1   # injected exactly once


# --- status: no "searching scriptures" on a no-verse turn (cloud QA #6) ---

def test_no_retrieve_status_on_close():
    events = collect("धन्यवाद, इससे मदद मिली",
                     history=[{"role": "user", "text": "x"}, {"role": "sarathi", "text": "y"}])
    status_nodes = [e.get("node") for e in events if e["type"] == "status"]
    assert "retrieve" not in status_nodes

"""Language handling regression guard (QA 2026-06-25: H-1 explicit requests, H-2 mixed scaffolding,
H-3 Gujarati support).

Pinned here (all deterministic — explicit-request detection and the localized labels are LLM-free):
  • an explicit "reply in English" request is honoured AND sticks across later turns,
  • the practical-step label and sensitive-topic disclaimer follow the reply language (not hardcoded
    Hindi), so an English turn is no longer language-mixed in its scaffolding,
  • Gujarati ("gu") is a supported reply language and flows through to the labels.
"""

from __future__ import annotations

import asyncio

from app.core import i18n
from app.core.budget import TurnBudget
from app.graph.nodes.understanding import sticky_language, understanding_node
from app.graph.pipeline import run_turn


def _budget():
    return TurnBudget(4000, 6000)


def _understand(msg, hist=None):
    return asyncio.run(understanding_node(
        {"user_message": msg, "thread_history": hist or [], "budget": _budget()}))


def collect(user_message: str, history=None) -> list[dict]:
    async def _run():
        return [ev async for ev in run_turn(
            user_message=user_message, history=history or [], turn_id="t", stream_delay_ms=0)]
    return asyncio.run(_run())


def text_of(events) -> str:
    return "".join(e["text"] for e in events if e["type"] == "token")


# --- H-1: explicit language request detection + stickiness -----------------------------------------

def test_explicit_request_detected_in_many_phrasings():
    for msg in ("Please reply in English", "answer in english from now on", "english only please",
                "अब अंग्रेजी में बताओ"):
        assert sticky_language(msg, []) == "en", msg
    assert sticky_language("कृपया हिंदी में जवाब दो", []) == "hi"
    assert sticky_language("please answer in gujarati", []) == "gu"
    # a bare mention is NOT a switch request
    assert sticky_language("I studied English literature in college", []) is None
    assert sticky_language("मुझे थोड़ा गुस्सा आता है", []) is None


def test_language_request_is_sticky_across_turns():
    hist = [{"role": "user", "text": "Please reply in English from now on"},
            {"role": "sarathi", "text": "Of course, my friend."}]
    # a later, language-neutral message still gets English (preference persists)
    assert sticky_language("why do I keep getting angry?", hist) == "en"
    # but the current turn overrides the sticky preference
    assert sticky_language("अब से हिंदी में बताओ", hist) == "hi"


def test_understanding_honours_explicit_request_over_detection():
    out = _understand("I feel lost about my purpose. Please reply in English.")
    assert out["language"] == "en"


# --- H-2: scaffolding follows the reply language ---------------------------------------------------

def test_step_label_is_localized_not_hardcoded_hindi():
    # explicit English request → deterministic language=en even without an LLM
    events = collect("My mind is restless and I can't focus. Please reply in English.")
    body = text_of(events)
    assert "Today's small step:" in body          # English label, not "आज का छोटा कदम:"
    assert "आज का छोटा कदम" not in body


def test_disclaimer_is_localized_on_sensitive_emotion():
    events = collect("I feel so much anger about this betrayal. Reply in English.")  # emotion=क्रोध
    body = text_of(events)
    assert "gentle reminder" in body              # English disclaimer
    assert "विशेषज्ञ" not in body                 # not the hardcoded Hindi one


# --- H-3: Gujarati is a supported language ---------------------------------------------------------

def test_gujarati_is_supported_and_flows_to_labels():
    assert "gu" in i18n.LANGUAGES
    assert i18n.step_label("gu") == "આજનું એક નાનું પગલું"
    assert "ગીતા" in i18n.disclaimer("gu") or "નિષ્ણાત" in i18n.disclaimer("gu")
    # an explicit Gujarati request routes the reply language to gu
    assert sticky_language("please answer in gujarati", []) == "gu"


def test_i18n_falls_back_to_hindi_for_unknown_language():
    assert i18n.normalize(None) == "hi"
    assert i18n.normalize("fr") == "hi"
    assert i18n.step_label("xx") == "आज का छोटा कदम"

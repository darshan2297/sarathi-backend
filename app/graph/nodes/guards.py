"""Guardrail graph nodes (plan §4 nodes 1 & 7, §8).

input_guard   : runs FIRST, EVERY turn. Crisis (self-harm) → short-circuit to crisis_response.
                Harm-to-others → firm-kind refusal. Jailbreak → flag (persona stays fixed).
crisis_response: compassionate Hindi + verified helplines; skips the normal flow.
output_guard  : final pass — append a gentle disclaimer on sensitive topics, strip any leftover
                {{VERSE}} placeholder, guarantee non-empty Hindi output.
"""

from __future__ import annotations

from app.core.i18n import disclaimer as localized_disclaimer
from app.core.logging import get_logger
from app.graph.state import GraphState
from app.guardrails.crisis import (
    CRISIS_STICKY_TURNS,
    HARM_OTHERS_RESPONSE_HI,
    classify_crisis_followup,
    crisis_payload,
    detect_crisis,
    detect_harm_to_others,
    turns_since_crisis,
)
from app.guardrails.safety import detect_jailbreak
from app.llm.base import VERSE_PLACEHOLDER

log = get_logger("sarathi.guard")

_SENSITIVE_EMOTIONS = {"शोक", "क्रोध"}


async def input_guard_node(state: GraphState) -> dict:
    msg = state["user_message"]
    history = state.get("thread_history", [])
    flags: list[str] = []

    # Crisis stickiness is BOUNDED (cloud QA #2): right after a crisis we never fall into the
    # cheerful normal close, but we also don't latch the helpline onto every later greeting for the
    # whole session. A fresh crisis re-arms the entry message; for up to CRISIS_STICKY_TURNS
    # follow-up turns we classify into the right exit response; after that the thread is released.
    fresh_crisis = detect_crisis(msg)
    since = turns_since_crisis(history)
    if fresh_crisis or (since is not None and since < CRISIS_STICKY_TURNS):
        if fresh_crisis:
            phase = "entry"
        else:
            phase = {"not_safe": "escalate", "goodbye": "safe_close",
                     "still_talking": "support"}[classify_crisis_followup(msg)]
        log.warning("crisis_route", turn_id=state.get("turn_id"), phase=phase, fresh=fresh_crisis)
        return {"safety_flag": True, "route": "crisis", "crisis_phase": phase, "flags": ["crisis"]}

    if detect_jailbreak(msg):
        flags.append("jailbreak")
        log.info("jailbreak_flagged", turn_id=state.get("turn_id"))

    if detect_harm_to_others(msg):
        flags.append("harm_to_others")

    return {"safety_flag": False, "route": "continue", "flags": flags}


async def crisis_response_node(state: GraphState) -> dict:
    phase = state.get("crisis_phase", "entry")
    # vary SUPPORT wording per turn so a flagged thread never loops identical text
    variant = len(state.get("thread_history", [])) // 2
    payload = crisis_payload(phase, variant=variant)
    return {
        "response_mode": "safety",
        "rendered_text": payload["message"],
        "safety_payload": payload,
        "verse_id": None,
        "verse_card": None,
        "practical_step_hi": None,
        "verified": True,
        "provider": "guardrail",
        "degraded": False,
    }


async def output_guard_node(state: GraphState) -> dict:
    # harm-to-others (non-crisis) → replace with firm-kind refusal
    if "harm_to_others" in (state.get("flags") or []) and not state.get("safety_flag"):
        return {"rendered_text": HARM_OTHERS_RESPONSE_HI, "verse_id": None,
                "verse_card": None, "practical_step_hi": None}

    text = state.get("rendered_text", "") or ""
    text = text.replace(VERSE_PLACEHOLDER, "").strip()  # safety net: never leak the placeholder

    updates: dict = {"rendered_text": text}

    # gentle disclaimer on sensitive emotions (not on the crisis path — that has its own message),
    # in the reply language so the answer isn't language-mixed (QA H-2)
    if not state.get("safety_flag") and state.get("emotion") in _SENSITIVE_EMOTIONS:
        updates["disclaimer"] = localized_disclaimer(state.get("language"))

    return updates

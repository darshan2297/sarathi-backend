"""Guardrail graph nodes (plan §4 nodes 1 & 7, §8).

input_guard   : runs FIRST, EVERY turn. Crisis (self-harm) → short-circuit to crisis_response.
                Harm-to-others → firm-kind refusal. Jailbreak → flag (persona stays fixed).
crisis_response: compassionate Hindi + verified helplines; skips the normal flow.
output_guard  : final pass — append a gentle disclaimer on sensitive topics, strip any leftover
                {{VERSE}} placeholder, guarantee non-empty Hindi output.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.graph.state import GraphState
from app.guardrails.crisis import (
    HARM_OTHERS_RESPONSE_HI,
    crisis_payload,
    detect_crisis,
    detect_harm_to_others,
)
from app.guardrails.safety import detect_jailbreak
from app.llm.base import VERSE_PLACEHOLDER

log = get_logger("sarathi.guard")

_SENSITIVE_EMOTIONS = {"शोक", "क्रोध"}
_DISCLAIMER_HI = ("(कोमल स्मरण: मैं गीता से राह दिखाता हूँ; यदि यह पीड़ा बहुत भारी लगे तो किसी अपने "
                  "या किसी विशेषज्ञ से बात करने में संकोच मत करना।)")


async def input_guard_node(state: GraphState) -> dict:
    msg = state["user_message"]
    flags: list[str] = []

    if detect_crisis(msg):
        log.warning("crisis_detected", turn_id=state.get("turn_id"))
        return {"safety_flag": True, "route": "crisis", "flags": ["crisis"]}

    if detect_jailbreak(msg):
        flags.append("jailbreak")
        log.info("jailbreak_flagged", turn_id=state.get("turn_id"))

    if detect_harm_to_others(msg):
        flags.append("harm_to_others")

    return {"safety_flag": False, "route": "continue", "flags": flags}


async def crisis_response_node(state: GraphState) -> dict:
    payload = crisis_payload()
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

    # gentle disclaimer on sensitive emotions (not on the crisis path — that has its own message)
    if not state.get("safety_flag") and state.get("emotion") in _SENSITIVE_EMOTIONS:
        updates["disclaimer"] = _DISCLAIMER_HI

    return updates

"""Understanding agent (plan §4 node 2, §2.6).

Detects language + intent + emotion + the core concern, and — reading the thread — sets turn_type
and the derived response_mode that shapes the whole answer. LLM-driven when a provider is available;
deterministic heuristic otherwise (so the graph runs with no key).
"""

from __future__ import annotations

import re

from app.graph.nodes.common import llm_json
from app.graph.state import GraphState
from app.llm.prompts import build_understanding_messages

_MODES = {"greet", "open", "continue", "deepen", "steer", "close"}
_TURNS = {"greeting", "new-topic", "follow-up", "deeper-request", "spiraling", "closing"}

# A bare hello must be met with a hello — never a diagnosis. We detect a pure greeting and route it
# to `greet` mode (no retrieval, no verse, no problem-solving). "hello, I lost my job" is NOT a pure
# greeting — it carries a real concern, so it still flows to `open`. (plan §2.6 — open warmly first.)
_GREETINGS = (
    "नमस्ते", "नमस्कार", "प्रणाम", "राम राम", "जय श्री कृष्ण", "जय श्रीकृष्ण", "हरे कृष्ण",
    "हरि ॐ", "सुप्रभात", "शुभ प्रभात", "हेलो", "हैलो", "हाय",
    "hello", "helo", "hii", "hi", "hey", "hiya", "yo", "namaste", "namaskar", "pranam",
    "ram ram", "good morning", "good afternoon", "good evening", "greetings",
)
# vocatives / fillers that may accompany a greeting without making it a real concern
_GREET_FILLER = (
    "sarathi", "सारथी", "guruji", "गुरुजी", "guru", "गुरु", "ji", "जी",
    "ॐ", "om", "there", "वत्स", "मित्र", "दोस्त", "please",
)


def _is_greeting(user_message: str) -> bool:
    msg = user_message.strip().lower()
    if not msg or len(msg) > 40:
        return False
    if not any(g in msg for g in _GREETINGS):
        return False
    residue = msg
    for token in (*_GREETINGS, *_GREET_FILLER):
        residue = residue.replace(token, " ")
    # keep only latin + devanagari letters; if almost nothing meaningful is left, it's just a greeting
    residue = re.sub(r"[^a-zऀ-ॿ]+", " ", residue).strip()
    return len(residue) < 3


_GRATITUDE = ("धन्यवाद", "शुक्रिया", "thank", "मदद मिली", "समझ गया", "ठीक है")
_DEEPEN = ("गहरा", "और बताओ", "कैसे छोड़", "how", "कैसे", "क्यों")
_EMOTION = {
    "क्रोध": ("क्रोध", "गुस्सा", "धोखा", "anger", "betray"),
    "शोक": ("शोक", "देहांत", "मृत्यु", "grief", "death", "loss"),
    "चिंता": ("चिंता", "डर", "नींद", "anxiety", "fear", "परिणाम"),
    "भ्रम": ("दिशा", "भटक", "उद्देश्य", "lost", "तुलना", "confus"),
}


def _emotion_for(msg: str) -> str:
    for emo, kws in _EMOTION.items():
        if any(k in msg for k in kws):
            return emo
    return "none"


def _greeting_result(history: list[dict]) -> dict:
    return {
        "language": "hi",
        "intent": "smalltalk",
        "emotion": "none",
        "concern": "",
        "turn_type": "greeting",
        "response_mode": "greet",
        "depth_level": len(history) // 2,
    }


def _heuristic(user_message: str, history: list[dict]) -> dict:
    msg = user_message.lower()
    if any(g in msg for g in _GRATITUDE) and len(msg) < 40:
        mode, turn = "close", "closing"
    elif not history:
        mode, turn = "open", "new-topic"
    elif any(d in msg for d in _DEEPEN):
        mode, turn = "deepen", "deeper-request"
    else:
        mode, turn = "continue", "follow-up"
    return {
        "language": "hi",
        "intent": "life-problem",
        "emotion": _emotion_for(msg),
        "concern": user_message[:60],
        "turn_type": turn,
        "response_mode": mode,
    }


async def understanding_node(state: GraphState) -> dict:
    um = state["user_message"]
    hist = state.get("thread_history", [])

    # Structural guarantee: a pure greeting is met with a greeting — listen first, never diagnose.
    # Resolved here (no LLM call) so it can't drift even if a model misreads the turn.
    if _is_greeting(um):
        return _greeting_result(hist)

    data = await llm_json(build_understanding_messages(um, hist), state["budget"])
    if not data:
        data = _heuristic(um, hist)

    mode = data.get("response_mode")
    if mode not in _MODES:
        mode = _heuristic(um, hist)["response_mode"]
    turn = data.get("turn_type") if data.get("turn_type") in _TURNS else "new-topic"

    return {
        "language": data.get("language", "hi"),
        "intent": data.get("intent", "life-problem"),
        "emotion": data.get("emotion", "none"),
        "concern": data.get("concern") or um[:60],
        "turn_type": turn,
        "response_mode": mode,
        "depth_level": len(hist) // 2,
    }

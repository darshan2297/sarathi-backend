"""Understanding agent (plan §4 node 2, §2.6).

Detects language + intent + emotion + the core concern, and — reading the thread — sets turn_type
and the derived response_mode that shapes the whole answer. LLM-driven when a provider is available;
deterministic heuristic otherwise (so the graph runs with no key).
"""

from __future__ import annotations

import re

from app.graph.nodes.common import llm_json
from app.graph.state import GraphState
from app.guardrails.crisis import detect_crisis
from app.llm.prompts import build_understanding_messages

_MODES = {"greet", "open", "continue", "deepen", "steer", "close", "out_of_scope"}
_TURNS = {"greeting", "new-topic", "follow-up", "deeper-request", "spiraling", "closing"}

# Out-of-scope detection (plan §8 / triage 2026-06-25). When the LITERAL ask is professional advice
# Sarathi must not give — stock/financial picks, medical diagnosis/treatment, legal advice — we route
# to `out_of_scope`: decline the surface question, reframe to the deeper concern (fear of the future,
# security, attachment to outcomes) which IS in scope. Triggers are domain-SPECIFIC professional terms,
# NOT bare "money"/"health" — "मुझे पैसे की चिंता है" stays an ordinary life-problem answered normally.
_OUT_OF_SCOPE = {
    "financial": (
        "invest", "investment", "stock", "stocks", "share market", "shares", "mutual fund",
        "mutual funds", "crypto", "bitcoin", "portfolio", "trading", "which stock", "best stock",
        "शेयर", "निवेश", "म्यूचुअल फंड", "म्यूचुअल फण्ड", "क्रिप्टो", "बिटकॉइन", "कहाँ लगाऊँ",
        "कहाँ लगाऊं", "कहाँ निवेश",
    ),
    "medical": (
        "diagnose", "diagnosis", "prescribe", "prescription", "dosage", "what medicine",
        "which medicine", "treatment for", "symptoms of", "दवा", "दवाई", "इलाज", "खुराक", "मर्ज़",
    ),
    "legal": (
        "lawsuit", "legal advice", "file a case", "court case", "sue him", "sue her", "sue them",
        "मुकदमा", "क़ानूनी सलाह", "कानूनी सलाह", "केस दर्ज",
    ),
}
# The deeper, in-scope concern under any out-of-scope ask — phrased so the retriever's curated
# theme_map lands on the अनासक्ति / परिणाम-की-चिंता verses (BG2.47/2.48), the right teaching here.
_OUT_OF_SCOPE_CONCERN = "कल का डर, भविष्य की चिंता, सुरक्षा की चाह, परिणाम से मोह"


def _out_of_scope_domain(user_message: str) -> str | None:
    low = user_message.lower()
    for domain, needles in _OUT_OF_SCOPE.items():
        if any(n in low for n in needles):
            return domain
    return None

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


# Explicit language requests (QA H-1). When the user asks to be answered in a given language, that
# wins over auto-detection AND must STICK across later turns. State is rebuilt every turn, so (like
# crisis stickiness) the preference is re-derived from thread_history each turn. Substrings are matched
# lowercased; phrasings require an explicit "in <lang>" / "<lang> me(in)" request, not a bare mention,
# so "I studied English" doesn't switch the reply language.
_LANG_REQUESTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("en", ("in english", "into english", "reply in english", "answer in english",
            "respond in english", "speak in english", "talk in english", "english only",
            "english me", "english mein", "english में", "अंग्रेजी में", "अंग्रेज़ी में",
            "इंग्लिश में", "इंग्लिश मे")),
    ("gu", ("in gujarati", "gujarati me", "gujarati mein", "gujarati only",
            "ગુજરાતીમાં", "ગુજરાતી માં", "ગુજરાતી મા", "गुजराती में")),
    ("hinglish", ("in hinglish", "hinglish me", "hinglish mein", "hinglish only")),
    ("hi", ("in hindi", "hindi me", "hindi mein", "hindi only", "हिंदी में", "हिन्दी में",
            "हिंदी मे")),
)


def _explicit_language(text: str) -> str | None:
    low = (text or "").lower()
    for lang, needles in _LANG_REQUESTS:
        if any(n in low for n in needles):
            return lang
    return None


def sticky_language(user_message: str, history: list[dict] | None) -> str | None:
    """The most recent explicit language request — this turn's message wins, else the latest such
    request from an earlier USER turn. None if the user never asked, so auto-detection stands."""
    cur = _explicit_language(user_message)
    if cur:
        return cur
    pref = None
    for h in (history or []):
        if h.get("role") == "user":
            got = _explicit_language(h.get("text", ""))
            if got:
                pref = got
    return pref


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
    # Out-of-scope professional advice wins over the topic heuristics below: the literal ask must be
    # declined and reframed to the in-scope concern (so we set that concern, not the surface text).
    if _out_of_scope_domain(user_message):
        return {
            "language": "hi",
            "intent": "life-problem",   # NOT off-topic: the UNDERLYING concern is in scope (gets a verse)
            "emotion": "चिंता",
            "concern": _OUT_OF_SCOPE_CONCERN,
            "turn_type": "new-topic",
            "response_mode": "out_of_scope",
        }
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


def heuristic_understanding(user_message: str, history: list[dict] | None = None) -> dict:
    """LLM-free classification — the deterministic safety net used when no provider is up.

    Exposed for the eval harness so scope/mode routing is measured REPRODUCIBLY, independent of
    live-model sampling — the same role `detect_crisis` plays for safety routing. Mirrors the
    node's own resolution order: a pure greeting first, then the topic/scope heuristic.
    """
    history = history or []
    if _is_greeting(user_message):
        return _greeting_result(history)
    return _heuristic(user_message, history)


async def understanding_node(state: GraphState) -> dict:
    um = state["user_message"]
    hist = state.get("thread_history", [])

    # Explicit language request (QA H-1) overrides auto-detection and persists across turns.
    lang_pref = sticky_language(um, hist)

    # Structural guarantee: a pure greeting is met with a greeting — listen first, never diagnose.
    # Resolved here (no LLM call) so it can't drift even if a model misreads the turn.
    if _is_greeting(um):
        res = _greeting_result(hist)
        if lang_pref:
            res["language"] = lang_pref
        return res

    # classification task → cheap/fast model (latency, plan §10.1)
    data = await llm_json(build_understanding_messages(um, hist), state["budget"], cheap=True)
    if not data:
        data = _heuristic(um, hist)

    mode = data.get("response_mode")
    if mode not in _MODES:
        mode = _heuristic(um, hist)["response_mode"]
    turn = data.get("turn_type") if data.get("turn_type") in _TURNS else "new-topic"

    result = {
        # explicit request (this turn or a sticky earlier one) wins over the model's auto-detection
        "language": lang_pref or data.get("language", "hi"),
        "intent": data.get("intent", "life-problem"),
        "emotion": data.get("emotion", "none"),
        "concern": data.get("concern") or um[:60],
        "turn_type": turn,
        "response_mode": mode,
        "depth_level": len(hist) // 2,
    }

    # SAFETY net (plan §8): the keyword detector in input_guard runs first; this is the SECOND layer
    # that catches indirect/passive ideation keywords miss (e.g. "life is pointless, I don't want to
    # be here"). If the model — or a keyword backstop — flags self-harm, reroute to the crisis path.
    if bool(data.get("self_harm")) or detect_crisis(um):
        result.update({"safety_flag": True, "crisis_phase": "entry", "route": "crisis"})
    return result

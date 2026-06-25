"""Localized UI scaffolding (plan §2.5) — the fixed bits the backend wraps around the LLM answer.

The guidance body itself is written by the composer in the user's language. But two pieces were
appended by the backend in HARDCODED Hindi (QA H-2, 2026-06-25) — the practical-step label and the
sensitive-topic disclaimer — which made every answer language-mixed even when the user asked for
English. These are keyed by the resolved reply `language`; an unknown code falls back to Hindi (the
default voice). Sanskrit verses are unaffected — they are always injected in their original script.
"""

from __future__ import annotations

# Supported reply languages. `gu` (Gujarati) added with QA H-3.
LANGUAGES = ("hi", "hinglish", "en", "gu")

_STEP_LABEL = {
    "hi": "आज का छोटा कदम",
    "hinglish": "Aaj ka chhota kadam",
    "en": "Today's small step",
    "gu": "આજનું એક નાનું પગલું",
}

_DISCLAIMER = {
    "hi": ("(कोमल स्मरण: मैं गीता से राह दिखाता हूँ; यदि यह पीड़ा बहुत भारी लगे तो किसी अपने या किसी "
           "विशेषज्ञ से बात करने में संकोच मत करना।)"),
    "hinglish": ("(Komal smaran: main Gita se raah dikhata hoon; yadi yeh peeda bahut bhaari lage to "
                 "kisi apne ya kisi visheshagya se baat karne mein sankoch mat karna.)"),
    "en": ("(A gentle reminder: I share guidance from the Gita; if this pain ever feels too heavy, "
           "please don't hesitate to reach out to someone you trust or a professional.)"),
    "gu": ("(કોમળ સ્મરણ: હું ગીતામાંથી માર્ગ બતાવું છું; જો આ પીડા ખૂબ ભારે લાગે તો કોઈ પોતાના કે કોઈ "
           "નિષ્ણાત સાથે વાત કરવામાં સંકોચ ન કરો.)"),
}


def normalize(language: str | None) -> str:
    """Map any reply-language code to a supported one, defaulting to Hindi (Sarathi's base voice)."""
    return language if language in LANGUAGES else "hi"


def step_label(language: str | None) -> str:
    """Label preceding the practical step, e.g. 'Today's small step' / 'आज का छोटा कदम'."""
    return _STEP_LABEL[normalize(language)]


def disclaimer(language: str | None) -> str:
    """Gentle professional-help disclaimer appended on sensitive emotions, in the reply language."""
    return _DISCLAIMER[normalize(language)]

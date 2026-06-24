"""Security guardrails (plan §8) — jailbreak / prompt-injection awareness.

Sarathi's behaviour can't actually be overridden (the system prompt is fixed and the corpus is fed as
delimited DATA, never instructions — plan §8). This detector flags obvious attempts so we can log them
and keep the persona steady; it does not need to mutate the message.
"""

from __future__ import annotations

_JAILBREAK = (
    "ignore previous", "ignore all previous", "ignore your instructions", "disregard the above",
    "system prompt", "you are now", "pretend you are", "developer mode", "jailbreak",
    "act as", "forget your rules", "जो तुम्हें कहा गया है भूल जाओ", "अपने नियम भूल", "सिस्टम प्रॉम्प्ट",
)


def detect_jailbreak(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in _JAILBREAK)

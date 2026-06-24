"""Shared LangGraph state (plan §4).

Each node writes its own keys (no concurrent writers), so plain last-write semantics are fine — no
custom reducers needed. `budget` is a shared TurnBudget object mutated in place across nodes.
"""

from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    # --- inputs ---
    user_message: str
    thread_history: list[dict]
    turn_id: str
    budget: Any  # TurnBudget (shared, mutated in place)
    user_id: str | None     # set for logged-in members (plan §1, §6)
    tier: str               # "guest" | "member"
    memories: list          # recalled past episodes (member only)

    # --- input guardrail (plan §8) ---
    safety_flag: bool       # crisis / self-harm detected → short-circuit to safety response
    route: str              # "crisis" | "continue"
    flags: list             # non-fatal flags (e.g. "jailbreak") for logging
    safety_payload: dict     # crisis message + helplines (when safety_flag)
    disclaimer: str          # output-guard disclaimer appended for sensitive topics

    # --- understanding agent ---
    language: str           # hi | hinglish | en
    intent: str             # life-problem | gita-question | smalltalk | off-topic
    emotion: str
    concern: str
    turn_type: str          # new-topic | follow-up | deeper-request | spiraling | closing
    response_mode: str      # open | continue | deepen | steer | close
    depth_level: int

    # --- retrieval agent ---
    candidates: list[dict]  # candidate verse records (from tree-nav or fallback)

    # --- compose / verify ---
    compose_result: Any     # ComposeResult
    verse_id: str | None    # validated id (None → honest redirect)
    verified: bool

    # --- output ---
    rendered_text: str
    verse_card: dict | None
    practical_step_hi: str | None
    provider: str | None
    degraded: bool

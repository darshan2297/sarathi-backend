"""LLM client interface (plan §4, §9).

The composer's contract is deliberately narrow: it returns Hindi guidance + a `verse_id`, and
NEVER any Sanskrit. Where the guidance refers to a verse inline, it writes the literal token
`{{VERSE}}`; the backend injects canonical Sanskrit there (plan §7.1). This interface is shared by
the Phase 1 stub and the Phase 2 OpenRouter↔Ollama router.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from app.core.budget import TurnBudget

VERSE_PLACEHOLDER = "{{VERSE}}"


class ComposeContext(BaseModel):
    user_message: str
    history: list[dict] = []
    candidates: list[dict] = []  # candidate verse records from the retriever
    memories: list[dict] = []    # recalled past episodes (member tier; plan §6)
    response_mode: str = "open"  # open | continue | deepen | steer | close
    turn_index: int = 0


class ComposeResult(BaseModel):
    spoken_guidance_hi: str          # may contain the {{VERSE}} placeholder
    verse_id: str | None = None      # chosen from candidates; injected by backend
    practical_step_hi: str | None = None
    mode: str = "open"
    provider: str | None = None      # which provider actually answered (openrouter/ollama/stub)
    degraded: bool = False           # True when a fallback (not the primary) served the answer


class LLMClient(Protocol):
    async def compose(self, ctx: ComposeContext, budget: TurnBudget) -> ComposeResult:
        """Produce Hindi guidance + verse_id. Records token spend on `budget`."""
        ...

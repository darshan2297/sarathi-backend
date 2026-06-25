"""Shared node helper: resilient LLM JSON call with graceful no-op fallback.

If the active client can't make raw JSON calls (e.g. the plain stub) or every provider is down,
`llm_json` returns None and the calling node uses its deterministic fallback. This keeps the whole
graph runnable with no API key (heuristic understanding + keyword retrieval + stub compose).
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.llm import get_client

log = get_logger("sarathi.graph")


async def llm_json(messages: list[dict], budget: Any, cheap: bool = False) -> dict | None:
    client = get_client()
    fn = getattr(client, "complete_json", None)
    if fn is None:
        return None
    try:
        return await fn(messages, budget, cheap=cheap)
    except TypeError:
        return await fn(messages, budget)  # client without the cheap kwarg
    except Exception as exc:  # never let an agent's LLM call crash the turn
        log.warning("llm_json_failed", error=str(exc))
        return None

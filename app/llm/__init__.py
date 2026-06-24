"""LLM client factory. Phase 1 → stub; Phase 2 → OpenRouter↔Ollama router (same interface)."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.llm.base import LLMClient


@lru_cache(maxsize=1)
def get_client() -> LLMClient:
    """Singleton LLM client. Router keeps per-provider circuit state + cache across turns."""
    provider = settings.llm_provider
    if provider == "stub":
        from app.llm.stub import StubLLM

        return StubLLM()
    if provider == "router":
        from app.llm.router import Router

        return Router()
    raise ValueError(f"Unknown llm_provider: {provider!r}")

"""LLM router (plan §9) — OpenRouter (primary) → Ollama (fallback) → stub (dev).

Responsibilities:
  • build the composer prompt, call the first healthy provider, parse strict JSON → ComposeResult
  • per-provider circuit breaker + bounded retries with exponential backoff + timeout
  • mark `degraded=True` whenever a non-primary provider answers (plan §9 honesty)
  • response cache to skip the whole fan-out on repeats
  • constrain verse_id to the offered candidates (defense-in-depth with §7.1 injection)

`complete_json()` exposes the same resilient chain to non-compose callers (the Phase 3 Understanding
and Retrieval agents), returning a parsed dict or None so each agent can fall back deterministically.
"""

from __future__ import annotations

import asyncio
import json
from typing import Callable

from app.cache.response_cache import ResponseCache, make_key
from app.core.budget import TurnBudget
from app.core.config import settings
from app.core.logging import get_logger
from app.llm.base import ComposeContext, ComposeResult
from app.llm.circuit import CircuitBreaker
from app.llm.prompts import build_messages, build_user_prompt, candidate_ids
from app.llm.providers.base import Provider, ProviderError
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openrouter import OpenRouterProvider

log = get_logger("sarathi.router")

_UNSET = object()  # sentinel so cache=None means "no cache" (not "use default")


def _extract_json(text: str) -> dict:
    """Defensively pull a JSON object out of a model reply (handles ```json fences / stray text)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t.lower().startswith("json") else t
    try:
        return json.loads(t)
    except ValueError:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(t[start : end + 1])
    raise ProviderError("could not parse JSON from model reply")


def parse_compose(text: str, ctx: ComposeContext) -> ComposeResult:
    data = _extract_json(text)
    spoken = (data.get("spoken_guidance_hi") or "").strip()
    if not spoken:
        raise ProviderError("model reply missing spoken_guidance_hi")
    verse_id = data.get("verse_id")
    if verse_id not in candidate_ids(ctx):  # only allow offered candidates (or None)
        verse_id = None
    return ComposeResult(
        spoken_guidance_hi=spoken,
        verse_id=verse_id,
        practical_step_hi=(data.get("practical_step_hi") or None),
        mode=data.get("mode") or ctx.response_mode,
    )


def _last_user(messages: list[dict]) -> str:
    return next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")


class Router:
    def __init__(
        self,
        providers: list[tuple[Provider, bool]] | None = None,
        cache=_UNSET,
        max_retries: int | None = None,
        retry_base_s: float = 0.2,
    ) -> None:
        self._chain = providers if providers is not None else self._default_chain()
        self._breakers = {p.name: CircuitBreaker(settings.circuit_fail_threshold, settings.circuit_reset_s)
                          for p, _ in self._chain}
        if cache is _UNSET:
            self._cache = ResponseCache(settings.cache_size) if settings.cache_enabled else None
        else:
            self._cache = cache  # explicit (including None = disabled)
        self._max_retries = settings.max_retries if max_retries is None else max_retries
        self._retry_base_s = retry_base_s

    @staticmethod
    def _default_chain() -> list[tuple[Provider, bool]]:
        return [
            (OpenRouterProvider(settings.openrouter_api_key, settings.openrouter_base_url,
                                settings.openrouter_model_strong), True),
            (OllamaProvider(settings.ollama_host, settings.ollama_model, settings.ollama_enabled), False),
        ]

    async def _run_chain(self, messages: list[dict], budget: TurnBudget, parse: Callable,
                         cheap: bool = False):
        """Try each healthy provider; `parse(text)` runs INSIDE the try so bad JSON triggers failover.

        `cheap=True` routes classification-style calls (understanding, navigation) to the smaller,
        faster model on OpenRouter — the big latency lever (plan §10.1) — while compose stays strong.

        Returns (parsed, provider_name, degraded) on success, or None if the whole chain is exhausted.
        """
        prompt_text = _last_user(messages)
        for provider, is_primary in self._chain:
            if not provider.is_configured:
                continue
            # only OpenRouter has a distinct cheap model; others use their single configured model
            model = settings.openrouter_model_cheap if (cheap and provider.name == "openrouter") else None
            breaker = self._breakers[provider.name]
            if not breaker.allow():
                log.info("circuit_open_skip", provider=provider.name)
                continue
            for attempt in range(self._max_retries + 1):
                try:
                    text = await provider.complete(
                        messages, json_mode=True, timeout=settings.request_timeout_s, model=model
                    )
                    parsed = parse(text)
                    breaker.record_success()
                    budget.add_call(prompt_text, text)
                    return parsed, provider.name, (not is_primary)
                except ProviderError as exc:
                    breaker.record_failure()
                    log.warning("provider_failed", provider=provider.name, attempt=attempt, error=str(exc))
                    if attempt < self._max_retries:
                        await asyncio.sleep(self._retry_base_s * (2 ** attempt))
        return None

    async def compose(self, ctx: ComposeContext, budget: TurnBudget) -> ComposeResult:
        cids = sorted(candidate_ids(ctx))

        key = make_key(ctx.user_message, ctx.response_mode, cids) if self._cache else None
        if key:
            cached = self._cache.get(key)
            if cached is not None:
                log.info("cache_hit", mode=ctx.response_mode)
                return cached

        out = await self._run_chain(build_messages(ctx), budget, lambda t: parse_compose(t, ctx))
        if out is not None:
            result, provider, degraded = out
            result.provider = provider
            result.degraded = degraded
            if key:
                self._cache.set(key, result)
            if degraded:
                log.warning("degraded_response", provider=provider)
            return result

        # last resort — deterministic stub so the app stays up without keys
        if settings.allow_stub_fallback:
            from app.llm.stub import StubLLM

            log.warning("stub_fallback", reason="no live provider available")
            result = await StubLLM().compose(ctx, budget)
            result.provider = "stub"
            result.degraded = True
            return result

        raise ProviderError("all providers unavailable and stub fallback disabled")

    async def complete_json(self, messages: list[dict], budget: TurnBudget,
                            cheap: bool = False) -> dict | None:
        """Resilient JSON completion for non-compose agents. None → caller uses its own fallback.
        `cheap=True` uses the faster/smaller model (classification tasks don't need the big model)."""
        out = await self._run_chain(messages, budget, _extract_json, cheap=cheap)
        return out[0] if out is not None else None

    def health(self) -> dict:
        return {
            "providers": [
                {"name": p.name, "configured": p.is_configured,
                 "primary": prim, "circuit": self._breakers[p.name].state.value}
                for p, prim in self._chain
            ],
            "cache": self._cache.stats() if self._cache else None,
        }

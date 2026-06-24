"""Ollama provider (plan §9, fallback). Local /api/chat. This is the DEGRADED path — a small local
model won't match the primary's guru-register Hindi; that's expected (plan §9)."""

from __future__ import annotations

from app.llm.providers.base import Provider, ProviderError


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, host: str, model: str, enabled: bool = False) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._enabled = enabled

    @property
    def is_configured(self) -> bool:
        # Gated by an explicit flag — a real connection failure (when enabled) trips the breaker.
        return self._enabled and bool(self._host)

    async def complete(
        self,
        messages: list[dict],
        *,
        json_mode: bool = True,
        timeout: float = 30.0,
        model: str | None = None,
    ) -> str:
        payload: dict = {
            "model": model or self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.7},
        }
        if json_mode:
            payload["format"] = "json"
        data = await self._post_json(
            f"{self._host}/api/chat", payload, {"Content-Type": "application/json"}, timeout
        )
        content = (data.get("message") or {}).get("content", "")
        if not content or not content.strip():
            raise ProviderError(f"{self.name}: empty completion")
        return content

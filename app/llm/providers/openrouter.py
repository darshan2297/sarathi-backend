"""OpenRouter provider (plan §9, primary). OpenAI-compatible /chat/completions."""

from __future__ import annotations

from app.llm.providers.base import Provider, ProviderError


class OpenRouterProvider(Provider):
    name = "openrouter"

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def complete(
        self,
        messages: list[dict],
        *,
        json_mode: bool = True,
        timeout: float = 30.0,
        model: str | None = None,
    ) -> str:
        payload: dict = {"model": model or self._model, "messages": messages, "temperature": 0.7}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            # OpenRouter attribution headers (optional but recommended)
            "HTTP-Referer": "https://sarathi.local",
            "X-Title": "Sarathi",
        }
        data = await self._post_json(
            f"{self._base_url}/chat/completions", payload, headers, timeout
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name}: unexpected response shape") from exc
        if not content or not content.strip():
            raise ProviderError(f"{self.name}: empty completion")
        return content

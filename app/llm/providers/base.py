"""Provider abstraction (plan §9). Each provider turns chat messages into a single text reply.

We use UNARY completions (await the full reply), not token streaming, on purpose: the answer must be
fully composed before we inject the canonical Sanskrit (plan §7.1), and only then is it streamed to
the user (the pipeline does that word-by-word). So provider-level streaming buys us nothing here.
"""

from __future__ import annotations

import httpx


class ProviderError(Exception):
    """Raised on any provider failure (network, timeout, bad status, empty/garbled reply)."""


class Provider:
    name: str = "base"

    @property
    def is_configured(self) -> bool:  # pragma: no cover - overridden
        return False

    async def complete(
        self,
        messages: list[dict],
        *,
        json_mode: bool = True,
        timeout: float = 30.0,
        model: str | None = None,
    ) -> str:
        raise NotImplementedError

    async def _post_json(self, url: str, payload: dict, headers: dict, timeout: float) -> dict:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: network error — {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(f"{self.name}: HTTP {resp.status_code} — {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name}: non-JSON response") from exc

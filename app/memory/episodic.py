"""Episodic memory service (plan §6) — logged-in users only.

write()   : record one turn as an episode.
recall()  : score past episodes by concern-overlap + recency, return top-k for injection.
journey_summary(): rolling consolidation of recent episodes to bound context.
"""

from __future__ import annotations

import re
import time

from app.core.config import settings
from app.db.store import Episode, MemoryStore, get_store

_TOKEN = re.compile(r"[ऀ-ॿa-zA-Z]+")


def _toks(s: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(s or "")}


class EpisodicMemory:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or get_store()

    async def write(self, user_id: str, concern: str, emotion: str = "none",
                    verse_ids: list[str] | None = None, safety: bool = False) -> Episode:
        prefix = f"{emotion}: " if emotion and emotion != "none" else ""
        episode = Episode(
            ts=time.time(),
            concern=concern or "",
            emotion=emotion or "none",
            verse_ids=verse_ids or [],
            summary=(prefix + (concern or ""))[:100],
            safety=safety,
        )
        await self.store.add_episode(user_id, episode)
        return episode

    async def recall(self, user_id: str, concern: str, k: int | None = None) -> list[dict]:
        k = k or settings.memory_recall_k
        episodes = await self.store.list_episodes(user_id)
        if not episodes:
            return []
        q = _toks(concern)
        n = len(episodes)
        scored = []
        for i, e in enumerate(episodes):
            overlap = len(q & (_toks(e.concern) | _toks(e.summary)))
            recency = (i + 1) / n  # newer episodes score higher
            scored.append((overlap * 2 + recency, i, e))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [e.model_dump() for _, _, e in scored[:k]]

    async def journey_summary(self, user_id: str, n: int = 5) -> str:
        episodes = await self.store.list_episodes(user_id)
        return " · ".join(e.summary for e in episodes[-n:]) if episodes else ""

"""In-process response cache (plan §10). Bounded LRU keyed by the semantically-relevant inputs.

Phase 2 starts with a simple exact-match LRU; a semantic cache can layer on later. Caching the
ComposeResult saves the whole 5–6-call fan-out on repeat questions (plan §10.1).
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict

from app.llm.base import ComposeResult


def make_key(user_message: str, mode: str, candidate_ids: list[str]) -> str:
    norm = " ".join(user_message.lower().split())
    raw = f"{mode}|{','.join(sorted(candidate_ids))}|{norm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, maxsize: int = 512) -> None:
        self._store: "OrderedDict[str, ComposeResult]" = OrderedDict()
        self._maxsize = maxsize
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> ComposeResult | None:
        if key in self._store:
            self._store.move_to_end(key)
            self.hits += 1
            return self._store[key].model_copy()
        self.misses += 1
        return None

    def set(self, key: str, value: ComposeResult) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def stats(self) -> dict:
        return {"size": len(self._store), "hits": self.hits, "misses": self.misses}

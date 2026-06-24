"""Storage layer (plan §6, §10).

Two implementations behind one interface:
  • InMemoryStore — default; lets the app run with no database (dev / this env).
  • MongoStore    — motor (async MongoDB); used when SARATHI_MONGO_ENABLED=true.

Holds the two member-tier collections: `users` and `episodes` (episodic memory). Guests never
touch this store (plan §1, §6) — nothing of theirs is persisted.

NOTE (prod): episodes contain sensitive personal content → enable encryption-at-rest + enforce the
retention window (settings.memory_retention_days) + explicit consent at login (plan §6). Marked TODO.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

from pydantic import BaseModel, Field

from app.core.config import settings


class Episode(BaseModel):
    ts: float
    concern: str
    emotion: str = "none"
    verse_ids: list[str] = Field(default_factory=list)
    summary: str
    safety: bool = False


def user_id_for(email: str) -> str:
    return "u-" + hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:12]


class MemoryStore:
    async def get_or_create_user(self, email: str) -> str:
        raise NotImplementedError

    async def add_episode(self, user_id: str, episode: Episode) -> None:
        raise NotImplementedError

    async def list_episodes(self, user_id: str) -> list[Episode]:
        raise NotImplementedError


class InMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self._users: dict[str, str] = {}              # email -> user_id
        self._episodes: dict[str, list[Episode]] = {}  # user_id -> episodes

    async def get_or_create_user(self, email: str) -> str:
        uid = user_id_for(email)
        self._users.setdefault(email.strip().lower(), uid)
        return uid

    async def add_episode(self, user_id: str, episode: Episode) -> None:
        self._episodes.setdefault(user_id, []).append(episode)

    async def list_episodes(self, user_id: str) -> list[Episode]:
        return list(self._episodes.get(user_id, []))


class MongoStore(MemoryStore):
    def __init__(self, uri: str, db: str) -> None:
        from motor.motor_asyncio import AsyncIOMotorClient  # lazy: only when enabled

        self._client = AsyncIOMotorClient(uri)
        self._db = self._client[db]

    async def get_or_create_user(self, email: str) -> str:
        uid = user_id_for(email)
        await self._db.users.update_one(
            {"_id": uid}, {"$setOnInsert": {"email": email.strip().lower()}}, upsert=True
        )
        return uid

    async def add_episode(self, user_id: str, episode: Episode) -> None:
        await self._db.episodes.insert_one({"user_id": user_id, **episode.model_dump()})

    async def list_episodes(self, user_id: str) -> list[Episode]:
        cursor = self._db.episodes.find({"user_id": user_id}).sort("ts", 1)
        return [Episode(**{k: v for k, v in doc.items() if k != "_id" and k != "user_id"})
                async for doc in cursor]


@lru_cache(maxsize=1)
def get_store() -> MemoryStore:
    if settings.mongo_enabled:
        return MongoStore(settings.mongo_uri, settings.mongo_db)
    return InMemoryStore()

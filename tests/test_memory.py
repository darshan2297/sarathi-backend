"""Phase 5 proof — accounts, episodic memory, guest vs member tiers. (from backend/)"""

from __future__ import annotations

import asyncio

from app.db.store import Episode, InMemoryStore, user_id_for
from app.graph.nodes.memory import memory_recall_node, memory_write_node
from app.graph.pipeline import run_turn
from app.memory.episodic import EpisodicMemory


def run(coro):
    return asyncio.run(coro)


# --- store + identity ---

def test_user_id_is_stable_per_email():
    assert user_id_for("A@x.com ") == user_id_for("a@x.com")
    assert user_id_for("a@x.com") != user_id_for("b@x.com")


def test_inmemory_store_roundtrip():
    async def _t():
        s = InMemoryStore()
        uid = await s.get_or_create_user("seeker@x.com")
        await s.add_episode(uid, Episode(ts=1.0, concern="क्रोध", summary="क्रोध"))
        eps = await s.list_episodes(uid)
        return uid, eps
    uid, eps = run(_t())
    assert uid.startswith("u-") and len(eps) == 1 and eps[0].concern == "क्रोध"


# --- episodic recall scoring ---

def test_recall_ranks_by_overlap():
    async def _t():
        mem = EpisodicMemory(InMemoryStore())
        await mem.write("u-1", "क्रोध भाई से", emotion="क्रोध")
        await mem.write("u-1", "पैसे की चिंता", emotion="चिंता")
        return await mem.recall("u-1", "गुस्सा क्रोध", k=2)
    out = run(_t())
    assert out and "क्रोध" in out[0]["concern"]


# --- tier behaviour ---

def test_guest_writes_nothing_and_recalls_empty():
    async def _t():
        recall = await memory_recall_node({"tier": "guest", "user_message": "x"})
        await memory_write_node({"tier": "guest", "concern": "क्रोध", "emotion": "क्रोध"})
        return recall
    recall = run(_t())
    assert recall["memories"] == []


def test_member_turn_then_recall_node_returns_episode():
    uid = user_id_for("remember-me@x.com")

    async def _t():
        # member turn writes an episode via the graph
        async for _ in run_turn(user_message="गुस्से से नींद नहीं आती", history=[],
                                turn_id="m1", user_id=uid, tier="member", stream_delay_ms=0):
            pass
        # a later recall (after understanding sets concern) finds it
        return await memory_recall_node(
            {"tier": "member", "user_id": uid, "concern": "गुस्सा", "user_message": "गुस्सा"})
    out = run(_t())
    assert out["memories"], "member should have a recalled episode"


def test_member_second_turn_references_past_journey():
    uid = user_id_for("journey@x.com")

    async def _t():
        async for _ in run_turn(user_message="भाई पर बहुत गुस्सा आता है", history=[],
                                turn_id="j1", user_id=uid, tier="member", stream_delay_ms=0):
            pass
        events = [ev async for ev in run_turn(
            user_message="फिर वही गुस्सा लौट आया", history=[],
            turn_id="j2", user_id=uid, tier="member", stream_delay_ms=0)]
        return "".join(e["text"] for e in events if e["type"] == "token")
    text = run(_t())
    assert "पिछली बार" in text  # the guru remembers the journey

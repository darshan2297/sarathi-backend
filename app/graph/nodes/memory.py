"""Memory graph nodes (plan §4 nodes 3 & 8, §6). Logged-in (member) tier only.

memory_recall : after understanding — pull relevant past episodes into state for the composer.
memory_write  : after output — record this turn as an episode (guests write nothing, ever).
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.db.store import get_store
from app.graph.state import GraphState
from app.memory.episodic import EpisodicMemory

log = get_logger("sarathi.memory")


def _is_member(state: GraphState) -> bool:
    return state.get("tier") == "member" and bool(state.get("user_id"))


async def memory_recall_node(state: GraphState) -> dict:
    if not _is_member(state):
        return {"memories": []}
    mem = EpisodicMemory(get_store())
    concern = state.get("concern") or state.get("user_message", "")
    episodes = await mem.recall(state["user_id"], concern)
    return {"memories": episodes}


async def memory_write_node(state: GraphState) -> dict:
    if not _is_member(state):
        return {}
    concern = state.get("concern")
    safety = bool(state.get("safety_flag"))
    if not concern and not safety:
        return {}
    mem = EpisodicMemory(get_store())
    verse_ids = [state["verse_id"]] if state.get("verse_id") else []
    await mem.write(
        state["user_id"], concern or "संकट क्षण",
        state.get("emotion", "none"), verse_ids, safety=safety,
    )
    log.info("episode_written", user_id=state["user_id"], safety=safety)
    return {}

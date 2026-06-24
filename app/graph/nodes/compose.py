"""Guru Composer node (plan §4 node 5) — delegates to the LLM router (Phase 2)."""

from __future__ import annotations

from app.graph.state import GraphState
from app.llm import get_client
from app.llm.base import ComposeContext


async def compose_node(state: GraphState) -> dict:
    ctx = ComposeContext(
        user_message=state["user_message"],
        history=state.get("thread_history", []),
        candidates=state.get("candidates", []),
        memories=state.get("memories", []),
        response_mode=state.get("response_mode", "open"),
        turn_index=len(state.get("thread_history", [])),
    )
    result = await get_client().compose(ctx, state["budget"])
    return {"compose_result": result}

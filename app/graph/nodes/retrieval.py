"""Retrieval agent (plan §5) — vectorless PageIndex tree-navigation.

LLM path: reason over `tree_index.json` to pick verse ids. Fallback: deterministic theme_map/tag
matcher (Phase 1). Skipped entirely on continue/steer/close — no reflex verse (plan §2.6).
"""

from __future__ import annotations

from app.core.metrics import metrics
from app.graph.nodes.common import llm_json
from app.graph.state import GraphState
from app.llm.prompts import build_navigate_messages
from app.retrieval.corpus import get_corpus
from app.retrieval.pageindex import retrieve

_NO_VERSE_MODES = {"greet", "continue", "steer", "close"}


async def retrieval_node(state: GraphState) -> dict:
    if state.get("response_mode", "open") in _NO_VERSE_MODES:
        return {"candidates": []}

    corpus = get_corpus()
    concern = state.get("concern") or state["user_message"]

    data = await llm_json(build_navigate_messages(concern, corpus.tree), state["budget"])
    ids: list[str] = []
    if data and isinstance(data.get("verse_ids"), list):
        ids = [i for i in data["verse_ids"] if isinstance(i, str) and corpus.exists(i)]

    if ids:
        metrics.incr("retrieval.llm")
        candidates = [corpus.get_verse(i) for i in ids[:3]]
    else:
        metrics.incr("retrieval.fallback")
        candidates = retrieve(concern, corpus)  # deterministic fallback

    return {"candidates": candidates}

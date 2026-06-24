"""Output node (plan §4 node 7) — inject canonical Sanskrit + assemble the final payload."""

from __future__ import annotations

from app.graph.render import inject_verse
from app.graph.state import GraphState
from app.retrieval.corpus import get_corpus


async def output_node(state: GraphState) -> dict:
    corpus = get_corpus()
    result = state["compose_result"]
    verse_id = state.get("verse_id")

    rendered, verse_card = inject_verse(result.spoken_guidance_hi, verse_id, corpus)

    return {
        "rendered_text": rendered,
        "verse_card": verse_card,
        "practical_step_hi": result.practical_step_hi,
        "provider": result.provider,
        "degraded": result.degraded,
    }

"""Verification node (plan §4 node 6, §7).

Fabrication is already impossible (verse text is injected, not generated), so this node:
  1. validates the chosen verse_id against the corpus (drops anything bogus), and
  2. runs a SECONDARY faithfulness filter (§7.2) — when an LLM is available, ask whether the verse
     genuinely supports the guidance; drop the verse only on an explicit "no" (conservative).

The faithfulness check is honestly NOT the primary defense — a human-reviewed theme_map is (§7.2).
With no LLM available we keep the curated mapping rather than guess.
"""

from __future__ import annotations

from app.core.config import settings
from app.graph.nodes.common import llm_json
from app.graph.state import GraphState
from app.llm.prompts import build_faithfulness_messages
from app.retrieval.corpus import get_corpus


async def verify_node(state: GraphState) -> dict:
    corpus = get_corpus()
    result = state["compose_result"]
    proposed = result.verse_id

    valid_id = proposed if (proposed and corpus.exists(proposed)) else None
    verified = (valid_id is not None) or (proposed is None)  # False only if we dropped a bogus id

    # secondary faithfulness filter — OPT-IN only (plan §7.2). Off by default because a fallible
    # (esp. small/local) LLM judge produces false negatives that strip valid verses.
    if valid_id and settings.faithfulness_filter_enabled:
        verse = corpus.get_verse(valid_id)
        check = await llm_json(
            build_faithfulness_messages(result.spoken_guidance_hi, verse["translation_hi"]),
            state["budget"],
        )
        if check is not None and check.get("supports") is False:
            valid_id = None       # honest redirect — don't cite a verse that doesn't fit
            verified = False

    return {"verse_id": valid_id, "verified": verified}

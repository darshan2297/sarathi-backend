"""Retrieval agent (plan §5) — vectorless RAG over the full Bhagavad Gita.

Always computes a curated/deterministic pool (Hindi-aware theme_map; §7.2 misapplication defense).
When a provider is available, a two-step LLM navigator reasons over the book — pick chapter(s),
then pick verse(s) within them — bridging a Hindi concern to the English book. Curated picks lead
the merge so the misapplication guarantee holds; the navigator widens coverage to all ~700 verses.
The final ≤3 verses are enriched with their page-grounded English passage for compose.

Skipped entirely on greet/continue/steer/close — no reflex verse (plan §2.6).
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.metrics import metrics
from app.graph.nodes.common import llm_json
from app.graph.state import GraphState
from app.llm.prompts import build_navigate_messages
from app.retrieval.book import BookIndex, get_book_index
from app.retrieval.corpus import get_corpus
from app.retrieval.pageindex import (
    build_candidate,
    curated_pool,
    curated_strong,
    gloss_pool,
    merge_ids,
)

_NO_VERSE_MODES = {"greet", "continue", "steer", "close"}
_POOL_K = 6      # deterministic curated/scan pool
_FINAL_K = 3     # verses handed to compose


async def retrieval_node(state: GraphState) -> dict:
    # no reflex verse on conversational turns (plan §2.6), and never force scripture onto an
    # off-topic question (cloud QA #3 — that path must honestly redirect, not cite a verse).
    if state.get("response_mode", "open") in _NO_VERSE_MODES or state.get("intent") == "off-topic":
        return {"candidates": []}

    corpus = get_corpus()
    book = get_book_index()
    # Retrieve on the user's ACTUAL words AND the concern (QA H-4/H-5). The understanding model's
    # `concern` paraphrase is often lossy or mistranslated (e.g. "comparison/purpose" → "किस्मत की
    # चाह", "brother" → "बROTHER"), which sent retrieval to the wrong verse. The raw message carries
    # the real topic/emotion tokens; the concern adds a (sometimes better) Hindi rephrase. Together
    # they recover the right verse far more often than the concern alone.
    concern = state.get("concern") or ""
    query = f"{state['user_message']} {concern}".strip()

    # Authority order (§7.2): high-confidence reviewed matches lead, then the rest of the reviewed
    # theme_map, THEN the LLM navigator (full-book reach), and the English gloss scan last. The
    # navigator widens coverage but must never bury a reviewed mapping (QA H-5: it was outranking
    # correct curated picks like BG2.47/2.48 for "fear of failure").
    strong = curated_strong(query, corpus)
    curated = curated_pool(query, corpus)
    # latency (plan §10.1): a confident curated match already has the right verse, so skip the
    # navigator round-trip; only reach into the full book when curated is unsure.
    nav_ids = (await _navigate(query, book, state["budget"])
               if settings.retrieval_use_pageindex and not strong else [])
    gloss = gloss_pool(query, k=_POOL_K)

    metrics.incr("retrieval.llm" if nav_ids else "retrieval.fallback")
    final_ids = merge_ids(strong, curated, nav_ids, gloss)[:_FINAL_K]

    candidates = [build_candidate(vid, corpus, book) for vid in final_ids]
    for c in candidates:                       # ground only the finalists (bounded PDF reads)
        c["passage"] = book.passage_for(c["id"])
    return {"candidates": candidates}


async def _navigate(concern: str, book: BookIndex, budget) -> list[str]:
    """Single-call vectorless navigation: concern + chapter map → verse ids (cloud QA #5: was two
    LLM calls, now one). Returns [] if no provider is available (falls back to deterministic)."""
    data = await llm_json(build_navigate_messages(concern, _chapter_digest(book)), budget, cheap=True)
    if data and isinstance(data.get("verse_ids"), list):
        return [i for i in data["verse_ids"] if isinstance(i, str) and book.has(i)]
    return []


@lru_cache(maxsize=1)
def _chapter_digest(book: BookIndex) -> str:
    """18 chapter headings — small enough to fit the per-turn token budget."""
    return "\n".join(f'{c["chapter"]}. {c.get("title", "")} ({c.get("verse_count", 0)} verses)'
                     for c in book.chapters)

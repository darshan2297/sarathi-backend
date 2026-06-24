"""Retriever (plan §5).

PHASE 1 is a deterministic theme_map + tag matcher — no LLM, no embeddings — enough to prove the
loop and exercise injection. PHASE 3 replaces `retrieve()` with true LLM tree-navigation over
`tree_index.json` (the vectorless PageIndex reasoning), keeping this same signature.
"""

from __future__ import annotations

import re

from app.retrieval.corpus import Corpus, get_corpus

_TOKEN = re.compile(r"[ऀ-ॿa-zA-Z]+")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "")}


def retrieve(query: str, corpus: Corpus | None = None, k: int = 3) -> list[dict]:
    """Return up to k candidate verse records most relevant to `query`.

    Scoring (Phase 1):
      • +3 per token shared with a theme's name/problem-examples (theme_map hint)
      • +1 per token shared with a verse's tags
    Ties broken by corpus order (stable, deterministic).
    """
    corpus = corpus or get_corpus()
    q = _tokens(query)
    if not q:
        return []

    scores: dict[str, int] = {vid: 0 for vid in corpus.all_ids}

    # theme_map hint
    for theme in corpus.themes:
        theme_tokens = _tokens(theme.get("theme", ""))
        for ex in theme.get("problem_examples", []):
            theme_tokens |= _tokens(ex)
        overlap = len(q & theme_tokens)
        if overlap:
            for vid in theme.get("verses", []):
                if vid in scores:
                    scores[vid] += 3 * overlap

    # per-verse tag match
    for vid in corpus.all_ids:
        v = corpus.get_verse(vid)
        tag_tokens: set[str] = set()
        for tag in v.get("tags", []):
            tag_tokens |= _tokens(tag)
        scores[vid] += len(q & tag_tokens)

    ranked = sorted(
        (vid for vid, s in scores.items() if s > 0),
        key=lambda vid: (-scores[vid], corpus.all_ids.index(vid)),
    )
    return [corpus.get_verse(vid) for vid in ranked[:k]]

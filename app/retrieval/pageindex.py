"""Retriever (plan §5) — vectorless RAG over the full Bhagavad-Gita.

Two layers, by design:
  • CURATED (Hindi-aware, reviewed): the theme_map maps common emotional concerns to the right
    canonical verses and encodes the §7.2 "avoid" rules (e.g. restless mind → BG6.35, NOT BG2.62).
    This leads, so the misapplication defense always holds.
  • FULL-BOOK (deterministic): a gloss keyword scan over all ~700 verses (English glosses) widens
    coverage beyond the curated set. The LLM tree-navigator (app/graph/nodes/retrieval.py) sits on
    top of this and bridges a Hindi concern to the English book by reasoning.

`retrieve()` is the deterministic, no-LLM workhorse (also the fallback when no provider is up): it
returns enriched candidate records — id + citation + pdf_page + meaning + the page-grounded passage
slot — curated-first. Candidate dicts are the contract consumed by compose (plan §4).
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.retrieval.book import BookIndex, get_book_index
from app.retrieval.corpus import Corpus, get_corpus

_TOKEN = re.compile(r"[ऀ-ॿa-zA-Z]+")

# Grammatical particles / fillers carry no topical signal (see plan §7.2 note on cross-linking).
_STOPWORDS = {
    "नहीं", "है", "हूँ", "हूं", "हो", "होता", "होती", "रहा", "रही", "रहता", "रहती",
    "और", "मैं", "मुझे", "मेरा", "मेरी", "में", "का", "की", "के", "को", "से", "पर",
    "यह", "वह", "इस", "उस", "जो", "भी", "ही", "तो", "ने", "कुछ", "हर", "बहुत", "बार",
    "a", "an", "the", "and", "or", "of", "to", "in", "is", "i", "my", "me", "about",
    "you", "your", "for", "with", "that", "this", "it", "be", "are", "but", "not",
}


def _tokens(text: str) -> set[str]:
    return {t for t in (m.lower() for m in _TOKEN.findall(text or "")) if t not in _STOPWORDS}


# ──────────────────────────────────────────────────────────────────────────────
# Candidate assembly — merge canonical text (where we have it) with book page/gloss
# ──────────────────────────────────────────────────────────────────────────────
def build_candidate(verse_id: str, corpus: Corpus, book: BookIndex) -> dict:
    """Assemble the candidate record consumed by compose/render. Canonical fields when available
    (rich Hindi card), otherwise the book's English gloss + page (full-book coverage)."""
    cv = corpus.get_verse(verse_id)            # canonical record or None
    m = book.meta(verse_id) or {}
    chapter = (cv or m).get("chapter")
    verse = (cv or m).get("verse")
    return {
        "id": verse_id,
        "chapter": chapter,
        "verse": verse,
        "pdf_page": book.page_for(verse_id),
        "page_end": m.get("page_end"),
        "citation": corpus.citation(verse_id),
        "translation_hi": cv.get("translation_hi", "") if cv else "",
        "chapter_theme_hi": cv.get("chapter_theme_hi", "") if cv else _chapter_title(book, chapter),
        "tags": cv.get("tags", []) if cv else [],
        "gloss_en": book.gloss(verse_id),
        "canonical": cv is not None,
        "passage": "",                          # filled for finalists by the retrieval node
    }


def _chapter_title(book: BookIndex, chapter: int | None) -> str:
    for c in book.chapters:
        if c.get("chapter") == chapter:
            return c.get("title", "")
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# CURATED layer — theme_map + tags over the canonical corpus (Hindi-aware, §7.2 safe)
# ──────────────────────────────────────────────────────────────────────────────
def curated_strong(query: str, corpus: Corpus | None = None, min_overlap: int = 2) -> list[str]:
    """Verses from theme_map themes that match the concern CONFIDENTLY (≥min_overlap content tokens).

    This is the high-confidence, reviewed signal that must LEAD so the §7.2 misapplication defense
    holds (restless mind → BG6.35). A single shared common word (e.g. "काम") is deliberately not
    enough — that noise is what let unrelated verses surface. Returned in theme-curated order.
    """
    corpus = corpus or get_corpus()
    q = _tokens(query)
    hits: list[tuple[int, int, str]] = []   # (overlap, curated_index, verse_id)
    for theme in corpus.themes:
        tt = _tokens(theme.get("theme", ""))
        for ex in theme.get("problem_examples", []):
            tt |= _tokens(ex)
        overlap = len(q & tt)
        if overlap >= min_overlap:
            for idx, vid in enumerate(theme.get("verses", [])):
                hits.append((overlap, idx, vid))
    hits.sort(key=lambda h: (-h[0], h[1]))
    return merge_ids([vid for _, _, vid in hits])


def _curated_rank(q: set[str], corpus: Corpus) -> list[str]:
    scores: dict[str, int] = {vid: 0 for vid in corpus.all_ids}

    for theme in corpus.themes:
        theme_tokens = _tokens(theme.get("theme", ""))
        for ex in theme.get("problem_examples", []):
            theme_tokens |= _tokens(ex)
        overlap = len(q & theme_tokens)
        if overlap:
            for idx, vid in enumerate(theme.get("verses", [])):
                if vid in scores:
                    # strong topical signal + a bounded primacy nudge for the curated order
                    scores[vid] += 3 * overlap + max(0, 3 - idx) * 2

    for vid in corpus.all_ids:
        v = corpus.get_verse(vid)
        tag_tokens: set[str] = set()
        for tag in v.get("tags", []):
            tag_tokens |= _tokens(tag)
        scores[vid] += len(q & tag_tokens)

    return sorted((vid for vid, s in scores.items() if s > 0),
                  key=lambda vid: (-scores[vid], corpus.all_ids.index(vid)))


# ──────────────────────────────────────────────────────────────────────────────
# FULL-BOOK layer — gloss keyword scan over all ~700 verses (English glosses)
# ──────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _gloss_index() -> dict[str, set[str]]:
    """verse_id → token set over its English gloss + chapter title (built once)."""
    book = get_book_index()
    title = {c["chapter"]: c.get("title", "") for c in book.chapters}
    idx: dict[str, set[str]] = {}
    for vid in book.all_ids:
        m = book.meta(vid) or {}
        idx[vid] = _tokens(m.get("gloss_en", "") + " " + title.get(m.get("chapter"), ""))
    return idx


def _gloss_rank(q: set[str], limit: int) -> list[str]:
    if not q:
        return []
    idx = _gloss_index()
    scored = ((vid, len(q & toks)) for vid, toks in idx.items())
    ranked = sorted((p for p in scored if p[1] > 0), key=lambda p: -p[1])
    return [vid for vid, _ in ranked[:limit]]


def merge_ids(*id_lists: list[str]) -> list[str]:
    """Concatenate ranked id lists preserving first-seen order (curated lists passed first)."""
    out: list[str] = []
    seen: set[str] = set()
    for ids in id_lists:
        for vid in ids:
            if vid not in seen:
                seen.add(vid)
                out.append(vid)
    return out


def curated_pool(query: str, corpus: Corpus | None = None) -> list[str]:
    """All reviewed theme_map / tag matches, ranked (curated authority) — WITHOUT the English gloss
    scan. The graph ranks this ABOVE the LLM navigator so a reviewed mapping is never buried by free
    full-book reasoning (QA H-5), while `strong` (≥2 overlap) still leads for the §7.2 guarantee."""
    corpus = corpus or get_corpus()
    q = _tokens(query)
    if not q:
        return []
    return _curated_rank(q, corpus)


def gloss_pool(query: str, k: int) -> list[str]:
    """Full-book English gloss keyword scan (lowest-confidence, last-resort coverage)."""
    return _gloss_rank(_tokens(query), limit=k)


def retrieve(query: str, corpus: Corpus | None = None, k: int = 3) -> list[dict]:
    """Deterministic candidates, curated-first then full-book gloss scan. No LLM (also the fallback).

    English glosses don't token-overlap a Hindi concern, so for Hindi queries the curated theme_map
    carries recall and the LLM navigator (which reasons cross-language) widens it in production.
    """
    corpus = corpus or get_corpus()
    book = get_book_index()
    q = _tokens(query)
    if not q:
        return []
    ordered = merge_ids(_curated_rank(q, corpus), _gloss_rank(q, limit=k * 3))
    ordered = [vid for vid in ordered if corpus.exists(vid) or book.has(vid)]
    return [build_candidate(vid, corpus, book) for vid in ordered[:k]]

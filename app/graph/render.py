"""Rendering helpers shared by the output node and the streaming layer.

`inject_verse` is the structural anti-hallucination step (plan §7.1): the model's {{VERSE}}
placeholder is replaced with canonical Sanskrit pulled from the corpus — never model-generated.
"""

from __future__ import annotations

import re

from app.llm.base import VERSE_PLACEHOLDER
from app.retrieval.corpus import Corpus

# A citation the model wrote itself (it shouldn't — the backend injects it). Matches
# "श्रीमद्भगवद्गीता (२.२०) —" / "गीता 2.20" with optional trailing dash, so we can remove it.
_MODEL_CITATION = re.compile(
    r"(श्रीमद्भगवद्गीता|गीता)\s*[\(（]?\s*[\d०-९]+\.[\d०-९]+\s*[\)）]?\s*[—–-]?\s*"
)


def _strip_model_citations(text: str) -> str:
    return _MODEL_CITATION.sub("", text)


def inject_verse(text: str, verse_id: str | None, corpus: Corpus) -> tuple[str, dict | None]:
    """Replace {{VERSE}} with canonical citation + Sanskrit from disk; build the verse_card.

    Returns (rendered_text, verse_card | None). Sanskrit here originates ONLY from the corpus.
    """
    if verse_id and corpus.exists(verse_id):
        cit_num = corpus.citation(verse_id).split()[-1]
        v = corpus.get_verse(verse_id)
        if v and v.get("sanskrit"):
            # canonical: reveal the citation + the verse's first Sanskrit line (from disk, never LLM)
            first_line = v["sanskrit"].splitlines()[0].rstrip("।॥ ")
            reveal = f"श्रीमद्भगवद्गीता ({cit_num}) — «{first_line}»"
        else:
            # full-book verse with no curated Sanskrit (mojibake in PDF) — cite by chapter.verse;
            # the verse_card carries the book's English translation + the clickable page.
            reveal = f"श्रीमद्भगवद्गीता ({cit_num})"
        # §7.1: the backend owns the citation. Strip any the model emitted itself, otherwise it
        # duplicates next to the injected one (cloud QA #4: "…गीता (२.२०) — …गीता (२.२०) —").
        text = _strip_model_citations(text)
        # inject at the FIRST placeholder only; drop any extra placeholders the model wrote
        rendered = text.replace(VERSE_PLACEHOLDER, reveal, 1).replace(VERSE_PLACEHOLDER, "")
        return rendered, corpus.verse_card(verse_id)

    # honest redirect — strip any dangling placeholder/connector, no invented verse
    rendered = text.replace(VERSE_PLACEHOLDER, "")
    rendered = re.sub(r"\s*[—-]\s*।", "।", rendered)
    rendered = re.sub(r"\s{2,}", " ", rendered).strip()
    return rendered, None


def word_stream(text: str) -> list[str]:
    """Chunk into space-preserving tokens for user-facing streaming (post-injection).

    The leading ``\\s*`` keeps any leading whitespace (e.g. the ``\\n\\n`` that separates the
    practical step / disclaimer from the guidance) — without it ``\\S+\\s*`` silently dropped the
    separator and ran the next block straight onto the previous sentence (e.g. "…ले जाओ।आज का…").
    """
    return re.findall(r"\s*\S+\s*", text)

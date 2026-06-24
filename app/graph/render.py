"""Rendering helpers shared by the output node and the streaming layer.

`inject_verse` is the structural anti-hallucination step (plan §7.1): the model's {{VERSE}}
placeholder is replaced with canonical Sanskrit pulled from the corpus — never model-generated.
"""

from __future__ import annotations

import re

from app.llm.base import VERSE_PLACEHOLDER
from app.retrieval.corpus import Corpus


def inject_verse(text: str, verse_id: str | None, corpus: Corpus) -> tuple[str, dict | None]:
    """Replace {{VERSE}} with canonical citation + Sanskrit from disk; build the verse_card.

    Returns (rendered_text, verse_card | None). Sanskrit here originates ONLY from the corpus.
    """
    if verse_id and corpus.exists(verse_id):
        v = corpus.get_verse(verse_id)
        first_line = v["sanskrit"].splitlines()[0].rstrip("।॥ ")
        reveal = f"श्रीमद्भगवद्गीता ({corpus.citation(verse_id).split()[-1]}) — «{first_line}»"
        rendered = text.replace(VERSE_PLACEHOLDER, reveal)
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

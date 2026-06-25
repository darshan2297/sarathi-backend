"""Book index (plan §5, Phase 3) — the full-book layer behind the vectorless RAG.

Loads the two artifacts built offline by `scripts/build_pageindex.py`:
  • verse_pages.json    — every verse (≈700) → exact PDF page + range + an English gloss
  • pageindex_tree.json — chapter→verse tree (drop-in replaceable by a real PageIndex tree)

It answers three questions the rest of the app needs:
  • where is this verse in the book?      → `page_for` / `meta`   (powers the clickable citation)
  • what does the book actually say here?  → `passage_for`         (English text that GROUNDS answers)
  • render a page for the viewer           → `render_png`          (Phase 2 endpoint)

The PDF is opened lazily and pages/passages are cached, so importing this module is cheap and the
test suite (which never touches the PDF) pays nothing.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.retrieval.corpus import to_devanagari_number

log = get_logger("sarathi.book")

_VERSE_MARK = re.compile(r"\bTEXTS?\s+\d")


def _english_only(text: str) -> str:
    """Keep clean Latin/ASCII lines; drop this PDF's mojibake Devanagari."""
    keep = []
    for ln in text.splitlines():
        s = ln.strip()
        if s and sum(c.isascii() for c in s) / len(s) >= 0.85:
            keep.append(s)
    return "\n".join(keep)


def _verse_passage(blob: str, max_chars: int) -> str:
    """From a verse's page text, return TRANSLATION + start of PURPORT, trimmed before the next verse."""
    blob = _english_only(blob)
    m = re.search(r"\bTRANSLATION\b", blob)
    if m:
        blob = blob[m.start():]
    # cut at the next verse marker so we don't bleed into the following verse
    nxt = _VERSE_MARK.search(blob, 30)
    if nxt:
        blob = blob[:nxt.start()]
    return re.sub(r"\s+", " ", blob).strip()[:max_chars]


class BookIndex:
    def __init__(self, corpus_dir: Path, pdf_path: Path) -> None:
        self.pdf_path = pdf_path
        self._pages: dict[str, dict] = {}
        self._tree: dict = {}
        self._doc = None  # lazy fitz.Document
        self._passage_cache: dict[str, str] = {}
        self._load(corpus_dir)

    def _load(self, corpus_dir: Path) -> None:
        vp = corpus_dir / "verse_pages.json"
        if vp.exists():
            self._pages = json.loads(vp.read_text(encoding="utf-8"))
        tree = corpus_dir / "pageindex_tree.json"
        if tree.exists():
            self._tree = json.loads(tree.read_text(encoding="utf-8"))

    # --- lookups ---
    def has(self, verse_id: str) -> bool:
        return verse_id in self._pages

    def meta(self, verse_id: str) -> dict | None:
        return self._pages.get(verse_id)

    def page_for(self, verse_id: str) -> int | None:
        m = self._pages.get(verse_id)
        return m["pdf_page"] if m else None

    def gloss(self, verse_id: str) -> str:
        m = self._pages.get(verse_id)
        return m.get("gloss_en", "") if m else ""

    @property
    def all_ids(self) -> list[str]:
        return list(self._pages)

    @property
    def chapters(self) -> list[dict]:
        return self._tree.get("chapters", [])

    @property
    def page_count(self) -> int:
        return int(self._tree.get("page_count", 0))

    def citation(self, verse_id: str) -> str | None:
        m = self._pages.get(verse_id)
        if not m:
            return None
        return f"गीता {to_devanagari_number(m['chapter'])}.{to_devanagari_number(m['verse'])}"

    # --- PDF-backed (lazy) ---
    def _open(self):
        if self._doc is None:
            import fitz  # imported lazily so non-PDF code paths/tests never load it
            self._doc = fitz.open(self.pdf_path)
        return self._doc

    def passage_for(self, verse_id: str, max_chars: int = 1500) -> str:
        """Clean English TRANSLATION + PURPORT for the verse — the evidence that grounds answers."""
        if verse_id in self._passage_cache:
            return self._passage_cache[verse_id]
        m = self._pages.get(verse_id)
        if not m:
            return ""
        try:
            doc = self._open()
            start = m["pdf_page"] - 1
            end = min(m.get("page_end", m["pdf_page"]), doc.page_count - 1)  # +1 page for spillover
            blob = "\n".join(doc[i].get_text() for i in range(start, end + 1))
            passage = _verse_passage(blob, max_chars)
        except Exception as exc:  # never let extraction crash a turn
            log.warning("passage_extract_failed", verse_id=verse_id, error=str(exc))
            passage = self.gloss(verse_id)
        self._passage_cache[verse_id] = passage
        return passage

    def render_png(self, page_1based: int, dpi: int | None = None) -> bytes:
        """Render a 1-based PDF page to PNG bytes (Phase 2 book viewer)."""
        doc = self._open()
        if not (1 <= page_1based <= doc.page_count):
            raise IndexError(f"page {page_1based} out of range 1..{doc.page_count}")
        pix = doc[page_1based - 1].get_pixmap(dpi=dpi or settings.book_page_dpi)
        return pix.tobytes("png")


@lru_cache(maxsize=1)
def get_book_index() -> BookIndex:
    return BookIndex(settings.corpus_dir, settings.pdf_path)

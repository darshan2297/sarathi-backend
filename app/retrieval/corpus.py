"""Corpus loader (plan §3). The single source of truth for canonical verse text.

CRITICAL (plan §7.1): every piece of Sanskrit that reaches a user comes from `get_verse()` here —
never from an LLM. This module is what makes fabricated scripture structurally impossible.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

_DEV_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")


def to_devanagari_number(n: int | str) -> str:
    return str(n).translate(_DEV_DIGITS)


class Corpus:
    def __init__(self, corpus_dir: Path) -> None:
        self.corpus_dir = corpus_dir
        self._verses: dict[str, dict] = {}
        self._tree: dict = {}
        self._theme_map: dict = {}
        self._load()

    def _load(self) -> None:
        verses_file = self.corpus_dir / "verses.json"
        if not verses_file.exists():
            raise FileNotFoundError(f"{verses_file} not found — run scripts/ingest_gita.py")
        for v in json.loads(verses_file.read_text(encoding="utf-8")):
            self._verses[v["id"]] = v

        tree_file = self.corpus_dir / "tree_index.json"
        if tree_file.exists():
            self._tree = json.loads(tree_file.read_text(encoding="utf-8"))

        theme_file = self.corpus_dir / "theme_map.json"
        if theme_file.exists():
            self._theme_map = json.loads(theme_file.read_text(encoding="utf-8"))

    @staticmethod
    def _book():
        # lazy import breaks the corpus↔book import cycle (book imports to_devanagari_number here)
        from app.retrieval.book import get_book_index
        return get_book_index()

    # --- accessors ---
    def get_verse(self, verse_id: str) -> dict | None:
        """Canonical verse record (rich Hindi/Sanskrit). None for verses we have not hand-curated;
        those are still retrievable/citable via the book index — see exists()/verse_card()."""
        return self._verses.get(verse_id)

    def is_canonical(self, verse_id: str) -> bool:
        return verse_id in self._verses

    def exists(self, verse_id: str) -> bool:
        """Resolvable to a real place in the book: canonical OR present in the page index (plan §7).
        This is the anti-fabrication gate — a cited verse must map to an actual PDF page."""
        return verse_id in self._verses or self._book().has(verse_id)

    @property
    def all_ids(self) -> list[str]:
        return list(self._verses)

    @property
    def tree(self) -> dict:
        return self._tree

    @property
    def themes(self) -> list[dict]:
        return self._theme_map.get("themes", [])

    def citation(self, verse_id: str) -> str:
        """Human citation like 'गीता २.४७' (Devanagari numerals). Works for the full book."""
        v = self.get_verse(verse_id)
        if v:
            return f"गीता {to_devanagari_number(v['chapter'])}.{to_devanagari_number(v['verse'])}"
        return self._book().citation(verse_id) or verse_id

    def page_for(self, verse_id: str) -> int | None:
        """1-based PDF page of the verse — the clickable book reference (plan §11)."""
        return self._book().page_for(verse_id)

    def verse_card(self, verse_id: str) -> dict | None:
        """The verse_card payload (plan §10 WS protocol), now carrying the book `pdf_page`.

        Canonical verses keep their reviewed Hindi/Sanskrit. Other verses (full-book coverage) show
        the book's own English translation + the page link — honest, drawn straight from the source;
        the Devanagari is NOT extracted here (it is mojibake in this PDF, plan risk note)."""
        v = self.get_verse(verse_id)
        if v:
            return {
                "id": v["id"],
                "citation": self.citation(verse_id),
                "sanskrit": v["sanskrit"],
                "transliteration": v["transliteration"],
                "translation_hi": v["translation_hi"],
                "word_meanings_hi": v["word_meanings_hi"],
                "pdf_page": self.page_for(verse_id),
            }
        book = self._book()
        if not book.has(verse_id):
            return None
        return {
            "id": verse_id,
            "citation": self.citation(verse_id),
            "sanskrit": "",
            "transliteration": "",
            "translation_hi": "",
            "translation_en": book.gloss(verse_id),
            "word_meanings_hi": "",
            "pdf_page": book.page_for(verse_id),
        }


@lru_cache(maxsize=1)
def get_corpus() -> Corpus:
    return Corpus(settings.corpus_dir)

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

    # --- accessors ---
    def get_verse(self, verse_id: str) -> dict | None:
        return self._verses.get(verse_id)

    def exists(self, verse_id: str) -> bool:
        return verse_id in self._verses

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
        """Human citation like 'गीता २.४७' (Devanagari numerals)."""
        v = self.get_verse(verse_id)
        if not v:
            return verse_id
        return f"गीता {to_devanagari_number(v['chapter'])}.{to_devanagari_number(v['verse'])}"

    def verse_card(self, verse_id: str) -> dict | None:
        """The verse_card payload (plan §10 WS protocol). All fields canonical, from disk."""
        v = self.get_verse(verse_id)
        if not v:
            return None
        return {
            "id": v["id"],
            "citation": self.citation(verse_id),
            "sanskrit": v["sanskrit"],
            "transliteration": v["transliteration"],
            "translation_hi": v["translation_hi"],
            "word_meanings_hi": v["word_meanings_hi"],
        }


@lru_cache(maxsize=1)
def get_corpus() -> Corpus:
    return Corpus(settings.corpus_dir)

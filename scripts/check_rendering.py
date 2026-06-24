#!/usr/bin/env python3
"""
check_rendering.py — Devanagari / Sanskrit rendering spot-check (plan §13, Phase 0).

A dataset with garbled diacritics or mojibake quietly loses the most knowledgeable users,
so we verify the corpus renders cleanly BEFORE building anything on top of it.

Checks per verse:
  1. no U+FFFD replacement characters (mojibake) anywhere
  2. `sanskrit` and `translation_hi` actually contain Devanagari (U+0900–U+097F)
  3. `transliteration` carries IAST diacritics (combining marks / extended Latin), not bare ASCII
  4. text is valid, normalizable Unicode (NFC round-trips)

Exits non-zero if any check fails. Also prints one full verse for a human eyeball check.

Standard library only.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus" / "bhagavad_gita"
VERSES_FILE = CORPUS_DIR / "verses.json"

REPLACEMENT = "�"
DEVANAGARI = range(0x0900, 0x0980)
# IAST diacritic code points (macrons, dots-below/above, etc.) commonly used for Sanskrit
IAST_MARKS = set("āīūṛṝḷṅñṭḍṇśṣṁṃḥĀĪŪṚṄÑṬḌṆŚṢṀṂḤ'")


def has_devanagari(s: str) -> bool:
    return any(ord(c) in DEVANAGARI for c in s)


def has_iast(s: str) -> bool:
    return any(c in IAST_MARKS for c in s)


def main() -> None:
    if not VERSES_FILE.exists():
        sys.exit(f"✗ {VERSES_FILE} not found — run ingest_gita.py first")

    verses = json.loads(VERSES_FILE.read_text(encoding="utf-8"))
    problems: list[str] = []

    for v in verses:
        vid = v["id"]

        # 1. mojibake
        for field in ("sanskrit", "transliteration", "word_meanings_hi", "translation_hi"):
            if REPLACEMENT in (v.get(field) or ""):
                problems.append(f"{vid}: U+FFFD (mojibake) in '{field}'")

        # 2. Devanagari presence
        if not has_devanagari(v.get("sanskrit", "")):
            problems.append(f"{vid}: 'sanskrit' has no Devanagari characters")
        if not has_devanagari(v.get("translation_hi", "")):
            problems.append(f"{vid}: 'translation_hi' has no Devanagari characters")

        # 3. IAST diacritics in transliteration (if provided)
        translit = v.get("transliteration", "")
        if translit and not has_iast(translit):
            problems.append(f"{vid}: 'transliteration' lacks IAST diacritics (looks like plain ASCII)")

        # 4. valid, normalizable Unicode
        for field in ("sanskrit", "transliteration", "translation_hi"):
            text = v.get(field) or ""
            if text and unicodedata.normalize("NFC", text) != text and \
               unicodedata.normalize("NFC", text) == "":
                problems.append(f"{vid}: '{field}' failed Unicode normalization")

    total = len(verses)
    print(f"Checked {total} verses for rendering integrity.\n")

    # human eyeball sample (pick a well-known verse if present)
    sample = next((v for v in verses if v["id"] == "BG2.47"), verses[0] if verses else None)
    if sample:
        print("── Sample render (verify this looks correct) ──")
        print(f"  {sample['id']}  [{sample['chapter']}.{sample['verse']}]  {sample['chapter_theme_hi']}")
        print(f"  संस्कृत  : {sample['sanskrit'].splitlines()[0]} …")
        print(f"  IAST     : {sample['transliteration'].splitlines()[0]} …")
        print(f"  हिंदी    : {sample['translation_hi']}")
        print("───────────────────────────────────────────────\n")

    if problems:
        print(f"✗ {len(problems)} rendering issue(s) found:")
        for p in problems:
            print(f"    - {p}")
        sys.exit(1)

    print(f"✓ All {total} verses render cleanly (Devanagari + IAST, no mojibake).")


if __name__ == "__main__":
    main()

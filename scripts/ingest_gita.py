#!/usr/bin/env python3
"""
ingest_gita.py — normalize raw Bhagavad Gita source files into the canonical verses.json.

Pipeline (Phase 0):
    raw/*.json  ->  validate + normalize + de-dupe + sort  ->  verses.json

Each raw verse object must contain at least:
    chapter (int), verse (int), sanskrit (str), translation_hi (str)
Optional fields are preserved: transliteration, word_meanings_hi, translation_en,
chapter_theme_hi, tags.

The canonical `id` is derived as  BG<chapter>.<verse>  (e.g. BG2.47) so the rest of the
system can inject verse text by id (see plan §7.1 — the LLM never writes Sanskrit).

Standard library only; safe to run anytime.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# --- paths (relative to backend/) ---
CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus" / "bhagavad_gita"
RAW_DIR = CORPUS_DIR / "raw"
OUT_FILE = CORPUS_DIR / "verses.json"

REQUIRED = ("chapter", "verse", "sanskrit", "translation_hi")
OPTIONAL = ("transliteration", "word_meanings_hi", "translation_en", "chapter_theme_hi", "tags")


def verse_id(chapter: int, verse: int) -> str:
    return f"BG{chapter}.{verse}"


def load_raw() -> list[dict]:
    if not RAW_DIR.is_dir():
        sys.exit(f"✗ raw directory not found: {RAW_DIR}")
    raw_files = sorted(RAW_DIR.glob("*.json"))
    if not raw_files:
        sys.exit(f"✗ no raw *.json files in {RAW_DIR}")

    records: list[dict] = []
    for f in raw_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit(f"✗ {f.name}: invalid JSON — {e}")
        if not isinstance(data, list):
            sys.exit(f"✗ {f.name}: expected a JSON array of verse objects")
        print(f"  • {f.name}: {len(data)} records")
        records.extend(data)
    return records


def normalize(records: list[dict]) -> list[dict]:
    seen: dict[str, str] = {}
    out: list[dict] = []
    errors: list[str] = []

    for i, r in enumerate(records):
        missing = [k for k in REQUIRED if k not in r or r[k] in (None, "")]
        if missing:
            errors.append(f"record #{i}: missing required field(s): {', '.join(missing)}")
            continue
        try:
            ch, vs = int(r["chapter"]), int(r["verse"])
        except (TypeError, ValueError):
            errors.append(f"record #{i}: chapter/verse must be integers")
            continue

        vid = verse_id(ch, vs)
        if vid in seen:
            errors.append(f"duplicate verse id {vid}")
            continue
        seen[vid] = vid

        norm = {
            "id": vid,
            "chapter": ch,
            "verse": vs,
            "sanskrit": str(r["sanskrit"]).strip(),
            "transliteration": str(r.get("transliteration", "")).strip(),
            "word_meanings_hi": str(r.get("word_meanings_hi", "")).strip(),
            "translation_hi": str(r["translation_hi"]).strip(),
            "translation_en": str(r.get("translation_en", "")).strip(),
            "chapter_theme_hi": str(r.get("chapter_theme_hi", "")).strip(),
            "tags": list(r.get("tags", []) or []),
        }
        out.append(norm)

    if errors:
        print("\n✗ Validation errors:")
        for e in errors:
            print(f"    - {e}")
        sys.exit(1)

    out.sort(key=lambda v: (v["chapter"], v["verse"]))
    return out


def main() -> None:
    print(f"Ingesting raw Gita sources from: {RAW_DIR}")
    records = load_raw()
    verses = normalize(records)

    OUT_FILE.write_text(
        json.dumps(verses, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    chapters = sorted({v["chapter"] for v in verses})
    print(f"\n✓ Wrote {len(verses)} verses → {OUT_FILE}")
    print(f"  chapters present: {chapters}")
    print(f"  ids: {', '.join(v['id'] for v in verses)}")


if __name__ == "__main__":
    main()

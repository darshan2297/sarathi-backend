#!/usr/bin/env python3
"""
build_tree_index.py — build the vectorless PageIndex tree from verses.json (plan §5).

The Bhagavad Gita is naturally hierarchical:
    root  ->  chapter (with theme + summary)  ->  verse leaf (id + short gloss)

At query time an LLM *reasons* down this tree ("which chapter's theme matches this
problem? which verse within it?") instead of doing embedding similarity search.

Phase 0 builds the tree DETERMINISTICALLY from the data we already have:
  - chapter theme  = `chapter_theme_hi`
  - chapter summary = auto-derived from the verses' tags  (marked for LLM enrichment in Phase 3)
  - verse gloss     = a short clause from `translation_hi`

Standard library only.
"""

from __future__ import annotations

import json
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus" / "bhagavad_gita"
VERSES_FILE = CORPUS_DIR / "verses.json"
OUT_FILE = CORPUS_DIR / "tree_index.json"

GLOSS_MAX = 90


def short_gloss(translation_hi: str) -> str:
    """First clause of the Hindi translation, trimmed — a navigation hint, not the full verse."""
    text = translation_hi.strip()
    for sep in ("।", ";", "—", "."):
        if sep in text:
            text = text.split(sep)[0].strip()
            break
    if len(text) > GLOSS_MAX:
        text = text[:GLOSS_MAX].rstrip() + "…"
    return text


def build() -> dict:
    if not VERSES_FILE.exists():
        raise SystemExit(f"✗ {VERSES_FILE} not found — run ingest_gita.py first")

    verses = json.loads(VERSES_FILE.read_text(encoding="utf-8"))

    chapters: dict[int, dict] = {}
    for v in verses:
        ch = v["chapter"]
        node = chapters.setdefault(
            ch,
            {
                "chapter": ch,
                "theme_hi": v.get("chapter_theme_hi", ""),
                "summary_hi": "",
                "summary_source": "auto (enrich with LLM in Phase 3)",
                "key_concepts": [],
                "verses": [],
            },
        )
        node["verses"].append(
            {"id": v["id"], "verse": v["verse"], "gloss_hi": short_gloss(v["translation_hi"])}
        )
        # accumulate distinct, human-readable (Devanagari) tags as key concepts
        for tag in v.get("tags", []):
            if any("ऀ" <= c <= "ॿ" for c in tag) and tag not in node["key_concepts"]:
                node["key_concepts"].append(tag)

    for node in chapters.values():
        node["verses"].sort(key=lambda x: x["verse"])
        concepts = ", ".join(node["key_concepts"]) or "—"
        node["summary_hi"] = (
            f"अध्याय {node['chapter']} — {node['theme_hi']}। "
            f"मुख्य विषय: {concepts}।"
        )

    return {
        "scripture": "bhagavad_gita",
        "title_hi": "श्रीमद्भगवद्गीता",
        "note": "Vectorless PageIndex tree — LLM navigates this by reasoning (plan §5). "
        "Chapter summaries are auto-derived in Phase 0; enrich with an LLM in Phase 3.",
        "verse_count": len(verses),
        "chapters": [chapters[c] for c in sorted(chapters)],
    }


def main() -> None:
    tree = build()
    OUT_FILE.write_text(json.dumps(tree, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ Wrote tree index → {OUT_FILE}")
    print(f"  {tree['verse_count']} verses across {len(tree['chapters'])} chapter(s)")
    for ch in tree["chapters"]:
        print(f"  • अध्याय {ch['chapter']} ({ch['theme_hi']}): {len(ch['verses'])} verses")


if __name__ == "__main__":
    main()

"""Offline ingestion — build the page index over the Bhagavad-Gita PDF (plan §5, Phase 3).

This is the DETERMINISTIC half of the "vectorless RAG" build (run once, no LLM, no cost):

  PDF ──PyMuPDF scan──▶ data/corpus/.../verse_pages.json   (chapter,verse) → exact PDF page + range
                       ▶ data/corpus/.../pageindex_tree.json  chapter→verse tree w/ English glosses

The page map is what powers the clickable "open the book at this page" citation, and the per-verse
English TRANSLATION/PURPORT (extracted clean — the Devanagari in this scan is mojibake and is
deliberately ignored) is what grounds the Hindi answer. A real PageIndex-built semantic tree can be
dropped in later at the same path without changing any consumer (app/retrieval/book.py).

Run:
    poetry run python scripts/build_pageindex.py
    poetry run python scripts/build_pageindex.py --pdf <path> --out <dir>

Idempotent: re-running overwrites the two JSON outputs and reprints coverage.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PDF = BACKEND_DIR / "aessets" / "Bhagavad-Gita As It Is (Original 1972 Edition).pdf"
DEFAULT_OUT = BACKEND_DIR / "data" / "corpus" / "bhagavad_gita"

# Canonical verse counts for "Bhagavad-gita As It Is" (1972) — used only to report coverage.
EXPECTED_VERSES = {1: 46, 2: 72, 3: 43, 4: 42, 5: 29, 6: 47, 7: 30, 8: 28, 9: 34,
                   10: 42, 11: 55, 12: 20, 13: 35, 14: 27, 15: 20, 16: 24, 17: 28, 18: 78}

# A page's running header is "Chapter-N" on (and only on) that chapter's first page.
_CHAPTER = re.compile(r"^Chapter-(\d+)\b", re.MULTILINE)
# Verse markers: "TEXT 47" or combined "TEXTS 16-18" / "TEXTS 16–18".
_VERSE = re.compile(r"\bTEXTS?\s+(\d+)\s*(?:[–-]\s*(\d+))?\b")


def _chapter_on_page(text: str) -> int | None:
    m = _CHAPTER.search(text)
    return int(m.group(1)) if m else None


def _chapter_title(text: str) -> str:
    """Best-effort English title from a chapter-start page (lines between CHAPTER X and TEXT 1)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    try:
        start = next(i for i, ln in enumerate(lines) if ln.upper().startswith("CHAPTER "))
    except StopIteration:
        return ""
    title: list[str] = []
    for ln in lines[start + 1:]:
        if _VERSE.search(ln) or ln.lower().startswith(("text", "translation", "purport")):
            break
        title.append(ln)
        if len(title) >= 3:
            break
    return " ".join(title).strip()


def _verses_on_page(text: str) -> list[int]:
    """Every verse number declared on a page, combined ranges expanded, in reading order."""
    nums: list[int] = []
    for m in _VERSE.finditer(text):
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        if 1 <= lo <= hi <= 200:  # sanity bound; expand combined "TEXTS a-b"
            nums.extend(range(lo, hi + 1))
    return nums


def _clean(text: str) -> str:
    """Keep clean ASCII/Latin lines (English); drop mojibake Devanagari lines from this PDF."""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        ascii_ratio = sum(c.isascii() for c in s) / len(s)
        if ascii_ratio >= 0.85:
            out.append(s)
    return "\n".join(out)


def build(pdf_path: Path, out_dir: Path) -> dict:
    doc = fitz.open(pdf_path)
    pages = [doc[i].get_text() for i in range(doc.page_count)]

    # 1) chapter boundaries (1-based pdf pages) + titles
    chapter_start: dict[int, int] = {}   # chapter -> 1-based pdf page
    chapter_title: dict[int, str] = {}
    for i, t in enumerate(pages):
        ch = _chapter_on_page(t)
        if ch is not None and ch not in chapter_start:
            chapter_start[ch] = i + 1
            chapter_title[ch] = _chapter_title(t)

    # 2) verse → first page it is declared on (within the running chapter)
    verse_page: dict[str, int] = {}        # "BG2.47" -> 1-based pdf page
    verse_meta: dict[str, dict] = {}
    ordered: list[str] = []                # verse ids in document order (for page_end)
    current = None
    for i, t in enumerate(pages):
        ch = _chapter_on_page(t)
        if ch is not None:
            current = ch
        if current is None:
            continue  # still in front matter
        for v in _verses_on_page(t):
            vid = f"BG{current}.{v}"
            if vid not in verse_page:
                verse_page[vid] = i + 1
                verse_meta[vid] = {"chapter": current, "verse": v, "pdf_page": i + 1}
                ordered.append(vid)

    # 3) page_end = page before the next verse starts (purport can span pages)
    for idx, vid in enumerate(ordered):
        start = verse_meta[vid]["pdf_page"]
        nxt = verse_meta[ordered[idx + 1]]["pdf_page"] if idx + 1 < len(ordered) else doc.page_count
        verse_meta[vid]["page_end"] = max(start, nxt - 1) if nxt > start else start

    # 4) per-verse English gloss (TRANSLATION block) for the navigator/tree
    for vid, meta in verse_meta.items():
        s, e = meta["pdf_page"] - 1, meta["page_end"] - 1
        # include one extra page so a TRANSLATION that spills past page_end still yields a gloss
        blob = _clean("\n".join(pages[s:min(e + 2, len(pages))]))
        meta["gloss_en"] = _translation_block(blob)

    # 5) assemble the navigable tree (chapter → verses), grouped + sorted
    chapters = []
    for ch in sorted(chapter_start):
        vids = sorted((v for v in verse_meta if verse_meta[v]["chapter"] == ch),
                      key=lambda v: verse_meta[v]["verse"])
        chapters.append({
            "chapter": ch,
            "title": chapter_title.get(ch, ""),
            "pdf_page": chapter_start[ch],
            "verse_count": len(vids),
            "verses": [{"id": v, "verse": verse_meta[v]["verse"],
                        "pdf_page": verse_meta[v]["pdf_page"], "gloss_en": verse_meta[v]["gloss_en"]}
                       for v in vids],
        })

    tree = {
        "scripture": "bhagavad_gita",
        "title": "Bhagavad-gita As It Is (Original 1972 Edition)",
        "source_pdf": pdf_path.name,
        "page_count": doc.page_count,
        "build": "deterministic-scan-v1",
        "note": "Chapter→verse tree with exact PDF pages + English glosses. A PageIndex-built "
                "semantic tree may replace this file later (same consumer: app/retrieval/book.py).",
        "chapters": chapters,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "verse_pages.json").write_text(
        json.dumps(verse_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "pageindex_tree.json").write_text(
        json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")

    _report(verse_meta)
    return verse_meta


def _translation_block(blob: str) -> str:
    """Extract the English TRANSLATION paragraph (between TRANSLATION and PURPORT), one line."""
    m = re.search(r"\bTRANSLATION\b(.*?)(?:\bPURPORT\b|\Z)", blob, re.DOTALL)
    chunk = m.group(1) if m else blob
    chunk = re.sub(r"\s+", " ", chunk).strip()
    return chunk[:240]


def _report(verse_meta: dict) -> None:
    found_by_ch: dict[int, int] = {}
    for meta in verse_meta.values():
        found_by_ch[meta["chapter"]] = found_by_ch.get(meta["chapter"], 0) + 1
    total_found = len(verse_meta)
    total_expected = sum(EXPECTED_VERSES.values())
    print(f"\n=== coverage: {total_found}/{total_expected} verses mapped to pages ===")
    for ch in sorted(EXPECTED_VERSES):
        f, exp = found_by_ch.get(ch, 0), EXPECTED_VERSES[ch]
        flag = "" if f == exp else "  <-- MISMATCH"
        print(f"  ch{ch:>2}: {f:>3}/{exp:<3}{flag}")
    for probe in ("BG2.47", "BG6.35", "BG2.14", "BG18.66"):
        m = verse_meta.get(probe)
        print(f"  {probe}: page {m['pdf_page']}-{m['page_end']}" if m else f"  {probe}: MISSING")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build deterministic page index over the Gita PDF.")
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    if not args.pdf.exists():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 2
    build(args.pdf, args.out)
    print(f"\nwrote: {args.out/'verse_pages.json'}\n       {args.out/'pageindex_tree.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

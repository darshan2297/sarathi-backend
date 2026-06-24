# Bhagavad Gita corpus — sourcing & licensing

## Sanskrit text & transliteration
The original Sanskrit ślokas of the Bhagavad Gita are **public domain** (ancient text).
The IAST transliteration is a mechanical/scholarly rendering, also free to use.

## Hindi & English translations
**The `translation_hi` / `word_meanings_hi` fields in this corpus are ORIGINAL, plain-language
renderings authored for this project.** They are intentionally *not* copied from any specific
published edition (e.g. Gita Press, or any copyrighted commentary), to avoid licensing issues and
to match Sarathi's own simple, warm Hindi voice. They aim for faithful meaning, not literary reuse.

`translation_en` (where present) is likewise an original plain rendering, kept only as a secondary
field for future use (v1 is Hindi-only).

## Adding a full 700-verse dataset later
When sourcing a complete dataset, confirm its license permits use and record it here. Candidates to
evaluate (verify license at integration time — do not assume):
- Open Gita datasets / APIs that publish under permissive terms.
- Public-domain translations (e.g. older works out of copyright) if a Hindi PD source is found.

Run `python scripts/ingest_gita.py` to normalize any raw source in `raw/` into `verses.json`.

## Current seed
The current `verses.json` is a hand-authored **seed** of widely-known, theologically central verses
(BG 2.14, 2.20, 2.22, 2.47, 2.48, 2.62, 2.63, 3.35) — enough to build the tree index, theme map, and
run downstream phases end-to-end. The theme_map and translations require review by a Gita-literate
person before any public launch (see plan §7.2).

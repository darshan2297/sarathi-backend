"""Phase 3 proof — full-book vectorless RAG: page-grounded retrieval + clickable citations.

These pin the deterministic (no-LLM) path that ships keyless and backs the LLM navigator:
  • the book index covers the whole Gita (~700 verses), not just the 10 curated ones,
  • passages are clean English (the grounding evidence; Devanagari is intentionally not extracted),
  • retrieval returns candidates carrying an exact pdf_page + citation,
  • corpus is page-aware for non-curated verses too (anti-fabrication = resolvable-to-a-page),
  • every grounded answer's done/verse_card carries the pdf_page (the clickable book reference),
  • the §7.2 restless-mind guarantee still holds end-to-end.
"""

from __future__ import annotations

import asyncio

from app.graph.pipeline import run_turn
from app.retrieval.book import get_book_index
from app.retrieval.corpus import get_corpus
from app.retrieval.pageindex import retrieve

GRIEF = "मेरे पिता का देहांत हो गया, मैं स्वीकार नहीं कर पा रहा"


def collect(user_message: str, history=None) -> list[dict]:
    async def _run():
        return [ev async for ev in run_turn(
            user_message=user_message, history=history or [], turn_id="t", stream_delay_ms=0)]
    return asyncio.run(_run())


# --- the book layer ---

def test_book_index_covers_the_whole_gita():
    b = get_book_index()
    assert len(b.all_ids) >= 700
    assert len(b.chapters) == 18 and b.page_count == 967
    # a verse that is NOT in the curated 10 is still in the book and resolvable to a page
    assert b.has("BG4.7") and not get_corpus().is_canonical("BG4.7")
    assert b.page_for("BG4.7")


def test_passage_is_clean_english_grounding():
    p = get_book_index().passage_for("BG2.47")
    assert "prescribed duty" in p and "fruits of action" in p   # the book's own translation
    assert p.isascii()                                          # no mojibake Devanagari leaks in


# --- retrieval returns page-grounded candidates ---

def test_retrieve_candidates_carry_page_and_citation():
    cands = retrieve(GRIEF, get_corpus(), k=3)
    assert cands and all(c["id"] for c in cands)
    top = cands[0]
    assert top["pdf_page"] and isinstance(top["pdf_page"], int)
    assert top["citation"].startswith("गीता")


def test_corpus_is_page_aware_for_noncurated_verses():
    c = get_corpus()
    assert c.exists("BG4.7")                       # anti-fabrication gate: resolvable to a page
    card = c.verse_card("BG4.7")
    assert card and card["pdf_page"] and card["translation_en"]


# --- end-to-end: the clickable page reaches the client ---

def test_done_and_verse_card_carry_pdf_page():
    events = collect(GRIEF)
    done = next(e for e in events if e["type"] == "done")
    assert done["grounded"] is True and done["verse_id"] and done["pdf_page"]
    cards = [e for e in events if e["type"] == "verse_card"]
    assert cards and cards[0]["pdf_page"]


def test_book_page_endpoint_serves_png():
    from starlette.testclient import TestClient

    from app.main import app
    with TestClient(app) as client:
        assert client.get("/book/meta").json()["page_count"] == 967
        r = client.get("/book/page/127")
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"      # real PNG bytes
        assert client.get("/book/page/100000").status_code == 404   # out of range


def test_restless_mind_still_leads_BG6_35():
    ids = [c["id"] for c in retrieve(
        "मेरा मन बहुत बेचैन रहता है, हर समय सोचता हूँ और ध्यान नहीं लगता", get_corpus())]
    assert ids[0] == "BG6.35"
    assert "BG2.62" not in ids[:2]
